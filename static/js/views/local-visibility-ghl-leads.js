/* #/local-visibility/ghl-leads — dense, spreadsheet-style list of Local
   Visibility scans sourced from the GoHighLevel webhook integration
   (POST /api/integrations/ghl/local-visibility-request). Subcategory of
   the Local Visibility Dashboard (#/local-visibility), the local-
   visibility counterpart of #/ghl-leads (website audit side). */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.localVisibilityGhlLeads = async function (main) {
    const U = WVA.ui;
    main.innerHTML = pageHead() + U.loading('Loading leads…');

    let scans;
    try {
        scans = await WVA.api.get('/api/local-visibility/scans?lead_source=local_visibility_ghl');
    } catch (e) {
        main.innerHTML = pageHead() + U.errorState(e);
        return;
    }

    if (!scans.length) {
        main.innerHTML = pageHead() + U.emptyState({
            icon: 'zap',
            title: 'No GHL local visibility leads yet',
            body: 'Once your GoHighLevel workflow starts POSTing contacts to the local-visibility-request webhook, scored leads will show up here as they complete.',
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
        const contact = [s.contact_name, s.contact_email, s.phone].filter(Boolean).map(U.esc).join(' · ') || '—';
        const loc = [s.street, s.city, s.state, s.zip_code].filter(Boolean).join(', ') || '—';
        const viewBtn = s.status === 'completed'
            ? `<button type="button" class="btn btn-secondary btn-sm lv-view" data-scan-id="${U.esc(s.id)}" data-biz-name="${U.esc(s.business_name || '')}">View Report</button>`
            : '<span class="muted">—</span>';
        return `<tr>
            <td>${U.esc(s.business_name || '—')}</td>
            <td>${contact}</td>
            <td>${U.esc(loc)}</td>
            <td class="tabular" style="font-weight:700;color:var(--text)">${score}</td>
            <td>${grade}</td>
            <td>${status}</td>
            <td class="tabular">${U.esc(U.fmtDateTime(s.created_at))}</td>
            <td>${viewBtn}</td>
        </tr>`;
    }).join('');

    main.innerHTML = pageHead(scans.length) + `<div class="table-wrap">
        <table class="table">
            <thead><tr><th>Business</th><th>Contact</th><th>Location</th><th>Score</th><th>Grade</th><th>Status</th><th>Scored</th><th>Actions</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;

    main.querySelectorAll('.lv-view').forEach((btn) => {
        btn.addEventListener('click', () => openReportModal(btn.dataset.bizName, btn.dataset.scanId));
    });

    function pageHead(count) {
        return U.pageHead({
            title: 'Local Visibility GHL Leads',
            sub: `Local search presence scoring results from GoHighLevel.${count ? ` ${count} lead${count === 1 ? '' : 's'}.` : ''}`,
            back: { href: '#/local-visibility', label: 'Local Visibility Dashboard' },
        });
    }

    async function openReportModal(businessName, scanId) {
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
        try {
            const data = await WVA.api.get(`/api/local-visibility/scans/${scanId}/report`);
            content.innerHTML = reportHtml(data.report);
        } catch (e) {
            content.innerHTML = U.errorState(e);
        }
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
