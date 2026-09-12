"""Phase 2 check catalog: computes real check results from a live_collector
profile, in the exact same output shape as checks.py's run_checks() so
scoring.py / recommendations.py / engine.py never need to know whether an
audit came from the Phase 1 sample-data path or this real one.

Every check below either:
  (a) computes a status from directly-observed page/header/DNS data, or
  (b) is marked NOT_APPLICABLE with an honest "Data unavailable" message,
      for anything that would require a paid third-party API we haven't
      connected yet (Core Web Vitals / Lighthouse via PageSpeed Insights,
      backlink data, Google Business Profile).

NOT_APPLICABLE checks always have rec_title=None, so recommendations.py
automatically skips them, and scoring.py excludes them from the weighted
average — an entire category with every check NOT_APPLICABLE (e.g.
Authority, until a backlink API is connected) ends up with a `None` score
and a "Data Unavailable" status label rather than a fabricated number.
"""

STATUS_PASS = "PASS"
STATUS_WARNING = "WARNING"
STATUS_FAIL = "FAIL"
STATUS_NOT_DETECTED = "NOT_DETECTED"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"

DATA_SOURCE = "live_crawl"


def _r(category, key, name, weight, status, result, raw=None, expected=None, why=None,
       rec_title=None, rec_action=None, rec_impact=None, rec_effort=None, rec_difficulty=None):
    return {
        "category": category, "key": key, "name": name, "weight": weight,
        "status": status, "result": result, "raw_value": raw, "expected_value": expected,
        "business_explanation": why, "data_source": DATA_SOURCE,
        "rec_title": rec_title, "rec_action": rec_action, "rec_impact": rec_impact,
        "rec_effort": rec_effort, "rec_difficulty": rec_difficulty,
    }


def _na(category, key, name, weight, why, expected=None):
    """A check we honestly can't evaluate yet (needs an unconnected paid API)."""
    return _r(category, key, name, weight, STATUS_NOT_APPLICABLE,
              "Data unavailable — this check requires a data source we haven't connected yet.",
              raw="Data unavailable", expected=expected, why=why)


