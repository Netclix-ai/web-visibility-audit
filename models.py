"""SQLAlchemy data model for the Web Visibility Audit platform.

Designed around: Business -> Website -> Audit -> CategoryScore / AuditCheck
                                              -> Recommendation
                                              -> Report (full / prospect)

This model intentionally keeps raw per-check data (AuditCheck) separate from
the derived CategoryScore/overall score so the scoring algorithm can be
changed later without losing underlying audit data. ScoringConfig and
GradeThreshold make the weighting/grading configurable without code changes.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint,
    LargeBinary,
)
from sqlalchemy.orm import relationship

from db import Base


def _uuid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class Business(Base):
    __tablename__ = "businesses"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    location = Column(String)
    category = Column(String)  # primary business category
    service_area = Column(String)
    primary_keywords = Column(String)  # comma separated, optional
    contact_name = Column(String)
    contact_email = Column(String)
    notes = Column(Text)
    # Lead-capture fields (populated when the record originates from the
    # public embeddable audit widget rather than manual/admin entry).
    first_name = Column(String)
    last_name = Column(String)
    phone = Column(String)
    lead_source = Column(String, default="manual")  # "manual" | "widget" | "ghl" | "csv_bulk" | "local_visibility_csv" | "local_visibility_ghl" | "local_visibility_manual" | "rank_checker_csv" | "rank_checker_ghl" | "rank_checker_manual"
    ghl_contact_id = Column(String)  # GoHighLevel contact id, when lead_source == "ghl" (idempotency key)
    # Set when a prospect responds to the "Request Your Full Audit" CTA on
    # their prospect snapshot (widget results or public share link).
    # None = never asked/answered. "yes"/"no" = their answer to
    # "Would you also like help correcting these issues?"
    wants_fix_help = Column(String)
    full_audit_requested_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=now)

    websites = relationship("Website", back_populates="business", cascade="all, delete-orphan")
    local_visibility_scans = relationship("LocalVisibilityScan", back_populates="business", cascade="all, delete-orphan")
    rank_check_scans = relationship("RankCheckScan", back_populates="business", cascade="all, delete-orphan")


class BulkUploadJob(Base):
    """Tracks one CSV upload -> lite-audit-scoring -> download round trip
    (routes.py's /api/bulk-scoring/* endpoints, static/js/views/bulk-
    scoring.js). A list of hundreds/thousands of rows, even at the ~1-5s
    per lite audit, can take minutes -- the upload request returns
    immediately with a job id the frontend polls for progress (same
    background-thread pattern as the widget/GHL audit flows), and the
    scored CSV bytes are stored directly in Postgres (no local filesystem,
    which doesn't survive a restart) until downloaded.

    job_type discriminates which bulk-scoring pipeline produced this row:
    "website_audit" (the original CSV bulk scoring, depth="lite" website
    audits) or "local_visibility" (Advice Local baseline-report scoring,
    see advicelocal_client.py). Same table/shape, different processing
    function and different required input columns -- kept as one table
    since the tracked lifecycle (upload -> background progress -> download
    CSV) is identical, just filtered by job_type in each feature's routes."""
    __tablename__ = "bulk_upload_jobs"

    id = Column(String, primary_key=True, default=_uuid)
    job_type = Column(String, default="website_audit")  # "website_audit" | "local_visibility"
    filename = Column(String)
    status = Column(String, default="running")  # running | completed | failed
    total_rows = Column(Integer, default=0)
    processed_rows = Column(Integer, default=0)
    error_message = Column(Text)
    result_csv = Column(LargeBinary)  # populated once status == "completed"
    result_filename = Column(String)
    created_at = Column(DateTime(timezone=True), default=now)
    completed_at = Column(DateTime(timezone=True))


class LocalVisibilityScan(Base):
    """One Advice Local baseline-report scan for a business (see
    advicelocal_client.py). Mirrors the role Audit plays for the website-
    audit side, but for Advice Local's own async pipeline instead of an
    in-house crawl: creating a client via POST /legacyclients kicks off
    an automatically-generated "baseline report" (included in the
    reseller fee, no per-run order/cost) that becomes available a short
    time later via GET /legacyscores. advice_local_client_id is the
    anchor needed to poll for that score; raw_scores keeps the full
    response (per-source breakdown: GMB/Yelp/Bing/directories, NAP
    consistency) as JSON for future drill-down, even though today only
    overall_score/overall_grade are surfaced in the bulk CSV output."""
    __tablename__ = "local_visibility_scans"

    id = Column(String, primary_key=True, default=_uuid)
    business_id = Column(String, ForeignKey("businesses.id"), nullable=False)
    street = Column(String)
    city = Column(String)
    state = Column(String)
    zip_code = Column(String)
    advice_local_client_id = Column(String)  # returned by POST /legacyclients
    status = Column(String, default="running")  # running | completed | failed
    overall_score = Column(Float)
    overall_grade = Column(String)
    raw_scores = Column(Text)  # full /legacyscores response, JSON-encoded
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=now)
    completed_at = Column(DateTime(timezone=True))

    business = relationship("Business", back_populates="local_visibility_scans")


