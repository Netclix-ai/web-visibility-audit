/* API layer — thin fetch wrappers. All endpoints are same-origin. */
window.WVA = window.WVA || {};

WVA.api = (function () {
    const TIMEOUT_MS = 20000;
    // Audits run a live site crawl + sequential PageSpeed Insights calls
    // (mobile then desktop) server-side, which can legitimately take up to
    // ~2 minutes on slow sites (see widget.js's TIMEOUT_MS for the same
    // reasoning). The default 20s timeout above is fine for normal CRUD
    // calls but far too short for anything that kicks off run_audit().
    const AUDIT_TIMEOUT_MS = 300000;

    async function request(method, path, body, timeoutMs) {
        const opts = { method, headers: {} };
        if (body !== undefined) {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(body);
        }
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeoutMs || TIMEOUT_MS);
        opts.signal = ctrl.signal;
        let res;
        try {
            res = await fetch(path, opts);
        } catch (e) {
            const err = e && e.name === 'AbortError'
                ? new Error('Request timed out — please try again.')
                : new Error('Network error — could not reach the server.');
            err.status = 0;
            throw err;
        } finally {
            clearTimeout(timer);
        }
        let data = null;
        try { data = await res.json(); } catch (e) { /* no body */ }
        if (!res.ok) {
            let msg = res.statusText || 'Request failed';
            if (data && data.detail) {
                msg = typeof data.detail === 'string'
                    ? data.detail
                    : (Array.isArray(data.detail)
                        ? data.detail.map(d => d.msg || JSON.stringify(d)).join('; ')
                        : JSON.stringify(data.detail));
            }
            const err = new Error(msg);
            err.status = res.status;
            throw err;
        }
        return data;
    }

    return {
        get: (path) => request('GET', path),
        post: (path, body) => request('POST', path, body === undefined ? {} : body),
        put: (path, body) => request('PUT', path, body === undefined ? {} : body),
        del: (path) => request('DELETE', path),
        // Long-running variant for endpoints that trigger a full audit run
        // (create audit, re-run audit) — see AUDIT_TIMEOUT_MS above.
        postLong: (path, body) => request('POST', path, body === undefined ? {} : body, AUDIT_TIMEOUT_MS),
        // Audit creation/rerun endpoints now return almost instantly with
        // status:"running" (the actual crawl runs in a background thread —
        // see routes.py / audit_engine/engine.py). A single long-lived
        // synchronous request used to risk hitting the reverse proxy's own
        // response timeout regardless of any client-side timeout, which is
        // what caused intermittent "something went wrong" failures
        // independent of whether the audit itself would have succeeded.
        // Poll GET /audits/{id} instead until status is no longer "running".
        pollAudit: async function (auditId, opts) {
            opts = opts || {};
            const intervalMs = opts.intervalMs || 3000;
            // PSI mobile+desktop run strictly sequentially with a 100s
            // per-call timeout and up to 1 retry each (see
            // audit_engine/google_apis.py) -- worst case that's ~400s
            // before the crawl even gets to scoring. Real-world full
            // audits have been observed taking ~162s. 180s used to be the
            // default here and was too tight -- widget/dashboard audits
            // would show a false "taking longer than expected" timeout
            // error to the user even though the background audit went on
            // to complete successfully seconds later. Give real headroom.
            const maxWaitMs = opts.maxWaitMs || 300000;
            const onTick = opts.onTick; // optional progress callback
            const t0 = Date.now();
            while (true) {
                const audit = await request('GET', `/api/audits/${auditId}`);
                if (onTick) onTick(audit);
                if (audit.status !== 'running') return audit;
                if (Date.now() - t0 > maxWaitMs) {
                    const err = new Error('The audit is taking longer than expected. It is still running in the background — check back in a minute.');
                    err.status = 0;
                    err.audit = audit;
                    throw err;
                }
                await new Promise(r => setTimeout(r, intervalMs));
            }
        },
    };
})();