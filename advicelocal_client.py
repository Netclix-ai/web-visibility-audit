"""Advice Local (advicelocal.com) API client -- internally named "Warpath"
by Advice Local. Used for the Local Visibility bulk-scoring feature
(routes.py's /api/local-visibility/* endpoints, static/js/views/local-
visibility.js), the local-presence counterpart to the existing website-
audit bulk scoring.

How this differs from the website audit pipeline: there is no in-house
crawler here. Advice Local's platform does the actual work --

    1. POST /legacyclients creates a "client" (business location, NAP
       data) in the partner's Advice Local account. This alone triggers
       an automatically-generated "baseline report" -- Advice Local's own
       docs/marketing confirm baseline reports are included in the
       reseller fee ("simply input your client's business name and zip
       code to receive their baseline local visibility report";
       "resellers have the ability to run as many Baseline Reports as
       they want as long as their dashboard is active and in good
       standing") -- so this does NOT require placing a paid /legacyorders
       order first, unlike ongoing rank-tracking/listing-distribution
       products. CONFIRMED live against the real API: POST /legacyclients
       with just name/street/city/state/zipcode/phone returns a client id
       within ~1s, no order needed.
    2. The baseline report is generated asynchronously, but fast --
       GET /legacyclients/{id}/report already returns a (partial, mostly
       zero) score structure within ~0.1s of client creation, and in live
       testing the score stabilized to its settled value within ~10-15s
       as the ~40 directories + 2 "locals" (Google/Bing) + voice platforms
       got checked. There is no explicit "done" flag in the response, so
       wait_for_baseline_score() below uses a stability heuristic: it
       polls until the found-counts (directoriesFound + localsFound +
       voiceFound) stop increasing across two consecutive polls (i.e. the
       scan has settled), or a hard timeout is hit -- whichever comes
       first. NOTE: the separate GET /legacyscores endpoint (documented
       in Advice Local's wiki with a "baseline" key) was tried first but
       its `data` field stayed null/incomplete throughout live testing --
       GET /legacyclients/{id}/report is the endpoint that actually
       returns a populated score, so that's what this module uses.
    3. data.overview.baselineOverview.visibilityScore (0-100) is the
       headline number surfaced as the "score" in the bulk CSV output,
       converted to a letter grade with the same
       audit_engine.scoring.grade_for_score + GradeThreshold rows the
       website audit already uses, so both bulk-scoring features report
       grades on the same scale.

Auth: every request sends the API key in the `x-api-token` header (per
Advice Local's published API docs at wiki.advicelocal.com). Base host is
p.lssdev.com -- this is Advice Local's actual API domain, not a typo.

Field names confirmed against the live API (not just the docs, which used
slightly different examples in places): the zip code field is `zipcode`,
not `zip` -- POST /legacyclients returns a 400 "zipcode can not be
emptys" if sent as `zip`.

Never raises across the public functions below -- every failure mode
(missing API key, network error, non-2xx response, timeout waiting for
the baseline score) is caught and surfaces as a (None, error_message)
style return so a single bad row can't crash a whole bulk job.
"""
import logging
import os
import time

import httpx

logger = logging.getLogger("advicelocal_client")

BASE_URL = "https://p.lssdev.com"
TIMEOUT = 20.0


def _api_key() -> str | None:
    return os.environ.get("ADVICE_LOCAL_API_KEY")


def _headers() -> dict:
    return {"x-api-token": _api_key() or "", "Content-Type": "application/json"}


