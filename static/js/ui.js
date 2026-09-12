/* UI toolkit: icons, badges, score rings, toasts, states, charts, shared builders. */
window.WVA = window.WVA || {};

WVA.ui = (function () {
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));

    /* ---------- Icons (Feather-style, stroke-based) ---------- */
    const ICON_PATHS = {
        dashboard: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/>',
        plus: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>',
        settings: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
        'map-pin': '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
        tag: '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.83z"/><line x1="7" y1="7" x2="7.01" y2="7"/>',
        globe: '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
        zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
        search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
        link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
        message: '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
        'file-text': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>',
        'bar-chart': '<line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>',
        eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
        printer: '<polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
        'arrow-left': '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
        'arrow-right': '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
        check: '<polyline points="20 6 9 17 4 12"/>',
        'alert-triangle': '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
        'alert-circle': '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
        x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
        copy: '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
        refresh: '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
        edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>',
        mail: '<path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/>',
        phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
        calendar: '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
        info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
        'trending-up': '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
        clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
        share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>',
        menu: '<line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>',
        'chevron-down': '<polyline points="6 9 12 15 18 9"/>',
        'external-link': '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
        shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
        flask: '<path d="M9 3h6"/><path d="M10 3v6L4.8 17.7A2 2 0 0 0 6.5 21h11a2 2 0 0 0 1.7-3.3L14 9V3"/><line x1="7.5" y1="15" x2="16.5" y2="15"/>',
        inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
        slash: '<circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>',
    };

    function icon(name, cls) {
        const p = ICON_PATHS[name] || ICON_PATHS.info;
        return `<span class="${cls || ''}" data-icon="${name}" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${p}</svg></span>`;
    }

    /* Replace <span data-icon="..."> placeholders (used for static nav markup) */
    function hydrateIcons(root) {
        (root || document).querySelectorAll('[data-icon]').forEach((el) => {
            const name = el.getAttribute('data-icon');
            if (!el.firstChild && ICON_PATHS[name]) {
                el.innerHTML = `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS[name]}</svg>`;
            }
        });
    }

    /* ---------- Formatting ---------- */
    function fmtScore(n) {
        if (n === null || n === undefined || isNaN(Number(n))) return '—';
        const v = Number(n);
        return Number.isInteger(v) ? String(v) : String(Math.round(v * 10) / 10);
    }
    function fmtDate(iso) {
        if (!iso) return '—';
        const d = new Date(iso);
        if (isNaN(d)) return '—';
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }
    function fmtDateTime(iso) {
        if (!iso) return '—';
        const d = new Date(iso);
        if (isNaN(d)) return '—';
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) +
            ' · ' + d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    }

    /* ---------- Grades ---------- */
    const GRADE_THRESHOLDS = [
        [97, 'A+'], [93, 'A'], [90, 'A-'], [87, 'B+'], [83, 'B'], [80, 'B-'],
        [77, 'C+'], [73, 'C'], [70, 'C-'], [67, 'D+'], [63, 'D'], [60, 'D-'], [0, 'F'],
    ];
    function gradeForScore(score) {
        const s = Number(score) || 0;
        for (const [min, g] of GRADE_THRESHOLDS) if (s >= min) return g;
        return 'F';
    }
    function gradeFamily(grade) {
        if (!grade) return 'x';
        const ch = String(grade)[0].toUpperCase();
        return ['A', 'B', 'C', 'D', 'F'].includes(ch) ? ch : 'x';
    }
    const GRADE_HEX = { A: '#16a34a', B: '#0d9488', C: '#d97706', D: '#ea580c', F: '#dc2626', x: '#64748b' };
    const GRADE_TEXT = { A: 'var(--g-a)', B: 'var(--g-b)', C: 'var(--g-c)', D: 'var(--g-d)', F: 'var(--g-f)' };
    function gradeColor(grade) {
        return GRADE_TEXT[gradeFamily(grade)] || GRADE_TEXT.x;
    }
    function gradeColorHex(grade) {
        return GRADE_HEX[gradeFamily(grade)] || GRADE_HEX.x;
    }
    function gradeBadge(grade, size) {
        const fam = gradeFamily(grade);
        const sz = size === 'lg' ? 'badge-lg' : size === 'sm' ? 'badge-sm' : '';
        return `<span class="badge ${sz} fg-${fam}" title="Grade ${esc(grade)}">${esc(grade || 'N/A')}</span>`;
    }

    /* ---------- Status badges ---------- */
    const STATUS_LABELS = {
        PASS: 'Pass', WARNING: 'Warning', FAIL: 'Fail',
        NOT_DETECTED: 'Not detected', NOT_APPLICABLE: 'N/A',
    };
    const STATUS_ICONS = { PASS: 'check', WARNING: 'alert-triangle', FAIL: 'x', NOT_DETECTED: 'info', NOT_APPLICABLE: 'slash' };
    function statusBadge(status, size) {
        const s = String(status || '');
        const label = STATUS_LABELS[s] || s;
        const fam = { PASS: 'fg-a', WARNING: 'fg-c', FAIL: 'fg-f', NOT_DETECTED: 'fg-x', NOT_APPLICABLE: 'fg-x' }[s] || 'fg-x';
        const sz = size === 'sm' ? 'badge-sm' : '';
        const ico = STATUS_ICONS[s];
        return `<span class="badge ${fam} ${sz}"><span data-icon="${ico}" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS[ico]}</svg></span>${esc(label)}</span>`;
    }

    const CAT_STATUS_FAM = { 'Excellent': 'fg-a', 'Good': 'fg-b', 'Needs Attention': 'fg-c', 'Critical Issues': 'fg-f' };
    function catStatusBadge(label) {
        const fam = CAT_STATUS_FAM[label] || 'fg-x';
        return `<span class="badge badge-sm cat-status ${fam}">${esc(label || '—')}</span>`;
    }

    function priorityBadge(priority, size) {
        const p = String(priority || '');
        const fam = { CRITICAL: 'pr-CRITICAL', HIGH: 'pr-HIGH', MEDIUM: 'pr-MEDIUM', LOW: 'pr-LOW' }[p] || 'fg-x';
        const sz = size === 'lg' ? 'badge-lg' : 'badge-sm';
        return `<span class="badge ${fam} ${sz}">${esc(p || '—')}</span>`;
    }

    function demoBadge(extraCls) {
        return `<span class="badge badge-demo ${extraCls || ''}" title="This audit uses Phase-1 sample/demo data, not a live crawl">${flaskIcon()}Demo Data</span>`;
    }
    function flaskIcon() {
        return `<span data-icon="flask" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS.flask}</svg></span>`;
    }

    function chip(ico, text) {
        return `<span class="chip">${ico ? `<span data-icon="${ico}" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS[ico] || ''}</svg></span>` : ''}${esc(text)}</span>`;
    }

    /* ---------- Score ring ---------- */
    function scoreRing(score, grade, size, opts) {
        size = size || 120;
        opts = opts || {};
        const stroke = opts.stroke || Math.max(7, Math.round(size * 0.072));
        const r = (size - stroke) / 2;
        const circ = 2 * Math.PI * r;
        const pct = Math.max(0, Math.min(100, Number(score) || 0)) / 100;
        const col = opts.color || gradeColorHex(grade);
        const num = fmtScore(score);
        const numSize = Math.round(size * (opts.numScale || 0.30));
        const subSize = Math.max(9, Math.round(size * 0.095));
        const cy = size / 2;
        // Below a certain ring size there simply isn't enough vertical room
        // for both the score number and a "/ 100" caption without them
        // colliding -- small rings (dashboard tiles, category cards) show
        // just the number. Larger rings (report hero, audit detail) show both.
        const showSub = size >= 100;
        // Position the subtext relative to the *actual* half-height of the
        // main number (approximated from its font-size) plus a fixed gap,
        // rather than a flat fraction of the ring size -- the previous
        // fixed-fraction offset put the subtext too close to the number at
        // most size/numScale combinations, causing visible overlap.
        const numHalf = numSize * 0.38;
        const subHalf = subSize * 0.38;
        const subY = cy + numHalf + 3 + subHalf;
        const label = `Overall score ${score} out of 100, grade ${grade || 'N/A'}`;
        return `<svg class="score-ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="${esc(label)}">
            <circle class="ring-track" cx="${cy}" cy="${cy}" r="${r}" fill="none" stroke-width="${stroke}"/>
            <circle cx="${cy}" cy="${cy}" r="${r}" fill="none" stroke="${col}" stroke-width="${stroke}" stroke-linecap="round"
                stroke-dasharray="${circ.toFixed(2)}" stroke-dashoffset="${(circ * (1 - pct)).toFixed(2)}"
                transform="rotate(-90 ${cy} ${cy})"/>
            <text x="50%" y="${showSub ? cy - (subHalf + 3) / 2 : cy}" class="ring-num" font-size="${numSize}" dominant-baseline="central" text-anchor="middle" dy=".05em">${esc(num)}</text>
            ${showSub ? `<text x="50%" y="${subY}" class="ring-sub" font-size="${subSize}" dominant-baseline="central" text-anchor="middle">/ 100</text>` : ''}
        </svg>`;
    }

    /* ---------- Toast ---------- */
    function toast(msg, type) {
        type = type || 'info';
        const root = document.getElementById('toast-root');
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        const ico = type === 'success' ? 'check' : type === 'error' ? 'alert-circle' : 'info';
        el.innerHTML = `<span data-icon="${ico}" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS[ico]}</svg></span><span>${esc(msg)}</span>`;
        root.appendChild(el);
        setTimeout(() => {
            el.classList.add('leaving');
            setTimeout(() => el.remove(), 220);
        }, 3600);
    }

    async function copyText(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (e) {
            try {
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.style.cssText = 'position:fixed;opacity:0;';
                document.body.appendChild(ta);
                ta.select();
                const ok = document.execCommand('copy');
                ta.remove();
                return ok;
            } catch (e2) { return false; }
        }
    }

    /* ---------- Timers (cleared on route change) ---------- */
    const timers = new Set();
    function after(ms, fn) {
        const t = setTimeout(() => { timers.delete(t); fn(); }, ms);
        timers.add(t);
        return t;
    }
    function clearTimers() {
        timers.forEach(clearTimeout);
        timers.clear();
    }

    /* ---------- Document-level handlers (removed on route change) ---------- */
    const docHandlers = new Set();
    function onDoc(fn) {
        document.addEventListener(fn.wvaType || 'click', fn);
        docHandlers.add(fn);
    }
    function clearDocHandlers() {
        docHandlers.forEach((fn) => {
            try { document.removeEventListener(fn.wvaType || 'click', fn); } catch (e) { /* noop */ }
        });
        docHandlers.clear();
    }

    /* ---------- Charts ---------- */
    const charts = {};
    function renderChart(canvasId, config) {
        if (!window.Chart) return;
        const el = document.getElementById(canvasId);
        if (!el) return;
        if (charts[canvasId]) { try { charts[canvasId].destroy(); } catch (e) { /* noop */ } }
        Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
        Chart.defaults.color = '#8a94a6';
        charts[canvasId] = new Chart(el, config);
    }
    function destroyCharts() {
        Object.keys(charts).forEach((k) => {
            try { charts[k].destroy(); } catch (e) { /* noop */ }
            delete charts[k];
        });
    }

    /* ---------- States ---------- */
    function pageHead(opts) {
        const back = opts.back
            ? `<a class="back-link" href="${esc(opts.back.href)}"><span data-icon="arrow-left" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS['arrow-left']}</svg></span>${esc(opts.back.label)}</a>`
            : '';
        return `<div class="page-head">${back}
            <div class="page-head-row">
                <div>
                    <h1>${esc(opts.title)}</h1>
                    ${opts.sub ? `<p class="page-sub">${esc(opts.sub)}</p>` : ''}
                </div>
                ${opts.actions ? `<div class="page-actions">${opts.actions}</div>` : ''}
            </div>
        </div>`;
    }

    function loading(msg) {
        return `<div class="loading-block"><div class="spinner"></div>${esc(msg || 'Loading…')}</div>`;
    }

    function errorState(err, retryHash) {
        const msg = (err && err.message) || 'Something went wrong.';
        return `<div class="card state-card state">
            <div class="state-ico"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS['alert-circle']}</svg></div>
            <div class="state-title">Couldn't load this page</div>
            <div class="state-body">${esc(msg)}</div>
            <a class="btn btn-secondary" href="${esc(retryHash || '#/dashboard')}"><span data-icon="arrow-left" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS['arrow-left']}</svg></span>Back to Dashboard</a>
        </div>`;
    }

    function emptyState(opts) {
        return `<div class="card state-card state">
            <div class="state-ico"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS[opts.icon || 'inbox']}</svg></div>
            <div class="state-title">${esc(opts.title)}</div>
            ${opts.body ? `<div class="state-body">${esc(opts.body)}</div>` : ''}
            ${opts.cta ? `<a class="btn btn-primary" href="${esc(opts.cta.href)}">${opts.cta.label}</a>` : ''}
        </div>`;
    }

    function notFound(msg) {
        return emptyState({ icon: 'search', title: 'Not found', body: msg || 'The page you requested does not exist.', cta: { href: '#/dashboard', label: 'Back to Dashboard' } });
    }

    /* ==================================================================
       Shared section builders (used by audit detail + full report)
       ================================================================== */

    function categoryCards(categories) {
        return `<div class="cat-grid">${(categories || []).map((c) => {
            const counts = [];
            if (c.issues_count) counts.push(`<span class="cnt-fail"><span data-icon="x" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS.x}</svg></span>${c.issues_count} issue${c.issues_count === 1 ? '' : 's'}</span>`);
            if (c.warnings_count) counts.push(`<span class="cnt-warn"><span data-icon="alert-triangle" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS['alert-triangle']}</svg></span>${c.warnings_count} warning${c.warnings_count === 1 ? '' : 's'}</span>`);
            if (c.passed_count) counts.push(`<span class="cnt-pass"><span data-icon="check" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS.check}</svg></span>${c.passed_count} passed</span>`);
            return `<div class="card cat-card" data-cat="${esc(c.category_key)}">
                <div class="cat-card-top">${scoreRing(c.score, c.grade, 64, { stroke: 6, numScale: 0.32 })}
                    <div class="cat-card-name">${esc(c.category_name)}</div>
                </div>
                <div class="cat-card-mid">${catStatusBadge(c.status)}${gradeBadge(c.grade, 'sm')}</div>
                ${counts.length ? `<div class="cat-counts">${counts.join('')}</div>` : '<div class="cat-counts muted text-sm">No checks recorded</div>'}
            </div>`;
        }).join('')}</div>`;
    }

    function topIssues(recommendations, limit) {
        const items = (recommendations || []).slice(0, limit || 5);
        if (!items.length) {
            return `<div class="card"><div class="card-pad muted text-sm">No priority issues identified — nice work.</div></div>`;
        }
        return `<div class="card top-issues">${items.map((r, i) => `
            <div class="issue-row">
                <span class="issue-rank">${i + 1}</span>
                <div class="issue-body">
                    <div class="issue-title">${priorityBadge(r.priority)}${esc(r.title)} <span class="rec-cat">· ${esc(r.category_name)}</span></div>
                    <div class="issue-found line-clamp-1">${esc(r.what_found)}</div>
                </div>
            </div>`).join('')}</div>`;
    }

    function recommendationCards(recs) {
        if (!(recs || []).length) {
            return `<div class="card"><div class="card-pad muted text-sm">No recommendations for this audit.</div></div>`;
        }
        return recs.map((r) => `
            <div class="card rec-card">
                <div class="rec-head">
                    ${priorityBadge(r.priority, 'lg')}
                    <span class="rec-cat">${esc(r.category_name)}</span>
                </div>
                <h3 class="rec-title">${esc(r.title)}</h3>
                <div class="rec-grid">
                    <div class="rec-cell">
                        <div class="cell-label"><span data-icon="search" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS.search}</svg></span>What we found</div>
                        <p>${esc(r.what_found)}</p>
                    </div>
                    <div class="rec-cell">
                        <div class="cell-label"><span data-icon="info" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS.info}</svg></span>Why it matters</div>
                        <p>${esc(r.why_matters)}</p>
                    </div>
                    <div class="rec-cell action">
                        <div class="cell-label"><span data-icon="check" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS.check}</svg></span>Recommended action</div>
                        <p>${esc(r.recommended_action)}</p>
                    </div>
                </div>
                <div class="rec-meta">
                    ${chip('trending-up', `Impact: ${r.estimated_impact || '—'}`)}
                    ${chip('clock', `Effort: ${r.estimated_effort || '—'}`)}
                    ${chip('shield', `Difficulty: ${r.technical_difficulty || '—'}`)}
                </div>
            </div>`).join('');
    }

    function checkRow(c) {
        const vals = [];
        if (c.raw_value !== null && c.raw_value !== undefined && String(c.raw_value).trim() !== '') {
            vals.push(`<div class="check-val"><span class="check-val-label">Value found</span><code>${esc(c.raw_value)}</code></div>`);
        }
        if (c.expected_value !== null && c.expected_value !== undefined && String(c.expected_value).trim() !== '') {
            vals.push(`<div class="check-val"><span class="check-val-label">Expected</span><code>${esc(c.expected_value)}</code></div>`);
        }
        return `<div class="check-row">
            <div>${statusBadge(c.status)}</div>
            <div class="check-main">
                <div class="check-name">${esc(c.check_name)}</div>
                <div class="check-result">${esc(c.result)}</div>
                ${vals.length ? `<div class="check-vals">${vals.join('')}</div>` : ''}
                ${c.business_explanation ? `<div class="check-explain"><span data-icon="info" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">${ICON_PATHS.info}</svg></span><span>${esc(c.business_explanation)}</span></div>` : ''}
            </div>
        </div>`;
    }

    function checksList(checks) {
        if (!(checks || []).length) return `<div class="card-pad muted text-sm">No checks recorded for this category.</div>`;
        return checks.map(checkRow).join('');
    }

    return {
        esc, icon, hydrateIcons,
        fmtScore, fmtDate, fmtDateTime,
        gradeForScore, gradeFamily, gradeColor, gradeColorHex, gradeBadge,
        statusBadge, catStatusBadge, priorityBadge, demoBadge, chip,
        scoreRing, toast, copyText,
        after, clearTimers, onDoc, clearDocHandlers,
        renderChart, destroyCharts,
        pageHead, loading, errorState, emptyState, notFound,
        categoryCards, topIssues, recommendationCards, checkRow, checksList,
    };
})();