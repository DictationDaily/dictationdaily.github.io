// Builds the static site into _site/: every src/pages/<slug>.html is wrapped in
// src/layout.html with the sidebar and the "next step" card, and a search index
// is written for the search box.
//
// A page starts with a JSON comment holding its metadata:
//   <!-- {"title": "...", "description": "...", "time": "1 min", "layout": "home"} -->
//
// Pages can use three shorthand tags, expanded here so the pages stay short:
//   <tour><step img="lesson-intro" x="95.9" y="53.6" title="Press START">Text</step>…</tour>
//       a click-through, one screenshot per step with a pulsing marker at x%/y%
//       (add phone to <step> for a phone screenshot; the shot zooms in on the
//       marker, zoom="1" turns that off)
//   <demo src="lesson" caption="…"></demo>  (add phone for a phone recording)
//       a looping screen recording from videos/<src>.mp4
//   <shot src="library" caption="…" alt="…">  a screenshot from images/<src>.webp
import fs from 'node:fs';
import path from 'node:path';

const SITE_URL = 'https://dictationdaily.github.io';
const OUT = '_site';

const nav = JSON.parse(fs.readFileSync('src/nav.json', 'utf8'));
const layout = fs.readFileSync('src/layout.html', 'utf8');
const ordered = nav.flatMap((group) =>
    group.pages.map((page) => ({ ...page, group: group.title })),
);

const escape = (s) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const stripTags = (s) =>
    s
        .replace(/<[^>]+>/g, ' ')
        .replace(/&nbsp;/g, ' ')
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/\s+/g, ' ')
        .trim();
const slugify = (s) =>
    stripTags(s)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '');
