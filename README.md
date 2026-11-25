# Dictation Daily user guide

The help centre for [Dictation Daily](https://dictationdaily.com), published with GitHub Pages:
**https://docs.dictationdaily.com/** (GitHub Pages with a custom domain; https://dictationdaily.github.io/ redirects there)

A friendly, step-by-step help site for learners, styled with Tailwind CSS. Pages are short and task-based,
written in simple English, with scroll steps over real screenshots (no Back/Next buttons: the picture
follows the step you are reading), looping screen recordings of the app, search (`/` or `Ctrl K`), a filterable FAQ and dark mode. `build.mjs` wraps each page in one layout.

## Layout

| Path | What |
|---|---|
| `src/pages/<slug>.html` | Page content. Starts with `<!-- {"title": …, "description": …, "time": …} -->`. Can use `<tour>`/`<step>`, `<demo>` and `<shot>` (see `build.mjs`) |
| `src/coords.json`, `src/boxes.json` | Button positions and highlight boxes for `<tour>`/`<step>` (empty: no page uses tours now) |
| `src/nav.json` | Sidebar groups, page icons and order (also sets the Next card) |
| `src/layout.html` | Header, sidebar, contents column, footer, search and lightbox |
| `src/input.css` | Tailwind entry and the content components (`callout`, `figure`, `steps`, `faq`, …) |
| `assets/site.js` | Scroll steps, recordings, scroll animations, search, theme, drawer, lightbox, FAQ filter |
| `build.mjs` | Writes `_site/`: pages, `search-index.json`, `sitemap.xml`, `robots.txt` |
| `images/` | Screenshots (WebP) |
| `videos/` | Screen recordings (`.mp4`) and their posters (`.jpg`) |

To add a page: create `src/pages/<slug>.html` and add it to `src/nav.json`.

## Develop

```bash
npm install
npm run build          # CSS + pages into _site/
npm run serve          # http://localhost:8000
npm run dev            # in another terminal: rebuild CSS on change (rerun build:pages after editing pages)
```

Pushing to `main` builds and deploys the site (`.github/workflows/pages.yml`).

## Screenshots

The pictures the pages show come from `scripts/shots.py`, on the live site, as the **Demo Learner** (see below). Since 2026-11-26 it takes exactly the shots the pages use: the hint close-ups (`lesson-hint`, `lesson-hint-missing`, `lesson-hint-extra`, `lesson-almost`, also the site's preview picture), `my-videos` (History), `youtube-speed-menu`, the finish screens (`lesson-last-part`, `lesson-finished-streak`, `lesson-finished-return`), `lesson-no-transcript` and `not-found`.

```bash
pip install playwright pillow
python3 scripts/shots.py                 # all, or: python3 scripts/shots.py my-videos not-found
python3 scripts/to_webp.py               # PNG -> WebP, and the crop-* hint close-ups
```

`lesson-finished-streak` spends about a minute on each of the video's last 6 sentences, so the finish screen shows the minutes of a real pass (about 7 minutes to take). `lesson-no-transcript` serves the page a lesson text with every line marked "just listen", which is what a lesson without exercises is.

Since 2026-11-26 `images/` holds only these 12 pictures: the older capture scripts (`capture.py`, `capture_signed_in.py`, `capture_pro.py`, `boxes.py`), which took the October 2026 app, and the 66 pictures no page used were removed. Never use screenshots that show a real learner's name, email or avatar.

### The Demo Learner

Every recording and screenshot is signed in as the Demo Learner: a Pro learner of French (mother tongue Vietnamese) whose every `/api` call is answered in the browser (`scripts/words_demo.py` for the words, the dictionary and today's streak; `scripts/learner_demo.py` for the practice card's inputs, My progress and Your skills, History, Liked, a lesson's likes and comments, Add a video and its minutes; `scripts/playlists_demo.py` for Playlists and the lesson's Save). Nothing is read from or written to any account, and no paid call is made. The lessons, their text, translations, the catalogue and the playlists of DictationDaily are the live ones. Its data is made around real videos of the live catalogue (titles, levels, lengths), and the word cards play real native recordings from Lingua Libre (Wikimedia Commons, with their credit). The shapes of the answers follow the app's worker (`worker/api.ts`, `worker/video-social.ts`, `worker/added-videos.ts`); when a page shows *Something went wrong* or a placeholder, an answer's shape has changed there. `DD_SESSION` (a real Pro account's cookie, read-only through `pro_session.py`) still works instead, but such an account shows its own, often empty, data.

## Screen recordings

Every page leads with a recording (since 2026-11-03): `<watch src="voice" title="…"></watch>` (add `phone` for a phone one) shows `videos/voice.mp4` with its steps beside it, which light up and fill as the video plays; clicking a step plays from there. The steps are the captions the recording shows, saved with their times in `videos/<scene>.json` by `scripts/record.py`, so a new recording brings its own steps. Pages keep text short: the description, the recording, at most three cards, and collapsed questions.

```bash
python3 scripts/record.py                 # all scenes, as the Demo Learner (see Screenshots)
python3 scripts/record.py voice shadow    # some
```

Scenes: `lesson`, `hints`, `library`, `speed`, `navigate`, `listen`, `mobile`, `translation`, `word`, `voice`, `pronounce`, `shadow`, `resume`, `streak`, `report`, `words`, `your-words`, `whole`, `theme`, `playlist`, `playlist-make`, and since 2026-11-26 `practice` (the practice card), `parts` (Part done), `skills` (Your skills), `social` (👍, Save, comments), `addvideo` (Add a video), `layout` (the small player; it replaced `cover`, the retired subtitle cover) and `hover` (the hover card and a phrase). Every lesson opens on Bizzy's question: scenes press **Listening** (or **Speaking**) where they used to press START (`pick()` / `pick_button()`). In the scenes with speech the speech checks (`voice-answer`, `shadow-check`, `word-check`) are answered in the browser with a canned result, and the microphone is Chrome's fake device fed a voice-like tone, so a recording makes no paid call; the interface filmed is the real one. `DD_DEBUG=<dir>` saves a screenshot when a scene breaks.

The look is Cap's: `scripts/cap_render.py` draws a big pointer, a red ring on each click and the captions over the frames, and zooms in gently (1.35×, 1.2× on a phone, where it stays centred across) towards whatever is clicked, typed into (`type_()`) or pointed at (`look()`). It doesn't overuse the zoom: once in, it stays in and glides to the next action while that is close by and comes within 5 s, and skips a zoom-out shorter than 1.5 s; it zooms out only when the next action is far away, after a pause, or at the end. Each take (frames + event log) is kept in `~/.cache/dd-guide/takes/`, so `python3 scripts/record.py --render [scene …]` redraws the videos with new settings without recording again. `record.py` logs those events while Chrome's screencast saves the frames; nothing is drawn into the page itself. Captions use Nunito (downloaded once to `~/.cache/dd-guide/Nunito.ttf`, DejaVu Sans if missing).

## Vietnamese (`/vi/`)

The whole guide is also in Vietnamese at https://docs.dictationdaily.com/vi/ (since 2026-11-05). The flag in the header opens a menu of both languages by flag (English 🇬🇧, Tiếng Việt 🇻🇳, images from the app's `public/flags`); each opens the same page and section in the other language, and every page carries `hreflang` links.

- Pages: `src/vi/pages/<slug>.html`, the same slugs and HTML as `src/pages/` with the text translated. `<h2>`s keep the English anchor as `id="…"`, so `#links` work in both. The app's buttons stay in English (**START**, **CHECK**…), as learners see them on screen.
- Sidebar: `src/vi/nav.json`. Layout words (header, footer, search, Next card): `src/strings.json`, one block per language; `assets/site.js` has its few words in `WORDS`.
- Recordings: `videos/vi/<scene>.mp4|jpg|json` are the same takes with Vietnamese captions, from `scripts/captions.vi.json` (English caption → Vietnamese): `python3 scripts/record.py --render --lang vi [scene …]`. After recording a scene again, add any new caption to that file (the render stops on a missing one) and redraw it. A page whose scene has no Vietnamese video uses the English one.
- Headings: Fredoka has no Vietnamese letters (ữ ạ ầ fell back to a serif face), so Vietnamese pages use Baloo 2 (weight 800 for big headings) through `--font-display` in `src/input.css`.
- Search is per language (`vi/search-index.json`) and ignores accents (“toc do” finds “tốc độ”).
- When an English page changes, change its Vietnamese page in the same PR.

## Keeping it accurate

Behaviour described here was checked against the app's code and the live site. When the app changes, update the matching page, and the FAQ if a question is affected.
