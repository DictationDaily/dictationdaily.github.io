"""Record short screen recordings of the app for the guide (videos/*.mp4).

A fake pointer and a caption bar are drawn over the frames (cap_render.py) so learners can follow
each step. Frames come from Chrome's screencast and are encoded with ffmpeg. Every scene is signed
in as the Demo Learner (words_demo.py, learner_demo.py, playlists_demo.py): a Pro learner of French
whose every /api answer is made up in the browser, so nothing is read from or written to any
account (or, with DD_SESSION, a real Pro account read-only, see pro_session.py).

usage: [DD_BASE=http://localhost:8788] python3 scripts/record.py [scene ...]
       python3 scripts/record.py --render [--lang vi] [scene ...]  (redraw kept takes)
DD_BASE records a local build instead of production, e.g. before a UI change
is deployed (dictationdaily.com: tests/e2e/local_worker.sh).
scenes: see SCENES at the end (and mobile). Every lesson opens on Bizzy's question
(Listening or Speaking): scenes press it where they used to press START.
"""
import base64
import html
import json
import time
import os
import re
import shutil
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

import cap_render

import pro_session

B = os.environ.get('DD_BASE', 'https://dictationdaily.com').rstrip('/')
VIDEO = 'g4IAa8wZlqU'  # Sir Ken Robinson, 2:15, opens with an exercise
# Opens with a "Just listen" part. A local build has only a few transcripts; this one is among them
LISTEN_VIDEO = '-BvcToPZCLI' if 'DD_BASE' in os.environ else 'Tp8xIgyyK7I'
CLIP1 = 'My contention is all kids have tremendous talents,'  # exercise 1 since the 2026-10 re-segmenting
# The lesson gives one word each side ("My … talents,"); learners type the rest
REST = ' have tremendous'
OUT = 'videos'
RECORDING = None  # the Recorder running now, for its chapters and events
TOUCH_PAGES = set()  # pages recorded as a phone: a finger instead of a pointer

OVERLAY = r"""
(() => {
  if (window.__overlay) return;
  window.__overlay = true;
  const add = () => {
    const style = document.createElement('style');
    style.textContent = `
      #__cur{position:fixed;left:0;top:0;width:28px;height:28px;z-index:2147483647;pointer-events:none;
        transform:translate(-100px,-100px);transition:transform .7s cubic-bezier(.4,.0,.2,1);filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}
      #__cur.touch{width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;background:rgba(213,39,40,.35);border:3px solid #d52728}
      .__ripple{position:fixed;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;border:3px solid #d52728;
        z-index:2147483646;pointer-events:none;animation:__r .6s ease-out forwards}
      @keyframes __r{to{transform:scale(4);opacity:0}}
      #__cap{position:fixed;left:50%;bottom:92px;transform:translate(-50%,20px);opacity:0;z-index:2147483645;pointer-events:none;
        background:#212121;color:#fff;font:700 26px/1.3 Nunito,system-ui,sans-serif;padding:14px 26px;border-radius:999px;
        box-shadow:0 10px 30px rgba(0,0,0,.35);transition:all .35s ease;white-space:nowrap}
      #__cap.on{opacity:1;transform:translate(-50%,0)}
      #__cap b{color:#ff6b6b;margin-right:10px}
      #__cap.small{font-size:30px;bottom:150px;white-space:normal;width:86%;text-align:center}
      #__cur,#__cap,.__ripple{display:none!important}`;
    document.head.appendChild(style);
    const cur = document.createElement('div');
    cur.id = '__cur';
    cur.innerHTML = '<svg viewBox="0 0 24 24" width="28" height="28"><path d="M3 2l16 10-7 1.5L8.5 21z" fill="#fff" stroke="#000" stroke-width="1.5" stroke-linejoin="round"/></svg>';
    const cap = document.createElement('div');
    cap.id = '__cap';
    document.body.append(cur, cap);
  };
  if (document.body) add(); else addEventListener('DOMContentLoaded', add);
  window.__move = (x, y) => { document.getElementById('__cur').style.transform = `translate(${x}px,${y}px)`; };
  window.__ripple = (x, y) => {
    const r = document.createElement('div'); r.className = '__ripple';
    r.style.left = x + 'px'; r.style.top = y + 'px'; document.body.appendChild(r); setTimeout(() => r.remove(), 700);
  };
  window.__caption = (html, small) => {
    const c = document.getElementById('__cap');
    if (!html) { c.classList.remove('on'); return; }
    c.innerHTML = html; c.classList.toggle('small', !!small); c.classList.add('on');
  };
  window.__touch = () => { const c = document.getElementById('__cur'); c.classList.add('touch'); c.innerHTML = ''; };
})();
"""


class Recorder:
    def __init__(self, page, name, size):
        self.page, self.name, self.size = page, name, size
        self.dir = tempfile.mkdtemp(prefix=f'rec-{name}-')
        self.frames = []
        self.stopped = False
        self.poster_at = None
        self.chapters = []  # (wall time, caption): the steps listed beside the video
        # pointer, clicks, typing and captions, drawn by cap_render.py
        self.events = []
        self.touch = page in TOUCH_PAGES
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on('Page.screencastFrame', self._frame)

    def _frame(self, e):
        if self.stopped:
            return
        path = os.path.join(self.dir, f'{len(self.frames):05d}.jpg')
        with open(path, 'wb') as f:
            f.write(base64.b64decode(e['data']))
        self.frames.append((path, e['metadata']['timestamp']))
        try:
            self.cdp.send('Page.screencastFrameAck', {'sessionId': e['sessionId']})
        except Exception:
            pass

    def poster(self):
        """Use the current moment as the still shown before the video plays."""
        self.page.wait_for_timeout(200)
        self.poster_at = self.frames[-1][1] - self.frames[0][1] if self.frames else 0

    def chapter(self, text):
        """A caption shown now: a step of the walkthrough (videos/<name>.json)."""
        text = _step_text(text)
        if text and (not self.chapters or self.chapters[-1][1] != text):
            self.chapters.append((time.time(), text))

    def log(self, kind, **e):
        self.events.append({'k': kind, 't': time.time(), **e})

    def start(self):
        global RECORDING
        RECORDING = self
        w, h = self.size
        self.cdp.send('Page.startScreencast', {'format': 'jpeg', 'quality': 88, 'maxWidth': w, 'maxHeight': h})

    def stop(self, out_width):
        self.page.wait_for_timeout(300)
        self.cdp.send('Page.stopScreencast')
        self.stopped = True
        # Keep the take (frames + what happened), so the video can be drawn
        # again with other zoom settings: record.py --render <scene>
        take = os.path.join(TAKES, self.name)
        shutil.rmtree(take, ignore_errors=True)
        os.makedirs(TAKES, exist_ok=True)
        shutil.move(self.dir, take)
        frame_w = cap_render.Image.open(self.frames[0][0].replace(self.dir, take)).size[0]
        with open(os.path.join(take, 'take.json'), 'w') as f:
            json.dump({'frames': [[os.path.basename(p), t] for p, t in self.frames], 'events': self.events,
                       'out_width': out_width, 'scale': frame_w / self.page.viewport_size['width'],
                       'touch': self.touch, 'poster_at': self.poster_at}, f)
        render_take(self.name)
        t0 = self.frames[0][1]
        end = self.frames[-1][1] - t0
        steps = [{'t': round(max(0.0, t - t0), 2), 'text': text} for t, text in self.chapters]
        with open(f'{OUT}/{self.name}.json', 'w') as f:
            json.dump({'duration': round(end, 2), 'steps': steps}, f, ensure_ascii=False, indent=1)


TAKES = os.path.expanduser('~/.cache/dd-guide/takes')
GLIDE = 0.7  # seconds the drawn pointer takes to glide to a new spot


def _step_text(text):
    """A caption as a step of the list beside the video."""
    text = html.unescape(re.sub(r'<b>\d+</b>', '', text))
    text = re.sub(r'<[^>]+>', '', text).strip()
    return re.sub(r'^\d+\.\s*', '', text)  # the list numbers its steps itself


