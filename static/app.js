/* Hash router + global chrome wiring. Views are registered by the files
   loaded before this one (window.WVA.views.*). */
(function () {
    const U = WVA.ui;

    const ROUTES = [
        { re: /^\/$/, view: 'dashboard', nav: 'dashboard' },
        { re: /^\/dashboard$/, view: 'dashboard', nav: 'dashboard' },
        { re: /^\/create-audit$/, view: 'createAudit', nav: 'create-audit' },
        { re: /^\/ghl-leads$/, view: 'ghlLeads', nav: 'ghl-leads' },
        { re: /^\/bulk-scoring$/, view: 'bulkScoring', nav: 'bulk-scoring' },
        { re: /^\/local-visibility$/, view: 'localVisibility', nav: 'local-visibility' },
        { re: /^\/local-visibility\/ghl-leads$/, view: 'localVisibilityGhlLeads', nav: 'local-visibility-ghl-leads' },
        { re: /^\/local-visibility\/bulk-scoring$/, view: 'localVisibilityBulk', nav: 'local-visibility-bulk-scoring' },
        { re: /^\/local-visibility\/manual$/, view: 'localVisibilityManual', nav: 'local-visibility-manual' },
        { re: /^\/business\/([A-Za-z0-9-]+)$/, view: 'business', nav: 'dashboard', params: (m) => ({ id: m[1] }) },
        { re: /^\/audit\/([A-Za-z0-9-]+)$/, view: 'audit', nav: 'dashboard', params: (m) => ({ id: m[1] }) },
        { re: /^\/report\/([A-Za-z0-9-]+)\/(full|prospect)$/, view: 'report', nav: 'dashboard', params: (m) => ({ id: m[1], mode: m[2] }) },
        { re: /^\/share\/([A-Za-z0-9-]+)$/, view: 'share', nav: null, public: true, params: (m) => ({ token: m[1] }) },
        { re: /^\/settings(?:\/(branding|scoring|embed))?$/, view: 'settings', nav: 'settings', params: (m) => ({ tab: m[1] || 'branding' }) },
    ];

    let renderSeq = 0;
    let chain = Promise.resolve();

    function currentPath() {
        const h = window.location.hash || '';
        const path = h.replace(/^#/, '');
        return path === '' ? '/dashboard' : path;
    }

    /* Serialize route renders so a slow earlier view can never clobber a
       newer route's DOM (rapid hash navigation race). */
    function render() {
        const seq = ++renderSeq;
        chain = chain.then(() => doRender(seq)).catch((e) => console.error('Render error:', e));
        return chain;
    }

    async function doRender(seq) {
        if (seq !== renderSeq) return; // superseded by a newer navigation
        U.clearTimers();
        U.clearDocHandlers();
        U.destroyCharts();
        document.body.classList.remove('nav-open');

        const path = currentPath();
        const main = document.getElementById('main');

        let matched = null;
        let match = null;
        for (const r of ROUTES) {
            const m = path.match(r.re);
            if (m) { matched = r; match = m; break; }
        }

        /* Nav active state */
        document.querySelectorAll('.nav-item[data-nav]').forEach((el) => {
            const on = matched && matched.nav === el.dataset.nav;
            el.classList.toggle('active', !!on);
            if (on) el.setAttribute('aria-current', 'page');
            else el.removeAttribute('aria-current');
        });

        /* Public share view: hide app chrome */
        document.body.classList.toggle('public', !!(matched && matched.public));
        closeMobileNav();

        window.scrollTo(0, 0);

        if (!matched) {
            main.innerHTML = U.notFound('This page does not exist. Check the link or head back to the dashboard.');
            return;
        }

        main.innerHTML = '';
        try {
            await WVA.views[matched.view](main, matched.params ? matched.params(match) : {});
            if (seq === renderSeq) U.hydrateIcons(document);
        } catch (err) {
            if (seq !== renderSeq) return;
            console.error('View error:', err);
            main.innerHTML = U.errorState(err);
        }
    }

    /* ---------- Mobile nav ---------- */
    function closeMobileNav() {
        document.body.classList.remove('nav-open');
        const btn = document.getElementById('navToggle');
        const scrim = document.getElementById('scrim');
        if (btn) btn.setAttribute('aria-expanded', 'false');
        if (scrim) scrim.hidden = true;
    }

    function initNav() {
        const btn = document.getElementById('navToggle');
        const scrim = document.getElementById('scrim');
        if (btn) {
            btn.addEventListener('click', () => {
                const open = document.body.classList.toggle('nav-open');
                btn.setAttribute('aria-expanded', String(open));
                if (scrim) scrim.hidden = !open;
            });
        }
        if (scrim) scrim.addEventListener('click', closeMobileNav);
        document.querySelectorAll('.nav-item[href]').forEach((el) => {
            el.addEventListener('click', closeMobileNav);
        });
    }

    initNav();
    U.hydrateIcons(document);
    window.addEventListener('hashchange', render);
    render();
})();