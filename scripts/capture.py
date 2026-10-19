"""Extra signed-out screenshots of production dictationdaily.com for the guide site.
Read-only: never signs in, so nothing is saved.
usage: python3 scripts/capture.py images [--only name ...]
PNGs are written; convert them with scripts/to_webp.py before committing."""
import re
import sys
import time

from playwright.sync_api import sync_playwright

B = 'https://dictationdaily.com'
OUT = sys.argv[1]
ONLY = sys.argv[3:] if len(sys.argv) > 2 and sys.argv[2] == '--only' else None
VIDEO = 'g4IAa8wZlqU'  # Sir Ken Robinson, 2:15
CLIP1 = 'My contention is all kids have tremendous talents,'


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


with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True,
                                args=['--autoplay-policy=no-user-gesture-required'])
    ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
    page = ctx.new_page()

    # Home
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
    page.get_by_role('tab', name=re.compile('^intermediate$', re.I)).click()
    page.wait_for_timeout(1500)
    shot(page, 'home-full', full_page=True)

    # Library: sorts, levels, durations, card close-up
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

    # Lesson flow
    open_lesson(page)
    shot(page, 'lesson-intro')
    page.get_by_text('START', exact=True).click()
    page.wait_for_timeout(2000)
    if page.get_by_role('heading', name='Just listen').count():
        shot(page, 'lesson-listen')
    wait_exercise(page)
    page.wait_for_timeout(1200)
    shot(page, 'lesson-clip-playing')
    ta = page.get_by_placeholder('Type what you hear').first
    ta.fill('my contention is all kids')
    shot(page, 'lesson-typing')
    ta.press('Enter')
    page.wait_for_timeout(1000)
    shot(page, 'lesson-hint-missing')
    ta.fill('My contention ix all kids have tremendous')
    ta.press('Enter')
    page.wait_for_timeout(1000)
    shot(page, 'lesson-hint')
    eshot(page.get_by_text(re.compile(r'^Matching')).locator('xpath=..'), 'hint-closeup')
    ta.fill(CLIP1)
    ta.press('Enter')
    page.wait_for_timeout(2500)
    shot(page, 'lesson-correct')
    page.keyboard.press('Enter')  # CONTINUE
    wait_exercise(page)
    page.wait_for_timeout(1500)
    shot(page, 'lesson-next-clip')
    bar = page.get_by_text(re.compile(r'^Exercise \d+/\d+$')).first
    eshot(bar.locator('xpath=ancestor::*[contains(@class,"MuiToolbar") or contains(@class,"MuiAppBar")][1]'),
          'bottom-bar')
    page.keyboard.press('Escape')  # SKIP
    page.wait_for_timeout(2000)
    shot(page, 'lesson-skipped')
    # go back to the answered clip with the ◀ button
    for _ in range(2):
        page.locator('footer button, .MuiAppBar-positionFixed button').first.click()
        page.wait_for_timeout(1200)
    shot(page, 'lesson-back')

    # Tablet
    t = browser.new_context(viewport={'width': 820, 'height': 1180}, device_scale_factor=1,
                            has_touch=True)
    tp = t.new_page()
    library(tp)
    shot(tp, 'tablet-library')
    open_lesson(tp)
    shot(tp, 'tablet-lesson')

    # Phone
    m = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True,
                            has_touch=True, device_scale_factor=2)
    mp = m.new_page()
    mp.goto(B + '/', wait_until='load')
    mp.wait_for_timeout(3000)
    shot(mp, 'mobile-home')
    library(mp)
    shot(mp, 'mobile-library')
    open_lesson(mp)
    shot(mp, 'mobile-lesson-intro')
    mp.get_by_text('START', exact=True).click()
    wait_exercise(mp)
    mp.wait_for_timeout(1000)
    mta = mp.get_by_placeholder('Type what you hear').first
    mta.fill('My contention ix all kids')
    mp.get_by_role('button', name='CHECK').click()
    mp.wait_for_timeout(1000)
    shot(mp, 'mobile-lesson')
    mta.fill(CLIP1)
    mp.get_by_role('button', name='CHECK').click()
    mp.wait_for_timeout(2000)
    shot(mp, 'mobile-lesson-correct')

    browser.close()
