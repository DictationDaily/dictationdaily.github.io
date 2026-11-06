"""Record short screen recordings of the app for the guide (videos/*.mp4).

A fake pointer and a caption bar are drawn into the page so learners can follow
each step. Frames come from Chrome's screencast and are encoded with ffmpeg.
Signed out, or (DD_SESSION, see pro_session.py) as a Pro learner with every
write blocked and every lesson unstarted, so nothing is saved to any account.

usage: [DD_BASE=http://localhost:8788] python3 scripts/record.py [scene ...]
       python3 scripts/record.py --render [--lang vi] [scene ...]  (redraw kept takes)
DD_BASE records a local build instead of production, e.g. before a UI change
is deployed (dictationdaily.com: tests/e2e/local_worker.sh).
scenes: lesson library speed navigate listen mobile, and with DD_SESSION (Pro):
translation word voice pronounce shadow resume streak report
words (Pro, every /api answer canned by words_demo.py: no DD_SESSION needed)
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

    def move_to(loc_or_xy, wait=750):
        if isinstance(loc_or_xy, tuple):
            x, y = loc_or_xy
        else:
            box = loc_or_xy.bounding_box()
            x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        page.evaluate(f'window.__move({x},{y})')
        log('move', x=x, y=y, dur=0.7)
        # The real mouse follows the drawn pointer: a click leaves it where it
        # clicked, and a button that later appears there (CONTINUE where
        # START was) would open its tooltip in the recording
        page.mouse.move(x, y)
        page.wait_for_timeout(wait)
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


def open_lesson(page, video=VIDEO):
    page.goto(f'{B}/videos/{video}', wait_until='load')
    page.wait_for_selector('text=START', timeout=20000)
    page.wait_for_selector('iframe[src*="youtube"]', timeout=20000)
    page.wait_for_timeout(4000)


def wait_exercise(page):
    page.get_by_placeholder(re.compile('what you hear')).first.wait_for(state='visible', timeout=60000)


def scene_lesson(ctx):
    page = ctx.new_page()
    open_lesson(page)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'lesson', (1440, 900))
    rec.start()
    place(page, 900, 600)
    caption('<b>1</b>Press START', 600)
    click(page.get_by_text('START', exact=True))
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
    page.get_by_text('START', exact=True).click()
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


def scene_library(ctx):
    page = ctx.new_page()
    # English, like the library screenshots (a signed-in learner sees their learning language)
    page.goto(f'{B}/videos?lang=en', wait_until='load')
    page.wait_for_selector('img[src*="ytimg.com"]', timeout=20000)
    page.wait_for_timeout(3000)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'library', (1440, 900))
    rec.start()
    place(page, 700, 500)
    caption('<b>1</b>Pick a topic', 400)
    click(page.get_by_role('button', name=re.compile('^Mind & psychology')))
    page.wait_for_timeout(1600)
    caption('<b>2</b>Short on time? Quick win', 300)
    click(page.get_by_role('button', name=re.compile('^Quick win')))
    page.wait_for_timeout(1600)
    caption('<b>3</b>Sort: Slowest speaker first', 300)
    click(page.get_by_role('button', name=re.compile('^Sort')))
    page.wait_for_timeout(700)
    click(page.get_by_role('menuitemradio', name=re.compile('^Slowest')))
    page.wait_for_timeout(1800)
    rec.poster()
    caption('<b>4</b>Click a video', 300)
    # the first card of the filtered list (signed in, "Pick up where you left off" comes first)
    card = page.locator('xpath=//*[contains(normalize-space(.), "Find your next video")][not(*)]'
                        '/following::a[starts-with(@href, "/videos/")][1]')
    move_to(card, 900)
    page.wait_for_timeout(500)
    click(card, 200)
    page.wait_for_selector('text=START', timeout=20000)
    caption('The lesson opens. Press START!', 3500)
    caption(None, 600)
    rec.stop(1280)


def scene_speed(ctx):
    page = ctx.new_page()
    open_lesson(page)
    move_to, click, caption = helpers(page)
    page.get_by_text('START', exact=True).click()
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
    page.get_by_text('START', exact=True).click()
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
    click(page.get_by_text('START', exact=True))
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
    pro_session.apply(ctx, B)
    ctx.add_init_script(OVERLAY)
    page = ctx.new_page()
    open_lesson(page)
    page.evaluate('window.__touch()')
    move_to, click, caption = helpers(page, touch=True)
    rec = Recorder(page, 'mobile', (780, 1688))
    rec.start()
    place(page, 195, 600)
    caption('Tap START', 400, small=True)
    click(page.get_by_text('START', exact=True))
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
    page.get_by_text('START', exact=True).click()
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
    caption('Press START: a French sentence plays', 400)
    click(page.get_by_text('START', exact=True))
    wait_exercise(page)
    page.wait_for_timeout(1800)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    caption('Type what you hear')
    move_to(ta, 300)
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
    page.get_by_text('START', exact=True).click()
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
    click(page.get_by_text('START', exact=True))
    wait_exercise(page)
    page.wait_for_timeout(1500)
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    move_to(ta, 200)
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


def scene_shadow(ctx):
    page = ctx.new_page()
    # green / brown / red words (since 2026-11-05): "contention" close,
    # "tremendous" left out
    canned(page, 'shadow-check', {**heard(LINE1, missing=('tremendous',)),
                                  'pronunciation': pronounced(LINE1, {'contention': 70, 'tremendous': 0})})
    page.goto(f'{B}/videos/{VIDEO}?mode=shadowing', wait_until='load')
    page.wait_for_selector('iframe[src*="youtube"]', timeout=20000)
    page.wait_for_timeout(1500)
    if not page.get_by_text('START', exact=True).count():
        page.get_by_role('button', name=re.compile('^Shadowing')).first.click()
    page.get_by_text('START', exact=True).first.wait_for(timeout=15000)
    page.wait_for_timeout(2500)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'shadow', (1440, 900))
    rec.start()
    place(page, 900, 600)
    caption('Press START', 400)
    click(page.get_by_text('START', exact=True).first)
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
    caption('3. Green: well said. Brown: close. Red: missed', 3000)
    rec.poster()
    caption('Enter: hear your take. Esc: try again', 2200)
    caption('Space: next line', 1000)
    page.keyboard.press('Space')
    page.wait_for_timeout(2500)
    caption(None, 400)
    rec.stop(1280)


def scene_resume(ctx):
    page = ctx.new_page()
    # this recording's started video resumes 2 minutes in
    page.route('**/api/me/progress?id=*', lambda r: r.fulfill(
        status=200, content_type='application/json', body='{"progress":120,"date":null}'))
    page.goto(f'{B}/videos', wait_until='load')
    page.get_by_text('Pick up where you left off').wait_for(timeout=20000)
    page.wait_for_selector('img[src*="ytimg.com"]', timeout=20000)
    page.wait_for_timeout(2500)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'resume', (1440, 900))
    rec.start()
    place(page, 700, 500)
    caption('Signed in, your videos wait at the top', 1800)
    rec.poster()
    caption('Click one', 300)
    card = page.locator('xpath=//*[normalize-space(.)="Pick up where you left off"][not(*)]'
                        '/following::a[starts-with(@href, "/videos/")][1]')
    click(card)
    page.get_by_text('START', exact=True).first.wait_for(timeout=20000)
    page.wait_for_timeout(1500)
    click(page.get_by_text('START', exact=True).first, 300)
    wait_exercise(page)
    caption('It goes on where you stopped', 2600)
    caption(None, 400)
    rec.stop(1280)


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
    page.get_by_text('START', exact=True).click()
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
    import words_demo
    page = ctx.new_page()
    words_demo.Demo(B).install(page)
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
    caption('See words: every word you saved', 300)
    see = page.get_by_test_id('word-save-note').get_by_role('link').first
    see.evaluate('a => a.removeAttribute("target")')  # it opens a new tab; the recording stays in this one
    click(see)
    page.get_by_test_id('saved-word').first.wait_for(timeout=30000)
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


SCENES = {'lesson': scene_lesson, 'hints': scene_hints, 'library': scene_library, 'speed': scene_speed,
          'navigate': scene_navigate, 'listen': scene_listen,
          'translation': scene_translation, 'word': scene_word, 'voice': scene_voice,
          'pronounce': scene_pronounce,
          'shadow': scene_shadow, 'resume': scene_resume, 'streak': scene_streak,
          'report': scene_report, 'words': scene_words}

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
                                    args=['--autoplay-policy=no-user-gesture-required',
                                          '--use-fake-ui-for-media-stream',
                                          '--use-fake-device-for-media-stream',
                                          f'--use-file-for-fake-audio-capture={fake_voice()}'])
        for name in wanted:
            if name == 'mobile':
                scene_mobile(browser)
                continue
            ctx = browser.new_context(viewport={'width': 1440, 'height': 900},
                                      permissions=['microphone'])
            pro_session.apply(ctx, B)
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
