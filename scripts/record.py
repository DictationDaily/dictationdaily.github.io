"""Record short screen recordings of the app for the guide (videos/*.mp4).

A fake pointer and a caption bar are drawn into the page so learners can follow
each step. Frames come from Chrome's screencast and are encoded with ffmpeg.
Signed out only, so nothing is saved to any account.

usage: [DD_BASE=http://localhost:8788] python3 scripts/record.py [scene ...]
DD_BASE records a local build instead of production, e.g. before a UI change
is deployed (dictationdaily.com: tests/e2e/local_worker.sh).
scenes: lesson library speed navigate listen mobile
"""
import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile

from playwright.sync_api import sync_playwright

B = os.environ.get('DD_BASE', 'https://dictationdaily.com').rstrip('/')
VIDEO = 'g4IAa8wZlqU'  # Sir Ken Robinson, 2:15, opens with an exercise
# Opens with a "Just listen" part. A local build has only a few transcripts; this one is among them
LISTEN_VIDEO = '-BvcToPZCLI' if 'DD_BASE' in os.environ else 'Tp8xIgyyK7I'
CLIP1 = 'My contention is all kids have tremendous talents and we squander them pretty ruthlessly.'
# The lesson gives two words each side ("My contention … pretty ruthlessly."); learners type the rest
REST = ' have tremendous talents and we squander them'
OUT = 'videos'

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
      #__cap.small{font-size:30px;bottom:150px;white-space:normal;width:86%;text-align:center}`;
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

    def start(self):
        w, h = self.size
        self.cdp.send('Page.startScreencast', {'format': 'jpeg', 'quality': 88, 'maxWidth': w, 'maxHeight': h})

    def stop(self, out_width):
        self.page.wait_for_timeout(300)
        self.cdp.send('Page.stopScreencast')
        self.stopped = True
        lines = []
        for i, (path, t) in enumerate(self.frames):
            nxt = self.frames[i + 1][1] if i + 1 < len(self.frames) else t + 1.5
            lines.append(f"file '{path}'\nduration {max(nxt - t, 0.001):.4f}")
        lines.append(f"file '{self.frames[-1][0]}'")
        concat = os.path.join(self.dir, 'list.txt')
        with open(concat, 'w') as f:
            f.write('\n'.join(lines))
        os.makedirs(OUT, exist_ok=True)
        mp4 = f'{OUT}/{self.name}.mp4'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', concat,
                        '-vf', f'scale={out_width}:-2:flags=lanczos,fps=25,format=yuv420p',
                        '-c:v', 'libx264', '-preset', 'slow', '-crf', '27', '-movflags', '+faststart', '-an', mp4],
                       check=True)
        seek = ['-ss', f'{self.poster_at:.2f}'] if self.poster_at is not None else ['-sseof', '-0.1']
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *seek, '-i', mp4, '-frames:v', '1',
                        '-vf', f'scale={out_width}:-2', f'{OUT}/{self.name}.jpg'], check=True)
        shutil.rmtree(self.dir)
        print('wrote', mp4, f'{os.path.getsize(mp4) // 1024} KB', flush=True)


def helpers(page, touch=False):
    def move_to(loc_or_xy, wait=750):
        if isinstance(loc_or_xy, tuple):
            x, y = loc_or_xy
        else:
            box = loc_or_xy.bounding_box()
            x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        page.evaluate(f'window.__move({x},{y})')
        page.wait_for_timeout(wait)
        return x, y

    def click(loc_or_xy, wait=750):
        x, y = move_to(loc_or_xy, wait)
        page.evaluate(f'window.__ripple({x},{y})')
        if touch:
            page.touchscreen.tap(x, y)
        else:
            page.mouse.click(x, y)

    def caption(text, wait=0, small=False):
        page.evaluate('([t, s]) => window.__caption(t, s)', [text, small])
        if wait:
            page.wait_for_timeout(wait)

    return move_to, click, caption


def open_lesson(page, video=VIDEO):
    page.goto(f'{B}/videos/{video}', wait_until='load')
    page.wait_for_selector('text=START', timeout=20000)
    page.wait_for_selector('iframe[src*="youtube"]', timeout=20000)
    page.wait_for_timeout(4000)


def wait_exercise(page):
    page.get_by_placeholder('Type what you hear').first.wait_for(state='visible', timeout=60000)


