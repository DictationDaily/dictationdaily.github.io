"""Canned /api/me/playlists answers for the `playlist` recording (record.py scene_playlist), on top of
words_demo.py's demo Pro learner (Vietnamese -> French). Public playlist reads (/api/playlists*) go to
the live site: DictationDaily's own playlists are real. Saving, making a playlist and adding a video
are answered here, so nothing is written to any account."""
import json
import re
import time
import urllib.request

UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/130 dd-guide-capture'}


class Playlists:
    def __init__(self, base, language='fr'):
        self.base = base
        self.language = language
        self.mine, self.saved, self.has = [], [], set()
        self.public = {}  # id -> card, from the live site
        self._lengths = None

    def length(self, vid):
        """A video's length in seconds, from the live catalogue (a new playlist's card shows it)."""
        if self._lengths is None:
            req = urllib.request.Request(f'{self.base}/catalog.json', headers=UA)
            data = json.load(urllib.request.urlopen(req))
            items = data if isinstance(data, list) else data.get('videos', [])
            self._lengths = {v.get('id'): v.get('duration') or 0 for v in items}
        return round(self._lengths.get(vid) or 0)

    def card(self, pid):
        if pid not in self.public:
            req = urllib.request.Request(f'{self.base}/api/playlists/{pid}', headers=UA)
            self.public[pid] = json.load(urllib.request.urlopen(req))['playlist']
        return self.public[pid]

    def install(self, page):
        def reply(route, x, status=200):
            route.fulfill(status=status, content_type='application/json', body=json.dumps(x))

        def mine_api(route, req):
            p = re.sub(r'^https?://[^/]+', '', req.url).split('?')[0]
            body = json.loads(req.post_data or '{}') if req.method != 'GET' else {}
            parts = p.split('/')[4:]  # after /api/me/playlists
            if not parts:
                if req.method == 'POST':  # New playlist
                    n = int(time.time())
                    card = {'id': f'demo{n}', 'title': body.get('title', ''), 'language': body.get('language'),
                            'level': body.get('level'), 'levelTo': body.get('levelTo'),
                            'visibility': 'link' if body.get('visibility') == 'public' else body.get('visibility', 'private'),
                            'featured': False, 'by': None, 'videoCount': 1 if body.get('videoId') else 0,
                            'seconds': self.length(body['videoId']) if body.get('videoId') else 0, 'firstVideo': body.get('videoId'), 'saves': 0, 'updatedAt': n, 'done': 0}
                    self.mine.insert(0, card)
                    if body.get('videoId'):
                        self.has.add(card['id'])
                    return reply(route, {'playlist': card, 'publicLater': body.get('visibility') == 'public'})
                return reply(route, {'mine': self.mine, 'saved': self.saved, 'has': sorted(self.has)})
            if parts == ['following']:
                return reply(route, {'following': []})
            pid, action = parts[0], (parts[1] if len(parts) > 1 else None)
            if action == 'save':
                if body.get('saved'):
                    self.saved = [c for c in self.saved if c['id'] != pid] + [{**self.card(pid), 'done': 0}]
                else:
                    self.saved = [c for c in self.saved if c['id'] != pid]
                return reply(route, {'saved': bool(body.get('saved'))})
            if action == 'videos':
                card = next((c for c in self.mine if c['id'] == pid), None)
                if card:
                    (self.has.add if body.get('add') else self.has.discard)(pid)
                    card['videoCount'] += 1 if body.get('add') else -1
                return reply(route, {'playlist': card})
            return reply(route, {})

        page.route(self.base + '/api/me/playlists**', mine_api)
        # the public reads come from the live site (words_demo answers every other /api call)
        page.route(self.base + '/api/playlists**', lambda route: route.continue_())