def render_take(name, lang=None):
    """Draw videos/<name>.mp4 and .jpg from the kept take. With lang (vi), the
    captions come from scripts/captions.<lang>.json and the video, poster and
    steps go to videos/<lang>/ for the guide in that language."""
    take = os.path.join(TAKES, name)
    with open(os.path.join(take, 'take.json')) as f:
        d = json.load(f)
    out, events = OUT, d['events']
    if lang:
        with open(os.path.join(os.path.dirname(__file__), f'captions.{lang}.json')) as f:
            words = json.load(f)
        out = f'{OUT}/{lang}'
        events = [{**e, 'html': words[e['html']]} if e['k'] == 'cap' and e['html'] else e for e in events]
    os.makedirs(out, exist_ok=True)
    frames = [(os.path.join(take, p), t) for p, t in d['frames']]
    mp4 = f'{out}/{name}.mp4'
    cap_render.render(frames, events, mp4, d['out_width'], scale=d['scale'], touch=d['touch'],
                      poster_at=d['poster_at'], poster_path=f'{out}/{name}.jpg')
    if lang:
        # the steps beside the video, at the times of the English ones
        with open(f'{OUT}/{name}.json') as f:
            meta = json.load(f)
        texts = []
        for e in events:
            text = e['k'] == 'cap' and e['html'] and _step_text(e['html'])
            if text and (not texts or texts[-1] != text):
                texts.append(text)
        assert len(texts) == len(meta['steps']), f'{name}: {len(texts)} captions, {len(meta["steps"])} steps'
        meta['steps'] = [{**st, 'text': t} for st, t in zip(meta['steps'], texts)]
        with open(f'{out}/{name}.json', 'w') as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
    print('drew', mp4, f'{os.path.getsize(mp4) // 1024} KB', flush=True)


def log(kind, **e):
    if RECORDING is not None and not RECORDING.stopped:
        RECORDING.log(kind, **e)


def place(page, x, y):
    """Put the pointer here, without a glide."""
    page.evaluate(f'window.__move({x},{y})')
    page.mouse.move(x, y)
    log('pos', x=x, y=y)


def type_(loc, text, delay=60):
    """Type into loc: the video zooms in on it while the letters appear."""
    box = loc.bounding_box()
    t0 = time.time()
    loc.press_sequentially(text, delay=delay)
    if box and RECORDING is not None and not RECORDING.stopped:
        RECORDING.events.append({'k': 'focus', 't': t0, 't1': time.time(),
                                 'x': box['x'] + min(box['width'], 520) / 2, 'y': box['y'] + box['height'] / 2})


def into_box(move_to, click, loc):
    """Click an empty part of a text box, as a learner does before typing, then
    rest the pointer low in the same column, above the bottom bar. Left on the
    box it hides the words being typed; just under it, the hint, the whole
    answer or a button that appears there after CHECK (CONTINUE, Éç)."""
    b = loc.bounding_box()
    click((b['x'] + b['width'] - 110, b['y'] + b['height'] * 0.7), 300)
    move_to((b['x'] + b['width'] * 0.55, loc.page.viewport_size['height'] - 110), 300)


def look(page, loc, secs):
    """Point at loc for secs: the video zooms in on it as for a click."""
    box = loc.bounding_box()
    t0 = time.time()
    page.wait_for_timeout(round(secs * 1000))
    if box and RECORDING is not None and not RECORDING.stopped:
        RECORDING.events.append({'k': 'focus', 't': t0, 't1': time.time(),
                                 'x': box['x'] + box['width'] / 2, 'y': box['y'] + box['height'] / 2})


def helpers(page, touch=False):
    if touch:
        TOUCH_PAGES.add(page)

    def move_to(loc_or_xy, wait=750, glide=GLIDE):
        if isinstance(loc_or_xy, tuple):
            x, y = loc_or_xy
        else:
            box = loc_or_xy.bounding_box()
            x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        page.evaluate(f'window.__move({x},{y})')
        log('move', x=x, y=y, dur=glide)
        # The drawn pointer takes `glide` seconds to get there (cap_render.py).
        # Nothing may happen before it arrives: a click, a drag or a hover
        # would show in the video while the pointer is still on its way.
        page.wait_for_timeout(round(glide * 1000) + 50)
        # The real mouse follows the drawn pointer: a click leaves it where it
        # clicked, and a button that later appears there (CONTINUE where
        # START was) would open its tooltip in the recording
        page.mouse.move(x, y)
        page.wait_for_timeout(max(0, wait - round(glide * 1000) - 50))
        return x, y

    def click(loc_or_xy, wait=750):
        x, y = move_to(loc_or_xy, wait)
        page.evaluate(f'window.__ripple({x},{y})')
        log('click', x=x, y=y)
        if touch:
            page.touchscreen.tap(x, y)
        else:
            page.mouse.click(x, y)

    def caption(text, wait=0, small=False):
        page.evaluate('([t, s]) => window.__caption(t, s)', [text, small])
        log('cap', html=text, small=small)
        if text and RECORDING is not None and not RECORDING.stopped:
            RECORDING.chapter(text)
        if wait:
            page.wait_for_timeout(wait)

    return move_to, click, caption


def open_lesson(page, video=VIDEO, query=''):
    """Open a lesson on Bizzy's start question (Listening or Speaking), the video loaded behind it."""
    page.goto(f'{B}/videos/{video}{query}', wait_until='load')
    pick_button(page, 'Listening').wait_for(timeout=20000)
    page.wait_for_selector('iframe[src*="youtube"]', timeout=20000)
    page.wait_for_timeout(4000)


def pick_button(page, mode='Listening'):
    """A card of Bizzy's start question: Listening (Dictation) or Speaking (Shadowing)."""
    return page.get_by_role('button', name=re.compile(rf'\b{mode}\b')).first


def pick(page, mode='Listening'):
    """Answer Bizzy's start question without the pointer (before a recording starts)."""
    pick_button(page, mode).click()


def wait_exercise(page):
    page.get_by_placeholder(re.compile('what you hear')).first.wait_for(state='visible', timeout=60000)


def scene_lesson(ctx):
    page = ctx.new_page()
    open_lesson(page)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'lesson', (1440, 900))
    rec.start()
    place(page, 900, 600)
    caption('<b>1</b>Bizzy asks: pick Listening', 900)
    click(pick_button(page))
    wait_exercise(page)
    caption('<b>2</b>Listen. The red line shows your words', 3400)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    caption('<b>3</b>Type the missing words')
    move_to(ta, 500)
    type_(ta, 'contention ix all kids', delay=110)
    page.wait_for_timeout(500)
    caption('<b>4</b>Press Enter to check', 1200)
    ta.press('Enter')
    page.wait_for_timeout(600)
    caption('<b>5</b>Fix the red word', 900)
    rec.poster()
    page.wait_for_timeout(900)
    type_(ta, 'is', delay=160)
    page.keyboard.press('End')
    caption('<b>6</b>Type the rest')
    type_(ta, REST, delay=70)
    # a complete answer is accepted as it's typed
    # By text: with the cursor resting where START was, CONTINUE appears
    # under it and its tooltip opens, which changes the button's accessible name
    page.locator('button').filter(has_text=re.compile('^continue$', re.I)).wait_for(timeout=8000)
    caption('✓ Right! It checks by itself', 2400)
    caption('Press Space for the next sentence', 1400)
    page.keyboard.press('Space')
    caption(None, 2500)
    rec.stop(1280)


def scene_hints(ctx):
    page = ctx.new_page()
    open_lesson(page)
    move_to, click, caption = helpers(page)
    pick(page)
    wait_exercise(page)
    page.wait_for_timeout(3500)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    rec = Recorder(page, 'hints', (1440, 900))
    rec.start()
    move_to(ta, 300)
    caption('A word is missing')
    type_(ta, 'contention is all kids tremendous', delay=40)
    ta.press('Enter')
    page.wait_for_timeout(500)
    caption('Green shows the missing word: type it at the cursor', 2800)
    ta.fill('')
    caption('A word too many')
    type_(ta, 'contention is all the kids have tremendous', delay=35)
    ta.press('Enter')
    page.wait_for_timeout(500)
    caption('Crossed out = extra: press Backspace', 2800)
    ta.fill('')
    caption('A wrong word')
    type_(ta, 'contention ix all kids have tremendous', delay=35)
    ta.press('Enter')
    page.wait_for_timeout(500)
    rec.poster()
    caption('Red is wrong, green is right. Type over it', 2400)
    type_(ta, 'is', delay=160)
    page.get_by_text('You are correct!').first.wait_for(timeout=8000)
    caption('✓ Right!', 1800)
    caption(None, 400)
    rec.stop(1280)


def scene_speed(ctx):
    page = ctx.new_page()
    open_lesson(page)
    move_to, click, caption = helpers(page)
    pick(page)
    wait_exercise(page)
    page.wait_for_timeout(800)
    rec = Recorder(page, 'speed', (1440, 900))
    rec.start()
    frame = page.frame_locator('iframe[src*="youtube"]')
    place(page, 500, 450)
    caption('<b>1</b>Click the ⚙ gear on the video', 500)
    page.locator('iframe[src*="youtube"]').hover()
    click(frame.get_by_role('button', name='Playback Settings'))
    page.wait_for_timeout(900)
    caption('<b>2</b>Choose Speed', 300)
    click(frame.get_by_text('Speed', exact=True))
    page.wait_for_timeout(900)
    caption('<b>3</b>Pick 0.5x', 300)
    rec.poster()
    click(frame.get_by_text('0.5x', exact=True))
    page.wait_for_timeout(600)
    place(page, 1100, 700)
    caption('🐢 Now the sentence plays slowly', 5000)
    caption(None, 400)
    rec.stop(1280)


