"""Signed-in shots for the guide from a LOCAL build of the app (never production:
it saves progress for the session's user). The Demo Learner (free plan, speaks
Vietnamese) needs the French lesson YCuU4SjcS2A and its translations/vi.json in
local R2 (see README › Screenshots).

    python3 scripts/capture_signed_in.py http://localhost:8788 images /tmp/cookie.txt [--only name ...]
    python3 scripts/to_webp.py

Writes: lesson-translation, lesson-gear-menu, bug-report, settings-languages,
settings-plan, shadowing-start, shadowing-ready, shadowing-listen, shadowing-pro.
Local data first (app repo, local D1/R2 only):
- the French lesson: put production's /transcripts/YCuU4SjcS2A.json (the public copy works) as
  YCuU4SjcS2A/dictation.json and /translations/YCuU4SjcS2A/vi.json as
  YCuU4SjcS2A/translations/vi.json; its source_hash must equal the lesson's
  (the ?h= the lesson asks for), or no translation line shows;
- the Pro card: the Demo Learner's Shadowing place on line 4 (see below).
The cookie file holds `node tests/e2e/mint_session.mjs authjs.session-token` from
the app repo (Demo Learner)."""
import json
import re
import sys
import urllib.request

from playwright.sync_api import sync_playwright

B = sys.argv[1].rstrip('/')
OUT = sys.argv[2]
cookie = open(sys.argv[3]).read().strip()
ONLY = sys.argv[5:] if len(sys.argv) > 4 and sys.argv[4] == '--only' else None
FR_VIDEO = 'YCuU4SjcS2A'   # Easy French 97, opens with an exercise
VIDEO = 'g4IAa8wZlqU'      # Sir Ken Robinson, 2:15
LISTEN_VIDEO = '-BvcToPZCLI'  # opens with a "Just listen" part


def wants(*names):
    return not ONLY or any(n in ONLY for n in names)


def shot(page, name, **kw):
    if ONLY and name not in ONLY:
        return
    page.screenshot(path=f'{OUT}/{name}.png', **kw)
    print('wrote', name, flush=True)


BOXES = {}


def box(page, name, label, loc):
    """[left, top, width, height] of loc in % of the 1440x900 shot, for <step box=>."""
    b = loc.first.bounding_box()
    if b:
        BOXES.setdefault(name, {})[label] = [round(b['x'] / 14.4, 1), round(b['y'] / 9, 1),
                                             round(b['width'] / 14.4, 1), round(b['height'] / 9, 1)]


def open_lesson(page, video):
    page.goto(f'{B}/videos/{video}', wait_until='load')
    page.wait_for_selector('text=START', timeout=20000)
    page.wait_for_selector('iframe[src*="youtube"]', timeout=20000)
    page.wait_for_timeout(3000)


