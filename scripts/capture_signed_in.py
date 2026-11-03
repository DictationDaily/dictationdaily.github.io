"""Signed-in shots for the guide, as a Pro learner.

Production, read-only (preferred): a Pro account's session, every write blocked
and every lesson looking unstarted, name/email/picture replaced (pro_session.py):

    DD_SESSION=/path/to/cookie.txt python3 scripts/capture_signed_in.py https://dictationdaily.com images
    python3 scripts/to_webp.py

Writes: signed-in-library, account-menu, my-videos, my-learning (whole page),
lesson-translation, lesson-gear-menu, bug-report (never sent),
settings-plan, settings-languages, shadowing-start, shadowing-ready,
shadowing-listen, shadowing-phone, lesson-resumed, lesson-finished-streak,
lesson-finished-return. --only name ... for some of them.

Nothing here makes a paid call: no word lookups, no Say it, no Shadowing take
is checked (the microphone is a fake device and the check is blocked). A
lesson whose translation isn't made yet orders one (OpenAI, under a cent).
"""
import json
import re
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

import pro_session

B = sys.argv[1].rstrip('/')
OUT = sys.argv[2]
ONLY = sys.argv[4:] if len(sys.argv) > 3 and sys.argv[3] == '--only' else None
assert pro_session.active(), 'set DD_SESSION (see pro_session.py)'
FR_VIDEO = 'YCuU4SjcS2A'     # Easy French 97, opens with an exercise
VIDEO = 'g4IAa8wZlqU'        # Sir Ken Robinson, 2:15, 42 sentences
LISTEN_VIDEO = 'Tp8xIgyyK7I'  # opens with a "Just listen" part
RESUME_VIDEO, RESUME_AT = '0G2U0R0hOCU', 400.5  # resumes at exercise 97/212
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/130 dd-guide-capture'}
BOXES = {}


def wants(*names):
    return not ONLY or any(n in ONLY for n in names)


def shot(page, name, **kw):
    if ONLY and name not in ONLY:
        return
    page.screenshot(path=f'{OUT}/{name}.png', **kw)
    print('wrote', name, flush=True)


def box(page, name, label, loc):
    """[left, top, width, height] of loc in % of the shot, for <step box=>."""
    vw, vh = page.viewport_size['width'], page.viewport_size['height']
    b = loc.first.bounding_box()
    if b:
        BOXES.setdefault(name, {})[label] = [round(b['x'] / vw * 100, 1), round(b['y'] / vh * 100, 1),
                                             round(b['width'] / vw * 100, 1),
                                             round(b['height'] / vh * 100, 1)]


def clips(video):
    req = urllib.request.Request(f'{B}/transcripts/{video}.json', headers=UA)
    tr = json.load(urllib.request.urlopen(req))
    return [x['text'].strip() for x in tr['segments']
            if not x.get('ignore') and x.get('start') is not None]


def saved(page, video, progress, date=None):
    """Make this page see a saved place in video (overrides pro_session's 'unstarted')."""
    body = json.dumps({'progress': progress, 'date': date})
    page.route(f'**/api/me/progress?id={video}*',
               lambda r: r.fulfill(status=200, content_type='application/json', body=body))


def open_lesson(page, video, mode=''):
    page.goto(f'{B}/videos/{video}{mode}', wait_until='load')
    page.wait_for_selector('iframe[src*="youtube"]', timeout=20000)
    page.wait_for_timeout(3000)


def exercise(page):
    label = page.get_by_text(re.compile(r'^Exercise \d+/\d+$')).first
    return int(re.search(r'(\d+)/', label.inner_text()).group(1))


def answer(page, text):
    ta = page.get_by_placeholder(re.compile('what you hear')).first
    ta.fill(text)
    page.get_by_text('You are correct!').first.wait_for(timeout=8000)


def shadowing(page, video):
    open_lesson(page, video, '?mode=shadowing')
    if not page.get_by_text('START', exact=True).count():
        page.get_by_role('button', name=re.compile('^Shadowing')).first.click()
    page.get_by_text('START', exact=True).first.wait_for(timeout=15000)


