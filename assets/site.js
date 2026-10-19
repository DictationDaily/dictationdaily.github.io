// Theme toggle, navigation drawer, search, step-by-step tours, screen
// recordings, scroll animations, tabbed screenshots and the lightbox.
// No dependencies.
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


    const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Step-by-step tours: one slide visible, Back/Next, dots, arrow keys
    $$('[data-tour]').forEach((tour) => {
        const slides = $$('[data-slide]', tour);
        const dots = $('[data-dots]', tour);
        const bar = $('[data-bar]', tour);
        const prev = $('[data-prev]', tour);
        const next = $('[data-next]', tour);
        let current = 0;
        slides.forEach((_, i) => {
            const d = document.createElement('button');
            d.type = 'button';
            d.setAttribute('aria-label', `Step ${i + 1}`);
            d.addEventListener('click', () => go(i));
            dots.appendChild(d);
        });
        const go = (i) => {
            if (i < 0 || i >= slides.length) return;
            slides.forEach((s, j) => {
                s.classList.toggle('active', j === i);
                s.classList.toggle('from-left', j < i);
                s.setAttribute('aria-hidden', j !== i);
            });
            $$('button', dots).forEach((d, j) => d.classList.toggle('on', j === i));
            bar.style.width = `${((i + 1) / slides.length) * 100}%`;
            prev.disabled = i === 0;
            const last = i === slides.length - 1;
            next.textContent = last ? 'Start again ↺' : 'Next →';
            current = i;
        };
        prev.addEventListener('click', () => go(current - 1));
        next.addEventListener('click', () => go(current === slides.length - 1 ? 0 : current + 1));
        tour.tabIndex = 0;
        tour.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight') { e.preventDefault(); go(current + 1); }
            if (e.key === 'ArrowLeft') { e.preventDefault(); go(current - 1); }
        });
        // Swipe on touch screens
        let x0 = null;
        tour.addEventListener('touchstart', (e) => { x0 = e.touches[0].clientX; }, { passive: true });
        tour.addEventListener('touchend', (e) => {
            if (x0 === null) return;
            const dx = e.changedTouches[0].clientX - x0;
            if (Math.abs(dx) > 50) go(current + (dx < 0 ? 1 : -1));
            x0 = null;
        });
        go(0);
    });

    // Screen recordings: play while on screen, pause button, no autoplay for reduced motion
    $$('[data-demo]').forEach((demo) => {
        const video = $('video', demo);
        const toggle = $('[data-demo-toggle]', demo);
        let userPaused = reduceMotion;
        const sync = () => {
            demo.classList.toggle('paused', video.paused);
            toggle.setAttribute('aria-label', video.paused ? 'Play' : 'Pause');
        };
        video.addEventListener('play', sync);
        video.addEventListener('pause', sync);
        const flip = () => {
            if (video.paused) { userPaused = false; video.play().catch(() => {}); }
            else { userPaused = true; video.pause(); }
        };
        toggle.addEventListener('click', flip);
        video.addEventListener('click', flip);
        new IntersectionObserver(([entry]) => {
            if (entry.isIntersecting && !userPaused) video.play().catch(sync);
            else if (!entry.isIntersecting) video.pause();
        }, { threshold: 0.35 }).observe(video);
        sync();
    });

    // Fade content in as it scrolls into view
    if (!reduceMotion && 'IntersectionObserver' in window) {
        document.documentElement.classList.add('motion');
        const blocks = $$('.reveal, .prose > *, .doc-main nav, [data-reveal] > *');
        blocks.forEach((el) => el.classList.add('reveal'));
        const io = new IntersectionObserver((entries) => {
            entries.forEach((e) => {
                if (e.isIntersecting) { e.target.classList.add('shown'); io.unobserve(e.target); }
            });
        }, { rootMargin: '0px 0px -8% 0px' });
        blocks.forEach((el) => io.observe(el));
    }

    // "When does my streak day change?" in the reader's own time zone
    $$('[data-utc-midnight]').forEach((el) => {
        const d = new Date();
        d.setUTCHours(24, 0, 0, 0);
        el.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    });

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
            list.innerHTML = `<li class="px-3 py-6 text-center text-sm text-gray-500">Try <button class="text-brand underline" data-q="slow">slow</button>, <button class="text-brand underline" data-q="skip">skip</button>, <button class="text-brand underline" data-q="streak">streak</button> or <button class="text-brand underline" data-q="phone">phone</button>.</li>`;
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
                if (heading) {
                    const t = heading.text.toLowerCase();
                    if (words.every((w) => t.includes(w))) score += 25;
                    else if (words.some((w) => t.includes(w))) score += 5;
                }
                results.push({ p, heading, score });
            }
            results.sort((a, b) => b.score - a.score);
            results = results.slice(0, 12);
            selected = 0;
            list.innerHTML = results.length
                ? results.map((r, i) => `
                    <li role="option" aria-selected="${i === 0}">
                        <a href="/${r.p.url}${r.heading ? '#' + r.heading.id : ''}" class="search-hit">
                            <span class="text-xs uppercase tracking-wide text-gray-400">${r.p.icon || ''} ${esc(r.p.group)}</span>
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
