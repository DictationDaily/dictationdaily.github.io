"""Canned /api answers for the `words` recording (record.py scene_words): a demo Pro learner
(Vietnamese -> French) who saves "épisode" in Easy French 97 and practises two flashcards.

Every /api call of the page is answered here, so the scene needs no account and writes nothing
(no DD_SESSION). The lesson text, its Vietnamese translation and the native recording are the
real public files; the dictionary card and the saved-words list are made up for the demo."""
import json
import re
import time
import urllib.request

VIDEO = 'YCuU4SjcS2A'  # Easy French 97, the guide's French lesson
TITLE = 'Why Do You Live in Paris? | Easy French 97'
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/130 dd-guide-capture'}

# word, segment, kind, level, due label, meaning in Vietnamese, simple French definition
WORDS = [
    ('épisode', 0, 'new', 0, 'New', 'tập, hồi', "Partie d'une série ou d'une histoire."),
    ('quartiers', 2, 'learning', 1, 'Now', 'khu phố', "Parties d'une ville."),
    ('branchés', 2, 'learning', 2, 'In 8 min', 'sành điệu, hợp thời', 'À la mode, modernes.'),
    ('emménager', 3, 'learning', 2, 'Tomorrow', 'chuyển đến ở', "S'installer dans un nouveau logement."),
    ('habiter', 13, 'learning', 3, 'In 3 days', 'sống, ở', 'Vivre dans un lieu.'),
    ('vécu', 17, 'known', 4, 'In 2 weeks', 'đã sống', 'Participe passé de « vivre ».'),
    ('énormément', 18, 'known', 4, 'In 3 weeks', 'rất nhiều', 'Beaucoup, en très grande quantité.'),
]
# More saved words for the Words page's chart and list (the practice cards stay the two above):
# word, segment, Vietnamese meaning, simple French definition
MORE = [
    ('bienvenue', 0, 'chào mừng', "Mot pour accueillir quelqu'un."),
    ('arrondissement', 1, 'quận', "Partie d'une grande ville."),
    ('demander', 3, 'hỏi', 'Poser une question.'),
    ('décidé', 3, 'đã quyết định', 'Participe passé de « décider ».'),
    ('aimeriez', 13, 'muốn, thích', 'Forme de « aimer ».'),
    ('études', 17, 'việc học', "Le temps où l'on étudie."),
    ('vraiment', 18, 'thật sự', "Pour dire que c'est vrai."),
    ('culturelle', 18, 'văn hóa', 'Qui concerne la culture.'),
    ('tellement', 19, 'rất, quá', 'Très, beaucoup.'),
    ('choses', 19, 'những điều', 'Objets ou faits.'),
    ('rigolo', 28, 'vui, buồn cười', 'Amusant, drôle.'),
    ('ville', 34, 'thành phố', 'Grande agglomération.'),
    ('particulièrement', 36, 'đặc biệt', "Surtout, plus que d'habitude."),
    ('belle', 36, 'đẹp', 'Jolie, agréable à voir.'),
    ('saisons', 37, 'mùa', 'Printemps, été, automne, hiver.'),
    ('toujours', 39, 'luôn luôn', 'Tout le temps.'),
    ('lumière', 39, 'ánh sáng', 'Ce qui éclaire.'),
    ('exceptionnelle', 39, 'đặc biệt, xuất sắc', 'Très rare, remarquable.'),
    ('complètement', 41, 'hoàn toàn', 'Tout à fait.'),
    ('différents', 41, 'khác nhau', 'Pas pareils.'),
    ('voyage', 42, 'đi du lịch', "Fait d'aller loin."),
    ('endroit', 42, 'nơi, chỗ', 'Un lieu.'),
    ('heure', 38, 'giờ', 'Soixante minutes.'),
]
# kind, level, when it comes back, of each MORE word (in order)
MORE_KIND = ['known', 'learning', 'known', 'learning', 'new', 'known', 'learning', 'known', 'learning',
             'known', 'new', 'learning', 'known', 'learning', 'learning', 'known', 'learning', 'new',
             'known', 'learning', 'learning', 'known', 'learning']
DUE = {'new': (0, 'New'), 'learning': (2, 'In 3 days'), 'known': (5, 'In 1 month')}
PRACTICE = ('épisode', 'quartiers')  # the practice page orders cards itself: only these two

SENSE = {'word': 'épisode', 'src': 'fr', 'lemma': 'épisode', 'pos': 'noun', 'gender': 'masculine',
         'ipa': '/e.pi.zɔd/', 'form': '', 'gloss': 'tập, hồi', 'def': "Partie d'une série ou d'une histoire."}
ENTRY_URL = '/dictionary/v4/fr/vi/épisode~noun.json'
ENTRY = {'headword': 'épisode', 'pos': 'noun', 'gender': 'masculine', 'ipa': [{'accent': '', 'ipa': '/e.pi.zɔd/'}],
         'forms': 'épisode, épisodes',
         'senses': [
             {'def': "partie d'une série ou d'une histoire", 'native': 'tập (phim, truyện)',
              'examples': [{'text': 'Le nouvel épisode sort demain.', 'native': 'Tập mới ra mắt vào ngày mai.'},
                           {'text': "J'ai regardé trois épisodes hier soir.",
                            'native': 'Tối qua tôi đã xem ba tập.'}]},
             {'def': "moment d'une vie ou d'une histoire", 'native': 'giai đoạn, đoạn',
              'examples': [{'text': "C'est un épisode de ma jeunesse.", 'native': 'Đó là một giai đoạn thời trẻ của tôi.'}]}]}