with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True, args=[
        '--autoplay-policy=no-user-gesture-required',
        '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'])
    ctx = browser.new_context(viewport={'width': 1440, 'height': 900},
                              permissions=['microphone'])
    ctx.add_cookies([{'name': 'authjs.session-token', 'value': cookie,
                      'domain': re.sub(r'^https?://|:\d+$', '', B), 'path': '/'}])
    page = ctx.new_page()

    if wants('lesson-translation', 'lesson-gear-menu', 'bug-report'):
        open_lesson(page, FR_VIDEO)
        page.get_by_text('START', exact=True).click()
        page.mouse.move(400, 32)
        ta = page.get_by_placeholder(re.compile('what you hear')).first
        ta.wait_for(timeout=20000)
        page.wait_for_timeout(1500)
        # type the sentence on screen (the whole line is accepted, given words too)
        tr = json.load(urllib.request.urlopen(f'{B}/transcripts/{FR_VIDEO}.json'))
        clips = [x['text'].strip() for x in tr['segments']
                 if not x.get('ignore') and x.get('start') is not None]
        n = int(re.search(r'Exercise (\d+)/', page.get_by_text(
            re.compile(r'^Exercise \d+/\d+$')).first.inner_text()).group(1))
        ta.fill(clips[n - 1])
        page.get_by_text('You are correct!').first.wait_for(timeout=8000)
        page.wait_for_timeout(3500)
        shot(page, 'lesson-translation')
        page.locator('[data-testid="lesson-settings"]').first.click()
        page.wait_for_timeout(800)
        shot(page, 'lesson-gear-menu')
        box(page, 'lesson-gear-menu', 'gear', page.locator('[data-testid="lesson-settings"]'))
        box(page, 'lesson-gear-menu', 'translation', page.get_by_text('Translation', exact=True))
        box(page, 'lesson-gear-menu', 'report', page.get_by_text('Report a bug', exact=True))
        page.get_by_text('Report a bug', exact=True).first.click()
        page.locator('[data-testid="bug-report-note"]').wait_for(timeout=8000)
        page.wait_for_timeout(2500)
        page.locator('[data-testid="bug-report-note"]').type(
            'The video stopped before the last word of the sentence.', delay=10)
        page.wait_for_timeout(800)
        shot(page, 'bug-report')
        box(page, 'bug-report', 'note', page.locator('[data-testid="bug-report-note"]'))
        box(page, 'bug-report', 'include', page.get_by_text('Include the screenshot'))
        box(page, 'bug-report', 'also', page.get_by_text(re.compile('Also sent')))
        box(page, 'bug-report', 'send', page.get_by_role('button', name=re.compile('^send$', re.I)))

    if wants('settings-languages', 'settings-plan'):
        page.goto(f'{B}/settings', wait_until='load')
        page.get_by_text('Languages').first.wait_for(timeout=15000)
        page.wait_for_timeout(2000)
        shot(page, 'settings-plan')
        sec = page.get_by_text('I speak', exact=True).first
        sec.evaluate("el => el.scrollIntoView({block: 'center'})")
        page.wait_for_timeout(800)
        if not ONLY or 'settings-languages' in ONLY:
            card = sec.locator('xpath=ancestor::*[.//text()[normalize-space()="Translations"]][1]')
            card.screenshot(path=f'{OUT}/settings-languages.png')
            print('wrote settings-languages', flush=True)

    if wants('shadowing-pro'):
        # A free learner gets the Pro card from line 4. Before the run, put the
        # Demo Learner's saved place on line 4 in local D1 (the lesson resumes there):
        # UPDATE user_videos SET shadow_at=6.62 WHERE user_email='demo@example.com'
        #   AND video_id='g4IAa8wZlqU'
        page.goto(f'{B}/videos/{VIDEO}?mode=shadowing', wait_until='load')
        page.wait_for_selector('iframe[src*="youtube"]', timeout=20000)
        page.wait_for_timeout(1500)
        # the card is shown at once, without START
        page.get_by_text(re.compile('Shadowing is for Pro')).first.wait_for(timeout=15000)
        page.wait_for_timeout(1500)
        shot(page, 'shadowing-pro')

    if wants('shadowing-start', 'shadowing-ready'):
        page.goto(f'{B}/videos/{VIDEO}?mode=shadowing', wait_until='load')
        page.wait_for_selector('iframe[src*="youtube"]', timeout=20000)
        page.wait_for_timeout(1500)
        if not page.get_by_text('START', exact=True).count():
            page.get_by_role('button', name=re.compile('^Shadowing')).first.click()
        page.get_by_text('START', exact=True).first.wait_for(timeout=15000)
        page.wait_for_timeout(4500)
        shot(page, 'shadowing-start')
        page.get_by_text('START', exact=True).first.click()
        page.mouse.move(400, 32)
        page.wait_for_timeout(1800)
        shot(page, 'shadowing-ready')
    if wants('shadowing-listen'):
        page.goto(f'{B}/videos/{LISTEN_VIDEO}?mode=shadowing', wait_until='load')
        page.wait_for_selector('iframe[src*="youtube"]', timeout=20000)
        page.wait_for_timeout(1500)
        if not page.get_by_text('START', exact=True).count():
            page.get_by_role('button', name=re.compile('^Shadowing')).first.click()
        page.get_by_text('START', exact=True).first.click(timeout=15000)
        page.mouse.move(400, 32)
        page.get_by_text('Just listen').first.wait_for(timeout=20000)
        page.wait_for_timeout(2500)
        shot(page, 'shadowing-listen')

    browser.close()

for name, found in BOXES.items():
    print(name, found)