const attrs = (s) =>
    Object.fromEntries(
        [...s.matchAll(/(\w+)(?:="([^"]*)")?/g)].map((m) => [m[1], m[2] ?? true]),
    );

function readPage(slug) {
    const raw = fs.readFileSync(`src/pages/${slug}.html`, 'utf8');
    const match = raw.match(/^<!--\s*(\{[\s\S]*?\})\s*-->\s*/);
    if (!match) throw new Error(`${slug}.html: missing metadata comment`);
    return { meta: JSON.parse(match[1]), body: raw.slice(match[0].length) };
}

function imageSize(name) {
    if (name.startsWith('mobile-')) return [780, 1688];
    if (name.startsWith('tablet-')) return [820, 1180];
    if (name.startsWith('youtube-')) return [704, 720];
    return [1440, 900];
}

function expandTour(_, inner) {
    const steps = [...inner.matchAll(/<step([^>]*)>([\s\S]*?)<\/step>/g)];
    const slides = steps
        .map(([, a, text], i) => {
            const s = attrs(a);
            const [w, h] = imageSize(s.img);
            const spots = [[s.x, s.y], [s.x2, s.y2]]
                .filter(([x, y]) => x && y)
                .map(
                    ([x, y]) =>
                        `<span class="hotspot" style="left:${x}%;top:${y}%" aria-hidden="true"></span>`,
                )
                .join('');
            return `
            <div class="tour-slide${i === 0 ? ' active' : ''}" data-slide aria-hidden="${i !== 0}">
                <div class="tour-shot${s.phone ? ' tour-shot-phone' : ''}">
                    <div class="tour-zoom${s.zoom === '1' ? ' no-zoom' : ''}" style="transform-origin:${s.x || 50}% ${s.y || 50}%">
                        <img src="images/${s.img}.webp" alt="${escape(s.alt || s.title)}" width="${w}" height="${h}" loading="lazy">
                        ${spots}
                    </div>
                </div>
                <div class="tour-text">
                    <p class="tour-count">Step ${i + 1} of ${steps.length}</p>
                    <p class="tour-title">${s.title}</p>
                    ${text.trim() ? `<p class="tour-body">${text.trim()}</p>` : ''}
                </div>
            </div>`;
        })
        .join('');
    return `
        <div class="tour not-prose${steps.length === 1 ? ' tour-single' : ''}" data-tour>
            <div class="tour-progress"><span data-bar></span></div>
            <div class="tour-slides">${slides}</div>
            <div class="tour-nav">
                <button type="button" class="tour-btn" data-prev>← Back</button>
                <div class="tour-dots" data-dots></div>
                <button type="button" class="tour-btn tour-btn-next" data-next>Next →</button>
            </div>
        </div>`;
}

function expandDemo(_, a) {
    const s = attrs(a);
    const video = `<video src="videos/${s.src}.mp4" poster="videos/${s.src}.jpg" muted loop playsinline preload="none" aria-label="${escape(s.caption || 'Screen recording')}"></video>
            <button type="button" class="demo-toggle" data-demo-toggle aria-label="Pause"><span class="demo-pause">❚❚</span><span class="demo-play">▶</span></button>`;
    const frame = s.phone
        ? `<div class="demo-phone">${video}</div>`
        : `<div class="demo-browser"><div class="demo-bar"><i></i><i></i><i></i><span>dictationdaily.com</span></div><div class="relative">${video}</div></div>`;
    return `
        <figure class="demo not-prose${s.phone ? ' demo-is-phone' : ''}" data-demo>
            <div class="relative">${frame}</div>
            ${s.caption ? `<figcaption><span class="demo-badge">▶ Watch</span> ${s.caption}</figcaption>` : ''}
        </figure>`;
}

function expandShot(_, a) {
    const s = attrs(a);
    const [w, h] = imageSize(s.src);
    const phone = s.src.startsWith('mobile-');
    return `
        <figure class="figure not-prose">
            <img src="images/${s.src}.webp" alt="${escape(s.alt || s.caption || '')}" class="${phone ? 'phone' : 'shot'}" width="${w}" height="${h}" loading="lazy">
            ${s.caption ? `<figcaption>${s.caption}</figcaption>` : ''}
        </figure>`;
}

function expand(body) {
    return body
        .replace(/<tour>([\s\S]*?)<\/tour>/g, expandTour)
        .replace(/<demo([^>]*)><\/demo>/g, expandDemo)
        .replace(/<shot([^>]*)>/g, expandShot);
}

// Give h2s ids (for links and search) and collect them with their section text
function addAnchors(body) {
    const headings = [];
    const used = new Set();
    const html = body.replace(/<h2([^>]*)>([\s\S]*?)<\/h2>/g, (all, a, inner) => {
        let id = (a.match(/\sid="([^"]+)"/) || [])[1];
        if (!id) {
            id = slugify(inner);
            let n = 2;
            while (used.has(id)) id = `${slugify(inner)}-${n++}`;
            a += ` id="${id}"`;
        }
        used.add(id);
        headings.push({ id, text: stripTags(inner) });
        return `<h2${a} class="scroll-mt-24">${inner}</h2>`;
    });
    const chunks = html.split(/(?=<h2[\s>])/);
    chunks.slice(chunks.length - headings.length).forEach((chunk, i) => {
        headings[i].body = stripTags(chunk);
    });
    return { html, headings };
}

function sidebar(current) {
    return nav
        .map(
            (group) => `
        <div>
            <p class="mb-2 px-3 text-xs font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">${group.title}</p>
            <ul class="space-y-0.5">${group.pages
                .map(
                    (p) => `
                <li><a href="${p.slug}.html" class="nav-link${p.slug === current ? ' active" aria-current="page' : ''}"><span class="nav-icon" aria-hidden="true">${p.icon}</span>${p.title}</a></li>`,
                )
                .join('')}
            </ul>
        </div>`,
        )
        .join('');
}

function nextCard(index) {
    const next = ordered[index + 1];
    const prev = ordered[index - 1];
    return `
        <nav class="mt-16 grid gap-4 sm:grid-cols-[1fr_2fr]" aria-label="Next page">
            ${prev ? `<a href="${prev.slug}.html" class="pager"><span class="text-xs uppercase tracking-wide text-gray-500">← Back</span><span class="mt-1 block font-semibold text-ink dark:text-white">${prev.title}</span></a>` : '<span></span>'}
            ${next ? `<a href="${next.slug}.html" class="pager pager-next"><span class="text-xs uppercase tracking-wide text-red-100">Next</span><span class="mt-1 flex items-center justify-between gap-3 text-lg font-bold text-white"><span>${next.icon} ${next.title}</span><span class="pager-arrow" aria-hidden="true">→</span></span></a>` : `<a href="./" class="pager pager-next"><span class="text-xs uppercase tracking-wide text-red-100">You've read it all!</span><span class="mt-1 block text-lg font-bold text-white">🎉 Back to the guide home</span></a>`}
        </nav>`;
}

function render(slug, meta, body) {
    const index = ordered.findIndex((p) => p.slug === slug);
    const entry = ordered[index];
    const home = meta.layout === 'home' || meta.layout === 'plain';
    const { html, headings } = home
        ? { html: expand(body), headings: [] }
        : addAnchors(expand(body));
    const vars = {
        title:
            slug === 'index'
                ? 'Dictation Daily Guide'
                : `${meta.title} · Dictation Daily Guide`,
        description: escape(meta.description || ''),
        canonical: `${SITE_URL}/${slug === 'index' ? '' : slug + '.html'}`,
        sidebar: sidebar(slug),
        body_class: home ? 'layout-home' : 'layout-doc',
        content: home
            ? html
            : `
            <header class="reveal">
                <a href="./" class="text-sm font-medium text-gray-500 hover:text-brand">← Guide home</a>
                <div class="mt-5 flex items-start gap-4">
                    <span class="page-icon" aria-hidden="true">${entry?.icon || '📘'}</span>
                    <div>
                        <h1 class="text-3xl font-black tracking-tight text-ink sm:text-4xl dark:text-white">${meta.title}</h1>
                        ${meta.description ? `<p class="mt-2 text-lg text-gray-600 dark:text-gray-400">${meta.description}</p>` : ''}
                        ${meta.time ? `<p class="mt-3 inline-flex items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300">⏱ ${meta.time}</p>` : ''}
                    </div>
                </div>
            </header>
            <div class="prose prose-lg prose-gray mt-10 max-w-none dark:prose-invert">${html}</div>
            ${index >= 0 ? nextCard(index) : ''}`,
    };
    return {
        page: layout.replace(/\{\{(\w+)\}\}/g, (_, key) => vars[key] ?? ''),
        headings,
        text: stripTags(html),
    };
}

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT);

const slugs = ['index', ...ordered.map((p) => p.slug), '404'];
const search = [];
for (const slug of slugs) {
    const { meta, body } = readPage(slug);
    let { page, headings, text } = render(slug, meta, body);
    if (slug === '404') {
        // GitHub Pages serves 404.html at the missing URL, which may be nested
        page = page
            .replace(/(href|src|poster)="(?!https?:|#|\/|mailto:)/g, '$1="/')
            .replace(/="\/\.\/"/g, '="/"');
    }
    fs.writeFileSync(path.join(OUT, `${slug}.html`), page);
    if (slug === 'index' || slug === '404') continue;
    const entry = ordered.find((p) => p.slug === slug);
    search.push({
        url: `${slug}.html`,
        title: meta.title,
        icon: entry.icon,
        group: entry.group,
        description: meta.description || '',
        headings,
        text,
    });
}
fs.writeFileSync(path.join(OUT, 'search-index.json'), JSON.stringify(search));

fs.writeFileSync(
    path.join(OUT, 'sitemap.xml'),
    `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${slugs
    .filter((s) => s !== '404')
    .map((s) => `  <url><loc>${SITE_URL}/${s === 'index' ? '' : s + '.html'}</loc></url>`)
    .join('\n')}
</urlset>
`,
);
fs.writeFileSync(
    path.join(OUT, 'robots.txt'),
    `User-agent: *\nAllow: /\nSitemap: ${SITE_URL}/sitemap.xml\n`,
);
fs.writeFileSync(path.join(OUT, '.nojekyll'), '');
for (const dir of ['images', 'videos', 'assets']) {
    fs.cpSync(dir, path.join(OUT, dir), { recursive: true });
}
fs.copyFileSync('favicon.ico', path.join(OUT, 'favicon.ico'));
console.log(`built ${slugs.length} pages into ${OUT}/`);
