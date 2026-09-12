/* #/settings, #/settings/branding, #/settings/scoring, #/settings/embed */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.settings = async function (main, params) {
    const U = WVA.ui;
    const tab = ['branding', 'scoring', 'embed', 'rank-checker'].includes(params.tab) ? params.tab : 'branding';
    main.innerHTML = U.loading('Loading settings…');

    const tabsHtml = `
        <div class="tabs" role="tablist" aria-label="Settings sections">
            <a class="tab-btn ${tab === 'branding' ? 'active' : ''}" role="tab" aria-selected="${tab === 'branding'}" href="#/settings/branding">Branding</a>
            <a class="tab-btn ${tab === 'scoring' ? 'active' : ''}" role="tab" aria-selected="${tab === 'scoring'}" href="#/settings/scoring">Scoring Weights</a>
            <a class="tab-btn ${tab === 'embed' ? 'active' : ''}" role="tab" aria-selected="${tab === 'embed'}" href="#/settings/embed">Embed Widget</a>
            <a class="tab-btn ${tab === 'rank-checker' ? 'active' : ''}" role="tab" aria-selected="${tab === 'rank-checker'}" href="#/settings/rank-checker">Rank Checker</a>
        </div>`;

    main.innerHTML = U.pageHead({
        title: 'Settings',
        sub: 'Agency branding for client-facing reports, lead-gen widget embedding, scoring weights for future audits, and the Rank Checker default keyword template.',
    }) + tabsHtml + `<div id="tab-body">${U.loading('Loading…')}</div>`;

    const body = main.querySelector('#tab-body');
    if (tab === 'branding') await renderBrandingTab(body);
    else if (tab === 'embed') renderEmbedTab(body);
    else if (tab === 'rank-checker') await renderRankCheckerTab(body);
    else await renderScoringTab(body);
};

/* ---------- Rank Checker tab ---------- */
async function renderRankCheckerTab(body) {
    const U = WVA.ui;
    let settings;
    try {
        settings = await WVA.api.get('/api/rank-checker/settings');
    } catch (e) {
        body.innerHTML = U.errorState(e);
        return;
    }
    const keywords = settings.default_keywords || [];

    body.innerHTML = `
    <div class="note-card">
        <span data-icon="info" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg></span>
        <span><strong>Default keyword template.</strong> Used by the Rank Checker's Bulk Scoring upload and GHL webhook when no keyword list is provided for a specific run (e.g. the manual check form pre-fills these, but you can add/remove keywords per check). Each keyword is combined with a business's own city/state or zip to build a location-based search, since Google Map Pack results are hyperlocal.</span>
    </div>
    <form id="rank-checker-settings-form" class="card card-pad form-card mt-16">
        <div class="logo-upload-title">Default Keywords</div>
        <div id="rc-settings-keyword-rows" class="mt-16" style="display:flex;flex-direction:column;gap:8px;"></div>
        <button type="button" class="btn btn-secondary btn-sm mt-8" id="rc-settings-add-keyword">+ Add keyword</button>
        <div class="form-actions mt-16">
            <button type="submit" class="btn btn-primary">Save Keywords</button>
        </div>
    </form>`;

    const rowsHolder = body.querySelector('#rc-settings-keyword-rows');
    function addRow(value) {
        const row = document.createElement('div');
        row.style.cssText = 'display:flex;gap:8px;align-items:center;';
        row.innerHTML = `<input class="input rc-settings-keyword-input" type="text" placeholder="e.g. tree trimming" value="${U.esc(value || '')}" style="flex:1;">
            <button type="button" class="btn btn-secondary btn-sm rc-settings-remove-keyword">Remove</button>`;
        row.querySelector('.rc-settings-remove-keyword').addEventListener('click', () => row.remove());
        rowsHolder.appendChild(row);
    }
    (keywords.length ? keywords : ['', '', '']).forEach(addRow);
    body.querySelector('#rc-settings-add-keyword').addEventListener('click', () => addRow(''));

    body.querySelector('#rank-checker-settings-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const values = Array.from(body.querySelectorAll('.rc-settings-keyword-input'))
            .map((el) => el.value.trim())
            .filter(Boolean);
        try {
            await WVA.api.put('/api/rank-checker/settings', { default_keywords: values });
            U.toast('Default keywords saved.', 'success');
        } catch (err) {
            U.toast(err.message || 'Could not save keywords.', 'error');
        }
    });
}

