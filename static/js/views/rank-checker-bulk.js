/* #/rank-checker/bulk-scoring — upload a lead-list CSV/Excel file plus a
   keyword list (designated once for the whole upload, per the user's
   spec), check each row's business against Serper's organic + Maps APIs
   for every keyword combined with that row's own location, then hand
   back the same file with two columns appended per keyword ("<keyword>
   - Organic Rank", "<keyword> - Map Pack Rank"). Businesses created here
   use lead_source="rank_checker_csv" and are excluded from the main
   dashboard (see routes.py's list_businesses). Mirrors
   static/js/views/local-visibility-bulk.js's structure closely. */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.rankCheckerBulk = async function (main) {
    const U = WVA.ui;
    let resumedPoll = false;
    let defaultKeywords = [];

    main.innerHTML = pageHtml();
    try {
        const settings = await WVA.api.get('/api/rank-checker/settings');
        defaultKeywords = settings.default_keywords || [];
    } catch (e) { /* fine — keyword field just starts empty */ }
    const kwInput = main.querySelector('#rc-bulk-keywords');
    if (kwInput && defaultKeywords.length) kwInput.value = defaultKeywords.join(', ');
    wireUpload();
    await refreshJobs();

    function pageHtml() {
        return U.pageHead({
            title: 'Rank Checker Bulk Scoring',
            sub: 'Upload a lead list, check each business\'s keyword rankings via Serper.dev, and download the same file back with organic + Map Pack rank columns added.',
            back: { href: '#/rank-checker', label: 'Rank Checker Dashboard' },
        }) + `<div class="card card-pad form-card" id="rc-upload-card">
            <div class="logo-upload-title">Upload lead list (CSV or Excel)</div>
            <div class="text-sm muted mt-8">
                Needs a Business Name column and a Website column. Optional columns
                (Street Address, City, State, Zip, Phone, Email, First Name, Last Name)
                improve location accuracy and are detected automatically — every other
                column in your file is preserved as-is.
            </div>
            <div class="mt-16">
                <label class="label" for="rc-bulk-keywords">Keywords for this list (comma-separated)</label>
                <input class="input mt-8" id="rc-bulk-keywords" type="text" placeholder="e.g. tree trimming, stump removal, tree removal">
                <div class="text-sm muted mt-8">
                    Each keyword will be combined with every row's own city/state (or zip) to
                    build a location-based search, e.g. "tree trimming Austin, TX". Leave blank
                    to use the default keyword template from Settings.
                </div>
            </div>
            <div class="mt-16">
                <input type="file" id="rc-file" accept=".csv,.xlsx" hidden>
                <button type="button" class="btn btn-primary" id="rc-upload-btn">
                    <span data-icon="upload" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg></span>Upload File
                </button>
            </div>
            <div id="rc-active-progress"></div>
        </div>
        <div id="rc-jobs-holder" class="mt-16">${U.loading('Loading upload history…')}</div>`;
    }

    function wireUpload() {
        const fileInput = main.querySelector('#rc-file');
        const btn = main.querySelector('#rc-upload-btn');
        btn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', async () => {
            const file = fileInput.files && fileInput.files[0];
            if (!file) return;
            btn.disabled = true;
            try {
                const fd = new FormData();
                fd.append('file', file);
                fd.append('keywords', (main.querySelector('#rc-bulk-keywords').value || '').trim());
                /* NOTE: deliberately no Content-Type header — the browser must
                   set the multipart boundary. Raw fetch (not WVA.api, which
                   forces a JSON content-type whenever a body is present). */
                const res = await fetch('/api/rank-checker/upload', { method: 'POST', body: fd });
                let data = null;
                try { data = await res.json(); } catch (e) { /* no body */ }
                if (!res.ok) {
                    let msg = res.statusText || 'Upload failed';
                    if (data && data.detail) {
                        msg = typeof data.detail === 'string'
                            ? data.detail
                            : (Array.isArray(data.detail) ? data.detail.map(d => d.msg || JSON.stringify(d)).join('; ') : JSON.stringify(data.detail));
                    }
                    throw new Error(msg);
                }
                U.toast(`Checking ${data.total_rows} row${data.total_rows === 1 ? '' : 's'} across ${data.keywords.length} keyword${data.keywords.length === 1 ? '' : 's'} in the background — this can take a while (external API), feel free to navigate away and come back.`, 'success');
                resumedPoll = true;
                pollJob(data.job_id);
                await refreshJobs();
            } catch (err) {
                U.toast(err.message || 'Could not upload file.', 'error');
            } finally {
                btn.disabled = false;
                fileInput.value = '';
            }
        });
    }

    function progressBarHtml(job) {
        const pct = job.total_rows ? Math.round((job.processed_rows / job.total_rows) * 100) : 0;
        return `<div class="mt-8 text-sm">Checking… ${job.processed_rows}/${job.total_rows} (${pct}%)</div>
            <div style="background:var(--border);border-radius:6px;height:8px;overflow:hidden;margin-top:4px;max-width:420px;">
                <div style="background:var(--accent);height:100%;width:${pct}%;transition:width .3s;"></div>
            </div>`;
    }

    function pollJob(jobId) {
        const tick = async () => {
            if (!main.isConnected) return; // navigated away from this view
            let job;
            try {
                job = await WVA.api.get(`/api/rank-checker/jobs/${jobId}`);
            } catch (e) {
                return;
            }
            const holder = main.querySelector('#rc-active-progress');
            if (job.status === 'running') {
                if (holder) holder.innerHTML = progressBarHtml(job);
                setTimeout(tick, 2000);
            } else {
                if (holder) holder.innerHTML = '';
                await refreshJobs();
                if (job.status === 'completed') {
                    U.toast('Rank checking finished — download is ready.', 'success');
                } else if (job.status === 'failed') {
                    U.toast(job.error_message || 'Rank checking job failed.', 'error');
                }
            }
        };
        tick();
    }

    async function refreshJobs() {
        const holder = main.querySelector('#rc-jobs-holder');
        if (!holder) return;
        let jobs;
        try {
            jobs = await WVA.api.get('/api/rank-checker/jobs');
        } catch (e) {
            holder.innerHTML = U.errorState(e);
            return;
        }
        if (!jobs.length) {
            holder.innerHTML = U.emptyState({
                icon: 'file-text',
                title: 'No uploads yet',
                body: 'Upload a CSV or Excel file above to get started.',
            });
            return;
        }
        const rows = jobs.map((j) => {
            const pct = j.total_rows ? Math.round((j.processed_rows / j.total_rows) * 100) : 0;
            const statusBadge = j.status === 'completed'
                ? '<span class="badge badge-sm fg-x">completed</span>'
                : j.status === 'failed'
                    ? `<span class="badge badge-sm fg-x" title="${U.esc(j.error_message || '')}">failed</span>`
                    : `<span class="badge badge-sm fg-x">running · ${pct}%</span>`;
            const download = j.download_available
                ? `<a class="btn btn-secondary btn-sm" href="/api/rank-checker/jobs/${U.esc(j.id)}/download" download>Download</a>`
                : '<span class="muted">—</span>';
            const view = j.download_available
                ? `<button type="button" class="btn btn-secondary btn-sm rc-view-btn" data-job-id="${U.esc(j.id)}">View</button>`
                : '';
            return `<tr class="rc-job-row" data-job-id="${U.esc(j.id)}">
                <td>${U.esc(j.filename || '—')}</td>
                <td class="tabular">${U.esc(U.fmtDateTime(j.created_at))}</td>
                <td>${statusBadge}</td>
                <td class="tabular">${j.processed_rows}/${j.total_rows}</td>
                <td style="white-space:nowrap;">${view} ${download}</td>
            </tr>
            <tr class="rc-results-row" data-job-id="${U.esc(j.id)}" style="display:none;">
                <td colspan="5"></td>
            </tr>`;
        }).join('');
        holder.innerHTML = `<div class="table-wrap">
            <table class="table">
                <thead><tr><th>File</th><th>Uploaded</th><th>Status</th><th>Rows</th><th>Actions</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;

        holder.querySelectorAll('.rc-view-btn').forEach((btn) => {
            btn.addEventListener('click', () => toggleResults(btn.dataset.jobId, btn));
        });

        if (!resumedPoll) {
            const running = jobs.find((j) => j.status === 'running');
            if (running) {
                resumedPoll = true;
                pollJob(running.id);
            }
        }
    }

    async function toggleResults(jobId, btn) {
        const holder = main.querySelector('#rc-jobs-holder');
        const resultsRow = holder.querySelector(`.rc-results-row[data-job-id="${cssEscape(jobId)}"]`);
        if (!resultsRow) return;
        const cell = resultsRow.querySelector('td');
        const isOpen = resultsRow.style.display !== 'none';
        if (isOpen) {
            resultsRow.style.display = 'none';
            btn.textContent = 'View';
            return;
        }
        resultsRow.style.display = '';
        btn.textContent = 'Hide';
        if (!cell.dataset.loaded) {
            cell.innerHTML = `<div class="mt-8">${U.loading('Loading results…')}</div>`;
            try {
                const data = await WVA.api.get(`/api/rank-checker/jobs/${jobId}/results`);
                cell.innerHTML = resultsTableHtml(data);
                cell.dataset.loaded = '1';
            } catch (e) {
                cell.innerHTML = U.errorState(e);
            }
        }
    }

    function cssEscape(s) {
        return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/["\\]/g, '\\$&');
    }

    function resultsTableHtml(data) {
        const cols = data.columns || [];
        const rows = data.rows || [];
        if (!cols.length || !rows.length) {
            return '<div class="text-sm muted mt-8">No results to show.</div>';
        }
        const head = cols.map((c) => `<th>${U.esc(c)}</th>`).join('');
        const body = rows.map((r) => {
            const cells = cols.map((c) => `<td>${U.esc(r[c] == null ? '' : String(r[c]))}</td>`).join('');
            return `<tr>${cells}</tr>`;
        }).join('');
        return `<div class="mt-8 table-wrap" style="max-height:420px;overflow:auto;">
            <table class="table">
                <thead><tr>${head}</tr></thead>
                <tbody>${body}</tbody>
            </table>
        </div>`;
    }
};
