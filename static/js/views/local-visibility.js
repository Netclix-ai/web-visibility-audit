/* #/local-visibility — "Local Visibility Dashboard" landing page.
   Summary stats + recent activity across all three Local Visibility
   scoring sources (Manual, Bulk CSV/Excel upload, GHL webhook), with
   quick links into each source's dedicated page:
     #/local-visibility/manual        -- static/js/views/local-visibility-manual.js
     #/local-visibility/bulk-scoring  -- static/js/views/local-visibility-bulk.js
     #/local-visibility/ghl-leads     -- static/js/views/local-visibility-ghl-leads.js
   Mirrors the relationship the main #/dashboard has to #/create-audit,
   #/ghl-leads and #/bulk-scoring for the website-audit side of the app. */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.localVisibility = async function (main) {
    const U = WVA.ui;
    main.innerHTML = U.pageHead({
        title: 'Local Visibility Dashboard',
        sub: 'Local search presence scoring via Advice Local -- manual checks, bulk CSV/Excel uploads, and GoHighLevel webhook leads all roll up here.',
    }) + U.loading('Loading overview…');

    let overview;
    try {
        overview = await WVA.api.get('/api/local-visibility/overview');
    } catch (e) {
        main.innerHTML = U.pageHead({ title: 'Local Visibility Dashboard' }) + U.errorState(e);
        return;
    }

    if (!overview.total_scans) {
        main.innerHTML = U.pageHead({
            title: 'Local Visibility Dashboard',
            sub: 'Local search presence scoring via Advice Local -- manual checks, bulk CSV/Excel uploads, and GoHighLevel webhook leads all roll up here.',
        }) + quickLinksHtml() + U.emptyState({
            icon: 'map-pin',
            title: 'No local visibility scans yet',
            body: 'Run a manual check, upload a lead list, or wire up the GHL webhook to get started.',
        });
        return;
    }

    const bySource = overview.by_source || {};
    const gradeCounts = overview.grade_counts || {};
    const sourceLabel = { local_visibility_manual: 'Manual', local_visibility_csv: 'Bulk Upload', local_visibility_ghl: 'GHL' };

    const statCards = `<div class="lv-report-overview" style="grid-template-columns:repeat(auto-fill,minmax(140px,1fr));">
        <div class="lv-report-stat"><div class="num">${overview.total_scans}</div><div class="lbl">Total Scans</div></div>
        <div class="lv-report-stat"><div class="num">${overview.completed_scans}</div><div class="lbl">Completed</div></div>
        <div class="lv-report-stat"><div class="num">${overview.failed_scans}</div><div class="lbl">Failed</div></div>
        <div class="lv-report-stat"><div class="num">${overview.average_score != null ? overview.average_score.toFixed(1) : '—'}</div><div class="lbl">Avg Score</div></div>
    </div>`;

    const gradeBar = Object.keys(gradeCounts).length ? `<div class="mt-8" style="display:flex;gap:8px;flex-wrap:wrap;">
        ${Object.entries(gradeCounts).sort().map(([g, n]) => `<span class="chip">${U.gradeBadge(g, 'sm')} ${n}</span>`).join('')}
    </div>` : '';

    const sourceBar = `<div class="mt-8" style="display:flex;gap:8px;flex-wrap:wrap;">
        ${Object.entries(bySource).map(([src, n]) => `<span class="chip">${U.esc(sourceLabel[src] || src)}: ${n}</span>`).join('')}
    </div>`;

    const recent = overview.recent || [];
    const rows = recent.map((s) => {
        const score = s.overall_score != null ? U.fmtScore(s.overall_score) : '—';
        const grade = s.overall_grade ? U.gradeBadge(s.overall_grade, 'sm') : '<span class="muted">—</span>';
        const status = s.status === 'completed'
            ? '<span class="badge badge-sm fg-x">completed</span>'
            : s.status === 'failed'
                ? `<span class="badge badge-sm fg-x" title="${U.esc(s.error_message || '')}">failed</span>`
                : '<span class="badge badge-sm fg-x">running</span>';
        return `<tr>
            <td>${U.esc(s.business_name || '—')}</td>
            <td><span class="badge badge-sm fg-x">${U.esc(sourceLabel[s.lead_source] || s.lead_source || '—')}</span></td>
            <td class="tabular" style="font-weight:700;color:var(--text)">${score}</td>
            <td>${grade}</td>
            <td>${status}</td>
            <td class="tabular">${U.esc(U.fmtDateTime(s.created_at))}</td>
        </tr>`;
    }).join('');

    main.innerHTML = U.pageHead({
        title: 'Local Visibility Dashboard',
        sub: 'Local search presence scoring via Advice Local -- manual checks, bulk CSV/Excel uploads, and GoHighLevel webhook leads all roll up here.',
    }) + quickLinksHtml() + `<div class="card card-pad mt-16">
        <div class="logo-upload-title">Overview</div>
        ${statCards}
        ${sourceBar}
        ${gradeBar}
    </div>
    <div class="card card-pad mt-16">
        <div class="logo-upload-title">Recent Activity</div>
        <div class="table-wrap mt-8">
            <table class="table">
                <thead><tr><th>Business</th><th>Source</th><th>Score</th><th>Grade</th><th>Status</th><th>Date</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    </div>`;

    function quickLinksHtml() {
        return `<div class="mt-16" style="display:flex;gap:12px;flex-wrap:wrap;">
            <a class="btn btn-primary" href="#/local-visibility/manual">
                <span data-icon="edit" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg></span>Manual Scoring
            </a>
            <a class="btn btn-secondary" href="#/local-visibility/bulk-scoring">
                <span data-icon="file-text" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></span>Bulk Scoring
            </a>
            <a class="btn btn-secondary" href="#/local-visibility/ghl-leads">
                <span data-icon="zap" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg></span>GHL Leads
            </a>
        </div>`;
    }
};
