"""Phase 2 live collector.

Replaces the Phase 1 hash-based stub (collector.py) with a real crawl of the
site's homepage plus a handful of well-known auxiliary files
(robots.txt, sitemap.xml, llms.txt) and DNS records (SPF/DMARC).

Design principle (per product spec): never fabricate data. If the site
can't be reached at all, we return a profile with `fetch_error` set and do
NOT invent a score — the caller (engine.py) is expected to mark the audit
as "failed" in that case. If the site *is* reachable, every field below is
either a directly-observed fact (HTML tag, HTTP header, DNS record) or a
clearly-labeled heuristic computed from real page content — nothing here is
randomly generated.

Fields intentionally NOT collected (require a paid third-party API not yet
connected): Core Web Vitals / Lighthouse performance scores, backlink /
referring-domain data, Google Business Profile data. live_checks.py marks
the corresponding checks NOT_APPLICABLE with "Data unavailable" language
rather than guessing.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

try:
    import dns.resolver
except ImportError:  # pragma: no cover - dnspython should always be installed
    dns = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - playwright should always be installed
    sync_playwright = None

from . import google_apis
from . import browser_worker

USER_AGENT = "NetclixVisibilityAuditBot/1.0 (+https://netclixmarketing.com)"
TIMEOUT = 12.0
RENDER_TIMEOUT_MS = 20000
RENDER_SETTLE_MS = 1000  # extra wait for late-executing JS (e.g. client-side title/meta injectors)


_SPA_SHELL_MARKERS = re.compile(r'id=["\'](root|app|__next|___gatsby)["\']', re.I)


def _looks_like_thin_spa_shell(raw_html: str, raw_word_count: int) -> bool:
    """Heuristic: raw (pre-render) HTML that has almost no visible text but
    does contain a common SPA mount point and JS bundle references. This is
    the signature of a client-side-rendered app (React/Vue/Next/Gatsby)
    whose real content only exists after JavaScript runs -- as opposed to a
    page that is genuinely just empty/broken."""
    if raw_word_count > 30:
        return False
    has_mount_point = bool(_SPA_SHELL_MARKERS.search(raw_html))
    has_script_bundle = bool(re.search(r'<script[^>]+src=', raw_html, re.I))
    return has_mount_point and has_script_bundle


def _quick_word_count(html: str) -> int:
    try:
        return len(BeautifulSoup(html, "html.parser").get_text(" ", strip=True).split())
    except Exception:
        return 0


def _render_and_verify(final_url: str, raw_html: str, raw_word_count: int):
    """Render `final_url` and keep retrying with progressively more patient
    strategies until we get content that plainly isn't an empty SPA shell --
    or we run out of attempts and have to admit we couldn't verify it.

    This closes a gap the simple "did the browser call throw?" check missed:
    Playwright can report a perfectly successful page load (no exception)
    while the *page's own JavaScript* still fails to inject real content --
    a slow XHR that hadn't resolved yet, a client-side runtime error, a JS
    bundle that 404'd, an ad/consent overlay blocking rendering, etc. In
    that case the old code took the "success" at face value and confidently
    reported 0 H1s / 0 images / near-zero word count, which is exactly as
    misleading as a hard render failure. Here we only trust a render if the
    resulting content is not itself still shell-thin AND the raw pre-render
    HTML doesn't look like a shell that will never resolve.

    Returns (html, js_rendered: bool, js_render_failed: bool, rendered_bytes).
    """
    thin_raw = _looks_like_thin_spa_shell(raw_html, raw_word_count)

    # Attempt schedule: start cheap/fast, escalate patience only if needed.
    # Each entry is (wait_until, timeout_ms, content_wait_ms). We deliberately
    # do NOT use "networkidle" here -- it's unreliable on real-world sites:
    # analytics beacons, chat widgets, and long-poll/websocket connections
    # mean many pages never actually go network-idle, so networkidle either
    # wastes the entire timeout for no reason or returns before the page is
    # really ready. Polling the live DOM for real text (content_wait_ms,
    # see browser_worker.py) is a direct, adaptive signal instead: it
    # returns the moment content shows up, and still has a hard ceiling.
    attempts_schedule = [
        ("load", 20000, 4000),
        ("load", 20000, 10000),
        ("load", 25000, 20000),
    ]

    last_html, last_bytes = None, None
    for i, (wait_until, timeout_ms, content_wait_ms) in enumerate(attempts_schedule):
        html, rendered_bytes = browser_worker.render_page(
            final_url, wait_until=wait_until, timeout_ms=timeout_ms, content_wait_ms=content_wait_ms)
        if html:
            last_html, last_bytes = html, rendered_bytes
            # If the raw page never looked like a JS-only shell to begin
            # with, one successful render is enough -- no need to keep
            # re-checking content thinness (a genuinely sparse static page
            # is real data, not a rendering failure).
            if not thin_raw:
                return html, True, False, rendered_bytes
            # For pages that DID look like an empty shell pre-render, make
            # sure the render actually produced real content before trusting
            # it -- a structurally "successful" Playwright call can still
            # yield a page whose own JS failed to populate anything.
            rendered_word_count = _quick_word_count(html)
            has_h1 = bool(re.search(r'<h1[\s>]', html, re.I))
            if rendered_word_count > 30 or has_h1:
                return html, True, False, rendered_bytes
        if i < len(attempts_schedule) - 1:
            time.sleep(1)

    # Every attempt either failed outright or came back still shell-thin.
    # If we at least got *some* rendered HTML, prefer it over the raw shell
    # for anything non-content-dependent (title/meta may still have loaded)
    # but tell live_checks.py not to trust content-dependent checks.
    if last_html:
        return last_html, True, True, last_bytes
    return None, False, True, None

AI_CRAWLER_NAMES = [
    "GPTBot", "ChatGPT-User", "ClaudeBot", "anthropic-ai", "Google-Extended",
    "PerplexityBot", "CCBot", "cohere-ai", "Applebot-Extended",
]

SOCIAL_DOMAINS = [
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "yelp.com", "pinterest.com",
]

ANALYTICS_SIGNATURES = [
    ("googletagmanager.com", "Google Tag Manager"),
    ("google-analytics.com", "Google Analytics"),
    ("gtag(", "Google gtag.js"),
    ("connect.facebook.net", "Meta Pixel"),
    ("hotjar.com", "Hotjar"),
    ("clarity.ms", "Microsoft Clarity"),
    ("plausible.io", "Plausible Analytics"),
]

TRUST_KEYWORDS = [
    "certified", "licensed", "insured", "accredited", "award", "since 19",
    "since 20", "years of experience", "years in business", "bbb",
    "google reviews", "5-star", "5 star",
]

ADDRESS_RE = re.compile(
    r"\d{1,6}\s+[A-Za-z0-9.\s]{3,40}\b(St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Ln|Lane|Way|Suite|Ste|Cir|Circle|Ct|Court)\b",
    re.I,
)
PHONE_RE = re.compile(r"(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})")


def _normalize(url: str) -> str:
    if "://" not in url:
        url = f"https://{url}"
    return url


def _get(client: httpx.Client, url: str):
    try:
        return client.get(url)
    except Exception:
        return None


def collect(url: str, business_name: str | None = None, location: str | None = None,
            depth: str = "full") -> dict:
    """Fetch real data for `url`. Returns a profile dict; sets
    profile['fetch_error'] (str) if the homepage itself could not be
    retrieved at all — every other field is best-effort real data.

    `business_name` / `location` are optional and, when provided, are used
    to run a Google Places lookup (Local SEO -> GBP presence check). They
    have no effect on the rest of the crawl.

    `depth`: "full" (default) does everything below, including the
    Playwright JS-render pass and the two sequential PageSpeed Insights
    calls -- together these are the dominant cost/latency of an audit (PSI
    alone can take up to ~100s per call, and JS rendering may fall back to
    a paid remote browser). "lite" skips both: no PSI calls (Performance
    checks degrade to their existing, already-built NOT_APPLICABLE path --
    see live_checks.py's `_perf_score_check`), and no Playwright render (the
    handful of DOM-dependent checks -- H1, heading structure, keyword
    consistency, content length, image alt text, internal linking --
    degrade the same way they already do today whenever a real render
    fails, via `profile["js_render_failed"]`). Everything else (raw HTML
    fetch, headers, robots.txt/sitemap, DNS, Google Places) is unchanged and
    still runs, so lite mode still produces an honest score for every
    check that doesn't strictly require a paid API call or a browser.
    Intended for high-volume/low-cost bulk scoring (e.g. GoHighLevel
    outreach); "full" remains the default for anyone actually viewing a
    report page."""
    url = _normalize(url)
    parsed = urlparse(url)
    domain = parsed.netloc

    profile = {
        "url": url,
        "domain": domain,
        "is_demo_data": False,
        "data_source": "live_crawl",
        "fetch_error": None,
        "depth": depth,
    }

    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}

    try:
        client = httpx.Client(follow_redirects=True, http2=True, headers=headers, timeout=TIMEOUT)
    except Exception as e:
        profile["fetch_error"] = f"Could not initialize HTTP client: {e}"
        return profile

    try:
        try:
            resp = client.get(url)
            resp.raise_for_status()
        except Exception as e:
            profile["fetch_error"] = f"Could not reach {url}: {e}"
            return profile

        final_url = str(resp.url)
        final_parsed = urlparse(final_url)
        base = f"{final_parsed.scheme}://{final_parsed.netloc}"

        profile["final_url"] = final_url
        profile["status_code"] = resp.status_code
        profile["scheme"] = final_parsed.scheme
        profile["http_version"] = resp.http_version
        profile["response_time_seconds"] = round(resp.elapsed.total_seconds(), 2) if resp.elapsed else None
        profile["page_size_bytes"] = len(resp.content)
        profile["has_hsts"] = "strict-transport-security" in {k.lower() for k in resp.headers.keys()}

        # ---- Kick off Google PageSpeed Insights + Places NOW, in the ----
        # ---- background, concurrently with the rest of the crawl below ----
        # `final_url` is all these calls need, and it's already known at
        # this point. Running them in parallel with the Playwright render /
        # robots.txt / sitemap / DNS work below (instead of after it, as a
        # strictly sequential step) roughly halves total wall-clock time —
        # those steps hit entirely different services (our own scrape vs.
        # Google's PSI/Places APIs) so there's no contention between them.
        # NOTE: the two PageSpeed calls (mobile, desktop) themselves must
        # still run sequentially relative to EACH OTHER on one worker —
        # PSI appears to serialize/throttle concurrent Lighthouse runs from
        # the same API key, so running mobile+desktop concurrently with
        # each other was tried and made both calls slower (see git history).
        def _run_pagespeed_sequential():
            mobile = google_apis.fetch_pagespeed(final_url, "mobile")
            desktop = google_apis.fetch_pagespeed(final_url, "desktop")
            return mobile, desktop

        bg_pool = ThreadPoolExecutor(max_workers=2)
        pagespeed_future = bg_pool.submit(_run_pagespeed_sequential) if depth == "full" else None
        places_future = bg_pool.submit(google_apis.find_place, business_name, location) if business_name else None

        # ---- JS rendering pass ----
        # Some sites inject SEO-critical tags (title, meta description, H1,
        # etc.) client-side via JavaScript after initial load. A plain HTTP
        # GET (above) can never see that content, so we render the page in
        # headless Chromium and parse the DOM *after* JS has executed.
        # httpx remains the source of truth for header/timing/protocol-level
        # signals above; the rendered HTML below is used for all DOM parsing.
        raw_word_count = len(BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True).split())
        if depth == "lite":
            # Skip the browser entirely -- this is the other half of what
            # makes lite mode cheap/fast. Reuse the exact same degradation
            # path live_checks.py already has for a *failed* render (rather
            # than inventing a new status), so DOM-dependent checks report
            # honest NOT_APPLICABLE instead of a false FAIL on the raw HTML.
            rendered_html, js_rendered, js_render_failed, rendered_bytes = None, False, True, None
        else:
            rendered_html, js_rendered, js_render_failed, rendered_bytes = _render_and_verify(
                final_url, resp.text, raw_word_count)

        if rendered_html:
            html = rendered_html
            profile["js_rendered"] = js_rendered
            profile["js_render_failed"] = js_render_failed
            if rendered_bytes:
                # Total transferred bytes across all page resources (JS/CSS/
                # images included) is a more accurate "page weight" signal
                # than the initial HTML document alone, now that a full
                # browser load happened anyway.
                profile["page_size_bytes"] = rendered_bytes
        else:
            html = resp.text
            profile["js_rendered"] = False
            # We could not render this page's JavaScript at all, AND the raw
            # HTML we're falling back to looks like an empty app shell rather
            # than real content. Content-dependent checks (H1, headings,
            # images, internal links, word count -- see live_checks.py)
            # must NOT report confident "0 found" failures in this case;
            # that would tell the customer their page has no content when
            # we simply couldn't see it. live_checks.py checks this flag
            # and reports "Data unavailable" instead for those checks.
            profile["js_render_failed"] = js_render_failed
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")

        title_tag = soup.find("title")
        profile["title"] = title_tag.get_text(strip=True) if title_tag else None

        meta_desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        profile["meta_description"] = (meta_desc.get("content") or "").strip() if meta_desc else None

        h1s = soup.find_all("h1")
        profile["h1_count"] = len(h1s)
        profile["h1_text"] = h1s[0].get_text(strip=True) if h1s else None

        profile["heading_counts"] = {tag: len(soup.find_all(tag)) for tag in ["h2", "h3", "h4", "h5", "h6"]}

        imgs = soup.find_all("img")
        profile["image_count"] = len(imgs)
        profile["images_missing_alt"] = sum(1 for i in imgs if not (i.get("alt") or "").strip())

        body_text = soup.get_text(" ", strip=True)
        profile["word_count"] = len(body_text.split())

        viewport = soup.find("meta", attrs={"name": "viewport"})
        profile["has_viewport"] = bool(viewport)

        canonical = soup.find("link", attrs={"rel": "canonical"})
        profile["canonical_href"] = canonical.get("href") if canonical else None

        robots_meta = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
        robots_content = (robots_meta.get("content") or "").lower() if robots_meta else ""
        profile["has_noindex"] = "noindex" in robots_content

        links = soup.find_all("a", href=True)
        internal = external = 0
        social_found = set()
        for a in links:
            href = a["href"]
            href_l = href.lower()
            for sd in SOCIAL_DOMAINS:
                if sd in href_l:
                    social_found.add(sd)
            if href.startswith("#") or href_l.startswith("mailto:") or href_l.startswith("tel:") or href.startswith("javascript:"):
                continue
            joined = urljoin(base, href)
            if urlparse(joined).netloc == final_parsed.netloc:
                internal += 1
            else:
                external += 1
        profile["internal_link_count"] = internal
        profile["external_link_count"] = external
        profile["social_profiles_found"] = sorted(social_found)

        profile["url_has_query_or_id_pattern"] = bool(re.search(r"\?\S", final_parsed.path + "?" + (final_parsed.query or "")) or re.search(r"/\d{3,}(/|$)", final_parsed.path))

        # Structured data (JSON-LD)
        ld_types = []
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "{}")
            except Exception:
                continue
            candidates = data if isinstance(data, list) else [data]
            for c in candidates:
                if isinstance(c, dict):
                    t = c.get("@type")
                    if isinstance(t, list):
                        ld_types.extend(str(x) for x in t)
                    elif t:
                        ld_types.append(str(t))
        profile["structured_data_types"] = ld_types
        profile["has_faq_schema"] = "FAQPage" in ld_types

        profile["has_open_graph"] = len(soup.find_all("meta", property=re.compile("^og:"))) > 0

        html_lower = html.lower()
        profile["analytics_signals"] = [name for pattern, name in ANALYTICS_SIGNATURES if pattern in html_lower]
        profile["trust_signal_matches"] = [k for k in TRUST_KEYWORDS if k in html_lower]

        faq_heading = bool(soup.find(
            lambda tag: tag.name in ("h1", "h2", "h3")
            and ("faq" in tag.get_text(strip=True).lower() or "frequently asked" in tag.get_text(strip=True).lower())
        ))
        profile["has_faq_content"] = profile["has_faq_schema"] or faq_heading

        phone_match = PHONE_RE.search(body_text)
        profile["phone_found"] = phone_match.group(0) if phone_match else None
        address_match = ADDRESS_RE.search(body_text)
        profile["address_found"] = address_match.group(0) if address_match else None

        profile["service_area_mentions"] = len(re.findall(r"serving\b|service area\b|we serve\b|areas we serve", html_lower))

        profile["has_date_signal"] = bool(
            soup.find("meta", attrs={"property": re.compile("article:modified_time|article:published_time", re.I)})
        ) or bool(re.search(r"(updated|last modified)\s*:?\s*[a-z]+\s+\d{1,2},?\s+\d{4}", html_lower))

        # Nav / mobile navigation heuristic
        nav = soup.find("nav")
        toggle = soup.find(attrs={"class": re.compile("toggle|hamburger|menu-btn|navbar-toggler", re.I)}) or \
            soup.find(attrs={"aria-label": re.compile("menu|navigation", re.I)})
        profile["has_nav"] = bool(nav)
        profile["has_mobile_nav_toggle"] = bool(toggle)

        # Forms / form accessibility
        forms = soup.find_all("form")
        profile["form_count"] = len(forms)
        if forms:
            inputs = [i for i in forms[0].find_all(["input", "textarea", "select"])
                      if i.get("type") not in ("hidden", "submit", "button")]
            labeled = 0
            for inp in inputs:
                has_label = bool(inp.get("aria-label")) or bool(inp.get("placeholder"))
                input_id = inp.get("id")
                if not has_label and input_id and soup.find("label", attrs={"for": input_id}):
                    has_label = True
                if has_label:
                    labeled += 1
            profile["form_fields_total"] = len(inputs)
            profile["form_fields_labeled"] = labeled
        else:
            profile["form_fields_total"] = None
            profile["form_fields_labeled"] = None

        # Minification heuristic: fraction of linked css/js assets whose
        # filename contains ".min." — a real, observable naming convention,
        # not a guess about actual byte-level minification.
        asset_srcs = [tag.get("src") for tag in soup.find_all("script", src=True)]
        asset_srcs += [tag.get("href") for tag in soup.find_all("link", rel="stylesheet")]
        asset_srcs = [s for s in asset_srcs if s]
        if asset_srcs:
            minified = sum(1 for s in asset_srcs if ".min." in s.lower())
            profile["asset_count"] = len(asset_srcs)
            profile["asset_minified_ratio"] = round(minified / len(asset_srcs), 2)
        else:
            profile["asset_count"] = 0
            profile["asset_minified_ratio"] = None

        # ---- robots.txt ----
        r_resp = _get(client, urljoin(base, "/robots.txt"))
        if r_resp is not None and r_resp.status_code == 200 and r_resp.text.strip():
            robots_txt = r_resp.text
            profile["robots_txt_found"] = True
            lower_robots = robots_txt.lower()
            blocked_ai = []
            for bot in AI_CRAWLER_NAMES:
                pattern = re.compile(rf"user-agent:\s*{re.escape(bot.lower())}\s*(.*?)(?=user-agent:|\Z)", re.S)
                m_ = pattern.search(lower_robots)
                if m_ and re.search(r"disallow:\s*/\s*(#.*)?$", m_.group(1), re.M):
                    blocked_ai.append(bot)
            profile["ai_crawlers_blocked"] = blocked_ai
        else:
            profile["robots_txt_found"] = False
            profile["ai_crawlers_blocked"] = []

        # ---- sitemap.xml ----
        s_resp = _get(client, urljoin(base, "/sitemap.xml"))
        profile["sitemap_found"] = bool(
            s_resp is not None and s_resp.status_code == 200 and
            ("<urlset" in s_resp.text.lower() or "<sitemapindex" in s_resp.text.lower())
        )

        # ---- llms.txt ----
        l_resp = _get(client, urljoin(base, "/llms.txt"))
        profile["llms_txt_found"] = bool(l_resp is not None and l_resp.status_code == 200 and l_resp.text.strip())

        # ---- HTTP -> HTTPS redirect ----
        if final_parsed.scheme == "https":
            try:
                with httpx.Client(follow_redirects=False, headers=headers, timeout=TIMEOUT) as nc:
                    h_resp = nc.get(f"http://{final_parsed.netloc}/")
                profile["http_redirects_to_https"] = (
                    h_resp.status_code in (301, 302, 307, 308)
                    and h_resp.headers.get("location", "").startswith("https://")
                )
            except Exception:
                profile["http_redirects_to_https"] = None
        else:
            profile["http_redirects_to_https"] = False

        # ---- DNS: SPF / DMARC ----
        profile["spf_found"] = False
        profile["dmarc_found"] = False
        if dns is not None:
            resolve_domain = final_parsed.netloc
            try:
                answers = dns.resolver.resolve(resolve_domain, "TXT", lifetime=6)
                for a in answers:
                    txt = b"".join(a.strings).decode(errors="ignore") if hasattr(a, "strings") else str(a)
                    if txt.lower().startswith("v=spf1"):
                        profile["spf_found"] = True
            except Exception:
                pass
            try:
                answers = dns.resolver.resolve(f"_dmarc.{resolve_domain}", "TXT", lifetime=6)
                for a in answers:
                    txt = b"".join(a.strings).decode(errors="ignore") if hasattr(a, "strings") else str(a)
                    if txt.lower().startswith("v=dmarc1"):
                        profile["dmarc_found"] = True
            except Exception:
                pass

        # ---- Google PageSpeed Insights + Places: collect results ----
        # (kicked off in the background right after final_url was known,
        # above — by now they've had the entire scrape's wall-clock time to
        # run concurrently with it, so this typically just picks up
        # already-finished results rather than waiting from scratch.)
        try:
            profile["pagespeed_mobile"], profile["pagespeed_desktop"] = (
                pagespeed_future.result() if pagespeed_future is not None else (None, None)
            )
        except Exception:
            profile["pagespeed_mobile"] = None
            profile["pagespeed_desktop"] = None

        if places_future is not None:
            try:
                profile["places_result"] = places_future.result()
            except Exception:
                profile["places_result"] = None
        else:
            profile["places_result"] = None
        bg_pool.shutdown(wait=False)

        return profile
    finally:
        client.close()
