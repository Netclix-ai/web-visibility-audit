"""Builds the two report payloads (Full Audit vs Prospect Snapshot) from an
audit's already-computed data. Pure data shaping — no scoring logic here.
"""
import hashlib

from models import Audit, BrandingConfig
from serializers import audit_detail, business_brief

FINDING_TEMPLATES = {
    "on_page_seo": {
        "positive": "Solid on-page SEO fundamentals in place",
        "negative": "Content & on-page optimization opportunities",
    },
    "technical_seo": {
        "positive": "Strong technical SEO foundation",
        "negative": "Technical SEO issues may be limiting visibility",
    },
    "performance": {
        "positive": "Fast, well-optimized page performance",
        "negative": "Page speed needs improvement",
    },
    "usability_mobile": {
        "positive": "Mobile-friendly, easy-to-navigate experience",
        "negative": "Mobile usability improvements needed",
    },
    "ai_geo": {
        "positive": "Well-positioned for AI-powered search",
        "negative": "AI search visibility could be improved",
    },
    "local_seo": {
        "positive": "Strong local search signals",
        "negative": "Local search visibility opportunities",
    },
    "social_tracking_security": {
        "positive": "Strong security & tracking foundation",
        "negative": "Security or tracking gaps detected",
    },
}


def branding_dict(b: BrandingConfig) -> dict:
    # Served from Postgres (bytea), not the filesystem, so it survives
    # restarts; cache-busted with a hash of the actual bytes so the browser
    # refetches after a re-upload but keeps caching the same logo otherwise.
    logo_url = ""
    if b.logo_data:
        logo_hash = hashlib.md5(b.logo_data).hexdigest()[:10]
        logo_url = f"/api/settings/branding/logo?v={logo_hash}"
    return {
        "company_name": b.company_name,
        "logo_url": logo_url,
        "phone": b.phone,
        "email": b.email,
        "from_email": b.from_email,
        "website": b.website,
        "contact_form_url": b.contact_form_url,
        "scheduling_url": b.scheduling_url,
        "cta_headline": b.cta_headline,
        "cta_button_text": b.cta_button_text,
        "widget_heading": b.widget_heading,
        "widget_button_text": b.widget_button_text,
    }


def _executive_summary(detail: dict) -> str:
    score = detail["overall_score"]
    grade = detail["overall_grade"]
    top_recs = detail["recommendations"][:3]
    rec_titles = ", ".join(r["title"] for r in top_recs) if top_recs else "no major issues"
    return (
        f"This website scored {score}/100 ({grade}) across on-page SEO, technical SEO, "
        f"performance, mobile usability, AI/GEO readiness, local SEO, and "
        f"security/tracking. The highest-priority opportunities identified were: {rec_titles}. "
        f"Addressing these can meaningfully improve search visibility, user experience, and "
        f"the ability for both search engines and AI tools to understand and recommend this business."
    )


def build_full_report(audit: Audit, branding: BrandingConfig) -> dict:
    detail = audit_detail(audit)
    detail["executive_summary"] = _executive_summary(detail)
    detail["branding"] = branding_dict(branding)
    detail["mode"] = "full"
    detail["methodology_note"] = (
        "This audit was generated using Netclix Marketing's Website Visibility Audit platform "
        "from a live crawl of the site (HTML, headers, robots.txt/sitemap.xml, and DNS records). "
        "Checks marked 'Data unavailable' require a third-party API not yet connected — "
        "Core Web Vitals/PageSpeed, backlink data, and Google Business Profile — and are "
        "excluded from scoring rather than estimated, so they never affect the final grade."
    )
    return detail


def build_prospect_snapshot(audit: Audit, branding: BrandingConfig) -> dict:
    detail = audit_detail(audit)
    categories = detail["categories"]
    scored_categories = [c for c in categories if c["score"] is not None]

    by_score_desc = sorted(scored_categories, key=lambda c: c["score"], reverse=True)
    by_score_asc = sorted(scored_categories, key=lambda c: c["score"])

    findings = []
    if by_score_desc and by_score_desc[0]["score"] >= 80:
        key = by_score_desc[0]["category_key"]
        findings.append({"type": "positive", "text": FINDING_TEMPLATES.get(key, {}).get("positive", f"Strong {by_score_desc[0]['category_name']}")})

    for cat in by_score_asc:
        if len(findings) >= 5:
            break
        if cat["score"] < 80:
            key = cat["category_key"]
            findings.append({"type": "warning", "text": FINDING_TEMPLATES.get(key, {}).get("negative", f"{cat['category_name']} needs attention")})

    return {
        "mode": "prospect",
        "business": detail["business"],
        "website_url": detail["website_url"],
        "overall_score": detail["overall_score"],
        "overall_grade": detail["overall_grade"],
        "is_demo_data": detail["is_demo_data"],
        "categories": [
            {"category_key": c["category_key"], "category_name": c["category_name"], "score": c["score"]}
            for c in categories
        ],
        "findings": findings[:5],
        "branding": branding_dict(branding),
    }
