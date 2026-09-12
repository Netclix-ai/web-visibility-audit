/* #/ghl-leads — dense, spreadsheet-style list of bulk/outreach "lite"
   audits sourced from the GoHighLevel webhook integration. Kept separate
   from the main dashboard on purpose: these are cheap, high-volume,
   low-detail scoring runs (no PageSpeed/Playwright data, Performance
   category always N/A) meant for outreach messaging, not the kind of
   audit the main dashboard is designed to showcase. */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.ghlLeads = async function (main) {
    const U = WVA.ui;
    main.innerHTML = U.pageHead({
        title: 'GHL Leads',
        sub: 'Bulk outreach scoring results from GoHighLevel — lite audits (no Performance data), for marketing use.',
    }) + U.loading('Loading leads…');

    const businesses = await WVA.api.get('/api/businesses?lead_source=ghl');

    if (!businesses.length) {
        main.innerHTML = U.pageHead({
            title: 'GHL Leads',
            sub: 'Bulk outreach scoring results from GoHighLevel — lite audits (no Performance data), for marketing use.',
        }) + U.emptyState({
            icon: 'zap',
            title: 'No GHL leads yet',
            body: 'Once your GoHighLevel workflow starts POSTing contacts to the audit-request webhook, scored leads will show up here as they complete.',
        });
        return;
    }

    const rows = businesses.map((b) => {
        const la = b.latest_audit;
        const url = la?.website_url ? (la.website_url || '').replace(/^https?:\/\//, '').replace(/\/$/, '') : '—';
        const score = la ? U.fmtScore(la.overall_score) : '—';
        const grade = la ? U.gradeBadge(la.overall_grade, 'sm') : '<span class="muted">—</span>';
        const status = la ? `<span class="badge badge-sm fg-x">${U.esc(la.status)}</span>` : '<span class="muted">—</span>';
        const contact = [b.contact_name, b.contact_email, b.phone].filter(Boolean).map(U.esc).join(' · ') || '—';
        return `<tr class="row-link" tabindex="0" role="link" data-href="#/business/${U.esc(b.id)}" aria-label="Open ${U.esc(b.name)}">
            <td>${U.esc(b.name || '—')}</td>
            <td class="tabular">${U.esc(url)}</td>
            <td>${contact}</td>
            <td class="tabular" style="font-weight:700;color:var(--text)">${score}</td>
            <td>${grade}</td>
            <td>${status}</td>
            <td class="tabular">${U.esc(U.fmtDateTime(b.created_at))}</td>
        </tr>`;
    }).join('');

    main.innerHTML = U.pageHead({
        title: 'GHL Leads',
        sub: `Bulk outreach scoring results from GoHighLevel — lite audits (no Performance data), for marketing use. ${businesses.length} lead${businesses.length === 1 ? '' : 's'}.`,
    }) + `<div class="table-wrap">
        <table class="table">
            <thead><tr><th>Business</th><th>Website</th><th>Contact</th><th>Score</th><th>Grade</th><th>Status</th><th>Scored</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;

    main.querySelectorAll('tr.row-link').forEach((row) => {
        row.addEventListener('click', () => { window.location.hash = row.dataset.href; });
        row.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') window.location.hash = row.dataset.href;
        });
    });
};
