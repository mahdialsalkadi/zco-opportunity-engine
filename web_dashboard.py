#!/usr/bin/env python3
"""
ZCO Hunter - Modern Web Dashboard & Real-Time Control Center
Author: Mohammad Mahdi Alsalkadi & Antigravity AI
Version: 5.2.0

Provides a full-featured, responsive web interface for:
- Browsing verified 100% zero-cost opportunities categorized by:
  (Volunteering, Beach Cleanup, Kids Education, Eco-Camps, AI Hackathons, Scholarships).
- 1-Click Opportunity-Tailored Custom CV PDF generation & download.
- 1-Click Tailored Motivation Letter (Statement of Purpose) preview & copy.
- Interactive Approval & Application submission.
- Real-time Candidate Portfolio & Vault management.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hmac
import json
import logging
import os
import pathlib
import secrets
import sys
import urllib.parse
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
import uvicorn

from coverage_utils import coverage_summary
from file_utils import atomic_write_text
from paths import DASHBOARD_TOKEN_FILE as PATH_DASHBOARD_TOKEN_FILE
from paths import DB_PATH

BASE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Load environment configuration
def _load_local_env() -> None:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass

_load_local_env()

DASHBOARD_TOKEN_FILE = PATH_DASHBOARD_TOKEN_FILE
AUTH_COOKIE_NAME = "zco_dashboard_token"


def _load_or_create_dashboard_token() -> tuple[str, str]:
    """Return (token, source). Always yields a non-empty token."""
    env_token = os.environ.get("DASHBOARD_AUTH_TOKEN", "").strip()
    if env_token:
        return env_token, "env"
    try:
        if DASHBOARD_TOKEN_FILE.exists():
            stored = DASHBOARD_TOKEN_FILE.read_text(encoding="utf-8").strip()
            if len(stored) >= 24:
                return stored, "file"
        token = secrets.token_urlsafe(32)
        atomic_write_text(DASHBOARD_TOKEN_FILE, token + "\n", mode=0o600)
        return token, "generated"
    except OSError:
        # Last resort: ephemeral token, printed once below.
        return secrets.token_urlsafe(32), "ephemeral"


DASHBOARD_AUTH_TOKEN, DASHBOARD_TOKEN_SOURCE = _load_or_create_dashboard_token()

from database import OpportunityDatabase, OpportunityStatus
from engines_and_auditor import AutonomousApplicantEngine, CandidateMemoryVault
from portfolio_and_docs_engine import (
    CV_PDF_FILE,
    PortfolioManager,
    get_opportunity_arabic_explanation,
    normalize_profile_updates,
)
from server import ZCOEngineController
from typst_agentic_cv_engine import (
    is_cv_required_for_opportunity,
    synthesize_tailored_typst_cv,
    synthesize_base_reference_typst_cv,
)

logger = logging.getLogger("ZCO-WebDashboard")

app = FastAPI(title="ZCO-Hunter Web Dashboard", version="5.2.0")

AUTH_GATE_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZCO-Hunter | دخول لوحة التحكم</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px;
    font-family: "Segoe UI", Tahoma, system-ui, sans-serif; color: #e2e8f0;
    background:
      radial-gradient(1000px 600px at 80% -10%, rgba(37, 99, 235, .28), transparent 60%),
      radial-gradient(800px 500px at 0% 110%, rgba(16, 185, 129, .16), transparent 60%),
      #070b14;
  }
  .gate {
    width: 100%; max-width: 440px; padding: 32px; border-radius: 24px;
    background: rgba(15, 23, 42, .82); border: 1px solid rgba(148, 163, 184, .16);
    box-shadow: 0 24px 80px -24px rgba(0, 0, 0, .8); backdrop-filter: blur(16px);
  }
  .mark {
    width: 52px; height: 52px; border-radius: 16px; display: grid; place-items: center;
    font-size: 24px; margin-bottom: 18px;
    background: linear-gradient(135deg, #2563eb, #4f46e5);
    box-shadow: 0 10px 30px -10px rgba(37, 99, 235, .8);
  }
  h1 { margin: 0 0 6px; font-size: 22px; letter-spacing: -.02em; }
  p { margin: 0 0 20px; color: #94a3b8; font-size: 13px; line-height: 1.8; }
  label { display: block; margin-bottom: 6px; font-size: 12px; font-weight: 700; color: #cbd5e1; }
  input {
    width: 100%; padding: 12px 14px; border-radius: 12px; font-size: 14px;
    border: 1px solid rgba(148, 163, 184, .22); background: #0b1220; color: #e2e8f0;
    direction: ltr; text-align: left; outline: none;
  }
  input:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59, 130, 246, .2); }
  button {
    width: 100%; margin-top: 12px; padding: 12px 16px; border: 0; border-radius: 12px;
    cursor: pointer; font-size: 14px; font-weight: 800; color: #fff;
    background: linear-gradient(135deg, #2563eb, #4f46e5);
  }
  button:hover { filter: brightness(1.08); }
  .hint { margin: 18px 0 0; font-size: 11px; color: #64748b; line-height: 1.9; }
  code {
    direction: ltr; unicode-bidi: plaintext; display: inline-block; padding: 1px 6px;
    border-radius: 6px; font-size: 11px; color: #93c5fd;
    background: #0b1220; border: 1px solid rgba(148, 163, 184, .14);
  }
  .error { display: none; margin-top: 10px; font-size: 12px; color: #fca5a5; }
</style>
</head>
<body>
<main class="gate">
  <div class="mark">🔒</div>
  <h1>لوحة تحكم ZCO-Hunter</h1>
  <p>هذه اللوحة محمية. الصق توكن الوصول للمتابعة إلى لوحة الفرص والتقديم الآلي.</p>
  <form onsubmit="event.preventDefault(); const t=document.getElementById('token').value.trim(); if(!t){document.getElementById('err').style.display='block'; return;} window.location.href='/?token='+encodeURIComponent(t);">
    <label for="token">Dashboard Token</label>
    <input id="token" type="password" placeholder="الصق التوكن هنا" autocomplete="current-password" autofocus>
    <div class="error" id="err">أدخل التوكن أولاً.</div>
    <button type="submit">دخول آمن</button>
  </form>
  <p class="hint">التوكن موجود في <code>data/dashboard_token.txt</code> أو متغير <code>DASHBOARD_AUTH_TOKEN</code>.</p>
</main>
</body>
</html>"""

PUBLIC_PATHS = {"/favicon.ico", "/healthz"}


@app.middleware("http")
async def security_token_middleware(request: Request, call_next):
    path = request.url.path

    if path in PUBLIC_PATHS:
        return await call_next(request)

    # Origin check for browser mutations (same-origin only; API clients omit Origin).
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin:
            parsed_origin = urllib.parse.urlparse(origin)
            if parsed_origin.netloc != request.headers.get("host", ""):
                return JSONResponse(
                    {"status": "error", "message": "Cross-origin mutation denied."},
                    status_code=403,
                )

    supplied = (
        request.headers.get("X-Dashboard-Token")
        or request.query_params.get("token")
        or request.cookies.get(AUTH_COOKIE_NAME)
        or ""
    )
    if not hmac.compare_digest(str(supplied), DASHBOARD_AUTH_TOKEN):
        if path == "/" or request.headers.get("accept", "").startswith("text/html"):
            return HTMLResponse(AUTH_GATE_HTML, status_code=401)
        return JSONResponse(
            {"status": "error", "message": "Unauthorized. Provide a valid session cookie or X-Dashboard-Token header."},
            status_code=401,
        )

    response: Response = await call_next(request)
    if request.query_params.get("token") == DASHBOARD_AUTH_TOKEN:
        response.set_cookie(
            AUTH_COOKIE_NAME,
            DASHBOARD_AUTH_TOKEN,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=60 * 60 * 12,
        )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response

db = OpportunityDatabase(DB_PATH)
vault = CandidateMemoryVault(db)
applicant = AutonomousApplicantEngine(db, vault)
controller = ZCOEngineController(db_path=DB_PATH)
pm = PortfolioManager()


def _parse_json_object(raw: Any) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


class ProfileUpdateRequest(BaseModel):
    full_name_en: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=254)
    phone_my: Optional[str] = Field(default=None, max_length=30)
    passport_number: Optional[str] = Field(default=None, max_length=20)
    address_my: Optional[str] = Field(default=None, max_length=300)
    activity_preferences: Optional[str] = Field(default=None, max_length=400)
    location_preference: Optional[str] = Field(default=None, max_length=30)
    availability_from: Optional[str] = Field(default=None, max_length=10)
    availability_to: Optional[str] = Field(default=None, max_length=10)
    cgpa: Optional[str] = Field(default=None, max_length=20)
    matric_number: Optional[str] = Field(default=None, max_length=30)
    github_url: Optional[str] = Field(default=None, max_length=300)


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {"status": "ok", "service": "zco-dashboard"}


