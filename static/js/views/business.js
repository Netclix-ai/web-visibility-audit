/* #/business/:id — business detail, websites, audit history, score-over-time charts */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.business = async function (main, params) {
    const U = WVA.ui;
    main.innerHTML = U.loading('Loading business…');

    const biz = await WVA.api.get(`/api/businesses/${params.id}`);
    renderBusiness(main, biz);
};

function renderBusiness(main, biz) {
    const U = WVA.ui;
    const chips = [
        biz.location ? U.chip('map-pin', biz.location) : '',
        biz.category ? U.chip('tag', biz.category) : '',
        biz.service_area ? U.chip('globe', `Serves: ${biz.service_area}`) : '',
        U.chip('calendar', `Added ${U.fmtDate(biz.created_at)}`),
    ].filter(Boolean).join('');

    const metaBits = [
        biz.location ? U.esc(biz.location) : '',
        biz.category ? U.esc(biz.category) : '',
    ].filter(Boolean).join(' · ');

    const head = U.pageHead({
        title: biz.name,
        sub: metaBits || undefined,
        back: { href: '#/dashboard', label: 'Dashboard' },
        actions: `<button class="btn btn-secondary" id="edit-biz-btn"><span data-icon="edit" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg></span>Edit</button>
                  <button class="btn btn-secondary btn-danger" id="delete-biz-btn"><span data-icon="trash" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></span>Delete</button>
                  <a class="btn btn-primary" href="#/create-audit"><span data-icon="plus" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg></span>New Audit</a>`,
    });

    const addWebsiteForm = `
        <form class="card card-pad mb-24" id="add-website-form">
            <div class="flex gap-12 items-center" style="flex-wrap:wrap">
                <div style="flex:1;min-width:260px">
                    <label class="label" for="new-website-url">Add a website for this business</label>
                    <div class="hint">Additional domains, landing pages or microsites to track.</div>
                </div>
                <input class="input" id="new-website-url" type="text" placeholder="https://example.com" style="max-width:360px" required>
                <button type="submit" class="btn btn-secondary"><span data-icon="plus" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg></span>Add Website</button>
            </div>
        </form>`;

    const websiteCards = (biz.websites || []).map((w) => {
        const chartHtml = (w.audits || []).length
            ? `<div class="chart-box"><canvas id="chart-${U.esc(w.id)}" role="img" aria-label="Overall score over time for ${U.esc(w.url)}"></canvas></div>`
            : `<div class="chart-empty">Run an audit to start the score history chart.</div>`;

        return `<section class="card website-card">
            <div class="website-head">
                <span data-icon="globe" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg></span>
                <span class="website-url"><a href="${U.esc(w.url)}" target="_blank" rel="noopener">${U.esc(w.url)}</a></span>
                <span class="chip">${w.audit_count} audit${w.audit_count === 1 ? '' : 's'}</span>
                <div class="website-actions">
                    <button class="btn btn-secondary btn-sm" data-rerun="${U.esc(w.id)}">
                        <span data-icon="refresh" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg></span>Re-run Audit
                    </button>
                    <button class="btn btn-secondary btn-sm btn-danger" data-delete-website="${U.esc(w.id)}" data-website-url="${U.esc(w.url)}" title="Delete website and all its audits">
                        <span data-icon="trash" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></span>
                    </button>
                </div>
            </div>
            ${chartHtml}
            <div style="overflow-x:auto">${auditTableHtml(w)}</div>
        </section>`;
    }).join('');

    function auditRowHtml(a) {
        return `
            <tr class="row-link" tabindex="0" role="link" data-href="#/audit/${U.esc(a.id)}" aria-label="Open audit from ${U.esc(U.fmtDate(a.created_at))}">
                <td class="tabular">${U.esc(U.fmtDateTime(a.created_at))}</td>
                <td class="tabular" style="font-weight:700;color:var(--text)">${U.esc(U.fmtScore(a.overall_score))}</td>
                <td>${U.gradeBadge(a.overall_grade, 'sm')}</td>
                <td><span class="badge badge-sm fg-x">${U.esc(a.status)}</span>${a.is_demo_data ? ' ' + U.demoBadge() : ''}</td>
                <td style="text-align:right">
                    <button class="audit-delete-btn" data-delete-audit="${U.esc(a.id)}" title="Delete this audit" aria-label="Delete audit from ${U.esc(U.fmtDate(a.created_at))}">
                        <span data-icon="trash" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg></span>
                    </button>
                    <span class="biz-arrow">Open <span data-icon="arrow-right" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg></span></span>
                </td>
            </tr>`;
    }

    function auditTableHtml(w) {
        if (!(w.audits || []).length) {
            return `<div class="card-pad muted text-sm" style="padding-top:0">No audits for this website yet.</div>`;
        }
        return `<table class="table">
            <thead><tr><th>Date</th><th>Score</th><th>Grade</th><th>Status</th><th></th></tr></thead>
            <tbody>${(w.audits || []).slice().reverse().map(auditRowHtml).join('')}</tbody>
        </table>`;
    }

    main.innerHTML = head + `
        ${chips ? `<div class="detail-list">${chips}</div>` : ''}
        <div class="mt-24"></div>
        ${addWebsiteForm}
        ${(biz.websites || []).length ? websiteCards : U.emptyState({ icon: 'globe', title: 'No websites yet', body: 'Add the business\'s first website to start auditing.' })}`;

    /* ---- Chart per website ---- */
    (biz.websites || []).forEach((w) => {
        const auditsAsc = (w.audits || []).slice();
        if (!auditsAsc.length) return;
        const labels = auditsAsc.map((a) => U.fmtDate(a.created_at));
        const scores = auditsAsc.map((a) => Number(a.overall_score));
        const pointColors = auditsAsc.map((a) => U.gradeColor(a.overall_grade));
        const grades = auditsAsc.map((a) => a.overall_grade);
        U.renderChart(`chart-${w.id}`, {
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label: 'Overall score',
                    data: scores,
                    borderColor: '#1d4ed8',
                    backgroundColor: 'rgba(29, 78, 216, .07)',
                    fill: true,
                    tension: 0.35,
                    borderWidth: 2.5,
                    pointRadius: 4.5,
                    pointHoverRadius: 6.5,
                    pointBackgroundColor: pointColors,
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 1.5,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                scales: {
                    y: { min: 0, max: 100, ticks: { stepSize: 20 }, grid: { color: '#eef1f7' }, border: { display: false } },
                    x: { grid: { display: false }, border: { display: false } },
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#101828',
                        padding: 12,
                        cornerRadius: 10,
                        titleFont: { weight: '600' },
                        callbacks: {
                            label: (ctx) => ` Score: ${U.fmtScore(ctx.parsed.y)} · Grade ${grades[ctx.dataIndex]}`,
                        },
                    },
                },
            },
        });
    });

    /* ---- Interactions ---- */
    main.querySelectorAll('tr.row-link').forEach((tr) => {
        tr.addEventListener('click', (e) => {
            if (e.target.closest('[data-delete-audit]')) return;
            window.location.hash = tr.dataset.href;
        });
        tr.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.target.closest('[data-delete-audit]')) window.location.hash = tr.dataset.href; });
    });

    main.querySelectorAll('[data-delete-audit]').forEach((btn) => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (!window.confirm('Delete this audit report? This cannot be undone.')) return;
            btn.disabled = true;
            try {
                await WVA.api.del(`/api/audits/${btn.dataset.deleteAudit}`);
                U.toast('Audit deleted.', 'success');
                const fresh = await WVA.api.get(`/api/businesses/${biz.id}`);
                renderBusiness(main, fresh);
            } catch (err) {
                btn.disabled = false;
                U.toast(err.message || 'Delete failed.', 'error');
            }
        });
    });

    main.querySelectorAll('[data-delete-website]').forEach((btn) => {
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const url = btn.dataset.websiteUrl || 'this website';
            if (!window.confirm(`Delete "${url}" and all of its audits? This cannot be undone.`)) return;
            btn.disabled = true;
            try {
                await WVA.api.del(`/api/websites/${btn.dataset.deleteWebsite}`);
                U.toast('Website deleted.', 'success');
                const fresh = await WVA.api.get(`/api/businesses/${biz.id}`);
                renderBusiness(main, fresh);
            } catch (err) {
                btn.disabled = false;
                U.toast(err.message || 'Delete failed.', 'error');
            }
        });
    });

    main.querySelectorAll('[data-rerun]').forEach((btn) => {
        btn.addEventListener('click', async () => {
            if (btn.disabled) return;
            btn.disabled = true;
            const originalLabel = btn.textContent;
            btn.textContent = 'Analyzing…';
            U.toast('Re-running audit — this can take up to 2 minutes on some sites…', 'info');
            try {
                // Returns almost instantly with status:"running" — the
                // actual crawl runs in the background (see routes.py).
                const started = await WVA.api.post(`/api/websites/${btn.dataset.rerun}/audits/rerun`);
                const audit = await WVA.api.pollAudit(started.id);
                if (audit.status === 'failed') {
                    throw new Error(audit.error_message || 'Audit could not be completed.');
                }
                U.toast(`Audit complete — score ${U.fmtScore(audit.overall_score)} (${audit.overall_grade}).`, 'success');
                const fresh = await WVA.api.get(`/api/businesses/${biz.id}`);
                renderBusiness(main, fresh);
            } catch (err) {
                btn.disabled = false;
                btn.textContent = originalLabel;
                U.toast(err.message || 'Re-run failed.', 'error');
            }
        });
    });

    const addForm = document.getElementById('add-website-form');
    if (addForm) {
        addForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const input = document.getElementById('new-website-url');
            const url = input.value.trim();
            if (!url) { input.focus(); return; }
            try {
                await WVA.api.post(`/api/businesses/${biz.id}/websites`, { url });
                U.toast('Website added.', 'success');
                const fresh = await WVA.api.get(`/api/businesses/${biz.id}`);
                renderBusiness(main, fresh);
            } catch (err) {
                U.toast(err.message || 'Could not add website.', 'error');
            }
        });
    }

    const editBtn = document.getElementById('edit-biz-btn');
    if (editBtn) editBtn.addEventListener('click', () => toggleEdit(main, biz));

    const deleteBtn = document.getElementById('delete-biz-btn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', async () => {
            if (!window.confirm(`Delete "${biz.name}" and all of its websites, audits and reports? This cannot be undone.`)) return;
            deleteBtn.disabled = true;
            try {
                await WVA.api.del(`/api/businesses/${biz.id}`);
                U.toast('Business deleted.', 'success');
                window.location.hash = '#/dashboard';
            } catch (err) {
                deleteBtn.disabled = false;
                U.toast(err.message || 'Delete failed.', 'error');
            }
        });
    }
}

