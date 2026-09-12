import hashlib
import csv
import io
import json
import os
import re
import threading
import concurrent.futures
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import FastAPI, APIRouter, Request, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

import models as m
from db import get_db, session_scope
from seed import init_db
from audit_engine.engine import create_audit_stub, execute_audit
from audit_engine.scoring import grade_for_score
from serializers import (
    business_brief, website_brief, audit_summary, audit_detail, report_meta,
)
from report_builder import build_full_report, build_prospect_snapshot, branding_dict
from emailer import send_email
from email_templates import lead_report_email, lead_notification_email, full_audit_email
import ghl_client
import advicelocal_client
import serper_client


def _run_audit_in_background(audit_id: str) -> None:
    """Fire-and-forget: runs the actual crawl/scoring pipeline on a
    daemon thread so the HTTP request that triggered it can return
    immediately instead of holding the connection open for up to ~2
    minutes. See audit_engine.engine.execute_audit for why this needed to
    be split out (Cloudflare's proxy-level response timeout was killing
    long-running synchronous requests before our own client-side timeout
    ever fired)."""
    t = threading.Thread(target=execute_audit, args=(audit_id,), daemon=True)
    t.start()


def _send_widget_emails(audit_id: str, lead: dict, business_name: str, website_url: str,
                         prospect_share_token: str, full_share_token: str, base_url: str) -> None:
    """Runs after the audit finishes (see _run_audit_in_background) --
    sends the lead's snapshot email and the agency notification email once
    real results actually exist, instead of racing the audit itself."""
    with session_scope() as db:
        audit = db.get(m.Audit, audit_id)
        if not audit or audit.status != "completed":
            return
        branding = db.query(m.BrandingConfig).first()
        b_dict = branding_dict(branding) if branding else {}
        from_email = b_dict.get("from_email") or None
        snapshot_url = f"{base_url}/#/share/{prospect_share_token}"
        full_report_url = f"{base_url}/#/share/{full_share_token}"

        try:
            subject, html = lead_report_email(
                b_dict, lead.get("first_name"), business_name, website_url,
                audit.overall_score, audit.overall_grade, snapshot_url,
            )
            send_email(lead.get("email"), subject, html, from_email=from_email)
        except Exception:
            pass

        agency_email = b_dict.get("email")
        if agency_email:
            try:
                subject, html = lead_notification_email(
                    b_dict, lead, business_name, website_url,
                    audit.overall_score, audit.overall_grade, full_report_url,
                )
                send_email(agency_email, subject, html, from_email=from_email, reply_to=lead.get("email"))
            except Exception:
                pass


def get_file_hash(filepath: str) -> str:
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()[:8]


# ---------------- Bulk CSV scoring ----------------
# Upload a lead-list CSV -> run a depth="lite" audit against each row's
# website -> hand back the SAME csv with two columns appended (Visibility
# Score, Website Audit Grade), ready to re-import into GHL or any other CRM.
# Runs in a background thread since even a fast lite audit (~1-5s each)
# adds up across a list of hundreds/thousands of rows -- the upload
# request itself returns immediately with a job id the frontend polls.

WEBSITE_HEADER_CANDIDATES = {"website", "websiteurl", "url", "weburl", "domain", "site", "siteurl", "homepage", "webaddress"}
NAME_HEADER_CANDIDATES = {"businessname", "business", "company", "companyname", "name", "organization"}
FIRST_NAME_HEADER_CANDIDATES = {"firstname", "fname"}
LAST_NAME_HEADER_CANDIDATES = {"lastname", "lname", "surname"}
EMAIL_HEADER_CANDIDATES = {"email", "emailaddress", "contactemail"}
PHONE_HEADER_CANDIDATES = {"phone", "phonenumber", "contactphone", "mobile", "mobilephone"}
LOCATION_HEADER_CANDIDATES = {"location", "city", "address"}

# Local Visibility (Advice Local) column candidates -- distinct from the
# website-audit ones above since Advice Local needs structured NAP data
# (street/city/state/zip) rather than a URL.
STREET_HEADER_CANDIDATES = {"street", "address", "address1", "streetaddress", "addressline1"}
CITY_HEADER_CANDIDATES = {"city", "town"}
STATE_HEADER_CANDIDATES = {"state", "province", "stateprovince"}
ZIP_HEADER_CANDIDATES = {"zip", "zipcode", "postalcode", "postcode", "zippostalcode"}


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def _find_column(fieldnames: list[str], candidates: set[str]) -> str | None:
    for f in fieldnames:
        if _norm_header(f) in candidates:
            return f
    return None


def _parse_bulk_upload_file(contents: bytes, filename: str) -> tuple[list[str], list[dict]]:
    """Parses either a CSV or an Excel (.xlsx/.xls) upload into
    (fieldnames, rows) -- both shapes then feed the same auto-detection /
    processing path. Excel support needs openpyxl (added specifically for
    this) since csv.DictReader can't read the binary/zip xlsx format --
    previously .xlsx uploads silently decoded as garbage text and produced
    a "could not read a header row" error."""
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        try:
            import openpyxl
        except ImportError:
            raise HTTPException(500, "Excel support is not available on this server.")
        try:
            wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True, data_only=True)
        except Exception:
            raise HTTPException(400, "Could not read this Excel file. Please make sure it's a valid .xlsx file.")
        sheet = wb.active
        rows_iter = sheet.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            header_row = None
        if not header_row:
            raise HTTPException(400, "Could not read a header row from this Excel file.")
        fieldnames = [str(h).strip() if h is not None else "" for h in header_row]
        rows = []
        for r in rows_iter:
            if r is None or all(v is None for v in r):
                continue
            row = {}
            for i, field in enumerate(fieldnames):
                if not field:
                    continue
                val = r[i] if i < len(r) else None
                row[field] = "" if val is None else str(val)
            rows.append(row)
        return fieldnames, rows
    if name.endswith(".xls"):
        raise HTTPException(
            400,
            "Legacy .xls files aren't supported. Please save/export as .xlsx or .csv and re-upload.",
        )

    # Default: CSV (also covers .txt/no-extension plain-text uploads)
    text = contents.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    rows = [dict(r) for r in reader]
    return fieldnames, rows


def _bulk_job_brief(j: m.BulkUploadJob) -> dict:
    return {
        "id": j.id,
        "filename": j.filename,
        "status": j.status,
        "total_rows": j.total_rows,
        "processed_rows": j.processed_rows,
        "error_message": j.error_message,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        "download_available": j.status == "completed" and bool(j.result_csv),
    }


def _process_bulk_row(row: dict, cols: dict) -> dict:
    """Runs one lite audit for a single CSV row, returning the row dict
    with two columns appended. Never raises -- any per-row problem (blank/
    bad URL, audit failure) just leaves those two columns blank for that
    row so one bad line can't abort the whole batch."""
    out = dict(row)
    out["Website Audit Score"] = ""
    out["Website Audit Grade"] = ""

    raw_url = (row.get(cols["website"]) or "").strip() if cols["website"] else ""
    if not raw_url:
        return out
    try:
        url = _normalize_url(raw_url)
    except HTTPException:
        return out

    business_name = (row.get(cols["name"]) or "").strip() if cols["name"] else ""
    first_name = (row.get(cols["first_name"]) or "").strip() if cols["first_name"] else ""
    last_name = (row.get(cols["last_name"]) or "").strip() if cols["last_name"] else ""
    email = (row.get(cols["email"]) or "").strip() if cols["email"] else ""
    phone = (row.get(cols["phone"]) or "").strip() if cols["phone"] else ""
    location = (row.get(cols["location"]) or "").strip() if cols["location"] else ""
    if not business_name:
        business_name = urlparse(url).netloc
    contact_name = " ".join(p for p in [first_name, last_name] if p).strip()

    try:
        with session_scope() as db:
            biz = m.Business(
                name=business_name,
                location=location or None,
                contact_name=contact_name or None,
                contact_email=email or None,
                first_name=first_name or None,
                last_name=last_name or None,
                phone=phone or None,
                lead_source="csv_bulk",
            )
            db.add(biz)
            db.flush()
            website = m.Website(business_id=biz.id, url=url)
            db.add(website)
            db.flush()
            audit = create_audit_stub(db, website, depth="lite")
            db.flush()
            audit_id = audit.id

        execute_audit(audit_id)

        with session_scope() as db:
            audit = db.get(m.Audit, audit_id)
            if audit and audit.status == "completed" and audit.overall_score is not None:
                out["Website Audit Score"] = f"{audit.overall_score:.1f}/100"
                out["Website Audit Grade"] = audit.overall_grade or ""
    except Exception as e:
        print(f"[bulk_upload] row failed for {raw_url}: {e}")
    return out


# Lite audits skip Playwright/PSI entirely (just raw HTTP fetch, DNS
# SPF/DMARC lookups, robots.txt/sitemap fetch, and a Google Places lookup),
# so a handful of concurrent workers speeds up large lists significantly
# without hammering any single dependency too hard, while staying safely
# inside the DB connection pool budget (pool_size=5 + max_overflow=10 = 15
# total connections) -- each row briefly opens up to 3 sequential DB
# sessions (create_audit_stub / execute_audit / the follow-up score read).
BULK_MAX_WORKERS = 8

_bulk_progress_lock = threading.Lock()