def scene_navigate(ctx):
    page = ctx.new_page()
    open_lesson(page)
    move_to, click, caption = helpers(page)
    pick(page)
    wait_exercise(page)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    ta.fill(CLIP1)
    ta.press('Enter')
    page.wait_for_timeout(800)
    page.keyboard.press('Space')
    wait_exercise(page)
    page.wait_for_timeout(1000)
    rec = Recorder(page, 'navigate', (1440, 900))
    rec.start()
    place(page, 1000, 600)
    caption('Too hard? Press <b style="margin:0">Esc</b> to skip it', 1800)
    page.keyboard.press('Escape')
    page.wait_for_timeout(1500)
    caption('Go back with the ◀ arrow', 300)
    # by name: signed in, the bar starts with the ⚙ gear
    back = page.get_by_role('button', name=re.compile('^Previous part$'))
    click(back)
    page.wait_for_timeout(1200)
    click(back, 500)
    page.wait_for_timeout(1300)
    caption('Press UNDO to try a sentence again', 300)
    rec.poster()
    click(page.get_by_role('button', name=re.compile('undo', re.I)))
    page.wait_for_timeout(2500)
    caption(None, 500)
    rec.stop(1280)


def scene_listen(ctx):
    page = ctx.new_page()
    open_lesson(page, LISTEN_VIDEO)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'listen', (1440, 900))
    rec.start()
    place(page, 900, 600)
    click(pick_button(page))
    page.get_by_role('heading', name='Just listen').wait_for(timeout=20000)
    caption('🎧 “Just listen” parts: nothing to type', 1300)
    rec.poster()
    page.wait_for_timeout(1300)
    caption('Press Space to skip, or wait', 1500)
    page.keyboard.press('Space')
    wait_exercise(page)
    caption('Then the next sentence starts', 2500)
    caption(None, 400)
    rec.stop(1280)


def scene_mobile(browser):
    ctx = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
                              device_scale_factor=2)
    sign_in(ctx)
    ctx.add_init_script(OVERLAY)
    page = ctx.new_page()
    open_lesson(page)
    page.evaluate('window.__touch()')
    move_to, click, caption = helpers(page, touch=True)
    rec = Recorder(page, 'mobile', (780, 1688))
    rec.start()
    place(page, 195, 600)
    caption('Tap Listening', 400, small=True)
    click(pick_button(page))
    wait_exercise(page)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    caption('Tap the box. Type the missing words', 300, small=True)
    click(ta)
    type_(ta, 'contention ix all kids', delay=100)
    caption('Tap CHECK', 300, small=True)
    click(page.get_by_role('button', name='CHECK'))
    page.wait_for_timeout(600)
    caption('Fix the red word', 700, small=True)
    rec.poster()
    page.wait_for_timeout(800)
    type_(ta, 'is', delay=150)
    page.keyboard.press('End')
    caption('Type the rest', 300, small=True)
    type_(ta, REST, delay=60)
    # a complete answer is accepted as it's typed
    cont = page.locator('button').filter(has_text=re.compile('^continue$', re.I))
    cont.wait_for(timeout=8000)
    caption('✓ Right! Tap CONTINUE', 1800, small=True)
    click(cont)
    page.wait_for_timeout(1500)
    caption(None, 400)
    rec.stop(390)


# ---- Pro features (DD_SESSION). The speech checks are answered in the browser
# with a canned result, so a recording never makes a paid call; the microphone
# is Chrome's fake device. The interface filmed is the real one.
FR_VIDEO = 'YCuU4SjcS2A'  # Easy French 97: "Bonjour … French," opens it
FR_GAP = "et bienvenue dans un nouvel épisode d'Easy"
LINE1 = CLIP1.split()


def canned(page, name, body):
    page.route(f'**/api/me/{name}', lambda r: r.fulfill(
        status=200, content_type='application/json', body=json.dumps(body)))


def heard(words, missing=()):
    """A speech check's words: each word of the line, except the missing ones."""
    out, t = [], 0.2
    for w in words:
        if w.strip(',.').lower() not in missing:
            out.append({'word': w.strip(',.').lower(), 'start': t, 'end': t + 0.35, 'confidence': 0.96})
        t += 0.4
    return {'text': ' '.join(x['word'] for x in out), 'words': out}


def answer_first(page, gap):
    pick(page)
    wait_exercise(page)
    page.wait_for_timeout(1500)
    page.get_by_placeholder(re.compile('what you hear')).first.fill(gap)
    page.get_by_text('You are correct!').first.wait_for(timeout=8000)


def scene_translation(ctx):
    page = ctx.new_page()
    open_lesson(page, FR_VIDEO)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'translation', (1440, 900))
    rec.start()
    place(page, 900, 600)
    caption('Pick Listening: a French sentence plays', 400)
    click(pick_button(page))
    wait_exercise(page)
    page.wait_for_timeout(1800)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    caption('Type what you hear')
    into_box(move_to, click, ta)
    type_(ta, FR_GAP, delay=45)
    page.get_by_text('You are correct!').first.wait_for(timeout=8000)
    page.get_by_test_id('translation').first.wait_for(timeout=30000)
    caption('Right! The translation in your language appears', 2600)
    rec.poster()
    caption('The ⚙ gear hides or shows it', 300)
    click(page.locator('[data-testid="lesson-settings"]'))
    page.wait_for_timeout(900)
    click(page.locator('[data-testid="lesson-settings-translation"]'), 400)
    page.wait_for_timeout(1300)
    click(page.locator('[data-testid="lesson-settings-translation"]'), 400)
    page.wait_for_timeout(1300)
    page.keyboard.press('Escape')
    caption(None, 600)
    rec.stop(1280)


def scene_word(ctx):
    page = ctx.new_page()
    canned(page, 'word-check', {'level': 'green', 'sounds': [
        {'ipa': 'e', 'score': 96}, {'ipa': 'p', 'score': 93}, {'ipa': 'i', 'score': 91},
        {'ipa': 'z', 'score': 90}, {'ipa': 'ɔ', 'score': 94}, {'ipa': 'd', 'score': 88}]})
    open_lesson(page, FR_VIDEO)
    move_to, click, caption = helpers(page)
    answer_first(page, FR_GAP)
    page.wait_for_timeout(1500)
    rec = Recorder(page, 'word', (1440, 900))
    rec.start()
    place(page, 1000, 600)
    caption('Tap any word of the sentence', 300)
    click(page.locator('[data-word]:visible').filter(has_text=re.compile('^épisode$')).first)
    page.locator('[data-word-card]').first.wait_for(timeout=15000)
    page.get_by_test_id('word-sense').first.wait_for(timeout=20000)
    caption('Its meaning, in your language', 2200)
    rec.poster()
    caption('Listen to it', 200)
    click(page.get_by_test_id('word-listen').first)
    page.wait_for_timeout(1600)
    caption('Say it: tap the microphone and say the word', 300)
    click(page.get_by_test_id('say-mic').first)
    page.wait_for_timeout(1800)
    click(page.get_by_test_id('say-word').get_by_role('button', name=re.compile('^Stop')).first, 200)
    page.get_by_test_id('say-word-result').first.wait_for(timeout=10000)
    caption('Green = easy to understand. Each sound gets a colour', 3200)
    page.keyboard.press('Escape')
    caption(None, 600)
    rec.stop(1280)


def scene_voice(ctx):
    page = ctx.new_page()
    canned(page, 'voice-answer', {'text': ' '.join(LINE1[1:-1])})
    canned(page, 'shadow-check', heard(LINE1, missing=('tremendous',)))
    open_lesson(page)
    move_to, click, caption = helpers(page)
    pick(page)
    wait_exercise(page)
    page.wait_for_timeout(3500)
    rec = Recorder(page, 'voice', (1440, 900))
    rec.start()
    place(page, 900, 600)
    caption('Tap the microphone in the box', 300)
    click(page.get_by_test_id('voice-mic').first)
    caption('Say the words you heard', 1800)
    click(page.get_by_test_id('voice-mic').first, 300)
    page.get_by_text('You are correct!').first.wait_for(timeout=10000)
    caption('They are written in the box and checked', 2400)
    rec.poster()
    caption('Now say the whole sentence', 300)
    click(page.get_by_test_id('say-line-mic').first)
    page.wait_for_timeout(2400)
    click(page.get_by_test_id('say-line-mic').first, 300)
    page.get_by_test_id('say-line-score').first.wait_for(timeout=10000)
    caption('Green words were heard, red ones were not', 3000)
    caption('Space: next sentence', 1200)
    page.keyboard.press('Space')
    caption(None, 1200)
    rec.stop(1280)



