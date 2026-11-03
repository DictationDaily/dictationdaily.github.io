"""Signed-in Pro shots for say-your-answer.html (dictation-mic, dictation-mic-correct),
from a local build of the app with the Demo Learner set to Pro (see README › Screenshots):

    python3 scripts/capture_pro.py http://localhost:8788 images /tmp/cookie.txt
    python3 scripts/to_webp.py

The cookie file holds `node tests/e2e/mint_session.mjs authjs.session-token` from the app repo.
"""
import json, sys, urllib.request
from playwright.sync_api import sync_playwright
B = sys.argv[1].rstrip('/'); OUT = sys.argv[2]; VIDEO = '0G2U0R0hOCU'
cookie = open(sys.argv[3]).read().strip()
tr = json.load(urllib.request.urlopen(f'{B}/transcripts/{VIDEO}.json'))
clips = [s['text'].strip() for s in tr['segments'] if not s.get('ignore') and s.get('start') is not None]
with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True, args=['--autoplay-policy=no-user-gesture-required'])
    ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
    ctx.add_cookies([{'name': 'authjs.session-token', 'value': cookie, 'domain': 'localhost', 'path': '/'}])
    page = ctx.new_page()
    page.goto(f'{B}/videos/{VIDEO}', wait_until='networkidle')
    page.wait_for_timeout(1500)
    page.keyboard.press('Enter')  # START
    ta = page.get_by_placeholder('what you hear').first
    ta.wait_for(timeout=15000)
    page.wait_for_timeout(2500)
    print('placeholder:', ta.get_attribute('placeholder'))
    page.screenshot(path=f'{OUT}/dictation-mic.png')
    import re
    n = int(re.search(r'Exercise (\d+)/', page.get_by_text(re.compile(r'Exercise \d+/')).first.inner_text()).group(1))
    print('exercise', n)
    ta.fill(clips[n - 1])
    page.get_by_text('You are correct!').first.wait_for(timeout=8000)
    page.wait_for_timeout(1200)
    page.screenshot(path=f'{OUT}/dictation-mic-correct.png')
    page.locator('[data-testid="lesson-settings"]').first.click()
    page.wait_for_timeout(800)
    page.screenshot(path=f'{OUT}/lesson-gear-menu.png')
    print('done', clips[n - 1])
    browser.close()
