/* #/audit/:id — full audit detail with categories, checks accordion, recommendations */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.audit = async function (main, params) {
    const U = WVA.ui;
    main.innerHTML = U.loading('Loading audit…');

    const audit = await WVA.api.get(`/api/audits/${params.id}`);
    if (audit.status === 'running') {
        renderRunningAudit(main, audit);
        return;
    }
    renderAudit(main, audit);
};

function renderRunningAudit(main, audit) {
    const U = WVA.ui;
    const biz = audit.business || {};
    main.innerHTML = `
        ${U.pageHead({
            title: biz.name || 'Audit',
            sub: audit.website_url || '',
            back: biz.id ? { href: `#/business/${biz.id}`, label: 'Back to Business' } : { href: '#/businesses', label: 'Back to Businesses' },
        })}
        <div class="card" style="max-width:640px;margin:24px auto;text-align:center;padding:40px 24px;">
            <div class="spinner" style="margin:0 auto 16px;"></div>
            <h2 style="margin:0 0 8px;">Analyzing ${U.esc(audit.website_url || 'this site')}…</h2>
            <p class="muted" style="margin:0;">Scoring 7 categories including SEO, performance, and AI readiness.<br>This can take up to 2 minutes on some sites — this page will update automatically.</p>
        </div>`;

    WVA.api.pollAudit(audit.id).then((finished) => {
        // Guard against the user having navigated away while we were polling.
        if (!document.body.contains(main)) return;
        if (window.location.hash !== `#/audit/${audit.id}`) return;
        renderAudit(main, finished);
    }).catch((err) => {
        if (!document.body.contains(main)) return;
        U.toast(err.message || 'Something went wrong while checking on this audit.', 'error');
    });
}

function renderAudit(main, audit) {
    const U = WVA.ui;
    const biz = audit.business || {};

    if (audit.status === 'failed') {
        renderFailedAudit(main, audit, biz);
        return;
    }

    /* Group checks by category, following the categories array order */
    const checksByCat = {};
    (audit.checks || []).forEach((c) => {
        (checksByCat[c.category_key] = checksByCat[c.category_key] || []).push(c);
    });

    const catNameByKey = {};
    (audit.categories || []).forEach((c) => { catNameByKey[c.category_key] = c.category_name; });

    const accordion = (audit.categories || []).map((cat, idx) => {
        const checks = checksByCat[cat.category_key] || [];
        const summary = [
            cat.issues_count ? `${cat.issues_count} issue${cat.issues_count === 1 ? '' : 's'}` : '',
            cat.warnings_count ? `${cat.warnings_count} warning${cat.warnings_count === 1 ? '' : 's'}` : '',
            cat.passed_count ? `${cat.passed_count} passed` : '',
        ].filter(Boolean).join(' · ');
        return `<div class="acc" id="acc-${U.esc(cat.category_key)}">
            <button class="acc-head" aria-expanded="false" aria-controls="acc-body-${idx}">
                <span class="acc-score tabular" style="font-weight:800;font-size:16px;color:${U.gradeColor(cat.grade)}">${U.esc(U.fmtScore(cat.score))}</span>
                ${U.gradeBadge(cat.grade, 'sm')}
                <span class="acc-name">${U.esc(cat.category_name)}</span>
                <span class="muted text-sm tabular">${U.esc(summary)}</span>
                <span class="chev"><span data-icon="chevron-down" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="6 9 12 15 18 9"/></svg></span></span>
            </button>
            <div class="acc-body" id="acc-body-${idx}">
                <div class="acc-body-inner">${U.checksList(checks)}</div>
            </div>
        </div>`;
    }).join('');

    const shareMenu = `
        <div class="menu-wrap">
            <button class="btn btn-secondary" id="share-btn" aria-haspopup="true" aria-expanded="false">
                <span data-icon="share" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg></span>Copy Share Link
            </button>
            <div class="menu hidden" id="share-menu" role="menu">
                <button type="button" role="menuitem" data-mode="prospect">
                    <span data-icon="eye" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></span>
                    <span>Prospect Snapshot<span class="menu-desc">Teaser report for leads</span></span>
                </button>
                <button type="button" role="menuitem" data-mode="full">
                    <span data-icon="file-text" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg></span>
                    <span>Full Report<span class="menu-desc">Complete detailed report</span></span>
                </button>
            </div>
        </div>`;

    main.innerHTML = `
        ${U.pageHead({
            title: 'Audit Result',
            back: { href: `#/business/${U.esc(biz.id || '')}`, label: 'Back to business' },
        })}
        <section class="card hero-card card-pad">
            <div class="hero-main">
                ${U.scoreRing(audit.overall_score, audit.overall_grade, 150)}
                <div class="hero-info">
                    <div class="hero-badges">
                        ${audit.is_demo_data ? U.demoBadge() : ''}
                        <span class="badge fg-x"><span data-icon="calendar" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg></span>${U.esc(U.fmtDateTime(audit.created_at))}</span>
                    </div>
                    <h1>${U.esc(biz.name || 'Website Audit')}</h1>
                    <a class="hero-url" href="${U.esc(audit.website_url)}" target="_blank" rel="noopener">
                        <span data-icon="globe" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg></span>
                        ${U.esc(audit.website_url)}
                        <span data-icon="external-link" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg></span>
                    </a>
                    <div class="hero-chips">
                        ${biz.location ? U.chip('map-pin', biz.location) : ''}
                        ${biz.category ? U.chip('tag', biz.category) : ''}
                        ${U.chip('shield', 'Grade ' + audit.overall_grade)}
                    </div>
                </div>
            </div>
            <div class="hero-actions no-print">
                <a class="btn btn-primary" href="#/report/${U.esc(audit.id)}/full">
                    <span data-icon="file-text" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg></span>View Full Report
                </a>
                <a class="btn btn-secondary" href="#/report/${U.esc(audit.id)}/prospect">
                    <span data-icon="eye" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg></span>View Prospect Snapshot
                </a>
                <span style="flex:1"></span>
                ${shareMenu}
            </div>
        </section>

        <div class="section-label">${U.icon('bar-chart')}Category Score Dashboard</div>
        ${U.categoryCards(audit.categories)}

        <div class="section-label">${U.icon('alert-triangle')}Highest Priority Issues <span class="count-pill">Top 5</span></div>
        ${U.topIssues(audit.recommendations, 5)}

        <div class="section-label">${U.icon('search')}All Checks by Category <span class="count-pill">${(audit.checks || []).length}</span></div>
        <div id="checks-accordion">${accordion}</div>

        <div class="section-label">${U.icon('zap')}Prioritized Recommendations <span class="count-pill">${(audit.recommendations || []).length}</span></div>
        <div id="recs">${U.recommendationCards(audit.recommendations)}</div>`;

    /* Accordion behavior */
    main.querySelectorAll('.acc-head').forEach((btn) => {
        btn.addEventListener('click', () => {
            const acc = btn.closest('.acc');
            const open = acc.classList.toggle('open');
            btn.setAttribute('aria-expanded', String(open));
        });
    });

    /* Category cards jump to their accordion section */
    main.querySelectorAll('.cat-card').forEach((card) => {
        card.style.cursor = 'pointer';
        card.setAttribute('role', 'button');
        card.setAttribute('tabindex', '0');
        card.setAttribute('aria-label', 'Jump to checks for this category');
        card.addEventListener('click', () => {
            const acc = main.querySelector(`#acc-${card.dataset.cat}`);
            if (!acc) return;
            const head = acc.querySelector('.acc-head');
            if (!acc.classList.contains('open')) head.click();
            acc.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
        card.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); card.click(); } });
    });

    /* Share dropdown */
    const shareBtn = main.querySelector('#share-btn');
    const shareMenuEl = main.querySelector('#share-menu');
    shareBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        shareMenuEl.classList.toggle('hidden');
        shareBtn.setAttribute('aria-expanded', String(!shareMenuEl.classList.contains('hidden')));
    });
    U.onDoc((e) => {
        if (!shareMenuEl.classList.contains('hidden') && !shareMenuEl.contains(e.target) && e.target !== shareBtn) {
            shareMenuEl.classList.add('hidden');
            shareBtn.setAttribute('aria-expanded', 'false');
        }
    });
    shareMenuEl.querySelectorAll('button[data-mode]').forEach((b) => {
        b.addEventListener('click', async () => {
            shareMenuEl.classList.add('hidden');
            const mode = b.dataset.mode;
            try {
                const rep = await WVA.api.post(`/api/audits/${audit.id}/reports`, { mode });
                const url = `${window.location.origin}/#/share/${rep.share_token}`;
                const ok = await U.copyText(url);
                if (ok) U.toast(`${mode === 'full' ? 'Full report' : 'Prospect snapshot'} link copied to clipboard.`, 'success');
                else U.toast(`Share link: ${url}`, 'info');
            } catch (err) {
                U.toast(err.message || 'Could not create share link.', 'error');
            }
        });
    });
}