FR_LINE = "Bonjour et bienvenue dans un nouvel épisode d'Easy French,".split()


def scene_pronounce(ctx):
    """Pro pronunciation check: the whole sentence after a right answer, then Say it on one word."""
    page = ctx.new_page()
    canned(page, 'shadow-check', heard(FR_LINE, missing=('nouvel',)))
    canned(page, 'word-check', {'level': 'brown', 'sounds': [
        {'ipa': 'n', 'score': 95}, {'ipa': 'u', 'score': 62}, {'ipa': 'v', 'score': 90},
        {'ipa': 'ɛ', 'score': 41}, {'ipa': 'l', 'score': 93}]})
    open_lesson(page, FR_VIDEO)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'pronounce', (1440, 900))
    rec.start()
    place(page, 900, 600)
    caption('Get the sentence right first', 300)
    click(pick_button(page))
    wait_exercise(page)
    page.wait_for_timeout(1500)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    into_box(move_to, click, ta)  # the pointer below the box: resting on a word opens its hover card
    type_(ta, FR_GAP, delay=35)
    page.get_by_text('You are correct!').first.wait_for(timeout=8000)
    page.wait_for_timeout(600)
    caption('Tap the microphone and say the whole sentence', 300)
    click(page.get_by_test_id('say-line-mic').first)
    page.wait_for_timeout(2600)
    click(page.get_by_test_id('say-line-mic').first, 300)
    page.get_by_test_id('say-line-score').first.wait_for(timeout=10000)
    caption('Green words came through, red ones did not', 3000)
    rec.poster()
    caption('Tap a word to practise it alone', 300)
    click(page.locator('[data-word]:visible').filter(has_text=re.compile('^nouvel$')).first)
    page.locator('[data-word-card]').first.wait_for(timeout=15000)
    page.get_by_test_id('word-sense').first.wait_for(timeout=20000)
    page.wait_for_timeout(800)
    caption('Listen, then Say it: tap the microphone and say the word', 300)
    click(page.get_by_test_id('word-listen').first)
    page.wait_for_timeout(1500)
    click(page.get_by_test_id('say-mic').first)
    page.wait_for_timeout(1500)
    click(page.get_by_test_id('say-word').get_by_role('button', name=re.compile('^Stop')).first, 200)
    page.get_by_test_id('say-word-result').first.wait_for(timeout=10000)
    move_to((1380, 840), 200)  # the pointer off the result
    caption('Each sound gets a colour: work on the red one')
    look(page, page.get_by_test_id('say-word-result').first, 3.6)
    page.keyboard.press('Escape')
    caption(None, 600)
    rec.stop(1280)


def pronounced(words, scores):
    """Azure's pronunciation score per word (90 unless given; 0 = left out)."""
    out = []
    for w in words:
        k = w.strip(',.').lower()
        sc = scores.get(k, 90)
        out.append({'word': k, 'score': sc, 'omitted': sc == 0})
    return out


def scene_streak(ctx):
    page = ctx.new_page()
    page.goto(f'{B}/videos', wait_until='load')
    page.get_by_role('link', name=re.compile(r'^\d+ day streak$')).first.wait_for(timeout=20000)
    page.wait_for_timeout(2500)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'streak', (1440, 900))
    rec.start()
    place(page, 700, 400)
    caption('The flame: days in a row', 300)
    flame = page.get_by_role('link', name=re.compile(r'^\d+ day streak$')).first
    move_to(flame, 500)
    look(page, flame, 1.2)
    caption("The ring: today's minutes", 300)
    ring = page.get_by_role('link', name=re.compile(r'min', re.I)).first
    move_to(ring, 500)
    look(page, ring, 1.2)
    caption('Click it: My progress', 300)
    click(page.get_by_role('link', name=re.compile(r'^\d+ day streak$')).first)
    page.get_by_text('Last 6 months').wait_for(timeout=20000)
    page.wait_for_timeout(1500)
    rec.poster()
    caption('Your week, your goal, your minutes', 2200)
    for _ in range(6):
        page.mouse.wheel(0, 260)
        page.wait_for_timeout(450)
    caption('Six months of practice, and badges', 2200)
    caption(None, 400)
    rec.stop(1280)


def scene_report(ctx):
    page = ctx.new_page()
    open_lesson(page)
    move_to, click, caption = helpers(page)
    pick(page)
    wait_exercise(page)
    page.wait_for_timeout(1500)
    rec = Recorder(page, 'report', (1440, 900))
    rec.start()
    place(page, 700, 600)
    caption('Something wrong? Open the ⚙ gear', 300)
    click(page.locator('[data-testid="lesson-settings"]'))
    page.wait_for_timeout(700)
    caption('Report a bug', 200)
    click(page.get_by_test_id('bug-report-open').first)
    note = page.locator('[data-testid="bug-report-note"]')
    note.wait_for(timeout=8000)
    page.wait_for_timeout(1200)
    caption('Say what went wrong')
    type_(note, 'The video stopped before the last word.', delay=45)
    page.wait_for_timeout(600)
    rec.poster()
    caption('A screenshot goes with it. Press SEND', 300)
    move_to(page.get_by_role('button', name=re.compile('^send$', re.I)), 2000)
    caption(None, 400)
    rec.stop(1280)


def scene_words(ctx):
    """Save a word, then practise it as a flashcard. Every /api answer is canned (words_demo.py):
    no account needed, nothing saved anywhere."""
    page = ctx.new_page()
    open_lesson(page, FR_VIDEO)
    move_to, click, caption = helpers(page)
    answer_first(page, FR_GAP)
    page.get_by_test_id('translation').first.wait_for(timeout=30000)
    page.wait_for_timeout(1500)
    rec = Recorder(page, 'words', (1440, 900))
    rec.start()
    place(page, 1000, 600)
    caption('Tap a word of the sentence', 300)
    click(page.locator('[data-word]:visible').filter(has_text=re.compile('^épisode$')).first)
    page.get_by_test_id('word-sense').first.wait_for(timeout=20000)
    page.wait_for_timeout(1200)
    save = page.get_by_test_id('word-save').first
    assert save.get_attribute('aria-pressed') != 'true', 'already saved'
    caption('Press Save', 300)
    click(save)
    page.get_by_test_id('word-save-note').first.wait_for(timeout=8000)
    caption('Saved to Words, with its sentence', 2200)
    caption('See words: your saved words', 300)
    see = page.get_by_test_id('word-save-note').get_by_role('link').first
    see.evaluate('a => a.removeAttribute("target")')  # it opens a new tab; the recording stays in this one
    click(see)
    page.get_by_test_id('words-chart-hit').first.wait_for(timeout=30000)
    page.wait_for_timeout(1800)
    caption('Press Practice', 300)
    click(page.get_by_test_id('words-practice').first)
    page.get_by_test_id('practice-card').first.wait_for(timeout=30000)
    page.wait_for_timeout(600)
    caption('The sentence from the video, your word missing', 2400)
    rec.poster()
    inp = page.get_by_test_id('practice-input').first
    caption('Type it (or say it) and press Enter', 300)
    move_to(inp, 300)
    type_(inp, 'épisode', delay=90)
    page.keyboard.press('Enter')
    page.get_by_test_id('practice-result').first.wait_for(timeout=10000)
    caption('Right! It comes back in a few days', 2600)
    click(page.get_by_test_id('practice-continue').first, 300)
    page.wait_for_timeout(1200)
    inp = page.get_by_test_id('practice-input').first
    caption('Wrong? Type it again to go on', 300)
    move_to(inp, 300)
    type_(inp, 'quartier', delay=90)
    page.keyboard.press('Enter')
    page.get_by_test_id('practice-retype').first.wait_for(timeout=10000)
    page.wait_for_timeout(1600)
    type_(page.get_by_test_id('practice-input').first, 'quartiers', delay=90)
    page.get_by_test_id('practice-result').first.wait_for(timeout=10000)
    # the screen is still now: a 1-px blink keeps the screencast sending frames
    page.evaluate('''() => { const d = document.createElement('div');
        d.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px;opacity:.02;background:#000';
        document.body.appendChild(d); let on = 0;
        setInterval(() => { d.style.background = (on ^= 1) ? '#fff' : '#000'; }, 40); }''')
    result = page.get_by_test_id('practice-result').first
    caption('A missed word comes back soon', 300)
    look(page, result, 2.4)
    caption(None, 400)
    rec.stop(1280)