def _run_bulk_upload_job(job_id: str, fieldnames: list[str], rows: list[dict], cols: dict) -> None:
    try:
        n = len(rows)
        out_rows: list[dict | None] = [None] * n
        processed = 0

        def _bump_progress():
            nonlocal processed
            # DB write happens inside the same lock as the increment --
            # otherwise two threads' writes can land out of order (thread
            # computing current=2 writes first, then thread computing
            # current=1 overwrites it back down), leaving a stale
            # processed_rows even after the job fully completes.
            with _bulk_progress_lock:
                processed += 1
                current = processed
                with session_scope() as db:
                    job = db.get(m.BulkUploadJob, job_id)
                    if job:
                        job.processed_rows = current

        def _work(i: int, row: dict) -> None:
            # Pre-allocated slot by index preserves the original CSV row
            # order in the output even though workers complete out of
            # order under concurrency.
            out_rows[i] = _process_bulk_row(row, cols)
            _bump_progress()

        max_workers = min(BULK_MAX_WORKERS, n) or 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_work, i, row) for i, row in enumerate(rows)]
            for f in futures:
                f.result()  # surface any worker exception immediately

        out_fieldnames = list(fieldnames) + ["Website Audit Score", "Website Audit Grade"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=out_fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)
        csv_bytes = buf.getvalue().encode("utf-8")

        with session_scope() as db:
            job = db.get(m.BulkUploadJob, job_id)
            if job:
                base, _ext = os.path.splitext(job.filename or "leads.csv")
                job.result_filename = f"{base}_scored.csv"
                job.result_csv = csv_bytes
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        print(f"[bulk_upload] job {job_id} failed: {e}")
        with session_scope() as db:
            job = db.get(m.BulkUploadJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.now(timezone.utc)


# ---------------- Local Visibility (Advice Local) bulk scoring ----------------
# Same upload -> background job -> download shape as the website-audit bulk
# scoring above, but each row creates an Advice Local "client" (NAP data)
# and polls for its auto-generated baseline visibility score instead of
# running an in-house audit. See advicelocal_client.py for the API details.

LOCAL_VISIBILITY_MAX_WORKERS = 4  # lower than website audit's 8: each row
# blocks polling an external service (up to ~90s worst case per
# advicelocal_client.wait_for_baseline_score) rather than doing quick local
# work, so fewer concurrent workers avoids hammering Advice Local's API
# and keeps DB sessions from piling up for very long stretches.

_local_visibility_progress_lock = threading.Lock()


def _grade_for_score(db, score: float) -> str:
    thresholds = [{"min_score": r.min_score, "grade": r.grade} for r in db.query(m.GradeThreshold).all()]
    return grade_for_score(score, thresholds)


def _local_visibility_scan_brief(scan: "m.LocalVisibilityScan") -> dict:
    biz = scan.business
    return {
        "id": scan.id,
        "business_id": scan.business_id,
        "business_name": biz.name if biz else None,
        "contact_name": biz.contact_name if biz else None,
        "contact_email": biz.contact_email if biz else None,
        "phone": biz.phone if biz else None,
        "lead_source": biz.lead_source if biz else None,
        "street": scan.street,
        "city": scan.city,
        "state": scan.state,
        "zip_code": scan.zip_code,
        "status": scan.status,
        "overall_score": scan.overall_score,
        "overall_grade": scan.overall_grade,
        "error_message": scan.error_message,
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
    }


def _process_local_visibility_row(row: dict, cols: dict) -> dict:
    """Creates an Advice Local client for one CSV row and waits for its
    baseline visibility score, returning the row dict with two columns
    appended. Never raises -- any per-row problem (missing name/zip,
    Advice Local API failure, baseline-generation timeout) just leaves
    those two columns blank so one bad line can't abort the whole batch."""
    out = dict(row)
    out["Local Visibility Score"] = ""
    out["Local Visibility Grade"] = ""

    business_name = (row.get(cols["name"]) or "").strip() if cols["name"] else ""
    zip_code = (row.get(cols["zip"]) or "").strip() if cols["zip"] else ""
    if not business_name or not zip_code:
        return out

    street = (row.get(cols["street"]) or "").strip() if cols["street"] else ""
    city = (row.get(cols["city"]) or "").strip() if cols["city"] else ""
    state = (row.get(cols["state"]) or "").strip() if cols["state"] else ""
    phone = (row.get(cols["phone"]) or "").strip() if cols["phone"] else ""
    email = (row.get(cols["email"]) or "").strip() if cols["email"] else ""
    first_name = (row.get(cols["first_name"]) or "").strip() if cols["first_name"] else ""
    last_name = (row.get(cols["last_name"]) or "").strip() if cols["last_name"] else ""
    website = (row.get(cols["website"]) or "").strip() if cols["website"] else ""
    contact_name = " ".join(p for p in [first_name, last_name] if p).strip()

    client_payload = {
        "name": business_name,
        "street": street or None,
        "city": city or None,
        "state": state or None,
        "zipcode": zip_code,
        "phone": phone or None,
        "email": email or None,
        "website": website or None,
    }
    client_payload = {k: v for k, v in client_payload.items() if v}

    try:
        with session_scope() as db:
            biz = m.Business(
                name=business_name,
                location=", ".join(p for p in [city, state] if p) or None,
                contact_name=contact_name or None,
                contact_email=email or None,
                first_name=first_name or None,
                last_name=last_name or None,
                phone=phone or None,
                lead_source="local_visibility_csv",
            )
            db.add(biz)
            db.flush()
            scan = m.LocalVisibilityScan(
                business_id=biz.id, street=street or None, city=city or None,
                state=state or None, zip_code=zip_code, status="running",
            )
            db.add(scan)
            db.flush()
            scan_id = scan.id

        client_id, error = advicelocal_client.create_client(client_payload)
        if error or not client_id:
            with session_scope() as db:
                scan = db.get(m.LocalVisibilityScan, scan_id)
                if scan:
                    scan.status = "failed"
                    scan.error_message = error or "Unknown error creating Advice Local client"
                    scan.completed_at = datetime.now(timezone.utc)
            return out

        with session_scope() as db:
            scan = db.get(m.LocalVisibilityScan, scan_id)
            if scan:
                scan.advice_local_client_id = client_id

        score_data, error = advicelocal_client.wait_for_baseline_score(client_id)
        visibility_score = advicelocal_client.extract_visibility_score(score_data)

        with session_scope() as db:
            scan = db.get(m.LocalVisibilityScan, scan_id)
            if not scan:
                return out
            if visibility_score is not None:
                grade = _grade_for_score(db, visibility_score)
                scan.overall_score = visibility_score
                scan.overall_grade = grade
                scan.raw_scores = json.dumps(score_data) if score_data else None
                scan.status = "completed"
                scan.completed_at = datetime.now(timezone.utc)
                out["Local Visibility Score"] = f"{visibility_score:.1f}/100"
                out["Local Visibility Grade"] = grade
            else:
                scan.status = "failed"
                scan.error_message = error or "Baseline report was not ready in time"
                scan.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        print(f"[local_visibility] row failed for {business_name}: {e}")
    return out


def _run_local_visibility_job(job_id: str, fieldnames: list[str], rows: list[dict], cols: dict) -> None:
    try:
        n = len(rows)
        out_rows: list[dict | None] = [None] * n
        processed = 0

        def _bump_progress():
            nonlocal processed
            with _local_visibility_progress_lock:
                processed += 1
                current = processed
                with session_scope() as db:
                    job = db.get(m.BulkUploadJob, job_id)
                    if job:
                        job.processed_rows = current

        def _work(i: int, row: dict) -> None:
            out_rows[i] = _process_local_visibility_row(row, cols)
            _bump_progress()

        max_workers = min(LOCAL_VISIBILITY_MAX_WORKERS, n) or 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_work, i, row) for i, row in enumerate(rows)]
            for f in futures:
                f.result()

        out_fieldnames = list(fieldnames) + ["Local Visibility Score", "Local Visibility Grade"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=out_fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)
        csv_bytes = buf.getvalue().encode("utf-8")

        with session_scope() as db:
            job = db.get(m.BulkUploadJob, job_id)
            if job:
                base, _ext = os.path.splitext(job.filename or "leads.csv")
                job.result_filename = f"{base}_scored.csv"
                job.result_csv = csv_bytes
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        print(f"[local_visibility] job {job_id} failed: {e}")
        with session_scope() as db:
            job = db.get(m.BulkUploadJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.now(timezone.utc)


# ---------------- Rank Checker (Serper.dev) ----------------
# Keyword rank checks (organic Google position + Google Map Pack position)
# for a business, built the same way for the manual single-check form, a
# bulk CSV/Excel upload, and the GHL webhook: each keyword gets combined
# with the business's own location ("<keyword> <city>, <state>" or
# "<keyword> <zip>") since Map Pack results are hyperlocal, per keyword
# results are stored as RankCheckKeywordResult rows. See serper_client.py.

RANK_CHECK_MAX_WORKERS = 4  # each row makes 2 Serper calls per keyword
# (organic + maps), sequentially per keyword within a row -- capped lower
# than website-audit's 8 workers to avoid bursting Serper's rate limit
# across a large bulk job.

_rank_check_progress_lock = threading.Lock()


def _default_rank_check_keywords(db: Session) -> list[str]:
    settings = db.query(m.RankCheckSettings).first()
    if not settings or not settings.default_keywords:
        return []
    return [k.strip() for k in settings.default_keywords.split(",") if k.strip()]


def _location_query_from(city: str | None, state: str | None, zip_code: str | None) -> str:
    parts = [p for p in [city, state] if p]
    if parts:
        return ", ".join(parts)
    return zip_code or ""


def _keyword_result_brief(r: "m.RankCheckKeywordResult") -> dict:
    return {
        "id": r.id,
        "keyword": r.keyword,
        "query": r.query,
        "organic_position": r.organic_position,
        "organic_url": r.organic_url,
        "map_pack_position": r.map_pack_position,
        "map_pack_found": r.map_pack_found,
        "raw_organic": json.loads(r.raw_organic) if r.raw_organic else None,
        "raw_maps": json.loads(r.raw_maps) if r.raw_maps else None,
        "error_message": r.error_message,
    }


def _rank_check_scan_brief(scan: "m.RankCheckScan") -> dict:
    biz = scan.business
    results = scan.keyword_results
    found_count = sum(1 for r in results if r.organic_position or r.map_pack_found)
    return {
        "id": scan.id,
        "business_id": scan.business_id,
        "business_name": biz.name if biz else None,
        "contact_name": biz.contact_name if biz else None,
        "contact_email": biz.contact_email if biz else None,
        "phone": biz.phone if biz else None,
        "lead_source": biz.lead_source if biz else None,
        "website": scan.website,
        "location_query": scan.location_query,
        "status": scan.status,
        "error_message": scan.error_message,
        "keyword_count": len(results),
        "found_count": found_count,
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
    }


def _run_keyword_checks(scan_id: str, business_name: str, website: str, location_query: str,
                         keywords: list[str], city: str | None = None, state: str | None = None) -> None:
    """Runs each keyword against Serper's /search (organic) and /maps
    (Map Pack), writing one RankCheckKeywordResult row per keyword, then
    marks the scan completed/failed. Opens its own DB sessions
    (session_scope) so it works identically whether called from the main
    request thread (manual single-check, GHL webhook) or a bulk-upload
    worker thread. Never raises -- a per-keyword Serper failure just
    leaves that keyword's positions null with an error_message, so one
    bad keyword can't abort the whole scan.

    `city`/`state` build a Serper `location` param (see
    serper_client.location_param) so results are actually geo-targeted to
    the business's metro area -- without it Serper only targets by `gl`
    (country), and results can otherwise land anywhere in the country.
    The location text embedded in `location_query`/`query` string still
    helps too, but the dedicated `location` param is what actually moves
    Google's ranking computation to the right area."""
    loc_param = serper_client.location_param(city, state)
    any_success = False
    last_error = None
    for kw in keywords:
        kw = (kw or "").strip()
        if not kw:
            continue
        query = f"{kw} {location_query}".strip()
        organic, err1 = serper_client.search_organic(query, location=loc_param)
        maps_places, err2 = serper_client.search_maps(query, location=loc_param)
        organic = organic or []
        maps_places = maps_places or []
        organic_position, organic_url = (
            serper_client.find_organic_position(organic, website) if website else (None, None)
        )
        map_pack_position = serper_client.find_map_pack_position(maps_places, business_name)
        error_message = None
        if err1 and err2:
            error_message = err1 or err2
            last_error = error_message
        else:
            any_success = True
        with session_scope() as db:
            db.add(m.RankCheckKeywordResult(
                scan_id=scan_id, keyword=kw, query=query,
                organic_position=organic_position, organic_url=organic_url,
                map_pack_position=map_pack_position, map_pack_found=map_pack_position is not None,
                raw_organic=json.dumps(organic[:10]) if organic else None,
                raw_maps=json.dumps(maps_places[:10]) if maps_places else None,
                error_message=error_message,
            ))
    with session_scope() as db:
        scan = db.get(m.RankCheckScan, scan_id)
        if scan:
            if any_success or not last_error:
                scan.status = "completed"
            else:
                scan.status = "failed"
                scan.error_message = last_error
            scan.completed_at = datetime.now(timezone.utc)


def _process_rank_check_row(row: dict, cols: dict, keywords: list[str]) -> dict:
    """Runs a rank check for one CSV row, returning the row dict with
    per-keyword columns appended (e.g. "tree trimming - Organic Rank",
    "tree trimming - Map Pack Rank"). Never raises -- any per-row problem
    (missing name/website) just leaves those columns blank."""
    out = dict(row)
    for kw in keywords:
        out[f"{kw} - Organic Rank"] = ""
        out[f"{kw} - Map Pack Rank"] = ""

    business_name = (row.get(cols["name"]) or "").strip() if cols["name"] else ""
    website = (row.get(cols["website"]) or "").strip() if cols["website"] else ""
    if not business_name or not website:
        return out

    street = (row.get(cols["street"]) or "").strip() if cols["street"] else ""
    city = (row.get(cols["city"]) or "").strip() if cols["city"] else ""
    state = (row.get(cols["state"]) or "").strip() if cols["state"] else ""
    zip_code = (row.get(cols["zip"]) or "").strip() if cols["zip"] else ""
    phone = (row.get(cols["phone"]) or "").strip() if cols["phone"] else ""
    email = (row.get(cols["email"]) or "").strip() if cols["email"] else ""
    first_name = (row.get(cols["first_name"]) or "").strip() if cols["first_name"] else ""
    last_name = (row.get(cols["last_name"]) or "").strip() if cols["last_name"] else ""
    contact_name = " ".join(p for p in [first_name, last_name] if p).strip()
    location_query = _location_query_from(city, state, zip_code)

    try:
        with session_scope() as db:
            biz = m.Business(
                name=business_name,
                location=location_query or None,
                contact_name=contact_name or None,
                contact_email=email or None,
                first_name=first_name or None,
                last_name=last_name or None,
                phone=phone or None,
                lead_source="rank_checker_csv",
            )
            db.add(biz)
            db.flush()
            scan = m.RankCheckScan(
                business_id=biz.id, website=website, location_query=location_query, status="running",
            )
            db.add(scan)
            db.flush()
            scan_id = scan.id

        _run_keyword_checks(scan_id, business_name, website, location_query, keywords, city=city, state=state)

        with session_scope() as db:
            results = (
                db.query(m.RankCheckKeywordResult)
                .filter_by(scan_id=scan_id)
                .all()
            )
            for r in results:
                if r.organic_position:
                    out[f"{r.keyword} - Organic Rank"] = str(r.organic_position)
                if r.map_pack_found:
                    out[f"{r.keyword} - Map Pack Rank"] = str(r.map_pack_position)
    except Exception as e:
        print(f"[rank_checker] row failed for {business_name}: {e}")
    return out


def _run_rank_check_job(job_id: str, fieldnames: list[str], rows: list[dict], cols: dict,
                         keywords: list[str]) -> None:
    try:
        n = len(rows)
        out_rows: list[dict | None] = [None] * n
        processed = 0

        def _bump_progress():
            nonlocal processed
            with _rank_check_progress_lock:
                processed += 1
                current = processed
                with session_scope() as db:
                    job = db.get(m.BulkUploadJob, job_id)
                    if job:
                        job.processed_rows = current

        def _work(i: int, row: dict) -> None:
            out_rows[i] = _process_rank_check_row(row, cols, keywords)
            _bump_progress()

        max_workers = min(RANK_CHECK_MAX_WORKERS, n) or 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_work, i, row) for i, row in enumerate(rows)]
            for f in futures:
                f.result()

        extra_cols = []
        for kw in keywords:
            extra_cols.append(f"{kw} - Organic Rank")
            extra_cols.append(f"{kw} - Map Pack Rank")
        out_fieldnames = list(fieldnames) + extra_cols
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=out_fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)
        csv_bytes = buf.getvalue().encode("utf-8")

        with session_scope() as db:
            job = db.get(m.BulkUploadJob, job_id)
            if job:
                base, _ext = os.path.splitext(job.filename or "leads.csv")
                job.result_filename = f"{base}_ranked.csv"
                job.result_csv = csv_bytes
                job.status = "completed"
                job.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        print(f"[rank_checker] job {job_id} failed: {e}")
        with session_scope() as db:
            job = db.get(m.BulkUploadJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.completed_at = datetime.now(timezone.utc)


# ---------- Request bodies ----------

class BusinessCreate(BaseModel):
    name: str
    location: str | None = None
    category: str | None = None
    service_area: str | None = None
    primary_keywords: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    notes: str | None = None


class BusinessUpdate(BusinessCreate):
    name: str | None = None


class WebsiteCreate(BaseModel):
    url: str


class CreateAuditRequest(BaseModel):
    website_url: str
    business_id: str | None = None
    business_name: str | None = None
    location: str | None = None
    category: str | None = None
    service_area: str | None = None
    primary_keywords: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    notes: str | None = None


class ReportRequest(BaseModel):
    mode: str  # "full" | "prospect"


class BrandingUpdate(BaseModel):
    company_name: str | None = None
    phone: str | None = None
    email: str | None = None
    from_email: str | None = None
    website: str | None = None
    contact_form_url: str | None = None
    scheduling_url: str | None = None
    cta_headline: str | None = None
    cta_button_text: str | None = None
    widget_heading: str | None = None
    widget_button_text: str | None = None


class WidgetAuditRequest(BaseModel):
    website_url: str
    business_name: str | None = None
    first_name: str
    last_name: str | None = None
    email: str
    phone: str | None = None


class ScoringWeightsUpdate(BaseModel):
    weights: dict[str, float]  # category_key -> weight (0-1)


class RequestFullAuditPayload(BaseModel):
    wants_help: bool


class GHLAuditRequest(BaseModel):
    """Body shape for GHL's outbound Custom Webhook action -- map contact
    fields into these keys in the workflow builder's payload editor.
    `website` is the only hard requirement; everything else is optional
    and only improves the Local SEO / NAP check (business_name + location
    feed a Google Places lookup) or gets echoed back in the result webhook
    so GHL Workflow #2 can match/update the right contact."""
    contact_id: str
    website: str
    business_name: str | None = None
    location: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None


class GHLLocalVisibilityRequest(BaseModel):
    """Body shape for the Local Visibility counterpart of the GHL
    audit-request webhook. Unlike the website audit, Advice Local needs
    structured NAP data (not a URL) -- business_name and zip are the hard
    requirements; street/city/state improve data quality but are
    optional. See advicelocal_client.py."""
    contact_id: str
    business_name: str
    zip: str
    street: str | None = None
    city: str | None = None
    state: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None


class LocalVisibilitySingleRequest(BaseModel):
    """Body shape for the single-lookup form at the top of #/local-visibility
    (as opposed to the bulk CSV/Excel upload below it). Same required
    fields as the bulk row processor (business_name + zip), same optional
    NAP fields. Runs synchronously -- Advice Local's baseline score can
    take up to advicelocal_client's ~60s poll timeout, which is fine for a
    single on-demand check triggered by a button click."""
    business_name: str
    zip: str
    street: str | None = None
    city: str | None = None
    state: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None


class RankCheckSingleRequest(BaseModel):
    """Body shape for the Rank Checker manual-check form. business_name +
    website are hard requirements (website's domain is what organic
    results are matched against); city/state/zip build the location
    string appended to each keyword ("<keyword> <city>, <state>"), since
    Map Pack results are hyperlocal. `keywords` is optional -- if omitted
    or empty, falls back to the default keyword template in
    RankCheckSettings (Settings page)."""
    business_name: str
    website: str
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    keywords: list[str] | None = None


class GHLRankCheckRequest(BaseModel):
    """Rank Checker counterpart of GHLAuditRequest/GHLLocalVisibilityRequest.
    `keywords` is optional -- if the GHL workflow doesn't map a keyword
    list, the default keyword template from RankCheckSettings is used, so
    a bulk GHL automation can run with zero per-contact keyword config."""
    contact_id: str
    business_name: str
    website: str
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    keywords: list[str] | None = None


class RankCheckSettingsUpdate(BaseModel):
    default_keywords: list[str]


def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise HTTPException(400, "Website URL is required")
    if "://" not in url:
        url = f"https://{url}"
    return url


def _public_base_url(request: Request) -> str:
    """Best-effort trusted base URL for building links inside emails.

    Prefers the published-app custom domain, then the browser-supplied
    Origin/Referer (present on same-origin fetch() calls from the widget),
    and only falls back to the raw request base URL (internal infra
    hostname) as a last resort so links still work during local testing.
    """
    custom_domain = os.environ.get("WORKSHOP_CUSTOM_DOMAIN")
    if custom_domain:
        return f"https://{custom_domain}"
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return str(request.base_url).rstrip("/")


def create_app(static_dir: str) -> FastAPI:
    # Ensure schema + reference data exist on boot (idempotent).
    init_db()

    api = APIRouter()
    templates = Jinja2Templates(directory=static_dir)

    @api.get("/health")
    def health():
        return {"ok": True}

    # ---------------- Categories & Settings ----------------

    @api.get("/categories")
    def list_categories(db: Session = Depends(get_db)):
        cats = db.query(m.Category).order_by(m.Category.sort_order).all()
        return [{"id": c.id, "key": c.key, "display_name": c.display_name} for c in cats]

    @api.get("/settings/branding")
    def get_branding(db: Session = Depends(get_db)):
        b = db.query(m.BrandingConfig).first()
        if not b:
            raise HTTPException(404, "Branding not configured")
        return branding_dict(b)

    @api.put("/settings/branding")
    def update_branding(payload: BrandingUpdate, db: Session = Depends(get_db)):
        b = db.query(m.BrandingConfig).first()
        if not b:
            b = m.BrandingConfig()
            db.add(b)
        for field, value in payload.dict(exclude_unset=True).items():
            setattr(b, field, value)
        db.commit()
        return branding_dict(b)

    @api.post("/settings/branding/logo")
    def upload_branding_logo(file: UploadFile = File(...), db: Session = Depends(get_db)):
        allowed_ext = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                       ".svg": "image/svg+xml", ".webp": "image/webp"}
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in allowed_ext:
            raise HTTPException(400, "Logo must be a PNG, JPG, SVG, or WEBP image")

        MAX_LOGO_BYTES = 5 * 1024 * 1024  # 5 MB cap
        contents = file.file.read(MAX_LOGO_BYTES + 1)
        if not contents:
            raise HTTPException(400, "Empty file")
        if len(contents) > MAX_LOGO_BYTES:
            raise HTTPException(413, "Logo file too large (max 5 MB)")

        # Stored as bytea in Postgres, not the local filesystem -- disk
        # writes in this environment don't survive a restart/redeploy.
        b = db.query(m.BrandingConfig).first()
        if not b:
            b = m.BrandingConfig()
            db.add(b)
        b.logo_data = contents
        b.logo_mime = allowed_ext[ext]
        b.logo_url = ""  # legacy field, no longer used to locate the file
        db.commit()
        return branding_dict(b)

    @api.get("/settings/branding/logo")
    def get_branding_logo(db: Session = Depends(get_db)):
        b = db.query(m.BrandingConfig).first()
        if not b or not b.logo_data:
            raise HTTPException(404, "No logo uploaded")
        # SVG is deliberately excluded from safe-inline types elsewhere in
        # the codebase's upload patterns (can embed <script>), but this is
        # an agency-only settings upload (not public user-generated
        # content), so SVG is fine to serve inline here.
        return Response(
            content=bytes(b.logo_data),
            media_type=b.logo_mime or "application/octet-stream",
            headers={
                "Cache-Control": "public, max-age=86400",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @api.get("/settings/scoring")
    def get_scoring(db: Session = Depends(get_db)):
        # Only active configs are shown/editable -- e.g. the retired
        # "authority" category is kept (soft-deactivated) in the DB so
        # historical audits still resolve their category_id FK, but it
        # should no longer appear in the admin scoring-weights UI.
        configs = db.query(m.ScoringConfig).filter_by(active=True).options(joinedload(m.ScoringConfig.category)).all()
        return [
            {
                "category_id": c.category_id,
                "category_key": c.category.key,
                "category_name": c.category.display_name,
                "weight": c.weight,
                "active": c.active,
            }
            for c in sorted(configs, key=lambda x: x.category.sort_order)
        ]

    @api.put("/settings/scoring")
    def update_scoring(payload: ScoringWeightsUpdate, db: Session = Depends(get_db)):
        total = sum(payload.weights.values())
        if total <= 0:
            raise HTTPException(400, "Weights must sum to a positive number")
        cats = {c.key: c for c in db.query(m.Category).all()}
        for key, weight in payload.weights.items():
            cat = cats.get(key)
            if not cat:
                continue
            cfg = db.query(m.ScoringConfig).filter_by(category_id=cat.id).first()
            if cfg:
                # normalize so weights always sum to 1.0 across submitted categories
                cfg.weight = weight / total
        db.commit()
        return get_scoring(db)

    # ---------------- Businesses ----------------

    @api.get("/businesses")
    def list_businesses(lead_source: str | None = None, db: Session = Depends(get_db)):
        """List businesses for the main dashboard.

        `lead_source="ghl"` / `lead_source="csv_bulk"` / `lead_source=
        "local_visibility_csv"` / `lead_source="local_visibility_ghl"`
        bulk-scoring records (GHL webhook, CSV bulk-upload, and Advice
        Local local-visibility scoring, all high-volume/low-detail
        outreach scoring runs) are deliberately excluded by default --
        not the kind of audit this dashboard is designed to showcase.
        They have their own dedicated spreadsheet-style views (GET
        /api/businesses?lead_source=ghl used by #/ghl-leads, the #/bulk-
        scoring view's own job-history list, and the #/local-visibility
        view's own job-history list) so they don't clutter the main list.
        Pass an explicit `lead_source` value to opt into a specific source
        (e.g. `?lead_source=ghl`), or `?lead_source=all` to get everything.
        """
        query = db.query(m.Business)
        if lead_source == "all":
            pass
        elif lead_source:
            query = query.filter(m.Business.lead_source == lead_source)
        else:
            query = query.filter(m.Business.lead_source.notin_(
                ["ghl", "csv_bulk", "local_visibility_csv", "local_visibility_ghl", "local_visibility_manual",
                 "rank_checker_csv", "rank_checker_ghl", "rank_checker_manual"]
            ))
        businesses = query.order_by(m.Business.created_at.desc()).all()
        results = []
        for b in businesses:
            brief = business_brief(b)
            latest_audit = None
            for w in b.websites:
                for a in sorted(w.audits, key=lambda x: x.created_at, reverse=True):
                    if latest_audit is None or a.created_at > latest_audit.created_at:
                        latest_audit = a
            brief["latest_audit"] = audit_summary(latest_audit) if latest_audit else None
            results.append(brief)
        return results

    @api.post("/businesses")
    def create_business(payload: BusinessCreate, db: Session = Depends(get_db)):
        biz = m.Business(**payload.dict())
        db.add(biz)
        db.commit()
        db.refresh(biz)
        return business_brief(biz)

    @api.get("/businesses/{business_id}")
    def get_business(business_id: str, db: Session = Depends(get_db)):
        biz = db.get(m.Business, business_id)
        if not biz:
            raise HTTPException(404, "Business not found")
        result = business_brief(biz)
        result["websites"] = []
        for w in biz.websites:
            w_data = website_brief(w)
            w_data["audits"] = [audit_summary(a) for a in sorted(w.audits, key=lambda x: x.created_at)]
            result["websites"].append(w_data)
        return result

    @api.put("/businesses/{business_id}")
    def update_business(business_id: str, payload: BusinessUpdate, db: Session = Depends(get_db)):
        biz = db.get(m.Business, business_id)
        if not biz:
            raise HTTPException(404, "Business not found")
        for field, value in payload.dict(exclude_unset=True).items():
            if value is not None:
                setattr(biz, field, value)
        db.commit()
        return business_brief(biz)

    @api.delete("/businesses/{business_id}")
    def delete_business(business_id: str, db: Session = Depends(get_db)):
        biz = db.get(m.Business, business_id)
        if not biz:
            raise HTTPException(404, "Business not found")
        db.delete(biz)
        db.commit()
        return {"deleted": True, "id": business_id}

    # ---------------- Websites ----------------

    @api.post("/businesses/{business_id}/websites")
    def add_website(business_id: str, payload: WebsiteCreate, db: Session = Depends(get_db)):
        biz = db.get(m.Business, business_id)
        if not biz:
            raise HTTPException(404, "Business not found")
        website = m.Website(business_id=business_id, url=_normalize_url(payload.url))
        db.add(website)
        db.commit()
        db.refresh(website)
        return website_brief(website)

    @api.get("/websites/{website_id}")
    def get_website(website_id: str, db: Session = Depends(get_db)):
        website = db.get(m.Website, website_id)
        if not website:
            raise HTTPException(404, "Website not found")
        data = website_brief(website)
        data["audits"] = [audit_summary(a) for a in sorted(website.audits, key=lambda x: x.created_at)]
        data["business"] = business_brief(website.business)
        return data

    @api.delete("/websites/{website_id}")
    def delete_website(website_id: str, db: Session = Depends(get_db)):
        website = db.get(m.Website, website_id)
        if not website:
            raise HTTPException(404, "Website not found")
        db.delete(website)
        db.commit()
        return {"deleted": True, "id": website_id}

    # ---------------- Audits ----------------

    @api.post("/audits")
    def create_audit(payload: CreateAuditRequest, db: Session = Depends(get_db)):
        url = _normalize_url(payload.website_url)

        if payload.business_id:
            biz = db.get(m.Business, payload.business_id)
            if not biz:
                raise HTTPException(404, "Business not found")
        else:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            biz = m.Business(
                name=payload.business_name or domain,
                location=payload.location,
                category=payload.category,
                service_area=payload.service_area,
                primary_keywords=payload.primary_keywords,
                contact_name=payload.contact_name,
                contact_email=payload.contact_email,
                notes=payload.notes,
            )
            db.add(biz)
            db.flush()

        website = m.Website(business_id=biz.id, url=url)
        db.add(website)
        db.flush()

        audit = create_audit_stub(db, website)
        db.commit()
        db.refresh(audit)
        _run_audit_in_background(audit.id)
        return audit_detail(audit)

    @api.post("/websites/{website_id}/audits/rerun")
    def rerun_audit(website_id: str, db: Session = Depends(get_db)):
        website = db.get(m.Website, website_id)
        if not website:
            raise HTTPException(404, "Website not found")
        audit = create_audit_stub(db, website)
        db.commit()
        db.refresh(audit)
        _run_audit_in_background(audit.id)
        return audit_detail(audit)

    @api.get("/audits/{audit_id}")
    def get_audit(audit_id: str, db: Session = Depends(get_db)):
        audit = db.get(m.Audit, audit_id)
        if not audit:
            raise HTTPException(404, "Audit not found")
        return audit_detail(audit)

    @api.delete("/audits/{audit_id}")
    def delete_audit(audit_id: str, db: Session = Depends(get_db)):
        audit = db.get(m.Audit, audit_id)
        if not audit:
            raise HTTPException(404, "Audit not found")
        db.delete(audit)
        db.commit()
        return {"deleted": True, "id": audit_id}

    # ---------------- Reports ----------------

    @api.post("/audits/{audit_id}/reports")
    def create_or_get_report(audit_id: str, payload: ReportRequest, db: Session = Depends(get_db)):
        if payload.mode not in ("full", "prospect"):
            raise HTTPException(400, "mode must be 'full' or 'prospect'")
        audit = db.get(m.Audit, audit_id)
        if not audit:
            raise HTTPException(404, "Audit not found")
        report = db.query(m.Report).filter_by(audit_id=audit_id, mode=payload.mode).first()
        if not report:
            report = m.Report(audit_id=audit_id, mode=payload.mode)
            db.add(report)
            db.commit()
            db.refresh(report)
        return report_meta(report)

    @api.get("/audits/{audit_id}/report")
    def get_report_for_audit(audit_id: str, mode: str = "full", db: Session = Depends(get_db)):
        audit = db.get(m.Audit, audit_id)
        if not audit:
            raise HTTPException(404, "Audit not found")
        branding = db.query(m.BrandingConfig).first()
        if mode == "prospect":
            return build_prospect_snapshot(audit, branding)
        return build_full_report(audit, branding)

    @api.get("/reports/{token}")
    def get_report_by_token(token: str, db: Session = Depends(get_db)):
        report = db.query(m.Report).filter_by(share_token=token).first()
        if not report:
            raise HTTPException(404, "Report not found")
        audit = db.get(m.Audit, report.audit_id)
        branding = db.query(m.BrandingConfig).first()
        if report.mode == "prospect":
            data = build_prospect_snapshot(audit, branding)
        else:
            data = build_full_report(audit, branding)
        data["share_token"] = token
        return data

    @api.post("/reports/{token}/request-full-audit")
    def request_full_audit(token: str, payload: RequestFullAuditPayload, request: Request, db: Session = Depends(get_db)):
        """Public, no-auth endpoint behind the "Request Your Full Audit" CTA
        on a prospect snapshot (widget results or public share link). Records
        the lead's answer to "want help fixing these?" on their Business
        record (shown as a badge on the business tile / report in the
        agency's dashboard) and emails them the full audit report either way.
        """
        report = db.query(m.Report).filter_by(share_token=token).first()
        if not report:
            raise HTTPException(404, "Report not found")
        audit = db.get(m.Audit, report.audit_id)
        if not audit or not audit.website or not audit.website.business:
            raise HTTPException(404, "Business not found for this report")
        biz = audit.website.business

        biz.wants_fix_help = "yes" if payload.wants_help else "no"
        biz.full_audit_requested_at = datetime.now(timezone.utc)

        full_report = db.query(m.Report).filter_by(audit_id=audit.id, mode="full").first()
        if not full_report:
            full_report = m.Report(audit_id=audit.id, mode="full")
            db.add(full_report)
        db.commit()
        db.refresh(full_report)

        emailed = False
        if biz.contact_email:
            branding = db.query(m.BrandingConfig).first()
            b_dict = branding_dict(branding) if branding else {}
            base_url = _public_base_url(request)
            full_report_url = f"{base_url}/#/share/{full_report.share_token}"
            try:
                subject, html = full_audit_email(
                    b_dict, biz.first_name, biz.name, audit.website.url,
                    full_report_url, payload.wants_help,
                )
                emailed = send_email(biz.contact_email, subject, html, from_email=b_dict.get("from_email") or None)
            except Exception:
                pass

        return {"ok": True, "wants_help": payload.wants_help, "emailed": emailed}

    # ---------------- GoHighLevel Integration ----------------

    @api.post("/integrations/ghl/audit-request")
    def ghl_audit_request(payload: GHLAuditRequest, request: Request, db: Session = Depends(get_db)):
        """Receiver for GHL Workflow #1's outbound "Custom Webhook" action.
        Runs a fast "lite" audit (no Playwright render, no PageSpeed
        Insights -- see live_collector.collect(depth="lite")) synchronously
        (typically a few seconds), then POSTs the score/grade/report link
        back to GHL's Inbound Webhook Trigger URL (ghl_client.post_audit_result)
        so a second GHL Workflow can update that contact's custom fields and
        send the outreach message -- entirely inside GHL, no CSV export/
        import and no GHL API key required for this flow. See ghl_client.py
        for the full round-trip design.

        Auth: a shared secret configured as a static header in GHL's
        Custom Webhook action (any header name works on GHL's side; this
        expects `X-GHL-Secret`), checked against the GHL_INBOUND_SECRET
        project secret. If that secret isn't set yet, the check is skipped
        (useful for first wiring this up before locking it down)."""
        expected_secret = os.environ.get("GHL_INBOUND_SECRET")
        if expected_secret and request.headers.get("x-ghl-secret") != expected_secret:
            raise HTTPException(401, "Invalid or missing webhook secret")

        url = _normalize_url(payload.website)
        business_name = (payload.business_name or "").strip() or urlparse(url).netloc
        full_name = " ".join(p for p in [payload.first_name, payload.last_name] if p).strip()

        # Idempotency: reuse the same Business record across repeat runs for
        # the same GHL contact (e.g. re-entering the workflow later) instead
        # of creating a fresh duplicate business every time.
        biz = db.query(m.Business).filter_by(ghl_contact_id=payload.contact_id).first()
        if biz:
            biz.name = business_name
            biz.location = payload.location or biz.location
            biz.contact_name = full_name or biz.contact_name
            biz.contact_email = payload.email or biz.contact_email
            biz.first_name = payload.first_name or biz.first_name
            biz.last_name = payload.last_name or biz.last_name
            biz.phone = payload.phone or biz.phone
        else:
            biz = m.Business(
                name=business_name,
                location=payload.location,
                contact_name=full_name or None,
                contact_email=payload.email,
                first_name=payload.first_name,
                last_name=payload.last_name,
                phone=payload.phone,
                lead_source="ghl",
                ghl_contact_id=payload.contact_id,
            )
            db.add(biz)
        db.flush()

        website = m.Website(business_id=biz.id, url=url)
        db.add(website)
        db.flush()

        audit = create_audit_stub(db, website, depth="lite")
        db.flush()
        prospect_report = m.Report(audit_id=audit.id, mode="prospect")
        db.add(prospect_report)
        db.commit()
        db.refresh(audit)
        db.refresh(prospect_report)

        # Lite audits are fast (no browser render, no PSI calls) -- run
        # inline rather than backgrounding, so the result webhook back to
        # GHL fires before this request even returns.
        execute_audit(audit.id)
        db.refresh(audit)

        base_url = _public_base_url(request)
        report_url = f"{base_url}/#/share/{prospect_report.share_token}"

        result = {
            "contact_id": payload.contact_id,
            "success": audit.status == "completed",
            "status": audit.status,
            "overall_score": audit.overall_score,
            "overall_grade": audit.overall_grade,
            "report_url": report_url,
            "error": audit.error_message,
        }
        ghl_client.post_audit_result(result)
        return result

    @api.post("/integrations/ghl/local-visibility-request")
    def ghl_local_visibility_request(payload: GHLLocalVisibilityRequest, request: Request, db: Session = Depends(get_db)):
        """Local Visibility counterpart of /integrations/ghl/audit-request.
        Creates/reuses a Business (idempotent on ghl_contact_id, same
        pattern), creates an Advice Local client, waits (synchronously --
        this can take up to advicelocal_client's ~90s timeout, which is
        fine since this endpoint is expected to be called from a GHL
        workflow action, not a page load) for the baseline score, then
        POSTs the result back to GHL's Inbound Webhook Trigger URL via the
        same ghl_client.post_audit_result -- Workflow #2 just needs to be
        set up to read local_visibility_score/grade fields instead of (or
        alongside) overall_score/overall_grade.

        Auth: same shared-secret check as the website-audit GHL route."""
        expected_secret = os.environ.get("GHL_INBOUND_SECRET")
        if expected_secret and request.headers.get("x-ghl-secret") != expected_secret:
            raise HTTPException(401, "Invalid or missing webhook secret")

        business_name = payload.business_name.strip()
        zip_code = payload.zip.strip()
        if not business_name or not zip_code:
            raise HTTPException(400, "business_name and zip are required")
        full_name = " ".join(p for p in [payload.first_name, payload.last_name] if p).strip()

        biz = db.query(m.Business).filter_by(ghl_contact_id=payload.contact_id).first()
        if biz:
            biz.name = business_name
            biz.location = ", ".join(p for p in [payload.city, payload.state] if p) or biz.location
            biz.contact_name = full_name or biz.contact_name
            biz.contact_email = payload.email or biz.contact_email
            biz.first_name = payload.first_name or biz.first_name
            biz.last_name = payload.last_name or biz.last_name
            biz.phone = payload.phone or biz.phone
        else:
            biz = m.Business(
                name=business_name,
                location=", ".join(p for p in [payload.city, payload.state] if p) or None,
                contact_name=full_name or None,
                contact_email=payload.email,
                first_name=payload.first_name,
                last_name=payload.last_name,
                phone=payload.phone,
                lead_source="local_visibility_ghl",
                ghl_contact_id=payload.contact_id,
            )
            db.add(biz)
        db.flush()

        scan = m.LocalVisibilityScan(
            business_id=biz.id, street=payload.street, city=payload.city,
            state=payload.state, zip_code=zip_code, status="running",
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)

        client_payload = {k: v for k, v in {
            "name": business_name, "street": payload.street, "city": payload.city,
            "state": payload.state, "zipcode": zip_code, "phone": payload.phone,
            "email": payload.email, "website": payload.website,
        }.items() if v}

        client_id, error = advicelocal_client.create_client(client_payload)
        result = {
            "contact_id": payload.contact_id,
            "success": False,
            "local_visibility_score": None,
            "local_visibility_grade": None,
            "error": error,
        }
        if client_id:
            scan.advice_local_client_id = client_id
            db.commit()
            score_data, error = advicelocal_client.wait_for_baseline_score(client_id)
            visibility_score = advicelocal_client.extract_visibility_score(score_data)
            if visibility_score is not None:
                grade = _grade_for_score(db, visibility_score)
                scan.overall_score = visibility_score
                scan.overall_grade = grade
                scan.raw_scores = json.dumps(score_data) if score_data else None
                scan.status = "completed"
                scan.completed_at = datetime.now(timezone.utc)
                result["success"] = True
                result["local_visibility_score"] = visibility_score
                result["local_visibility_grade"] = grade
                result["error"] = None
            else:
                scan.status = "failed"
                scan.error_message = error or "Baseline report was not ready in time"
                result["error"] = scan.error_message
        else:
            scan.status = "failed"
            scan.error_message = error
        scan.completed_at = scan.completed_at or datetime.now(timezone.utc)
        db.commit()

        ghl_client.post_audit_result(result)
        return result

    @api.post("/integrations/ghl/rank-check-request")
    def ghl_rank_check_request(payload: GHLRankCheckRequest, request: Request, db: Session = Depends(get_db)):
        """Rank Checker counterpart of the GHL audit-request webhooks
        above. Creates/reuses a Business (idempotent on ghl_contact_id,
        same pattern), builds a location string from city/state/zip, runs
        each keyword (payload.keywords, or the default keyword template
        from RankCheckSettings if omitted -- see _default_rank_check_keywords)
        against Serper's organic + Maps APIs, then POSTs the result back
        to GHL's Inbound Webhook Trigger URL the same way the other GHL
        routes do. Runs synchronously -- fine for a workflow action, not a
        page load; total time is roughly len(keywords) * ~2-4s (two
        sequential Serper calls per keyword).

        Auth: same shared-secret check as the other GHL routes."""
        expected_secret = os.environ.get("GHL_INBOUND_SECRET")
        if expected_secret and request.headers.get("x-ghl-secret") != expected_secret:
            raise HTTPException(401, "Invalid or missing webhook secret")

        business_name = payload.business_name.strip()
        website = (payload.website or "").strip()
        if not business_name or not website:
            raise HTTPException(400, "business_name and website are required")
        keywords = [k.strip() for k in (payload.keywords or []) if k.strip()] or _default_rank_check_keywords(db)
        if not keywords:
            raise HTTPException(400, "No keywords provided and no default keyword template configured in Settings")
        full_name = " ".join(p for p in [payload.first_name, payload.last_name] if p).strip()
        location_query = _location_query_from(payload.city, payload.state, payload.zip)

        biz = db.query(m.Business).filter_by(ghl_contact_id=payload.contact_id).first()
        if biz:
            biz.name = business_name
            biz.location = location_query or biz.location
            biz.contact_name = full_name or biz.contact_name
            biz.contact_email = payload.email or biz.contact_email
            biz.first_name = payload.first_name or biz.first_name
            biz.last_name = payload.last_name or biz.last_name
            biz.phone = payload.phone or biz.phone
        else:
            biz = m.Business(
                name=business_name,
                location=location_query or None,
                contact_name=full_name or None,
                contact_email=payload.email,
                first_name=payload.first_name,
                last_name=payload.last_name,
                phone=payload.phone,
                lead_source="rank_checker_ghl",
                ghl_contact_id=payload.contact_id,
            )
            db.add(biz)
        db.flush()

        scan = m.RankCheckScan(
            business_id=biz.id, website=website, location_query=location_query, status="running",
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)

        _run_keyword_checks(scan.id, business_name, website, location_query, keywords, city=payload.city, state=payload.state)

        db.refresh(scan)
        keyword_results = (
            db.query(m.RankCheckKeywordResult)
            .filter_by(scan_id=scan.id)
            .order_by(m.RankCheckKeywordResult.created_at)
            .all()
        )
        result = {
            "contact_id": payload.contact_id,
            "success": scan.status == "completed",
            "status": scan.status,
            "error": scan.error_message,
            "keyword_results": [_keyword_result_brief(r) for r in keyword_results],
        }
        ghl_client.post_audit_result(result)
        return result



    @api.post("/widget/audit")
    def widget_audit(payload: WidgetAuditRequest, request: Request, db: Session = Depends(get_db)):
        """Public, no-auth endpoint backing the embeddable "Audit Your
        Website Now!" widget. Creates a lead-sourced Business + Website,
        starts the real audit in the background, and returns immediately
        with IDs the widget polls -- it does NOT wait for the audit to
        finish. A single long-lived synchronous request here previously
        risked hitting the reverse proxy's own response timeout (independent
        of any client-side timeout), which surfaced to visitors as a
        generic "something went wrong" failure with no useful audit ever
        having run. See audit_engine.engine.execute_audit / routes.py's
        _run_audit_in_background for the actual pipeline.
        """
        url = _normalize_url(payload.website_url)
        full_name = " ".join(p for p in [payload.first_name, payload.last_name] if p).strip()
        business_name = (payload.business_name or "").strip() or urlparse(url).netloc

        biz = m.Business(
            name=business_name,
            contact_name=full_name or None,
            contact_email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone=payload.phone,
            lead_source="widget",
        )
        db.add(biz)
        db.flush()

        website = m.Website(business_id=biz.id, url=url)
        db.add(website)
        db.flush()

        audit = create_audit_stub(db, website)
        db.flush()

        prospect_report = m.Report(audit_id=audit.id, mode="prospect")
        db.add(prospect_report)
        full_report = m.Report(audit_id=audit.id, mode="full")
        db.add(full_report)
        db.commit()
        db.refresh(audit)
        db.refresh(prospect_report)
        db.refresh(full_report)

        base_url = _public_base_url(request)
        lead = {"first_name": payload.first_name, "last_name": payload.last_name,
                "email": payload.email, "phone": payload.phone}

        def _run_then_email():
            execute_audit(audit.id)
            _send_widget_emails(
                audit.id, lead, biz.name, url,
                prospect_report.share_token, full_report.share_token, base_url,
            )

        threading.Thread(target=_run_then_email, daemon=True).start()

        return {
            "status": "running",
            "audit_id": audit.id,
            "business_id": biz.id,
            "website_id": website.id,
            "share_token": prospect_report.share_token,
            "full_share_token": full_report.share_token,
        }

    # ---------------- Bulk CSV Scoring ----------------

    @api.post("/bulk-scoring/upload")
    async def bulk_upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
        """Accepts a lead-list CSV, auto-detects the website/URL column
        (plus optional business name / contact columns), and kicks off a
        background job that runs a depth="lite" audit against every row.
        Returns immediately with a job id to poll -- see
        _run_bulk_upload_job for the actual processing."""
        MAX_BULK_BYTES = 20 * 1024 * 1024  # 20 MB -- plenty for tens of thousands of plain-text rows
        contents = await file.read(MAX_BULK_BYTES + 1)
        if not contents:
            raise HTTPException(400, "Empty file")
        if len(contents) > MAX_BULK_BYTES:
            raise HTTPException(413, "File too large (max 20 MB)")

        fieldnames, rows = _parse_bulk_upload_file(contents, file.filename or "")
        if not fieldnames:
            raise HTTPException(400, "Could not read a header row from this file.")

        website_col = _find_column(fieldnames, WEBSITE_HEADER_CANDIDATES)
        if not website_col:
            raise HTTPException(
                400,
                f"Could not find a website/URL column. Found columns: {', '.join(fieldnames)}. "
                "Please include a column named Website, URL, Domain, or Site.",
            )
        cols = {
            "website": website_col,
            "name": _find_column(fieldnames, NAME_HEADER_CANDIDATES),
            "first_name": _find_column(fieldnames, FIRST_NAME_HEADER_CANDIDATES),
            "last_name": _find_column(fieldnames, LAST_NAME_HEADER_CANDIDATES),
            "email": _find_column(fieldnames, EMAIL_HEADER_CANDIDATES),
            "phone": _find_column(fieldnames, PHONE_HEADER_CANDIDATES),
            "location": _find_column(fieldnames, LOCATION_HEADER_CANDIDATES),
        }

        rows = [dict(r) for r in rows]
        if not rows:
            raise HTTPException(400, "No data rows found in this file.")

        job = m.BulkUploadJob(
            job_type="website_audit",
            filename=file.filename or "upload.csv", status="running",
            total_rows=len(rows), processed_rows=0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        threading.Thread(
            target=_run_bulk_upload_job,
            args=(job.id, fieldnames, rows, cols),
            daemon=True,
        ).start()

        return {"job_id": job.id, "status": "running", "total_rows": job.total_rows}

    @api.get("/bulk-scoring/jobs")
    def list_bulk_jobs(db: Session = Depends(get_db)):
        jobs = (
            db.query(m.BulkUploadJob)
            .filter(m.BulkUploadJob.job_type == "website_audit")
            .order_by(m.BulkUploadJob.created_at.desc())
            .all()
        )
        return [_bulk_job_brief(j) for j in jobs]

    @api.get("/bulk-scoring/jobs/{job_id}")
    def get_bulk_job(job_id: str, db: Session = Depends(get_db)):
        job = db.get(m.BulkUploadJob, job_id)
        if not job or job.job_type != "website_audit":
            raise HTTPException(404, "Job not found")
        return _bulk_job_brief(job)

    @api.get("/bulk-scoring/jobs/{job_id}/download")
    def download_bulk_job(job_id: str, db: Session = Depends(get_db)):
        job = db.get(m.BulkUploadJob, job_id)
        if not job or job.job_type != "website_audit" or not job.result_csv:
            raise HTTPException(404, "Result not ready yet")
        filename = job.result_filename or "scored_leads.csv"
        return Response(
            content=bytes(job.result_csv),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @api.get("/bulk-scoring/jobs/{job_id}/results")
    def get_bulk_job_results(job_id: str, db: Session = Depends(get_db)):
        """Parses the job's stored result CSV back into JSON rows so the
        dashboard can render the scored list inline, not just offer a
        download. Reuses the same bytes that /download serves -- no
        separate storage needed."""
        job = db.get(m.BulkUploadJob, job_id)
        if not job or job.job_type != "website_audit":
            raise HTTPException(404, "Job not found")
        if not job.result_csv:
            return {"columns": [], "rows": []}
        text = bytes(job.result_csv).decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        columns = reader.fieldnames or []
        rows = [dict(r) for r in reader]
        return {"columns": columns, "rows": rows}

    # ---------------- Local Visibility (Advice Local) Bulk Scoring ----------------

    @api.post("/local-visibility/single")
    def local_visibility_single(payload: LocalVisibilitySingleRequest, db: Session = Depends(get_db)):
        """One-off check for the form at the top of #/local-visibility.
        Same Advice Local client-create + baseline-poll flow as a bulk
        row / the GHL webhook, just triggered manually and returned
        directly in the response (no CSV, no job row, no GHL callback).
        Creates a real Business + LocalVisibilityScan so it shows up
        alongside CSV/GHL-sourced scans in the DB (lead_source=
        "local_visibility_manual", also excluded from the main dashboard
        list -- see list_businesses)."""
        business_name = payload.business_name.strip()
        zip_code = payload.zip.strip()
        street = (payload.street or "").strip()
        phone = (payload.phone or "").strip()
        if not business_name or not zip_code or not street or not phone:
            raise HTTPException(400, "Business name, street address, zip code, and phone are required")
        full_name = " ".join(p for p in [payload.first_name, payload.last_name] if p).strip()

        biz = m.Business(
            name=business_name,
            location=", ".join(p for p in [payload.city, payload.state] if p) or None,
            contact_name=full_name or None,
            contact_email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone=payload.phone,
            lead_source="local_visibility_manual",
        )
        db.add(biz)
        db.flush()

        scan = m.LocalVisibilityScan(
            business_id=biz.id, street=payload.street, city=payload.city,
            state=payload.state, zip_code=zip_code, status="running",
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)

        client_payload = {k: v for k, v in {
            "name": business_name, "street": payload.street, "city": payload.city,
            "state": payload.state, "zipcode": zip_code, "phone": payload.phone,
            "email": payload.email, "website": payload.website,
        }.items() if v}

        client_id, error = advicelocal_client.create_client(client_payload)
        result = {
            "business_id": biz.id,
            "scan_id": scan.id,
            "business_name": business_name,
            "success": False,
            "local_visibility_score": None,
            "local_visibility_grade": None,
            "report": None,
            "error": error,
        }
        if client_id:
            scan.advice_local_client_id = client_id
            db.commit()
            score_data, error = advicelocal_client.wait_for_baseline_score(client_id)
            visibility_score = advicelocal_client.extract_visibility_score(score_data)
            if visibility_score is not None:
                grade = _grade_for_score(db, visibility_score)
                scan.overall_score = visibility_score
                scan.overall_grade = grade
                scan.raw_scores = json.dumps(score_data) if score_data else None
                scan.status = "completed"
                scan.completed_at = datetime.now(timezone.utc)
                result["success"] = True
                result["local_visibility_score"] = visibility_score
                result["local_visibility_grade"] = grade
                result["report"] = score_data
                result["error"] = None
            else:
                scan.status = "failed"
                scan.error_message = error or "Baseline report was not ready in time"
                result["error"] = scan.error_message
        else:
            scan.status = "failed"
            scan.error_message = error
        scan.completed_at = scan.completed_at or datetime.now(timezone.utc)
        db.commit()

        return result

    @api.get("/local-visibility/scans")
    def list_local_visibility_scans(lead_source: str | None = None, db: Session = Depends(get_db)):
        """Flat list of individual LocalVisibilityScan rows (joined with
        their Business) -- backs the Local Visibility GHL Leads page and
        the Manual Scoring page's persisted history list. `lead_source`
        filters to one of "local_visibility_manual" / "local_visibility_ghl"
        / "local_visibility_csv"; omit for everything (used by the
        dashboard overview)."""
        query = db.query(m.LocalVisibilityScan).options(joinedload(m.LocalVisibilityScan.business))
        if lead_source:
            query = query.join(m.Business).filter(m.Business.lead_source == lead_source)
        scans = query.order_by(m.LocalVisibilityScan.created_at.desc()).all()
        return [_local_visibility_scan_brief(s) for s in scans]

    @api.get("/local-visibility/overview")
    def local_visibility_overview(db: Session = Depends(get_db)):
        """Summary stats for the Local Visibility Dashboard landing page:
        totals, average score, grade distribution, per-source counts, and
        the most recent scans across all three sources (manual/CSV/GHL)."""
        scans = (
            db.query(m.LocalVisibilityScan)
            .options(joinedload(m.LocalVisibilityScan.business))
            .order_by(m.LocalVisibilityScan.created_at.desc())
            .all()
        )
        completed = [s for s in scans if s.status == "completed" and s.overall_score is not None]
        by_source: dict[str, int] = {}
        for s in scans:
            src = (s.business.lead_source if s.business else None) or "unknown"
            by_source[src] = by_source.get(src, 0) + 1
        grade_counts: dict[str, int] = {}
        for s in completed:
            g = (s.overall_grade or "?")[:1].upper()
            grade_counts[g] = grade_counts.get(g, 0) + 1
        avg_score = round(sum(s.overall_score for s in completed) / len(completed), 1) if completed else None
        return {
            "total_scans": len(scans),
            "completed_scans": len(completed),
            "failed_scans": len([s for s in scans if s.status == "failed"]),
            "average_score": avg_score,
            "by_source": by_source,
            "grade_counts": grade_counts,
            "recent": [_local_visibility_scan_brief(s) for s in scans[:10]],
        }

    @api.get("/local-visibility/scans/{scan_id}/report")
    def get_local_visibility_scan_report(scan_id: str, db: Session = Depends(get_db)):
        """Returns the stored Advice Local baseline report blob for a scan
        (captured at completion time in LocalVisibilityScan.raw_scores) --
        backs the "View Report" button in the single-check result card.
        Kept separate from the /single response itself so a report can
        still be reloaded/re-viewed after a page refresh."""
        scan = db.get(m.LocalVisibilityScan, scan_id)
        if not scan:
            raise HTTPException(404, "Scan not found")
        report = json.loads(scan.raw_scores) if scan.raw_scores else None
        return {
            "scan_id": scan.id,
            "business_name": scan.business.name if scan.business else None,
            "overall_score": scan.overall_score,
            "overall_grade": scan.overall_grade,
            "status": scan.status,
            "report": report,
        }

    @api.post("/local-visibility/upload")
    async def local_visibility_upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
        """Accepts a lead-list CSV/Excel file, auto-detects the business
        name + address columns, and kicks off a background job that
        creates an Advice Local client per row and polls for its
        auto-generated baseline visibility score. Returns immediately
        with a job id to poll -- see _run_local_visibility_job for the
        actual processing. Mirrors /bulk-scoring/upload's shape exactly,
        just against a different external API and column set."""
        MAX_BULK_BYTES = 20 * 1024 * 1024
        contents = await file.read(MAX_BULK_BYTES + 1)
        if not contents:
            raise HTTPException(400, "Empty file")
        if len(contents) > MAX_BULK_BYTES:
            raise HTTPException(413, "File too large (max 20 MB)")

        fieldnames, rows = _parse_bulk_upload_file(contents, file.filename or "")
        if not fieldnames:
            raise HTTPException(400, "Could not read a header row from this file.")

        name_col = _find_column(fieldnames, NAME_HEADER_CANDIDATES)
        zip_col = _find_column(fieldnames, ZIP_HEADER_CANDIDATES)
        if not name_col or not zip_col:
            raise HTTPException(
                400,
                f"Could not find both a Business Name and a Zip Code column. Found columns: {', '.join(fieldnames)}. "
                "Please include columns named Business Name (or Company/Name) and Zip/Zip Code/Postal Code.",
            )
        cols = {
            "name": name_col,
            "street": _find_column(fieldnames, STREET_HEADER_CANDIDATES),
            "city": _find_column(fieldnames, CITY_HEADER_CANDIDATES),
            "state": _find_column(fieldnames, STATE_HEADER_CANDIDATES),
            "zip": zip_col,
            "phone": _find_column(fieldnames, PHONE_HEADER_CANDIDATES),
            "email": _find_column(fieldnames, EMAIL_HEADER_CANDIDATES),
            "first_name": _find_column(fieldnames, FIRST_NAME_HEADER_CANDIDATES),
            "last_name": _find_column(fieldnames, LAST_NAME_HEADER_CANDIDATES),
            "website": _find_column(fieldnames, WEBSITE_HEADER_CANDIDATES),
        }

        rows = [dict(r) for r in rows]
        if not rows:
            raise HTTPException(400, "No data rows found in this file.")

        job = m.BulkUploadJob(
            job_type="local_visibility",
            filename=file.filename or "upload.csv", status="running",
            total_rows=len(rows), processed_rows=0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        threading.Thread(
            target=_run_local_visibility_job,
            args=(job.id, fieldnames, rows, cols),
            daemon=True,
        ).start()

        return {"job_id": job.id, "status": "running", "total_rows": job.total_rows}

    @api.get("/local-visibility/jobs")
    def list_local_visibility_jobs(db: Session = Depends(get_db)):
        jobs = (
            db.query(m.BulkUploadJob)
            .filter(m.BulkUploadJob.job_type == "local_visibility")
            .order_by(m.BulkUploadJob.created_at.desc())
            .all()
        )
        return [_bulk_job_brief(j) for j in jobs]

    @api.get("/local-visibility/jobs/{job_id}")
    def get_local_visibility_job(job_id: str, db: Session = Depends(get_db)):
        job = db.get(m.BulkUploadJob, job_id)
        if not job or job.job_type != "local_visibility":
            raise HTTPException(404, "Job not found")
        return _bulk_job_brief(job)

    @api.get("/local-visibility/jobs/{job_id}/download")
    def download_local_visibility_job(job_id: str, db: Session = Depends(get_db)):
        job = db.get(m.BulkUploadJob, job_id)
        if not job or job.job_type != "local_visibility" or not job.result_csv:
            raise HTTPException(404, "Result not ready yet")
        filename = job.result_filename or "scored_leads.csv"
        return Response(
            content=bytes(job.result_csv),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @api.get("/local-visibility/jobs/{job_id}/results")
    def get_local_visibility_job_results(job_id: str, db: Session = Depends(get_db)):
        job = db.get(m.BulkUploadJob, job_id)
        if not job or job.job_type != "local_visibility":
            raise HTTPException(404, "Job not found")
        if not job.result_csv:
            return {"columns": [], "rows": []}
        text = bytes(job.result_csv).decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        columns = reader.fieldnames or []
        rows = [dict(r) for r in reader]
        return {"columns": columns, "rows": rows}

    # ---------------- Rank Checker (Serper.dev) ----------------

    @api.get("/rank-checker/settings")
    def get_rank_checker_settings(db: Session = Depends(get_db)):
        return {"default_keywords": _default_rank_check_keywords(db)}

    @api.put("/rank-checker/settings")
    def update_rank_checker_settings(payload: RankCheckSettingsUpdate, db: Session = Depends(get_db)):
        settings = db.query(m.RankCheckSettings).first()
        if not settings:
            settings = m.RankCheckSettings()
            db.add(settings)
        settings.default_keywords = ",".join(k.strip() for k in payload.default_keywords if k.strip())
        db.commit()
        return {"default_keywords": _default_rank_check_keywords(db)}

    @api.post("/rank-checker/single")
    def rank_checker_single(payload: RankCheckSingleRequest, db: Session = Depends(get_db)):
        """One-off check for the Rank Checker manual form. Creates a real
        Business + RankCheckScan (lead_source="rank_checker_manual", also
        excluded from the main dashboard list -- see list_businesses),
        runs synchronously since Serper is fast (a few seconds per
        keyword)."""
        business_name = payload.business_name.strip()
        website = payload.website.strip()
        if not business_name or not website:
            raise HTTPException(400, "Business name and website are required")
        keywords = [k.strip() for k in (payload.keywords or []) if k.strip()] or _default_rank_check_keywords(db)
        if not keywords:
            raise HTTPException(400, "At least one keyword is required (no default keyword template configured in Settings)")
        full_name = " ".join(p for p in [payload.first_name, payload.last_name] if p).strip()
        location_query = _location_query_from(payload.city, payload.state, payload.zip)

        biz = m.Business(
            name=business_name,
            location=location_query or None,
            contact_name=full_name or None,
            contact_email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            phone=payload.phone,
            lead_source="rank_checker_manual",
        )
        db.add(biz)
        db.flush()

        scan = m.RankCheckScan(
            business_id=biz.id, website=website, location_query=location_query, status="running",
        )
        db.add(scan)
        db.commit()
        db.refresh(scan)

        _run_keyword_checks(scan.id, business_name, website, location_query, keywords, city=payload.city, state=payload.state)

        db.refresh(scan)
        keyword_results = (
            db.query(m.RankCheckKeywordResult)
            .filter_by(scan_id=scan.id)
            .order_by(m.RankCheckKeywordResult.created_at)
            .all()
        )
        return {
            "business_id": biz.id,
            "scan_id": scan.id,
            "business_name": business_name,
            "website": website,
            "location_query": location_query,
            "status": scan.status,
            "error": scan.error_message,
            "keyword_results": [_keyword_result_brief(r) for r in keyword_results],
        }

    @api.get("/rank-checker/scans")
    def list_rank_check_scans(lead_source: str | None = None, db: Session = Depends(get_db)):
        """Flat list of RankCheckScan rows (joined with Business) --
        backs the Rank Checker GHL Leads page and the Manual Scoring
        page's persisted history list. `lead_source` filters to one of
        "rank_checker_manual" / "rank_checker_ghl" / "rank_checker_csv";
        omit for everything (used by the dashboard overview)."""
        query = db.query(m.RankCheckScan).options(
            joinedload(m.RankCheckScan.business), joinedload(m.RankCheckScan.keyword_results)
        )
        if lead_source:
            query = query.join(m.Business).filter(m.Business.lead_source == lead_source)
        scans = query.order_by(m.RankCheckScan.created_at.desc()).all()
        return [_rank_check_scan_brief(s) for s in scans]

    @api.get("/rank-checker/scans/{scan_id}")
    def get_rank_check_scan(scan_id: str, db: Session = Depends(get_db)):
        """Full scan detail including every keyword's result -- backs the
        "View Report" modal (reload-safe after a page refresh, same
        pattern as /local-visibility/scans/{id}/report)."""
        scan = db.get(m.RankCheckScan, scan_id)
        if not scan:
            raise HTTPException(404, "Scan not found")
        brief = _rank_check_scan_brief(scan)
        brief["keyword_results"] = [_keyword_result_brief(r) for r in scan.keyword_results]
        return brief

    @api.get("/rank-checker/overview")
    def rank_checker_overview(db: Session = Depends(get_db)):
        """Summary stats for the Rank Checker Dashboard landing page."""
        scans = (
            db.query(m.RankCheckScan)
            .options(joinedload(m.RankCheckScan.business), joinedload(m.RankCheckScan.keyword_results))
            .order_by(m.RankCheckScan.created_at.desc())
            .all()
        )
        completed = [s for s in scans if s.status == "completed"]
        by_source: dict[str, int] = {}
        for s in scans:
            src = (s.business.lead_source if s.business else None) or "unknown"
            by_source[src] = by_source.get(src, 0) + 1
        total_keywords = sum(len(s.keyword_results) for s in scans)
        organic_found = sum(1 for s in scans for r in s.keyword_results if r.organic_position)
        map_pack_found = sum(1 for s in scans for r in s.keyword_results if r.map_pack_found)
        return {
            "total_scans": len(scans),
            "completed_scans": len(completed),
            "failed_scans": len([s for s in scans if s.status == "failed"]),
            "total_keywords_checked": total_keywords,
            "organic_found_count": organic_found,
            "map_pack_found_count": map_pack_found,
            "by_source": by_source,
            "recent": [_rank_check_scan_brief(s) for s in scans[:10]],
        }

    @api.post("/rank-checker/upload")
    async def rank_checker_upload(
        file: UploadFile = File(...), keywords: str = "", db: Session = Depends(get_db),
    ):
        """Accepts a lead-list CSV/Excel file plus a `keywords` form field
        (comma-separated -- the keyword list to apply to every row in
        this upload, designated once for the whole list, per the user's
        spec), auto-detects the business name + website columns, and
        kicks off a background job. Mirrors /local-visibility/upload's
        shape exactly, just against Serper instead of Advice Local. Falls
        back to the default keyword template (Settings) if `keywords` is
        blank."""
        MAX_BULK_BYTES = 20 * 1024 * 1024
        contents = await file.read(MAX_BULK_BYTES + 1)
        if not contents:
            raise HTTPException(400, "Empty file")
        if len(contents) > MAX_BULK_BYTES:
            raise HTTPException(413, "File too large (max 20 MB)")

        kw_list = [k.strip() for k in (keywords or "").split(",") if k.strip()]
        if not kw_list:
            kw_list = _default_rank_check_keywords(db)
        if not kw_list:
            raise HTTPException(400, "No keywords provided and no default keyword template configured in Settings")

        fieldnames, rows = _parse_bulk_upload_file(contents, file.filename or "")
        if not fieldnames:
            raise HTTPException(400, "Could not read a header row from this file.")

        name_col = _find_column(fieldnames, NAME_HEADER_CANDIDATES)
        website_col = _find_column(fieldnames, WEBSITE_HEADER_CANDIDATES)
        if not name_col or not website_col:
            raise HTTPException(
                400,
                f"Could not find both a Business Name and a Website column. Found columns: {', '.join(fieldnames)}. "
                "Please include columns named Business Name (or Company/Name) and Website (or URL/Domain).",
            )
        cols = {
            "name": name_col,
            "website": website_col,
            "street": _find_column(fieldnames, STREET_HEADER_CANDIDATES),
            "city": _find_column(fieldnames, CITY_HEADER_CANDIDATES),
            "state": _find_column(fieldnames, STATE_HEADER_CANDIDATES),
            "zip": _find_column(fieldnames, ZIP_HEADER_CANDIDATES),
            "phone": _find_column(fieldnames, PHONE_HEADER_CANDIDATES),
            "email": _find_column(fieldnames, EMAIL_HEADER_CANDIDATES),
            "first_name": _find_column(fieldnames, FIRST_NAME_HEADER_CANDIDATES),
            "last_name": _find_column(fieldnames, LAST_NAME_HEADER_CANDIDATES),
        }

        rows = [dict(r) for r in rows]
        if not rows:
            raise HTTPException(400, "No data rows found in this file.")

        job = m.BulkUploadJob(
            job_type="rank_checker",
            filename=file.filename or "upload.csv", status="running",
            total_rows=len(rows), processed_rows=0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        threading.Thread(
            target=_run_rank_check_job,
            args=(job.id, fieldnames, rows, cols, kw_list),
            daemon=True,
        ).start()

        return {"job_id": job.id, "status": "running", "total_rows": job.total_rows, "keywords": kw_list}

    @api.get("/rank-checker/jobs")
    def list_rank_checker_jobs(db: Session = Depends(get_db)):
        jobs = (
            db.query(m.BulkUploadJob)
            .filter(m.BulkUploadJob.job_type == "rank_checker")
            .order_by(m.BulkUploadJob.created_at.desc())
            .all()
        )
        return [_bulk_job_brief(j) for j in jobs]

    @api.get("/rank-checker/jobs/{job_id}")
    def get_rank_checker_job(job_id: str, db: Session = Depends(get_db)):
        job = db.get(m.BulkUploadJob, job_id)
        if not job or job.job_type != "rank_checker":
            raise HTTPException(404, "Job not found")
        return _bulk_job_brief(job)

    @api.get("/rank-checker/jobs/{job_id}/download")
    def download_rank_checker_job(job_id: str, db: Session = Depends(get_db)):
        job = db.get(m.BulkUploadJob, job_id)
        if not job or job.job_type != "rank_checker" or not job.result_csv:
            raise HTTPException(404, "Result not ready yet")
        filename = job.result_filename or "ranked_leads.csv"
        return Response(
            content=bytes(job.result_csv),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @api.get("/rank-checker/jobs/{job_id}/results")
    def get_rank_checker_job_results(job_id: str, db: Session = Depends(get_db)):
        job = db.get(m.BulkUploadJob, job_id)
        if not job or job.job_type != "rank_checker":
            raise HTTPException(404, "Job not found")
        if not job.result_csv:
            return {"columns": [], "rows": []}
        text = bytes(job.result_csv).decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        columns = reader.fieldnames or []
        rows = [dict(r) for r in reader]
        return {"columns": columns, "rows": rows}

    # ---------------- App wiring ----------------

    app = FastAPI(title="Website Visibility Audit")
    app.include_router(api, prefix="/api")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        css_hash = get_file_hash(os.path.join(static_dir, "styles.css"))
        js_hash = get_file_hash(os.path.join(static_dir, "app.js"))
        view_hashes = {
            name: get_file_hash(os.path.join(static_dir, "js", *name.split("/")))
            for name in [
                "api.js", "ui.js",
                "views/dashboard.js", "views/create.js", "views/business.js",
                "views/audit.js", "views/report.js", "views/settings.js",
                "views/ghl-leads.js", "views/bulk-scoring.js", "views/local-visibility.js",
                "views/local-visibility-ghl-leads.js", "views/local-visibility-bulk.js",
                "views/local-visibility-manual.js",
                "views/rank-checker.js", "views/rank-checker-ghl-leads.js",
                "views/rank-checker-bulk.js", "views/rank-checker-manual.js",
            ]
        }
        return templates.TemplateResponse(
            request, "index.html", {"css_hash": css_hash, "js_hash": js_hash, "view_hashes": view_hashes}
        )

    @app.get("/robots.txt", include_in_schema=False)
    def robots():
        return FileResponse(os.path.join(static_dir, "robots.txt"))

    @app.get("/widget", response_class=HTMLResponse, include_in_schema=False)
    def widget_page(request: Request):
        widget_js_hash = get_file_hash(os.path.join(static_dir, "widget.js"))
        widget_css_hash = get_file_hash(os.path.join(static_dir, "widget.css"))
        return templates.TemplateResponse(
            request, "widget.html", {"widget_js_hash": widget_js_hash, "widget_css_hash": widget_css_hash}
        )

    app.mount("/static", StaticFiles(directory=static_dir), name="ui")
    return app
