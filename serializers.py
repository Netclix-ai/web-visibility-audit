"""Serialization helpers: convert SQLAlchemy model rows into plain dicts
for JSON responses. Kept separate from routes.py to keep that file focused
on request handling.
"""
from models import Business, Website, Audit, CategoryScore, AuditCheck, Recommendation, Report


def iso(dt):
    return dt.isoformat() if dt else None


def business_brief(b: Business) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "location": b.location,
        "category": b.category,
        "service_area": b.service_area,
        "primary_keywords": b.primary_keywords,
        "contact_name": b.contact_name,
        "contact_email": b.contact_email,
        "phone": b.phone,
        "notes": b.notes,
        "created_at": iso(b.created_at),
        "website_count": len(b.websites),
        "lead_source": b.lead_source,
        "ghl_contact_id": b.ghl_contact_id,
        "wants_fix_help": b.wants_fix_help,
        "full_audit_requested_at": iso(b.full_audit_requested_at),
    }


def website_brief(w: Website) -> dict:
    return {
        "id": w.id,
        "business_id": w.business_id,
        "url": w.url,
        "created_at": iso(w.created_at),
        "audit_count": len(w.audits),
    }


def audit_summary(a: Audit) -> dict:
    return {
        "id": a.id,
        "website_id": a.website_id,
        "website_url": a.website.url if a.website else None,
        "status": a.status,
        "overall_score": a.overall_score,
        "overall_grade": a.overall_grade,
        "is_demo_data": a.is_demo_data,
        "depth": a.depth,
        "error_message": a.error_message,
        "created_at": iso(a.created_at),
        "completed_at": iso(a.completed_at),
    }


def category_score_detail(cs: CategoryScore) -> dict:
    return {
        "category_key": cs.category.key if cs.category else None,
        "category_name": cs.category.display_name if cs.category else None,
        "score": cs.score,
        "grade": cs.grade,
        "status": cs.status,
        "issues_count": cs.issues_count,
        "warnings_count": cs.warnings_count,
        "passed_count": cs.passed_count,
    }


def check_detail(c: AuditCheck) -> dict:
    return {
        "id": c.id,
        "category_key": c.category.key if c.category else None,
        "category_name": c.category.display_name if c.category else None,
        "check_name": c.check_name,
        "result": c.result,
        "raw_value": c.raw_value,
        "expected_value": c.expected_value,
        "status": c.status,
        "business_explanation": c.business_explanation,
        "data_source": c.data_source,
    }


def recommendation_detail(r: Recommendation) -> dict:
    return {
        "id": r.id,
        "category_key": r.category.key if r.category else None,
        "category_name": r.category.display_name if r.category else None,
        "title": r.title,
        "priority": r.priority,
        "severity": r.severity,
        "what_found": r.what_found,
        "why_matters": r.why_matters,
        "recommended_action": r.recommended_action,
        "estimated_impact": r.estimated_impact,
        "estimated_effort": r.estimated_effort,
        "technical_difficulty": r.technical_difficulty,
        "rank": r.rank,
    }


def audit_detail(a: Audit) -> dict:
    d = audit_summary(a)
    d["business"] = business_brief(a.website.business) if a.website and a.website.business else None
    d["categories"] = [category_score_detail(cs) for cs in sorted(a.category_scores, key=lambda x: x.category.sort_order if x.category else 0)]
    d["checks"] = [check_detail(c) for c in a.checks]
    d["recommendations"] = [recommendation_detail(r) for r in sorted(a.recommendations, key=lambda x: x.rank)]
    return d


def report_meta(r: Report) -> dict:
    return {
        "id": r.id,
        "audit_id": r.audit_id,
        "mode": r.mode,
        "share_token": r.share_token,
        "created_at": iso(r.created_at),
    }
