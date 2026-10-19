// Builds the static site into _site/: every src/pages/<slug>.html is wrapped in
// src/layout.html with the sidebar, breadcrumbs, "On this page" contents and
// previous/next links, and a search index is written for the search box.
//
// A page starts with a JSON comment holding its metadata:
//   <!-- {"title": "...", "description": "...", "layout": "home"} -->
import fs from 'node:fs';
import path from 'node:path';

const SITE_URL = 'https://dictationdaily.github.io';
const REPO_URL = 'https://github.com/DictationDaily/dictationdaily.github.io';
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

function readPage(slug) {
    const raw = fs.readFileSync(`src/pages/${slug}.html`, 'utf8');
    const match = raw.match(/^<!--\s*(\{[\s\S]*?\})\s*-->\s*/);
    if (!match) throw new Error(`${slug}.html: missing metadata comment`);
    return { meta: JSON.parse(match[1]), body: raw.slice(match[0].length) };
}

// Give h2/h3 ids and a hover anchor; collect them for the contents column
function addAnchors(body) {
    const headings = [];
    const used = new Set();
    const html = body.replace(
        /<h([23])([^>]*)>([\s\S]*?)<\/h\1>/g,
        (all, level, attrs, inner) => {
            let id = (attrs.match(/\sid="([^"]+)"/) || [])[1];
            if (!id) {
                id = slugify(inner);
                let n = 2;
                while (used.has(id)) id = `${slugify(inner)}-${n++}`;
                attrs += ` id="${id}"`;
            }
            used.add(id);
            const text = stripTags(inner.replace(/<span class="badge[^>]*>.*?<\/span>/g, ''));
            headings.push({ level: Number(level), id, text });
            return `<h${level}${attrs} class="group scroll-mt-24">${inner}<a href="#${id}" class="anchor" aria-label="Link to this section">#</a></h${level}>`;
        },
    );
    // Each heading's section text, so search can link straight to it
    const chunks = html.split(/(?=<h[23][\s>])/);
    chunks.slice(chunks.length - headings.length).forEach((chunk, i) => {
        headings[i].body = stripTags(
            chunk
                .replace(/<a [^>]*class="anchor"[^>]*>#<\/a>/g, '')
                .replace(/<span class="badge[^>]*>.*?<\/span>/g, ''),
        );
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
                <li><a href="${p.slug}.html" class="nav-link${p.slug === current ? ' active" aria-current="page' : ''}">${p.title}</a></li>`,
                )
                .join('')}
            </ul>
        </div>`,
        )
        .join('');
}

function tocColumn(headings) {
    if (headings.length < 2) return '';
    return `
        <p class="mb-3 text-xs font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">On this page</p>
        <ul class="space-y-1.5 border-l border-gray-200 text-sm dark:border-gray-800">${headings
            .map(
                (h) => `
            <li><a href="#${h.id}" class="toc-link ${h.level === 3 ? 'pl-7' : 'pl-4'}">${escape(h.text)}</a></li>`,
            )
            .join('')}
        </ul>`;
}

function prevNext(index) {
    const prev = ordered[index - 1];
    const next = ordered[index + 1];
    const card = (p, dir) =>
        p
            ? `<a href="${p.slug}.html" class="pager group ${dir === 'next' ? 'sm:col-start-2 text-right' : ''}">
                <span class="text-xs uppercase tracking-wide text-gray-500">${dir === 'next' ? 'Next' : 'Previous'}</span>
                <span class="mt-1 block font-semibold text-ink group-hover:text-brand dark:text-white">${dir === 'next' ? '' : '← '}${p.title}${dir === 'next' ? ' →' : ''}</span>
            </a>`
            : '';
    return `<nav class="mt-16 grid gap-4 sm:grid-cols-2" aria-label="Previous and next page">${card(prev, 'prev')}${card(next, 'next')}</nav>`;
}

function render(slug, meta, body) {
    const index = ordered.findIndex((p) => p.slug === slug);
    const entry = ordered[index];
    const home = meta.layout === 'home' || meta.layout === 'plain';
    const { html, headings } = home
        ? { html: body, headings: [] }
        : addAnchors(body);
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
            <nav class="mb-4 flex items-center gap-1.5 text-sm text-gray-500" aria-label="Breadcrumb">
                <a href="./" class="hover:text-brand">Guide</a><span aria-hidden="true">›</span>
                <span>${entry ? entry.group : ''}</span>
            </nav>
            <h1 class="text-3xl font-black tracking-tight text-ink sm:text-4xl dark:text-white">${meta.title}</h1>
            ${meta.description ? `<p class="mt-3 text-lg text-gray-600 dark:text-gray-400">${meta.description}</p>` : ''}
            <div class="prose prose-gray mt-8 max-w-none dark:prose-invert">${html}</div>
            <div class="mt-12 flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 pt-6 text-sm text-gray-500 dark:border-gray-800">
                <span>Screenshots from the live app.</span>
                <a class="hover:text-brand" href="${REPO_URL}/edit/main/src/pages/${slug}.html">Suggest an edit on GitHub</a>
            </div>
            ${index >= 0 ? prevNext(index) : ''}`,
        toc: home ? '' : tocColumn(headings),
    };
    return {
        page: layout.replace(/\{\{(\w+)\}\}/g, (_, key) => vars[key] ?? ''),
        headings,
        text: stripTags(
            html
                .replace(/<a [^>]*class="anchor"[^>]*>#<\/a>/g, '')
                .replace(/<span class="badge[^>]*>.*?<\/span>/g, ''),
        ),
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
        page = page.replace(
            /(href|src)="(?!https?:|#|\/|mailto:)/g,
            '$1="/',
        ).replace(/="\/\.\/"/g, '="/"');
    }
    fs.writeFileSync(path.join(OUT, `${slug}.html`), page);
    if (slug === 'index' || slug === '404') continue;
    const group = ordered.find((p) => p.slug === slug)?.group || '';
    search.push({
        url: `${slug}.html`,
        title: meta.title,
        group,
        description: meta.description || '',
        headings: headings.map((h) => ({ id: h.id, text: h.text, body: h.body })),
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
fs.cpSync('images', path.join(OUT, 'images'), { recursive: true });
fs.cpSync('assets', path.join(OUT, 'assets'), { recursive: true });
fs.copyFileSync('favicon.ico', path.join(OUT, 'favicon.ico'));
console.log(`built ${slugs.length} pages into ${OUT}/`);