def scene_your_words(ctx):
    """Words: the chart of how the saved words grew, then See all, a word's sentence, a tab.
    Every /api/me answer is canned (words_demo.py): no account needed, nothing saved anywhere."""
    page = playlist_page(ctx, '/videos')
    rail = page.locator('nav a[href="/words"]:visible').first
    rail.wait_for(timeout=30000)
    page.wait_for_timeout(2500)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'your-words', (1440, 900))
    rec.start()
    place(page, 700, 500)
    caption('Words, in the menu on the left', 300)
    click(rail, 300)
    hit = page.get_by_test_id('words-chart-hit').first
    hit.wait_for(timeout=30000)
    page.wait_for_timeout(1800)
    caption('How your words grow: New, Learning, Known', 300)
    move_to((900, 640), 300)
    look(page, hit, 2.6)
    box = hit.bounding_box()
    caption('Point at a day to see it', 300)
    move_to((box['x'] + box['width'] * 0.45, box['y'] + box['height'] * 0.6), 1400)
    rec.poster()
    move_to((box['x'] + box['width'] * 0.8, box['y'] + box['height'] * 0.6), 1600)
    caption('See all your words', 300)
    click(page.get_by_test_id('words-see-all').first, 300)
    page.get_by_test_id('saved-word').first.wait_for(timeout=30000)
    page.wait_for_timeout(1500)
    caption('Click a word: its sentence and the lesson', 300)
    row = page.get_by_test_id('saved-word-row').filter(has_text='quartiers').first
    click(row, 300)
    detail = page.get_by_test_id('saved-word-detail').first
    detail.wait_for(timeout=10000)
    page.wait_for_timeout(500)
    look(page, detail, 2.8)
    caption('Pick New, Learning or Known', 300)
    click(page.get_by_role('button', name='Known 11'), 300)
    page.wait_for_timeout(2200)
    caption(None, 400)
    rec.stop(1280)


def demo_lesson(ctx):
    """Easy French 97 as a demo Pro learner, the first sentence played. Every /api answer is
    canned (words_demo.py): no account needed, nothing saved anywhere."""
    page = ctx.new_page()
    open_lesson(page, FR_VIDEO)
    pick(page)
    wait_exercise(page)
    return page


def scene_whole(ctx):
    """The Dictation gear's Show the whole answer: every mistake at once after Enter."""
    page = demo_lesson(ctx)
    move_to, click, caption = helpers(page)
    page.wait_for_timeout(3000)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    rec = Recorder(page, 'whole', (1440, 900))
    rec.start()
    place(page, 900, 620)
    caption('Open the ⚙ gear', 300)
    click(page.get_by_test_id('lesson-settings'))
    page.wait_for_timeout(900)
    caption('Turn on Show the whole answer', 300)
    click(page.get_by_test_id('lesson-settings-whole'), 400)
    page.wait_for_timeout(1200)
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)
    caption('Type what you hear and press Enter')
    into_box(move_to, click, ta)
    type_(ta, 'et bienvenue dans un nouveau épisode', delay=60)
    page.wait_for_timeout(300)
    ta.press('Enter')
    answer = page.get_by_test_id('whole-answer').first
    answer.wait_for(timeout=8000)
    caption('Every mistake at once: red is wrong, green is right', 300)
    look(page, answer, 3.2)
    rec.poster()
    caption('Fix them in the box. The wrong word is selected')
    page.wait_for_timeout(600)  # typing replaces the selected word; the pointer stays out of the way
    type_(ta, 'nouvel', delay=140)
    page.keyboard.press('End')
    type_(ta, " d'Easy", delay=110)
    page.get_by_text('You are correct!').first.wait_for(timeout=8000)
    caption('✓ Right!', 1800)
    caption(None, 400)
    rec.stop(1280)


def scene_theme(ctx):
    """Light or dark: the Theme switch in the account menu (and Settings › Appearance).
    A demo Pro learner, every /api answer canned (words_demo.py); the device is light."""
    page = ctx.new_page()
    # History's started videos (the today block): none, so the page stays short
    page.route(B + '/api/me/videos*', lambda r: r.fulfill(
        status=200, content_type='application/json', body='[]'))
    page.goto(f'{B}/videos', wait_until='load')
    page.get_by_role('button', name='Account').wait_for(timeout=20000)
    page.wait_for_timeout(2500)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'theme', (1440, 900))
    rec.start()
    place(page, 900, 500)
    caption('Click your picture', 300)
    click(page.get_by_role('button', name='Account'))
    page.wait_for_timeout(700)
    switch = page.get_by_role('radiogroup', name='Theme').first
    caption('Theme: choose Dark', 300)
    click(switch.get_by_role('radio', name='Dark'), 500)
    page.wait_for_timeout(900)
    page.keyboard.press('Escape')
    caption('Every page is dark now, lessons too', 300)
    move_to((760, 420), 300)
    look(page, page.locator('main').first, 2.4)
    rec.poster()
    caption('Device: dark when your phone or computer is dark', 300)
    click(page.get_by_role('button', name='Account'))
    page.wait_for_timeout(700)
    click(switch.get_by_role('radio', name='Device'), 500)
    page.wait_for_timeout(1400)
    page.keyboard.press('Escape')
    caption('It is also in Settings, under Appearance', 300)
    page.goto(f'{B}/settings', wait_until='load')
    section = page.locator('section[aria-label="Appearance"]')
    section.wait_for(timeout=20000)
    section.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    move_to(section.get_by_role('radiogroup', name='Theme'), 300)
    look(page, section, 2.6)
    caption(None, 400)
    rec.stop(1280)


def playlist_page(ctx, url):
    """A demo Pro learner of French with no playlist yet: every /api/me answer canned (words_demo.py +
    playlists_demo.py); DictationDaily's own playlists are the live ones."""
    import playlists_demo
    page = ctx.new_page()
    playlists_demo.Playlists(B).install(page)
    # History's started videos: none, so Home's video cards sit near the top
    page.route(B + '/api/me/videos*', lambda r: r.fulfill(
        status=200, content_type='application/json', body='[]'))
    page.goto(f'{B}{url}', wait_until='load')
    return page


def scene_playlist(ctx):
    """Follow a playlist: Explore › a level › a playlist › Save › Start, the lesson's playlist bar."""
    # no playlist yet: the page opens on Explore by itself
    page = playlist_page(ctx, '/playlists')
    page.get_by_text('French For Beginners (A1)').first.wait_for(timeout=20000)
    page.wait_for_timeout(2500)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'playlist', (1440, 900))
    rec.start()
    place(page, 900, 300)
    caption('Playlists: videos in order, from the first to the last', 300)
    move_to((760, 520), 300)
    look(page, page.locator('main').first, 2.0)
    caption('Pick your level', 300)
    click(page.get_by_role('button', name='A1', exact=True), 300)
    page.wait_for_timeout(1500)
    caption('Open a playlist', 300)
    click(page.get_by_text('French For Beginners (A1)').first, 300)
    save = page.get_by_role('button', name='Save', exact=True)
    save.wait_for(timeout=20000)
    page.wait_for_timeout(1500)
    rec.poster()
    caption('Save keeps it in Your playlists', 300)
    click(save, 300)
    page.wait_for_timeout(1200)
    caption('Continue plays the video you are on', 300)
    click(page.get_by_role('link', name=re.compile('^(Start|Continue)$')).first, 300)
    pick_button(page).wait_for(timeout=30000)
    page.wait_for_timeout(1000)
    caption('Pick Listening', 300)
    click(pick_button(page), 300)
    wait_exercise(page)
    caption('At the end of the video: Next video in the playlist', 2600)
    caption(None, 400)
    rec.stop(1280)


def scene_playlist_make(ctx):
    """Make your own playlist: a video's ⋯ › Save to playlist › New playlist, the "Saved to" note,
    then the playlist in Playlists › Your playlists."""
    page = playlist_page(ctx, '/videos')
    more = page.locator('[aria-label^="More for"]').first
    more.wait_for(state='attached', timeout=20000)
    page.wait_for_timeout(2500)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'playlist-make', (1440, 900))
    rec.start()
    place(page, 900, 300)
    caption('Press ⋯ on any video', 300)
    move_to(more.locator('xpath=..'), 300)  # the ⋯ shows when the pointer is on the card
    click(more, 300)
    caption('Save to playlist, then New playlist', 300)
    click(page.get_by_role('menuitem', name='Save to playlist'), 300)
    new = page.get_by_role('button', name=re.compile('New playlist')).last
    new.wait_for(timeout=10000)
    page.wait_for_timeout(500)
    click(new, 300)
    name = page.locator('#pl-title')
    name.wait_for(timeout=10000)
    rec.poster()
    caption('Give it a name and choose who can see it', 300)
    page.wait_for_timeout(300)
    type_(name, 'My French', delay=90)
    page.wait_for_timeout(400)
    click(page.get_by_text('Anyone with the link').first, 300)
    page.wait_for_timeout(600)
    click(page.get_by_role('button', name='Create'), 300)
    toast = page.get_by_test_id('toast')
    toast.wait_for(timeout=10000)
    caption('Saved: the video is in your new playlist', 300)
    tb = toast.bounding_box()
    move_to((tb['x'] - 50, tb['y'] - 40), 300)  # beside the note, not on its words
    look(page, toast, 2.2)
    click(page.get_by_role('button', name='Close'), 300)
    page.wait_for_timeout(700)
    caption('Find it in Playlists › Your playlists', 300)
    click(page.locator('nav a[href="/playlists"], a[href="/playlists"]').first, 300)
    page.get_by_text('My French').first.wait_for(timeout=20000)
    page.wait_for_timeout(800)
    move_to((560, 450), 300)
    t0 = time.time()
    page.wait_for_timeout(2600)
    # zoom on Made by you (the left column), not the middle of the page
    RECORDING.events.append({'k': 'focus', 't': t0, 't1': time.time(), 'x': 420, 'y': 400})
    caption(None, 400)
    rec.stop(1280)