with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True, args=[
        '--autoplay-policy=no-user-gesture-required',
        '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'])

    def context(**kw):
        ctx = browser.new_context(permissions=['microphone'], **kw)
        pro_session.apply(ctx, B)
        return ctx

    page = context(viewport={'width': 1440, 'height': 900}).new_page()

    if wants('signed-in-library', 'account-menu', 'my-videos', 'my-learning'):
        def cards(pg):
            pg.wait_for_selector('img[src*="ytimg.com"]', timeout=20000)
            pg.wait_for_timeout(2500)
        page.goto(f'{B}/videos', wait_until='load')
        page.get_by_role('link', name=re.compile(r'^\d+ day streak$')).first.wait_for(timeout=20000)
        page.get_by_text('Pick up where you left off').wait_for(timeout=20000)
        cards(page)
        shot(page, 'signed-in-library')
        page.get_by_role('button', name='Account').click()
        page.wait_for_timeout(1000)
        shot(page, 'account-menu')
        page.keyboard.press('Escape')
        page.goto(f'{B}/my-videos', wait_until='load')
        page.get_by_role('region', name='Up next').wait_for(timeout=20000)
        cards(page)
        shot(page, 'my-videos')
        page.goto(f'{B}/my-learning', wait_until='load')
        page.get_by_text('Last 6 months').wait_for(timeout=20000)
        page.wait_for_timeout(3000)
        shot(page, 'my-learning', full_page=True)  # the guide uses its top and bottom 900 px

    if wants('lesson-translation', 'lesson-gear-menu', 'bug-report'):
        fr = clips(FR_VIDEO)
        open_lesson(page, FR_VIDEO)
        page.get_by_text('START', exact=True).click()
        page.mouse.move(400, 32)
        page.get_by_placeholder(re.compile('what you hear')).first.wait_for(timeout=20000)
        page.wait_for_timeout(1500)
        answer(page, fr[exercise(page) - 1])
        page.get_by_text(re.compile('Xin chào')).first.wait_for(timeout=30000)
        page.wait_for_timeout(2000)
        shot(page, 'lesson-translation')
        page.locator('[data-testid="lesson-settings"]').first.click()
        page.wait_for_timeout(800)
        shot(page, 'lesson-gear-menu')
        box(page, 'lesson-gear-menu', 'gear', page.locator('[data-testid="lesson-settings"]'))
        box(page, 'lesson-gear-menu', 'report', page.get_by_text('Report a bug', exact=True))
        page.get_by_text('Report a bug', exact=True).first.click()
        note = page.locator('[data-testid="bug-report-note"]')
        note.wait_for(timeout=8000)
        page.wait_for_timeout(2500)
        note.type('The video stopped before the last word of the sentence.', delay=10)
        page.wait_for_timeout(800)
        shot(page, 'bug-report')
        box(page, 'bug-report', 'note', note)
        box(page, 'bug-report', 'also', page.get_by_text(re.compile('Also sent')))
        box(page, 'bug-report', 'include', page.get_by_text('Include the screenshot'))
        box(page, 'bug-report', 'send', page.get_by_role('button', name=re.compile('^send$', re.I)))
        page.keyboard.press('Escape')

    if wants('settings-plan', 'settings-languages'):
        page.goto(f'{B}/settings', wait_until='load')
        page.get_by_text('I speak', exact=True).first.wait_for(timeout=15000)
        page.wait_for_timeout(2500)
        shot(page, 'settings-plan')
        sec = page.get_by_text('I speak', exact=True).first
        sec.evaluate("el => el.scrollIntoView({block: 'center'})")
        page.wait_for_timeout(800)
        if not ONLY or 'settings-languages' in ONLY:
            card = sec.locator('xpath=ancestor::*[.//text()[normalize-space()="Translations"]][1]')
            card.screenshot(path=f'{OUT}/settings-languages.png')
            print('wrote settings-languages', flush=True)

    if wants('shadowing-start', 'shadowing-ready'):
        shadowing(page, VIDEO)
        page.wait_for_timeout(4500)
        shot(page, 'shadowing-start')
        page.get_by_text('START', exact=True).first.click()
        page.mouse.move(400, 32)
        page.wait_for_timeout(1800)
        shot(page, 'shadowing-ready')

    if wants('shadowing-listen'):
        shadowing(page, LISTEN_VIDEO)
        page.get_by_text('START', exact=True).first.click()
        page.mouse.move(400, 32)
        page.get_by_text('Just listen').first.wait_for(timeout=20000)
        page.wait_for_timeout(2500)
        shot(page, 'shadowing-listen')

    if wants('shadowing-phone'):
        mp = context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True,
                     device_scale_factor=2).new_page()
        shadowing(mp, VIDEO)
        mp.get_by_text('START', exact=True).first.tap()
        # the microphone opens by itself when the line ends: "Say it now"
        mp.get_by_text(re.compile('Say it now')).first.wait_for(timeout=30000)
        mp.wait_for_timeout(900)
        shot(mp, 'shadowing-phone')

    if wants('lesson-resumed'):
        saved(page, RESUME_VIDEO, RESUME_AT, int(time.time()) - 86400)
        open_lesson(page, RESUME_VIDEO)
        page.get_by_text('START', exact=True).click()
        page.mouse.move(400, 32)
        page.get_by_placeholder(re.compile('what you hear')).first.wait_for(timeout=20000)
        page.wait_for_timeout(2500)
        shot(page, 'lesson-resumed')
        page.unroute(f'**/api/me/progress?id={RESUME_VIDEO}*')

    if wants('lesson-finished-streak'):
        lines = clips(VIDEO)
        fp = context(viewport={'width': 1440, 'height': 900}).new_page()
        open_lesson(fp, VIDEO)
        fp.get_by_text('START', exact=True).click()
        fp.mouse.move(400, 32)
        done = fp.get_by_text(re.compile(r'-day streak!$|^Lesson done!$')).first
        for _ in range(200):
            if done.count() and done.is_visible():
                break
            ta = fp.get_by_placeholder(re.compile('what you hear')).first
            if ta.count() and ta.is_visible() and ta.is_editable():
                answer(fp, lines[exercise(fp) - 1])
                fp.wait_for_timeout(300)
            fp.keyboard.press('Space')
            fp.wait_for_timeout(700)
        done.wait_for(timeout=10000)
        fp.wait_for_timeout(2500)
        shot(fp, 'lesson-finished-streak')

    if wants('lesson-finished-return'):
        saved(page, VIDEO, 135, int(time.time()) - 2 * 86400)
        open_lesson(page, VIDEO)
        page.get_by_text(re.compile('done this one')).first.wait_for(timeout=20000)
        page.wait_for_timeout(2000)
        shot(page, 'lesson-finished-return')

    browser.close()

for name, found in BOXES.items():
    print(name, found)