/* ---------- Inline edit ---------- */
function toggleEdit(main, biz) {
    const U = WVA.ui;
    const existing = document.getElementById('biz-edit-panel');
    if (existing) { existing.remove(); return; }

    const inp = (id, label, value, opts) => {
        opts = opts || {};
        return `<div class="field ${opts.span2 ? 'span-2' : ''}">
            <label class="label" for="edit-${id}">${U.esc(label)}</label>
            ${opts.textarea
                ? `<textarea class="textarea" id="edit-${id}">${U.esc(value || '')}</textarea>`
                : `<input class="input" id="edit-${id}" type="text" value="${U.esc(value || '')}">`}
        </div>`;
    };

    const panel = document.createElement('div');
    panel.className = 'edit-panel';
    panel.id = 'biz-edit-panel';
    panel.innerHTML = `
        <h3 class="mb-16" style="font-size:15px">Edit business details</h3>
        <div class="form-grid">
            ${inp('name', 'Business Name', biz.name, { span2: true })}
            ${inp('location', 'Location', biz.location)}
            ${inp('category', 'Category', biz.category)}
            ${inp('service_area', 'Target Service Area', biz.service_area)}
            ${inp('primary_keywords', 'Primary Keywords', biz.primary_keywords)}
            ${inp('contact_name', 'Contact Name', biz.contact_name)}
            ${inp('contact_email', 'Contact Email', biz.contact_email)}
            ${inp('notes', 'Notes', biz.notes, { textarea: true, span2: true })}
        </div>
        <div class="form-actions">
            <button class="btn btn-ghost" id="edit-cancel">Cancel</button>
            <button class="btn btn-primary" id="edit-save">Save Changes</button>
        </div>`;

    const anchor = main.querySelector('.page-head');
    anchor.insertAdjacentElement('afterend', panel);
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    panel.querySelector('#edit-cancel').addEventListener('click', () => panel.remove());
    panel.querySelector('#edit-save').addEventListener('click', async () => {
        const get = (id) => panel.querySelector(`#edit-${id}`).value.trim();
        const body = {
            name: get('name') || biz.name,
            location: get('location'),
            category: get('category'),
            service_area: get('service_area'),
            primary_keywords: get('primary_keywords'),
            contact_name: get('contact_name'),
            contact_email: get('contact_email'),
            notes: get('notes'),
        };
        try {
            await WVA.api.put(`/api/businesses/${biz.id}`, body);
            U.toast('Business updated.', 'success');
            const fresh = await WVA.api.get(`/api/businesses/${biz.id}`);
            renderBusiness(main, fresh);
        } catch (err) {
            U.toast(err.message || 'Update failed.', 'error');
        }
    });
}