class Demo:
    def __init__(self, base):
        self.base = base
        self.now = int(time.time())
        get = lambda path: json.load(urllib.request.urlopen(urllib.request.Request(base + path, headers=UA)))
        tr = get(f'/transcripts/{VIDEO}.json')
        self.lines = [' '.join(w['text'] if isinstance(w, dict) else w for w in s['words']) for s in tr['segments']]
        self.starts = [s['start'] for s in tr['segments']]
        self.trans = {l['i']: l['t'] for l in get(f'/translations/{VIDEO}/vi.json?v=3')['lines']}

    def sentence(self, sid, seg, word):
        text = self.lines[seg]
        m = re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text)
        return {'id': sid, 'videoId': VIDEO, 'seg': seg, 'start': round(self.starts[seg], 2),
                'before': text[:m.start()], 'gap': word, 'after': text[m.end():], 'trans': self.trans.get(seg),
                'transLang': 'vi', 'title': TITLE}

    def saved(self):
        rows = list(WORDS) + [(w, seg, kind, DUE[kind][0], DUE[kind][1], g, d)
                              for (w, seg, g, d), kind in zip(MORE, MORE_KIND)]
        words, reviews = [], []
        for n, (w, seg, kind, level, label, g, d) in enumerate(rows):
            # saved over the last month: new words lately, known ones longest ago; the
            # history the chart draws (when it was saved, its reviews and what they left)
            days = {'new': n % 3, 'learning': 2 + (n * 7) % 19, 'known': 12 + (n * 5) % 18}[kind]
            created = self.now - days * 86400 - (n * 2917) % 30000 - 60
            first = None if kind == 'new' else created + 3600
            if first:
                reviews.append([100 + n, first, 1])
            if kind == 'known':
                reviews.append([100 + n, min(self.now - 600, first + (8 + n % 5) * 86400), 2])
            words.append({'id': 100 + n, 'word': w, 'kind': kind, 'level': level, 'due': self.now + n * 3600,
                          'dueLabel': label, 'created': created, 'firstReview': first,
                          'sentence': self.sentence(200 + n, seg, w), 'meaning': {'gloss': g, 'def': d}})
        words.sort(key=lambda x: -x['created'])
        counts = {k: sum(1 for x in words if x['kind'] == k) for k in ('new', 'learning', 'known')}
        return {'lang': 'fr', 'words': words, 'reviews': sorted(reviews, key=lambda r: r[1]), 'counts': counts,
                'due': 2, 'newLeft': 9, 'now': self.now, 'next': 'In 8 min'}

    def practice(self):
        return {'lang': 'fr', 'cards': [
            {'id': 100 + n, 'word': w, 'isNew': kind == 'new', 'sentence': self.sentence(200 + n, seg, w),
             'meaning': {'gloss': g, 'def': d}}
            for n, (w, seg, kind, level, label, g, d) in enumerate(WORDS) if w in PRACTICE]}

    def install(self, page):
        """Answer every /api call of this page (and the made-up dictionary entry)."""
        today = {'streak': {'count': 19, 'startDate': (self.now - 18 * 86400) * 1000, 'endDate': self.now * 1000},
                 'goal': None, 'plan': {'plan': 'pro', 'proUntil': None, 'waitlisted': False},
                 'langs': {'native': 'vi', 'learning': 'fr', 'translations': 'after'},
                 'week': [600, 540, 720, 480, 660, 600, 420]}
        session = {'user': {'name': 'Demo Learner', 'email': 'demo@example.com'},
                   'expires': '2030-01-01T00:00:00.000Z'}

        def api(route, req):
            path = re.sub(r'^https?://[^/]+', '', req.url)
            p, m = path.split('?')[0], req.method
            body = lambda: json.loads(req.post_data or '{}')
            reply = lambda x: route.fulfill(status=200, content_type='application/json', body=json.dumps(x))
            if p == '/api/auth/session':
                return reply(session)
            if p.startswith('/api/auth/'):
                return route.continue_()
            if p == '/api/me/today':
                return reply(today)
            if p == '/api/me/progress' and m == 'GET':
                return reply({'progress': None, 'date': None})
            if p == '/api/me/translation':
                return reply({'state': 'ready'})
            if p == '/api/me/word':
                if (body().get('word') or '').lower() == 'épisode':
                    return reply({'state': 'ready', 'native': 'vi', 'sense': SENSE, 'ipaSource': 'wiktionary',
                                  'headwordIpa': ENTRY['ipa'], 'entry': {'state': 'ready', 'url': ENTRY_URL},
                                  'audio': {'state': 'none', 'url': None}, 'sound': {'state': 'none', 'url': None}})
                return reply({'state': 'none'})
            if p.startswith('/api/me/word/'):
                return reply({'state': 'ready', 'url': ENTRY_URL} if p.endswith('/entry') else {'state': 'none'})
            if p == '/api/me/cards/keys':
                return reply({'keys': []})
            if p == '/api/me/cards/save':
                return reply({'saved': True, 'count': len(WORDS)})
            if p == '/api/me/cards':
                return reply(self.saved())
            if p == '/api/me/cards/practice':
                return reply(self.practice())
            if p == '/api/me/cards/review':
                nxt = {'right': 'In 3 days', 'almost': 'Tomorrow'}.get(body().get('answer'), 'In 10 min')
                return reply({'due': self.now + 86400, 'next': nxt, 'kind': 'learning', 'level': 2})
            if p == '/api/me/cards/sound':
                return reply({'state': 'none'})
            return reply({})

        page.route(self.base + '/api/**', api)
        page.route('**/dictionary/v4/fr/vi/*noun.json', lambda r: r.fulfill(
            status=200, content_type='application/json', body=json.dumps(ENTRY)))
