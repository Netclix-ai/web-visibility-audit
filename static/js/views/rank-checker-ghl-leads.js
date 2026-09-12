/* #/rank-checker/ghl-leads — dense, spreadsheet-style list of Rank
   Checker scans sourced from the GoHighLevel webhook integration
   (POST /api/integrations/ghl/rank-check-request). Subcategory of the
   Rank Checker Dashboard (#/rank-checker), the rank-checker counterpart
   of #/local-visibility/ghl-leads. */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.rankCheckerGhlLeads = async function (main) {
    const U = WVA.ui;
    main.innerHTML = pageHead() + U.loading('Loading leads…');
    await load('');
    wireFilter();

    function pageHead() {
        return U.pageHead({
            title: 'Rank Checker GHL Checker',
            sub: 'Keyword rank checks triggered by the GoHighLevel webhook integration.',
            back: { href: '#/rank-checker', label: 'Rank Checker Dashboard' },
        }) + `<div class="mt-8" style="display:flex;justify-content:flex-end;">
            <select class="input" id="rc-ghl-filter" style="max-width:200px;">
                <option value="">All check types</option>
                <option value="both">Organic + Map Pack</option>
                <option value="organic">Organic only</option>
                <option value="maps">Map Pack only</option>
            </select>
        </div>`;
    }

    function wireFilter() {
        const filterEl = main.querySelector('#rc-ghl-filter');
        if (filterEl) filterEl.addEventListener('change', () => load(filterEl.value));
    }

    async function load(checkTypeFilter) {
        let url = '/api/rank-checker/scans?lead_source=rank_checker_ghl';
        if (checkTypeFilter) url += `&check_type=${encodeURIComponent(checkTypeFilter)}`;
        let scans;
        try {
            scans = await WVA.api.get(url);
        } catch (e) {
            main.innerHTML = pageHead() + U.errorState(e);
            wireFilter();
            return;
        }

        if (!scans.length) {
            main.innerHTML = pageHead() + U.emptyState({
                icon: 'zap',
                title: 'No GHL rank checker leads yet',
                body: 'Once your GoHighLevel workflow starts POSTing contacts to the rank-check-request webhook, scored leads will show up here as they complete.',
            });
            wireFilter();
            const filterEl = main.querySelector('#rc-ghl-filter');
            if (filterEl) filterEl.value = checkTypeFilter || '';
            return;
        }

        const rows = scans.map((s) => {
            const status = s.status === 'completed'
                ? '<span class="badge badge-sm fg-x">completed</span>'
                : s.status === 'failed'
                    ? `<span class="badge badge-sm fg-x" title="${U.esc(s.error_message || '')}">failed</span>`
                    : '<span class="badge badge-sm fg-x">running</span>';
            const contact = [s.contact_name, s.contact_email, s.phone].filter(Boolean).map(U.esc).join(' · ') || '—';
            const viewBtn = s.status === 'completed'
                ? `<button type="button" class="btn btn-secondary btn-sm rc-view" data-scan-id="${U.esc(s.id)}" data-biz-name="${U.esc(s.business_name || '')}">View Report</button>`
                : '<span class="muted">—</span>';
            return `<tr>
                <td>${U.esc(s.business_name || '—')}</td>
                <td>${contact}</td>
                <td>${U.esc(s.website || '—')}</td>
                <td>${U.esc(checkTypeLabel(s.check_type))}</td>
                <td class="tabular">${s.keyword_count}</td>
                <td class="tabular">${s.found_count}</td>
                <td>${status}</td>
                <td class="tabular">${U.esc(U.fmtDateTime(s.created_at))}</td>
                <td>${viewBtn}</td>
            </tr>`;
        }).join('');

        main.innerHTML = pageHead() + `<div class="table-wrap mt-8">
            <table class="table">
                <thead><tr><th>Business</th><th>Contact</th><th>Website</th><th>Check Type</th><th>Keywords</th><th>Found</th><th>Status</th><th>Date</th><th>Actions</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;

        wireFilter();
        const filterEl = main.querySelector('#rc-ghl-filter');
        if (filterEl) filterEl.value = checkTypeFilter || '';

        main.querySelectorAll('.rc-view').forEach((btn) => {
            btn.addEventListener('click', () => openReportModal(btn.dataset.bizName, btn.dataset.scanId));
        });
    }

    function checkTypeLabel(checkType) {
        if (checkType === 'organic') return 'Organic only';
        if (checkType === 'maps') return 'Map Pack only';
        return 'Organic + Map Pack';
    }

    async function openReportModal(businessName, scanId) {
        const overlay = document.createElement('div');
        overlay.className = 'wva-modal-overlay';
        overlay.innerHTML = `
            <div class="wva-modal wva-modal-lg" role="dialog" aria-modal="true">
                <div class="wva-modal-body wva-modal-body-lg">
                    <h3>${U.esc(businessName || 'Rank Check Report')}</h3>
                    <div data-report-content>${U.loading('Loading report…')}</div>
                </div>
            </div>`;
        document.body.appendChild(overlay);
        const close = () => { if (overlay.parentNode) overlay.parentNode.removeChild(overlay); };
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
        document.addEventListener('keydown', function onEsc(e) {
            if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onEsc); }
        });

        const content = overlay.querySelector('[data-report-content]');
        try {
            const scan = await WVA.api.get(`/api/rank-checker/scans/${scanId}`);
            content.innerHTML = keywordResultsTable(scan.keyword_results || [], scan.check_type);
        } catch (e) {
            content.innerHTML = U.errorState(e);
        }
    }

    function keywordResultsTable(results, checkType) {
        checkType = checkType || 'both';
        const showOrganic = checkType === 'organic' || checkType === 'both';
        const showMaps = checkType === 'maps' || checkType === 'both';
        if (!results.length) return '<div class="text-sm muted mt-8">No keyword results.</div>';
        const rowsHtml = results.map((r) => {
            const organic = r.organic_position
                ? `<span class="badge badge-sm fg-x">#${r.organic_position}</span>`
                : '<span class="muted">Not found</span>';
            const mapPack = r.map_pack_found
                ? `<span class="badge badge-sm fg-x">#${r.map_pack_position}</span>`
                : '<span class="muted">Not found</span>';
            return `<tr>
                <td>${U.esc(r.keyword)}</td>
                ${showOrganic ? `<td>${organic}</td>` : ''}
                ${showMaps ? `<td>${mapPack}</td>` : ''}
            </tr>`;
        }).join('');
        return `<div class="table-wrap mt-8">
            <table class="table">
                <thead><tr><th>Keyword</th>${showOrganic ? '<th>Organic Rank</th>' : ''}${showMaps ? '<th>Map Pack Rank</th>' : ''}</tr></thead>
                <tbody>${rowsHtml}</tbody>
            </table>
        </div>`;
    }
};
