/* #/report/:id/:mode and #/share/:token — full report, prospect snapshot, public share */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

/* ---------- #/report/:id/full | #/report/:id/prospect ---------- */
WVA.views.report = async function (main, params) {
    const U = WVA.ui;
    main.innerHTML = U.loading('Building report…');
    try {
        const data = await WVA.api.get(`/api/audits/${params.id}/report?mode=${params.mode}`);
        if (params.mode === 'prospect') renderProspectReport(main, data, { internal: true });
        else renderFullReport(main, data, { internal: true });
    } catch (err) {
        main.innerHTML = U.errorState(err);
    }
};

/* ---------- #/share/:token ---------- */
WVA.views.share = async function (main, params) {
    const U = WVA.ui;
    main.innerHTML = U.loading('Opening shared report…');
    try {
        const data = await WVA.api.get(`/api/reports/${params.token}`);
        if (data.mode === 'prospect') renderProspectReport(main, data, { internal: false });
        else renderFullReport(main, data, { internal: false });
    } catch (err) {
        main.innerHTML = U.emptyState({
            icon: 'search',
            title: 'Report not available',
            body: 'This share link is invalid or has been removed. Ask Netclix Marketing for a fresh link.',
            cta: { href: '#/dashboard', label: 'Go to Dashboard' },
        });
    }
};

/* ==================================================================
   FULL REPORT
   ================================================================== */
