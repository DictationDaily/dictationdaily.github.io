"""Sign the capture browser in as a real Pro learner on production, read-only.

    DD_SESSION=/path/to/cookie.txt python3 scripts/capture.py images ...

The file holds the value of a Pro account's `__Secure-authjs.session-token`
cookie (from the browser's dev tools; never commit it). With it:
- every write the app makes is answered locally and never reaches the server
  (progress, activity, Shadowing place, goal, languages, waitlist, word
  reports, the visit log, bug reports, voice/take checks), so the account's
  streak, progress and analytics are untouched;
- every lesson looks unstarted (progress and Shadowing place read as empty),
  so the scripts always begin at sentence 1;
- the account's name, email and picture are replaced by "Demo Learner",
  demo@example.com and a plain "D" avatar in every page.
Reads (translations, word cards) go through as for any Pro learner.
"""
import json
import os
import re
import urllib.request

SESSION_FILE = os.environ.get('DD_SESSION')
COOKIE = '__Secure-authjs.session-token'
WRITES = re.compile(r'/api/me/(progress|activity|shadow|goal|languages|pro-waitlist|word/report|visit|'
                    r'bug-report|shadow-check|word-check|voice-answer|account)(/|\?|$)')
FRESH = {'progress': '{"progress":null,"date":null}', 'shadow': '{"seconds":null}'}


def active():
    return bool(SESSION_FILE)


def _token():
    return open(SESSION_FILE).read().strip()


def _who(base):
    req = urllib.request.Request(f'{base}/api/auth/session',
                                 headers={'Cookie': f'{COOKIE}={_token()}',
                                          'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/130 dd-guide-capture'})
    user = json.load(urllib.request.urlopen(req)).get('user') or {}
    assert user.get('email'), 'the session cookie is not signed in'
    return user


def _route(route):
    req = route.request
    m = WRITES.search(req.url)
    if m and req.method != 'GET':
        return route.fulfill(status=200, content_type='application/json', body='{}')
    if req.method == 'GET':
        for name, body in FRESH.items():
            if re.search(rf'/api/me/{name}\?', req.url):
                return route.fulfill(status=200, content_type='application/json', body=body)
    return route.continue_()


def apply(ctx, base):
    """Sign ctx in (no-op without DD_SESSION)."""
    if not active():
        return
    user = _who(base)
    host = re.sub(r'^https?://|[:/].*$', '', base)
    ctx.add_cookies([{'name': COOKIE, 'value': _token(), 'domain': host, 'path': '/',
                      'secure': True, 'httpOnly': True, 'sameSite': 'Lax'}])
    ctx.route('**/api/me/**', _route)
    swaps = [[user.get('email', ''), 'demo@example.com'], [user.get('name', ''), 'Demo Learner']]
    ctx.add_init_script("""
(() => {
  const swaps = %s.filter(([a]) => a);
  // a plain "D" (Demo Learner) avatar in place of the account's picture
  const pic = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect width="40" height="40" fill="#5C6BC0"/><text x="20" y="27" font-family="Arial,sans-serif" font-size="20" font-weight="700" fill="#fff" text-anchor="middle">D</text></svg>');
  const css = `img[src*="googleusercontent"],img[src*="gravatar"]{content:url("${pic}")!important}`;
  const fix = (root) => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode())
      for (const [a, b] of swaps) if (n.nodeValue.includes(a)) n.nodeValue = n.nodeValue.split(a).join(b);
    root.querySelectorAll && root.querySelectorAll('[alt],[title],[aria-label]').forEach((el) => {
      for (const at of ['alt', 'title', 'aria-label']) {
        const v = el.getAttribute(at);
        if (v) for (const [a, b] of swaps) if (v.includes(a)) el.setAttribute(at, v.split(a).join(b));
      }
    });
  };
  const start = () => {
    const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s);
    fix(document.body);
    new MutationObserver((ms) => ms.forEach((m) => {
      m.addedNodes.forEach((n) => fix(n.nodeType === 3 ? n.parentNode || document.body : n));
      if (m.type === 'characterData') fix(m.target.parentNode || document.body);
    })).observe(document.body, {childList: true, subtree: true, characterData: true});
  };
  if (document.body) start(); else addEventListener('DOMContentLoaded', start);
})();
""" % json.dumps(swaps))
