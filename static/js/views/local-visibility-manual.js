/* #/local-visibility/manual — one-off Advice Local baseline checks for a
   single business (no file upload). Subcategory of the Local Visibility
   Dashboard (#/local-visibility), alongside Bulk Scoring and GHL Leads.
   Unlike the old inline-only version of this form, results are now
   persisted: every check creates a real LocalVisibilityScan row
   (lead_source="local_visibility_manual", see routes.py's
   /local-visibility/single), and this page loads + displays the full
   history of past manual checks below the form so nothing is lost on
   navigation or reload -- mirrors the "keep past results visible"
   pattern already used by the Bulk Scoring job-history table and
   #/ghl-leads. */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.localVisibilityManual = async function (main) {
    const U = WVA.ui;

    main.innerHTML = pageHtml();
    wireSingleCheck();
    await refreshHistory();

    function pageHtml() {
        return U.pageHead({
            title: 'Local Visibility Manual Scoring',
            sub: 'Run a one-off Advice Local baseline check for a single business. Every check is saved below.',
            back: { href: '#/local-visibility', label: 'Local Visibility Dashboard' },
        }) + `<div class="card card-pad form-card" id="lv-single-card">
            <div class="logo-upload-title">Check a single business</div>
            <div class="text-sm muted mt-8">
                Business Name, Street Address, Zip/Postal Code, and Phone are required
                (Advice Local needs these to create a client); the rest improve accuracy.
            </div>
            <form id="lv-single-form" class="mt-16">
                <div class="form-grid">
                    <div class="field">
                        <label class="label" for="lv-business_name">Business Name <span class="req">*</span></label>
                        <input class="input" id="lv-business_name" name="business_name" type="text" required>
                    </div>
                    <div class="field">
                        <label class="label" for="lv-zip">Zip / Postal Code <span class="req">*</span></label>
                        <input class="input" id="lv-zip" name="zip" type="text" required>
                    </div>
                    <div class="field">
                        <label class="label" for="lv-street">Street Address <span class="req">*</span></label>
                        <input class="input" id="lv-street" name="street" type="text" required>
                    </div>
                    <div class="field">
                        <label class="label" for="lv-city">City <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="lv-city" name="city" type="text">
                    </div>
                    <div class="field">
                        <label class="label" for="lv-state">State <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="lv-state" name="state" type="text">
                    </div>
                    <div class="field">
                        <label class="label" for="lv-phone">Phone <span class="req">*</span></label>
                        <input class="input" id="lv-phone" name="phone" type="text" required>
                    </div>
                    <div class="field">
                        <label class="label" for="lv-email">Email <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="lv-email" name="email" type="email">
                    </div>
                    <div class="field">
                        <label class="label" for="lv-website">Website <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="lv-website" name="website" type="text">
                    </div>
                    <div class="field">
                        <label class="label" for="lv-first_name">First Name <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="lv-first_name" name="first_name" type="text">
                    </div>
                    <div class="field">
                        <label class="label" for="lv-last_name">Last Name <span class="muted" style="font-weight:500">(optional)</span></label>
                        <input class="input" id="lv-last_name" name="last_name" type="text">
                    </div>
                </div>
                <div class="form-actions">
                    <button type="submit" class="btn btn-primary" id="lv-single-btn">Run Check</button>
                </div>
            </form>
            <div id="lv-single-result" class="mt-16"></div>
        </div>
        <div class="card card-pad mt-16">
            <div class="logo-upload-title">Past Manual Checks</div>
            <div id="lv-history-holder" class="mt-8">${U.loading('Loading history…')}</div>
        </div>`;
    }

    function wireSingleCheck() {
        const form = main.querySelector('#lv-single-form');
        const btn = main.querySelector('#lv-single-btn');
        const resultHolder = main.querySelector('#lv-single-result');
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fd = new FormData(form);
            const businessName = (fd.get('business_name') || '').toString().trim();
            const zip = (fd.get('zip') || '').toString().trim();
            const street = (fd.get('street') || '').toString().trim();
            const phone = (fd.get('phone') || '').toString().trim();
            if (!businessName || !zip || !street || !phone) {
                U.toast('Business Name, Street Address, Zip/Postal Code, and Phone are required.', 'error');
                return;
            }
            const payload = {
                business_name: businessName,
                zip,
                street,
                city: (fd.get('city') || '').toString().trim() || null,
                state: (fd.get('state') || '').toString().trim() || null,
                phone,
                email: (fd.get('email') || '').toString().trim() || null,
                website: (fd.get('website') || '').toString().trim() || null,
                first_name: (fd.get('first_name') || '').toString().trim() || null,
                last_name: (fd.get('last_name') || '').toString().trim() || null,
            };
            btn.disabled = true;
            const prevLabel = btn.textContent;
            btn.textContent = 'Running… (can take up to a minute)';
            resultHolder.innerHTML = U.loading('Creating Advice Local client and waiting for baseline score…');
            try {
                const res = await WVA.api.postLong('/api/local-visibility/single', payload);
                resultHolder.innerHTML = singleResultHtml(res);
                wireResultActions(res, res.report || null);
                if (res.success) {
                    U.toast('Check complete.', 'success');
                    form.reset();
                } else {
                    U.toast(res.error || 'Check failed.', 'error');
                }
                await refreshHistory(); // keep the persisted list in sync immediately
            } catch (err) {
                resultHolder.innerHTML = U.errorState(err);
                U.toast(err.message || 'Check failed.', 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = prevLabel;
            }
        });

        function wireResultActions(res, cachedReport) {
            const viewBtn = resultHolder.querySelector('[data-lv-view-report]');
            if (viewBtn) {
                viewBtn.addEventListener('click', () => openReportModal(res.business_name, res.scan_id, cachedReport));
            }
        }
    }

    function singleResultHtml(res) {
        if (!res.success) {
            return `<div class="card card-pad" style="border-color:var(--danger,#e5484d);">
                <div class="text-sm"><strong>${U.esc(res.business_name || 'Check')}</strong> failed.</div>
                <div class="text-sm muted mt-8">${U.esc(res.error || 'Unknown error')}</div>
            </div>`;
        }
        return `<div class="card card-pad">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;">
                <div style="display:flex;align-items:center;gap:16px;">
                    ${U.scoreRing(res.local_visibility_score, res.local_visibility_grade, 88, { stroke: 7, numScale: 0.32 })}
                    <div>
                        <div class="text-sm muted">Result for</div>
                        <div class="logo-upload-title">${U.esc(res.business_name || '')}</div>
                        <div class="mt-8">${U.gradeBadge ? U.gradeBadge(res.local_visibility_grade) : U.esc(res.local_visibility_grade || '')}</div>
                    </div>
                </div>
                <button type="button" class="btn btn-secondary" data-lv-view-report>View Report</button>
            </div>
        </div>`;
    }

    async function refreshHistory() {
        const holder = main.querySelector('#lv-history-holder');
        if (!holder) return;
        let scans;
        try {
            scans = await WVA.api.get('/api/local-visibility/scans?lead_source=local_visibility_manual');
        } catch (e) {
            holder.innerHTML = U.errorState(e);
            return;
        }
        if (!scans.length) {
            holder.innerHTML = U.emptyState({
                icon: 'edit',
                title: 'No manual checks yet',
                body: 'Run a check above to see it appear here.',
            });
            return;
        }
        const rows = scans.map((s) => {
            const score = s.overall_score != null ? U.fmtScore(s.overall_score) : '—';
            const grade = s.overall_grade ? U.gradeBadge(s.overall_grade, 'sm') : '<span class="muted">—</span>';
            const status = s.status === 'completed'
                ? '<span class="badge badge-sm fg-x">completed</span>'
                : s.status === 'failed'
                    ? `<span class="badge badge-sm fg-x" title="${U.esc(s.error_message || '')}">failed</span>`
                    : '<span class="badge badge-sm fg-x">running</span>';
            const loc = [s.city, s.state].filter(Boolean).join(', ') || '—';
            const viewBtn = s.status === 'completed'
                ? `<button type="button" class="btn btn-secondary btn-sm lv-hist-view" data-scan-id="${U.esc(s.id)}" data-biz-name="${U.esc(s.business_name || '')}">View Report</button>`
                : '<span class="muted">—</span>';
            return `<tr>
                <td>${U.esc(s.business_name || '—')}</td>
                <td>${U.esc(loc)}</td>
                <td class="tabular" style="font-weight:700;color:var(--text)">${score}</td>
                <td>${grade}</td>
                <td>${status}</td>
                <td class="tabular">${U.esc(U.fmtDateTime(s.created_at))}</td>
                <td>${viewBtn}</td>
            </tr>`;
        }).join('');
        holder.innerHTML = `<div class="table-wrap">
            <table class="table">
                <thead><tr><th>Business</th><th>Location</th><th>Score</th><th>Grade</th><th>Status</th><th>Date</th><th>Actions</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
        holder.querySelectorAll('.lv-hist-view').forEach((btn) => {
            btn.addEventListener('click', () => openReportModal(btn.dataset.bizName, btn.dataset.scanId, null));
        });
    }

    async function openReportModal(businessName, scanId, cachedReport) {
        const overlay = document.createElement('div');
        overlay.className = 'wva-modal-overlay';
        overlay.innerHTML = `
            <div class="wva-modal wva-modal-lg" role="dialog" aria-modal="true">
                <div class="wva-modal-body wva-modal-body-lg">
                    <h3>${U.esc(businessName || 'Baseline Report')}</h3>
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
        let report = cachedReport;
        if (!report && scanId) {
            try {
                const data = await WVA.api.get(`/api/local-visibility/scans/${scanId}/report`);
                report = data.report;
            } catch (e) {
                content.innerHTML = U.errorState(e);
                return;
            }
        }
        content.innerHTML = reportHtml(report);
    }

    function reportHtml(report) {
        if (!report) {
            return '<div class="text-sm muted">No report data available for this check.</div>';
        }
        const ov = (report.overview && report.overview.baselineOverview) || {};
        const stat = (label, val) => `<div class="lv-report-stat"><div class="num">${val == null ? '—' : U.esc(String(val))}</div><div class="lbl">${U.esc(label)}</div></div>`;
        const overviewHtml = `<div class="lv-report-overview">
            ${stat('Visibility', ov.visibilityScore)}
            ${stat('Presence', ov.presenceScore)}
            ${stat('NAP', ov.napScore)}
            ${stat('Google', ov.googleScore)}
            ${stat('Bing', ov.bingScore)}
            ${stat('Yelp', ov.yelpScore)}
            ${stat('Directories', ov.directoriesScore)}
            ${stat('Locals', ov.localsScore)}
            ${stat('Voice', ov.voiceScore)}
        </div>`;

        const baseline = (report.data && report.data.baseline) || {};
        const locals = baseline.locals || [];
        const directories = baseline.directories || [];
        const voice = baseline.voice || [];

        const rowHtml = (item, name, extra) => `<div class="lv-report-row ${item.found === false ? 'not-found' : ''}">
            <span class="name">${U.esc(name)}</span>
            <span class="text-sm muted">${extra || (item.found ? 'Found' : 'Not found')}</span>
        </div>`;

        const localsHtml = locals.length ? `<div class="lv-report-section-title">Local Listings (Google, Bing)</div>
            <div class="lv-report-list">${locals.map((l) => rowHtml(
                l, l.product || l.directory,
                l.found ? `Score ${l.score ?? '—'}${l.reviews != null ? ` · ${l.reviews} reviews` : ''}` : 'Not found'
            )).join('')}</div>` : '';

        const sortedDirs = directories.slice().sort((a, b) => (b.found ? 1 : 0) - (a.found ? 1 : 0));
        const directoriesHtml = directories.length ? `<div class="lv-report-section-title">
            Directories (${directories.filter((d) => d.found).length}/${directories.length} found)
        </div>
        <div class="lv-report-list">${sortedDirs.map((d) => rowHtml(
            d, d.product || d.directory,
            d.found ? `Score ${d.score ?? '—'}` : 'Not found'
        )).join('')}</div>` : '';

        const voiceHtml = voice.length ? `<div class="lv-report-section-title">Voice Assistants</div>
            <div class="lv-report-list">${voice.map((v) => `<div class="lv-report-row ${!v.score ? 'not-found' : ''}">
                <span class="name">${U.esc(v.name || v.device)}</span>
                <span class="text-sm muted">Score ${v.score ?? '—'}</span>
            </div>`).join('')}</div>` : '';

        return overviewHtml + localsHtml + directoriesHtml + voiceHtml;
    }
};
