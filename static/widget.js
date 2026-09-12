/* ==========================================================================
   Public embeddable widget logic — fully self-contained.
   Deliberately does NOT use the admin app's app.js/ui.js/api.js so the page
   can be embedded in third-party <iframe>s without style/script conflicts.
   Branding is white-label ready: nothing is hardcoded to a specific company;
   everything is pulled from GET /api/settings/branding (a ?brand=slug query
   param is forwarded for future multi-tenant branding profiles).
   ========================================================================== */
(function () {
    'use strict';

    var TIMEOUT_MS = 300000; // PSI mobile+desktop run strictly sequentially, 100s/call with up to 1 retry each (see audit_engine/google_apis.py) -- worst case ~400s before scoring; real full audits observed taking ~162s. Previously 150000, which was too tight and caused the widget to show a false "taking longer than expected" error while the background audit went on to complete successfully seconds later.

    /* ---------- helpers ---------- */
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    function $(id) { return document.getElementById(id); }

    function fmtScore(n) {
        var v = Number(n);
        if (n === null || n === undefined || isNaN(v)) return '—';
        return Number.isInteger(v) ? String(v) : String(Math.round(v * 10) / 10);
    }

    /* Grade scale — kept in sync with the main app's ui.js */
    var GRADE_THRESHOLDS = [
        [97, 'A+'], [93, 'A'], [90, 'A-'], [87, 'B+'], [83, 'B'], [80, 'B-'],
        [77, 'C+'], [73, 'C'], [70, 'C-'], [67, 'D+'], [63, 'D'], [60, 'D-'], [0, 'F']
    ];
    function gradeForScore(score) {
        var s = Number(score) || 0;
        for (var i = 0; i < GRADE_THRESHOLDS.length; i++) {
            if (s >= GRADE_THRESHOLDS[i][0]) return GRADE_THRESHOLDS[i][1];
        }
        return 'F';
    }
    function gradeFamily(grade) {
        if (!grade) return 'x';
        var ch = String(grade).charAt(0).toUpperCase();
        return ['A', 'B', 'C', 'D', 'F'].indexOf(ch) !== -1 ? ch : 'x';
    }
    var GRADE_HEX = { A: '#16a34a', B: '#0d9488', C: '#d97706', D: '#ea580c', F: '#dc2626', x: '#64748b' };
    function gradeColorHex(grade) { return GRADE_HEX[gradeFamily(grade)] || GRADE_HEX.x; }

    /* ---------- state ---------- */
    var BRANDING = null;
    var analyzing = false;
    var FORM_HTML = null; /* captured at boot so errors/reset can restore the form */

    /* ---------- branding ---------- */
    function brandingUrl() {
        // ?brand=slug is ignored by the API today but forwarded so a future
        // multi-tenant branding profile can be selected without changes here.
        try {
            var slug = new URLSearchParams(window.location.search).get('brand');
            return '/api/settings/branding' + (slug ? '?brand=' + encodeURIComponent(slug) : '');
        } catch (e) {
            return '/api/settings/branding';
        }
    }

    function renderLogo(companyName, logoUrl) {
        var slot = $('wv-logo-slot');
        if (logoUrl) {
            var img = document.createElement('img');
            img.src = logoUrl;
            img.alt = (companyName || 'Company') + ' logo';
            slot.textContent = '';
            slot.appendChild(img);
            return;
        }
        /* Styled stacked text-logotype fallback so the widget still looks
           polished when no logo has been uploaded. */
        var name = String(companyName || 'Website Visibility Audit').trim();
        var words = name.split(/\s+/).filter(Boolean);
        var first = (words.shift() || 'Audit').toUpperCase();
        var rest = words.join(' ').toUpperCase();
        slot.innerHTML =
            '<span class="wv-logotype">' +
                '<span class="wv-logotype-mark">' + esc(first.charAt(0)) + '</span>' +
                '<span class="wv-logotype-text"><strong>' + esc(first) + '</strong>' +
                (rest ? '<span>' + esc(rest) + '</span>' : '') +
                '</span>' +
            '</span>';
    }

    function applyBranding(b) {
        b = b || {};
        BRANDING = b;
        var company = b.company_name || '';

        renderLogo(company, b.logo_url);

        if (b.widget_heading) {
            $('wv-heading').textContent = b.widget_heading;
        }
        if (b.widget_button_text) {
            $('wv-submit-text').textContent = b.widget_button_text;
        }
        document.title = company ? company + ' · Website Audit' : 'Website Visibility Audit';

        var foot = $('wv-pagefoot');
        foot.textContent = company ? ('Powered by ' + company) : '';
    }

    function loadBranding() {
        return fetch('/api/settings/branding', { headers: { Accept: 'application/json' } })
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (b) { applyBranding(b); })
            .catch(function () {
                /* Branding fetch is non-fatal: defaults keep the widget usable. */
                applyBranding({});
            });
    }

    /* ---------- validation ---------- */
    function stripScheme(url) {
        return String(url || '').trim().replace(/^https?:\/\//i, '').replace(/^\/+/, '');
    }
    function looksLikeDomain(url) {
        var v = stripScheme(url);
        return /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+(:\d+)?(\/.*)?$/i.test(v);
    }
    function looksLikeEmail(v) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(v || '').trim());
    }

    function setFieldError(fieldId, errId, msg) {
        var field = $(fieldId);
        var err = $(errId);
        if (msg) {
            field.classList.add('wv-invalid');
            err.textContent = msg;
            return true;
        }
        field.classList.remove('wv-invalid');
        err.textContent = '';
        return false;
    }

    function validate() {
        var url = $('wv-url').value.trim();
        var fn = $('wv-fn').value.trim();
        var email = $('wv-email').value.trim();

        var bad = false;
        var urlMsg = '';
        if (!url) urlMsg = 'Website URL is required.';
        else if (!looksLikeDomain(url)) urlMsg = 'Enter a valid website address, e.g. yourcompany.com.';
        if (setFieldError('wv-field-url', 'wv-err-url', urlMsg)) bad = true;

        if (setFieldError('wv-field-fn', 'wv-err-fn', fn ? '' : 'First name is required.')) bad = true;

        var emailMsg = '';
        if (!email) emailMsg = 'Email is required.';
        else if (!looksLikeEmail(email)) emailMsg = 'Enter a valid email address.';
        if (setFieldError('wv-field-email', 'wv-err-email', emailMsg)) bad = true;

        return !bad;
    }

    function clearAlert() {
        var al = $('wv-alert');
        al.classList.remove('show');
        $('wv-alert-msg').textContent = '';
        $('wv-alert-title').textContent = 'Something went wrong';
    }

    function showAlert(title, msg, retryable) {
        $('wv-alert-title').textContent = title || 'Something went wrong';
        $('wv-alert-msg').textContent = msg || '';
        $('wv-alert-retry').style.display = retryable === false ? 'none' : '';
        $('wv-alert').classList.add('show');
    }

    /* ---------- submission ---------- */
    function setSubmitting(on) {
        analyzing = on;
        var btn = $('wv-submit');
        var txt = $('wv-submit-text');
        if (!btn || !txt) return; /* DOM may have been swapped to results */
        btn.disabled = on;
        if (on) {
            btn.dataset.origText = txt.textContent;
            txt.textContent = 'Analyzing…';
            var arrow = btn.querySelector('.wv-arrow');
            if (arrow) arrow.style.display = 'none';
        } else {
            txt.textContent = btn.dataset.origText || (BRANDING && BRANDING.widget_button_text) || 'Check';
            var arrow2 = btn.querySelector('.wv-arrow');
            if (arrow2) arrow2.style.display = '';
        }
    }

    function showAnalyzing() {
        $('wv-body').innerHTML =
            '<div class="wv-analyzing" role="status">' +
                '<div class="wv-analyzing-ring">' +
                    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
                    '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>' +
                '</div>' +
                '<h2>Analyzing your website…</h2>' +
                '<p>Scoring 7 categories including SEO, performance and AI readiness.<br>This can take up to 2 minutes on some sites — hang tight.</p>' +
            '</div>';
    }

    function submitAudit() {
        var payload = {
            website_url: $('wv-url').value.trim(),
            business_name: $('wv-biz').value.trim() || null,
            first_name: $('wv-fn').value.trim(),
            last_name: $('wv-ln').value.trim() || null,
            email: $('wv-email').value.trim(),
            phone: $('wv-phone').value.trim() || null
        };

        clearAlert();
        setSubmitting(true);
        showAnalyzing();

        // /api/widget/audit now returns almost instantly with
        // status:"running" -- the actual crawl (which can take up to ~2
        // minutes on slow sites: JS rendering + two sequential PageSpeed
        // Insights calls) runs in the background on the server. We poll
        // GET /api/audits/{id} instead of holding one long-lived request
        // open. This matters because this widget is embedded on a public
        // page behind a reverse proxy (Cloudflare) with its own hard
        // ceiling on how long it will wait for a single response --
        // holding the connection open for the full ~2 minutes previously
        // risked a proxy-level timeout with no useful error message,
        // regardless of anyone's client-side timeout budget.
        var startCtrl = ('AbortController' in window) ? new AbortController() : null;
        var startTimer = startCtrl ? setTimeout(function () { startCtrl.abort(); }, 20000) : null;
        var startOpts = {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify(payload)
        };
        if (startCtrl) startOpts.signal = startCtrl.signal;

        fetch('/api/widget/audit', startOpts)
            .then(function (res) {
                return res.json().catch(function () { return null; }).then(function (data) {
                    if (res.ok && data) return data;
                    var msg = (data && data.detail && typeof data.detail === 'string') ? data.detail
                        : (res.status === 429 ? 'Too many requests — please try again shortly.'
                            : 'The audit could not be started. Please double-check your website address and try again.');
                    var err = new Error(msg);
                    err.userMessage = msg;
                    throw err;
                });
            })
            .then(function (started) {
                return pollAuditStatus(started.audit_id, TIMEOUT_MS).then(function (audit) {
                    if (audit.status === 'failed') {
                        throw new Error('fallback');
                    }
                    return fetch('/api/audits/' + encodeURIComponent(started.audit_id) + '/report?mode=prospect', { headers: { Accept: 'application/json' } })
                        .then(function (res) { return res.json(); })
                        .then(function (snapshot) {
                            snapshot.share_token = started.share_token;
                            return snapshot;
                        });
                });
            })
            .then(function (data) { renderResults(data); })
            .catch(function () {
                // Fail-safe: whatever went wrong (start request failed,
                // network error, backend audit failure, or the poll simply
                // ran past TIMEOUT_MS while the audit kept working in the
                // background), never show the visitor a scary/technical
                // error. The audit's own background thread finishes and
                // emails the report the moment it completes (see
                // _send_widget_emails in routes.py) independent of whether
                // this tab is still open/polling, so this single reassuring
                // message is always the honest, safe thing to show.
                showFallbackMessage();
            })
            .finally(function () {
                if (startTimer) clearTimeout(startTimer);
                setSubmitting(false);
            });
    }

    /* Poll GET /api/audits/{id} every few seconds until status leaves
       "running" (or maxWaitMs elapses). This is a plain, self-contained
       loop -- the widget deliberately avoids depending on the main app's
       api.js (see file header), so it can't reuse WVA.api.pollAudit. */
    function pollAuditStatus(auditId, maxWaitMs) {
        var intervalMs = 3000;
        var startedAt = Date.now();
        function tick() {
            return fetch('/api/audits/' + encodeURIComponent(auditId), { headers: { Accept: 'application/json' } })
                .then(function (res) { return res.json(); })
                .then(function (audit) {
                    if (audit.status !== 'running') return audit;
                    if (Date.now() - startedAt > maxWaitMs) {
                        throw new Error('fallback');
                    }
                    return new Promise(function (resolve) { setTimeout(resolve, intervalMs); }).then(tick);
                });
        }
        return tick();
    }

    function showFallbackMessage() {
        /* Restore the form (fields keep their values) and show a single,
           reassuring, non-alarming message -- never a technical error --
           regardless of what actually went wrong (start request failed,
           network drop, backend audit failure, or just a slow site that
           outran TIMEOUT_MS while still working in the background). */
        var body = $('wv-body');
        if (!$('wv-form')) {
            body.innerHTML = FORM_HTML;
            wireForm();
            applyBranding(BRANDING || {});
        }
        showAlert('Your report is on its way', 'The report is taking longer than usual. The report will be emailed to you as soon as it\'s completed.', false);
    }

    /* ---------- results rendering ---------- */
    function scoreRingSvg(score, grade) {
        var size = 112, stroke = 9;
        var r = (size - stroke) / 2;
        var circ = 2 * Math.PI * r;
        var pct = Math.max(0, Math.min(100, Number(score) || 0)) / 100;
        var col = gradeColorHex(grade);
        var cy = size / 2;
        var subY = cy + size * 0.17;
        return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '" role="img" aria-label="Overall score ' + esc(fmtScore(score)) + ' out of 100, grade ' + esc(grade) + '">' +
            '<circle class="wv-ring-track" cx="' + cy + '" cy="' + cy + '" r="' + r + '" fill="none" stroke-width="' + stroke + '"/>' +
            '<circle cx="' + cy + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="' + col + '" stroke-width="' + stroke + '" stroke-linecap="round"' +
            ' stroke-dasharray="' + circ.toFixed(2) + '" stroke-dashoffset="' + (circ * (1 - pct)).toFixed(2) + '" transform="rotate(-90 ' + cy + ' ' + cy + ')"/>' +
            '<text x="50%" y="50%" class="wv-ring-num" font-size="30" dominant-baseline="central" text-anchor="middle" dy=".05em">' + esc(fmtScore(score)) + '</text>' +
            '<text x="50%" y="' + subY + '" class="wv-ring-sub" font-size="10.5" text-anchor="middle">/ 100</text>' +
        '</svg>';
    }

    function demoBadgeHtml() {
        return '<span class="wv-badge wv-badge-demo" title="This audit uses Phase-1 sample/demo data, not a live crawl">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
            '<path d="M9 3h6"/><path d="M10 3v6L4.8 17.7A2 2 0 0 0 6.5 21h11a2 2 0 0 0 1.7-3.3L14 9V3"/><line x1="7.5" y1="15" x2="16.5" y2="15"/></svg>' +
            'Demo Data</span>';
    }

    function findingIcon(type) {
        if (type === 'positive') {
            return '<span class="wv-finding-ico pos"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg></span>';
        }
        return '<span class="wv-finding-ico warn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></span>';
    }

    function contactRowHtml(branding) {
        var items = [];
        var phone = branding.phone;
        if (phone) {
            items.push('<a href="tel:' + esc(String(phone).replace(/[^+\d]/g, '')) + '">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>' +
                esc(phone) + '</a>');
        }
        if (branding.email) {
            items.push('<a href="mailto:' + esc(branding.email) + '">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>' +
                esc(branding.email) + '</a>');
        }
        if (branding.website) {
            items.push('<span>' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>' +
                esc(String(branding.website).replace(/^https?:\/\//, '')) + '</span>');
        }
        return items.join('');
    }

    function renderResults(data) {
        var b = data.business || {};
        var branding = data.branding || {};
        var company = branding.company_name || (BRANDING && BRANDING.company_name) || '';
        var grade = data.overall_grade || gradeForScore(data.overall_score);
        var fam = gradeFamily(grade);

        var barsHtml = (data.categories || []).map(function (c) {
            var color = gradeColorHex(gradeForScore(c.score));
            var w = Math.max(2, Math.min(100, Number(c.score) || 0));
            return '<div class="wv-bar-row">' +
                '<span class="wv-bar-label">' + esc(c.category_name) + '</span>' +
                '<span class="wv-bar-score" style="color:' + color + '">' + esc(fmtScore(c.score)) + '</span>' +
                '<div class="wv-bar-track"><div class="wv-bar-fill" data-w="' + w + '" style="background:' + color + ';width:0"></div></div>' +
            '</div>';
        }).join('');

        var findingsHtml = (data.findings || []).map(function (f) {
            return '<div class="wv-finding-row">' + findingIcon(f.type) +
                '<span class="wv-finding-text">' + esc(f.text) + '</span></div>';
        }).join('') || '<div class="wv-finding-row"><span class="wv-finding-text">No findings available.</span></div>';

        var emailNote = data.lead_emailed
            ? '<div class="wv-email-note">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>' +
                '<span>We\'ve also emailed your results to <strong>' + esc(data.business && data.business.contact_email ? data.business.contact_email : '') + '</strong>.</span>' +
            '</div>'
            : '';

        var ctaHref = branding.contact_form_url || branding.scheduling_url ||
            (branding.email ? 'mailto:' + branding.email : (branding.website || '#'));
        var newTab = /^https?:\/\//i.test(ctaHref);
        var shareToken = data.share_token || null;

        $('wv-body').innerHTML =
            '<div class="wv-results">' +
                '<div class="wv-res-head">' +
                    '<div class="wv-eyebrow">Your Visibility Snapshot</div>' +
                    '<h2>' + esc(b.name || 'Your Website') + '</h2>' +
                    '<div class="wv-res-url">' + esc(data.website_url || '') + '</div>' +
                '</div>' +

                '<section class="wv-score-panel" aria-label="Overall score">' +
                    scoreRingSvg(data.overall_score, grade) +
                    '<div class="wv-score-side">' +
                        '<span class="wv-badges">' +
                            '<span class="wv-badge wv-badge-lg wv-g-' + fam + '">Grade ' + esc(grade) + '</span>' +
                            (data.is_demo_data ? demoBadgeHtml() : '') +
                        '</span>' +
                        '<span class="wv-score-label">Overall Visibility Score — a blend of all 7 categories below, weighted by their impact on search and AI visibility.</span>' +
                    '</div>' +
                '</section>' +

                '<section class="wv-cats" aria-label="Category scores">' +
                    '<div class="wv-sec-title">Score by category</div>' + barsHtml +
                '</section>' +

                '<section class="wv-findings" aria-label="Key findings">' +
                    '<div class="wv-sec-title" style="padding:14px 16px 0">Key findings</div>' + findingsHtml +
                '</section>' +

                emailNote +

                '<section class="wv-cta">' +
                    '<h3>' + esc(branding.cta_headline || "Want to see what's holding your website back?") + '</h3>' +
                    '<p>Get the complete audit — every issue found, why it matters, and exactly how to fix it — from ' + esc(company || 'our team') + '.</p>' +
                    (shareToken
                        ? '<button type="button" class="wv-btn wv-btn-cta" id="wv-cta-btn">' +
                            esc(branding.cta_button_text || 'Request Your Full Audit') +
                            '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>' +
                          '</button>'
                        : '<a class="wv-btn wv-btn-cta" href="' + esc(ctaHref) + '"' + (newTab ? ' target="_blank" rel="noopener"' : '') + '>' +
                            esc(branding.cta_button_text || 'Request Your Full Audit') +
                            '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>' +
                          '</a>') +
                    '<div class="wv-contact-row">' + contactRowHtml(branding) + '</div>' +
                '</section>' +

                '<div class="wv-powered">Powered by <strong>' + esc(company || 'Website Visibility Audit') + '</strong></div>' +
                '<button type="button" class="wv-reset-btn" id="wv-reset">Run another audit</button>' +
            '</div>';

        /* Animate the category bars in. */
        var fills = $('wv-body').querySelectorAll('.wv-bar-fill');
        for (var i = 0; i < fills.length; i++) {
            (function (el) {
                requestAnimationFrame(function () {
                    requestAnimationFrame(function () { el.style.width = el.dataset.w + '%'; });
                });
            })(fills[i]);
        }

        var reset = $('wv-reset');
        if (reset) reset.addEventListener('click', resetToForm);

        var ctaBtn = $('wv-cta-btn');
        if (ctaBtn && shareToken) {
            ctaBtn.addEventListener('click', function () { openFullAuditModal(shareToken); });
        }
    }

    /* ---------- "Request Your Full Audit" confirmation modal ---------- */
    function openFullAuditModal(shareToken) {
        var overlay = document.createElement('div');
        overlay.className = 'wv-modal-overlay';
        overlay.id = 'wv-modal-overlay';
        overlay.innerHTML =
            '<div class="wv-modal" role="dialog" aria-modal="true" aria-labelledby="wv-modal-title">' +
                '<div class="wv-modal-body" id="wv-modal-body">' +
                    '<h3 id="wv-modal-title">Your full audit is being emailed to you.</h3>' +
                    '<p>Would you also like help correcting any of these issues?</p>' +
                    '<div class="wv-modal-actions">' +
                        '<button type="button" class="wv-btn wv-btn-cta" data-answer="yes">Yes, I\'d like help</button>' +
                        '<button type="button" class="wv-btn wv-btn-ghost" data-answer="no">No thanks</button>' +
                    '</div>' +
                '</div>' +
            '</div>';
        document.body.appendChild(overlay);

        function closeModal() {
            if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
        }

        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closeModal();
        });

        overlay.querySelectorAll('[data-answer]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var wantsHelp = btn.dataset.answer === 'yes';
                var body = $('wv-modal-body');
                body.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
                body.innerHTML =
                    '<h3>Sending your full audit…</h3>' +
                    '<p>One moment.</p>';

                fetch('/api/reports/' + encodeURIComponent(shareToken) + '/request-full-audit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ wants_help: wantsHelp })
                })
                    .then(function (res) { return res.json().catch(function () { return {}; }); })
                    .then(function () {
                        body.innerHTML =
                            '<h3>You\'re all set!</h3>' +
                            '<p>' + (wantsHelp
                                ? 'Your full audit is on its way to your email — we\'ll also be in touch about helping you fix these issues.'
                                : 'Your full audit is on its way to your email.') + '</p>' +
                            '<div class="wv-modal-actions">' +
                                '<button type="button" class="wv-btn wv-btn-ghost" id="wv-modal-close">Close</button>' +
                            '</div>';
                        var closeBtn = $('wv-modal-close');
                        if (closeBtn) closeBtn.addEventListener('click', closeModal);
                        var ctaBtn2 = $('wv-cta-btn');
                        if (ctaBtn2) {
                            ctaBtn2.disabled = true;
                            ctaBtn2.textContent = wantsHelp ? 'Help requested ✓' : 'Full audit sent ✓';
                        }
                    })
                    .catch(function () {
                        body.innerHTML =
                            '<h3>Something went wrong.</h3>' +
                            '<p>Please try again in a moment.</p>' +
                            '<div class="wv-modal-actions">' +
                                '<button type="button" class="wv-btn wv-btn-ghost" id="wv-modal-close">Close</button>' +
                            '</div>';
                        var closeBtn2 = $('wv-modal-close');
                        if (closeBtn2) closeBtn2.addEventListener('click', closeModal);
                    });
            });
        });
    }

    /* ---------- reset ---------- */
    function resetToForm() {
        $('wv-body').innerHTML = FORM_HTML;
        wireForm();
        applyBranding(BRANDING || {});
    }

    /* ---------- boot ---------- */
    function wireForm() {
        var form = $('wv-form');
        if (!form) return;
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (analyzing) return;
            if (!validate()) return;
            submitAudit();
        });
        ['wv-url', 'wv-fn', 'wv-email'].forEach(function (id) {
            var input = $(id);
            input.addEventListener('input', function () {
                var field = input.closest('.wv-field');
                if (field && field.classList.contains('wv-invalid')) {
                    field.classList.remove('wv-invalid');
                    var err = field.querySelector('.wv-field-err');
                    if (err) err.textContent = '';
                }
            });
        });
        var retry = $('wv-alert-retry');
        retry.addEventListener('click', function () { clearAlert(); });
    }

    loadBranding();
    FORM_HTML = $('wv-body').innerHTML;
    wireForm();
})();
