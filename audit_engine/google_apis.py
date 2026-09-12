"""Thin wrappers around two Google Cloud APIs used to fill in checks that
previously had no real data source:

  - PageSpeed Insights API v5 -> Performance category (mobile/desktop
    score, LCP, CLS, image optimization).
  - Places API (Find Place From Text) -> Local SEO "Google Business
    Profile Signal" check.

Both are key-only (no OAuth) and have generous free tiers. If
GOOGLE_API_KEY isn't set, or a call fails/times out for any reason, every
function here returns None (or a dict with an "error" key) so the caller
can fall back to the existing honest NOT_APPLICABLE / "Data unavailable"
behavior instead of crashing the audit.
"""
import os

import httpx

PAGESPEED_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
# Places API (New) — https://developers.google.com/maps/documentation/places/web-service/text-search
# (the legacy "Places API" findplacefromtext endpoint is a different product
# with a different auth/request shape; this project uses the New API.)
PLACES_SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"

TIMEOUT = 100.0  # PageSpeed Insights mobile runs simulate throttled network + CPU and have high
                 # variance -- empirically observed anywhere from ~15s to 60s+ for the same site
                 # across separate runs (confirmed directly: one run of the same URL timed out
                 # at 60s, the very next completed in 18s with a real score). Now that audits run
                 # in a background thread (see the async audit architecture -- there's no longer a
                 # reverse-proxy request deadline to worry about), we can afford a longer timeout
                 # and a single retry on failure instead of silently reporting "Data unavailable"
                 # for what is often just a slow-but-working PSI run.


def _api_key() -> str | None:
    return os.environ.get("GOOGLE_API_KEY") or None


def fetch_pagespeed(url: str, strategy: str) -> dict | None:
    """Runs PageSpeed Insights for `url` with strategy in {"mobile", "desktop"}.

    Returns a dict with keys: performance_score (0-100 int or None),
    lcp_seconds (float or None), cls (float or None),
    modern_image_format_score / uses_optimized_images_score (0-1 float or
    None, from Lighthouse's opportunity audits — used as an image
    optimization signal). Returns None if the API key is missing or the
    call fails.
    """
    key = _api_key()
    if not key:
        return None
    params = {
        "url": url,
        "strategy": strategy,
        "key": key,
        "category": ["performance"],
    }
    # One retry on failure/timeout: confirmed via direct testing that PSI
    # mobile runs are genuinely flaky in duration for the exact same URL
    # (one run times out, the immediate next succeeds fast) -- not a bug
    # in this code. A single retry is now affordable since this call runs
    # in a background thread with no reverse-proxy deadline (see the async
    # audit architecture), unlike when this was first written.
    data = None
    for attempt in range(2):
        try:
            resp = httpx.get(PAGESPEED_URL, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception:
            if attempt == 0:
                continue
            return None
    if data is None:
        return None

    lh = data.get("lighthouseResult") or {}
    categories = lh.get("categories") or {}
    audits = lh.get("audits") or {}

    perf_cat = categories.get("performance") or {}
    perf_score = perf_cat.get("score")
    performance_score = round(perf_score * 100) if isinstance(perf_score, (int, float)) else None

    lcp_audit = audits.get("largest-contentful-paint") or {}
    lcp_ms = lcp_audit.get("numericValue")
    lcp_seconds = round(lcp_ms / 1000, 2) if isinstance(lcp_ms, (int, float)) else None

    cls_audit = audits.get("cumulative-layout-shift") or {}
    cls_value = cls_audit.get("numericValue")
    cls_value = round(cls_value, 3) if isinstance(cls_value, (int, float)) else None

    # Image optimization signal: newer Lighthouse versions replaced the
    # classic "opportunity" audits (modern-image-formats, etc.) with an
    # "insight" audit; support both shapes so this keeps working across
    # Lighthouse versions PageSpeed Insights may roll out over time.
    image_audit_keys = [
        "image-delivery-insight",  # current Lighthouse (13+)
        "modern-image-formats", "uses-optimized-images", "uses-responsive-images",  # legacy Lighthouse
    ]
    image_scores = []
    for k in image_audit_keys:
        a = audits.get(k) or {}
        s = a.get("score")
        if isinstance(s, (int, float)):
            image_scores.append(s)
    image_optimization_score = round(sum(image_scores) / len(image_scores), 2) if image_scores else None

    return {
        "performance_score": performance_score,
        "lcp_seconds": lcp_seconds,
        "cls_value": cls_value,
        "image_optimization_score": image_optimization_score,
    }


def find_place(business_name: str, location: str | None) -> dict | None:
    """Looks up `business_name` (+ optional `location`) via the Places API
    (New) Text Search endpoint. Returns a dict with keys: found (bool),
    place_id, name, formatted_address, rating, user_ratings_total,
    business_status -- or None if the API key is missing or the call fails.
    """
    key = _api_key()
    if not key or not business_name:
        return None
    query = business_name if not location else f"{business_name}, {location}"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.businessStatus",
    }
    body = {"textQuery": query}
    try:
        resp = httpx.post(PLACES_SEARCH_TEXT_URL, headers=headers, json=body, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    places = data.get("places") or []
    if not places:
        return {"found": False}

    p = places[0]
    display_name = (p.get("displayName") or {}).get("text")
    return {
        "found": True,
        "place_id": p.get("id"),
        "name": display_name,
        "formatted_address": p.get("formattedAddress"),
        "rating": p.get("rating"),
        "user_ratings_total": p.get("userRatingCount"),
        "business_status": p.get("businessStatus"),
    }
