"""The screenshots the guide's pages show (images/*.webp), from the live site as the Demo Learner.

    python3 scripts/shots.py [name ...]      # all, or some
    python3 scripts/to_webp.py               # then: PNG -> WebP, and the hint close-ups (crop-*)

The Demo Learner (words_demo.py + learner_demo.py) is a Pro learner of French whose every /api
answer is made up in the browser: nothing is read from or written to any account. Lessons, the
lesson text and the videos are the live ones.

Shots: lesson-hint, lesson-hint-missing, lesson-hint-extra, lesson-almost (the hints page's
close-ups, and the site's preview picture), my-videos (History), youtube-speed-menu (the video's
own speed menu), lesson-finished-streak and lesson-finished-return (the finish screens),
lesson-no-transcript and not-found (Something's not working)."""
import json
import os
import re
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

import words_demo

B = os.environ.get('DD_BASE', 'https://dictationdaily.com').rstrip('/')
OUT = 'images'
VIDEO = 'g4IAa8wZlqU'  # Sir Ken Robinson, 2:15: "My … talents," opens it
WANT = sys.argv[1:]


def wants(name):
    return not WANT or name in WANT


def shot(page, name, **kw):
    page.screenshot(path=f'{OUT}/{name}.png', **kw)
    print('wrote', name, flush=True)


def segments(video):
    req = urllib.request.Request(f'{B}/transcripts/{video}.json', headers={'User-Agent': 'Mozilla/5.0 dd-guide-capture'})
    return json.load(urllib.request.urlopen(req))['segments']


def at(page, video, seconds, days_ago=1):
    """The demo learner's saved place in this video."""
    page.route(f'**/api/me/progress?id={video}*', lambda r: r.fulfill(
        status=200, content_type='application/json',
        body=json.dumps({'progress': seconds, 'date': int(time.time()) - days_ago * 86400, 'partSize': None})))


def open_lesson(page, video=VIDEO):
    page.goto(f'{B}/videos/{video}', wait_until='load')
    page.wait_for_selector('iframe[src*="youtube"]', timeout=20000)


def bizzy(page, mode='Listening'):
    return page.get_by_role('button', name=re.compile(rf'\b{mode}\b')).first


def textbox(page):
    return page.get_by_placeholder(re.compile('what you hear')).first


with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True,
                                args=['--autoplay-policy=no-user-gesture-required'])
    demo = words_demo.Demo(B)

    def new_page():
        ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
        demo.reset()
        demo.install(ctx)
        return ctx.new_page()

    if any(wants(n) for n in ('lesson-hint', 'lesson-hint-missing', 'lesson-hint-extra', 'lesson-almost')):
        page = new_page()
        open_lesson(page)
        bizzy(page).click()
        page.mouse.move(400, 32)  # off the buttons: no tooltip in the shots
        ta = textbox(page)
        ta.wait_for(timeout=30000)
        page.wait_for_timeout(5000)  # the sentence has played
        for name, text in (('lesson-hint-missing', 'contention is all kids tremendous'),
                           ('lesson-hint-extra', 'contention is all the kids have tremendous'),
                           ('lesson-almost', 'contention is all kids have tremendus'),
                           ('lesson-hint', 'contention ix all kids have tremendous')):
            ta.fill(text)
            ta.press('Enter')
            page.wait_for_timeout(1000)
            if wants(name):
                shot(page, name)

    if wants('youtube-speed-menu'):
        page = new_page()
        open_lesson(page)
        bizzy(page).click()
        textbox(page).wait_for(timeout=30000)
        page.wait_for_timeout(1500)
        frame = page.frame_locator('iframe[src*="youtube"]')
        page.locator('iframe[src*="youtube"]').hover()
        frame.get_by_role('button', name='Playback Settings').click()
        page.wait_for_timeout(700)
        frame.get_by_text('Speed', exact=True).click()
        page.wait_for_timeout(900)
        box = page.locator('iframe[src*="youtube"]').bounding_box()
        shot(page, 'youtube-speed-menu', clip=box)

    if wants('my-videos'):
        page = new_page()
        page.goto(f'{B}/my-videos', wait_until='load')
        page.get_by_text(re.compile('^Up next$', re.I)).first.wait_for(timeout=30000)
        page.wait_for_selector('img[src*="ytimg.com"]', timeout=20000)
        page.wait_for_timeout(3000)
        shot(page, 'my-videos')

    if wants('lesson-finished-streak'):
        # the last sentence left: answer it, Last part done!, FINISH
        # The last 6 sentences, about a minute on each (as a learner who listens a few times),
        # so the finish screen shows the minutes of a real pass
        page = new_page()
        exercises = [s for s in segments(VIDEO) if not s.get('ignore')]
        at(page, VIDEO, exercises[-7]['end'])
        open_lesson(page)
        bizzy(page).click()
        page.mouse.move(400, 32)
        for seg in exercises[-6:]:
            if page.get_by_role('heading', name='Just listen').count():
                page.keyboard.press('Space')
            ta = textbox(page)
            ta.wait_for(timeout=30000)
            page.wait_for_timeout(62_000)
            ta.fill(seg['text'])
            page.locator('button').filter(has_text=re.compile('^continue$', re.I)).wait_for(timeout=8000)
            page.wait_for_timeout(400)
            page.keyboard.press('Space')
            page.wait_for_timeout(1000)
        finish = page.get_by_role('button', name=re.compile('^finish$', re.I)).first
        finish.wait_for(timeout=20000)
        if wants('lesson-last-part'):
            page.wait_for_timeout(1500)
            shot(page, 'lesson-last-part')
        page.wait_for_timeout(1200)
        finish.click()
        page.get_by_text(re.compile('day streak', re.I)).first.wait_for(timeout=20000)
        page.mouse.move(400, 32)
        page.wait_for_timeout(4000)  # the flame rolls up, the confetti settles
        shot(page, 'lesson-finished-streak')

    if wants('lesson-finished-return'):
        page = new_page()
        at(page, VIDEO, 135, days_ago=2)
        open_lesson(page)
        bizzy(page).click()  # Bizzy asks first, even on a finished video
        page.get_by_text(re.compile('done this one', re.I)).first.wait_for(timeout=30000)
        page.mouse.move(400, 32)
        page.wait_for_timeout(2500)
        shot(page, 'lesson-finished-return')

    if wants('lesson-no-transcript'):
        # A lesson whose text has nothing to type: its transcript with every line marked "just listen"
        page = new_page()
        tr = json.load(urllib.request.urlopen(urllib.request.Request(
            f'{B}/transcripts/{VIDEO}.json', headers={'User-Agent': 'Mozilla/5.0 dd-guide-capture'})))
        for seg in tr['segments']:
            seg['ignore'], seg['reason'] = True, 'music'
        page.route(f'**/transcripts/{VIDEO}.json*', lambda r: r.fulfill(
            status=200, content_type='application/json', body=json.dumps(tr)))
        open_lesson(page)
        page.wait_for_timeout(3000)
        if bizzy(page).count():
            bizzy(page).click()
        page.get_by_text(re.compile('not available yet')).first.wait_for(timeout=30000)
        page.mouse.move(400, 32)
        page.wait_for_timeout(2000)
        shot(page, 'lesson-no-transcript')

    if wants('not-found'):
        page = new_page()
        page.goto(f'{B}/this-page-is-not-here', wait_until='load')
        page.wait_for_timeout(3000)
        shot(page, 'not-found')

    browser.close()
