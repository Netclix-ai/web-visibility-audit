"""One-time DB init + seed for reference data (categories, weights, grades, branding).

Safe to re-run: uses get-or-create semantics for reference tables, and
idempotent ALTER TABLE ... ADD COLUMN IF NOT EXISTS statements to evolve
existing tables without a full migration framework (fine at this stage of
the project; revisit with Alembic once the schema stabilizes).
"""
from sqlalchemy import text

from db import Base, engine, session_scope
import models as m

CATEGORIES = [
    # Authority ("Links / Authority") was removed (Sept 2026) -- it isn't a
    # true on-site feature (no backlink data source is connected, so every
    # check in it always reported NOT_APPLICABLE) and its 0.10 weight has
    # been redistributed proportionally across the remaining 7 categories
    # below so weights still sum to 1.0. See _migrate_remove_authority()
    # for the one-time DB migration that deactivates the old category's
    # ScoringConfig row and reweights existing installations to match.
    ("on_page_seo", "On-Page SEO", 0.2222, 1),
    ("technical_seo", "Technical SEO", 0.1667, 2),
    ("performance", "Performance", 0.1667, 3),
    ("usability_mobile", "Usability / Mobile", 0.1111, 4),
    ("ai_geo", "AI Search & GEO Readiness", 0.1667, 5),
    ("local_seo", "Local SEO", 0.1111, 6),
    ("social_tracking_security", "Social, Tracking & Security", 0.0556, 7),
]

GRADE_THRESHOLDS = [
    (97, "A+", 1), (93, "A", 2), (90, "A-", 3),
    (87, "B+", 4), (83, "B", 5), (80, "B-", 6),
    (77, "C+", 7), (73, "C", 8), (70, "C-", 9),
    (67, "D+", 10), (63, "D", 11), (60, "D-", 12),
    (0, "F", 13),
]

# (table, column, DDL type) — additive, backward-compatible schema changes.
COLUMN_MIGRATIONS = [
    ("businesses", "first_name", "VARCHAR"),
    ("businesses", "last_name", "VARCHAR"),
    ("businesses", "phone", "VARCHAR"),
    ("businesses", "lead_source", "VARCHAR DEFAULT 'manual'"),
    ("branding_config", "logo_url", "VARCHAR DEFAULT ''"),
    ("branding_config", "logo_data", "BYTEA"),
    ("branding_config", "logo_mime", "VARCHAR DEFAULT ''"),
    ("branding_config", "from_email", "VARCHAR DEFAULT ''"),
    ("branding_config", "widget_heading", "VARCHAR DEFAULT 'Audit Your Website Now!'"),
    ("branding_config", "widget_button_text", "VARCHAR DEFAULT 'Check'"),
    ("audits", "error_message", "TEXT"),
    ("businesses", "wants_fix_help", "VARCHAR"),
    ("businesses", "full_audit_requested_at", "TIMESTAMPTZ"),
    ("businesses", "ghl_contact_id", "VARCHAR"),
    ("audits", "depth", "VARCHAR DEFAULT 'full'"),
    ("bulk_upload_jobs", "job_type", "VARCHAR DEFAULT 'website_audit'"),
]

# Raw, idempotent SQL statements for changes ADD COLUMN can't express
# (e.g. relaxing a NOT NULL constraint). Safe to re-run.
EXTRA_MIGRATIONS = [
    "ALTER TABLE category_scores ALTER COLUMN score DROP NOT NULL",
    "ALTER TABLE category_scores ALTER COLUMN grade DROP NOT NULL",
]


def _run_column_migrations():
    with engine.begin() as conn:
        for table, column, ddl_type in COLUMN_MIGRATIONS:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl_type}'))
        for stmt in EXTRA_MIGRATIONS:
            conn.execute(text(stmt))


def _migrate_remove_authority(db):
    """One-time migration for installations that already seeded the old
    8-category schema: deactivates the "authority" category's ScoringConfig
    (kept in the DB, not deleted, so historical CategoryScore/AuditCheck/
    Recommendation rows for past audits still resolve their category_id FK)
    and updates sort_order + weight on the remaining categories to match
    the new CATEGORIES list above. Idempotent: guarded on the authority
    config still being active, so it's a no-op after the first run."""
    authority_cat = db.query(m.Category).filter_by(key="authority").first()
    if not authority_cat:
        return  # fresh install -- authority was never seeded, nothing to do
    cfg = db.query(m.ScoringConfig).filter_by(category_id=authority_cat.id).first()
    if not cfg or not cfg.active:
        return  # already migrated
    cfg.active = False

    sort_and_weight_by_key = {key: (sort_order, weight) for key, _, weight, sort_order in CATEGORIES}
    for key, (sort_order, weight) in sort_and_weight_by_key.items():
        cat = db.query(m.Category).filter_by(key=key).first()
        if not cat:
            continue
        cat.sort_order = sort_order
        other_cfg = db.query(m.ScoringConfig).filter_by(category_id=cat.id).first()
        if other_cfg:
            other_cfg.weight = weight


def init_db():
    Base.metadata.create_all(bind=engine)
    _run_column_migrations()
    with session_scope() as db:
        # Categories + scoring weights
        for key, display_name, weight, sort_order in CATEGORIES:
            cat = db.query(m.Category).filter_by(key=key).first()
            if not cat:
                cat = m.Category(key=key, display_name=display_name, sort_order=sort_order)
                db.add(cat)
                db.flush()
            cfg = db.query(m.ScoringConfig).filter_by(category_id=cat.id).first()
            if not cfg:
                db.add(m.ScoringConfig(category_id=cat.id, weight=weight, active=True))

        _migrate_remove_authority(db)

        # Grade thresholds
        if db.query(m.GradeThreshold).count() == 0:
            for min_score, grade, sort_order in GRADE_THRESHOLDS:
                db.add(m.GradeThreshold(min_score=min_score, grade=grade, sort_order=sort_order))

        # Branding (single row)
        if db.query(m.BrandingConfig).count() == 0:
            db.add(m.BrandingConfig())

        # Rank Checker default keyword template (single row)
        if db.query(m.RankCheckSettings).count() == 0:
            db.add(m.RankCheckSettings(default_keywords="tree trimming,stump removal,tree removal"))

    print("DB initialized and seeded.")


if __name__ == "__main__":
    init_db()