class RankCheckSettings(Base):
    """Singleton row (mirrors BrandingConfig's single-row pattern) holding
    the default keyword template used when a bulk CSV/Excel upload or GHL
    webhook request doesn't specify its own keyword list. Stored as a
    comma-separated string (simplest shape for a short editable list in
    the Settings UI) -- e.g. "tree trimming,stump removal,tree removal"."""
    __tablename__ = "rank_check_settings"

    id = Column(String, primary_key=True, default=_uuid)
    default_keywords = Column(Text, default="")  # comma-separated
    updated_at = Column(DateTime(timezone=True), default=now, onupdate=now)


class RankCheckScan(Base):
    """One on-demand keyword-rank-check run for a business (manual form,
    one row of a bulk CSV/Excel upload, or a GHL webhook request). Mirrors
    the role LocalVisibilityScan plays for Advice Local, but for
    Serper.dev's Google Search/Maps APIs -- see serper_client.py. Each
    scan checks N keywords (built from the scan's keyword list + the
    business's own location, since Map Pack results are hyperlocal), with
    the per-keyword results stored in RankCheckKeywordResult rows so the
    UI can drill into organic position + Map Pack position per keyword."""
    __tablename__ = "rank_check_scans"

    id = Column(String, primary_key=True, default=_uuid)
    business_id = Column(String, ForeignKey("businesses.id"), nullable=False)
    website = Column(String)  # domain used to match "your" organic result
    location_query = Column(String)  # e.g. "Austin, TX" or a zip -- appended to each keyword
    check_type = Column(String, default="both")  # "organic" | "maps" | "both" -- which Serper
    # endpoint(s) this scan actually calls. Lets a bulk/GHL campaign request only the checks
    # it needs (e.g. a maps-only outreach campaign never burns an organic call, and vice versa).
    status = Column(String, default="running")  # running | completed | failed
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=now)
    completed_at = Column(DateTime(timezone=True))

    business = relationship("Business", back_populates="rank_check_scans")
    keyword_results = relationship(
        "RankCheckKeywordResult", back_populates="scan", cascade="all, delete-orphan",
        order_by="RankCheckKeywordResult.created_at",
    )


class RankCheckKeywordResult(Base):
    """One keyword's result within a RankCheckScan -- organic Google
    position (matched by domain against the scan's `website`) and Google
    Map Pack position (matched by business-name substring against the
    Maps API's `places` results), plus a raw JSON snapshot of the top
    results from each for drill-down in the "View Report" style modal."""
    __tablename__ = "rank_check_keyword_results"

    id = Column(String, primary_key=True, default=_uuid)
    scan_id = Column(String, ForeignKey("rank_check_scans.id"), nullable=False)
    keyword = Column(String, nullable=False)
    query = Column(String)  # the actual query text sent to Serper (keyword + location)
    organic_position = Column(Integer)  # None = not found in the results checked
    organic_url = Column(String)
    map_pack_position = Column(Integer)
    map_pack_found = Column(Boolean, default=False)
    raw_organic = Column(Text)  # JSON: top organic results snapshot
    raw_maps = Column(Text)  # JSON: top Map Pack results snapshot
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=now)

    scan = relationship("RankCheckScan", back_populates="keyword_results")


class Website(Base):
    __tablename__ = "websites"

    id = Column(String, primary_key=True, default=_uuid)
    business_id = Column(String, ForeignKey("businesses.id"), nullable=False)
    url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now)

    business = relationship("Business", back_populates="websites")
    audits = relationship("Audit", back_populates="website", cascade="all, delete-orphan")


class Category(Base):
    """Static reference table of audit categories (seeded once)."""
    __tablename__ = "categories"

    id = Column(String, primary_key=True, default=_uuid)
    key = Column(String, unique=True, nullable=False)  # e.g. on_page_seo
    display_name = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)


class ScoringConfig(Base):
    """Configurable category weight used for the overall weighted score."""
    __tablename__ = "scoring_config"

    id = Column(String, primary_key=True, default=_uuid)
    category_id = Column(String, ForeignKey("categories.id"), nullable=False, unique=True)
    weight = Column(Float, nullable=False)  # 0-1, should sum to 1 across active categories
    active = Column(Boolean, default=True)

    category = relationship("Category")


class GradeThreshold(Base):
    """Configurable score->letter grade mapping."""
    __tablename__ = "grade_thresholds"

    id = Column(String, primary_key=True, default=_uuid)
    min_score = Column(Integer, nullable=False)
    grade = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)


