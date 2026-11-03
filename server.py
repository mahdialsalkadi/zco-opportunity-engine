#!/usr/bin/env python3
"""
ZCO-Engine v4.0 — Antigravity MCP Server, 6-Hour Auto-Applicant & Matrix Renderer (`server.py`)
===============================================================================================
Exposes the complete v4.0 pipeline to Google Antigravity via:
1. Model Context Protocol (`FastMCP` stdio server configured in `mcp.json`).
2. 6-Hour Scheduled Sidecar CLI (`python3 server.py --audit-batch --window-hours 6`).
3. Interactive Self-Learning Memory Vault CLI (`python3 server.py --learn-answers '{...}'`).
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional

_VENV_PYTHON = pathlib.Path(__file__).resolve().parent / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and pathlib.Path(sys.executable).resolve() != _VENV_PYTHON.resolve():
    if "-c" not in sys.argv:
        os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

from database import OpportunityDatabase, OpportunityStatus
from coverage_utils import coverage_summary
from engines_and_auditor import (
    AutonomousApplicantEngine,
    CandidateMemoryVault,
    DEFAULT_CANDIDATE_PROFILE,
    audit_opportunity_record,
)
from paths import DASHBOARD_PATH, DB_PATH

BASE_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_DB_PATH = DB_PATH
DEFAULT_DASHBOARD_PATH = DASHBOARD_PATH

TRACK_LABELS_AR: Dict[str, str] = {
    "NATURE_ECO_CONSERVATION": "1. أنشطة الطبيعة والبيئة والحفظ البيئي (Nature, Eco & Conservation)",
    "GREEN_AI_CLIMATE_TECH": "2. الذكاء الاصطناعي للبيئة والمناخ (Green AI & Climate Tech)",
    "CORE_AI_HACKATHONS": "3. الذكاء الاصطناعي والتقنية والهاكاثونات (Core AI & Hackathons)",
    "OUTDOOR_LEADERSHIP_CAMPS": "4. المخيمات الميدانية والمغامرات والقيادة (Outdoor Leadership & Camps)",
    "COMMUNITY_VOLUNTEERING_EXCHANGE": "5. التطوع المجتمعي والتبادل الشبابي (Community Volunteering & Exchange)",
    "MENA_GCC_ASEAN_SPECIAL": "6. مسار الشرق الأوسط والخليج والآسيان (MENA, GCC & ASEAN Special Tracks)",
}

STATUS_BADGES_AR: Dict[str, str] = {
    OpportunityStatus.APPLIED_AUTOMATICALLY: "تم التقديم بتأكيد رسمي",
    OpportunityStatus.SUBMITTED_UNCONFIRMED: "تم الإرسال — بانتظار تأكيد رسمي",
    OpportunityStatus.READY_FOR_REVIEW: "جاهز للمراجعة والتقديم اليدوي",
    OpportunityStatus.PAUSED_NEEDS_USER_INPUT: "بانتظار استكمال بيانات لأول مرة",
    OpportunityStatus.PAUSED_AT_CAPTCHA: "متوقف عند CAPTCHA / تسجيل دخول",
    OpportunityStatus.APPLICATION_FAILED: "فشل تجهيز/تقديم الطلب",
    OpportunityStatus.VERIFIED_ELIGIBLE: "مؤهل وجاهز للتقديم",
}


class ZCOEngineController:
    """High-level controller orchestrating the 6-hour audit, Memory Vault, and Real Chromium Auto-Applicant."""

    def __init__(
        self,
        db_path: pathlib.Path = DEFAULT_DB_PATH,
        dashboard_path: pathlib.Path = DEFAULT_DASHBOARD_PATH,
    ) -> None:
        self.db = OpportunityDatabase(db_path)
        self.vault = CandidateMemoryVault(self.db)
        self.applicant = AutonomousApplicantEngine(self.db, self.vault)
        self.dashboard_path = dashboard_path
        self.dashboard_path.parent.mkdir(parents=True, exist_ok=True)

    def get_crawler_daemon_status(self) -> Dict[str, Any]:
        status = self.db.get_daemon_status_summary()
        status["known_vault_fields"] = self.vault.get_known_fields()
        return status

    def run_six_hour_batch_audit(
        self,
        window_hours: float = 6.0,
        auto_apply: bool = False,
        allow_submit: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Audit queued opportunities and optionally prepare/submit applications.

        ``auto_apply`` only controls whether applications are prepared at all.
        Clicking Submit additionally requires ``allow_submit=True`` (or the
        ``ZCO_AUTO_SUBMIT=1`` environment opt-in). The default is draft-only.
        """
        if allow_submit is None:
            allow_submit = os.environ.get("ZCO_AUTO_SUBMIT", "0").strip() == "1"
        batch = self.db.fetch_unprocessed_batch(window_hours=window_hours, limit=200)
        verified_codes: List[str] = []
        rejected_cost: List[Dict[str, str]] = []
        rejected_ineligible: List[Dict[str, str]] = []

        for opp in batch:
            cost_res, elig_res = audit_opportunity_record(opp)
            opp_code = opp.get("opportunity_code") or f"ID-{opp['id']}"

            if not cost_res.is_zero_cost_compliant:
                self.db.commit_audit_verdict(
                    opportunity_id=opp["id"],
                    status=OpportunityStatus.REJECTED_COST,
                    match_score=0,
                    matched_jurisdiction_track="",
                    visa_support_summary=cost_res.visa_support_summary,
                    financial_coverage=dataclasses.asdict(cost_res),
                    rejection_reason=cost_res.rejection_reason,
                )
                rejected_cost.append(
                    {
                        "code": opp_code,
                        "title": opp["title"],
                        "reason": cost_res.rejection_reason,
                    }
                )
                continue

            if not elig_res.is_eligible:
                self.db.commit_audit_verdict(
                    opportunity_id=opp["id"],
                    status=OpportunityStatus.REJECTED_INELIGIBLE,
                    match_score=0,
                    matched_jurisdiction_track="",
                    visa_support_summary=cost_res.visa_support_summary,
                    financial_coverage=dataclasses.asdict(cost_res),
                    rejection_reason=elig_res.rejection_reason,
                )
                rejected_ineligible.append(
                    {
                        "code": opp_code,
                        "title": opp["title"],
                        "reason": elig_res.rejection_reason,
                    }
                )
                continue

            self.db.commit_audit_verdict(
                opportunity_id=opp["id"],
                status=OpportunityStatus.VERIFIED_ELIGIBLE,
                match_score=elig_res.match_score,
                matched_jurisdiction_track=elig_res.matched_jurisdiction_track,
                visa_support_summary=cost_res.visa_support_summary,
                financial_coverage=dataclasses.asdict(cost_res),
                rejection_reason="",
                audit_notes=elig_res.audit_notes,
            )
            verified_codes.append(opp_code)

        application_report: Dict[str, Any] = {}
        if auto_apply:
            application_report = self.applicant.process_all_pending_applications(
                allow_submit=bool(allow_submit)
            )

        dashboard_file = self.render_categorized_dashboard(
            consolidated_questions=application_report.get("consolidated_questions_for_user", [])
        )
        return {
            "window_hours": window_hours,
            "batch_size_audited": len(batch),
            "verified_eligible_count": len(verified_codes),
            "verified_codes": verified_codes,
            "rejected_cost_count": len(rejected_cost),
            "rejected_cost_items": rejected_cost,
            "rejected_ineligible_count": len(rejected_ineligible),
            "rejected_ineligible_items": rejected_ineligible,
            "submit_enabled": bool(auto_apply and allow_submit),
            "autonomous_application_report": application_report,
            "dashboard_path": str(dashboard_file),
        }

    def learn_and_resume_applications(
        self,
        user_answers: Dict[str, str],
        allow_submit: bool = False,
    ) -> Dict[str, Any]:
        learn_summary = self.vault.learn_from_user_answers(user_answers)
        application_report = self.applicant.process_all_pending_applications(
            allow_submit=allow_submit
        )
        dashboard_file = self.render_categorized_dashboard(
            consolidated_questions=application_report.get("consolidated_questions_for_user", [])
        )
        return {
            "vault_learning_summary": learn_summary,
            "autonomous_application_report": application_report,
            "dashboard_path": str(dashboard_file),
        }

    @staticmethod
    def _clean_display_url(item: Dict[str, Any]) -> str:
        import urllib.parse
        url = item.get("apply_url", "")
        if url.startswith("file://"):
            url = item.get("source_url", "https://www.frim.gov.my/")

        # Strip google search or redirect wrappers
        if "google.com/search?q=" in url or "google.com/url?q=" in url:
            try:
                parsed = urllib.parse.urlparse(url)
                params = urllib.parse.parse_qs(parsed.query)
                target = params.get("q", [None])[0] or params.get("url", [None])[0]
                if target and target.startswith("http"):
                    url = target
            except Exception:
                pass
        return url

    def render_categorized_dashboard(
        self,
        is_inside_malaysia: Optional[bool] = None,
        track_category: Optional[str] = None,
        consolidated_questions: Optional[List[Dict[str, Any]]] = None,
    ) -> pathlib.Path:
        all_verified = self.db.get_verified_opportunities(
            is_inside_malaysia=is_inside_malaysia,
            track_category=track_category,
        )
        inside_my = [o for o in all_verified if bool(o["is_inside_malaysia"])]
        outside_my = [o for o in all_verified if not bool(o["is_inside_malaysia"])]
        status_info = self.db.get_daemon_status_summary()
        known_vault = self.vault.get_known_fields()
        now_my_str = (
            dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M MYT")
        )

        applied_count = status_info["queue_counts"].get(OpportunityStatus.APPLIED_AUTOMATICALLY, 0)
        unconfirmed_count = status_info["queue_counts"].get(OpportunityStatus.SUBMITTED_UNCONFIRMED, 0)
        ready_count = status_info["queue_counts"].get(OpportunityStatus.READY_FOR_REVIEW, 0)
        paused_count = status_info["queue_counts"].get(OpportunityStatus.PAUSED_NEEDS_USER_INPUT, 0)

        lines: List[str] = [
            "# لوحة الفرص والتجهيز الذاتي عبر المتصفح الحقيقي (ZCO-Engine Production Matrix)",
            "",
            f"* **المرشح:** محمد مهدي (الجنسية: سوري | الإقامة الأكاديمية: ماليزيا - طالب ذكاء اصطناعي سنة أولى في [UTM](https://www.utm.my/) | الإقامة الثانية: الكويت | العمر: 20 سنة)",
            f"* **آخر دورة فحص وتجهيز (6-Hour Batch Audit & Chromium Applicant):** `{now_my_str}`",
            f"* **حالة التقديم:** مؤكد رسمياً: `{applied_count}` | أُرسل بانتظار تأكيد: `{unconfirmed_count}` | جاهز لمراجعة بشرية: `{ready_count}` | بانتظار بيانات تُطلب لأول مرة: `{paused_count}` | الحقول المحفوظة في خزنة الذاكرة الدائمة (`CandidateMemoryVault`): `{len(known_vault)} حقل`",
            f"* **إحصائيات الفلترة:** إجمالي المرصود `{status_info['total_tracked']}` | مرفوض لوجود رسوم/نقص تمويل: `{status_info['queue_counts'].get('REJECTED_COST', 0)}` | مرفوض لعدم تطابق الأهلية: `{status_info['queue_counts'].get('REJECTED_INELIGIBLE', 0)}`",
            "",
        ]

        if consolidated_questions:
            lines.extend(
                [
                    "## تنبيه الذاكرة المتعلمة: بيانات مطلوبة لأول مرة فقط (One-Time Vault Questions)",
                    "واجه محرك التقديم التلقائي الحقول التالية غير الموجودة بعد في خزنتك؛ بمجرد تزويده بها مرة واحدة سيحفظها للأبد ويكمل التقديم على جميع الفرص المعلقة تلقائياً ولن يسألك عنها مجدداً:",
                    "",
                    "| مفتاح الحقل (`field_key`) | البيان المطلوب (يُطلب مرة واحدة فقط) | الفرص المتوقفة بانتظاره |",
                    "| :--- | :--- | :--- |",
                ]
            )
            for q in consolidated_questions:
                codes_str = ", ".join(f"`{c}`" for c in q["needed_by_opportunities"])
                lines.append(f"| `{q['field_key']}` | {q['label_ar']} | {codes_str} |")
            lines.append("")

        lines.extend(
            [
                "## أولاً: الفرص داخل ماليزيا (Inside Malaysia — Domestic, Borneo & ASEAN Hub)",
                "لا تتطلب فيزا سفر دولية؛ جميعها مجانية التقديم (0 رسوم) وتغطي السكن والوجبات والمواصلات الداخلية (أو الطيران الداخلي لبورنيو):",
                "",
            ]
        )

        if not inside_my:
            lines.append("*لا توجد فرص مطابقة حالياً في هذا القسم.*")
            lines.append("")
        else:
            lines.extend(self._format_grouped_tables(inside_my, is_domestic=True))

        lines.extend(
            [
                "## ثانياً: الفرص خارج ماليزيا (Outside Malaysia — 100% Funded International from KUL)",
                "تشمل تذاكر الطيران ذهاباً وإياباً من كوالالمبور (`KUL`) + السكن الكامل + الوجبات/المخصص اليومي + دعم الفيزا + 0 رسوم تقديم:",
                "",
            ]
        )

        if not outside_my:
            lines.append("*لا توجد فرص مطابقة حالياً في هذا القسم.*")
            lines.append("")
        else:
            lines.extend(self._format_grouped_tables(outside_my, is_domestic=False))

        self.dashboard_path.write_text("\n".join(lines), encoding="utf-8")
        return self.dashboard_path

    def _format_grouped_tables(
        self, opportunities: List[Dict[str, Any]], is_domestic: bool
    ) -> List[str]:
        out: List[str] = []
        for track_key, track_title_ar in TRACK_LABELS_AR.items():
            track_items = [o for o in opportunities if o["track_category"] == track_key]
            if not track_items:
                continue
            out.append(f"### {track_title_ar}")
            out.append("")
            if is_domestic:
                out.append(
                    "| الكود | اسم الفرصة والجهة المنظمة | المدينة | التغطية الشاملة (0 رسوم) | حالة التقديم التلقائي ورقم الإيصال | آخر موعد | التطابق |"
                )
                out.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
                for item in track_items:
                    cov = json.loads(item.get("financial_coverage_json") or "{}")
                    cov_text, _cov_known = coverage_summary(cov)
                    status_str = self._format_application_status_cell(item)
                    disp_url = self._clean_display_url(item)
                    title_link = f"[{item['title']}]({disp_url}) — *{item['organizer']}*"
                    out.append(
                        f"| `{item['opportunity_code']}` | {title_link} | {item['location_city']} | {cov_text} | {status_str} | `{item['deadline_iso']}` | **{item['match_score']}%** |"
                    )
            else:
                out.append(
                    "| الكود | اسم الفرصة والدولة | التغطية الشاملة (من KUL) | مسار الأهلية والفيزا | حالة التقديم التلقائي ورقم الإيصال | آخر موعد | التطابق |"
                )
                out.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
                for item in track_items:
                    cov = json.loads(item.get("financial_coverage_json") or "{}")
                    cov_text, _cov_known = coverage_summary(cov)
                    status_str = self._format_application_status_cell(item)
                    elig_visa = f"{item['matched_jurisdiction_track']} ({item['visa_support_summary']})"
                    disp_url = self._clean_display_url(item)
                    title_link = f"[{item['title']}]({disp_url}) — **{item['location_country']}** ({item['location_city']})"
                    out.append(
                        f"| `{item['opportunity_code']}` | {title_link} | {cov_text} | {elig_visa} | {status_str} | `{item['deadline_iso']}` | **{item['match_score']}%** |"
                    )
            out.append("")
        return out

    @staticmethod
    def _format_application_status_cell(item: Dict[str, Any]) -> str:
        st = item.get("status", "")
        badge = STATUS_BADGES_AR.get(st, st)
        if st == OpportunityStatus.APPLIED_AUTOMATICALLY:
            receipt = json.loads(item.get("submission_receipt_json") or "{}")
            ref = receipt.get("confirmation_ref", "")
            return f"**{badge}** (`{ref}`)"
        if st == OpportunityStatus.SUBMITTED_UNCONFIRMED:
            receipt = json.loads(item.get("submission_receipt_json") or "{}")
            note = receipt.get("notes", "")
            return f"{badge}" + (f": {note}" if note else "")
        if st == OpportunityStatus.PAUSED_NEEDS_USER_INPUT:
            missing = json.loads(item.get("missing_fields_json") or "[]")
            keys = ", ".join(f"`{m['field_key']}`" for m in missing)
            return f"{badge}: {keys}"
        return badge

    def prepare_application_kit(self, opportunity_code: str) -> Dict[str, Any]:
        opp = self.db.get_opportunity_by_code(opportunity_code)
        if not opp:
            return {
                "status": "error",
                "message": f"Opportunity code '{opportunity_code}' not found in database.",
            }

        known = self.vault.get_known_fields()
        cov = json.loads(opp.get("financial_coverage_json") or "{}")
        motivation_letter = self.applicant.synthesize_motivation_statement(opp, known)

        return {
            "status": "ok",
            "opportunity_code": opp["opportunity_code"],
            "title": opp["title"],
            "organizer": opp["organizer"],
            "apply_url": self._clean_display_url(opp),
            "application_status": opp["status"],
            "submission_receipt": json.loads(opp.get("submission_receipt_json") or "{}"),
            "vault_filled_fields": known,
            "financial_coverage": cov,
            "tailored_motivation_letter": motivation_letter,
        }

    def synthesize_tailored_cv(self, opportunity_code: str, force: bool = False) -> Dict[str, Any]:
        opp = self.db.get_opportunity_by_code(opportunity_code)
        if not opp:
            return {"status": "error", "message": f"Opportunity '{opportunity_code}' not found."}
        from typst_agentic_cv_engine import synthesize_tailored_typst_cv
        return synthesize_tailored_typst_cv(opp, force=force)

    def synthesize_base_reference_cv(self, force: bool = False) -> Dict[str, Any]:
        from typst_agentic_cv_engine import synthesize_base_reference_typst_cv
        return synthesize_base_reference_typst_cv(force_recompile=force)

    def approve_and_submit_opportunity(
        self, opportunity_code: str, force_resubmit: bool = False
    ) -> Dict[str, Any]:
        opp = self.db.get_opportunity_by_code(opportunity_code)
        if not opp:
            return {"status": "error", "message": f"Opportunity '{opportunity_code}' not found."}
        from typst_agentic_cv_engine import is_cv_required_for_opportunity, synthesize_tailored_typst_cv
        cv_required, reason = is_cv_required_for_opportunity(opp)
        cv_info = None
        if cv_required:
            cv_res = synthesize_tailored_typst_cv(opp, force=True)
            if cv_res.get("status") != "generated" or not cv_res.get("pdf_path"):
                return {
                    "status": "failed",
                    "opportunity_code": opportunity_code,
                    "cv_required": True,
                    "cv_reason": reason,
                    "cv_generated": cv_res,
                    "message": "تعذر توليد السيرة الذاتية المطلوبة؛ لم يتم تقديم الطلب.",
                }
            self.vault.set_known_field("cv_pdf_path", cv_res["pdf_path"])
            cv_info = cv_res
        app_res = self.applicant.attempt_auto_application(
            opp, allow_submit=True, force_resubmit=force_resubmit
        )
        return {
            "status": app_res.get("application_status", "unknown"),
            "opportunity_code": opportunity_code,
            "cv_required": cv_required,
            "cv_reason": reason,
            "cv_generated": cv_info,
            "application_result": app_res,
        }

    def inspect_vault_profile(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "known_fields": self.vault.get_known_fields(),
            "fields_count": len(self.vault.get_known_fields()),
        }


