"""The rest of the Demo Learner's canned /api answers (words_demo.py answers the words, the
dictionary and today's streak): the practice card's inputs, My progress and Your skills, History,
Liked, a lesson's likes and comments, Add a video and its minutes.

Nothing here reaches the server: every answer is made up in the browser, around real videos of the
live catalogue (titles, levels, lengths), so the pages look as a learner of French with a few weeks
of practice sees them. Shapes follow the app's worker (dictationdaily.com, worker/api.ts,
worker/video-social.ts, worker/added-videos.ts), read on 2026-11-26."""
import json
import re
import time
import urllib.request

UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/130 dd-guide-capture'}
DAY = 86400

# Easy French videos the demo learner has practised (id, parts of 10 sentences done, or 'done'), newest first
HISTORY = [('16-01J9ybPE', 2), ('aMx0d42wzBs', 'done'), ('MBK7K1Xw3Lc', 1), ('-4p0fngSbUs', 'done'),
           ('tcF32PewZqY', 3), ('2lMIShoMuIk', 'done'), ('unmu4yKfBg0', 1)]
PART = 10  # sentences in a part (the app's first part size)
LIKED = ['aMx0d42wzBs', 'MBK7K1Xw3Lc', '-4p0fngSbUs', '2lMIShoMuIk', 'xr1V8HDt8GQ', 'EAX8mc_ovDk']
LATER = ['JFqUtnm161I', '3jdRN1LZvSg']

COMMENTS = [
    {'name': 'Linh', 'streak': 34, 'body': 'Je ne savais pas que « branché » voulait dire à la mode 😄',
     'quote': None, 'likes': 12, 'replies': 1, 'ago': 2 * DAY},
    {'name': 'Marco', 'streak': 9, 'body': 'She speaks so fast here! I needed REPLAY five times.',
     'quote': {'text': "Bonjour et bienvenue dans un nouvel épisode d'Easy French,", 'seconds': 0.4},
     'likes': 7, 'replies': 0, 'ago': 5 * DAY},
    {'name': 'Hana', 'streak': 61, 'body': 'Tip: turn on Show the whole answer for this one, the long lines are easier.',
     'quote': None, 'likes': 4, 'replies': 0, 'ago': 9 * 3600},
]


