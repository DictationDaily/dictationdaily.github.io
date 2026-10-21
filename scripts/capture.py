"""Extra signed-out screenshots of dictationdaily.com for the guide site.
Read-only: never signs in, so nothing is saved.
usage: [DD_BASE=http://localhost:8788] python3 scripts/capture.py images [--only name ...]
PNGs are written; convert them with scripts/to_webp.py before committing.
src/coords.json gets the position of the buttons in each lesson shot, in % of
the screenshot, for the x/y of the markers in <tour> steps."""
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

B = os.environ.get('DD_BASE', 'https://dictationdaily.com').rstrip('/')
OUT = sys.argv[1]
ONLY = sys.argv[3:] if len(sys.argv) > 2 and sys.argv[2] == '--only' else None
VIDEO = 'g4IAa8wZlqU'  # Sir Ken Robinson, 2:15
CLIP1 = 'My contention is all kids have tremendous talents,'
# The lesson gives the first and last word ("My … talents,"); learners type the rest
GAP = 'contention is all kids have tremendous'
COORDS = {}


def wants(*names):
    return not ONLY or any(n.startswith(name) for n in ONLY for name in names)


def coords(page, name, targets):
    """Centre of each target, in % of the viewport, for <step x= y=>."""
    if ONLY and name not in ONLY:
        return
    vw, vh = page.viewport_size['width'], page.viewport_size['height']
    found = {}
    for label, loc in targets.items():
        try:
            box = loc.first.bounding_box(timeout=2000)
        except Exception:
            box = None
        if box:
            found[label] = [round((box['x'] + box['width'] / 2) / vw * 100, 1),
                            round((box['y'] + box['height'] / 2) / vh * 100, 1)]
    COORDS[name] = found


def shot(page, name, **kw):
    if ONLY and name not in ONLY:
        return
    page.screenshot(path=f'{OUT}/{name}.png', **kw)
    print('wrote', name, flush=True)


def eshot(loc, name):
    if ONLY and name not in ONLY:
        return
    loc.screenshot(path=f'{OUT}/{name}.png')
    print('wrote', name, flush=True)


def library(page, query=''):
    page.goto(f'{B}/videos{query}', wait_until='load')
    page.wait_for_selector('img[src*="ytimg.com"]', timeout=20000)
    page.wait_for_timeout(2500)


def wait_exercise(page, timeout=60):
    deadline = time.time() + timeout
    label = page.get_by_text(re.compile(r'^Exercise \d+/\d+$'))
    while not label.count() or page.get_by_role('heading', name='Just listen').count():
        assert time.time() < deadline, 'no exercise'
        page.wait_for_timeout(300)


def open_lesson(page):
    page.goto(f'{B}/videos/{VIDEO}', wait_until='load')
    page.wait_for_selector('text=START', timeout=20000)
    page.wait_for_selector('iframe[src*="youtube"]', timeout=20000)
    page.wait_for_timeout(3500)


def lesson_targets(page):
    bottom = page.locator('.MuiAppBar-positionFixed').last
    return {
        'start': page.get_by_text('START', exact=True),
        'replay': page.get_by_role('button', name=re.compile('^replay', re.I)),
        'skip': page.get_by_role('button', name=re.compile('^skip', re.I)),
        'undo': page.get_by_role('button', name=re.compile('^undo', re.I)),
        # By text: while its tooltip is open, the tooltip names the button
        'continue': page.get_by_role('button').filter(has_text=re.compile('^continue$', re.I)),
        'check': page.get_by_role('button', name=re.compile('^check', re.I)),
        'textarea': page.get_by_placeholder('Type what you hear'),
        'matching': page.get_by_text(re.compile(r'^(Matching|Almost)')),
        'del': page.locator('del'),
        'ins': page.locator('ins'),
        'tick': page.locator('[data-testid="CheckCircleRoundedIcon"]'),
        'exercise': page.get_by_text(re.compile(r'^Exercise \d+/\d+$')),
        'back': bottom.locator('button').first,
        'forward': bottom.locator('button').nth(1),
        'close': page.get_by_role('button', name=re.compile('^close', re.I)),
        'gear': page.locator('iframe[src*="youtube"]'),
    }


def lesson_shot(page, name):
    shot(page, name)
    coords(page, name, lesson_targets(page))


