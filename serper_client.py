"""Serper.dev (google.serper.dev) API client -- powers the Rank Checker
feature (routes.py's /api/rank-checker/* endpoints, static/js/views/rank-
checker*.js). Serper is Google-only: it does not offer a Bing endpoint.
The two endpoints used here:

    POST https://google.serper.dev/search  -- organic Google search
        results. Response's `organic` array has `position` (1-indexed
        rank), `title`, `link`, `snippet`. A local-intent query may also
        include a `places` block in the same response, but we always hit
        the dedicated /maps endpoint below for Map Pack checks since it
        returns a cleaner, purpose-built local-pack ranking.

    POST https://google.serper.dev/maps  -- Google Maps / "Map Pack"
        results. Response's `places` array has `position`, `title`
        (business name), `address`, `rating`, `ratingCount`, `website`,
        `phoneNumber`, `cid`.

Auth: `X-API-KEY` header (per Serper's published docs), not a query param
or bearer token. Never raises across the public functions -- every
failure mode (missing key, network error, non-2xx, unexpected shape)
surfaces as (None, error_message) so a single bad keyword can't crash a
whole scan or bulk job.
"""
import logging
import os

import httpx

logger = logging.getLogger("serper_client")

BASE_URL = "https://google.serper.dev"
TIMEOUT = 20.0


def _api_key() -> str | None:
    return os.environ.get("SERPER_API_KEY")


def _headers() -> dict:
    return {"X-API-KEY": _api_key() or "", "Content-Type": "application/json"}


def _post(path: str, payload: dict) -> tuple[dict | None, str | None]:
    api_key = _api_key()
    if not api_key:
        return None, "SERPER_API_KEY is not configured"
    try:
        resp = httpx.post(f"{BASE_URL}{path}", headers=_headers(), json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json(), None
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:300] if e.response is not None else str(e)
        logger.warning("Serper %s rejected %r: %s", path, payload.get("q"), detail)
        return None, f"Serper rejected the request: {detail}"
    except Exception as e:
        logger.exception("Serper %s failed for %r", path, payload.get("q"))
        return None, f"Could not reach Serper: {e}"


def search_organic(query: str, gl: str = "us") -> tuple[list[dict] | None, str | None]:
    """POST /search. Returns (organic_results, error) -- organic_results
    is a list of {position, title, link, snippet}, top ~10-100 depending
    on Serper's default page size (typically the first SERP page, ~10)."""
    data, error = _post("/search", {"q": query, "gl": gl})
    if error:
        return None, error
    organic = (data or {}).get("organic") or []
    return [
        {"position": r.get("position"), "title": r.get("title"), "link": r.get("link"),
         "snippet": r.get("snippet")}
        for r in organic if isinstance(r, dict)
    ], None


def search_maps(query: str, gl: str = "us") -> tuple[list[dict] | None, str | None]:
    """POST /maps. Returns (places, error) -- places is a list of
    {position, title, address, rating, ratingCount, website, phoneNumber,
    cid}, i.e. the Google Maps / Map Pack ranking for this query."""
    data, error = _post("/maps", {"q": query, "gl": gl})
    if error:
        return None, error
    places = (data or {}).get("places") or []
    return [
        {
            "position": p.get("position"), "title": p.get("title"), "address": p.get("address"),
            "rating": p.get("rating"), "rating_count": p.get("ratingCount"),
            "website": p.get("website"), "phone": p.get("phoneNumber"), "cid": p.get("cid"),
        }
        for p in places if isinstance(p, dict)
    ], None


def _domain(url: str) -> str:
    url = (url or "").strip().lower()
    url = url.replace("https://", "").replace("http://", "")
    url = url.split("/")[0]
    if url.startswith("www."):
        url = url[4:]
    return url


def find_organic_position(organic: list[dict], website: str) -> tuple[int | None, str | None]:
    """Finds the first organic result whose link's domain matches
    `website` (also domain-normalized). Returns (position, matched_url) or
    (None, None) if not found in the checked results."""
    target = _domain(website)
    if not target:
        return None, None
    for r in organic:
        if _domain(r.get("link") or "") == target:
            return r.get("position"), r.get("link")
    return None, None


def find_map_pack_position(places: list[dict], business_name: str) -> int | None:
    """Finds the first Map Pack place whose title contains (or is
    contained by) `business_name`, case-insensitively. Substring match
    rather than exact-equality since Map Pack listing names sometimes
    include extra branding/location suffixes."""
    name = (business_name or "").strip().lower()
    if not name:
        return None
    for p in places:
        title = (p.get("title") or "").strip().lower()
        if not title:
            continue
        if name in title or title in name:
            return p.get("position")
    return None