def scene_lesson(ctx):
    page = ctx.new_page()
    open_lesson(page)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'lesson', (1440, 900))
    rec.start()
    page.evaluate('window.__move(900, 600)')
    caption('<b>1</b>Press START', 600)
    click(page.get_by_text('START', exact=True))
    wait_exercise(page)
    caption('<b>2</b>Listen. The red line shows your words', 3400)
    ta = page.get_by_placeholder('Type what you hear').first
    caption('<b>3</b>Type the missing words')
    move_to(ta, 500)
    ta.press_sequentially('ix all kids', delay=110)
    page.wait_for_timeout(500)
    caption('<b>4</b>Press Enter to check', 1200)
    ta.press('Enter')
    page.wait_for_timeout(600)
    caption('<b>5</b>Fix the red word', 900)
    rec.poster()
    page.wait_for_timeout(900)
    ta.press_sequentially('is', delay=160)
    page.keyboard.press('End')
    caption('<b>6</b>Type the rest')
    ta.press_sequentially(REST, delay=70)
    # a complete answer is accepted as it's typed
    page.get_by_role('button', name=re.compile('^continue', re.I)).wait_for(timeout=8000)
    caption('✓ Right! It checks by itself', 2400)
    caption('Press Space for the next sentence', 1400)
    page.keyboard.press('Space')
    caption(None, 2500)
    rec.stop(1280)


def scene_library(ctx):
    page = ctx.new_page()
    page.goto(f'{B}/videos', wait_until='load')
    page.wait_for_selector('img[src*="ytimg.com"]', timeout=20000)
    page.wait_for_timeout(3000)
    move_to, click, caption = helpers(page)
    rec = Recorder(page, 'library', (1440, 900))
    rec.start()
    page.evaluate('window.__move(700, 500)')
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
    card = page.locator('a[href^="/videos/"]').first
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
    page.evaluate('window.__move(500, 450)')
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
    page.evaluate('window.__move(1100, 700)')
    caption('🐢 Now the sentence plays slowly', 5000)
    caption(None, 400)
    rec.stop(1280)


def scene_navigate(ctx):
    page = ctx.new_page()
    open_lesson(page)
    move_to, click, caption = helpers(page)
    page.get_by_text('START', exact=True).click()
    wait_exercise(page)
    ta = page.get_by_placeholder('Type what you hear').first
    ta.fill(CLIP1)
    ta.press('Enter')
    page.wait_for_timeout(800)
    page.keyboard.press('Space')
    wait_exercise(page)
    page.wait_for_timeout(1000)
    rec = Recorder(page, 'navigate', (1440, 900))
    rec.start()
    page.evaluate('window.__move(1000, 600)')
    caption('Too hard? Press <b style="margin:0">Esc</b> to skip it', 1800)
    page.keyboard.press('Escape')
    page.wait_for_timeout(1500)
    caption('Go back with the ◀ arrow', 300)
    back = page.locator('header, .MuiAppBar-positionFixed').last.locator('button').first
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
    page.evaluate('window.__move(900, 600)')
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
    ctx.add_init_script(OVERLAY)
    page = ctx.new_page()
    open_lesson(page)
    page.evaluate('window.__touch()')
    move_to, click, caption = helpers(page, touch=True)
    rec = Recorder(page, 'mobile', (780, 1688))
    rec.start()
    page.evaluate('window.__move(195, 600)')
    caption('Tap START', 400, small=True)
    click(page.get_by_text('START', exact=True))
    wait_exercise(page)
    ta = page.get_by_placeholder('Type what you hear').first
    caption('Tap the box. Type the missing words', 300, small=True)
    click(ta)
    ta.press_sequentially('ix all kids', delay=100)
    caption('Tap CHECK', 300, small=True)
    click(page.get_by_role('button', name='CHECK'))
    page.wait_for_timeout(600)
    caption('Fix the red word', 700, small=True)
    rec.poster()
    page.wait_for_timeout(800)
    ta.press_sequentially('is', delay=150)
    page.keyboard.press('End')
    caption('Type the rest', 300, small=True)
    ta.press_sequentially(REST, delay=60)
    # a complete answer is accepted as it's typed
    cont = page.get_by_role('button', name=re.compile('^continue', re.I))
    cont.wait_for(timeout=8000)
    caption('✓ Right! Tap CONTINUE', 1800, small=True)
    click(cont)
    page.wait_for_timeout(1500)
    caption(None, 400)
    rec.stop(390)


SCENES = {'lesson': scene_lesson, 'library': scene_library, 'speed': scene_speed,
          'navigate': scene_navigate, 'listen': scene_listen}

if __name__ == '__main__':
    wanted = sys.argv[1:] or [*SCENES, 'mobile']
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True,
                                    args=['--autoplay-policy=no-user-gesture-required'])
        for name in wanted:
            if name == 'mobile':
                scene_mobile(browser)
                continue
            ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
            ctx.add_init_script(OVERLAY)
            SCENES[name](ctx)
            ctx.close()
        browser.close()
