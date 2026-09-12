"""Recommendation engine.

Converts weak/failed checks into prioritized, business-friendly
recommendations. Priority is derived from a combination of the check's
result status and its importance weight within its category — a FAIL on a
high-weight check (e.g. missing title tag) ranks above a WARNING on a
low-weight check (e.g. suboptimal alt text), which keeps the "top issues"
list focused on what actually matters.
"""

PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

CATEGORY_DISPLAY = {
    "on_page_seo": "On-Page SEO",
    "technical_seo": "Technical SEO",
    "performance": "Performance",
    "usability_mobile": "Usability / Mobile",
    "ai_geo": "AI Search & GEO Readiness",
    "local_seo": "Local SEO",
    "social_tracking_security": "Social, Tracking & Security",
}


def _priority_for(status: str, weight: float) -> str:
    if status == "FAIL":
        return "CRITICAL" if weight >= 3 else "HIGH"
    if status == "WARNING":
        if weight >= 3:
            return "HIGH"
        if weight == 2:
            return "MEDIUM"
        return "LOW"
    if status == "NOT_DETECTED":
        return "MEDIUM" if weight >= 2 else "LOW"
    return "LOW"


def build_recommendations(checks: list[dict]) -> list[dict]:
    """checks: list of dicts from audit_engine.checks.run_checks.

    Returns a list of recommendation dicts, sorted by priority (most
    important first). Checks without a `rec_title` (i.e. PASS, or an
    outcome that isn't actionable) are skipped.
    """
    recs = []
    for c in checks:
        if not c.get("rec_title"):
            continue
        priority = _priority_for(c["status"], c.get("weight", 1))
        recs.append({
            "check_key": c["key"],
            "category": c["category"],
            "category_display": CATEGORY_DISPLAY.get(c["category"], c["category"]),
            "title": c["rec_title"],
            "priority": priority,
            "severity": c["status"],
            "what_found": c["result"],
            "why_matters": c.get("business_explanation"),
            "recommended_action": c.get("rec_action"),
            "estimated_impact": c.get("rec_impact"),
            "estimated_effort": c.get("rec_effort"),
            "technical_difficulty": c.get("rec_difficulty"),
        })

    recs.sort(key=lambda r: (PRIORITY_ORDER.get(r["priority"], 9), -{"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}.get(r["priority"], 0)))
    for i, r in enumerate(recs):
        r["rank"] = i
    return recs