with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True,
                                args=['--autoplay-policy=no-user-gesture-required'])
    ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
    page = ctx.new_page()

    if wants('home'):
        page.goto(B + '/', wait_until='load')
        page.get_by_role('button', name='Sign In').first.wait_for(timeout=15000)
        page.wait_for_timeout(2000)
        shot(page, 'home-hero')
        tabs = [('INTERMEDIATE', 'b1'), ('UPPER INTERMEDIATE', 'b2'),
                ('ADVANCED', 'c1'), ('PROFICIENT', 'c2')]
        for label, code in tabs:
            page.get_by_role('tab', name=re.compile(f'^{label}$', re.I)).click()
            page.wait_for_timeout(2500)
            box = page.get_by_role('tablist').first.bounding_box()
            y = box['y'] + page.evaluate('window.scrollY') - 150
            shot(page, f'home-level-{code}', full_page=True,
                 clip={'x': 0, 'y': y, 'width': 1440, 'height': 820})

    if wants('library'):
        library(page)
        shot(page, 'library')
        eshot(page.locator('a[href^="/videos/"]').first, 'library-card')
        for sort in ['Popular', 'Slow']:
            library(page, f'?sort={sort}')
            shot(page, f'library-sort-{sort.lower()}')
        for lvl in ['B1', 'B2', 'C1', 'C2']:
            library(page, f'?level={lvl}')
            shot(page, f'library-level-{lvl.lower()}')
        library(page, '?sort=Slow&level=B1&duration=under-4-minutes')
        shot(page, 'library-combined')
        library(page, '?duration=over-20-minutes')
        shot(page, 'library-duration-long')
        library(page)
        page.mouse.wheel(0, 20000)
        page.wait_for_timeout(1500)
        shot(page, 'library-load-more')

    if wants('lesson', 'hint', 'bottom'):
        open_lesson(page)
        lesson_shot(page, 'lesson-intro')
        page.get_by_text('START', exact=True).click()
        wait_exercise(page)
        # while the hidden words play, the gap's red line is filling
        page.wait_for_timeout(3200)
        lesson_shot(page, 'lesson-clip-playing')
        ta = page.get_by_placeholder('Type what you hear').first
        ta.fill('contention is all kids')
        lesson_shot(page, 'lesson-typing')
        ta.press('Enter')
        page.wait_for_timeout(1000)
        lesson_shot(page, 'lesson-hint-missing')
        ta.fill('contention is all the kids have tremendous')
        ta.press('Enter')
        page.wait_for_timeout(1000)
        lesson_shot(page, 'lesson-hint-extra')
        ta.fill('contention is all kids have tremendus')
        ta.press('Enter')
        page.wait_for_timeout(1000)
        lesson_shot(page, 'lesson-almost')
        ta.fill('contention ix all kids have tremendous')
        ta.press('Enter')
        page.wait_for_timeout(1000)
        lesson_shot(page, 'lesson-hint')
        eshot(page.get_by_text(re.compile(r'^Matching')).locator('xpath=..'), 'hint-closeup')
        ta.fill(GAP)
        # A complete answer is accepted as it's typed; Enter would continue
        page.get_by_text('You are correct!').first.wait_for(timeout=8000)
        page.wait_for_timeout(2500)
        lesson_shot(page, 'lesson-correct')
        page.keyboard.press('Enter')  # CONTINUE
        wait_exercise(page)
        page.wait_for_timeout(1500)
        lesson_shot(page, 'lesson-next-clip')
        bar = page.get_by_text(re.compile(r'^Exercise \d+/\d+$')).first
        eshot(bar.locator('xpath=ancestor::*[contains(@class,"MuiToolbar") or contains(@class,"MuiAppBar")][1]'),
              'bottom-bar')
        page.keyboard.press('Escape')  # SKIP
        page.wait_for_timeout(2000)
        lesson_shot(page, 'lesson-skipped')
        # go back to the answered clip with the ◀ button
        for _ in range(2):
            page.locator('.MuiAppBar-positionFixed').last.locator('button').first.click()
            page.wait_for_timeout(1200)
        lesson_shot(page, 'lesson-back')

    if wants('tablet'):
        t = browser.new_context(viewport={'width': 820, 'height': 1180}, device_scale_factor=1,
                                has_touch=True)
        tp = t.new_page()
        library(tp)
        shot(tp, 'tablet-library')
        open_lesson(tp)
        shot(tp, 'tablet-lesson')

    if wants('mobile'):
        m = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True,
                                has_touch=True, device_scale_factor=2)
        mp = m.new_page()
        mp.goto(B + '/', wait_until='load')
        mp.wait_for_timeout(3000)
        shot(mp, 'mobile-home')
        library(mp)
        shot(mp, 'mobile-library')
        open_lesson(mp)
        lesson_shot(mp, 'mobile-lesson-intro')
        mp.get_by_text('START', exact=True).click()
        wait_exercise(mp)
        mp.wait_for_timeout(1000)
        mta = mp.get_by_placeholder('Type what you hear').first
        mta.fill('contention ix all kids')
        mp.get_by_role('button', name='CHECK').click()
        mp.wait_for_timeout(1000)
        lesson_shot(mp, 'mobile-lesson')
        mta.fill(GAP)
        # A complete answer is accepted as it's typed; CHECK goes away
        mp.get_by_text('You are correct!').first.wait_for(timeout=8000)
        mp.wait_for_timeout(2000)
        lesson_shot(mp, 'mobile-lesson-correct')

    browser.close()

if COORDS:
    path = 'src/coords.json'
    old = json.load(open(path)) if os.path.exists(path) else {}
    json.dump({**old, **COORDS}, open(path, 'w'), indent=1)
    print('wrote', path)
