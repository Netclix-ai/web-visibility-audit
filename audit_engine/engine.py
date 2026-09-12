"""Audit engine orchestrator.

run_audit() is the single entry point that ties together the pipeline:

    live_collector.collect(url)
        -> live_checks.run_checks(site_profile)
        -> scoring.score_categories(checks, weights, thresholds)
        -> recommendations.build_recommendations(checks)
        -> persist Audit / CategoryScore / AuditCheck / Recommendation rows

It is intentionally interface-agnostic: it takes a `website` row and a db
session, and doesn't care whether it was invoked from a manual "Create
Audit" form, a CSV import, a webhook, or a scheduled job. That's what makes
future automation (bulk upload, GoHighLevel, API) a matter of calling this
same function from a new entry point rather than rebuilding the engine.

Phase 1's sample-data collector/checks (collector.py / checks.py) are kept
in the codebase for reference but are no longer used by run_audit() as of
Phase 2 — every audit now reflects a real crawl (or an honest "failed"
status if the site couldn't be reached).
"""
from datetime import datetime, timezone

import models as m
from db import session_scope
from . import scoring, recommendations as recs_mod
from . import live_collector, live_checks


def _grade_thresholds(db) -> list[dict]:
    rows = db.query(m.GradeThreshold).all()
    return [{"min_score": r.min_score, "grade": r.grade} for r in rows]


def _category_weights(db) -> tuple[dict, dict]:
    """Returns (weights_by_key, category_id_by_key)."""
    cats = db.query(m.Category).all()
    cat_id_by_key = {c.key: c.id for c in cats}
    configs = db.query(m.ScoringConfig).filter_by(active=True).all()
    weights = {}
    for cfg in configs:
        cat = next((c for c in cats if c.id == cfg.category_id), None)
        if cat:
            weights[cat.key] = cfg.weight
    return weights, cat_id_by_key


def create_audit_stub(db, website: m.Website, depth: str = "full") -> m.Audit:
    """Creates the Audit row in status="running" and returns immediately --
    this is the fast, synchronous part of starting an audit. The actual
    crawl/scoring work (which can take up to ~2 minutes worst case: JS
    rendering + two sequential PageSpeed Insights calls) is intentionally
    NOT done here -- see execute_audit() below, meant to be run in a
    background thread so the HTTP request that kicks off an audit can
    return in well under a second instead of holding the connection open
    for the full run. That matters because this app sits behind a
    reverse proxy (Cloudflare) with its own hard ceiling on how long it
    will wait for an origin response -- a single long-lived synchronous
    request risks hitting that ceiling and failing with a proxy-level
    timeout, regardless of any client-side timeout budget. Callers should
    have the frontend poll GET /audits/{id} for completion instead.

    `depth`: "full" (default) or "lite" -- see live_collector.collect() for
    what lite mode skips (Playwright render + PageSpeed Insights). Stored
    on the Audit row so execute_audit() (which only gets an audit_id, not
    a depth) knows which mode to run."""
    audit = m.Audit(website_id=website.id, status="running", is_demo_data=False,
                     data_source_note="live_crawl", depth=depth)
    db.add(audit)
    db.flush()
    return audit


def execute_audit(audit_id: str) -> None:
    """The actual crawl -> checks -> scoring -> persistence pipeline for an
    audit that already exists in status="running" (see create_audit_stub).
    Opens its OWN database session (session_scope) because this is meant
    to run in a background thread, decoupled from any HTTP request's
    request-scoped session -- that session gets closed as soon as the
    route handler returns, which happens immediately after create_audit_stub
    now that this is split out. Any exception here is caught and persisted
    as audit.status = "failed" with the error message, rather than left as
    a permanently "running" row with no explanation."""
    with session_scope() as db:
        audit = db.get(m.Audit, audit_id)
        if not audit:
            return
        website = db.get(m.Website, audit.website_id)
        if not website:
            audit.status = "failed"
            audit.error_message = "Website record was deleted before the audit could run."
            audit.completed_at = datetime.now(timezone.utc)
            return

        try:
            site_profile = live_collector.collect(
                website.url,
                business_name=website.business.name if website.business else None,
                location=website.business.location if website.business else None,
                depth=audit.depth or "full",
            )
        except Exception as e:
            audit.status = "failed"
            audit.error_message = f"Unexpected error while auditing this site: {e}"
            audit.completed_at = datetime.now(timezone.utc)
            return

        if site_profile.get("fetch_error"):
            audit.status = "failed"
            audit.error_message = site_profile["fetch_error"]
            audit.completed_at = datetime.now(timezone.utc)
            return

        try:
            raw_checks = live_checks.run_checks(site_profile)

            weights, cat_id_by_key = _category_weights(db)
            thresholds = _grade_thresholds(db)
            scored = scoring.score_categories(raw_checks, weights, thresholds)
            recs = recs_mod.build_recommendations(raw_checks)

            for c in raw_checks:
                db.add(m.AuditCheck(
                    audit_id=audit.id,
                    category_id=cat_id_by_key.get(c["category"]),
                    check_name=c["name"],
                    result=c["result"],
                    raw_value=c.get("raw_value"),
                    expected_value=c.get("expected_value"),
                    status=c["status"],
                    weight=c.get("weight", 1),
                    business_explanation=c.get("business_explanation"),
                    data_source=c.get("data_source", "sample_data"),
                ))

            for cat_key, result in scored["categories"].items():
                db.add(m.CategoryScore(
                    audit_id=audit.id,
                    category_id=cat_id_by_key.get(cat_key),
                    score=result["score"],
                    grade=result["grade"],
                    status=scoring.category_status_label(result["score"]),
                    issues_count=result["issues_count"],
                    warnings_count=result["warnings_count"],
                    passed_count=result["passed_count"],
                ))

            for r in recs:
                db.add(m.Recommendation(
                    audit_id=audit.id,
                    category_id=cat_id_by_key.get(r["category"]),
                    title=r["title"],
                    priority=r["priority"],
                    severity=r["severity"],
                    what_found=r["what_found"],
                    why_matters=r["why_matters"],
                    recommended_action=r["recommended_action"],
                    estimated_impact=r["estimated_impact"],
                    estimated_effort=r["estimated_effort"],
                    technical_difficulty=r["technical_difficulty"],
                    rank=r["rank"],
                ))

            audit.overall_score = scored["overall_score"]
            audit.overall_grade = scored["overall_grade"]
            audit.status = "completed"
            audit.completed_at = datetime.now(timezone.utc)
        except Exception as e:
            audit.status = "failed"
            audit.error_message = f"Unexpected error while scoring this audit: {e}"
            audit.completed_at = datetime.now(timezone.utc)


def run_audit(db, website: m.Website, depth: str = "full") -> m.Audit:
    """Synchronous convenience wrapper kept for any callers (scripts, tests)
    that want the old fully-blocking behavior in one call. Route handlers
    should prefer create_audit_stub() + a backgrounded execute_audit() so
    the HTTP request returns immediately -- see routes.py."""
    audit = create_audit_stub(db, website, depth=depth)
    db.commit()
    execute_audit(audit.id)
    db.refresh(audit)
    return audit
