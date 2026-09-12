"""GoHighLevel (GHL) round-trip integration.

Design: this app never calls into GHL's REST API and never needs a GHL API
key for the core bulk-scoring loop. Instead, both directions are plain
webhooks that stay entirely inside GHL's own Workflow Builder:

    GHL Workflow #1 (e.g. triggered when a contact gets a "needs-audit" tag,
    or is added to a list/campaign of up to thousands of contacts)
        -> "Custom Webhook" action (outbound)
        -> POST /api/integrations/ghl/audit-request on this app
              (see routes.py) -- runs a fast "lite" audit (no Playwright,
              no PageSpeed Insights -- see live_collector.collect(depth=))
        -> this module POSTs the result back to an "Inbound Webhook"
           Trigger URL the user creates in a second GHL Workflow
    GHL Workflow #2 (trigger = Inbound Webhook)
        -> native "Update Contact" action, mapping the webhook payload's
           score/grade/report_url fields onto that contact's custom fields
        -> native SMS/Email action, merging those same custom fields into
           the outreach message

That second leg (posting results back) is the only thing this module does.
GHL_RESULTS_WEBHOOK_URL is the Inbound Webhook Trigger URL from Workflow #2
-- copy it from GHL's Workflow Builder (Trigger step -> Inbound Webhook ->
"Copy URL") and store it as a project secret. If it isn't set yet (e.g.
Workflow #2 hasn't been built), this silently no-ops so Workflow #1 can
still be wired up and tested end-to-end minus the final hand-back.
"""
import logging
import os

import httpx

logger = logging.getLogger("ghl_client")

TIMEOUT = 10.0


def post_audit_result(payload: dict) -> bool:
    """POST the completed (or failed) lite-audit result back to GHL's
    Inbound Webhook Trigger URL. Returns True on a 2xx response, False on
    any failure (missing URL, timeout, non-2xx) -- never raises, so a
    flaky/unconfigured webhook can't break the audit-request endpoint that
    calls this."""
    url = os.environ.get("GHL_RESULTS_WEBHOOK_URL")
    if not url:
        logger.warning("GHL_RESULTS_WEBHOOK_URL not set; skipping GHL result webhook for contact %s",
                        payload.get("contact_id"))
        return False
    try:
        resp = httpx.post(url, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to POST audit result back to GHL for contact %s", payload.get("contact_id"))
        return False