def run_checks(profile: dict) -> list[dict]:
    checks = []

    # If we couldn't render this page's JavaScript AND the raw HTML we fell
    # back to looks like an empty app shell (see live_collector.py's
    # _looks_like_thin_spa_shell), several checks below would otherwise
    # confidently report "0 H1 tags", "0 images", "~9 words", etc. -- which
    # reads as "your page has no content" when the truth is "we couldn't see
    # your content this time." Route those specific checks to an honest
    # NOT_APPLICABLE instead of a false FAIL/NOT_DETECTED.
    render_uncertain = bool(profile.get("js_render_failed"))

    def _render_na(category, key, name, weight):
        return _r(category, key, name, weight, STATUS_NOT_APPLICABLE,
            "Could not verify — this page appears to load its content via JavaScript, and our crawler wasn't able to fully render it on this pass.",
            raw="Render incomplete", expected="Verified after a successful render",
            why="This does not mean the content is missing -- just that we couldn't confirm it this time. Re-running the audit often resolves this, "
                "since JavaScript rendering can occasionally fail on a given attempt.")

    # =================== ON-PAGE SEO ===================
    title = profile.get("title") or ""
    tlen = len(title)
    if not title:
        checks.append(_r("on_page_seo", "title_tag", "Title Tag", 3, STATUS_FAIL,
            "Your page is missing a title tag.", raw="Not found", expected="50-60 characters",
            why="Without a title tag, search engines have to guess what your page is about, which typically hurts rankings and click-through rates.",
            rec_title="Add a Title Tag", rec_action="Add a unique, descriptive title tag to every important page.",
            rec_impact="Search visibility & rankings", rec_effort="Low", rec_difficulty="Low"))
    elif 50 <= tlen <= 60:
        checks.append(_r("on_page_seo", "title_tag", "Title Tag", 3, STATUS_PASS,
            "Your page has a well-optimized title tag.", raw=f"{tlen} characters", expected="50-60 characters",
            why="A clear, well-sized title tag helps search engines and searchers understand your page at a glance, which directly affects click-through rates from search results."))
    else:
        checks.append(_r("on_page_seo", "title_tag", "Title Tag", 3, STATUS_WARNING,
            "Your title tag is present but not ideally sized.", raw=f"{tlen} characters", expected="50-60 characters",
            why="Titles that are too short waste an opportunity to describe your page; titles that are too long get cut off in search results.",
            rec_title="Optimize Title Tag Length", rec_action="Rewrite the title tag to fall between 50-60 characters while including your main service and location.",
            rec_impact="Search visibility & click-through rate", rec_effort="Low", rec_difficulty="Low"))

    meta_desc = profile.get("meta_description") or ""
    mlen = len(meta_desc)
    if not meta_desc:
        checks.append(_r("on_page_seo", "meta_description", "Meta Description", 2, STATUS_FAIL,
            "Your page is missing a meta description.", raw="Not found", expected="120-160 characters",
            why="Without a meta description, search engines will auto-generate one from your page text, which is often less compelling.",
            rec_title="Add Meta Descriptions", rec_action="Write a unique, benefit-focused meta description for every important page.",
            rec_impact="Search click-through rate", rec_effort="Low", rec_difficulty="Low"))
    elif 120 <= mlen <= 160:
        checks.append(_r("on_page_seo", "meta_description", "Meta Description", 2, STATUS_PASS,
            "Your meta description is present and well-sized.", raw=f"{mlen} characters", expected="120-160 characters",
            why="A good meta description acts like ad copy in search results and can improve your click-through rate."))
    else:
        checks.append(_r("on_page_seo", "meta_description", "Meta Description", 2, STATUS_WARNING,
            "Your meta description is present but not ideally sized.", raw=f"{mlen} characters", expected="120-160 characters",
            why="Meta descriptions that are too short or too long may be truncated or under-utilized in search results.",
            rec_title="Adjust Meta Description Length", rec_action="Rewrite the meta description to be between 120-160 characters, highlighting your key differentiator.",
            rec_impact="Search click-through rate", rec_effort="Low", rec_difficulty="Low"))

    h1_count = profile.get("h1_count", 0)
    if render_uncertain:
        checks.append(_render_na("on_page_seo", "h1_tag", "H1 Header Tag", 2))
    elif h1_count == 1:
        checks.append(_r("on_page_seo", "h1_tag", "H1 Header Tag", 2, STATUS_PASS,
            "Your page has a single, clear H1 tag.", raw="1 H1 tag found", expected="Exactly 1 H1 tag",
            why="The H1 tag tells both visitors and search engines the main topic of the page."))
    else:
        checks.append(_r("on_page_seo", "h1_tag", "H1 Header Tag", 2, STATUS_FAIL,
            "Your page is missing an H1 tag, or has multiple conflicting H1 tags.", raw=f"{h1_count} H1 tags found", expected="Exactly 1 H1 tag",
            why="Missing or duplicate H1 tags make it harder for search engines to understand your page's main topic.",
            rec_title="Fix H1 Header Tag Usage", rec_action="Ensure every page has exactly one H1 tag summarizing its main topic.",
            rec_impact="Content clarity & rankings", rec_effort="Low", rec_difficulty="Low"))

    hc = profile.get("heading_counts", {}) or {}
    h2 = hc.get("h2", 0)
    lower_present = any(hc.get(t, 0) for t in ("h3", "h4", "h5", "h6"))
    if render_uncertain:
        checks.append(_render_na("on_page_seo", "heading_structure", "H2-H6 Header Structure", 1))
    elif h2 > 0:
        checks.append(_r("on_page_seo", "heading_structure", "H2-H6 Header Structure", 1, STATUS_PASS,
            "Your page makes good use of multiple heading levels.", raw=f"H2: {h2}, H3: {hc.get('h3',0)}, H4: {hc.get('h4',0)}", expected="Logical H2-H6 hierarchy",
            why="A clear heading hierarchy makes content easier to scan for both readers and search engines."))
    elif lower_present:
        checks.append(_r("on_page_seo", "heading_structure", "H2-H6 Header Structure", 1, STATUS_WARNING,
            "Your page uses lower-level headings without any H2s, which skips a level in the hierarchy.", raw="H2 skipped, H3+ used directly", expected="Logical H2-H6 hierarchy",
            why="An inconsistent heading structure can confuse search engines about which sections are most important.",
            rec_title="Improve Heading Hierarchy", rec_action="Reorganize headings so H2s introduce major sections and H3-H6 nest logically beneath them.",
            rec_impact="Content structure & readability", rec_effort="Low", rec_difficulty="Low"))
    else:
        checks.append(_r("on_page_seo", "heading_structure", "H2-H6 Header Structure", 1, STATUS_NOT_DETECTED,
            "No secondary heading levels (H2-H6) were detected.", raw="No H2-H6 tags found", expected="Logical H2-H6 hierarchy",
            why="Without secondary headings, long pages can be harder to scan for both visitors and search engines.",
            rec_title="Add Secondary Headings", rec_action="Break up page content with descriptive H2/H3 headings.",
            rec_impact="Content structure & readability", rec_effort="Low", rec_difficulty="Low"))

    # Keyword/topic consistency: how much overlap exists between title words and H1/meta words
    def _sig_words(text):
        return {w for w in (text or "").lower().split() if len(w) > 3}
    title_words = _sig_words(title)
    overlap_targets = _sig_words(profile.get("h1_text")) | _sig_words(meta_desc)
    overlap = len(title_words & overlap_targets)
    if render_uncertain:
        checks.append(_render_na("on_page_seo", "keyword_consistency", "Keyword / Topic Consistency", 3))
    elif title_words and overlap >= 2:
        checks.append(_r("on_page_seo", "keyword_consistency", "Keyword / Topic Consistency", 3, STATUS_PASS,
            "Your main topics are consistently reflected across title, headings, and content.", raw=f"{overlap} shared significant words across title/H1/meta", expected="Consistent topical focus",
            why="When your core topics appear consistently across key HTML elements, search engines have a clearer signal of what you should rank for."))
    elif title_words and overlap == 1:
        checks.append(_r("on_page_seo", "keyword_consistency", "Keyword / Topic Consistency", 3, STATUS_WARNING,
            "Your page's main topics show only partial overlap across title, H1, and meta description.", raw="1 shared significant word", expected="Present in title, meta, headings & content",
            why="If your core topics only partially overlap across title, headings, and meta description, you may be missing easy ranking opportunities.",
            rec_title="Improve Keyword Placement Across Key Tags", rec_action="Work your primary services/topics naturally into the title, meta description, and headings.",
            rec_impact="Topical relevance & rankings", rec_effort="Medium", rec_difficulty="Low"))
    else:
        checks.append(_r("on_page_seo", "keyword_consistency", "Keyword / Topic Consistency", 3, STATUS_FAIL,
            "No clear, consistent topical focus was detected across title, headings, and meta description.", raw="No shared significant words", expected="Consistent topical focus",
            why="Without a clear topical focus, search engines struggle to know which searches your page should appear for.",
            rec_title="Establish Clear Page Topics", rec_action="Define 1-3 primary topics per page and reinforce them across title, headings, and content.",
            rec_impact="Topical relevance & rankings", rec_effort="Medium", rec_difficulty="Medium"))

    wc = profile.get("word_count", 0)
    if render_uncertain:
        checks.append(_render_na("on_page_seo", "content_length", "Content Length & Depth", 2))
    elif wc >= 600:
        checks.append(_r("on_page_seo", "content_length", "Content Length & Depth", 2, STATUS_PASS,
            "Your page has substantial, topic-relevant content.", raw=f"~{wc} words", expected="Sufficient depth for topic & intent",
            why="Pages with meaningful depth tend to answer more visitor questions and are more likely to satisfy search intent."))
    elif wc >= 150:
        checks.append(_r("on_page_seo", "content_length", "Content Length & Depth", 2, STATUS_WARNING,
            "Your page content is on the thin side for its topic.", raw=f"~{wc} words", expected="Sufficient depth for topic & intent",
            why="Thin content may not fully answer visitor questions, which can hurt both rankings and conversion.",
            rec_title="Increase Page Content Depth", rec_action="Expand key pages with more detail on services, benefits, process, and FAQs.",
            rec_impact="Search relevance & user engagement", rec_effort="Medium", rec_difficulty="Low"))
    else:
        checks.append(_r("on_page_seo", "content_length", "Content Length & Depth", 2, STATUS_FAIL,
            "Your page has very little text content.", raw=f"~{wc} words", expected="Sufficient depth for topic & intent",
            why="Extremely thin pages give search engines very little to work with and often struggle to rank at all.",
            rec_title="Add Substantial Page Content", rec_action="Add meaningful, unique content that explains your services, service area, and value proposition.",
            rec_impact="Search relevance & rankings", rec_effort="Medium", rec_difficulty="Medium"))

    img_count = profile.get("image_count", 0)
    missing_alt = profile.get("images_missing_alt", 0)
    if render_uncertain:
        checks.append(_render_na("on_page_seo", "image_alt_text", "Image Alt Attributes", 1))
    elif img_count == 0:
        checks.append(_r("on_page_seo", "image_alt_text", "Image Alt Attributes", 1, STATUS_NOT_DETECTED,
            "No images were detected on the page to evaluate.", raw="0 images found", expected="All meaningful images",
            why="This isn't necessarily a problem — it simply means we couldn't evaluate image alt text on the page reviewed."))
    else:
        missing_ratio = missing_alt / img_count
        if missing_ratio <= 0.15:
            checks.append(_r("on_page_seo", "image_alt_text", "Image Alt Attributes", 1, STATUS_PASS,
                "Most images have descriptive alt attributes.", raw=f"{img_count - missing_alt}/{img_count} images", expected="All meaningful images",
                why="Alt text helps search engines understand images and improves accessibility for visitors using screen readers."))
        elif missing_ratio <= 0.6:
            checks.append(_r("on_page_seo", "image_alt_text", "Image Alt Attributes", 1, STATUS_WARNING,
                "Some images are missing alt attributes.", raw=f"{img_count - missing_alt}/{img_count} images", expected="All meaningful images",
                why="Missing alt text is a minor but easy-to-fix accessibility and SEO gap.",
                rec_title="Add Alt Attributes to All Images", rec_action="Add descriptive alt text to every meaningful image, including your logo and service photos.",
                rec_impact="Accessibility & image search", rec_effort="Low", rec_difficulty="Low"))
        else:
            checks.append(_r("on_page_seo", "image_alt_text", "Image Alt Attributes", 1, STATUS_FAIL,
                "Most images are missing alt attributes.", raw=f"{img_count - missing_alt}/{img_count} images", expected="All meaningful images",
                why="Without alt text, search engines and screen readers can't interpret your images at all.",
                rec_title="Add Alt Attributes to All Images", rec_action="Add descriptive alt text to every meaningful image, including your logo and service photos.",
                rec_impact="Accessibility & image search", rec_effort="Low", rec_difficulty="Low"))

    if profile.get("url_has_query_or_id_pattern"):
        checks.append(_r("on_page_seo", "url_structure", "URL Structure", 1, STATUS_WARNING,
            "This page's URL contains query parameters or an ID-style pattern rather than a clean, descriptive path.", raw=profile.get("final_url", ""), expected="Descriptive, hyphenated URLs",
            why="Unclear URLs are harder for visitors to trust and give search engines less context about the page.",
            rec_title="Clean Up URL Structure", rec_action="Use short, descriptive, hyphenated URLs for important pages going forward.",
            rec_impact="User trust & crawlability", rec_effort="Medium", rec_difficulty="Medium"))
    else:
        checks.append(_r("on_page_seo", "url_structure", "URL Structure", 1, STATUS_PASS,
            "Your URL is clean and human-readable.", raw=profile.get("final_url", ""), expected="Descriptive, hyphenated URLs",
            why="Clean URLs are easier for visitors to trust and share, and give search engines an extra relevance signal."))

    internal_links = profile.get("internal_link_count", 0)
    if render_uncertain:
        checks.append(_render_na("on_page_seo", "internal_linking", "Internal Linking", 2))
    elif internal_links >= 5:
        checks.append(_r("on_page_seo", "internal_linking", "Internal Linking", 2, STATUS_PASS,
            "Your page links well to other relevant pages on your site.", raw=f"{internal_links} internal links", expected="Meaningful internal linking",
            why="Internal links help visitors discover more of your content and help search engines understand site structure."))
    else:
        checks.append(_r("on_page_seo", "internal_linking", "Internal Linking", 2, STATUS_WARNING,
            "Your page has very few internal links to other pages.", raw=f"{internal_links} internal link(s)", expected="Meaningful internal linking",
            why="Limited internal linking makes it harder for visitors and search engines to find your other important pages.",
            rec_title="Improve Internal Linking", rec_action="Add contextual links from this page to related services, locations, or blog content.",
            rec_impact="Site structure & page authority flow", rec_effort="Low", rec_difficulty="Low"))

    # =================== TECHNICAL SEO ===================
    scheme = profile.get("scheme")
    if scheme == "https":
        checks.append(_r("technical_seo", "https", "HTTPS", 3, STATUS_PASS,
            "Your website loads securely over HTTPS.", raw="HTTPS enabled", expected="HTTPS enabled",
            why="HTTPS is a baseline trust and ranking signal, and browsers flag non-HTTPS sites as 'Not Secure'."))
    else:
        checks.append(_r("technical_seo", "https", "HTTPS", 3, STATUS_FAIL,
            "Your website does not load over HTTPS.", raw="HTTP only", expected="HTTPS enabled",
            why="Without HTTPS, browsers warn visitors your site isn't secure, which damages trust and can hurt rankings.",
            rec_title="Enable HTTPS Site-Wide", rec_action="Install an SSL certificate and force all traffic to HTTPS.",
            rec_impact="Trust, security & rankings", rec_effort="Low", rec_difficulty="Low"))

    redirect = profile.get("http_redirects_to_https")
    if scheme != "https":
        checks.append(_na("technical_seo", "http_to_https_redirect", "HTTP to HTTPS Redirect", 1,
            "This site doesn't serve HTTPS at all yet, so a redirect check doesn't apply — see the HTTPS check above.",
            expected="301 redirect to HTTPS"))
    elif redirect is True:
        checks.append(_r("technical_seo", "http_to_https_redirect", "HTTP to HTTPS Redirect", 1, STATUS_PASS,
            "HTTP requests correctly redirect to HTTPS.", raw="Redirect confirmed", expected="301 redirect to HTTPS",
            why="This ensures visitors and search engines always land on the secure version of your site."))
    elif redirect is False:
        checks.append(_r("technical_seo", "http_to_https_redirect", "HTTP to HTTPS Redirect", 1, STATUS_WARNING,
            "HTTP does not cleanly redirect to HTTPS.", raw="No redirect detected", expected="301 redirect to HTTPS",
            why="Without a redirect, some visitors or old links may load an insecure, unindexed version of your site.",
            rec_title="Add HTTP to HTTPS Redirect", rec_action="Configure a site-wide 301 redirect from HTTP to HTTPS.",
            rec_impact="Security & duplicate content prevention", rec_effort="Low", rec_difficulty="Low"))
    else:
        checks.append(_na("technical_seo", "http_to_https_redirect", "HTTP to HTTPS Redirect", 1,
            "We couldn't reliably test the plain-HTTP version of this site (the request failed or timed out).",
            expected="301 redirect to HTTPS"))

    if profile.get("robots_txt_found"):
        checks.append(_r("technical_seo", "robots_txt", "Robots.txt", 1, STATUS_PASS,
            "A robots.txt file was found.", raw="/robots.txt found", expected="Valid robots.txt",
            why="Robots.txt gives search engines guidance on which parts of your site to crawl."))
    else:
        checks.append(_r("technical_seo", "robots_txt", "Robots.txt", 1, STATUS_NOT_DETECTED,
            "No robots.txt file was found.", raw="Not found", expected="Valid robots.txt",
            why="Without robots.txt, search engines will crawl using default behavior, which is usually fine but leaves you without explicit control.",
            rec_title="Add a Robots.txt File", rec_action="Create a robots.txt file to guide search engine crawling behavior.",
            rec_impact="Crawl efficiency", rec_effort="Low", rec_difficulty="Low"))

    if profile.get("sitemap_found"):
        checks.append(_r("technical_seo", "xml_sitemap", "XML Sitemap", 2, STATUS_PASS,
            "An XML sitemap was found.", raw="/sitemap.xml found", expected="Valid XML sitemap",
            why="A sitemap helps search engines discover and index all of your important pages efficiently."))
    else:
        checks.append(_r("technical_seo", "xml_sitemap", "XML Sitemap", 2, STATUS_NOT_DETECTED,
            "No XML sitemap was found at /sitemap.xml.", raw="Not found", expected="Valid XML sitemap",
            why="Without a sitemap, search engines rely solely on links to discover your pages, which can slow down indexing of new content.",
            rec_title="Implement an XML Sitemap File", rec_action="Generate an XML sitemap and submit it in Google Search Console.",
            rec_impact="Search engine crawlability", rec_effort="Low", rec_difficulty="Low"))

    if profile.get("canonical_href"):
        checks.append(_r("technical_seo", "canonical_tag", "Canonical Tag", 2, STATUS_PASS,
            "A canonical tag is present.", raw=profile["canonical_href"], expected="Valid canonical tag",
            why="Canonical tags prevent duplicate content issues when multiple URLs show similar content."))
    else:
        checks.append(_r("technical_seo", "canonical_tag", "Canonical Tag", 2, STATUS_NOT_DETECTED,
            "No canonical tag was found.", raw="Not found", expected="Self-referencing canonical",
            why="Without canonical tags, similar or duplicate pages could compete against each other in search results.",
            rec_title="Add Canonical Tags", rec_action="Add self-referencing canonical tags to all indexable pages.",
            rec_impact="Duplicate content prevention", rec_effort="Low", rec_difficulty="Low"))

    if profile.get("has_noindex"):
        checks.append(_r("technical_seo", "noindex_directive", "Noindex Directive", 3, STATUS_FAIL,
            "A noindex directive was found on this page.", raw="noindex meta tag present", expected="No noindex on important pages",
            why="A noindex tag tells search engines to exclude the page entirely from search results, which can silently remove key pages from Google.",
            rec_title="Remove Unintended Noindex Directive", rec_action="Remove the noindex tag/header from pages that should appear in search results.",
            rec_impact="Search visibility", rec_effort="Low", rec_difficulty="Low"))
    else:
        checks.append(_r("technical_seo", "noindex_directive", "Noindex Directive", 3, STATUS_PASS,
            "This page is indexable (no blocking noindex directive found).", raw="No noindex found", expected="No noindex on important pages",
            why="This confirms search engines are allowed to index and rank your important pages."))

    sd_types = profile.get("structured_data_types", []) or []
    if any(t in ("Organization", "LocalBusiness") for t in sd_types) or any("LocalBusiness" in t for t in sd_types):
        checks.append(_r("technical_seo", "structured_data_org", "Organization / LocalBusiness Schema", 2, STATUS_PASS,
            "Organization/LocalBusiness structured data was found.", raw=", ".join(sd_types) or "Detected", expected="Organization or LocalBusiness schema",
            why="Structured data helps search engines (and increasingly AI assistants) clearly understand who you are and what you do."))
    else:
        checks.append(_r("technical_seo", "structured_data_org", "Organization / LocalBusiness Schema", 2, STATUS_NOT_DETECTED,
            "No Organization or LocalBusiness structured data was found.", raw="Not found", expected="Organization or LocalBusiness schema",
            why="Without structured data, search engines and AI tools have to infer your business details from unstructured text, which is less reliable.",
            rec_title="Add LocalBusiness Structured Data", rec_action="Implement LocalBusiness (or Organization) schema markup with name, address, phone, and hours.",
            rec_impact="Search & AI entity recognition", rec_effort="Medium", rec_difficulty="Medium"))

    if profile.get("has_viewport"):
        checks.append(_r("technical_seo", "mobile_viewport", "Mobile Viewport Tag", 2, STATUS_PASS,
            "A mobile viewport meta tag is present.", raw="Viewport tag found", expected="Responsive viewport tag",
            why="The viewport tag is required for your site to render correctly and scale properly on phones and tablets."))
    else:
        checks.append(_r("technical_seo", "mobile_viewport", "Mobile Viewport Tag", 2, STATUS_FAIL,
            "No mobile viewport meta tag was found.", raw="Not found", expected="Responsive viewport tag",
            why="Without this tag, your site may display as a shrunken desktop layout on mobile devices, hurting usability.",
            rec_title="Add a Mobile Viewport Meta Tag", rec_action="Add a responsive viewport meta tag to the site template.",
            rec_impact="Mobile usability & rankings", rec_effort="Low", rec_difficulty="Low"))

    http_version = profile.get("http_version") or ""
    if http_version.upper() in ("HTTP/2", "HTTP/3"):
        checks.append(_r("technical_seo", "http_protocol", "HTTP/2 or HTTP/3 Support", 1, STATUS_PASS,
            "Your server supports a modern HTTP protocol version.", raw=http_version, expected="HTTP/2 or HTTP/3",
            why="Modern protocols allow browsers to load your pages faster through better connection handling."))
    else:
        checks.append(_r("technical_seo", "http_protocol", "HTTP/2 or HTTP/3 Support", 1, STATUS_NOT_DETECTED,
            "Unable to confirm HTTP/2 or HTTP/3 support.", raw=http_version or "HTTP/1.1", expected="HTTP/2 or HTTP/3",
            why="Older protocols can mean slightly slower page loads, especially on pages with many resources.",
            rec_title="Upgrade Server to HTTP/2 or HTTP/3", rec_action="Work with your host/CDN to enable HTTP/2 or HTTP/3.",
            rec_impact="Page load speed", rec_effort="Low", rec_difficulty="Medium"))

    # =================== PERFORMANCE ===================
    mobile_ps = profile.get("pagespeed_mobile")
    desktop_ps = profile.get("pagespeed_desktop")

    def _perf_score_check(key, name, weight, ps):
        score = ps.get("performance_score") if ps else None
        if score is None:
            return _na("performance", key, name, weight,
                "A true performance score requires Google PageSpeed Insights / Lighthouse. The API call didn't return a score for this page (or the API isn't connected).",
                expected="90+")
        if score >= 90:
            return _r("performance", key, name, weight, STATUS_PASS,
                "Lighthouse reports a strong performance score.", raw=f"{score}/100", expected="90+",
                why="A high performance score generally means faster load times and a better user experience, which search engines factor into rankings.")
        elif score >= 50:
            return _r("performance", key, name, weight, STATUS_WARNING,
                "Lighthouse reports a moderate performance score with room for improvement.", raw=f"{score}/100", expected="90+",
                why="A moderate score suggests some visitors experience slower load times, which can hurt conversions and rankings.",
                rec_title=f"Improve {name}", rec_action="Review the Lighthouse report for specific opportunities (image sizing, render-blocking resources, server response time).",
                rec_impact="Page load speed & rankings", rec_effort="Medium", rec_difficulty="Medium")
        else:
            return _r("performance", key, name, weight, STATUS_FAIL,
                "Lighthouse reports a poor performance score.", raw=f"{score}/100", expected="90+",
                why="A low score means many visitors are likely experiencing slow load times, which hurts both user experience and search rankings.",
                rec_title=f"Improve {name}", rec_action="Address the highest-impact Lighthouse opportunities: optimize images, reduce JavaScript, and improve server response time.",
                rec_impact="Page load speed & rankings", rec_effort="High", rec_difficulty="Medium")

    checks.append(_perf_score_check("mobile_performance", "Mobile Performance Score", 3, mobile_ps))
    checks.append(_perf_score_check("desktop_performance", "Desktop Performance Score", 2, desktop_ps))

    # LCP and CLS come from the mobile PageSpeed run (mobile is the
    # stricter/more representative signal for most sites).
    lcp_seconds = mobile_ps.get("lcp_seconds") if mobile_ps else None
    if lcp_seconds is None:
        checks.append(_na("performance", "lcp", "Largest Contentful Paint (LCP)", 2,
            "Largest Contentful Paint requires real browser timing data from Google PageSpeed Insights, which didn't return a value for this page (or the API isn't connected).",
            expected="< 2.5s"))
    elif lcp_seconds <= 2.5:
        checks.append(_r("performance", "lcp", "Largest Contentful Paint (LCP)", 2, STATUS_PASS,
            "The main content of the page loads quickly.", raw=f"{lcp_seconds}s", expected="< 2.5s",
            why="A fast LCP means visitors see the main content of your page quickly, which improves user experience and search rankings."))
    elif lcp_seconds <= 4.0:
        checks.append(_r("performance", "lcp", "Largest Contentful Paint (LCP)", 2, STATUS_WARNING,
            "The main content of the page takes a moderate amount of time to load.", raw=f"{lcp_seconds}s", expected="< 2.5s",
            why="A slower LCP means visitors wait longer to see your main content, which can increase bounce rates.",
            rec_title="Improve Largest Contentful Paint", rec_action="Optimize the largest above-the-fold image or text block: compress images, preload key resources, and reduce server response time.",
            rec_impact="Page load speed & rankings", rec_effort="Medium", rec_difficulty="Medium"))
    else:
        checks.append(_r("performance", "lcp", "Largest Contentful Paint (LCP)", 2, STATUS_FAIL,
            "The main content of the page takes too long to load.", raw=f"{lcp_seconds}s", expected="< 2.5s",
            why="A slow LCP significantly hurts user experience and is a factor Google uses in search rankings.",
            rec_title="Improve Largest Contentful Paint", rec_action="Reduce server response time, compress and preload the largest above-the-fold content, and eliminate render-blocking resources.",
            rec_impact="Page load speed & rankings", rec_effort="High", rec_difficulty="Medium"))

    cls_value = mobile_ps.get("cls_value") if mobile_ps else None
    if cls_value is None:
        checks.append(_na("performance", "cls", "Cumulative Layout Shift (CLS)", 1,
            "Cumulative Layout Shift requires real browser rendering data from Google PageSpeed Insights, which didn't return a value for this page (or the API isn't connected).",
            expected="< 0.1"))
    elif cls_value <= 0.1:
        checks.append(_r("performance", "cls", "Cumulative Layout Shift (CLS)", 1, STATUS_PASS,
            "The page layout is visually stable as it loads.", raw=f"{cls_value}", expected="< 0.1",
            why="A low CLS means page elements don't unexpectedly shift around while loading, which prevents accidental clicks and frustration."))
    elif cls_value <= 0.25:
        checks.append(_r("performance", "cls", "Cumulative Layout Shift (CLS)", 1, STATUS_WARNING,
            "The page layout shifts a moderate amount as it loads.", raw=f"{cls_value}", expected="< 0.1",
            why="Noticeable layout shift can cause visitors to accidentally click the wrong thing, hurting user experience.",
            rec_title="Reduce Cumulative Layout Shift", rec_action="Set explicit width/height on images and embeds, and avoid inserting content above existing content after load.",
            rec_impact="User experience & rankings", rec_effort="Medium", rec_difficulty="Medium"))
    else:
        checks.append(_r("performance", "cls", "Cumulative Layout Shift (CLS)", 1, STATUS_FAIL,
            "The page layout shifts significantly as it loads.", raw=f"{cls_value}", expected="< 0.1",
            why="High layout shift creates a jarring, unreliable experience and is a factor in Google's page experience ranking signals.",
            rec_title="Reduce Cumulative Layout Shift", rec_action="Set explicit dimensions for images/ads/embeds, preload web fonts, and avoid dynamically injected content above the fold.",
            rec_impact="User experience & rankings", rec_effort="Medium", rec_difficulty="Medium"))

    page_size = profile.get("page_size_bytes")
    if page_size is not None:
        mb = page_size / (1024 * 1024)
        if mb < 2.5:
            checks.append(_r("performance", "page_size", "Total Page Size", 1, STATUS_PASS,
                "Page size is reasonable.", raw=f"{mb:.1f} MB", expected="< 2.5 MB",
                why="Smaller page sizes generally load faster, especially on mobile connections."))
        elif mb < 6:
            checks.append(_r("performance", "page_size", "Total Page Size", 1, STATUS_WARNING,
                "Page size is larger than ideal.", raw=f"{mb:.1f} MB", expected="< 2.5 MB",
                why="Larger page sizes take longer to download, especially for visitors on mobile networks.",
                rec_title="Reduce Total Page Size", rec_action="Compress and resize images, and remove unused CSS/JS.",
                rec_impact="Page load speed", rec_effort="Medium", rec_difficulty="Low"))
        else:
            checks.append(_r("performance", "page_size", "Total Page Size", 1, STATUS_FAIL,
                "Page size is significantly larger than recommended.", raw=f"{mb:.1f} MB", expected="< 2.5 MB",
                why="Very large pages create a poor experience for mobile visitors and slow-connection users.",
                rec_title="Reduce Total Page Size", rec_action="Audit and compress large media files; consider lazy-loading below-the-fold images.",
                rec_impact="Page load speed", rec_effort="Medium", rec_difficulty="Medium"))
    else:
        checks.append(_na("performance", "page_size", "Total Page Size", 1, "The page size couldn't be measured for this crawl.", expected="< 2.5 MB"))

    image_score = mobile_ps.get("image_optimization_score") if mobile_ps else None
    if image_score is None:
        checks.append(_na("performance", "image_optimization", "Image Optimization", 2,
            "Image optimization data comes from Google PageSpeed Insights, which didn't return this signal for this page (or the API isn't connected).",
            expected="Compressed, modern formats"))
    elif image_score >= 0.9:
        checks.append(_r("performance", "image_optimization", "Image Optimization", 2, STATUS_PASS,
            "Images appear to be well-optimized (modern formats, appropriately sized).", raw=f"{int(image_score*100)}% optimized", expected="Compressed, modern formats",
            why="Well-optimized images load faster, which improves both user experience and page speed scores."))
    elif image_score >= 0.5:
        checks.append(_r("performance", "image_optimization", "Image Optimization", 2, STATUS_WARNING,
            "Some images could be better optimized.", raw=f"{int(image_score*100)}% optimized", expected="Compressed, modern formats",
            why="Partially optimized images mean there's meaningful room to shrink page weight and speed up load times.",
            rec_title="Optimize Images", rec_action="Convert images to modern formats (WebP/AVIF), compress them, and serve appropriately sized versions for each device.",
            rec_impact="Page load speed", rec_effort="Medium", rec_difficulty="Low"))
    else:
        checks.append(_r("performance", "image_optimization", "Image Optimization", 2, STATUS_FAIL,
            "Images are not well-optimized.", raw=f"{int(image_score*100)}% optimized", expected="Compressed, modern formats",
            why="Unoptimized images are one of the most common causes of slow page loads and poor performance scores.",
            rec_title="Optimize Images", rec_action="Convert images to modern formats (WebP/AVIF), compress all images, and use responsive image sizing.",
            rec_impact="Page load speed", rec_effort="Medium", rec_difficulty="Low"))

    asset_ratio = profile.get("asset_minified_ratio")
    if asset_ratio is None:
        checks.append(_na("performance", "minification", "CSS/JS Minification", 1,
            "No external CSS/JS files were found to evaluate for minification.", expected="Minified"))
    elif asset_ratio >= 0.7:
        checks.append(_r("performance", "minification", "CSS/JS Minification", 1, STATUS_PASS,
            "Most linked CSS/JS files appear to be minified based on their filenames.", raw=f"{int(asset_ratio*100)}% minified filenames", expected="Minified",
            why="Minified files are smaller and load faster."))
    else:
        checks.append(_r("performance", "minification", "CSS/JS Minification", 1, STATUS_WARNING,
            "Most linked CSS/JS files don't appear to be minified based on their filenames.", raw=f"{int(asset_ratio*100)}% minified filenames", expected="Minified",
            why="Unminified files are larger than necessary and slow down page loads slightly.",
            rec_title="Minify CSS & JavaScript", rec_action="Enable minification for CSS and JS assets, often available as a plugin or build step.",
            rec_impact="Page load speed", rec_effort="Low", rec_difficulty="Low"))

    # =================== USABILITY / MOBILE ===================
    if profile.get("has_viewport"):
        checks.append(_r("usability_mobile", "responsive_design", "Responsive Design", 3, STATUS_PASS,
            "Your site declares a responsive viewport, a baseline signal of a mobile-adapted layout.", raw="Viewport tag present", expected="Fully responsive",
            why="A responsive design ensures visitors have a good experience regardless of device, which is essential since most searches happen on mobile."))
    else:
        checks.append(_r("usability_mobile", "responsive_design", "Responsive Design", 3, STATUS_FAIL,
            "No responsive viewport meta tag was found, which usually means the layout won't adapt to mobile screens.", raw="Viewport tag missing", expected="Fully responsive",
            why="Layout issues on mobile can frustrate the majority of your visitors and increase bounce rates.",
            rec_title="Fix Mobile Responsiveness Issues", rec_action="Add a responsive viewport meta tag and review layout on mobile screen sizes.",
            rec_impact="Mobile user experience", rec_effort="Medium", rec_difficulty="Medium"))

    checks.append(_na("usability_mobile", "tap_targets", "Tap Target Sizing", 1,
        "Measuring actual tap target sizes requires rendering the page in a browser, which this phase doesn't yet do.",
        expected="Adequately sized/spaced tap targets"))
    checks.append(_na("usability_mobile", "font_readability", "Font Readability", 1,
        "Measuring computed font sizes requires rendering the page in a browser, which this phase doesn't yet do.",
        expected=">=16px base font"))

    if profile.get("has_nav") and profile.get("has_mobile_nav_toggle"):
        checks.append(_r("usability_mobile", "mobile_navigation", "Mobile Navigation", 2, STATUS_PASS,
            "Navigation includes what looks like a mobile menu toggle.", raw="Nav + toggle element found", expected="Clear, accessible mobile nav",
            why="Easy navigation helps mobile visitors quickly find what they need, supporting conversions."))
    elif profile.get("has_nav"):
        checks.append(_r("usability_mobile", "mobile_navigation", "Mobile Navigation", 2, STATUS_WARNING,
            "A navigation menu was found, but no clear mobile menu toggle was detected.", raw="Nav found, no toggle detected", expected="Clear, accessible mobile nav",
            why="Without an obvious mobile menu pattern, navigation may be harder to use on small screens.",
            rec_title="Verify Mobile Navigation Usability", rec_action="Confirm your navigation collapses into an accessible mobile menu on small screens.",
            rec_impact="Mobile usability & conversions", rec_effort="Medium", rec_difficulty="Low"))
    else:
        checks.append(_r("usability_mobile", "mobile_navigation", "Mobile Navigation", 2, STATUS_NOT_DETECTED,
            "No navigation element was detected to evaluate.", raw="No <nav> found", expected="Clear, accessible mobile nav",
            why="This isn't necessarily a problem — it simply means we couldn't identify a standard navigation element on the page reviewed."))

    total_fields = profile.get("form_fields_total")
    labeled_fields = profile.get("form_fields_labeled")
    if not profile.get("form_count"):
        checks.append(_r("usability_mobile", "form_accessibility", "Form Accessibility", 1, STATUS_NOT_DETECTED,
            "No forms were detected to evaluate.", raw="No forms found", expected="Labeled, accessible forms",
            why="This isn't necessarily a problem — it simply means we couldn't evaluate a contact/lead form on the page reviewed."))
    elif total_fields == 0:
        checks.append(_r("usability_mobile", "form_accessibility", "Form Accessibility", 1, STATUS_NOT_DETECTED,
            "A form was found, but it has no visible input fields to evaluate.", raw="0 evaluable fields", expected="Labeled, accessible forms",
            why="This isn't necessarily a problem — the form may rely on hidden or dynamically-injected fields we can't see from static HTML."))
    elif labeled_fields == total_fields:
        checks.append(_r("usability_mobile", "form_accessibility", "Form Accessibility", 1, STATUS_PASS,
            "Forms are accessible and easy to complete.", raw=f"{labeled_fields}/{total_fields} fields labeled", expected="Labeled, accessible forms",
            why="Accessible forms make it easier for all visitors — including those using assistive technology — to contact you."))
    else:
        checks.append(_r("usability_mobile", "form_accessibility", "Form Accessibility", 1, STATUS_WARNING,
            "Some form fields are missing labels or placeholders.", raw=f"{labeled_fields}/{total_fields} fields labeled", expected="Labeled, accessible forms",
            why="Unlabeled form fields are harder to use for visitors relying on screen readers.",
            rec_title="Label All Form Fields", rec_action="Add visible labels or aria-labels to every form field.",
            rec_impact="Accessibility & conversions", rec_effort="Low", rec_difficulty="Low"))

    # =================== AI SEARCH & GEO READINESS ===================
    blocked_ai = profile.get("ai_crawlers_blocked", []) or []
    if not blocked_ai:
        checks.append(_r("ai_geo", "ai_crawler_access", "AI Crawler Accessibility", 2, STATUS_PASS,
            "Your robots.txt does not block major AI crawlers.", raw="No AI crawlers blocked", expected="AI crawlers not blocked",
            why="If AI crawlers can't access your site, your business can't be referenced by AI-powered search and chat tools."))
    else:
        checks.append(_r("ai_geo", "ai_crawler_access", "AI Crawler Accessibility", 2, STATUS_WARNING,
            "Some AI crawlers appear to be blocked in robots.txt.", raw=", ".join(blocked_ai) + " disallowed", expected="AI crawlers not blocked",
            why="Blocking AI crawlers may prevent your business from appearing in AI-generated answers and recommendations.",
            rec_title="Allow AI Crawlers in Robots.txt", rec_action="Review robots.txt and remove blanket disallows for major AI crawlers, if blocking wasn't intentional.",
            rec_impact="AI search visibility", rec_effort="Low", rec_difficulty="Low"))

    if profile.get("llms_txt_found"):
        checks.append(_r("ai_geo", "llms_txt", "llms.txt Presence", 1, STATUS_PASS,
            "An llms.txt file was found.", raw="/llms.txt found", expected="llms.txt present (optional signal)",
            why="llms.txt is an emerging, optional convention for guiding AI tools to key content. It's one signal among many — not a ranking guarantee."))
    else:
        checks.append(_r("ai_geo", "llms_txt", "llms.txt Presence", 1, STATUS_NOT_DETECTED,
            "No llms.txt file was found.", raw="Not found", expected="llms.txt present (optional signal)",
            why="llms.txt is an emerging, optional standard. Its absence is not a major issue today, but adding one is a low-effort way to help AI tools find your key pages.",
            rec_title="Consider Adding an llms.txt File", rec_action="Add a simple llms.txt file pointing AI tools to your most important pages.",
            rec_impact="Emerging AI-readiness signal", rec_effort="Low", rec_difficulty="Low"))

    has_schema_entity = any(t in ("Organization", "LocalBusiness") for t in sd_types) or any("LocalBusiness" in t for t in sd_types)
    has_nap = bool(profile.get("phone_found")) and bool(profile.get("address_found"))
    if has_schema_entity and has_nap:
        checks.append(_r("ai_geo", "entity_clarity", "Business Entity Clarity", 3, STATUS_PASS,
            "Your business name, services, and location are clearly stated in text and markup.", raw="Structured data + NAP found", expected="Clear entity identification",
            why="AI systems rely on clear, consistent facts to correctly identify and recommend your business."))
    elif has_schema_entity or has_nap:
        checks.append(_r("ai_geo", "entity_clarity", "Business Entity Clarity", 3, STATUS_WARNING,
            "Your business identity is only partially clear from the page content.", raw="Partial entity signals found", expected="Clear entity identification",
            why="If AI tools can't clearly determine what you do and where you serve, they're less likely to recommend you for relevant queries.",
            rec_title="Clarify Business Identity & Services", rec_action="Add a clear 'About' section stating your business name, services, and service area in plain language.",
            rec_impact="AI & search entity recognition", rec_effort="Medium", rec_difficulty="Low"))
    else:
        checks.append(_r("ai_geo", "entity_clarity", "Business Entity Clarity", 3, STATUS_FAIL,
            "Business identity signals are unclear or missing.", raw="No entity signals found", expected="Clear entity identification",
            why="Without clear identity signals, both traditional search engines and AI tools struggle to understand and recommend your business.",
            rec_title="Clarify Business Identity & Services", rec_action="Add clear business name, service, and location information throughout the site and in structured data.",
            rec_impact="AI & search entity recognition", rec_effort="Medium", rec_difficulty="Medium"))

    if profile.get("has_faq_content"):
        checks.append(_r("ai_geo", "faq_content", "FAQ / Q&A Content", 2, STATUS_PASS,
            "Your site includes FAQ-style content.", raw="FAQ section/schema detected", expected="FAQ / Q&A content present",
            why="Question-and-answer content maps naturally to how people ask AI assistants questions, increasing the chance of being referenced."))
    else:
        checks.append(_r("ai_geo", "faq_content", "FAQ / Q&A Content", 2, STATUS_NOT_DETECTED,
            "No FAQ or Q&A style content was detected.", raw="Not found", expected="FAQ / Q&A content present",
            why="AI tools frequently pull from question-and-answer formatted content. Without it, you may be missed for common customer questions.",
            rec_title="Add FAQ / Q&A Content", rec_action="Add a FAQ section answering the most common questions prospects ask before hiring you.",
            rec_impact="AI search visibility & user education", rec_effort="Medium", rec_difficulty="Low"))

    trust_matches = profile.get("trust_signal_matches", []) or []
    if len(trust_matches) >= 2:
        checks.append(_r("ai_geo", "trust_signals", "Trust & Expertise Signals", 2, STATUS_PASS,
            "Your site includes credibility signals (credentials, years in business, reviews, etc).", raw=f"{len(trust_matches)} trust-signal phrases found", expected="Visible trust/expertise signals",
            why="Trust signals help both visitors and AI tools judge the credibility of your business."))
    else:
        checks.append(_r("ai_geo", "trust_signals", "Trust & Expertise Signals", 2, STATUS_WARNING,
            "Limited trust or expertise signals were found.", raw=f"{len(trust_matches)} trust-signal phrase(s) found", expected="Visible trust/expertise signals",
            why="Without visible credibility markers, prospects and AI tools have less reason to trust and recommend your business over competitors.",
            rec_title="Add Trust & Expertise Signals", rec_action="Highlight certifications, years in business, awards, and customer reviews prominently.",
            rec_impact="Conversion & AI credibility signals", rec_effort="Medium", rec_difficulty="Low"))

    if profile.get("has_date_signal"):
        checks.append(_r("ai_geo", "content_freshness", "Content Freshness", 1, STATUS_PASS,
            "Content appears to include recency/update signals.", raw="Date signal found", expected="Regularly updated content",
            why="Fresh content signals to search engines and AI tools that your business information is current and reliable."))
    else:
        checks.append(_r("ai_geo", "content_freshness", "Content Freshness", 1, STATUS_NOT_DETECTED,
            "Unable to determine how recently content was updated.", raw="No date signals found", expected="Regularly updated content",
            why="This isn't necessarily a problem, but adding visible update dates (e.g. on blog posts) can help build freshness signals over time.",
            rec_title="Add Content Freshness Signals", rec_action="Add publish/update dates to blog and service content, and refresh key pages periodically.",
            rec_impact="Content freshness signal", rec_effort="Low", rec_difficulty="Low"))

    service_mentions = profile.get("service_area_mentions", 0)
    if service_mentions >= 1 and wc >= 150:
        checks.append(_r("ai_geo", "service_definitions", "Clear Service & Geographic Definitions", 2, STATUS_PASS,
            "Services and service area are explicitly described.", raw=f"{service_mentions} service-area mention(s)", expected="Explicit service & area definitions",
            why="Specific, explicit descriptions make it far easier for AI and search tools to match you to relevant local queries."))
    else:
        checks.append(_r("ai_geo", "service_definitions", "Clear Service & Geographic Definitions", 2, STATUS_WARNING,
            "Services or service area are not clearly/explicitly described on this page.", raw=f"{service_mentions} service-area mention(s)", expected="Explicit service & area definitions",
            why="Vague descriptions make it harder for AI tools and search engines to confidently match you to specific customer needs.",
            rec_title="Clarify Services & Service Area", rec_action="Explicitly list each service offered and every city/area served, rather than generic descriptions.",
            rec_impact="Local & AI search matching", rec_effort="Medium", rec_difficulty="Low"))

    # =================== LOCAL SEO ===================
    phone_found = profile.get("phone_found")
    address_found = profile.get("address_found")
    if phone_found and address_found:
        checks.append(_r("local_seo", "nap_consistency", "NAP (Name, Address, Phone) Presence", 3, STATUS_PASS,
            "Business address and phone number are clearly listed on the page.", raw="Phone + address found", expected="Consistent NAP across site",
            why="Consistent NAP information helps both search engines and customers trust and find your business."))
    elif phone_found or address_found:
        checks.append(_r("local_seo", "nap_consistency", "NAP (Name, Address, Phone) Presence", 3, STATUS_WARNING,
            "NAP information is only partially present on this page.", raw=("Phone found, address not found" if phone_found else "Address found, phone not found"), expected="Consistent NAP across site",
            why="Inconsistent or incomplete contact information can confuse both customers and local search algorithms.",
            rec_title="Standardize NAP Information", rec_action="Ensure your business name, address, and phone number are identical and visible on every page.",
            rec_impact="Local search rankings & trust", rec_effort="Low", rec_difficulty="Low"))
    else:
        checks.append(_r("local_seo", "nap_consistency", "NAP (Name, Address, Phone) Presence", 3, STATUS_FAIL,
            "Business address or phone number could not be found on the page.", raw="Not found", expected="Consistent NAP across site",
            why="Missing contact information hurts both local rankings and customer trust.",
            rec_title="Add Complete NAP Information", rec_action="Add your business name, address, and phone number prominently, ideally in the header/footer.",
            rec_impact="Local search rankings & trust", rec_effort="Low", rec_difficulty="Low"))

    if any("LocalBusiness" in t for t in sd_types):
        checks.append(_r("local_seo", "localbusiness_schema", "LocalBusiness Schema Markup", 2, STATUS_PASS,
            "LocalBusiness structured data was found.", raw="Schema detected", expected="LocalBusiness schema present",
            why="This structured data helps search engines display rich local business information directly in search results."))
    else:
        checks.append(_r("local_seo", "localbusiness_schema", "LocalBusiness Schema Markup", 2, STATUS_NOT_DETECTED,
            "No LocalBusiness structured data was found.", raw="Not found", expected="LocalBusiness schema present",
            why="Without this markup, search engines rely purely on unstructured page text to understand your business details.",
            rec_title="Add LocalBusiness Schema Markup", rec_action="Implement LocalBusiness schema with your name, address, phone, hours, and service area.",
            rec_impact="Local search visibility", rec_effort="Medium", rec_difficulty="Medium"))

    places_result = profile.get("places_result")
    if places_result is None:
        checks.append(_na("local_seo", "gbp_presence", "Google Business Profile Signal", 2,
            "A Google Business Profile is often the single biggest driver of local visibility, but no business name was available to look one up (or the Places API isn't connected).",
            expected="Connected GBP data source"))
    elif not places_result.get("found"):
        checks.append(_r("local_seo", "gbp_presence", "Google Business Profile Signal", 2, STATUS_FAIL,
            "No matching Google Business Profile / Places listing could be found for this business name.", raw="Not found", expected="Listing found on Google",
            why="Without a discoverable Google Business Profile, this business is likely missing out on local map pack visibility and 'near me' searches.",
            rec_title="Create or Claim a Google Business Profile", rec_action="Set up a Google Business Profile with accurate name, address, phone, hours, and photos.",
            rec_impact="Local search & maps visibility", rec_effort="Low", rec_difficulty="Low"))
    else:
        rating = places_result.get("rating")
        ratings_total = places_result.get("user_ratings_total")
        status = places_result.get("business_status")
        raw_bits = []
        if rating is not None:
            raw_bits.append(f"{rating}★")
        if ratings_total is not None:
            raw_bits.append(f"{ratings_total} reviews")
        raw = ", ".join(raw_bits) if raw_bits else "Listing found"
        if status and status != "OPERATIONAL":
            checks.append(_r("local_seo", "gbp_presence", "Google Business Profile Signal", 2, STATUS_WARNING,
                f"A listing was found, but its status is '{status}', not confirmed operational.", raw=raw, expected="Active, operational listing",
                why="A non-operational listing status can prevent the business from appearing properly in local search results.",
                rec_title="Verify Google Business Profile Status", rec_action="Log into Google Business Profile and confirm the listing is verified and marked open/operational.",
                rec_impact="Local search & maps visibility", rec_effort="Low", rec_difficulty="Low"))
        elif ratings_total is not None and ratings_total < 5:
            checks.append(_r("local_seo", "gbp_presence", "Google Business Profile Signal", 2, STATUS_WARNING,
                "A Google Business Profile listing was found, but it has very few reviews.", raw=raw, expected="Active listing with reviews",
                why="A thin review count makes it harder to stand out in local search results compared to competitors with more reviews.",
                rec_title="Grow Google Business Profile Reviews", rec_action="Ask satisfied customers to leave a Google review; aim for a steady, ongoing flow of new reviews.",
                rec_impact="Local search rankings & trust", rec_effort="Low", rec_difficulty="Low"))
        else:
            checks.append(_r("local_seo", "gbp_presence", "Google Business Profile Signal", 2, STATUS_PASS,
                "An active Google Business Profile / Places listing was found for this business.", raw=raw, expected="Active listing with reviews",
                why="An established Google Business Profile with reviews is one of the strongest signals for local search and maps visibility."))

    if service_mentions >= 2:
        checks.append(_r("local_seo", "service_area_pages", "Service Area / Location Pages", 2, STATUS_PASS,
            "This page clearly and repeatedly describes the service area.", raw=f"{service_mentions} service-area mentions", expected="Location-specific content",
            why="Location-specific pages help you rank for 'near me' and city-specific searches."))
    elif service_mentions == 1:
        checks.append(_r("local_seo", "service_area_pages", "Service Area / Location Pages", 2, STATUS_WARNING,
            "Service area is mentioned but not described in much depth on this page.", raw="1 service-area mention", expected="Location-specific content",
            why="Without dedicated content per service area, you're less likely to rank for location-specific searches beyond your main city.",
            rec_title="Create Service Area Landing Pages", rec_action="Build dedicated pages for each major city/area you serve, with locally relevant content.",
            rec_impact="Local search rankings", rec_effort="Medium", rec_difficulty="Low"))
    else:
        checks.append(_r("local_seo", "service_area_pages", "Service Area / Location Pages", 2, STATUS_NOT_DETECTED,
            "No clear service area information was found on this page.", raw="Not found", expected="Location-specific content",
            why="Without a clearly defined service area, both customers and search engines may be uncertain where you operate.",
            rec_title="Define & Publish Your Service Area", rec_action="Clearly state which cities/regions you serve, ideally with dedicated content per area.",
            rec_impact="Local search rankings", rec_effort="Medium", rec_difficulty="Low"))

    # =================== SOCIAL, TRACKING & SECURITY ===================
    social_profiles = profile.get("social_profiles_found", []) or []
    if social_profiles:
        checks.append(_r("social_tracking_security", "social_profiles", "Linked Social Profiles", 1, STATUS_PASS,
            "Links to social media profiles were found.", raw=", ".join(social_profiles), expected="Linked social profiles",
            why="Linked social profiles give visitors more ways to engage with and vet your business."))
    else:
        checks.append(_r("social_tracking_security", "social_profiles", "Linked Social Profiles", 1, STATUS_NOT_DETECTED,
            "No links to social media profiles were found.", raw="Not found", expected="Linked social profiles",
            why="This isn't necessarily a problem, but linking active social profiles can build additional trust and engagement.",
            rec_title="Link Your Social Profiles", rec_action="Add links to your active social media profiles, typically in the header or footer.",
            rec_impact="Brand engagement & trust", rec_effort="Low", rec_difficulty="Low"))

    if profile.get("has_open_graph"):
        checks.append(_r("social_tracking_security", "open_graph", "Open Graph / Social Sharing Tags", 1, STATUS_PASS,
            "Open Graph tags were found for social sharing.", raw="og: tags present", expected="Open Graph tags present",
            why="Open Graph tags control how your page looks when shared on social media, improving click-through from shares."))
    else:
        checks.append(_r("social_tracking_security", "open_graph", "Open Graph / Social Sharing Tags", 1, STATUS_NOT_DETECTED,
            "No Open Graph tags were found.", raw="Not found", expected="Open Graph tags present",
            why="Without Open Graph tags, social platforms will guess at a preview image/title, which is often less compelling.",
            rec_title="Add Open Graph Tags", rec_action="Add og:title, og:description, and og:image meta tags to key pages.",
            rec_impact="Social sharing appearance", rec_effort="Low", rec_difficulty="Low"))

    analytics = profile.get("analytics_signals", []) or []
    if analytics:
        checks.append(_r("social_tracking_security", "analytics", "Analytics / Tracking Installed", 2, STATUS_PASS,
            "Analytics/tracking tools were detected on the page.", raw=", ".join(analytics), expected="Analytics installed",
            why="Analytics data is essential for measuring traffic, conversions, and the impact of marketing efforts."))
    else:
        checks.append(_r("social_tracking_security", "analytics", "Analytics / Tracking Installed", 2, STATUS_NOT_DETECTED,
            "No common analytics/tracking tools were detected.", raw="Not found", expected="Analytics installed",
            why="Without analytics, it's difficult to measure what's working and make informed marketing decisions.",
            rec_title="Install Website Analytics", rec_action="Install Google Analytics (or a similar tool) to start tracking visitor behavior and conversions.",
            rec_impact="Marketing visibility & decision-making", rec_effort="Low", rec_difficulty="Low"))

    spf = profile.get("spf_found")
    dmarc = profile.get("dmarc_found")
    if spf and dmarc:
        checks.append(_r("social_tracking_security", "email_security", "Email/Domain Security (SPF & DMARC)", 1, STATUS_PASS,
            "SPF and DMARC records are configured.", raw="SPF + DMARC found", expected="SPF & DMARC present",
            why="These records help prevent your domain from being spoofed in phishing emails, protecting your brand reputation."))
    elif spf:
        checks.append(_r("social_tracking_security", "email_security", "Email/Domain Security (SPF & DMARC)", 1, STATUS_WARNING,
            "SPF is configured, but DMARC is missing.", raw="SPF found, DMARC missing", expected="SPF & DMARC present",
            why="Without DMARC, your domain is more vulnerable to email spoofing, which can damage customer trust.",
            rec_title="Add a DMARC Record", rec_action="Publish a DMARC DNS record to strengthen email security and brand protection.",
            rec_impact="Email deliverability & brand protection", rec_effort="Low", rec_difficulty="Medium"))
    else:
        checks.append(_r("social_tracking_security", "email_security", "Email/Domain Security (SPF & DMARC)", 1, STATUS_FAIL,
            "No SPF or DMARC records were found.", raw="Not found", expected="SPF & DMARC present",
            why="Without SPF/DMARC, it's easier for bad actors to send spoofed emails that appear to come from your domain.",
            rec_title="Configure SPF & DMARC Records", rec_action="Add SPF and DMARC DNS records to protect your domain from email spoofing.",
            rec_impact="Email deliverability & brand protection", rec_effort="Low", rec_difficulty="Medium"))

    if profile.get("has_hsts"):
        checks.append(_r("social_tracking_security", "hsts", "HSTS Header", 1, STATUS_PASS,
            "HSTS is enabled, enforcing secure connections.", raw="Strict-Transport-Security header found", expected="HSTS enabled",
            why="HSTS tells browsers to always use HTTPS for your domain, protecting visitors from downgrade attacks."))
    else:
        checks.append(_r("social_tracking_security", "hsts", "HSTS Header", 1, STATUS_NOT_DETECTED,
            "HSTS header was not detected.", raw="Not found", expected="HSTS enabled",
            why="Without HSTS, there's a small window where a visitor's first connection could be intercepted before redirecting to HTTPS.",
            rec_title="Enable HSTS", rec_action="Add the Strict-Transport-Security header via your server or CDN configuration.",
            rec_impact="Security hardening", rec_effort="Low", rec_difficulty="Medium"))

    return checks
