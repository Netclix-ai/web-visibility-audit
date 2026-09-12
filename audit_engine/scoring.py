"""Weighted scoring engine.

Turns a flat list of check results into per-category scores (0-100 +
letter grade) and an overall weighted score, using the configurable
category weights (ScoringConfig) and grade thresholds (GradeThreshold)
stored in the database. Nothing here is hardcoded so weights/thresholds
can be changed via the admin UI without touching this code.

Status -> numeric contribution mapping is intentionally not "PASS=100,
anything else=0" — WARNING and NOT_DETECTED are partial-credit outcomes so
a handful of minor gaps don't tank a category the way a genuine FAIL would.
"""

STATUS_SCORE = {
    "PASS": 100,
    "WARNING": 60,
    "FAIL": 15,
    "NOT_DETECTED": 70,   # absence isn't automatically a failure (per spec)
    "NOT_APPLICABLE": None,  # excluded entirely from scoring
}


def grade_for_score(score: float, thresholds: list[dict]) -> str:
    """thresholds: list of {"min_score": int, "grade": str}, any order."""
    ordered = sorted(thresholds, key=lambda t: t["min_score"], reverse=True)
    for t in ordered:
        if score >= t["min_score"]:
            return t["grade"]
    return ordered[-1]["grade"] if ordered else "N/A"


def score_categories(checks: list[dict], category_weights: dict, thresholds: list[dict]) -> dict:
    """
    checks: list of check dicts from audit_engine.checks.run_checks (each has
        'category', 'weight', 'status').
    category_weights: {category_key: weight_fraction} e.g. {"on_page_seo": 0.20, ...}
    thresholds: grade threshold rows as dicts.

    Returns {
        "categories": {category_key: {score, grade, issues, warnings, passed, checks: [...]}},
        "overall_score": float,
        "overall_grade": str,
    }
    """
    by_category: dict[str, list[dict]] = {}
    for c in checks:
        by_category.setdefault(c["category"], []).append(c)

    category_results = {}
    for cat_key, cat_checks in by_category.items():
        weighted_sum = 0.0
        weight_total = 0.0
        issues = warnings = passed = 0
        for c in cat_checks:
            status = c["status"]
            if status == "PASS":
                passed += 1
            elif status == "WARNING":
                warnings += 1
            elif status == "FAIL":
                issues += 1
            contribution = STATUS_SCORE.get(status)
            if contribution is None:
                continue
            w = c.get("weight", 1)
            weighted_sum += contribution * w
            weight_total += w
        score = round(weighted_sum / weight_total, 1) if weight_total else None
        grade = grade_for_score(score, thresholds) if score is not None else None
        category_results[cat_key] = {
            "score": score,
            "grade": grade,
            "issues_count": issues,
            "warnings_count": warnings,
            "passed_count": passed,
            "checks": cat_checks,
        }

    overall_weighted = 0.0
    overall_weight_total = 0.0
    for cat_key, result in category_results.items():
        w = category_weights.get(cat_key)
        if not w or result["score"] is None:
            continue
        overall_weighted += result["score"] * w
        overall_weight_total += w
    overall_score = round(overall_weighted / overall_weight_total, 1) if overall_weight_total else 0.0
    overall_grade = grade_for_score(overall_score, thresholds)

    return {
        "categories": category_results,
        "overall_score": overall_score,
        "overall_grade": overall_grade,
    }


def category_status_label(score: float) -> str:
    """Short human status label shown next to a category score."""
    if score is None:
        return "Data Unavailable"
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 60:
        return "Needs Attention"
    return "Critical Issues"
