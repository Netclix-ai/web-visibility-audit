/* #/rank-checker/manual — one-off keyword rank checks (organic Google
   position + Google Map Pack position, via Serper.dev) for a single
   business. Subcategory of the Rank Checker Dashboard (#/rank-checker),
   alongside Bulk Scoring and GHL Leads. Starts with the default keyword
   template (Settings -> Rank Checker) pre-filled as editable chips/inputs
   (per the user's spec: "start with three keyword searches and then make
   the option to add more if we choose"), each combined with the
   business's own city/state/zip for a location-based query. Every check
   creates a real RankCheckScan row (lead_source="rank_checker_manual",
   see routes.py's /rank-checker/single) and this page shows the full
   history of past manual checks below the form -- mirrors the pattern
   established by local-visibility-manual.js. */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.rankCheckerManual = async function (main) {
    const U = WVA.ui;
    let defaultKeywords = [];

    main.innerHTML = pageHtml();
    try {
        const settings = await WVA.api.get('/api/rank-checker/settings');
        defaultKeywords = settings.default_keywords || [];
    } catch (e) { /* fine — keyword rows just start empty */ }
    renderKeywordRows(defaultKeywords.length ? defaultKeywords : ['', '', '']);
    wireForm();
    await refreshHistory();

    function pageHtml() {
        return U.pageHead({
            title: 'Rank Checker Manual Scoring',
            sub: 'Run a one-off keyword rank check for a single business. Every check is saved below.',
            back: { href: '#/rank-checker', label: 'Rank Checker Dashboard' },
        }) + `<div class="card card-pad form-card" id="rc-single-card">
            <div class="logo-upload-title">Check a single business</div>
            <div class="text-sm muted mt-8">
                Business Name and Website are required (website's domain is matched against
                organic results); City/State or Zip build the location string appended to
                each keyword, since Map Pack results are hyperlocal.
            </div>
            <form id="rc-single-form" class="mt-16">
                <div class="form-grid">
                    <div class="field">
                        <label class="label" for="rc-business_name">Business Name <span class="req">*</span></label>
                        <input class="input" id="rc-business_name" name="business_name" type="text" required>
                    </div>
                    <div class="field">
                        <label class="label" for="rc-website">Website <span class="req">*</span></label>
                        <input class="input" id="rc-website" name="website" type="text" required placeholder="example.com">
                    </div>
                    <div class="field">
                        <label class="label" for="rc-street">Street Address <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="rc-street" name="street" type="text">
                    </div>
                    <div class="field">
                        <label class="label" for="rc-city">City <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="rc-city" name="city" type="text">
                    </div>
                    <div class="field">
                        <label class="label" for="rc-state">State <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="rc-state" name="state" type="text">
                    </div>
                    <div class="field">
                        <label class="label" for="rc-zip">Zip / Postal Code <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="rc-zip" name="zip" type="text">
                    </div>
                    <div class="field">
                        <label class="label" for="rc-email">Email <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="rc-email" name="email" type="email">
                    </div>
                    <div class="field">
                        <label class="label" for="rc-first_name">First Name <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="rc-first_name" name="first_name" type="text">
                    </div>
                    <div class="field">
                        <label class="label" for="rc-last_name">Last Name <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="rc-last_name" name="last_name" type="text">
                    </div>
                </div>
                <div class="mt-16">
                    <label class="label">Keywords</label>
                    <div id="rc-keyword-rows" class="mt-8" style="display:flex;flex-direction:column;gap:8px;"></div>
                    <button type="button" class="btn btn-secondary btn-sm mt-8" id="rc-add-keyword">+ Add keyword</button>
                </div>
                <div class="form-actions mt-16">
                    <button type="submit" class="btn btn-primary" id="rc-single-btn">Run Check</button>
                </div>
            </form>
            <div id="rc-single-result" class="mt-16"></div>
        </div>
        <div class="card card-pad mt-16">
            <div class="logo-upload-title">Past Manual Checks</div>
            <div id="rc-history-holder" class="mt-8">${U.loading('Loading history…')}</div>
        </div>`;
    }

    function renderKeywordRows(keywords) {
        const holder = main.querySelector('#rc-keyword-rows');
        holder.innerHTML = '';
        keywords.forEach((kw) => addKeywordRow(kw));
    }

    function addKeywordRow(value) {
        const holder = main.querySelector('#rc-keyword-rows');
        const row = document.createElement('div');
        row.style.cssText = 'display:flex;gap:8px;align-items:center;';
        row.innerHTML = `<input class="input rc-keyword-input" type="text" placeholder="e.g. tree trimming" value="${U.esc(value || '')}" style="flex:1;">
            <button type="button" class="btn btn-secondary btn-sm rc-remove-keyword">Remove</button>`;
        row.querySelector('.rc-remove-keyword').addEventListener('click', () => row.remove());
        holder.appendChild(row);
    }

    function wireForm() {
        main.querySelector('#rc-add-keyword').addEventListener('click', () => addKeywordRow(''));

        const form = main.querySelector('#rc-single-form');
        const btn = main.querySelector('#rc-single-btn');
        const resultHolder = main.querySelector('#rc-single-result');
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fd = new FormData(form);
            const businessName = (fd.get('business_name') || '').toString().trim();
            const website = (fd.get('website') || '').toString().trim();
            if (!businessName || !website) {
                U.toast('Business Name and Website are required.', 'error');
                return;
            }
            const keywords = Array.from(main.querySelectorAll('.rc-keyword-input'))
                .map((el) => el.value.trim())
                .filter(Boolean);
            const payload = {
                business_name: businessName,
                website,
                street: (fd.get('street') || '').toString().trim() || null,
                city: (fd.get('city') || '').toString().trim() || null,
                state: (fd.get('state') || '').toString().trim() || null,
                zip: (fd.get('zip') || '').toString().trim() || null,
                email: (fd.get('email') || '').toString().trim() || null,
                first_name: (fd.get('first_name') || '').toString().trim() || null,
                last_name: (fd.get('last_name') || '').toString().trim() || null,
                keywords: keywords.length ? keywords : null,
            };
            btn.disabled = true;
            const prevLabel = btn.textContent;
            btn.textContent = 'Running…';
            resultHolder.innerHTML = U.loading('Checking keyword rankings…');
            try {
                const res = await WVA.api.postLong('/api/rank-checker/single', payload);
                resultHolder.innerHTML = singleResultHtml(res);
                if (res.status === 'completed') {
                    U.toast('Check complete.', 'success');
                } else {
                    U.toast(res.error || 'Check failed.', 'error');
                }
                await refreshHistory();
            } catch (err) {
                resultHolder.innerHTML = U.errorState(err);
                U.toast(err.message || 'Check failed.', 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = prevLabel;
            }
        });
    }

    function singleResultHtml(res) {
        if (res.status !== 'completed') {
            return `<div class="card card-pad" style="border-color:var(--danger,#e5484d);">
                <div class="text-sm"><strong>${U.esc(res.business_name || 'Check')}</strong> failed.</div>
                <div class="text-sm muted mt-8">${U.esc(res.error || 'Unknown error')}</div>
            </div>`;
        }
        return `<div class="card card-pad">
            <div class="logo-upload-title">Results for ${U.esc(res.business_name || '')}</div>
            <div class="text-sm muted mt-8">${U.esc(res.location_query || '')}</div>
            ${keywordResultsTable(res.keyword_results || [])}
        </div>`;
    }

    function keywordResultsTable(results) {
        if (!results.length) return '<div class="text-sm muted mt-8">No keyword results.</div>';
        const rows = results.map((r) => {
            const organic = r.organic_position
                ? `<span class="badge badge-sm fg-x">#${r.organic_position}</span>`
                : '<span class="muted">Not found</span>';
            const mapPack = r.map_pack_found
                ? `<span class="badge badge-sm fg-x">#${r.map_pack_position}</span>`
                : '<span class="muted">Not found</span>';
            return `<tr>
                <td>${U.esc(r.keyword)}</td>
                <td>${organic}</td>
                <td>${mapPack}</td>
            </tr>`;
        }).join('');
        return `<div class="table-wrap mt-8">
            <table class="table">
                <thead><tr><th>Keyword</th><th>Organic Rank</th><th>Map Pack Rank</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
    }

    async function refreshHistory() {
        const holder = main.querySelector('#rc-history-holder');
        if (!holder) return;
        let scans;
        try {
            scans = await WVA.api.get('/api/rank-checker/scans?lead_source=rank_checker_manual');
        } catch (e) {
            holder.innerHTML = U.errorState(e);
            return;
        }
        if (!scans.length) {
            holder.innerHTML = U.emptyState({
                icon: 'search',
                title: 'No manual checks yet',
                body: 'Run a check above to see it appear here.',
            });
            return;
        }
        const rows = scans.map((s) => {
            const status = s.status === 'completed'
                ? '<span class="badge badge-sm fg-x">completed</span>'
                : s.status === 'failed'
                    ? `<span class="badge badge-sm fg-x" title="${U.esc(s.error_message || '')}">failed</span>`
                    : '<span class="badge badge-sm fg-x">running</span>';
            const viewBtn = s.status === 'completed'
                ? `<button type="button" class="btn btn-secondary btn-sm rc-hist-view" data-scan-id="${U.esc(s.id)}" data-biz-name="${U.esc(s.business_name || '')}">View Report</button>`
                : '<span class="muted">—</span>';
            return `<tr>
                <td>${U.esc(s.business_name || '—')}</td>
                <td>${U.esc(s.website || '—')}</td>
                <td class="tabular">${s.keyword_count}</td>
                <td class="tabular">${s.found_count}</td>
                <td>${status}</td>
                <td class="tabular">${U.esc(U.fmtDateTime(s.created_at))}</td>
                <td>${viewBtn}</td>
            </tr>`;
        }).join('');
        holder.innerHTML = `<div class="table-wrap">
            <table class="table">
                <thead><tr><th>Business</th><th>Website</th><th>Keywords</th><th>Found</th><th>Status</th><th>Date</th><th>Actions</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
        holder.querySelectorAll('.rc-hist-view').forEach((btn) => {
            btn.addEventListener('click', () => openReportModal(btn.dataset.bizName, btn.dataset.scanId));
        });
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
            content.innerHTML = keywordResultsTable(scan.keyword_results || []);
        } catch (e) {
            content.innerHTML = U.errorState(e);
        }
    }
};