def create_client(payload: dict) -> tuple[str | None, str | None]:
    """POST /legacyclients. `payload` keys: name, street, city, state,
    zipcode (all confirmed against the live API -- note `zipcode`, not
    `zip`), plus optional phone/email/website. Returns (client_id, error)
    -- exactly one of the two is set."""
    api_key = _api_key()
    if not api_key:
        return None, "ADVICE_LOCAL_API_KEY is not configured"
    try:
        resp = httpx.post(f"{BASE_URL}/legacyclients", headers=_headers(), json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        # Advice Local returns a helpful validation-error body on 400s
        # (e.g. {"error":"Invalid Request","data":[{"message":"zipcode
        # can not be emptys","field":"zipcode"}]}) -- surface it instead
        # of just "400 Bad Request" so a bad row is easy to diagnose from
        # the CSV/job error rather than needing to check server logs.
        detail = e.response.text[:300] if e.response is not None else str(e)
        logger.warning("Advice Local create_client rejected %r: %s", payload.get("name"), detail)
        return None, f"Advice Local rejected the request: {detail}"
    except Exception as e:
        logger.exception("Advice Local create_client failed for %r", payload.get("name"))
        return None, f"Could not create Advice Local client: {e}"
    body = data.get("data") if isinstance(data, dict) else None
    client_id = None
    if isinstance(body, dict):
        client_id = body.get("id") or body.get("client") or body.get("client_id")
    elif isinstance(body, (str, int)):
        client_id = body
    if not client_id:
        return None, f"Advice Local did not return a client id: {data}"
    return str(client_id), None


def get_report(client_id: str) -> tuple[dict | None, str | None]:
    """GET /legacyclients/{id}/report -- returns the `data` object (contains
    `overview.baselineOverview` with the score fields, plus the full
    directory/locals breakdown under `data.baseline`), or (None, error) on
    an actual request failure."""
    api_key = _api_key()
    if not api_key:
        return None, "ADVICE_LOCAL_API_KEY is not configured"
    try:
        resp = httpx.get(f"{BASE_URL}/legacyclients/{client_id}/report", headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.exception("Advice Local get_report failed for client %s", client_id)
        return None, f"Could not fetch Advice Local report: {e}"
    return data.get("data") if isinstance(data, dict) else None, None


def extract_visibility_score(report_data: dict | None) -> float | None:
    """Pulls overview.baselineOverview.visibilityScore (0-100) out of the
    blob returned by get_report(). Returns None only if the response shape
    is missing entirely (e.g. an unexpected API change) -- 0 is a valid,
    real score (a business with literally no local presence found), so
    this deliberately does not treat 0 as "not ready" the way a naive
    truthiness check would."""
    if not isinstance(report_data, dict):
        return None
    overview = report_data.get("overview")
    if not isinstance(overview, dict):
        return None
    baseline_overview = overview.get("baselineOverview")
    if not isinstance(baseline_overview, dict):
        return None
    score = baseline_overview.get("visibilityScore")
    return float(score) if isinstance(score, (int, float)) else None


def _found_total(report_data: dict) -> int:
    """Sums the *Found counters (directoriesFound + localsFound +
    voiceFound) from baselineOverview -- used as a settling signal: once
    this stops increasing across consecutive polls, the baseline scan has
    finished checking every source it's going to check, even though the
    API exposes no explicit "done" flag."""
    overview = (report_data or {}).get("overview", {})
    bo = overview.get("baselineOverview", {}) if isinstance(overview, dict) else {}
    if not isinstance(bo, dict):
        return 0
    return sum(
        bo.get(k) or 0
        for k in ("directoriesFound", "localsFound", "voiceFound")
    )


def wait_for_baseline_score(client_id: str, timeout_s: float = 60.0, poll_interval_s: float = 5.0,
                             stability_polls: int = 2) -> tuple[dict | None, str | None]:
    """Polls get_report() until the found-counts stabilize (unchanged
    across `stability_polls` consecutive reads) or timeout_s elapses.
    Returns (report_data, error) -- report_data is the full blob (so
    callers can stash the raw breakdown even though only the headline
    score is used today).

    Live testing showed the score settles within ~10-15s for a typical
    business, so the default 60s timeout / 5s interval leaves comfortable
    headroom without making a bulk job wait too long per row on the (rare)
    slow case. error is set only on a hard request failure; a timeout
    still returns whatever report_data was last read (a best-effort score
    is better than none) rather than None, since the client was created
    successfully either way."""
    last_found_total = None
    stable_count = 0
    last_report_data = None
    deadline = time.monotonic() + timeout_s
    while True:
        report_data, error = get_report(client_id)
        if error:
            return None, error
        last_report_data = report_data
        found_total = _found_total(report_data) if report_data else 0
        if found_total == last_found_total:
            stable_count += 1
            if stable_count >= stability_polls:
                return report_data, None
        else:
            stable_count = 0
        last_found_total = found_total
        if time.monotonic() >= deadline:
            return last_report_data, None
        time.sleep(poll_interval_s)

