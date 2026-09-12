/* #/create-audit — new audit form + analyzing checklist animation */
window.WVA = window.WVA || {};
WVA.views = WVA.views || {};

WVA.views.createAudit = function (main) {
    const U = WVA.ui;

    const field = (id, label, opts) => {
        opts = opts || {};
        return `<div class="field ${opts.span2 ? 'span-2' : ''}">
            <label class="label" for="${id}">${U.esc(label)}${opts.required ? ' <span class="req">*</span>' : ' <span class="muted" style="font-weight:500">(optional)</span>'}</label>
            ${opts.textarea
                ? `<textarea class="textarea" id="${id}" name="${id}" placeholder="${U.esc(opts.ph || '')}"></textarea>`
                : `<input class="input" id="${id}" name="${id}" type="${opts.type || 'text'}" placeholder="${U.esc(opts.ph || '')}" ${opts.required ? 'required' : ''} ${opts.autocomplete ? `autocomplete="${opts.autocomplete}"` : ''}>`}
            ${opts.hint ? `<div class="hint">${U.esc(opts.hint)}</div>` : ''}
        </div>`;
    };

    main.innerHTML = U.pageHead({
        title: 'Create New Website Audit',
        sub: 'Enter a website URL to generate a full visibility audit. Add business details to personalize the reports.',
        back: { href: '#/dashboard', label: 'Dashboard' },
    }) + `
    <form class="card card-pad form-card" id="audit-form" novalidate>
        <div class="form-grid">
            ${field('website_url', 'Website URL', { required: true, ph: 'https://example.com', span2: true, hint: 'We\'ll analyze this domain. Enter it with or without https://.' })}
            ${field('business_name', 'Business Name', { ph: 'e.g. Grand Finale Detailing' })}
            ${field('location', 'Location', { ph: 'e.g. Rochester, NY' })}
            ${field('category', 'Primary Business Category', { ph: 'e.g. Auto Detailing' })}
            ${field('service_area', 'Target Service Area', { ph: 'e.g. Monroe County, NY' })}
            ${field('primary_keywords', 'Primary Keywords', { ph: 'e.g. car detailing rochester ny', span2: true })}
            ${field('contact_name', 'Contact Name', { ph: 'e.g. Jane Smith' })}
            ${field('contact_email', 'Contact Email', { type: 'email', ph: 'name@business.com' })}
            ${field('notes', 'Notes', { textarea: true, ph: 'Anything useful — goals, competitors, context…' })}
        </div>
        <div class="form-actions">
            <button type="submit" class="btn btn-primary btn-lg">
                <span data-icon="zap" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg></span>Start Audit
            </button>
        </div>
    </form>`;

    const form = document.getElementById('audit-form');
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const urlInput = form.querySelector('#website_url');
        const url = urlInput.value.trim();
        if (!url) {
            urlInput.focus();
            urlInput.style.borderColor = 'var(--bad)';
            U.toast('Website URL is required.', 'error');
            return;
        }
        const val = (id) => { const v = form.querySelector('#' + id).value.trim(); return v || null; };
        const body = {
            website_url: url,
            business_name: val('business_name'),
            location: val('location'),
            category: val('category'),
            service_area: val('service_area'),
            primary_keywords: val('primary_keywords'),
            contact_name: val('contact_name'),
            contact_email: val('contact_email'),
            notes: val('notes'),
        };

        showAnalyzing(main, url);
        try {
            const audit = await WVA.api.post('/api/audits', body);
            // The endpoint now returns almost instantly with status:"running"
            // (the actual crawl runs in the background — see routes.py).
            // Navigate straight to the audit page; it knows how to show a
            // "still analyzing" state and poll until real results land.
            window.location.hash = `#/audit/${audit.id}`;
        } catch (err) {
            U.toast(err.message || 'Audit failed.', 'error');
            // Restore the form
            WVA.views.createAudit(main);
            const f2 = document.getElementById('audit-form');
            f2.querySelector('#website_url').value = url;
            U.toast('Audit could not be completed. Check the URL and try again.', 'error');
        }
    });
};

/* Sequential checklist animation while the backend runs */
function showAnalyzing(main, url) {
    const U = WVA.ui;
    const steps = [
        'Checking technical SEO',
        'Checking page structure',
        'Checking performance',
        'Checking AI readiness',
        'Checking local signals',
        'Checking links',
        'Building recommendations',
    ];
    main.innerHTML = `
        <div class="analyzing" role="status" aria-live="polite">
            <div class="pulse-ring"><span data-icon="search" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" width="30" height="30"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></span></div>
            <h2>Analyzing website…</h2>
            <p class="an-sub">${U.esc(url)}</p>
            <ul class="checklist">
                ${steps.map((s) => `<li><span class="li-ico"><span class="spinner" style="width:15px;height:15px;border-width:2px;margin:0"></span></span>${U.esc(s)}</li>`).join('')}
            </ul>
        </div>`;

    const items = main.querySelectorAll('.checklist li');
    let i = 0;
    const tick = () => {
        if (i >= items.length) return;
        items[i].classList.add('done');
        items[i].querySelector('.li-ico').innerHTML = `<span data-icon="check" aria-hidden="true"><svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><polyline points="20 6 9 17 4 12"/></svg></span>`;
        i += 1;
        U.after(230, tick);
    };
    U.after(150, tick);
}