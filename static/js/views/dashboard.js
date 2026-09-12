/* #/ and #/dashboard — businesses list */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.dashboard = async function (main) {
    const U = WVA.ui;
    main.innerHTML = U.pageHead({
        title: 'Website Audit Dashboard',
        sub: 'All audited businesses and their latest visibility scores.',
        actions: `<a class="btn btn-primary" href="#/create-audit"><span data-icon="plus" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg></span>New Audit</a>`,
    }) + U.loading('Loading businesses…');

    const businesses = await WVA.api.get('/api/businesses');

    if (!businesses.length) {
        main.innerHTML = U.pageHead({
            title: 'Website Audit Dashboard',
            sub: 'All audited businesses and their latest visibility scores.',
            actions: `<a class="btn btn-primary" href="#/create-audit">+ New Audit</a>`,
        }) + U.emptyState({
            icon: 'dashboard',
            title: 'No businesses yet',
            body: 'Run your first website audit to see visibility scores, issues and recommendations here.',
            cta: { href: '#/create-audit', label: '+ Create your first audit' },
        });
        return;
    }

    const cards = businesses.map((b) => {
        const la = b.latest_audit;
        const initials = (b.name || '?').split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
        const meta = [
            b.location ? `<span><span data-icon="map-pin" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg></span>${U.esc(b.location)}</span>` : '',
            b.category ? `<span><span data-icon="tag" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.83z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg></span>${U.esc(b.category)}</span>` : '',
        ].filter(Boolean).join('');

        const displayUrl = la?.website_url ? (la.website_url || '').replace(/^https?:\/\//, '').replace(/\/$/, '') : null;

        const scoreBlock = la
            ? `<div class="biz-score-row">
                    ${U.scoreRing(la.overall_score, la.overall_grade, 78, { stroke: 7, numScale: 0.31 })}
                    <div class="biz-score-info">
                        ${U.gradeBadge(la.overall_grade)}
                        <div class="biz-date">Latest audit ${U.esc(U.fmtDate(la.created_at))}</div>
                        ${la.is_demo_data ? U.demoBadge() : ''}
                    </div>
                </div>`
            : `<div class="biz-noaudit">No audits yet — create one to see visibility scores.</div>`;

        return `<div class="card biz-card" data-href="#/business/${U.esc(b.id)}" role="link" tabindex="0" aria-label="Open ${U.esc(b.name)}">
            <button class="biz-delete-btn" data-delete-biz="${U.esc(b.id)}" data-biz-name="${U.esc(b.name)}" title="Delete business" aria-label="Delete ${U.esc(b.name)}">
                <span data-icon="trash" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></span>
            </button>
            <div class="biz-card-top">
                <div class="biz-avatar" aria-hidden="true">${U.esc(initials)}</div>
                <div>
                    <div class="biz-name-row">
                        <h3>${U.esc(displayUrl || b.name)}</h3>
                        ${b.lead_source === 'widget' ? `<span class="badge badge-lead" title="This business came in through the public website widget"><span data-icon="zap" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg></span>Lead</span>` : ''}
                        ${b.wants_fix_help === 'yes' ? `<span class="badge" style="background:#dcfce7;color:#166534;border-color:#bbf7d0" title="This lead asked for help fixing their issues"><span data-icon="check" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="20 6 9 17 4 12"/></svg></span>Wants help</span>` : ''}
                        ${b.wants_fix_help === 'no' ? `<span class="badge" style="background:#f1f5f9;color:#475569;border-color:#e2e8f0" title="This lead declined the help offer">Declined help</span>` : ''}
                    </div>
                    ${displayUrl ? `<div class="biz-business-name">${U.esc(b.name)}</div>` : ''}
                    <div class="biz-meta">${meta}</div>
                </div>
            </div>
            ${scoreBlock}
            <div class="biz-card-foot">
                <span class="chip"><span data-icon="globe" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg></span>${b.website_count} website${b.website_count === 1 ? '' : 's'}</span>
                <span class="biz-arrow">View business <span data-icon="arrow-right" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg></span></span>
            </div>
        </div>`;
    }).join('');

    main.innerHTML = U.pageHead({
        title: 'Website Audit Dashboard',
        sub: 'All audited businesses and their latest visibility scores.',
        actions: `<a class="btn btn-primary" href="#/create-audit"><span data-icon="plus" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg></span>New Audit</a>`,
    }) + `<div class="biz-grid">${cards}</div>`;

    main.querySelectorAll('.biz-card').forEach((card) => {
        card.addEventListener('click', () => { window.location.hash = card.dataset.href; });
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.target === card) window.location.hash = card.dataset.href;
        });
    });

    main.querySelectorAll('[data-delete-biz]').forEach((btn) => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const name = btn.dataset.bizName || 'this business';
            if (!window.confirm(`Delete "${name}" and all of its websites, audits and reports? This cannot be undone.`)) return;
            btn.disabled = true;
            try {
                await WVA.api.del(`/api/businesses/${btn.dataset.deleteBiz}`);
                U.toast('Business deleted.', 'success');
                WVA.views.dashboard(main);
            } catch (err) {
                btn.disabled = false;
                U.toast(err.message || 'Delete failed.', 'error');
            }
        });
    });
};