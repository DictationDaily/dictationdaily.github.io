// Theme toggle, navigation drawer, search, scroll steps, screen recordings,
// scroll animations and the lightbox.
// No dependencies.
(() => {
    const $ = (s, el = document) => el.querySelector(s);
    const $$ = (s, el = document) => [...el.querySelectorAll(s)];
    const store = {
        get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
        set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} },
    };

    // Words this script writes, in the page's language (<html lang>)
    const WORDS = {
        en: {
            play: 'Play', pause: 'Pause', try: 'Try', or: 'or', tryWords: ['slow', 'skip', 'streak', 'phone'],
            none: (q) => `No results for “${q}”. Try the <a class="text-brand underline" href="faq.html">FAQ</a>.`,
        },
        vi: {
            play: 'Phát', pause: 'Tạm dừng', try: 'Thử', or: 'hoặc', tryWords: ['nghe chậm', 'bỏ qua', 'chuỗi ngày', 'điện thoại'],
            none: (q) => `Không tìm thấy “${q}”. Xem <a class="text-brand underline" href="faq.html">Câu hỏi thường gặp</a>.`,
        },
    };
    const T = WORDS[document.documentElement.lang] || WORDS.en;

    // The other language's page opens at the same section
    $$('[data-lang-link]').forEach((a) => a.addEventListener('click', () => {
        if (location.hash) a.href = a.href.split('#')[0] + location.hash;
    }));

    // The flag menu: opens on click, closes on a click outside or Esc
    $$('[data-lang-menu]').forEach((menu) => {
        const button = $('button', menu);
        const list = $('ul', menu);
        const show = (on) => { list.classList.toggle('hidden', !on); button.setAttribute('aria-expanded', on); };
        button.addEventListener('click', (e) => { e.stopPropagation(); show(list.classList.contains('hidden')); });
        document.addEventListener('click', (e) => { if (!menu.contains(e.target)) show(false); });
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape') show(false); });
    });

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

    // Scroll steps: the step nearest the middle of the screen is active; its
    // picture shows beside the list on wide screens and zooms in
    $$('[data-steps]').forEach((group) => {
        const steps = $$('[data-step]', group);
        const shots = $$('[data-stage-shot]', group);
        let current = 0;
        const select = (i) => {
            if (i === current) return;
            const from = shots[current], to = shots[i];
            const img = (shot) => $('img', shot)?.getAttribute('src');
            const glide = from && to && !reduceMotion && img(from) === img(to)
                && $('.hotspot', from) && $('.hotspot', to)
                && $('.hotspot', from).classList.contains('pointer') === $('.hotspot', to).classList.contains('pointer');
            current = i;
            let target;
            if (glide) {
                // Same picture: show the new step where the old one was, then
                // let the highlight and the zoom slide over to the new target
                const zf = $('.step-zoom', from), zt = $('.step-zoom', to);
                const hf = $('.hotspot', from), ht = $('.hotspot', to);
                target = [zt.style.transformOrigin, ht.style.cssText];
                group.classList.add('snap');
                zt.style.transformOrigin = zf.style.transformOrigin;
                ht.style.cssText = hf.style.cssText;
                ht.classList.add('glide');
                zt.classList.add('glide');
            }
            steps.forEach((s, j) => s.classList.toggle('is-active', j === i));
            shots.forEach((s, j) => {
                s.classList.toggle('is-active', j === i);
                if (j !== i) $$('.glide', s).forEach((el) => el.classList.remove('glide'));
            });
            if (glide) {
                void to.offsetWidth;
                group.classList.remove('snap');
                $('.step-zoom', to).style.transformOrigin = target[0];
                $('.hotspot', to).style.cssText = target[1];
            }
        };
        if (!('IntersectionObserver' in window)) return;
        const io = new IntersectionObserver((entries) => {
            entries.forEach((e) => { if (e.isIntersecting) select(steps.indexOf(e.target)); });
        }, { rootMargin: '-40% 0px -50% 0px' });
        steps.forEach((s) => io.observe(s));
        // Clicking a step (wide screens) shows its picture too
        steps.forEach((s, i) => s.addEventListener('click', () => select(i)));
    });

    // Screen recordings: play while on screen, pause button, no autoplay for reduced motion
    $$('[data-demo]').forEach((demo) => {
        const video = $('video', demo);
        const toggle = $('[data-demo-toggle]', demo);
        let userPaused = reduceMotion;
        const sync = () => {
            demo.classList.toggle('paused', video.paused);
            toggle.setAttribute('aria-label', video.paused ? T.play : T.pause);
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

    // Walkthroughs: the step being played lights up and fills; a click on a
    // step plays the recording from there
    $$('[data-watch]').forEach((watch) => {
        const video = $('video', watch);
        const steps = $$('.watch-step', watch);
        const tick = () => {
            const t = video.currentTime;
            steps.forEach((b) => {
                const from = +b.dataset.t, to = +b.dataset.end;
                const on = t >= from && t < to;
                b.classList.toggle('is-active', on);
                b.classList.toggle('is-done', t >= to);
                b.style.setProperty('--p', on ? Math.min(1, (t - from) / Math.max(0.1, to - from)) : (t >= to ? 1 : 0));
            });
        };
        let raf = 0;
        const loop = () => { tick(); raf = requestAnimationFrame(loop); };
        video.addEventListener('play', () => { cancelAnimationFrame(raf); loop(); });
        video.addEventListener('pause', () => { cancelAnimationFrame(raf); tick(); });
        video.addEventListener('seeked', tick);
        steps.forEach((b) => b.addEventListener('click', () => {
            video.currentTime = +b.dataset.t + 0.05;
            video.play().catch(() => {});
        }));
    });

    // The home page's small recordings play while on screen
    $$('video[data-autoplay]').forEach((video) => {
        if (reduceMotion) return;
        new IntersectionObserver(([e]) => {
            if (e.isIntersecting) video.play().catch(() => {});
            else video.pause();
        }, { threshold: 0.4 }).observe(video);
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
        // in the page's language: 07:00 on the Vietnamese guide, not 07:00 AM
        el.textContent = d.toLocaleTimeString(document.documentElement.lang === 'vi' ? 'vi-VN' : [], { hour: '2-digit', minute: '2-digit' });
    });

    // Search, in the page's language: /search-index.json or /vi/search-index.json
    const search = $('#search');
    const base = document.documentElement.dataset.base || '/';
    const input = $('#search-input');
    const list = $('#search-results');
    let index = null;
    let results = [];
    let selected = 0;
    const loadIndex = () => index || (index = fetch(`${base}search-index.json`).then((r) => r.json()).catch(() => []));
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
    // Lower case without accents, one character for one ("tốc độ" finds "toc do"),
    // so positions in the folded text are positions in the original
    const fold = (s) => s.toLowerCase().replace(/[^\x00-\x7f]/g, (c) => (c === 'đ' ? 'd' : c.normalize('NFD').replace(/\p{M}/gu, '')) || c);
    const mark = (s, words) => {
        const f = fold(s);
        const hit = new Array(s.length).fill(false);
        for (const w of words) for (let i = f.indexOf(w); i >= 0; i = f.indexOf(w, i + 1)) hit.fill(true, i, i + w.length);
        let out = '';
        for (let i = 0; i < s.length; i++) {
            if (hit[i] && !hit[i - 1]) out += '<mark>';
            out += esc(s[i]);
            if (hit[i] && !hit[i + 1]) out += '</mark>';
        }
        return out;
    };

    function snippet(text, words) {
        const lower = fold(text);
        const at = Math.max(0, Math.min(...words.map((w) => { const i = lower.indexOf(w); return i < 0 ? Infinity : i; })));
        if (!isFinite(at)) return text.slice(0, 120) + '…';
        const start = Math.max(0, at - 50);
        return (start ? '…' : '') + text.slice(start, start + 140) + '…';
    }

    function render(query) {
        const words = fold(query).split(/\s+/).filter(Boolean);
        if (!words.length) {
            results = [];
            const q = T.tryWords.map((w) => `<button class="text-brand underline" data-q="${w}">${w}</button>`);
            list.innerHTML = `<li class="px-3 py-6 text-center text-sm text-gray-500">${T.try} ${q.slice(0, -1).join(', ')} ${T.or} ${q[q.length - 1]}.</li>`;
            $$('[data-q]', list).forEach((b) => b.addEventListener('click', () => { input.value = b.dataset.q; input.dispatchEvent(new Event('input')); input.focus(); }));
            return;
        }
        Promise.resolve(loadIndex()).then((pages) => {
            results = [];
            for (const p of pages) {
                const title = fold(p.title);
                const body = fold(p.description + ' ' + p.text);
                if (!words.every((w) => title.includes(w) || body.includes(w) || p.headings.some((h) => fold(h.text).includes(w)))) continue;
                let score = words.reduce((s, w) => s + (title.includes(w) ? 10 : 0) + (body.split(w).length - 1), 0);
                // a page named after the search comes first ("phát âm" → Kiểm tra phát âm, not the FAQ)
                if (words.every((w) => title.includes(w))) score += 100;
                // Link to the section that matches best: heading text counts most
                let heading = null;
                let best = 0;
                for (const h of p.headings) {
                    const t = fold(h.text);
                    const s = fold(h.body || '');
                    const hs = words.reduce((n, w) => n + (t.includes(w) ? 20 : 0) + (s.split(w).length - 1), 0);
                    if (hs > best) { best = hs; heading = h; }
                }
                if (heading) {
                    const t = fold(heading.text);
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
                        <a href="${base}${r.p.url}${r.heading ? '#' + r.heading.id : ''}" class="search-hit">
                            <span class="text-xs uppercase tracking-wide text-gray-400">${r.p.icon || ''} ${esc(r.p.group)}</span>
                            <span class="block font-semibold text-ink dark:text-white">${mark(r.p.title, words)}${r.heading ? ` <span class="font-normal text-gray-500">› ${mark(r.heading.text, words)}</span>` : ''}</span>
                            <span class="mt-0.5 block text-sm text-gray-500">${mark(snippet(r.heading?.body || r.p.text, words), words)}</span>
                        </a>
                    </li>`).join('')
                : `<li class="px-3 py-6 text-center text-sm text-gray-500">${T.none(esc(query))}</li>`;
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
            const words = fold(filter.value).split(/\s+/).filter(Boolean);
            let shown = 0;
            items.forEach((d) => {
                const hit = words.every((w) => fold(d.textContent).includes(w));
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