# ---- New in November 2026: the practice card, lesson parts, Your skills, likes and comments,
# Add a video, the small player and the hover card. All as the Demo Learner (sign_in()).

def segments(video):
    """The lesson's sentences (the public transcript file), to answer them before a recording."""
    import urllib.request
    req = urllib.request.Request(f'{B}/transcripts/{video}.json', headers={'User-Agent': 'Mozilla/5.0 dd-guide-capture'})
    return json.load(urllib.request.urlopen(req))['segments']


def answer_now(page, text):
    """Answer the sentence on screen at once (off camera), then go on to the next one."""
    wait_exercise(page)
    page.get_by_placeholder(re.compile('what you hear')).first.fill(text)
    page.locator('button').filter(has_text=re.compile('^continue$', re.I)).wait_for(timeout=8000)
    page.keyboard.press('Space')


def scene_practice(ctx):
    """/videos: the practice card picks the next video; Another one; START opens it on Bizzy's question."""
    page = ctx.new_page()
    page.goto(f'{B}/videos', wait_until='load')
    start = page.get_by_role('button', name=re.compile('^START$')).first
    start.wait_for(timeout=30000)
    page.wait_for_timeout(3000)
    move_to, click, caption = helpers(page)
    card = start.locator('xpath=ancestor::section[1]')
    rec = Recorder(page, 'practice', (1440, 900))
    rec.start()
    place(page, 900, 520)
    caption('Your practice card: the next video, picked for you', 300)
    move_to((560, 160), 300)
    look(page, card, 2.6)
    caption('Which part is next, and about how long it takes', 300)
    move_to((520, 205), 300)
    look(page, page.get_by_text(re.compile(r'^(Part \d+ of \d+|Whole video)')).first, 2.4)
    rec.poster()
    caption('Not this one? Another one', 300)
    click(page.get_by_role('button', name=re.compile('another one', re.I)).first, 300)
    page.wait_for_timeout(2600)
    caption('START: Bizzy asks Listening or Speaking', 300)
    click(page.get_by_role('button', name=re.compile('^START$')).first, 300)
    pick_button(page).wait_for(timeout=30000)
    page.wait_for_timeout(1800)
    click(pick_button(page), 300)
    wait_exercise(page)
    caption('It starts at once, part after part', 2600)
    caption(None, 400)
    rec.stop(1280)


def scene_parts(ctx):
    """A lesson part ends: the Part done card, then KEEP GOING."""
    page = ctx.new_page()
    segs = [s for s in segments(VIDEO)]
    open_lesson(page)
    move_to, click, caption = helpers(page)
    pick(page)
    # Answer the part's sentences off camera, but the last one (and skip one, to show a dash)
    label = page.get_by_text(re.compile(r'Part 1 of \d+ · \d+/\d+'))
    label.first.wait_for(timeout=30000)
    total = int(re.search(r'/(\d+)', label.first.inner_text()).group(1))
    exercises = [s for s in segs if not s.get('ignore')]
    for n in range(total - 1):
        if n == 2:
            wait_exercise(page)
            page.get_by_placeholder(re.compile('what you hear')).first.press('Escape')  # skipped
            page.wait_for_timeout(600)
            continue
        if page.get_by_role('heading', name='Just listen').count():
            page.keyboard.press('Space')
        if n in (4, 7):
            # a word missed first: it shows under Words you missed
            words = exercises[n]['text'].split()
            k = max(range(len(words)), key=lambda i: len(words[i].strip(',.?!')))
            words[k] = words[k][:-2] + 'x'
            wait_exercise(page)
            box = page.get_by_placeholder(re.compile('what you hear')).first
            box.fill(' '.join(words))
            box.press('Enter')
            page.wait_for_timeout(700)
        answer_now(page, exercises[n]['text'])
        page.wait_for_timeout(500)
    wait_exercise(page)
    page.wait_for_timeout(2500)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    rec = Recorder(page, 'parts', (1440, 900))
    rec.start()
    place(page, 900, 640)
    caption('The last sentence of a part', 300)
    into_box(move_to, click, ta)
    type_(ta, exercises[total - 1]['text'], delay=45)
    # right: the part's last sentence goes straight on to Part done
    done = page.get_by_text(re.compile('Part \\d+ done', re.I)).first
    done.wait_for(timeout=15000)
    page.wait_for_timeout(1200)
    caption('Part done: how the part went', 300)
    look(page, done, 2.4)
    rec.poster()
    caption('A square per sentence: ✓ first try, 2 checks, – skipped', 300)
    move_to((1250, 330), 300)
    look(page, page.get_by_text(re.compile('right on the first try')).first, 2.4)
    missed = page.get_by_text(re.compile('Words you missed', re.I)).first
    if missed.count():
        caption('Words you missed: rest the mouse on one for its meaning', 300)
        look(page, missed, 2.4)
    caption('The hardest sentence: hear it again', 300)
    look(page, page.get_by_text(re.compile('^Hardest')).first, 2.2)
    caption('KEEP GOING: the next part starts', 300)
    click(page.get_by_role('button', name=re.compile('keep going', re.I)).first, 300)
    wait_exercise(page)
    page.wait_for_timeout(1800)
    caption(None, 400)
    rec.stop(1280)


def scene_skills(ctx):
    """My progress › Your skills: speaking and listening, 7 or 30 days."""
    page = ctx.new_page()
    page.goto(f'{B}/my-learning', wait_until='load')
    title = page.get_by_text(re.compile('your skills', re.I)).first
    title.wait_for(timeout=30000)
    page.wait_for_timeout(2500)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'skills', (1440, 900))
    rec.start()

    def show(loc, block='start'):
        loc.evaluate(f"e => e.scrollIntoView({{behavior: 'smooth', block: '{block}'}})")
        page.wait_for_timeout(1300)

    place(page, 900, 500)
    caption('My progress: You, in the menu on the left', 1600)
    caption('Your skills: speaking and listening', 300)
    show(title)
    speaking = page.get_by_text(re.compile('^Speaking$')).first
    move_to((760, 560), 300)
    look(page, speaking, 2.6)
    rec.poster()
    caption('Sounds to work on, and words to say again', 300)
    show(page.get_by_text('Sounds to work on').first, 'center')
    look(page, page.get_by_text('Words to say again').first, 2.4)
    caption('Listening: right on the first try, by speed', 300)
    show(page.get_by_text(re.compile('^Listening$')).first, 'center')
    look(page, page.get_by_text(re.compile('Where it gets hard')).first, 2.6)
    caption('Last 7 days or Last 30 days', 300)
    show(title, 'center')
    seven = page.get_by_role('button', name='Last 7 days').or_(page.get_by_role('tab', name='Last 7 days')).first
    click(seven, 1800)
    caption(None, 400)
    rec.stop(1280)