function renderFailedAudit(main, audit, biz) {
    const U = WVA.ui;
    main.innerHTML = `
        ${U.pageHead({
            title: biz.name || 'Audit',
            sub: audit.website_url || '',
            back: biz.id ? { href: `#/business/${biz.id}`, label: 'Back to Business' } : { href: '#/businesses', label: 'Back to Businesses' },
        })}
        <div class="card" style="max-width:640px;margin:24px auto;text-align:center;padding:32px 24px;">
            <div style="font-size:40px;line-height:1;margin-bottom:8px;">⚠️</div>
            <h2 style="margin:0 0 8px;">We couldn't complete this audit</h2>
            <p class="muted" style="margin:0 0 4px;">${U.esc(audit.website_url || '')}</p>
            <p style="margin:16px 0;">${U.esc(audit.error_message || 'The website could not be reached.')}</p>
            <p class="muted text-sm">This isn't a fabricated or partial result — when a site can't be reached at all, we don't generate a score.</p>
            <div style="margin-top:20px;display:flex;gap:8px;justify-content:center;">
                <button class="btn btn-primary" id="retry-audit-btn" data-website="${U.esc(audit.website_id)}">Try Again</button>
                ${biz.id ? `<a class="btn btn-secondary" href="#/business/${U.esc(biz.id)}">Back to Business</a>` : ''}
            </div>
        </div>`;

    const retryBtn = main.querySelector('#retry-audit-btn');
    if (retryBtn) {
        retryBtn.addEventListener('click', async () => {
            retryBtn.disabled = true;
            retryBtn.textContent = 'Retrying…';
            try {
                const newAudit = await WVA.api.post(`/api/websites/${retryBtn.dataset.website}/audits/rerun`);
                window.location.hash = `#/audit/${newAudit.id}`;
                window.location.reload();
            } catch (err) {
                U.toast(err.message || 'Retry failed.', 'error');
                retryBtn.disabled = false;
                retryBtn.textContent = 'Try Again';
            }
        });
    }
}