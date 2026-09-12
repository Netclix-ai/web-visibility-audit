# Website Visibility Audit — Phase 1 Plan

## Context

Netclix Marketing needs a scalable "Online Visibility Platform" that starts with **Website Audits** but is architected to grow into AI visibility, local visibility, rank tracking, backlinks, social, etc. It must support two report modes (full internal audit + curiosity-driven prospect snapshot), audit history over time, and a future automation/GoHighLevel pipeline.

This plan covers **Phase 1 only**, per the user's own phased rollout:
> "Build the complete UI, database structure, audit engine architecture, scoring system, recommendation engine, and report layouts... Use realistic sample audit data for the UI where actual crawling/API data is not yet implemented, but clearly label sample/demo data as such."

Real crawling/checks (Phase 2), performance API (Phase 3), backlink API (Phase 4), sharing/snapshot polish (Phase 5), bulk upload/automation (Phase 6), GoHighLevel (Phase 7), and additional visibility modules (Phase 8) are explicitly **out of scope** for this build but the data model/engine interfaces must not block them.

## Stack

- Template: **Data App HTML Python** (FastAPI backend + HTML/CSS/JS frontend, multi-page).
- Database: **Neon Postgres** (already provisioned — connector `DB5C90F310`). Use SQLAlchemy models.
- No authentication in v1 (internal agency tool). Revisit if the app is ever exposed to prospects directly for self-serve snapshot creation.

## Scope & Non-Goals

**In scope (Phase 1):**
- Full data model (Users optional/skip, Business, Website, Audit, Category, AuditCheck, Score, Recommendation, Report/ReportSnapshot, Integration placeholder, ScoringConfig, BrandingConfig).
- Audit engine skeleton with clear seams: `Crawler → Checks → Scoring → Recommendations → Report`, but Phase 1 populates checks with **clearly labeled sample/demo data** (deterministic per URL, not random garbage) rather than live crawling.
- Configurable scoring weights + grade thresholds (stored in DB or config table, editable via admin UI).
- Admin dashboard: businesses, websites, create audit, audit "processing" screen (simulated steps), completed audit view, recommendations, full report, prospect snapshot, audit history + score-over-time chart, branding settings, scoring-weights settings.
- Report layouts for both Full Audit (18 sections) and Prospect Snapshot (score, category mini-dashboard, 3-5 findings, CTA).
- Shareable report URL (simple slug/token-based, no auth) — "Share via secure URL" from spec, done via unguessable token for now (real access control deferred).

**Non-goals (explicitly deferred):**
- Real website crawling, PageSpeed/Core Web Vitals APIs, backlink APIs, GBP APIs, social APIs.
- CSV/Excel/GHL/webhook import UIs (just make Audit creation function callable independent of the form, so it's easy to wire later).
- Login/auth, multi-tenant users.
- Actual email/SMS sending for CTA.

## Data Model (SQLAlchemy / Postgres)

- `Business`: id, name, location, category, service_area, primary_keywords, contact_name, contact_email, notes, created_at
- `Website`: id, business_id FK, url, created_at
- `Audit`: id, website_id FK, status (pending/running/completed/failed), overall_score, overall_grade, created_at, completed_at, is_demo_data (bool)
- `Category`: id, key (on_page_seo, technical_seo, performance, usability_mobile, ai_geo, authority, local_seo, social_tracking_security), display_name, default_weight
- `CategoryScore`: id, audit_id FK, category_id FK, score, grade, status, issues_count, warnings_count, passed_count
- `AuditCheck`: id, audit_id FK, category_id FK, check_name, result, raw_value, expected_value, status (PASS/WARNING/FAIL/NOT_DETECTED/NOT_APPLICABLE), score_contribution, priority, data_source, timestamp
- `Recommendation`: id, audit_id FK, check_id FK (nullable), title, category_id FK, priority (CRITICAL/HIGH/MEDIUM/LOW), severity, what_found, why_matters, recommended_action, estimated_impact, estimated_effort, technical_difficulty
- `Report`: id, audit_id FK, mode (full/prospect), share_token, created_at
- `ScoringConfig`: id, category_id FK, weight (editable), active
- `GradeThreshold`: id, min_score, grade (editable)
- `BrandingConfig`: id, company_name, phone, email, website, contact_form_url, scheduling_url

## Audit Engine Architecture (Phase 1 seams)

```
run_audit(website_id) 
  -> collect_data(url)        # Phase1: returns sample/demo dataset; Phase2: real crawler
  -> run_checks(data)         # produces list of AuditCheck rows per category
  -> score_categories(checks, ScoringConfig)  # weighted 0-100 + grade
  -> build_recommendations(checks)            # from FAIL/WARNING checks
  -> persist(audit, checks, scores, recommendations)
```
Each function is a plain Python module (`audit_engine/collector.py`, `checks.py`, `scoring.py`, `recommendations.py`) so Phase 2+ can swap `collector.py` without touching scoring/reporting.

Sample data generator: deterministic pseudo-random based on hash(url) so re-running the same URL gives consistent demo results; every check row sets `data_source="sample_data"` and UI shows a persistent "Demo Data" badge on any audit where `is_demo_data=True`.

## Implementation Plan

1. Clone template, set up FastAPI app skeleton, connect Neon via SQLAlchemy, create models + Alembic-free `create_all` migration (or simple init script).
2. Seed `Category`, default `ScoringConfig` weights (20/15/15/10/15/10/10/5), `GradeThreshold` rows, default `BrandingConfig` (Netclix Marketing details from spec).
3. Build `audit_engine/` package: sample data collector, checks per category (9 categories, using the check list from spec), scoring (weighted, configurable), recommendation builder (maps FAIL/WARNING checks → recommendation with why/impact/effort).
4. Build API endpoints: CRUD for businesses/websites, create audit (kicks off engine synchronously for now), get audit detail, get category scores, get recommendations, get report (full/prospect) by id or share token, update branding, update scoring weights.
5. Build frontend pages (HTML/CSS/JS, multi-page or SPA-lite):
   - Dashboard/home (list businesses + recent audits)
   - Business detail (websites, audit history, score-over-time chart)
   - Create Audit form (URL required, other fields optional)
   - Audit processing screen (checklist animation, then redirect to results)
   - Audit results: overall score, category score cards, detailed findings per category (PASS/WARN/FAIL/NOT DETECTED/NOT APPLICABLE), recommendations list (sorted by priority)
   - Full Report view (18-section layout, printable/clean)
   - Prospect Snapshot view (score hero, mini dashboard, 3-5 curiosity findings, CTA w/ branding)
   - Settings: branding config, scoring weights config
6. Score-over-time chart (simple line chart, e.g. Chart.js) on business detail page, plotting overall_score per audit; extend later to per-category lines.
7. Add "Demo Data" badges throughout wherever `is_demo_data` is true; never label sample output as real results.

## Verification

- Create a business + website via UI, run "Create Audit" for a real-looking URL, confirm processing screen shows steps then lands on results with 8 category scores, overall weighted score/grade, and recommendations sorted by priority.
- Confirm re-running audit for the same URL creates a second `Audit` row (history preserved) and the score-over-time chart shows both points.
- Open Full Report and Prospect Snapshot views for the same audit; confirm prospect view hides detailed findings and shows only 3-5 summary bullets + CTA with branding config values.
- Change scoring weights in Settings, re-run/recompute an audit, confirm overall score changes accordingly.
- Confirm every audit/report screen displays a visible "Sample/Demo Data" indicator since Phase 1 has no live crawler.
- `curl` key API endpoints (create audit, get report by share token) to confirm JSON responses are well-formed.
