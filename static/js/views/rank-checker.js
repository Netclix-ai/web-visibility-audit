/* #/rank-checker — "Rank Checker Dashboard" landing page. Summary stats +
   recent activity across all three Rank Checker sources (Manual, Bulk
   CSV/Excel upload, GHL webhook), with quick links into each source's
   dedicated page:
     #/rank-checker/manual        -- static/js/views/rank-checker-manual.js
     #/rank-checker/bulk-scoring  -- static/js/views/rank-checker-bulk.js
     #/rank-checker/ghl-leads     -- static/js/views/rank-checker-ghl-leads.js
   Mirrors the relationship the Local Visibility Dashboard has to its own
   three subpages (static/js/views/local-visibility.js). Rank Checker
   tracks keyword rank (Google organic position + Google Map Pack
   position, via Serper.dev -- see serper_client.py) rather than an
   overall score/grade, so its overview surfaces keyword counts and
   found-rate instead of an average score. */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.rankChecker = async function (main) {
    const U = WVA.ui;
    const sub = 'Keyword rank checks via Serper.dev -- organic Google position and Google Map Pack position, for manual checks, bulk CSV/Excel uploads, and GoHighLevel webhook leads.';

    main.innerHTML = U.pageHead({ title: 'Rank Checker Dashboard', sub }) + U.loading('Loading overview…');

    let overview;
    try {
        overview = await WVA.api.get('/api/rank-checker/overview');
    } catch (e) {
        main.innerHTML = U.pageHead({ title: 'Rank Checker Dashboard' }) + U.errorState(e);
        return;
    }

    if (!overview.total_scans) {
        main.innerHTML = U.pageHead({ title: 'Rank Checker Dashboard', sub }) + quickLinksHtml() + U.emptyState({
            icon: 'search',
            title: 'No rank checks yet',
            body: 'Run a manual check, upload a lead list, or wire up the GHL webhook to get started.',
        });
        return;
    }

    const bySource = overview.by_source || {};
    const sourceLabel = { rank_checker_manual: 'Manual', rank_checker_csv: 'Bulk Upload', rank_checker_ghl: 'GHL' };

    const statCards = `<div class="lv-report-overview" style="grid-template-columns:repeat(auto-fill,minmax(140px,1fr));">
        <div class="lv-report-stat"><div class="num">${overview.total_scans}</div><div class="lbl">Total Scans</div></div>
        <div class="lv-report-stat"><div class="num">${overview.completed_scans}</div><div class="lbl">Completed</div></div>
        <div class="lv-report-stat"><div class="num">${overview.failed_scans}</div><div class="lbl">Failed</div></div>
        <div class="lv-report-stat"><div class="num">${overview.total_keywords_checked}</div><div class="lbl">Keywords Checked</div></div>
        <div class="lv-report-stat"><div class="num">${overview.organic_found_count}</div><div class="lbl">Organic Found</div></div>
        <div class="lv-report-stat"><div class="num">${overview.map_pack_found_count}</div><div class="lbl">Map Pack Found</div></div>
    </div>`;

    const sourceBar = `<div class="mt-8" style="display:flex;gap:8px;flex-wrap:wrap;">
        ${Object.entries(bySource).map(([src, n]) => `<span class="chip">${U.esc(sourceLabel[src] || src)}: ${n}</span>`).join('')}
    </div>`;

    const recent = overview.recent || [];
    const rows = recent.map((s) => {
        const status = s.status === 'completed'
            ? '<span class="badge badge-sm fg-x">completed</span>'
            : s.status === 'failed'
                ? `<span class="badge badge-sm fg-x" title="${U.esc(s.error_message || '')}">failed</span>`
                : '<span class="badge badge-sm fg-x">running</span>';
        return `<tr>
            <td>${U.esc(s.business_name || '—')}</td>
            <td><span class="badge badge-sm fg-x">${U.esc(sourceLabel[s.lead_source] || s.lead_source || '—')}</span></td>
            <td class="tabular">${s.keyword_count}</td>
            <td class="tabular">${s.found_count}</td>
            <td>${status}</td>
            <td class="tabular">${U.esc(U.fmtDateTime(s.created_at))}</td>
        </tr>`;
    }).join('');

    main.innerHTML = U.pageHead({ title: 'Rank Checker Dashboard', sub }) + quickLinksHtml() + `<div class="card card-pad mt-16">
        <div class="logo-upload-title">Overview</div>
        ${statCards}
        ${sourceBar}
    </div>
    <div class="card card-pad mt-16">
        <div class="logo-upload-title">Recent Activity</div>
        <div class="table-wrap mt-8">
            <table class="table">
                <thead><tr><th>Business</th><th>Source</th><th>Keywords</th><th>Found</th><th>Status</th><th>Date</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    </div>`;

    function quickLinksHtml() {
        return `<div class="mt-16" style="display:flex;gap:12px;flex-wrap:wrap;">
            <a class="btn btn-primary" href="#/rank-checker/manual">
                <span data-icon="edit" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg></span>Manual Checker
            </a>
            <a class="btn btn-secondary" href="#/rank-checker/bulk-scoring">
                <span data-icon="file-text" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></span>Bulk Checker
            </a>
            <a class="btn btn-secondary" href="#/rank-checker/ghl-leads">
                <span data-icon="zap" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg></span>GHL Checker
            </a>
        </div>`;
    }
};