@app.get("/api/status")
async def get_system_status() -> Dict[str, Any]:
    summary = controller.get_crawler_daemon_status()
    subscribers = db.get_telegram_subscribers()
    return {
        "status": "online",
        "total_tracked": summary.get("total_tracked", 0),
        "queue_counts": summary.get("queue_counts", {}),
        "telegram_subscribers_count": len(subscribers),
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


@app.get("/api/opportunities")
async def get_opportunities(
    category: Optional[str] = None,
    location: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    raw_opps = db.get_verified_opportunities()
    
    # Deduplicate by normalized title, strictly prioritizing canonical official URLs over aggregator posts
    from collections import defaultdict
    aggregator_domains = [
        "opportunitydesk.org",
        "opportunitiescorners.com",
        "oyaop.com",
        "scholarshiproar.com",
        "opportunitiesforafricans.com",
        "scholars4dev.com",
        "youthop.com",
        "armacad.info",
    ]

    def score_opp(opp):
        s = 0
        u = (opp.get("apply_url") or "").lower()
        if u and not any(agg in u for agg in aggregator_domains):
            s += 100
        st = opp.get("status", "")
        status_priority = {
            "APPLIED_AUTOMATICALLY": 80,
            "SUBMITTED_UNCONFIRMED": 70,
            "READY_FOR_REVIEW": 60,
            "PAUSED_NEEDS_USER_INPUT": 55,
            "PAUSED_AT_CAPTCHA": 55,
            "VERIFIED_ELIGIBLE": 50,
        }
        s += status_priority.get(st, 0)
        s += opp.get("id", 0)
        return s

    by_title = defaultdict(list)
    for opp in raw_opps:
        norm_title = opp["title"].strip().lower()
        by_title[norm_title].append(opp)

    unique_opps = []
    for norm_title, group in by_title.items():
        group.sort(key=score_opp, reverse=True)
        best = group[0]
        u = best.get("apply_url") or ""
        if any(agg in u.lower() for agg in aggregator_domains):
            src = best.get("source_url") or ""
            if src and not any(agg in src.lower() for agg in aggregator_domains):
                best["apply_url"] = src
        unique_opps.append(best)

    results = []
    for o in unique_opps:
        code = o.get("opportunity_code") or f"ID-{o['id']}"
        title = o.get("title", "")
        organizer = o.get("organizer", "")
        city = o.get("location_city", "")
        country = o.get("location_country", "")
        is_my = bool(o.get("is_inside_malaysia", 0))
        track = o.get("track_category", "GENERAL")
        opp_status = o.get("status", "")
        score = o.get("match_score", 92)
        deadline = o.get("deadline_iso", "")
        apply_url = o.get("apply_url", "")
        if apply_url.startswith("file://"):
            apply_url = o.get("source_url", "https://www.frim.gov.my/")

        cov = _parse_json_object(o.get("financial_coverage_json"))
        cov_summary, cov_known = coverage_summary(cov)

        # Determine broad human category
        title_upper = title.upper()
        track_upper = track.upper()

        if any(k in title_upper or k in track_upper for k in ["CLEANUP", "BEACH", "TURTLE", "COMMUNITY", "SOLS 24/7", "UN VOLUNTEERS", "UNV", "CHILD"]):
            category_tag = "VOLUNTEERING"
            category_label_ar = "🌊 تطوع وخدمة مجتمع وتنظيف شواطئ"
        elif any(k in title_upper or k in track_upper for k in ["SCHOLARSHIP", "FELLOWSHIP", "RESEARCH", "AMGEN", "CALTECH", "HARVARD", "LAB", "GOVAI", "MASTERCARD"]):
            category_tag = "SCHOLARSHIPS"
            category_label_ar = "🎓 منح دراسية وتدريب بحثي"
        elif any(k in title_upper or k in track_upper for k in ["HACKATHON", "GREEN-AI", "COMPUTING", "SOFTWARE"]):
            category_tag = "AI_TECH"
            category_label_ar = "🤖 ذكاء اصطناعي وهاكاثونات"
        elif any(k in title_upper or k in track_upper for k in ["CAMP", "ECO", "NATURE", "FOREST", "FRIM", "WILDLIFE", "PARKS", "SUMMIT"]):
            category_tag = "CAMPS"
            category_label_ar = "🏕 مخيمات ومعسكرات بيئية"
        else:
            category_tag = "GENERAL"
            category_label_ar = "🌟 برامج عامة"

        explanation_ar = get_opportunity_arabic_explanation(o)
        cv_req, cv_reason = is_cv_required_for_opportunity(o)

        # Filters
        if category and category != "ALL" and category_tag != category:
            continue
        if location == "MALAYSIA" and not is_my:
            continue
        if location == "INTERNATIONAL" and is_my:
            continue
        if status and status != "ALL":
            if status == "READY_FOR_REVIEW" and opp_status != "READY_FOR_REVIEW":
                continue
            elif status == "APPLICATION_FAILED" and opp_status != "APPLICATION_FAILED":
                continue
            elif status not in ["READY_FOR_REVIEW", "APPLICATION_FAILED"] and opp_status != status:
                continue
        if search:
            search_lower = search.lower()
            if not (search_lower in title.lower() or search_lower in organizer.lower() or search_lower in city.lower() or search_lower in country.lower() or search_lower in explanation_ar.lower()):
                continue

        results.append({
            "opportunity_code": code,
            "title": title,
            "organizer": organizer,
            "location_city": city,
            "location_country": country,
            "is_inside_malaysia": is_my,
            "category_tag": category_tag,
            "category_label_ar": category_label_ar,
            "track_category": track,
            "match_score": score,
            "status": opp_status,
            "deadline_iso": deadline,
            "program_start_iso": o.get("program_start_iso", ""),
            "program_end_iso": o.get("program_end_iso", ""),
            "apply_url": apply_url,
            "source_type": o.get("source_type", "unknown"),
            "source_confidence": o.get("source_confidence", 0),
            "deadline_confidence": o.get("deadline_confidence", 0),
            "financial_coverage_ar": cov_summary,
            "coverage_known": cov_known,
            "explanation_ar": explanation_ar,
            "cv_required": cv_req,
            "cv_requirement_reason": cv_reason,
            "custom_cv_url": f"/api/opportunities/{code}/cv",
            "kit_url": f"/api/opportunities/{code}/kit",
        })

    return {
        "count": len(results),
        "opportunities": results,
    }


@app.get("/api/opportunities/{code}/cv")
async def download_tailored_cv(code: str):
    opp = db.get_opportunity_by_code(code)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity code not found")
    
    cv_req, cv_reason = is_cv_required_for_opportunity(opp)
    if not cv_req:
        raise HTTPException(
            status_code=400,
            detail=f"السيرة الذاتية غير مطلوبة في هذه الفرصة ({cv_reason}). تطبيقاً للقاعدة الصارمة: لا يتم التوليد إلا للفرص التي تشترط السيرة صراحة."
        )

    try:
        res = await run_in_threadpool(synthesize_tailored_typst_cv, opp)
        if res.get("status") == "generated" and res.get("pdf_path") and os.path.exists(res["pdf_path"]):
            return FileResponse(
                path=res["pdf_path"],
                filename=f"CV_Mohammad_Alsalkadi_{code}_Typst.pdf",
                media_type="application/pdf",
            )
        else:
            raise RuntimeError(f"Typst generation status: {res.get('status')}")
    except Exception as e:
        logger.error("Failed to render custom Typst CV for %s: %s", code, e)
        # Fallback to PortfolioManager if needed
        try:
            pdf_path = await run_in_threadpool(pm.render_custom_cv_for_opportunity, opp)
            return FileResponse(
                path=str(pdf_path),
                filename=f"CV_Mohammad_Alsalkadi_{code}.pdf",
                media_type="application/pdf",
            )
        except Exception as inner_e:
            raise HTTPException(status_code=500, detail=str(inner_e))


@app.get("/api/cv/base")
async def download_base_cv():
    try:
        res = await run_in_threadpool(synthesize_base_reference_typst_cv, force_recompile=False)
        if res.get("pdf_path") and os.path.exists(res["pdf_path"]):
            return FileResponse(
                path=res["pdf_path"],
                filename="CV_Mohammad_Mahdi_Alsalkadi_Reference.pdf",
                media_type="application/pdf",
            )
        pdf_path = await run_in_threadpool(pm.render_cv_pdf)
        return FileResponse(
            path=str(pdf_path),
            filename="CV_Mohammad_Mahdi_Alsalkadi_Base.pdf",
            media_type="application/pdf",
        )
    except Exception as e:
        logger.error("Failed to render base reference CV: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/opportunities/{code}/kit")
async def get_opportunity_kit(code: str) -> Dict[str, Any]:
    opp = db.get_opportunity_by_code(code)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity code not found")

    essay = await run_in_threadpool(pm.synthesize_tailored_motivation_letter, opp)
    cov = _parse_json_object(opp.get("financial_coverage_json"))
    cov_summary, cov_known = coverage_summary(cov)
    cov["coverage_summary_ar"] = cov_summary
    cv_req, cv_reason = is_cv_required_for_opportunity(opp)

    return {
        "opportunity_code": code,
        "title": opp.get("title", ""),
        "organizer": opp.get("organizer", ""),
        "financial_coverage": cov,
        "coverage_known": cov_known,
        "tailored_motivation_letter": essay,
        "cv_required": cv_req,
        "cv_requirement_reason": cv_reason,
        "applicant": pm.data.get("personal", {}),
        "academic": pm.data.get("education", {}),
    }


@app.post("/api/opportunities/{code}/approve")
async def approve_opportunity(code: str) -> Dict[str, Any]:
    opp = db.get_opportunity_by_code(code)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity code not found")

    cv_req, cv_reason = is_cv_required_for_opportunity(opp)
    tailored_cv_info = None

    if cv_req:
        # Human approval path: synthesize the tailored Typst CV before submitting.
        cv_res = await run_in_threadpool(synthesize_tailored_typst_cv, opp)
        if cv_res.get("status") == "generated" and cv_res.get("pdf_path"):
            known = vault.get_known_fields()
            known["cv_pdf_path"] = str(cv_res["pdf_path"])
            tailored_cv_info = {
                "generated": True,
                "pdf_filename": cv_res["pdf_filename"],
                "domain_focus": cv_res["domain_focus"],
                "ats_score": cv_res["ats_score"],
            }
        else:
            return {
                "status": "failed",
                "opportunity_code": code,
                "cv_tailored_info": cv_res,
                "message": "تعذر توليد السيرة الذاتية المطلوبة؛ لم يتم تقديم الطلب.",
            }
    else:
        # Opportunity does not require CV -> clear it from the payload.
        tailored_cv_info = {"generated": False, "reason": cv_reason}

    # Explicit user approval via dashboard: Submit is allowed for this one request.
    res = await run_in_threadpool(
        applicant.attempt_auto_application, opp, True
    )
    return {
        "status": res.get("application_status", "unknown"),
        "opportunity_code": code,
        "cv_tailored_info": tailored_cv_info,
        "result": res,
    }


@app.post("/api/opportunities/{code}/decline")
async def decline_opportunity(code: str) -> Dict[str, Any]:
    opp = db.get_opportunity_by_code(code)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity code not found")

    db.update_opportunity_status(
        opportunity_code=code,
        new_status=OpportunityStatus.DECLINED_BY_USER,
        rejection_reason="Declined by user via Web Dashboard",
    )
    return {
        "status": "success",
        "message": f"Opportunity {code} declined and archived.",
    }


@app.get("/api/profile")
async def get_candidate_profile() -> Dict[str, Any]:
    return pm.data


def _apply_profile_update(values: Dict[str, str], clear_keys: set[str]) -> Dict[str, Any]:
    pm.update_profile(values)
    with db.connect() as conn:
        pm.sync_to_sqlite_vault(conn, clear_keys=clear_keys)
    return dict(pm.data)


@app.post("/api/profile")
async def update_candidate_profile(req: ProfileUpdateRequest) -> Dict[str, Any]:
    supplied = {
        field: getattr(req, field)
        for field in req.model_fields_set
        if getattr(req, field) is not None
    }
    cleaned, errors = normalize_profile_updates(supplied)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    clear_keys = pm.vault_keys_to_clear(cleaned)
    updated = await run_in_threadpool(_apply_profile_update, cleaned, clear_keys)

    return {
        "status": "success",
        "message": "Candidate profile updated and synchronized with vault.",
        "profile": updated,
    }


@app.post("/api/crawl")
async def trigger_crawl_cycle(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    from async_crawler import AsyncOpportunityCrawler

    async def _run():
        crawler = AsyncOpportunityCrawler(db=db)
        await crawler.run_single_cycle(include_curated_seed=False)
        controller.run_six_hour_batch_audit(window_hours=24.0, auto_apply=False)

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Crawler cycle initiated in background."}


@app.post("/api/audit")
async def trigger_audit_cycle() -> Dict[str, Any]:
    res = await run_in_threadpool(
        controller.run_six_hour_batch_audit,
        window_hours=48.0,
        auto_apply=False,
    )
    return res


# =============================================================================
# Dashboard HTML Template
# =============================================================================

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#060a13">
    <meta name="description" content="ZCO-Hunter — منصة مراجعة الفرص المجانية والتقديم الآلي لمحمد مهدي السلقدي">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎯</text></svg>">
    <title>ZCO-Hunter | منصة صيد الفرص الذكية والتقديم الآلي</title>
    <!-- Tailwind CSS & FontAwesome -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

    <style>
        :root {
            --bg: #060a13;
            --panel: rgba(13, 21, 38, 0.82);
            --line: rgba(148, 163, 184, 0.14);
            --accent: #3b82f6;
        }
        * {
            font-family: 'Cairo', 'Inter', -apple-system, sans-serif;
        }
        html { scroll-behavior: smooth; }
        body {
            background-color: var(--bg);
            color: #e2e8f0;
            background-image:
                radial-gradient(900px 500px at 85% -10%, rgba(37, 99, 235, 0.18), transparent 60%),
                radial-gradient(700px 420px at 0% 100%, rgba(16, 185, 129, 0.10), transparent 60%);
            background-attachment: fixed;
        }
        ::selection { background: #2563eb; color: #fff; }
        .glass-header { background: rgba(6, 10, 19, 0.82); backdrop-filter: blur(16px); }
        .card-glow {
            transition: transform .22s ease, box-shadow .22s ease, border-color .22s ease;
        }
        .card-glow:hover {
            transform: translateY(-4px);
            box-shadow: 0 22px 45px -20px rgba(37, 99, 235, .55);
            border-color: rgba(59, 130, 246, .32);
        }
        .opp-card { position: relative; overflow: hidden; }
        .opp-card::before {
            content: ""; position: absolute; inset: 0 0 auto 0; height: 2px;
            background: linear-gradient(90deg, transparent, rgba(59,130,246,.9), rgba(99,102,241,.6), transparent);
            opacity: .75;
        }
        .kpi-card {
            position: relative; overflow: hidden;
            transition: transform .2s ease, border-color .2s ease, background .2s ease;
        }
        .kpi-card:hover {
            transform: translateY(-2px);
            border-color: rgba(59, 130, 246, .28);
            background: rgba(17, 28, 49, .9);
        }
        .kpi-card::after {
            content: ""; position: absolute; inset: auto 0 0 0; height: 1px;
            background: linear-gradient(90deg, transparent, rgba(59,130,246,.35), transparent);
        }
        .tab-btn { border: 1px solid transparent; white-space: nowrap; }
        .tab-btn.active {
            background: linear-gradient(135deg, #2563eb, #4f46e5);
            color: #fff; font-weight: 700; border-color: rgba(96, 165, 250, .45);
            box-shadow: 0 8px 22px -10px rgba(37, 99, 235, .9);
        }
        input, select, textarea {
            transition: border-color .15s ease, box-shadow .15s ease, background .15s ease;
        }
        input:focus, select:focus, textarea:focus {
            outline: none !important;
            border-color: #3b82f6 !important;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, .18);
        }
        button, a { -webkit-tap-highlight-color: transparent; }
        button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible {
            outline: 2px solid #60a5fa; outline-offset: 2px;
        }
        .modal-panel { animation: modalIn .18s ease-out; }
        @keyframes modalIn {
            from { opacity: 0; transform: translateY(10px) scale(.985); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }
        .timeline-chip { min-width: 0; }
        .timeline-chip .value { overflow-wrap: anywhere; }
        body.modal-open { overflow: hidden; }
        .skeleton {
            position: relative; overflow: hidden; min-height: 300px;
            background: #0d1526; border: 1px solid rgba(148, 163, 184, .08);
            border-radius: 24px;
        }
        .skeleton::after {
            content: ""; position: absolute; inset: 0; transform: translateX(-100%);
            background: linear-gradient(90deg, transparent, rgba(148,163,184,.08), transparent);
            animation: shimmer 1.4s infinite;
        }
        @keyframes shimmer { 100% { transform: translateX(100%); } }
        .toast { animation: toastIn .2s ease-out; }
        @keyframes toastIn {
            from { opacity: 0; transform: translateY(-8px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .urgency-soon { color: #fbbf24; }
        .urgency-expired { color: #f87171; }
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        ::-webkit-scrollbar { width: 9px; height: 9px; }
        ::-webkit-scrollbar-track { background: #0b1220; }
        ::-webkit-scrollbar-thumb {
            background: #334155; border-radius: 999px; border: 2px solid #0b1220;
        }
        ::-webkit-scrollbar-thumb:hover { background: #475569; }
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { animation: none !important; transition: none !important; }
        }
    </style>
</head>
<body class="min-h-screen flex flex-col">

    <!-- Top Navigation Bar -->
    <header class="glass-header border-b border-white/5 sticky top-0 z-40">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-wrap items-center justify-between gap-4">
            <div class="flex items-center space-x-3 space-x-reverse">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-md">
                    <i class="fa-solid fa-radar text-white text-xl"></i>
                </div>
                <div>
                    <h1 class="text-xl font-extrabold text-white tracking-wide">ZCO-Hunter</h1>
                    <p class="text-xs text-blue-400 font-semibold">منصة صيد الفرص الذكية والتقديم الآلي 100% مجاناً</p>
                </div>
            </div>

            <!-- Candidate Identity Pill -->
            <div class="hidden sm:flex items-center space-x-3 space-x-reverse bg-gray-800/80 px-4 py-2 rounded-xl border border-gray-700/80">
                <div class="w-8 h-8 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center font-bold">
                    <i class="fa-solid fa-user-graduate"></i>
                </div>
                <div class="text-xs">
                    <div class="font-bold text-gray-200" id="header-name">محمد مهدي السلقدي</div>
                    <div class="text-gray-400">UTM Year 1 AI Honours | CGPA: <span class="text-emerald-400 font-semibold" id="header-cgpa">3.53</span></div>
                </div>
            </div>

            <!-- Action Toolbar -->
            <div class="flex items-center space-x-2 space-x-reverse">
                <a href="/api/cv/base" target="_blank" class="px-3 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-lg text-xs font-bold flex items-center space-x-1.5 space-x-reverse shadow transition">
                    <i class="fa-solid fa-file-invoice"></i>
                    <span>السيرة المرجعية (Reference CV)</span>
                </a>
                <button onclick="openProfileModal()" class="px-3 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-200 rounded-lg text-xs font-semibold flex items-center space-x-1 space-x-reverse transition">
                    <i class="fa-solid fa-id-card"></i>
                    <span>ملفي الشخصي</span>
                </button>
                <button onclick="triggerAudit()" id="btn-audit" class="px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold flex items-center space-x-1 space-x-reverse transition">
                    <i class="fa-solid fa-bolt"></i>
                    <span>تدقيق فوري</span>
                </button>
                <button onclick="triggerCrawl()" id="btn-crawl" class="px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold flex items-center space-x-1 space-x-reverse transition">
                    <i class="fa-solid fa-globe"></i>
                    <span>زحف الويب</span>
                </button>
            </div>
        </div>
    </header>

    <!-- Main Content Container -->
    <main class="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6">

        <!-- KPI Summary Cards -->
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
            <div class="kpi-card bg-gray-900/80 border border-gray-800 p-4 rounded-2xl">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-gray-400 text-[11px] font-semibold">إجمالي الفرص المفحوصة</span>
                    <i class="fa-solid fa-list-check text-blue-400/80 text-xs"></i>
                </div>
                <div class="text-2xl font-black text-white" id="stat-total" aria-live="polite">--</div>
            </div>
            <div class="kpi-card bg-gray-900/80 border border-gray-800 p-4 rounded-2xl">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-emerald-400 text-[11px] font-semibold">فرص مؤهلة 100% مجانية</span>
                    <i class="fa-solid fa-circle-check text-emerald-400/80 text-xs"></i>
                </div>
                <div class="text-2xl font-black text-emerald-400" id="stat-verified" aria-live="polite">--</div>
            </div>
            <div class="kpi-card bg-gray-900/80 border border-gray-800 p-4 rounded-2xl">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-cyan-400 text-[11px] font-semibold">تطوع وتنظيف شواطئ</span>
                    <i class="fa-solid fa-hand-holding-heart text-cyan-400/80 text-xs"></i>
                </div>
                <div class="text-2xl font-black text-cyan-400" id="stat-vol" aria-live="polite">--</div>
            </div>
            <div class="kpi-card bg-gray-900/80 border border-gray-800 p-4 rounded-2xl">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-amber-400 text-[11px] font-semibold">مخيمات بيئية وغابات</span>
                    <i class="fa-solid fa-tree text-amber-400/80 text-xs"></i>
                </div>
                <div class="text-2xl font-black text-amber-400" id="stat-camps" aria-live="polite">--</div>
            </div>
            <div class="kpi-card bg-gray-900/80 border border-gray-800 p-4 rounded-2xl">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-purple-400 text-[11px] font-semibold">منح وبحث وذكاء اصطناعي</span>
                    <i class="fa-solid fa-brain text-purple-400/80 text-xs"></i>
                </div>
                <div class="text-2xl font-black text-purple-400" id="stat-ai" aria-live="polite">--</div>
            </div>
        </div>

        <!-- Filter Tabs & Controls -->
        <div class="bg-gray-900/80 border border-gray-800/80 p-4 rounded-2xl mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
            
            <!-- Category Tabs -->
            <div class="flex flex-wrap gap-2" id="category-tabs">
                <button onclick="setCategory('ALL')" class="tab-btn active px-4 py-2 rounded-xl text-xs font-semibold bg-gray-800 text-gray-300 hover:bg-gray-700 transition" data-cat="ALL">
                    🌟 الكل (All)
                </button>
                <button onclick="setCategory('VOLUNTEERING')" class="tab-btn px-4 py-2 rounded-xl text-xs font-semibold bg-gray-800 text-gray-300 hover:bg-gray-700 transition" data-cat="VOLUNTEERING">
                    🌊 تطوع وتنظيف شواطئ وتعليم أطفال
                </button>
                <button onclick="setCategory('CAMPS')" class="tab-btn px-4 py-2 rounded-xl text-xs font-semibold bg-gray-800 text-gray-300 hover:bg-gray-700 transition" data-cat="CAMPS">
                    🏕 مخيمات ومعسكرات بيئية
                </button>
                <button onclick="setCategory('AI_TECH')" class="tab-btn px-4 py-2 rounded-xl text-xs font-semibold bg-gray-800 text-gray-300 hover:bg-gray-700 transition" data-cat="AI_TECH">
                    🤖 ذكاء اصطناعي وهاكاثونات
                </button>
                <button onclick="setCategory('SCHOLARSHIPS')" class="tab-btn px-4 py-2 rounded-xl text-xs font-semibold bg-gray-800 text-gray-300 hover:bg-gray-700 transition" data-cat="SCHOLARSHIPS">
                    🎓 منح وتدريب بحثي صيفي
                </button>
            </div>

            <!-- Search & Location Filters -->
            <div class="flex items-center space-x-3 space-x-reverse w-full md:w-auto">
                <div class="relative flex-1 md:w-64">
                    <input type="text" id="search-input" onkeyup="handleSearch()" placeholder="ابحث باسم الفرصة، المدينة..." class="w-full bg-gray-800 border border-gray-700 text-gray-200 text-xs rounded-xl px-4 py-2 pr-9 focus:outline-none focus:border-blue-500">
                    <i class="fa-solid fa-search absolute right-3 top-2.5 text-gray-400 text-xs"></i>
                </div>
                <select id="status-filter" onchange="loadOpportunities()" class="bg-gray-800 border border-gray-700 text-gray-200 text-xs rounded-xl px-3 py-2 focus:outline-none focus:border-blue-500">
                    <option value="">جميع الحالات</option>
                    <option value="READY_FOR_REVIEW">📝 جاهزة للتقديم فوراً (READY)</option>
                    <option value="APPLICATION_FAILED">🛠 تحتاج تدخلاً (FAILED)</option>
                </select>
                <select id="location-filter" onchange="loadOpportunities()" class="bg-gray-800 border border-gray-700 text-gray-200 text-xs rounded-xl px-3 py-2 focus:outline-none focus:border-blue-500">
                    <option value="">جميع المواقع</option>
                    <option value="MALAYSIA">🇲🇾 داخل ماليزيا</option>
                    <option value="INTERNATIONAL">✈️ دولية شاملة الطيران</option>
                </select>
            </div>
        </div>

        <!-- Results Summary & Sort -->
        <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div id="results-summary" class="text-[11px] text-gray-400 font-semibold">جارٍ تحميل الفرص...</div>
            <div class="flex items-center gap-2 text-[11px] text-gray-400">
                <label for="sort-select" class="font-semibold">ترتيب حسب:</label>
                <select id="sort-select" onchange="loadOpportunities()" class="bg-gray-800/80 border border-gray-700 text-gray-200 text-[11px] rounded-lg px-2.5 py-1.5 focus:border-blue-500">
                    <option value="match">نسبة التطابق</option>
                    <option value="deadline">آخر موعد للتسجيل</option>
                </select>
            </div>
        </div>

        <!-- Opportunities Grid -->
        <div id="loading-spinner" class="hidden">
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-6" aria-hidden="true">
                <div class="skeleton"></div>
                <div class="skeleton"></div>
                <div class="skeleton"></div>
                <div class="skeleton"></div>
            </div>
            <div class="text-center text-gray-400 text-sm mt-4">
                <i class="fa-solid fa-circle-notch fa-spin text-blue-500 ml-1"></i>
                جاري تحميل أحدث الفرص والتحقق من التغطية...
            </div>
        </div>

        <div id="opps-container" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <!-- Dynamically populated via JavaScript -->
        </div>

        <div id="no-results" class="py-16 text-center text-gray-500 text-sm hidden">
            <i class="fa-regular fa-folder-open text-4xl mb-3"></i>
            <div>لا توجد فرص مطابقة لهذا التصنيف حالياً. جرب اختيار تصنيف آخر أو اضغط على "تدقيق فوري".</div>
        </div>

        <div id="error-state" class="hidden py-16 text-center">
            <div class="inline-flex flex-col items-center gap-3 max-w-md">
                <div class="w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/20 text-red-400 flex items-center justify-center text-xl">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                </div>
                <div class="text-sm font-bold text-red-300">تعذر تحميل الفرص</div>
                <div class="text-xs text-gray-400">تأكد من أن الخادم يعمل ثم أعد المحاولة.</div>
                <button onclick="loadOpportunities()" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-200 rounded-xl text-xs font-bold">
                    <i class="fa-solid fa-rotate-right ml-1"></i> إعادة المحاولة
                </button>
            </div>
        </div>

    </main>

    <!-- Motivation Letter / Kit Modal -->
    <div id="kit-modal" role="dialog" aria-modal="true" class="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50 hidden" onclick="if(event.target===this) closeKitModal()">
        <div class="modal-panel bg-gray-900 border border-gray-800 rounded-3xl max-w-3xl w-full p-6 max-h-[90vh] flex flex-col shadow-2xl">
            <div class="flex items-center justify-between border-b border-gray-800 pb-4 mb-4">
                <div class="flex items-center space-x-3 space-x-reverse">
                    <div class="w-10 h-10 rounded-xl bg-blue-600/20 text-blue-400 flex items-center justify-center">
                        <i class="fa-solid fa-envelope-open-text text-lg"></i>
                    </div>
                    <div>
                        <h3 class="text-base font-bold text-white" id="modal-kit-title">ملف التقديم وخطاب الدافع المخصص</h3>
                        <p class="text-xs text-gray-400" id="modal-kit-code">كود الفرصة</p>
                    </div>
                </div>
                <button onclick="closeKitModal()" class="text-gray-400 hover:text-white text-lg">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>

            <div class="flex-1 overflow-y-auto space-y-4 pr-1 text-sm">
                <div class="bg-gray-800/60 p-4 rounded-xl border border-gray-700/50">
                    <div class="text-xs text-blue-400 font-semibold mb-1">🎁 التغطية المالية المؤكدة:</div>
                    <div class="text-xs text-gray-200" id="modal-kit-cov">0 رسوم + سكن مجاني + وجبات + طيران</div>
                </div>

                <div>
                    <div class="flex items-center justify-between mb-2">
                        <span class="text-xs font-bold text-gray-300">✍️ مسودة خطاب الدافع المخصص (Tailored Statement of Purpose):</span>
                        <button onclick="copyMotivationLetter()" class="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 px-3 py-1 rounded-lg flex items-center space-x-1 space-x-reverse">
                            <i class="fa-solid fa-copy"></i>
                            <span id="copy-btn-text">نسخ المقال</span>
                        </button>
                    </div>
                    <div class="bg-gray-950 p-4 rounded-xl border border-gray-800 font-mono text-xs text-gray-300 leading-relaxed whitespace-pre-wrap select-all" id="modal-kit-essay">
                        <!-- Essay inserted here -->
                    </div>
                </div>
            </div>

            <div class="border-t border-gray-800 pt-4 mt-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                    <div id="modal-kit-cv-notice" class="px-3.5 py-1.5 bg-indigo-950/60 border border-indigo-800/60 text-indigo-300 rounded-xl text-xs font-semibold flex items-center space-x-1.5 space-x-reverse">
                        <i class="fa-solid fa-wand-magic-sparkles text-indigo-400"></i>
                        <span id="modal-kit-cv-text">تتطلب سيرة ذاتية: ستُعاد كتابتها وتوليدها وإرفاقها تلقائياً عند التقديم</span>
                    </div>
                </div>
                <div class="flex items-center space-x-2 space-x-reverse">
                    <button onclick="closeKitModal()" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-xl text-xs font-semibold">إغلاق</button>
                    <button id="modal-kit-approve-btn" onclick="" class="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold flex items-center space-x-1.5 space-x-reverse shadow transition">
                        <i class="fa-solid fa-check"></i>
                        <span>موافقة وتقديم الآن</span>
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- Profile View & Edit Modal -->
    <div id="profile-modal" role="dialog" aria-modal="true" class="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 z-50 hidden" onclick="if(event.target===this) closeProfileModal()">
        <div class="modal-panel bg-gray-900 border border-gray-800 rounded-3xl max-w-2xl w-full p-6 max-h-[90vh] flex flex-col shadow-2xl">
            <div class="flex items-center justify-between border-b border-gray-800 pb-4 mb-4">
                <div class="flex items-center space-x-3 space-x-reverse">
                    <div class="w-10 h-10 rounded-xl bg-indigo-600/20 text-indigo-400 flex items-center justify-center">
                        <i class="fa-solid fa-user-gear text-lg"></i>
                    </div>
                    <div>
                        <h3 class="text-base font-bold text-white">ملف المرشح والخزانة الآمنة</h3>
                        <p class="text-xs text-gray-400">البيانات الحقيقية المستخدمة لملء الاستمارات</p>
                    </div>
                </div>
                <button onclick="closeProfileModal()" class="text-gray-400 hover:text-white text-lg">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>

            <form id="profile-form" onsubmit="saveProfile(event)" class="flex-1 overflow-y-auto space-y-4 pr-1 text-xs">
                <div>
                    <label class="block text-gray-400 mb-1 font-semibold">الاسم الكامل بالإنجليزية (كما في الجواز):</label>
                    <input type="text" id="prof-name" class="w-full bg-gray-800 border border-gray-700 rounded-xl p-2.5 text-gray-200">
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="block text-gray-400 mb-1 font-semibold">البريد الإلكتروني الجامعي:</label>
                        <input type="email" id="prof-email" class="w-full bg-gray-800 border border-gray-700 rounded-xl p-2.5 text-gray-200">
                    </div>
                    <div>
                        <label class="block text-gray-400 mb-1 font-semibold">رقم الهاتف / واتساب:</label>
                        <input type="text" id="prof-phone" class="w-full bg-gray-800 border border-gray-700 rounded-xl p-2.5 text-gray-200">
                    </div>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="block text-gray-400 mb-1 font-semibold">رقم جواز السفر:</label>
                        <input type="text" id="prof-passport" class="w-full bg-gray-800 border border-gray-700 rounded-xl p-2.5 text-gray-200">
                    </div>
                    <div>
                        <label class="block text-gray-400 mb-1 font-semibold">الرقم الجامعي (Matric Number):</label>
                        <input type="text" id="prof-matric" class="w-full bg-gray-800 border border-gray-700 rounded-xl p-2.5 text-gray-200">
                    </div>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="block text-gray-400 mb-1 font-semibold">المعدل التراكمي (CGPA):</label>
                        <input type="text" id="prof-cgpa" class="w-full bg-gray-800 border border-gray-700 rounded-xl p-2.5 text-gray-200">
                    </div>
                    <div>
                        <label class="block text-gray-400 mb-1 font-semibold">رابط GitHub (اختياري):</label>
                        <input type="url" id="prof-github" class="w-full bg-gray-800 border border-gray-700 rounded-xl p-2.5 text-gray-200">
                    </div>
                </div>
                <div>
                    <label class="block text-gray-400 mb-1 font-semibold">عنوان السكن في كوالالمبور:</label>
                    <input type="text" id="prof-address" class="w-full bg-gray-800 border border-gray-700 rounded-xl p-2.5 text-gray-200">
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                        <label class="block text-gray-400 mb-1 font-semibold">متاح من تاريخ:</label>
                        <input type="date" id="prof-avail-from" class="w-full bg-gray-800 border border-gray-700 rounded-xl p-2.5 text-gray-200">
                    </div>
                    <div>
                        <label class="block text-gray-400 mb-1 font-semibold">متاح حتى تاريخ:</label>
                        <input type="date" id="prof-avail-to" class="w-full bg-gray-800 border border-gray-700 rounded-xl p-2.5 text-gray-200">
                    </div>
                </div>
                <div>
                    <label class="block text-gray-400 mb-1 font-semibold">تفضيل موقع الفرصة:</label>
                    <select id="prof-location-pref" class="w-full bg-gray-800 border border-gray-700 rounded-xl p-2.5 text-gray-200">
                        <option value="">بدون تفضيل</option>
                        <option value="INSIDE_MALAYSIA">داخل ماليزيا فقط</option>
                        <option value="OUTSIDE_MALAYSIA">خارج ماليزيا فقط</option>
                        <option value="ANY">داخل وخارج ماليزيا</option>
                    </select>
                </div>
                <div>
                    <label class="block text-gray-400 mb-1 font-semibold">تفضيلات أنواع الأنشطة:</label>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <label class="flex items-center gap-2 bg-gray-800/60 border border-gray-700 rounded-xl p-2 cursor-pointer">
                            <input type="checkbox" name="activity-pref" value="NATURE_ECO_CONSERVATION" class="accent-emerald-500">
                            <span class="text-gray-300">الطبيعة والبيئة</span>
                        </label>
                        <label class="flex items-center gap-2 bg-gray-800/60 border border-gray-700 rounded-xl p-2 cursor-pointer">
                            <input type="checkbox" name="activity-pref" value="GREEN_AI_CLIMATE_TECH" class="accent-emerald-500">
                            <span class="text-gray-300">الذكاء الاصطناعي الأخضر</span>
                        </label>
                        <label class="flex items-center gap-2 bg-gray-800/60 border border-gray-700 rounded-xl p-2 cursor-pointer">
                            <input type="checkbox" name="activity-pref" value="CORE_AI_HACKATHONS" class="accent-emerald-500">
                            <span class="text-gray-300">هاكاثونات ومسابقات</span>
                        </label>
                        <label class="flex items-center gap-2 bg-gray-800/60 border border-gray-700 rounded-xl p-2 cursor-pointer">
                            <input type="checkbox" name="activity-pref" value="OUTDOOR_LEADERSHIP_CAMPS" class="accent-emerald-500">
                            <span class="text-gray-300">معسكرات ميدانية وقيادة</span>
                        </label>
                        <label class="flex items-center gap-2 bg-gray-800/60 border border-gray-700 rounded-xl p-2 cursor-pointer">
                            <input type="checkbox" name="activity-pref" value="COMMUNITY_VOLUNTEERING_EXCHANGE" class="accent-emerald-500">
                            <span class="text-gray-300">تطوع مجتمعي وتبادل</span>
                        </label>
                        <label class="flex items-center gap-2 bg-gray-800/60 border border-gray-700 rounded-xl p-2 cursor-pointer">
                            <input type="checkbox" name="activity-pref" value="MENA_GCC_ASEAN_SPECIAL" class="accent-emerald-500">
                            <span class="text-gray-300">الشرق الأوسط والخليج وآسيان</span>
                        </label>
                    </div>
                </div>

                <div class="bg-gray-800/40 p-3 rounded-xl border border-gray-700/30 text-[11px] text-gray-400 leading-normal">
                    💡 <strong>ملاحظة أمان:</strong> أي تعديل هنا ينعكس فوراً على خزانة الذاكرة المستدامة (SQLite Vault) ويعيد توليد الـ CV المخصص لكل فرصة بصورة تلقائية.
                </div>

                <div class="border-t border-gray-800/80 pt-4 flex items-center justify-end space-x-2 space-x-reverse sticky bottom-0 bg-gray-900/95 backdrop-blur rounded-b-3xl">
                    <button type="button" id="btn-close-profile-modal" onclick="closeProfileModal()" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-xl font-semibold">إلغاء</button>
                    <button type="submit" class="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold">حفظ التعديلات</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Toast Notifications -->
    <div id="toast-container" class="fixed top-20 inset-x-4 flex flex-col items-center gap-2 pointer-events-none" style="z-index:60"></div>

    <!-- Confirm Dialog -->
    <div id="confirm-modal" class="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4 hidden" style="z-index:70" role="dialog" aria-modal="true">
        <div class="modal-panel bg-gray-900 border border-gray-800 rounded-3xl max-w-md w-full p-6 shadow-2xl">
            <div class="flex items-start gap-3">
                <div class="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center shrink-0">
                    <i class="fa-solid fa-circle-question"></i>
                </div>
                <div class="flex-1">
                    <h3 class="text-sm font-bold text-white mb-1">تأكيد الإجراء</h3>
                    <p id="confirm-message" class="text-xs text-gray-400 leading-relaxed"></p>
                </div>
            </div>
            <div class="flex items-center justify-end gap-2 mt-6">
                <button id="confirm-cancel" type="button" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 rounded-xl text-xs font-semibold">إلغاء</button>
                <button id="confirm-ok" type="button" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold">تأكيد</button>
            </div>
        </div>
    </div>

    <!-- Scripts -->
    <script>
        let currentCategory = 'ALL';
        let opportunities = [];
        let sortMode = 'match';

        async function initDashboard() {
            await loadProfile();
            await loadOpportunities();
        }

        async function loadProfile() {
            try {
                const res = await fetch('/api/profile');
                const data = await res.json();
                const p = data.personal || {};
                const edu = data.education || {};
                
                document.getElementById('header-name').innerText = p.full_name_en || 'محمد مهدي السلقدي';
                document.getElementById('header-cgpa').innerText = edu.cgpa || '3.53';

                document.getElementById('prof-name').value = p.full_name_en || '';
                document.getElementById('prof-email').value = p.email || '';
                document.getElementById('prof-phone').value = p.phone_my || '';
                document.getElementById('prof-passport').value = p.passport_number || '';
                document.getElementById('prof-matric').value = edu.matric_number || '';
                document.getElementById('prof-cgpa').value = edu.cgpa || '';
                document.getElementById('prof-address').value = p.address_my || '';
                const activityPrefs = new Set(
                    String(p.activity_preferences || '')
                        .split(',')
                        .map(item => item.trim())
                        .filter(Boolean)
                );
                document.querySelectorAll('input[name="activity-pref"]').forEach(cb => {
                    cb.checked = activityPrefs.has(cb.value);
                });
                document.getElementById('prof-location-pref').value = p.location_preference || '';
                document.getElementById('prof-avail-from').value = p.availability_from || '';
                document.getElementById('prof-avail-to').value = p.availability_to || '';
                document.getElementById('prof-github').value = p.github_url || '';
            } catch (err) {
                console.error("Failed to load profile", err);
            }
        }

        function setCategory(cat) {
            currentCategory = cat;
            document.querySelectorAll('#category-tabs .tab-btn').forEach(btn => {
                if (btn.getAttribute('data-cat') === cat) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
            loadOpportunities();
        }

        async function loadOpportunities() {
            const spinner = document.getElementById('loading-spinner');
            const container = document.getElementById('opps-container');
            const noResults = document.getElementById('no-results');
            const errorState = document.getElementById('error-state');
            const search = document.getElementById('search-input').value.trim();
            const location = document.getElementById('location-filter').value;
            const statusFilter = document.getElementById('status-filter')?.value || '';
            sortMode = document.getElementById('sort-select').value || 'match';

            spinner.classList.remove('hidden');
            container.innerHTML = '';
            noResults.classList.add('hidden');
            errorState.classList.add('hidden');

            try {
                const params = new URLSearchParams();
                if (currentCategory && currentCategory !== 'ALL') params.append('category', currentCategory);
                if (location) params.append('location', location);
                if (statusFilter) params.append('status', statusFilter);
                if (search) params.append('search', search);

                const res = await fetch(`/api/opportunities?${params.toString()}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                opportunities = data.opportunities || [];

                updateKPICounters(opportunities);
                updateResultsSummary();
                spinner.classList.add('hidden');

                if (opportunities.length === 0) {
                    noResults.classList.remove('hidden');
                    return;
                }

                container.innerHTML = sortOpportunities(opportunities).map(opp => renderOpportunityCard(opp)).join('');
            } catch (err) {
                console.error("Error loading opportunities", err);
                spinner.classList.add('hidden');
                updateResultsSummary(0);
                errorState.classList.remove('hidden');
            }
        }

        function updateKPICounters(opps) {
            document.getElementById('stat-total').innerText = opps.length;
            document.getElementById('stat-verified').innerText = opps.filter(o => o.status !== 'DECLINED_BY_USER').length;
            document.getElementById('stat-vol').innerText = opps.filter(o => o.category_tag === 'VOLUNTEERING').length;
            document.getElementById('stat-camps').innerText = opps.filter(o => o.category_tag === 'CAMPS').length;
            document.getElementById('stat-ai').innerText = opps.filter(o => o.category_tag === 'AI_TECH' || o.category_tag === 'SCHOLARSHIPS').length;
        }

        function escHtml(value) {
            return String(value ?? '').replace(/[&<>"']/g, ch => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            }[ch]));
        }

        function safeHttpUrl(value) {
            try {
                const url = new URL(String(value || ''), window.location.origin);
                if (url.protocol === 'http:' || url.protocol === 'https:') return url.href;
            } catch (e) {}
            return '';
        }

        function safeCode(value) {
            return String(value || '').replace(/[^A-Za-z0-9_-]/g, '');
        }

        function toast(message, type = 'info') {
            const container = document.getElementById('toast-container');
            const palette = {
                success: 'bg-emerald-950/95 border-emerald-500/30 text-emerald-200',
                error: 'bg-red-950/95 border-red-500/30 text-red-200',
                info: 'bg-slate-900/95 border-blue-500/30 text-slate-200',
            };
            const icons = {
                success: 'fa-circle-check',
                error: 'fa-circle-exclamation',
                info: 'fa-circle-info',
            };
            const el = document.createElement('div');
            el.className = `toast pointer-events-auto w-full max-w-md border rounded-2xl px-4 py-3 shadow-2xl text-xs font-semibold flex items-start gap-2 ${palette[type] || palette.info}`;
            el.innerHTML = `<i class="fa-solid ${icons[type] || icons.info} mt-0.5"></i><span class="flex-1 leading-relaxed">${escHtml(message)}</span>`;
            container.appendChild(el);
            setTimeout(() => {
                el.style.opacity = '0';
                el.style.transform = 'translateY(-6px)';
                el.style.transition = 'all .2s ease';
            }, 4200);
            setTimeout(() => el.remove(), 4600);
        }

        function askConfirm(message) {
            return new Promise((resolve) => {
                const modal = document.getElementById('confirm-modal');
                const ok = document.getElementById('confirm-ok');
                const cancel = document.getElementById('confirm-cancel');
                document.getElementById('confirm-message').innerText = message;
                modal.classList.remove('hidden');
                const finish = (value) => {
                    modal.classList.add('hidden');
                    ok.onclick = null;
                    cancel.onclick = null;
                    resolve(value);
                };
                ok.onclick = () => finish(true);
                cancel.onclick = () => finish(false);
            });
        }

        function setModalOpen(modalId, open) {
            const modal = document.getElementById(modalId);
            if (!modal) return;
            modal.classList.toggle('hidden', !open);
            const anyOpen = ['kit-modal', 'profile-modal'].some((id) => {
                const el = document.getElementById(id);
                return el && !el.classList.contains('hidden');
            });
            document.body.classList.toggle('modal-open', anyOpen);
        }

        function sortOpportunities(items) {
            const copy = [...items];
            if (sortMode === 'deadline') {
                copy.sort((a, b) => String(a.deadline_iso || '9999-12-31').localeCompare(String(b.deadline_iso || '9999-12-31')));
            } else {
                copy.sort((a, b) => Number(b.match_score || 0) - Number(a.match_score || 0));
            }
            return copy;
        }

        function updateResultsSummary(count) {
            const total = typeof count === 'number' ? count : opportunities.length;
            const label = total === 0 ? 'لا توجد نتائج مطابقة' : `${total} فرصة مطابقة`;
            const time = new Date().toLocaleTimeString('ar-MY', { hour: '2-digit', minute: '2-digit' });
            document.getElementById('results-summary').innerText = `${label} • آخر تحديث ${time}`;
        }

        function renderOpportunityCard(opp) {
            const rawCode = safeCode(opp.opportunity_code);
            const code = escHtml(rawCode);
            const title = escHtml(opp.title);
            const organizer = escHtml(opp.organizer);
            const city = escHtml(opp.location_city);
            const country = escHtml(opp.location_country);
            const categoryLabel = escHtml(opp.category_label_ar);
            const coverage = escHtml(opp.financial_coverage_ar);
            const coverageKnown = Boolean(opp.coverage_known);
            const explanation = escHtml(opp.explanation_ar);
            const matchScore = Number.isFinite(Number(opp.match_score)) ? Number(opp.match_score) : 0;
            const sourceConfidence = Math.max(0, Math.min(100, Math.round(Number(opp.source_confidence || 0) * 100)));
            const deadlineConfidence = Math.max(0, Math.min(100, Math.round(Number(opp.deadline_confidence || 0) * 100)));
            const deadline = escHtml(opp.deadline_iso || 'غير محدد');
            const programStart = escHtml(opp.program_start_iso || 'غير محدد');
            const programEnd = escHtml(opp.program_end_iso || 'غير محدد');
            const deadlineDate = opp.deadline_iso ? new Date(`${opp.deadline_iso}T23:59:59`) : null;
            const daysToDeadline = deadlineDate && !Number.isNaN(deadlineDate.getTime())
                ? Math.ceil((deadlineDate.getTime() - Date.now()) / 86400000)
                : null;
            let deadlineBadge = '';
            if (daysToDeadline !== null) {
                if (daysToDeadline < 0) {
                    deadlineBadge = '<span class="urgency-expired font-bold">انتهى الموعد</span>';
                } else if (daysToDeadline <= 14) {
                    deadlineBadge = `<span class="urgency-soon font-bold">متبقي ${daysToDeadline} يوم</span>`;
                }
            }
            const sourceType = escHtml(opp.source_type || 'unknown');
            const applyUrl = safeHttpUrl(opp.apply_url);
            const isMY = opp.is_inside_malaysia;
            const locationBadge = isMY
                ? `<span class="px-2.5 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-lg text-[11px] font-semibold"><i class="fa-solid fa-map-pin ml-1"></i>داخل ماليزيا (سارية بإقامة UTM)</span>`
                : `<span class="px-2.5 py-1 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded-lg text-[11px] font-semibold"><i class="fa-solid fa-plane-departure ml-1"></i>دولية (شاملة تذاكر الطيران من KUL)</span>`;

            const cvBadge = opp.cv_required
                ? `<span class="px-2.5 py-1 bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 rounded-lg text-[11px] font-semibold"><i class="fa-solid fa-wand-magic-sparkles ml-1"></i>📄 تتطلب سيرة ذاتية (تُصاغ تلقائياً بالكامل عند التقديم)</span>`
                : `<span class="px-2.5 py-1 bg-gray-800/90 text-gray-400 border border-gray-700 rounded-lg text-[11px] font-semibold"><i class="fa-solid fa-file-circle-check ml-1"></i>📄 تقديم مباشر (لا تتطلب سيرة ذاتية)</span>`;

            let statusBadge = `<span class="px-2 py-0.5 bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 rounded-md text-[10px] font-bold">بانتظار قرارك</span>`;
            if (opp.status === 'APPLIED_AUTOMATICALLY') {
                statusBadge = `<span class="px-2 py-0.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-md text-[10px] font-bold">✅ تم التقديم</span>`;
            } else if (opp.status === 'SUBMITTED_UNCONFIRMED') {
                statusBadge = `<span class="px-2 py-0.5 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-md text-[10px] font-bold">⚠️ أُرسل بانتظار تأكيد</span>`;
            } else if (opp.status === 'READY_FOR_REVIEW') {
                statusBadge = `<span class="px-2 py-0.5 bg-sky-500/10 text-sky-400 border border-sky-500/20 rounded-md text-[10px] font-bold">📝 جاهز للمراجعة</span>`;
            } else if (opp.status === 'PAUSED_AT_CAPTCHA' || opp.status === 'APPLICATION_FAILED') {
                statusBadge = `<span class="px-2 py-0.5 bg-orange-500/10 text-orange-400 border border-orange-500/20 rounded-md text-[10px] font-bold">🛠 يحتاج تدخلاً</span>`;
            } else if (opp.status === 'DECLINED_BY_USER') {
                statusBadge = `<span class="px-2 py-0.5 bg-red-500/10 text-red-400 border border-red-500/20 rounded-md text-[10px] font-bold">مستبعد</span>`;
            }

            return `
            <div class="card-glow opp-card bg-gray-900/90 border border-gray-800/90 rounded-3xl p-6 flex flex-col justify-between">
                <div>
                    <!-- Header Badges -->
                    <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
                        <div class="flex items-center space-x-2 space-x-reverse">
                            <span class="text-xs font-mono font-bold text-gray-400 bg-gray-800 px-2 py-0.5 rounded-md border border-gray-700">${code}</span>
                            <span class="text-xs font-semibold text-indigo-400">${categoryLabel}</span>
                        </div>
                        <div class="flex items-center space-x-2 space-x-reverse">
                            ${statusBadge}
                            <span class="text-xs font-black text-blue-400 bg-blue-900/40 px-2.5 py-0.5 rounded-lg border border-blue-800">🎯 ${matchScore}% تطابق</span>
                        </div>
                    </div>

                    <!-- Title -->
                    <h3 class="text-lg font-bold text-white mb-2 leading-snug">${title}</h3>

                    <!-- Organizer & Location & CV Requirement -->
                    <div class="flex flex-wrap items-center gap-2 text-xs text-gray-400 mb-3">
                        <span><i class="fa-solid fa-building-columns text-gray-500 ml-1"></i>${organizer}</span>
                        <span><i class="fa-solid fa-location-dot text-gray-500 ml-1"></i>${city ? city + '، ' : ''}${country}</span>
                        ${locationBadge}
                        ${cvBadge}
                    </div>

                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3 text-[11px]">
                        <div class="bg-gray-800/60 border border-gray-700/60 rounded-xl p-2">
                            <div class="text-gray-500">📅 آخر موعد للتسجيل</div>
                            <div class="text-gray-200 font-semibold">${deadline}</div>
                            ${deadlineBadge ? `<div class="mt-1 text-[10px]">${deadlineBadge}</div>` : ''}
                        </div>
                        <div class="bg-gray-800/60 border border-gray-700/60 rounded-xl p-2">
                            <div class="text-gray-500">🚀 بداية الرحلة</div>
                            <div class="text-gray-200 font-semibold">${programStart}</div>
                        </div>
                        <div class="bg-gray-800/60 border border-gray-700/60 rounded-xl p-2">
                            <div class="text-gray-500">🏁 نهاية الرحلة</div>
                            <div class="text-gray-200 font-semibold">${programEnd}</div>
                        </div>
                    </div>

                    <div class="flex flex-wrap items-center gap-2 text-[11px] text-gray-500 mb-3">
                        <span><i class="fa-solid fa-link text-gray-600 ml-1"></i>المصدر: ${sourceType}</span>
                        <span>ثقة المصدر: ${sourceConfidence}%</span>
                        <span>ثقة الموعد: ${deadlineConfidence}%</span>
                        ${sourceConfidence < 50 ? '<span class="text-amber-400 font-semibold">⚠️ تحقق يدوياً قبل التقديم</span>' : ''}
                    </div>

                    <!-- Financial Coverage Pill -->
                    <div class="bg-gray-800/70 border ${coverageKnown ? 'border-emerald-500/20' : 'border-amber-500/40'} p-3 rounded-xl mb-3 flex items-start space-x-2 space-x-reverse">
                        <i class="fa-solid ${coverageKnown ? 'fa-gift text-emerald-400' : 'fa-circle-exclamation text-amber-400'} mt-0.5 text-sm"></i>
                        <div class="text-xs ${coverageKnown ? 'text-emerald-300' : 'text-amber-300'} font-semibold leading-relaxed">
                            ${coverage}
                        </div>
                    </div>

                    <!-- Simplified Arabic Explanation Box -->
                    <div class="bg-gray-950/70 border-r-4 border-blue-500 p-3.5 rounded-xl mb-4 text-xs text-gray-300 leading-relaxed">
                        <div class="text-blue-400 font-bold mb-1 flex items-center space-x-1.5 space-x-reverse">
                            <i class="fa-solid fa-lightbulb"></i>
                            <span>شرح مبسط عن الفرصة:</span>
                        </div>
                        <p>${explanation}</p>
                    </div>
                </div>

                <!-- Action Toolbar (Without separate manual CV button) -->
                <div class="border-t border-gray-800/80 pt-4 mt-2 flex flex-wrap items-center justify-between gap-2">
                    <div class="flex flex-wrap items-center gap-2">
                        <button onclick="approveOpp('${rawCode}')" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold flex items-center space-x-1.5 space-x-reverse shadow transition">
                            <i class="fa-solid fa-check"></i>
                            <span>موافقة وتقديم</span>
                        </button>
                        <button onclick="openKitModal('${rawCode}')" class="px-3.5 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 rounded-xl text-xs font-semibold flex items-center space-x-1.5 space-x-reverse transition">
                            <i class="fa-solid fa-envelope-open-text"></i>
                            <span>خطاب الدافع والمراجعة</span>
                        </button>
                    </div>

                    <div class="flex items-center space-x-2 space-x-reverse">
                        ${applyUrl ? `<a href="${applyUrl}" target="_blank" rel="noopener noreferrer" class="p-2 text-gray-400 hover:text-blue-400 text-sm transition" title="فتح الإعلان الرسمي"><i class="fa-solid fa-arrow-up-right-from-square"></i></a>` : ''}
                        <button onclick="declineOpp('${rawCode}')" class="p-2 text-gray-400 hover:text-red-400 text-sm transition" title="استبعاد الفرصة">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                </div>
            </div>
            `;
        }

        async function approveOpp(code) {
            code = safeCode(code);
            if (!code) return;
            if (!await askConfirm(`هل أنت متأكد من رغبتك بالموافقة على التقديم للفرصة ${code}؟`)) return;
            try {
                const res = await fetch(`/api/opportunities/${encodeURIComponent(code)}/approve`, { method: 'POST' });
                const data = await res.json();
                if (!res.ok) {
                    toast(`تعذر التقديم: ${data.detail || data.message || res.status}`, 'error');
                    return;
                }
                if (data.status === 'APPLIED_AUTOMATICALLY') {
                    toast(`تم التقديم بتأكيد رسمي. كود الفرصة: ${code}`, 'success');
                } else if (data.status === 'SUBMITTED_UNCONFIRMED') {
                    toast(`تم الضغط على Submit لكن لا يوجد تأكيد رسمي بعد. الحالة: ${data.status}.`, 'info');
                } else if (data.status === 'PAUSED_NEEDS_USER_INPUT') {
                    toast(`الطلب متوقف بانتظار بيانات إضافية. كود الفرصة: ${code}`, 'info');
                } else {
                    toast(`الحالة: ${data.status}. لم يتم تأكيد أي تقديم.`, 'info');
                }
                loadOpportunities();
            } catch (err) {
                toast(`حدث خطأ: ${err.message}`, 'error');
            }
        }

        async function declineOpp(code) {
            code = safeCode(code);
            if (!code) return;
            if (!await askConfirm(`هل تريد استبعاد الفرصة ${code}؟`)) return;
            try {
                await fetch(`/api/opportunities/${encodeURIComponent(code)}/decline`, { method: 'POST' });
                toast('تم استبعاد الفرصة من القائمة.', 'success');
                loadOpportunities();
            } catch (err) {
                toast(`تعذر استبعاد الفرصة: ${err.message}`, 'error');
            }
        }

        async function openKitModal(code) {
            code = safeCode(code);
            if (!code) return;
            try {
                const res = await fetch(`/api/opportunities/${encodeURIComponent(code)}/kit`);
                const kit = await res.json();

                document.getElementById('modal-kit-title').innerText = kit.title;
                document.getElementById('modal-kit-code').innerText = `كود: ${code} | الجهة: ${kit.organizer}`;
                document.getElementById('modal-kit-cov').innerText = kit.financial_coverage.coverage_summary_ar || 'غير محدد — تحقق من الجهة قبل التقديم';
                document.getElementById('modal-kit-essay').innerText = kit.tailored_motivation_letter;

                const cvNotice = document.getElementById('modal-kit-cv-notice');
                const cvText = document.getElementById('modal-kit-cv-text');

                if (kit.cv_required) {
                    cvNotice.className = "px-3.5 py-1.5 bg-indigo-950/60 border border-indigo-800/60 text-indigo-300 rounded-xl text-xs font-semibold flex items-center space-x-1.5 space-x-reverse";
                    cvText.innerText = "تتطلب سيرة ذاتية: ستُعاد كتابتها وتوليدها وإرفاقها تلقائياً عند التقديم";
                } else {
                    cvNotice.className = "px-3.5 py-1.5 bg-gray-800/80 border border-gray-700 text-gray-400 rounded-xl text-xs font-semibold flex items-center space-x-1.5 space-x-reverse";
                    cvText.innerText = "تقديم مباشر: استمارة تسجيل مباشرة دون الحاجة لسيرة ذاتية";
                }

                document.getElementById('modal-kit-approve-btn').onclick = () => { closeKitModal(); approveOpp(code); };

                setModalOpen('kit-modal', true);
            } catch (err) {
                toast(`تعذر جلب ملف التقديم: ${err.message}`, 'error');
            }
        }

        function closeKitModal() {
            setModalOpen('kit-modal', false);
        }

        function copyMotivationLetter() {
            const text = document.getElementById('modal-kit-essay').innerText;
            navigator.clipboard.writeText(text);
            toast('تم نسخ خطاب الدافع.', 'success');
            const btnText = document.getElementById('copy-btn-text');
            btnText.innerText = "تم النسخ!";
            setTimeout(() => { btnText.innerText = "نسخ المقال"; }, 2000);
        }

        function openProfileModal() {
            setModalOpen('profile-modal', true);
            const firstField = document.getElementById('prof-name');
            if (firstField) setTimeout(() => firstField.focus(), 60);
        }

        function closeProfileModal() {
            setModalOpen('profile-modal', false);
        }

        async function saveProfile(e) {
            e.preventDefault();
            const payload = {
                full_name_en: document.getElementById('prof-name').value,
                email: document.getElementById('prof-email').value,
                phone_my: document.getElementById('prof-phone').value,
                passport_number: document.getElementById('prof-passport').value,
                matric_number: document.getElementById('prof-matric').value,
                cgpa: document.getElementById('prof-cgpa').value,
                address_my: document.getElementById('prof-address').value,
                activity_preferences: Array.from(
                    document.querySelectorAll('input[name="activity-pref"]:checked')
                ).map(cb => cb.value).join(', '),
                location_preference: document.getElementById('prof-location-pref').value,
                availability_from: document.getElementById('prof-avail-from').value,
                availability_to: document.getElementById('prof-avail-to').value,
                github_url: document.getElementById('prof-github').value,
            };

            try {
                const res = await fetch('/api/profile', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    const detail = Array.isArray(data.detail) ? data.detail.join('\\n') : (data.detail || 'تحقق من صحة البيانات.');
                    throw new Error(detail);
                }
                toast('تم حفظ وتحديث بياناتك بنجاح.', 'success');
                closeProfileModal();
                loadProfile();
            } catch (err) {
                toast(`تعذر حفظ البيانات: ${err.message}`, 'error');
            }
        }

        async function triggerAudit() {
            const btn = document.getElementById('btn-audit');
            btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i><span>جاري التدقيق...</span>`;
            try {
                const res = await fetch('/api/audit', { method: 'POST' });
                const data = await res.json();
                toast(`اكتمل التدقيق! فرص مؤهلة جديدة: ${data.verified_eligible_count || 0}`, 'success');
                loadOpportunities();
            } catch (err) {
                toast(`حدث خطأ أثناء التدقيق: ${err.message}`, 'error');
            } finally {
                btn.innerHTML = `<i class="fa-solid fa-bolt"></i><span>تدقيق فوري</span>`;
            }
        }

        async function triggerCrawl() {
            const btn = document.getElementById('btn-crawl');
            btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i><span>جاري السحب...</span>`;
            try {
                const res = await fetch('/api/crawl', { method: 'POST' });
                toast('تم إطلاق دورة السحب الآلية في الخلفية. سيتم تدقيق الفرص فور اكتمالها.', 'success');
            } catch (err) {
                toast(`حدث خطأ أثناء السحب: ${err.message}`, 'error');
            } finally {
                btn.innerHTML = `<i class="fa-solid fa-globe"></i><span>زحف الويب</span>`;
            }
        }

        function handleSearch() {
            clearTimeout(window._searchTimer);
            window._searchTimer = setTimeout(() => {
                loadOpportunities();
            }, 300);
        }

        // Close modals with Escape.
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeKitModal();
                closeProfileModal();
            }
        });

        // Initialize on load
        window.onload = initDashboard;
    </script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard() -> str:
    return DASHBOARD_HTML


def main() -> None:
    import argparse
    default_host = os.environ.get("HOST", "127.0.0.1")
    default_port = int(os.environ.get("PORT", "8080"))
    parser = argparse.ArgumentParser(description="ZCO-Hunter Web Dashboard & Real-Time Control Center")
    parser.add_argument("--host", default=default_host, help=f"Host IP (default: {default_host})")
    parser.add_argument("--port", type=int, default=default_port, help=f"Port to listen on (default: {default_port})")
    args = parser.parse_args()

    logger.info("Starting ZCO Web Dashboard on http://%s:%d ...", args.host, args.port)
    logger.info("Dashboard auth token source: %s", DASHBOARD_TOKEN_SOURCE)
    if DASHBOARD_TOKEN_SOURCE == "generated":
        logger.info("Generated a new dashboard token at %s (chmod 600).", DASHBOARD_TOKEN_FILE)
    elif DASHBOARD_TOKEN_SOURCE == "ephemeral":
        logger.warning("Could not persist token to disk. Use this token: %s", DASHBOARD_AUTH_TOKEN)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