class Learner:
    def __init__(self, base, now):
        self.base, self.now = base, now
        get = lambda path: json.load(urllib.request.urlopen(urllib.request.Request(base + path, headers=UA)))
        cat = get('/catalog.json')
        self.channels = cat['channels']
        self.videos = {v['id']: v for v in cat['videos']}
        self.tz = time.localtime().tm_gmtoff
        self.today = (now + self.tz) // DAY
        self.get = get
        self.places = {}
        self.rating = {}  # video -> 1 / -1 (this recording's 👍 / 👎)
        self.comments = {}  # video -> comments added in this recording

    # ---- pieces
    def item(self, vid, **more):
        """A VideoItem (queries.ts) of the live catalogue."""
        v = self.videos[vid]
        ch = self.channels.get(v.get('channel_id'), {})
        out = {'id': vid, 'title': v['title'], 'language': v.get('language', 'en'), 'description': '',
               'duration': v['duration'], 'view_count': v.get('view_count', 0),
               'thumbnail': f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg', 'timestamp': v.get('timestamp', 0),
               'channel_id': v.get('channel_id'),
               'channel': {'id': v.get('channel_id'), 'title': ch.get('title', ''), 'description': '',
                           'channel_follower_count': 0, 'avatar_url': '', 'banner_url': ''},
               'words_per_minute': v.get('words_per_minute'), 'progress': None}
        if v.get('cefr_level'):
            out['cefr_level'] = v['cefr_level']
        out.update(more)
        return out

    def place(self, vid, p):
        """Seconds into the video: its end, or the end of the last sentence of the parts done."""
        if p == 'done':
            return self.videos[vid]['duration'] - 2
        if vid not in self.places:
            segs = [x for x in self.get(f'/transcripts/{vid}.json')['segments'] if not x.get('ignore')]
            self.places[vid] = segs[min(len(segs), p * PART) - 1]['end']
        return self.places[vid]

    def history(self):
        return [self.item(vid, progress=self.place(vid, p), practised_at=self.now - 3600 - n * DAY * 2)
                for n, (vid, p) in enumerate(HISTORY)]

    def next_data(self, learning):
        """GET /api/me/next: the recommender's inputs (the browser picks the video)."""
        rows, t = [], self.now - 3600
        for vid, p in HISTORY:
            if p == 'done' or self.videos[vid].get('language') != learning:
                continue
            for seg in range(12):
                rows.append([vid, t, 30, None, seg, 'right' if seg % 4 else 'skip', 1 if seg % 3 else 2])
                t -= 40
            t -= DAY
        # Only the finished videos: a video left in the middle of a part makes the card read
        # "Part 2 of 8 · 2 sentences · about 1 min"; the guide shows a whole part to come
        videos = [[vid, self.place(vid, p), None, self.now - 3600 - n * DAY * 2, PART]
                  for n, (vid, p) in enumerate(HISTORY) if p == 'done']
        return {'tzOffset': self.tz, 'learning': learning, 'rows': rows, 'videos': videos, 'events': [],
                'starters': [], 'ratings': [[v, 1, None, self.now - 5 * DAY] for v in LIKED],
                'later': LATER}

    def summary(self):
        """GET /api/me/summary: My progress (streak, goal, 6 months of days, levels)."""
        days = {}
        for k in range(190):
            d = self.today - k
            if k < 19 or (k % 7 not in (3, 5) and k < 150):
                days[str(d)] = 240 + (k * 137) % 900 if k else 420
        return {'currentStreak': {'count': 19, 'startDate': (self.now - 18 * DAY) * 1000, 'endDate': self.now * 1000},
                'longestStreak': {'count': 26, 'startDate': (self.now - 120 * DAY) * 1000,
                                  'endDate': (self.now - 95 * DAY) * 1000},
                'goal': 10, 'today': self.today, 'days': days,
                'levels': {'A1': 15400, 'A2': 9800, 'B1': 21500, 'B2': 3200},
                'finished': 14, 'inProgress': 5, 'yearSeconds': 186000, 'yearActiveDays': 112}

    def skills(self, days, language):
        w = lambda k, s, n: {'at': self.now - 35 * DAY + k * 7 * DAY, 'score': s, 'n': n}
        return {'days': days, 'from': self.now - days * DAY, 'language': language,
                'speaking': {'lines': 86, 'score': 78, 'before': 71, 'wordLines': 80, 'pronunciation': 82,
                             'completeness': 91, 'checks': 24, 'words': 74,
                             'weeks': [w(0, 66, 12), w(1, 71, 18), w(2, 74, 20), w(3, 77, 25), w(4, 81, 31)],
                             'sounds': [{'ipa': 'ʁ', 'score': 58, 'words': ['rue', 'très'], 'example': 'rouge'},
                                        {'ipa': 'y', 'score': 63, 'words': ['tu', 'vu'], 'example': None},
                                        {'ipa': 'ɑ̃', 'score': 74, 'words': ['enfant', 'temps'], 'example': None}],
                             'again': [{'word': 'grenouille', 'score': 41}, {'word': 'heureux', 'score': 0},
                                       {'word': 'quartiers', 'score': 52}, {'word': 'branchés', 'score': 66}]},
                'listening': {'sentences': 240, 'first': 168, 'before': {'n': 190, 'first': 120},
                              'speeds': {'slow': {'n': 60, 'first': 50}, 'natural': {'n': 150, 'first': 104},
                                         'fast': {'n': 30, 'first': 14}},
                              'parts': 19, 'videos': 9}}

    def social(self, vid):
        r = self.rating.get(vid, 0)
        return {'likes': 23 + (r == 1), 'dislikes': 2 + (r == -1), 'comments': len(COMMENTS) + len(self.comments.get(vid, [])),
                'rating': r, 'reason': None, 'saved': False, 'signedIn': True}

    def comment_list(self, vid, sort):
        rows = [{'id': f'demoCmt{n:05d}', 'parentId': None, 'name': c['name'], 'photo': None, 'streak': c['streak'],
                 'body': c['body'], 'quote': c['quote'], 'likes': c['likes'], 'replies': c['replies'],
                 'at': self.now - c['ago'], 'mine': False, 'liked': False} for n, c in enumerate(COMMENTS)]
        rows = self.comments.get(vid, []) + rows
        if sort == 'new':
            rows.sort(key=lambda c: -c['at'])
        else:
            rows.sort(key=lambda c: (-c['likes'], -c['replies'], -c['at']))
        return rows

    def added(self):
        return {'quota': {'limits': {'day': 30, 'week': 120}, 'usedToday': 540, 'usedWeek': 2280, 'left': 1260,
                          'dayResets': (self.today + 1) * DAY - self.tz, 'weekResets': self.now + 4 * DAY},
                'items': [{'id': 'aMx0d42wzBs', 'title': self.videos['aMx0d42wzBs']['title'], 'channel': 'Easy French',
                           'language': 'fr', 'seconds': 0, 'state': 'ready', 'place': None, 'reason': None,
                           'createdAt': self.now - 6 * DAY, 'existing': True}],
                'pro': True}

    # ---- the routes
    def answer(self, p, q, m, body, reply, route, learning):
        """Answer /api path p, or return False to let words_demo answer it."""
        lesson = re.match(r'^/api/(?:me/)?lessons/([\w-]+)/(.+)$', p)
        if p == '/api/me/next':
            return reply(self.next_data(learning))
        if p == '/api/me/progress' and 'all' in q:
            return reply({vid: self.place(vid, pl) for vid, pl in HISTORY})
        if p == '/api/me/progress' and m == 'GET':
            return reply({'progress': None, 'date': None, 'partSize': None})
        if p == '/api/me/shadow' and m == 'GET':
            return reply({'seconds': None, 'partSize': None})
        if p == '/api/me/mode' and m == 'GET':
            return reply({'video': None, 'last': 'dictation', 'chosen': None})
        if p in ('/api/me/mode', '/api/me/progress', '/api/me/shadow', '/api/me/goal', '/api/me/languages'):
            return reply({'ok': True})
        if p == '/api/me/activity':
            return reply({'ok': True, 'todaySeconds': 480, 'freeSecondsLeft': None, 'freeMinutes': 10})
        if p in ('/api/me/visit', '/api/me/word-open', '/api/me/recommend-event'):
            return route.fulfill(status=204, body='')
        if p == '/api/me/summary':
            return reply(self.summary())
        if p == '/api/me/skills':
            days = 7 if re.search(r'(^|&)days=7(&|$)', q) else 30
            lang = (re.search(r'language=(\w+)', q) or [None, learning])[1]
            return reply(self.skills(days, lang))
        if p == '/api/me/videos':
            items = [x for x in self.history() if x['language'] == learning]
            return reply({'language': learning, 'videos': items} if 'language=mine' in q else items)
        if p == '/api/me/liked':
            return reply([self.item(v, liked_at=self.now - n * DAY, progress=None) for n, v in enumerate(LIKED)])
        if p == '/api/me/keep-takes':
            return reply({'on': True})
        if p == '/api/me/added-videos' and m == 'GET':
            return reply(self.added())
        if lesson:
            vid, what = lesson.groups()
            if what == 'social':
                return reply(self.social(vid))
            if what == 'comments' and m == 'GET':
                return reply({'comments': [] if 'parent=' in q else self.comment_list(vid, 'new' if 'sort=new' in q else 'top')})
            if what == 'comments':
                b = body()
                c = {'id': f'demoNew{int(time.time()) % 100000:05d}', 'parentId': b.get('parentId'), 'name': 'Demo',
                     'photo': None, 'streak': 19, 'body': b.get('body', ''), 'quote': b.get('quote'), 'likes': 0,
                     'replies': 0, 'at': int(time.time()), 'mine': True, 'liked': False}
                self.comments.setdefault(vid, []).insert(0, c)
                return reply({'comment': c})
            if what == 'rate':
                self.rating[vid] = body().get('rating', 0)
                s = self.social(vid)
                return reply({'rating': s['rating'], 'likes': s['likes'], 'dislikes': s['dislikes']})
            if what == 'reason':
                return reply({'reason': body().get('reason')})
            m2 = re.match(r'comments/(\w+)/like$', what)
            if m2:
                return reply({'liked': bool(body().get('liked')), 'likes': 13})
            return reply({'ok': True})
        return False