class BrandingConfig(Base):
    """Single-row table holding agency branding used in reports/CTAs.

    Structured as a standalone "brand profile" row (name, logo, contact
    details, sender email) so this table can later grow into a
    per-client/white-label table (one row per agency reselling the
    platform) without changing how reports/widget/email code reads it —
    for now there is exactly one active row.
    """
    __tablename__ = "branding_config"

    id = Column(String, primary_key=True, default=_uuid)
    company_name = Column(String, default="Netclix Marketing")
    logo_url = Column(String, default="")  # legacy filesystem path; kept for backward-compat reads only, no longer written
    logo_data = Column(LargeBinary)  # actual logo bytes, persisted in Postgres (filesystem uploads don't survive restarts)
    logo_mime = Column(String, default="")
    phone = Column(String, default="208-841-5531")
    email = Column(String, default="dev@netclixmarketing.com")
    from_email = Column(String, default="")  # sender address for Resend; falls back to a shared default if blank
    website = Column(String, default="https://netclixmarketing.com")
    contact_form_url = Column(String, default="")
    scheduling_url = Column(String, default="")
    cta_headline = Column(String, default="Want to see what's holding your website back?")
    cta_button_text = Column(String, default="Request Your Full Audit")
    widget_heading = Column(String, default="Audit Your Website Now!")
    widget_button_text = Column(String, default="Check")


class Audit(Base):
    __tablename__ = "audits"

    id = Column(String, primary_key=True, default=_uuid)
    website_id = Column(String, ForeignKey("websites.id"), nullable=False)
    status = Column(String, default="pending")  # pending/running/completed/failed
    overall_score = Column(Float)
    overall_grade = Column(String)
    is_demo_data = Column(Boolean, default=True)  # Phase 1: always True (no live crawler yet)
    data_source_note = Column(String, default="sample_data")
    depth = Column(String, default="full")  # "full" | "lite" -- see live_collector.collect()
    error_message = Column(Text)  # populated when status == "failed" (live crawl couldn't reach the site)
    created_at = Column(DateTime(timezone=True), default=now)
    completed_at = Column(DateTime(timezone=True))

    website = relationship("Website", back_populates="audits")
    category_scores = relationship("CategoryScore", back_populates="audit", cascade="all, delete-orphan")
    checks = relationship("AuditCheck", back_populates="audit", cascade="all, delete-orphan")
    recommendations = relationship("Recommendation", back_populates="audit", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="audit", cascade="all, delete-orphan")


class CategoryScore(Base):
    __tablename__ = "category_scores"

    id = Column(String, primary_key=True, default=_uuid)
    audit_id = Column(String, ForeignKey("audits.id"), nullable=False)
    category_id = Column(String, ForeignKey("categories.id"), nullable=False)
    score = Column(Float)  # nullable: None when an entire category is data-unavailable (e.g. Authority pre-backlink-API)
    grade = Column(String)  # nullable for the same reason
    status = Column(String)  # e.g. "Needs Attention", "Good", "Excellent", "Data Unavailable"
    issues_count = Column(Integer, default=0)
    warnings_count = Column(Integer, default=0)
    passed_count = Column(Integer, default=0)

    audit = relationship("Audit", back_populates="category_scores")
    category = relationship("Category")


class AuditCheck(Base):
    __tablename__ = "audit_checks"

    id = Column(String, primary_key=True, default=_uuid)
    audit_id = Column(String, ForeignKey("audits.id"), nullable=False)
    category_id = Column(String, ForeignKey("categories.id"), nullable=False)
    check_name = Column(String, nullable=False)
    result = Column(Text)  # human readable summary
    raw_value = Column(String)
    expected_value = Column(String)
    status = Column(String, nullable=False)  # PASS/WARNING/FAIL/NOT_DETECTED/NOT_APPLICABLE
    score_contribution = Column(Float, default=0)  # 0-100 weight within its category
    weight = Column(Float, default=1.0)  # relative weight of this check within category
    priority = Column(String)  # CRITICAL/HIGH/MEDIUM/LOW (for related recommendation, if any)
    business_explanation = Column(Text)  # plain-language "why it matters"
    data_source = Column(String, default="sample_data")
    timestamp = Column(DateTime(timezone=True), default=now)

    audit = relationship("Audit", back_populates="checks")
    category = relationship("Category")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(String, primary_key=True, default=_uuid)
    audit_id = Column(String, ForeignKey("audits.id"), nullable=False)
    check_id = Column(String, ForeignKey("audit_checks.id"), nullable=True)
    category_id = Column(String, ForeignKey("categories.id"), nullable=False)
    title = Column(String, nullable=False)
    priority = Column(String, nullable=False)  # CRITICAL/HIGH/MEDIUM/LOW
    severity = Column(String)
    what_found = Column(Text)
    why_matters = Column(Text)
    recommended_action = Column(Text)
    estimated_impact = Column(String)
    estimated_effort = Column(String)  # Low/Medium/High
    technical_difficulty = Column(String)  # Low/Medium/High
    rank = Column(Integer, default=0)  # computed priority rank for sorting

    audit = relationship("Audit", back_populates="recommendations")
    category = relationship("Category")


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=_uuid)
    audit_id = Column(String, ForeignKey("audits.id"), nullable=False)
    mode = Column(String, nullable=False)  # "full" | "prospect"
    share_token = Column(String, unique=True, default=lambda: uuid.uuid4().hex)
    created_at = Column(DateTime(timezone=True), default=now)

    audit = relationship("Audit", back_populates="reports")

    __table_args__ = (UniqueConstraint("audit_id", "mode", name="uq_audit_mode"),)