function renderFullReport(main, data, opts) {
    const U = WVA.ui;
    const b = data.business || {};
    const branding = data.branding || {};
    const cats = data.categories || [];
    const recs = data.recommendations || [];
    const checksByCat = {};
    (data.checks || []).forEach((c) => {
        (checksByCat[c.category_key] = checksByCat[c.category_key] || []).push(c);
    });

    const toolbar = `
        <div class="report-toolbar no-print">
            ${opts.internal
                ? `<a class="btn btn-secondary" href="#/audit/${U.esc(data.id)}"><span data-icon="arrow-left" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg></span>Back to Audit</a>`
                : `<span class="muted text-sm">Shared report · ${U.esc(U.fmtDate(data.created_at))}</span>`}
            <button class="btn btn-primary" id="print-btn">
                <span data-icon="printer" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg></span>Print / Save as PDF
            </button>
        </div>`;

    /* Category sections (checks) */
    const catSections = cats.map((cat) => {
        const checks = checksByCat[cat.category_key] || [];
        return `<section class="report-sec report-cat-sec card" aria-label="${U.esc(cat.category_name)}">
            <div class="report-cat-head">
                <span class="rc-name">${U.esc(cat.category_name)}</span>
                <span class="rc-score tabular" style="color:${U.gradeColor(cat.grade)}">${U.esc(U.fmtScore(cat.score))}/100</span>
                ${U.gradeBadge(cat.grade, 'sm')}
                ${U.catStatusBadge(cat.status)}
                <span class="muted text-sm tabular">${cat.passed_count || 0} passed · ${cat.warnings_count || 0} warnings · ${cat.issues_count || 0} issues</span>
            </div>
            <div class="report-cat-body">${U.checksList(checks)}</div>
        </section>`;
    }).join('');

    const nextSteps = recs.slice(0, 5)
        .map((r) => `<div class="next-step"><p>${U.esc(r.recommended_action)}</p></div>`)
        .join('');

    const brandingWebsite = branding.website
        ? `<a href="${U.esc(branding.website)}" target="_blank" rel="noopener">${U.esc(String(branding.website).replace(/^https?:\/\//, ''))}</a>` : '';

    main.innerHTML = `${toolbar}
    <article class="report-sheet">
        <header class="report-cover">
            <span class="cover-brand">${U.esc(branding.company_name || 'Website Visibility Audit')} · Website Visibility Audit</span>
            <h1>${U.esc(b.name || 'Website Visibility Report')}</h1>
            <div class="cover-url">${U.esc(data.website_url || '')}</div>
            <div class="cover-meta">
                <span>Prepared ${U.esc(U.fmtDate(data.created_at))}</span>
                ${data.is_demo_data ? U.demoBadge() : ''}
            </div>
            <div class="cover-score-strip">
                <div class="strip-num"><span class="strip-score tabular">${U.esc(U.fmtScore(data.overall_score))}</span><small>/100</small></div>
                <div class="strip-label">Overall Visibility<br>Score</div>
                <div style="margin-left:auto">${U.gradeBadge(data.overall_grade, 'lg')}</div>
            </div>
        </header>

        <div class="report-body">
            <section class="report-sec">
                <div class="sec-eyebrow muted text-sm">Overall Score</div>
                <h2>How visible is this website?</h2>
                <div class="card card-pad" style="display:flex;align-items:center;gap:28px;flex-wrap:wrap">
                    ${U.scoreRing(data.overall_score, data.overall_grade, 132)}
                    <div>
                        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
                            ${U.gradeBadge(data.overall_grade, 'lg')}
                            <strong style="font-size:15px">Grade ${U.esc(data.overall_grade)}</strong>
                        </div>
                        <p class="muted text-sm" style="max-width:480px">
                            This overall score blends all seven categories below, weighted by how much each
                            area influences search and AI-driven visibility. ${cats.length} categories · ${(data.checks || []).length} checks assessed.
                        </p>
                    </div>
                </div>
            </section>

            <section class="report-sec">
                <div class="sec-eyebrow muted text-sm">In plain language</div>
                <h2>Executive Summary</h2>
                <div class="exec-summary">${U.esc(data.executive_summary || '')}</div>
            </section>

            <section class="report-sec">
                <div class="sec-eyebrow muted text-sm">At a glance</div>
                <h2>Score Dashboard by Category</h2>
                ${U.categoryCards(cats)}
            </section>

            <section class="report-sec">
                <div class="sec-eyebrow muted text-sm">Fix these first</div>
                <h2>Highest Priority Issues</h2>
                ${U.topIssues(recs, 5)}
            </section>

            ${catSections}

            <section class="report-sec">
                <div class="sec-eyebrow muted text-sm">Improvement plan</div>
                <h2>Prioritized Recommendations</h2>
                ${U.recommendationCards(recs)}
            </section>

            <section class="report-sec">
                <div class="sec-eyebrow muted text-sm">Action plan</div>
                <h2>Suggested Next Steps</h2>
                <div class="card card-pad">${nextSteps ? `<div class="next-steps">${nextSteps}</div>` : '<p class="muted text-sm">No next steps available.</p>'}</div>
            </section>

            <section class="report-sec">
                <div class="sec-eyebrow muted text-sm">About this audit</div>
                <h2>Methodology & Disclaimer</h2>
                <div class="methodology">
                    <div>${U.esc(data.methodology_note || '')}</div>
                    ${data.is_demo_data ? `<div class="demo-line"><span data-icon="flask" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M9 3h6"/><path d="M10 3v6L4.8 17.7A2 2 0 0 0 6.5 21h11a2 2 0 0 0 1.7-3.3L14 9V3"/><line x1="7.5" y1="15" x2="16.5" y2="15"/></svg></span><span>This audit currently uses sample/demo data. Scores illustrate the report format and will reflect a live crawl of the website in an upcoming release.</span></div>` : ''}
                </div>
            </section>

            <footer class="report-footer">
                <div>
                    <div class="rf-brand">${U.esc(branding.company_name || '')}</div>
                    <div class="muted text-sm">Website Visibility Audit Platform</div>
                </div>
                <div class="rf-contact">
                    ${branding.phone ? `<span class="rf-contact-item"><span data-icon="phone" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg></span>${U.esc(branding.phone)}</span>` : ''}
                    ${branding.email ? `<a class="rf-contact-item" href="mailto:${U.esc(branding.email)}"><span data-icon="mail" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg></span>${U.esc(branding.email)}</a>` : ''}
                    ${brandingWebsite ? `<span class="rf-contact-item"><span data-icon="globe" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg></span>${brandingWebsite}</span>` : ''}
                    <span class="rf-fine">Generated by the Website Visibility Audit platform · Powered by ${U.esc(branding.company_name || 'Netclix Marketing')}</span>
                </div>
            </footer>
        </div>
    </article>
    ${opts.internal ? '' : `<div class="share-footer">Powered by <strong>${U.esc(branding.company_name || 'Netclix Marketing')}</strong> · Website Visibility Audit</div>`}`;

    main.querySelector('#print-btn').addEventListener('click', () => window.print());
}

/* ==================================================================
   PROSPECT SNAPSHOT
   ================================================================== */
function renderProspectReport(main, data, opts) {
    const U = WVA.ui;
    const b = data.business || {};
    const branding = data.branding || {};

    const bars = (data.categories || []).map((c) => {
        const color = U.gradeColor(U.gradeForScore(c.score));
        return `<div class="prospect-bar-row">
            <span class="prospect-bar-label">${U.esc(c.category_name)}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, Math.min(100, Number(c.score) || 0))}%;background:${color}"></div></div>
            <span class="prospect-bar-score tabular" style="font-weight:700;color:${color}">${U.esc(U.fmtScore(c.score))}</span>
        </div>`;
    }).join('');

    const findingsHtml = (data.findings || []).map((f) => {
        const pos = f.type === 'positive';
        const ico = pos
            ? '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="20 6 9 17 4 12"/></svg>'
            : '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
        return `<div class="finding-row">
            <span class="finding-ico ${pos ? 'pos' : 'warn'}">${ico}</span>
            <span class="finding-text">${U.esc(f.text)}</span>
        </div>`;
    }).join('');

    const ctaHref = branding.contact_form_url || branding.scheduling_url ||
        (branding.email ? `mailto:${branding.email}` : (branding.website || '#'));
    const isNewTab = /^https?:\/\//.test(ctaHref);
    const shareToken = data.share_token || null;

    const contactItems = [
        branding.phone ? `<a href="tel:${U.esc(String(branding.phone).replace(/[^+\d]/g, ''))}"><span data-icon="phone" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg></span>${U.esc(branding.phone)}</a>` : '',
        branding.email ? `<a href="mailto:${U.esc(branding.email)}"><span data-icon="mail" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg></span>${U.esc(branding.email)}</a>` : '',
        branding.website ? `<span><span data-icon="globe" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg></span>${U.esc(String(branding.website).replace(/^https?:\/\//, ''))}</span>` : '',
    ].filter(Boolean).join('');

    const helpBadgeHtml = fixHelpBadge(U, b.wants_fix_help);

    main.innerHTML = `
    <div class="prospect-wrap">
        <section class="prospect-hero">
            <div class="prospect-eyebrow">Website Visibility Snapshot</div>
            <h1>${U.esc(b.name || 'Your Website')}</h1>
            <div class="prospect-url">${U.esc(data.website_url || '')}</div>
            <div class="prospect-score-row">
                <div class="prospect-num">${U.esc(U.fmtScore(data.overall_score))}<span>/100</span></div>
                <div class="prospect-grade-badge" style="color:${U.gradeColor(data.overall_grade)}" aria-label="Grade ${U.esc(data.overall_grade)}">${U.esc(data.overall_grade)}</div>
            </div>
            <div class="prospect-demo-row">${data.is_demo_data ? U.demoBadge() : ''}${opts.internal ? helpBadgeHtml : ''}</div>
        </section>

        <section class="card prospect-bars" aria-label="Category scores">
            ${bars}
        </section>

        <p class="prospect-intro">Your website has several opportunities that may be limiting its visibility in search and AI-powered results.</p>

        <section class="card" aria-label="Key findings">
            ${findingsHtml || '<div class="card-pad muted text-sm">No findings available.</div>'}
        </section>

        <section class="card cta-card">
            <h2>${U.esc(branding.cta_headline || "Want to see what's holding your website back?")}</h2>
            <p class="cta-sub">Get the complete audit — every issue found, why it matters, and exactly how to fix it — from ${U.esc(branding.company_name || 'our team')}.</p>
            ${!opts.internal && shareToken
                ? `<button type="button" class="btn btn-primary btn-lg" id="prospect-cta-btn">
                        ${U.esc(branding.cta_button_text || 'Request Your Full Audit')}
                        <span data-icon="arrow-right" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg></span>
                   </button>`
                : `<a class="btn btn-primary btn-lg" href="${U.esc(ctaHref)}" ${isNewTab ? 'target="_blank" rel="noopener"' : ''}>
                        ${U.esc(branding.cta_button_text || 'Request Your Full Audit')}
                        <span data-icon="arrow-right" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg></span>
                   </a>`}
            <div class="cta-contact">${contactItems}</div>
        </section>

        <footer class="share-footer">Powered by <strong>${U.esc(branding.company_name || 'Netclix Marketing')}</strong> · Website Visibility Audit Platform</footer>
    </div>`;

    const ctaBtn = document.getElementById('prospect-cta-btn');
    if (ctaBtn && shareToken) {
        ctaBtn.addEventListener('click', () => openFullAuditModal(U, shareToken, ctaBtn));
    }
}

function fixHelpBadge(U, wantsFixHelp) {
    if (wantsFixHelp === 'yes') {
        return `<span class="badge" style="background:#dcfce7;color:#166534;border-color:#bbf7d0;margin-left:8px">
            <span data-icon="check" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="20 6 9 17 4 12"/></svg></span>
            Wants help fixing issues</span>`;
    }
    if (wantsFixHelp === 'no') {
        return `<span class="badge" style="background:#f1f5f9;color:#475569;border-color:#e2e8f0;margin-left:8px">Declined help offer</span>`;
    }
    return '';
}

function openFullAuditModal(U, shareToken, ctaBtn) {
    const overlay = document.createElement('div');
    overlay.className = 'wva-modal-overlay';
    overlay.innerHTML = `
        <div class="wva-modal" role="dialog" aria-modal="true">
            <div class="wva-modal-body">
                <h3>Your full audit is being emailed to you.</h3>
                <p>Would you also like help correcting any of these issues?</p>
                <div class="wva-modal-actions">
                    <button type="button" class="btn btn-primary" data-answer="yes">Yes, I'd like help</button>
                    <button type="button" class="btn btn-ghost" data-answer="no">No thanks</button>
                </div>
            </div>
        </div>`;
    document.body.appendChild(overlay);

    const close = () => { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); };
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    overlay.querySelectorAll('[data-answer]').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const wantsHelp = btn.dataset.answer === 'yes';
            const body = overlay.querySelector('.wva-modal-body');
            body.querySelectorAll('button').forEach((b) => { b.disabled = true; });
            body.innerHTML = '<h3>Sending your full audit…</h3><p>One moment.</p>';
            try {
                await WVA.api.post(`/api/reports/${encodeURIComponent(shareToken)}/request-full-audit`, { wants_help: wantsHelp });
                body.innerHTML = `<h3>You're all set!</h3>
                    <p>${wantsHelp
                        ? "Your full audit is on its way to your email — we'll also be in touch about helping you fix these issues."
                        : 'Your full audit is on its way to your email.'}</p>
                    <div class="wva-modal-actions"><button type="button" class="btn btn-ghost" data-close>Close</button></div>`;
                body.querySelector('[data-close]').addEventListener('click', close);
                if (ctaBtn) {
                    ctaBtn.disabled = true;
                    ctaBtn.textContent = wantsHelp ? 'Help requested ✓' : 'Full audit sent ✓';
                }
            } catch (err) {
                body.innerHTML = `<h3>Something went wrong.</h3>
                    <p>Please try again in a moment.</p>
                    <div class="wva-modal-actions"><button type="button" class="btn btn-ghost" data-close>Close</button></div>`;
                body.querySelector('[data-close]').addEventListener('click', close);
            }
        });
    });
}