def scene_social(ctx):
    """The lesson's 👍 / 👎, Save (Practise later) and comments."""
    page = demo_lesson(ctx)
    move_to, click, caption = helpers(page)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    page.wait_for_timeout(1500)
    ta.fill(FR_GAP)
    page.get_by_text('You are correct!').first.wait_for(timeout=8000)
    page.wait_for_timeout(1500)
    rec = Recorder(page, 'social', (1440, 900))
    rec.start()
    place(page, 900, 600)
    caption('Like the video? 👍', 300)
    click(page.get_by_role('button', name=re.compile('^I like this')), 1400)
    caption('Save: keep it in Practise later', 300)
    click(page.get_by_role('button', name='Save to playlist'), 300)
    later = page.get_by_role('dialog').locator('text="Practise later" >> visible=true').first
    later.wait_for(timeout=10000)
    page.wait_for_timeout(600)
    click(later, 1200)
    click(page.get_by_role('dialog').get_by_role('button', name=re.compile('^close$', re.I)).first, 300)
    page.wait_for_timeout(600)
    rec.poster()
    caption('Comments: questions and tips about this video', 300)
    click(page.get_by_role('button', name=re.compile('^Comments')), 300)
    box = page.get_by_role('textbox', name='Your comment')
    box.wait_for(timeout=10000)
    page.wait_for_timeout(1500)
    caption('Write one. Quote the line you mean', 300)
    click(box, 300)
    type_(box, "C'est quoi « Easy French » en français ?", delay=50)
    quote = page.get_by_text(re.compile('^Quote the line')).first
    if quote.count():
        click(quote, 600)
    send = page.get_by_role('button', name='Post comment')
    click(send, 1600)
    caption('Close it with ‹ or a click on the lesson', 300)
    click((1200, 450), 1200)
    caption(None, 400)
    rec.stop(1280)


def scene_addvideo(ctx):
    """＋ Create: paste a YouTube link, check the language, Make the lesson; it waits its turn."""
    vid = 'EAX8mc_ovDk'  # What Do The French Have For Breakfast? | Easy French 218
    info = DEMO.learner.videos[vid]
    made = []

    def preview(route, req, body):
        route.fulfill(status=200, content_type='application/json', body=json.dumps(
            {'id': vid, 'title': info['title'], 'channel': 'Easy French', 'seconds': info['duration'],
             'lesson': False, 'added': False, 'problem': None}))
        return True

    def make(route, req, body):
        if req.method != 'POST':
            data = DEMO.learner.added()
            data['items'] = made + data['items']
            data['quota']['usedToday'] += sum(x['seconds'] for x in made)
            route.fulfill(status=200, content_type='application/json', body=json.dumps(data))
            return True
        item = {'id': vid, 'title': info['title'], 'channel': 'Easy French', 'language': 'fr',
                'seconds': info['duration'], 'state': 'waiting', 'place': 2, 'reason': None,
                'createdAt': int(time.time()), 'existing': False}
        made.insert(0, item)
        route.fulfill(status=200, content_type='application/json', body=json.dumps({'item': item}))
        return True

    DEMO.on(r'^/api/me/added-videos/preview$', preview)
    DEMO.on(r'^/api/me/added-videos$', make)
    page = ctx.new_page()
    page.goto(f'{B}/videos', wait_until='load')
    create = page.get_by_role('link', name=re.compile('Create')).first
    create.wait_for(timeout=30000)
    page.wait_for_timeout(2500)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'addvideo', (1440, 900))
    rec.start()
    place(page, 900, 500)
    caption('Pro: make a lesson from any YouTube video. ＋ Create', 300)
    click(create, 300)
    link = page.get_by_placeholder(re.compile('paste', re.I)).first
    link.wait_for(timeout=20000)
    page.wait_for_timeout(1200)
    caption('Paste the link of one video', 300)
    click(link, 300)
    type_(link, f'https://www.youtube.com/watch?v={vid}', delay=25)
    page.get_by_text(info['title']).first.wait_for(timeout=20000)
    page.wait_for_timeout(1200)
    caption('Check the language, then Make the lesson', 300)
    rec.poster()
    make_btn = page.get_by_role('button', name=re.compile('make the lesson', re.I)).first
    click(make_btn, 300)
    page.get_by_text(re.compile('In line', re.I)).first.wait_for(timeout=20000)
    page.wait_for_timeout(800)
    row = page.get_by_text(re.compile('^In line')).first
    row.evaluate("e => e.scrollIntoView({behavior: 'smooth', block: 'center'})")
    page.wait_for_timeout(1200)
    caption('It waits its turn. We email you when it is ready', 300)
    look(page, row, 3.0)
    caption(None, 400)
    rec.stop(1280)


def scene_layout(ctx):
    """⚙ › Video layout: Small player (the subtitles in the picture too small to read) or Side by side."""
    page = demo_lesson(ctx)
    move_to, click, caption = helpers(page)
    player = page.get_by_test_id('player-box').first
    page.wait_for_timeout(3000)
    rec = Recorder(page, 'layout', (1440, 900))
    rec.start()
    place(page, 900, 620)
    caption('Words written in the video? It plays small', 300)
    move_to(player, 300)
    look(page, player, 2.4)
    rec.poster()
    caption('Want it big? ⚙ › Video layout › Side by side', 300)
    click(page.get_by_test_id('lesson-settings'), 300)
    page.wait_for_timeout(700)
    click(page.get_by_test_id('lesson-settings-layout-side'), 600)
    page.wait_for_timeout(1200)
    page.keyboard.press('Escape')
    move_to((380, 420), 300)
    page.wait_for_timeout(2200)
    caption('Small player puts it back', 300)
    click(page.get_by_test_id('lesson-settings'), 300)
    page.wait_for_timeout(700)
    click(page.get_by_test_id('lesson-settings-layout-small'), 600)
    page.wait_for_timeout(1200)
    page.keyboard.press('Escape')
    move_to(player, 300)
    look(page, player, 2.0)
    caption(None, 400)
    rec.stop(1280)


PHRASE_SEG = 19  # "et il y a tellement de choses qui se passent tout le temps," (se passer, tout le temps)


def scene_hover(ctx):
    """Rest the mouse on a word: its meaning and Save; a phrase shows in orange, and saves too."""
    segs = segments(FR_VIDEO)
    line = segs[PHRASE_SEG]
    words = [w['text'] if isinstance(w, dict) else w for w in line['words']]
    wi = words.index('passent')
    vi_word = {'word': 'passent', 'src': 'fr', 'lemma': 'passer', 'pos': 'verb', 'gender': '', 'ipa': '/pas/',
               'form': 'ils, présent', 'gloss': 'đi qua, trôi qua', 'def': "Aller d'un endroit à un autre ; s'écouler."}
    vi_phrase = {'word': 'se passer', 'src': 'fr', 'lemma': 'se passer', 'pos': 'phrase', 'gender': '',
                 'ipa': '/sə pa.se/', 'form': '', 'gloss': 'xảy ra, diễn ra', 'def': 'Avoir lieu, arriver.'}

    def word(route, req, body):
        b = body()
        sense = vi_phrase if b.get('phrase') is not None else (vi_word if b.get('seg') == PHRASE_SEG and b.get('wi') == wi else None)
        if not sense:
            return False
        route.fulfill(status=200, content_type='application/json', body=json.dumps(
            {'state': 'ready', 'native': 'vi', 'sense': sense, 'ipaSource': 'wiktionary',
             'headwordIpa': [{'accent': '', 'ipa': '/pa.se/'}], 'entry': {'state': 'none', 'url': None},
             'audio': {'state': 'none', 'url': None}, 'sound': {'state': 'none', 'url': None}}))
        return True

    DEMO.on(r'^/api/me/word$', word)
    page = ctx.new_page()
    # the lesson opens at this sentence: the place is the end of the one before
    page.route('**/api/me/progress?id=*', lambda r: r.fulfill(
        status=200, content_type='application/json',
        body=json.dumps({'progress': segs[PHRASE_SEG - 1]['end'], 'date': int(time.time()) - 86400, 'partSize': 10})))
    open_lesson(page, FR_VIDEO)
    move_to, click, caption = helpers(page)
    pick(page)
    wait_exercise(page)
    page.wait_for_timeout(1500)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    ta.fill(line['text'])
    page.get_by_text('You are correct!').first.wait_for(timeout=8000)
    page.wait_for_timeout(2000)
    target = page.locator('[data-word]:visible').filter(has_text=re.compile('^passent$')).first
    rec = Recorder(page, 'hover', (1440, 900))
    rec.start()
    place(page, 1000, 650)
    caption('Rest the mouse on a word', 300)
    move_to(target, 300)
    hover = page.locator('[role="tooltip"]').filter(has_text='passent').first
    hover.wait_for(timeout=15000)
    page.wait_for_timeout(900)
    caption('Its meaning, in your language and in French', 300)
    look(page, hover, 2.6)
    rec.poster()
    caption('Part of a phrase? Its words turn orange', 300)
    look(page, hover.get_by_text('se passer').first, 2.6)
    caption('The bookmark saves the word', 300)
    save = hover.get_by_role('button', name=re.compile('save', re.I)).first
    click(save, 1500)
    caption('The phrase: Everything about this word', 300)
    click(hover.get_by_text(re.compile('Everything about this word')).first, 300)
    box = page.locator('[data-word-card]').get_by_text(re.compile('Part of a phrase', re.I)).first
    box.wait_for(timeout=15000)
    page.wait_for_timeout(1200)
    phrase = box.locator('xpath=ancestor::*[.//button][1]')
    look(page, phrase, 2.0)
    caption('Its bookmark saves the phrase to Words', 300)
    click(phrase.get_by_role('button', name=re.compile('save', re.I)).last, 2000)
    page.keyboard.press('Escape')
    caption(None, 400)
    rec.stop(1280)