/* ---------- Branding tab ---------- */
async function renderBrandingTab(body) {
    const U = WVA.ui;
    const data = await WVA.api.get('/api/settings/branding');

    const inp = (id, label, value, opts) => {
        opts = opts || {};
        return `<div class="field ${opts.span2 ? 'span-2' : ''}">
            <label class="label" for="b-${id}">${U.esc(label)}</label>
            <input class="input" id="b-${id}" type="text" value="${U.esc(value || '')}" placeholder="${U.esc(opts.ph || '')}">
            ${opts.hint ? `<div class="hint">${U.esc(opts.hint)}</div>` : ''}
        </div>`;
    };

    const logoPreview = data.logo_url
        ? `<img class="logo-preview-img" src="${U.esc(data.logo_url)}" alt="Company logo preview">`
        : `<span class="logo-preview-empty">No logo yet —<br>a styled text logo is used</span>`;

    body.innerHTML = `
    <div class="note-card">
        <span data-icon="info" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg></span>
        <span>These details appear on client-facing reports (full report footer and prospect snapshot CTA) and on the public lead-gen widget, so prospects always know who prepared the audit.</span>
    </div>

    <div class="card card-pad form-card" id="logo-card">
        <div class="logo-upload-row">
            <div class="logo-preview" id="logo-preview" aria-live="polite">${logoPreview}</div>
            <div class="logo-upload-info">
                <div class="logo-upload-title">Company Logo</div>
                <div class="hint">Shown at the top of the public audit widget and on shared reports. Accepted: PNG, JPG, SVG, or WEBP.</div>
                <input type="file" id="logo-file" accept=".png,.jpg,.jpeg,.svg,.webp" hidden>
                <button type="button" class="btn btn-secondary mt-8" id="logo-upload-btn">
                    <span data-icon="upload" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg></span>Upload Logo
                </button>
            </div>
        </div>
    </div>

    <form class="card card-pad form-card mt-16" id="branding-form">
        <div class="form-grid">
            ${inp('company_name', 'Company Name', data.company_name, { ph: 'Netclix Marketing' })}
            ${inp('phone', 'Phone', data.phone, { ph: '208-841-5531' })}
            ${inp('email', 'Email', data.email, { ph: 'dev@netclixmarketing.com' })}
            ${inp('website', 'Website', data.website, { ph: 'https://netclixmarketing.com' })}
            ${inp('from_email', 'Sender Email (for Resend)', data.from_email, { span2: true, ph: 'reports@yourdomain.com', hint: "Leave blank to use Resend's shared test sender. Set this once your sending domain is verified in Resend." })}
            ${inp('contact_form_url', 'Contact Form URL', data.contact_form_url, { ph: 'https://…/contact', span2: true, hint: 'Used as the prospect snapshot CTA destination when set (highest priority).' })}
            ${inp('scheduling_url', 'Scheduling URL', data.scheduling_url, { ph: 'https://calendly.com/…', span2: true })}
            ${inp('cta_headline', 'CTA Headline', data.cta_headline, { span2: true, ph: "Want to see what's holding your website back?" })}
            ${inp('cta_button_text', 'CTA Button Text', data.cta_button_text, { span2: true, ph: 'Request Your Full Audit' })}
            ${inp('widget_heading', 'Widget Heading', data.widget_heading, { ph: 'Audit Your Website Now!', hint: 'Large heading shown at the top of the public embeddable widget.' })}
            ${inp('widget_button_text', 'Widget Button Text', data.widget_button_text, { ph: 'Check', hint: 'Label for the submit button on the public widget.' })}
        </div>
        <div class="form-actions">
            <button type="submit" class="btn btn-primary">Save Branding</button>
        </div>
    </form>`;

    /* --- Logo upload --- */
    const logoInput = body.querySelector('#logo-file');
    body.querySelector('#logo-upload-btn').addEventListener('click', () => logoInput.click());
    logoInput.addEventListener('change', async () => {
        const file = logoInput.files && logoInput.files[0];
        if (!file) return;
        const btn = body.querySelector('#logo-upload-btn');
        btn.disabled = true;
        try {
            const fd = new FormData();
            fd.append('file', file);
            /* NOTE: deliberately no Content-Type header — the browser must set
               the multipart boundary. Uses raw fetch (not WVA.api, which forces
               a JSON content-type whenever a body is present). */
            const res = await fetch('/api/settings/branding/logo', { method: 'POST', body: fd });
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
            const preview = body.querySelector('#logo-preview');
            preview.innerHTML = `<img class="logo-preview-img" src="${U.esc(data.logo_url)}" alt="Company logo preview">`;
            U.toast('Logo updated — it now appears on the public widget and reports.', 'success');
        } catch (err) {
            U.toast(err.message || 'Could not upload logo.', 'error');
        } finally {
            btn.disabled = false;
            logoInput.value = '';
        }
    });

    /* --- Branding form --- */
    body.querySelector('#branding-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const get = (id) => body.querySelector('#b-' + id).value.trim();
        const payload = {
            company_name: get('company_name'),
            phone: get('phone'),
            email: get('email'),
            from_email: get('from_email'),
            website: get('website'),
            contact_form_url: get('contact_form_url'),
            scheduling_url: get('scheduling_url'),
            cta_headline: get('cta_headline'),
            cta_button_text: get('cta_button_text'),
            widget_heading: get('widget_heading'),
            widget_button_text: get('widget_button_text'),
        };
        try {
            await WVA.api.put('/api/settings/branding', payload);
            U.toast('Branding saved — new reports will use these details.', 'success');
        } catch (err) {
            U.toast(err.message || 'Could not save branding.', 'error');
        }
    });
}

