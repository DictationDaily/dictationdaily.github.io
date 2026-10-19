// Theme toggle, navigation drawer, search, "On this page" highlight, tabbed
// screenshots and the screenshot lightbox. No dependencies.
(() => {
    const $ = (s, el = document) => el.querySelector(s);
    const $$ = (s, el = document) => [...el.querySelectorAll(s)];
    const store = {
        get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
        set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} },
    };

    // Theme
    $('#theme-toggle')?.addEventListener('click', () => {
        const dark = document.documentElement.classList.toggle('dark');
        store.set('theme', dark ? 'dark' : 'light');
    });

    // Modal helpers (drawer, search, lightbox)
    const open = (el) => { el.classList.remove('hidden'); if (el.id === 'lightbox') el.classList.add('flex'); document.body.style.overflow = 'hidden'; };
    const close = (el) => { el.classList.add('hidden'); el.classList.remove('flex'); document.body.style.overflow = ''; };
    $$('[data-close]').forEach((b) => b.addEventListener('click', () => close(b.closest('[role="dialog"]'))));

    // Drawer
    const drawer = $('#drawer');
    $('#drawer-open')?.addEventListener('click', () => open(drawer));
    $$('#drawer a').forEach((a) => a.addEventListener('click', () => close(drawer)));
    $('#drawer .active')?.scrollIntoView({ block: 'center' });

    // Tabbed screenshots: <div data-tabs> with [data-tab] buttons and [data-panel] figures
    $$('[data-tabs]').forEach((group) => {
        const buttons = $$('[data-tab]', group);
        const panels = $$('[data-panel]', group);
        const select = (i) => {
            buttons.forEach((b) => {
                const on = b.dataset.tab === String(i);
                b.setAttribute('aria-selected', on);
                b.classList.toggle('tab-on', on);
            });
            panels.forEach((p) => p.classList.toggle('hidden', p.dataset.panel !== String(i)));
        };
        buttons.forEach((b) => b.addEventListener('click', () => select(b.dataset.tab)));
        select(0);
    });

    // Lightbox: click any screenshot to enlarge it
    const box = $('#lightbox');
    $$('main img').forEach((img) => {
        img.addEventListener('click', () => {
            $('#lightbox-img').src = img.src;
            $('#lightbox-img').alt = img.alt;
            $('#lightbox-cap').textContent = img.closest('figure')?.querySelector('figcaption')?.textContent || img.alt;
            open(box);
        });
    });
    box?.addEventListener('click', () => close(box));

    // "On this page": highlight the last heading that has scrolled past 25% of the viewport
    const tocLinks = $$('#toc a');
    if (tocLinks.length) {
        const targets = tocLinks.map((a) => document.getElementById(a.hash.slice(1)));
        let ticking = false;
        const highlight = () => {
            ticking = false;
            const line = innerHeight * 0.25;
            let current = 0;
            targets.forEach((t, i) => { if (t && t.getBoundingClientRect().top <= line) current = i; });
            if (innerHeight + scrollY >= document.body.scrollHeight - 4) current = targets.length - 1;
            tocLinks.forEach((a, i) => a.classList.toggle('active', i === current));
        };
        addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(highlight); } }, { passive: true });
        highlight();
    }

    // Search
    const search = $('#search');
    const input = $('#search-input');
    const list = $('#search-results');
    let index = null;
    let results = [];
    let selected = 0;
    const loadIndex = () => index || (index = fetch('/search-index.json').then((r) => r.json()).catch(() => []));
    const openSearch = () => { open(search); input.value = ''; render(''); input.focus(); loadIndex().then(() => render(input.value)); };
    $('#search-open')?.addEventListener('click', openSearch);
    addEventListener('keydown', (e) => {
        const typing = /INPUT|TEXTAREA/.test(document.activeElement?.tagName);
        if ((e.key === 'k' && (e.ctrlKey || e.metaKey)) || (e.key === '/' && !typing)) {
            e.preventDefault();
            openSearch();
        } else if (e.key === 'Escape') {
            $$('[role="dialog"]').forEach(close);
        }
    });

    const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
    const mark = (s, words) => words.reduce((acc, w) => acc.replace(new RegExp(`(${w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'), '<mark>$1</mark>'), esc(s));

    function snippet(text, words) {
        const lower = text.toLowerCase();
        const at = Math.max(0, Math.min(...words.map((w) => { const i = lower.indexOf(w); return i < 0 ? Infinity : i; })));
        if (!isFinite(at)) return text.slice(0, 120) + '…';
        const start = Math.max(0, at - 50);
        return (start ? '…' : '') + text.slice(start, start + 140) + '…';
    }

    function render(query) {
        const words = query.toLowerCase().split(/\s+/).filter(Boolean);
        if (!words.length) {
            results = [];
            list.innerHTML = `<li class="px-3 py-6 text-center text-sm text-gray-500">Try <button class="text-brand underline" data-q="speed">speed</button>, <button class="text-brand underline" data-q="streak">streak</button>, <button class="text-brand underline" data-q="skip">skip</button> or <button class="text-brand underline" data-q="phone">phone</button>.</li>`;
            $$('[data-q]', list).forEach((b) => b.addEventListener('click', () => { input.value = b.dataset.q; input.dispatchEvent(new Event('input')); input.focus(); }));
            return;
        }
        Promise.resolve(loadIndex()).then((pages) => {
            results = [];
            for (const p of pages) {
                const title = p.title.toLowerCase();
                const body = (p.description + ' ' + p.text).toLowerCase();
                if (!words.every((w) => title.includes(w) || body.includes(w) || p.headings.some((h) => h.text.toLowerCase().includes(w)))) continue;
                let score = words.reduce((s, w) => s + (title.includes(w) ? 10 : 0) + (body.split(w).length - 1), 0);
                // Link to the section that matches best: heading text counts most
                let heading = null;
                let best = 0;
                for (const h of p.headings) {
                    const t = h.text.toLowerCase();
                    const s = (h.body || '').toLowerCase();
                    const hs = words.reduce((n, w) => n + (t.includes(w) ? 20 : 0) + (s.split(w).length - 1), 0);
                    if (hs > best) { best = hs; heading = h; }
                }
                if (heading && words.some((w) => heading.text.toLowerCase().includes(w))) score += 5;
                results.push({ p, heading, score });
            }
            results.sort((a, b) => b.score - a.score);
            results = results.slice(0, 12);
            selected = 0;
            list.innerHTML = results.length
                ? results.map((r, i) => `
                    <li role="option" aria-selected="${i === 0}">
                        <a href="/${r.p.url}${r.heading ? '#' + r.heading.id : ''}" class="search-hit">
                            <span class="text-xs uppercase tracking-wide text-gray-400">${esc(r.p.group)}</span>
                            <span class="block font-semibold text-ink dark:text-white">${mark(r.p.title, words)}${r.heading ? ` <span class="font-normal text-gray-500">› ${mark(r.heading.text, words)}</span>` : ''}</span>
                            <span class="mt-0.5 block text-sm text-gray-500">${mark(snippet(r.heading?.body || r.p.text, words), words)}</span>
                        </a>
                    </li>`).join('')
                : `<li class="px-3 py-6 text-center text-sm text-gray-500">No results for “${esc(query)}”. Try the <a class="text-brand underline" href="faq.html">FAQ</a>.</li>`;
            $$('a', list).forEach((a) => a.addEventListener('click', () => close(search)));
        });
    }

    input?.addEventListener('input', () => render(input.value));
    input?.addEventListener('keydown', (e) => {
        const items = $$('[role="option"]', list);
        if (!items.length) return;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            selected = (selected + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
            items.forEach((li, i) => li.setAttribute('aria-selected', i === selected));
            items[selected].scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'Enter') {
            e.preventDefault();
            $('a', items[selected])?.click();
        }
    });

    // FAQ filter: <input data-faq-filter> hides <details data-faq> that don't match
    const filter = $('[data-faq-filter]');
    if (filter) {
        const items = $$('[data-faq]');
        const empty = $('[data-faq-empty]');
        filter.addEventListener('input', () => {
            const words = filter.value.toLowerCase().split(/\s+/).filter(Boolean);
            let shown = 0;
            items.forEach((d) => {
                const hit = words.every((w) => d.textContent.toLowerCase().includes(w));
                d.classList.toggle('hidden', !hit);
                if (hit) shown++;
                d.open = words.length > 0 && hit && shown <= 3;
            });
            $$('[data-faq-group]').forEach((g) => g.classList.toggle('hidden', !$$('[data-faq]:not(.hidden)', g).length));
            empty?.classList.toggle('hidden', shown > 0);
        });
    }

    // Open the FAQ answer a link points at (faq.html#some-question)
    const openFromHash = () => {
        const target = location.hash && document.getElementById(location.hash.slice(1));
        if (target?.tagName === 'DETAILS') target.open = true;
    };
    openFromHash();
    addEventListener('hashchange', openFromHash);
})();