def create_mcp_app(controller: ZCOEngineController) -> Any:
    try:
        from mcp.server.fastmcp import FastMCP  # type: ignore

        mcp = FastMCP("zco-opportunity-engine-v4")

        @mcp.tool()
        def get_crawler_daemon_status() -> Dict[str, Any]:
            """Returns the 24/7 background crawler heartbeat, queue counts, and Memory Vault fields."""
            return controller.get_crawler_daemon_status()

        @mcp.tool()
        def run_six_hour_batch_audit(
            window_hours: float = 6.0, allow_submit: bool = False
        ) -> Dict[str, Any]:
            """Audits RAW_INGESTED items and prepares applications from the Memory Vault.

            Submit clicks stay disabled unless ``allow_submit=True`` or the daemon runs
            with the explicit ``ZCO_AUTO_SUBMIT=1`` opt-in.
            """
            return controller.run_six_hour_batch_audit(
                window_hours=window_hours,
                auto_apply=True,
                allow_submit=allow_submit,
            )

        @mcp.tool()
        def provide_missing_answers_and_resume(
            answers_json: str, allow_submit: bool = False
        ) -> Dict[str, Any]:
            """
            Saves new user-provided answers permanently into CandidateMemoryVault (never asking again)
            and resumes paused applications. Submission requires ``allow_submit=True``.
            """
            answers_dict = json.loads(answers_json)
            return controller.learn_and_resume_applications(
                answers_dict, allow_submit=allow_submit
            )

        @mcp.tool()
        def render_categorized_dashboard(
            location_scope: str = "ALL", track_filter: str = ""
        ) -> str:
            """Renders verified_opportunities_matrix.md split by Inside/Outside Malaysia and Track."""
            inside_my: Optional[bool] = None
            if location_scope.upper() == "INSIDE_MY":
                inside_my = True
            elif location_scope.upper() == "OUTSIDE_MY":
                inside_my = False
            path = controller.render_categorized_dashboard(
                is_inside_malaysia=inside_my,
                track_category=track_filter or None,
            )
            return path.read_text(encoding="utf-8")

        @mcp.tool()
        def prepare_application_kit(opportunity_code: str) -> Dict[str, Any]:
            """Inspects the submission payload, receipt, and motivation letter for an opportunity code."""
            return controller.prepare_application_kit(opportunity_code)

        @mcp.tool()
        def synthesize_tailored_cv(opportunity_code: str, force: bool = False) -> Dict[str, Any]:
            """
            Synthesizes a vacancy-adapted 1-page ATS Typst CV for the given opportunity code,
            deeply tailored to the opportunity domain, with strict sanitization (0 matric number,
            0 t-shirt size, and 0 unsolicited GitHub).
            """
            return controller.synthesize_tailored_cv(opportunity_code, force=force)

        @mcp.tool()
        def synthesize_base_reference_cv(force: bool = False) -> Dict[str, Any]:
            """
            Synthesizes or returns the Master Reference 1-page ATS Typst CV for Mohammad Mahdi,
            strictly sanitized (no matric number, no t-shirt size, no unsolicited GitHub).
            """
            return controller.synthesize_base_reference_cv(force=force)

        @mcp.tool()
        def approve_and_submit_opportunity(
            opportunity_code: str, force_resubmit: bool = False
        ) -> Dict[str, Any]:
            """
            Approves and submits the application for an opportunity.
            If a CV is required, automatically synthesizes a tailored Typst CV first,
            injects it into the vault, applies, and returns the submission receipt.
            Already-submitted opportunities are blocked unless ``force_resubmit`` is true.
            """
            return controller.approve_and_submit_opportunity(
                opportunity_code, force_resubmit=force_resubmit
            )

        @mcp.tool()
        def inspect_vault_profile() -> Dict[str, Any]:
            """Returns the current candidate profile and learned Memory Vault fields."""
            return controller.inspect_vault_profile()

        return mcp
    except ImportError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ZCO-Engine v4.0 MCP Server, Real Chromium Auto-Applicant & Self-Learning Vault CLI"
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--dashboard-path",
        default=str(DEFAULT_DASHBOARD_PATH),
        help="Output path for verified_opportunities_matrix.md",
    )
    parser.add_argument(
        "--audit-batch",
        action="store_true",
        help="Run the 6-hour batch audit and prepare applications (no submission unless --auto-submit)",
    )
    parser.add_argument(
        "--auto-submit",
        action="store_true",
        default=os.environ.get("ZCO_AUTO_SUBMIT", "0").strip() == "1",
        help="Explicitly allow unattended Submit clicks (default: disabled; env ZCO_AUTO_SUBMIT=1)",
    )
    parser.add_argument(
        "--window-hours",
        type=float,
        default=6.0,
        help="Lookback window in hours for batch auditing (default: 6.0)",
    )
    parser.add_argument(
        "--learn-answers",
        type=str,
        default="",
        help="JSON dictionary of new field answers to store permanently in the Memory Vault and resume paused applications",
    )
    parser.add_argument(
        "--prepare-kit",
        type=str,
        default="",
        help="Inspect application kit & receipt for a specific opportunity code (e.g. MY-ECO-001)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print daemon heartbeat, queue status, and learned Vault fields as JSON",
    )
    parser.add_argument(
        "--synthesize-cv",
        type=str,
        default="",
        help="Synthesize vacancy-adapted 1-page Typst CV for an opportunity code",
    )
    parser.add_argument(
        "--base-cv",
        action="store_true",
        help="Synthesize and verify the Master Reference 1-page Typst CV",
    )
    parser.add_argument(
        "--approve",
        type=str,
        default="",
        help="Approve opportunity, synthesize CV if required, and submit application",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Print candidate profile and learned Memory Vault fields",
    )
    parser.add_argument(
        "--daemon-auditor",
        action="store_true",
        help="Run continuous background batch auditor loop every N hours",
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=6.0,
        help="Interval in hours for daemon auditor (default: 6.0)",
    )
    args = parser.parse_args()

    controller = ZCOEngineController(
        db_path=pathlib.Path(args.db_path),
        dashboard_path=pathlib.Path(args.dashboard_path),
    )

    if args.daemon_auditor:
        import time
        interval_sec = max(60.0, args.interval_hours * 3600.0)
        print(f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] Starting 6-Hour Periodic Opportunity Auditor Daemon (interval: {args.interval_hours}h, submit={args.auto_submit})...", flush=True)
        while True:
            try:
                print(f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] Running periodic batch audit...", flush=True)
                summary = controller.run_six_hour_batch_audit(
                    window_hours=args.interval_hours,
                    auto_apply=True,
                    allow_submit=args.auto_submit,
                )
                audited_count = summary.get("batch_size_audited", 0)
                verified_count = summary.get("verified_eligible_count", 0)
                report = summary.get("autonomous_application_report", {}) or {}
                applied_count = report.get("applied_automatically_count", 0)
                unconfirmed_count = report.get("submitted_unconfirmed_count", 0)
                ready_count = report.get("ready_for_review_count", 0)
                paused_count = report.get("paused_needs_input_count", 0)
                failed_count = report.get("application_failed_count", 0)
                print(
                    f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] Batch audit completed. "
                    f"Audited: {audited_count} | Eligible: {verified_count} | "
                    f"Confirmed applied: {applied_count} | Unconfirmed: {unconfirmed_count} | "
                    f"Ready for review: {ready_count} | Paused for inputs: {paused_count} | Failed: {failed_count}",
                    flush=True,
                )
            except Exception as exc:
                print(f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] Error in batch audit daemon loop: {exc}", flush=True)
            time.sleep(interval_sec)
        return

    if args.status:
        print(json.dumps(controller.get_crawler_daemon_status(), indent=2, ensure_ascii=False))
        return

    if args.profile:
        print(json.dumps(controller.inspect_vault_profile(), indent=2, ensure_ascii=False))
        return

    if args.base_cv:
        print(json.dumps(controller.synthesize_base_reference_cv(force=True), indent=2, ensure_ascii=False))
        return

    if args.synthesize_cv:
        print(json.dumps(controller.synthesize_tailored_cv(args.synthesize_cv, force=True), indent=2, ensure_ascii=False))
        return

    if args.approve:
        print(json.dumps(controller.approve_and_submit_opportunity(args.approve), indent=2, ensure_ascii=False))
        return

    if args.learn_answers:
        parsed_answers = json.loads(args.learn_answers)
        res = controller.learn_and_resume_applications(
            parsed_answers, allow_submit=args.auto_submit
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    if args.audit_batch:
        summary = controller.run_six_hour_batch_audit(
            window_hours=args.window_hours,
            auto_apply=True,
            allow_submit=args.auto_submit,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    if args.prepare_kit:
        kit = controller.prepare_application_kit(args.prepare_kit)
        print(json.dumps(kit, indent=2, ensure_ascii=False))
        return

    mcp_app = create_mcp_app(controller)
    if mcp_app is not None:
        mcp_app.run()
    else:
        print(
            json.dumps(
                {
                    "info": "FastMCP package not detected in current Python env; running CLI status check.",
                    "status": controller.get_crawler_daemon_status(),
                },
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()