/* ---------- Embed Widget tab ---------- */
function renderEmbedTab(body) {
    const U = WVA.ui;
    const origin = window.location.origin;
    const snippet = `<iframe src="${origin}/widget" width="100%" height="720" frameborder="0" style="border:none; max-width:600px;"></iframe>`;

    body.innerHTML = `
    <div class="note-card">
        <span data-icon="info" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg></span>
        <span>Paste this snippet into any website to embed the public lead-generation widget. Visitors get an instant audit, and every submission is saved to your dashboard with a <strong>Lead</strong> badge.</span>
    </div>
    <div class="card card-pad form-card">
        <div class="embed-head">
            <div>
                <div class="embed-title">Embeddable Audit Widget</div>
                <div class="hint">Paste this snippet into any website or landing page. Branding, heading, and button text follow your Branding settings.</div>
            </div>
            <div class="embed-actions">
                <a class="btn btn-secondary" href="/widget" target="_blank" rel="noopener">Preview</a>
                <button type="button" class="btn btn-primary" id="copy-embed-btn">Copy Embed Code</button>
            </div>
        </div>
        <pre class="embed-code" id="embed-code" tabindex="0" aria-label="Iframe embed snippet (read-only)">${U.esc(snippet)}</pre>
    </div>`;

    body.querySelector('#copy-embed-btn').addEventListener('click', async () => {
        const ok = await U.copyText(snippet);
        U.toast(ok ? 'Embed code copied to clipboard.' : 'Could not copy — please select the code manually.', ok ? 'success' : 'error');
    });
}

/* ---------- Scoring weights tab ---------- */
async function renderScoringTab(body) {
    const U = WVA.ui;
    const configs = await WVA.api.get('/api/settings/scoring');

    const rows = configs.map((c, i) => `
        <div class="weight-row">
            <div>
                <div class="weight-name">${U.esc(c.category_name)}</div>
                <div class="hint">Current: ${Math.round(c.weight * 1000) / 10}%</div>
            </div>
            <div class="weight-input-wrap">
                <input class="weight-input" type="number" min="0" max="100" step="0.1"
                    data-key="${U.esc(c.category_key)}" value="${Math.round(c.weight * 1000) / 10}"
                    aria-label="Weight for ${U.esc(c.category_name)} in percent">
                <span class="weight-pct">%</span>
            </div>
        </div>`).join('');

    body.innerHTML = `
    <div class="note-card">
        <span data-icon="info" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg></span>
        <span><strong>Weights are automatically normalized to sum to 100%.</strong> Changes affect future audits only — existing audit scores don't change retroactively.</span>
    </div>
    <form id="scoring-form">
        <div class="card">
            ${rows}
            <div class="total-bar" id="total-bar">
                <span>Weight total</span>
                <span class="total-val" id="total-val">0%</span>
            </div>
        </div>
        <div class="form-actions mt-16">
            <button type="submit" class="btn btn-primary">Save Weights</button>
        </div>
    </form>`;

    const inputs = Array.from(body.querySelectorAll('.weight-input'));
    const totalBar = body.querySelector('#total-bar');
    const totalValEl = body.querySelector('#total-val');

    function updateTotal() {
        const total = inputs.reduce((sum, el) => sum + (parseFloat(el.value) || 0), 0);
        const rounded = Math.round(total * 10) / 10;
        totalValEl.textContent = rounded + '%';
        totalBar.classList.toggle('ok', Math.abs(rounded - 100) <= 0.5);
        totalBar.classList.toggle('off', Math.abs(rounded - 100) > 0.5);
    }
    inputs.forEach((el) => el.addEventListener('input', updateTotal));
    updateTotal();

    body.querySelector('#scoring-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const total = inputs.reduce((sum, el) => sum + (parseFloat(el.value) || 0), 0);
        if (total <= 0) {
            U.toast('Total weight must be greater than 0.', 'error');
            return;
        }
        const weights = {};
        configs.forEach((c, i) => {
            const v = parseFloat(inputs[i].value);
            weights[c.category_key] = (isNaN(v) ? 0 : v) / 100;
        });
        try {
            const updated = await WVA.api.put('/api/settings/scoring', { weights });
            U.toast('Scoring weights saved and normalized to 100%.', 'success');
            // Re-sync inputs with normalized server values
            updated.forEach((u, i) => {
                const el = inputs[i];
                if (el && u.category_key === configs[i].category_key) {
                    el.value = Math.round(u.weight * 1000) / 10;
                }
            });
            updateTotal();
        } catch (err) {
            U.toast(err.message || 'Could not save weights.', 'error');
        }
    });
}