def first_card(page):
    """The first video card of the list (under the topics, not the practice card)."""
    row = page.get_by_role('button', name='All', exact=True).first.bounding_box()
    for a in page.locator('a[href^="/videos/"]:visible').all():
        box = a.bounding_box()
        if box and box['y'] > row['y'] + 20 and a.locator('img').count():
            return a
    raise AssertionError('no video card')


def scene_library(ctx):
    page = ctx.new_page()
    page.goto(f'{B}/videos', wait_until='load')
    page.wait_for_selector('img[src*="ytimg.com"]', timeout=20000)
    page.get_by_role('button', name=re.compile('^Filters')).wait_for(timeout=20000)
    page.wait_for_timeout(3000)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'library', (1440, 900))
    rec.start()
    place(page, 700, 500)
    caption('<b>1</b>Pick a topic', 400)
    click(page.get_by_role('button', name='Daily life', exact=True))
    page.wait_for_timeout(1500)
    caption('<b>2</b>Filters: level, length, speed', 300)
    click(page.get_by_role('button', name=re.compile('^Filters')))
    panel = page.get_by_role('dialog').first
    panel.wait_for(timeout=10000)
    page.wait_for_timeout(700)
    click(panel.get_by_role('button', name=re.compile('^A1')), 700)
    rec.poster()
    click(panel.get_by_role('button', name=re.compile(r'^Show \d+ videos?$')), 300)
    page.wait_for_timeout(1400)
    caption('<b>3</b>Sort: Slowest speaker first', 300)
    click(page.get_by_role('button', name=re.compile('^Sort')))
    page.wait_for_timeout(700)
    click(page.get_by_role('menuitemradio', name=re.compile('^Slowest')))
    page.wait_for_timeout(1800)
    caption('<b>4</b>Click a video', 300)
    card = first_card(page)
    move_to(card, 900)
    click(card, 200)
    pick_button(page).wait_for(timeout=30000)
    page.wait_for_timeout(800)
    caption('Bizzy asks: Listening or Speaking?', 3200)
    caption(None, 600)
    rec.stop(1280)


def scene_resume(ctx):
    """History › Up next › Continue: the lesson goes on where you stopped."""
    page = ctx.new_page()
    segs = segments('16-01J9ybPE')
    stop = [s for s in segs if not s.get('ignore')][19]['end']  # stopped after part 2 (20 sentences)
    page.route('**/api/me/progress?id=16-01J9ybPE*', lambda r: r.fulfill(
        status=200, content_type='application/json',
        body=json.dumps({'progress': stop, 'date': int(time.time()) - 3600, 'partSize': 10})))
    page.goto(f'{B}/videos', wait_until='load')
    rail = page.locator('nav a[href="/my-videos"]:visible').first
    rail.wait_for(timeout=30000)
    page.wait_for_timeout(2500)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'resume', (1440, 900))
    rec.start()
    place(page, 700, 500)
    caption('History, in the menu on the left', 300)
    click(rail, 300)
    cont = page.get_by_role('link', name=re.compile('^Continue$')).or_(page.get_by_role('button', name=re.compile('^Continue$'))).first
    cont.wait_for(timeout=30000)
    page.wait_for_timeout(1500)
    caption('Up next: the video you did last', 300)
    look(page, cont.locator('xpath=ancestor::section[1]'), 2.2)
    rec.poster()
    caption('Press Continue', 300)
    click(cont, 300)
    pick_button(page).wait_for(timeout=30000)
    page.wait_for_timeout(1200)
    caption('Pick Listening', 300)
    click(pick_button(page), 300)
    caption('It goes on where you stopped', 300)
    wait_exercise(page)
    look(page, page.get_by_text(re.compile(r'Part \d+ of \d+')).first, 2.6)
    caption(None, 400)
    rec.stop(1280)


def scene_shadow(ctx):
    page = ctx.new_page()
    # green / brown / red words: "contention" close, "tremendous" left out
    canned(page, 'shadow-check', {**heard(LINE1, missing=('tremendous',)),
                                  'pronunciation': pronounced(LINE1, {'contention': 70, 'tremendous': 0})})
    open_lesson(page)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'shadow', (1440, 900))
    rec.start()
    place(page, 900, 600)
    caption('Bizzy asks: pick Speaking', 500)
    click(pick_button(page, 'Speaking'))
    caption('1. Listen to the line', 300)
    result = page.get_by_role('region', name='Shadowing result').first
    page.get_by_text(re.compile('Say it now')).or_(result).first.wait_for(timeout=30000)
    caption('2. The microphone opens: say it', 2200)
    if not result.is_visible():
        # it stops by itself after a quiet moment; if not yet, tap it
        rec_btn = page.get_by_test_id('record').first
        if rec_btn.is_visible():
            click(rec_btn, 300)
    result.wait_for(timeout=10000)
    move_to((1180, 760), 300)  # off the ear button: its tooltip would cover the result
    caption('3. Green: well said. Brown: close. Red: missed', 3000)
    rec.poster()
    caption('Enter: hear your take. Esc: try again', 2200)
    caption('Space: next line', 1000)
    page.keyboard.press('Space')
    page.wait_for_timeout(2500)
    caption(None, 400)
    rec.stop(1280)


SCENES = {'lesson': scene_lesson, 'hints': scene_hints, 'library': scene_library, 'speed': scene_speed,
          'navigate': scene_navigate, 'listen': scene_listen,
          'translation': scene_translation, 'word': scene_word, 'voice': scene_voice,
          'pronounce': scene_pronounce,
          'shadow': scene_shadow, 'resume': scene_resume, 'streak': scene_streak,
          'report': scene_report, 'words': scene_words,
          'whole': scene_whole, 'theme': scene_theme,
          'playlist': scene_playlist, 'playlist-make': scene_playlist_make,
          'your-words': scene_your_words,
          'practice': scene_practice, 'parts': scene_parts, 'skills': scene_skills, 'social': scene_social,
          'addvideo': scene_addvideo, 'layout': scene_layout, 'hover': scene_hover}

def sign_in(ctx):
    """The Demo Learner (words_demo.py: a Pro learner of French whose every /api answer is
    canned, so nothing is read from or written to any account), or with DD_SESSION a real
    Pro account, read-only (pro_session.py)."""
    global DEMO
    if pro_session.active():
        pro_session.apply(ctx, B)
        return
    import words_demo
    if DEMO is None:
        DEMO = words_demo.Demo(B)
    DEMO.reset()
    DEMO.install(ctx)


DEMO = None


def fake_voice():
    """A voice-like sound for the fake microphone (a tone pulsing like syllables):
    Chrome's own fake device beeps so rarely that the app hears silence."""
    path = os.path.join(tempfile.gettempdir(), 'dd-guide-fake-voice.wav')
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=180:duration=8',
                    '-f', 'lavfi', '-i', 'sine=frequency=4:duration=8', '-filter_complex',
                    '[0][1]amultiply,volume=4,aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=mono',
                    path], check=True)
    return path


if __name__ == '__main__':
    if sys.argv[1:2] == ['--render']:
        # draw again from the kept takes, without recording;
        # --render --lang vi [scene ...] draws the Vietnamese guide's videos
        args, lang = sys.argv[2:], None
        if args[:1] == ['--lang']:
            lang, args = args[1], args[2:]
        for name in args or sorted(os.listdir(TAKES)):
            render_take(name, lang)
        sys.exit()
    wanted = sys.argv[1:] or [*SCENES, 'mobile']
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True,
                                    # GPU: without it the subtitle cover's blur skips a playing video
                                    args=['--autoplay-policy=no-user-gesture-required',
                                          '--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=vulkan',
                                          '--enable-features=Vulkan',
                                          '--use-fake-ui-for-media-stream',
                                          '--use-fake-device-for-media-stream',
                                          f'--use-file-for-fake-audio-capture={fake_voice()}'])
        for name in wanted:
            if name == 'mobile':
                scene_mobile(browser)
                continue
            ctx = browser.new_context(viewport={'width': 1440, 'height': 900},
                                      permissions=['microphone'])
            sign_in(ctx)
            ctx.add_init_script(OVERLAY)
            try:
                SCENES[name](ctx)
            except Exception:
                # what the page showed when a scene broke (DD_DEBUG=<dir>)
                if os.environ.get('DD_DEBUG') and ctx.pages:
                    ctx.pages[-1].screenshot(path=f"{os.environ['DD_DEBUG']}/{name}-failed.png")
                raise
            ctx.close()
        browser.close()
