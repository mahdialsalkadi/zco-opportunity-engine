#!/usr/bin/env python3
"""Phase 0 regression tests: containment, auth, escaping, and receipt honesty."""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DASHBOARD_AUTH_TOKEN", "phase0-test-token")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_IDS", "12345")

from database import OpportunityDatabase, OpportunityStatus, RawOpportunityRecord
from engines_and_auditor import (
    AutonomousApplicantEngine,
    BrowserSubmissionReceipt,
    CandidateMemoryVault,
)


def _ingest_opp(db: OpportunityDatabase, **overrides) -> dict:
    values = dict(
        title="Beach Cleanup Volunteer Day",
        organizer="Community Group",
        source_url="https://example.org/cleanup",
        apply_url="https://example.org/apply",
        location_country="Malaysia",
        location_city="Kuala Lumpur",
        is_inside_malaysia=True,
        track_category="COMMUNITY_VOLUNTEERING_EXCHANGE",
        raw_description="Join a weekend beach cleanup. No fee.",
        raw_terms_text="Free to join.",
        deadline_iso="2027-01-01",
        source_feed_id="phase0-test",
    )
    values.update(overrides)
    if "required_form_fields_json" in values:
        values["required_form_fields"] = json.loads(values.pop("required_form_fields_json"))
    db.ingest_raw_opportunity(RawOpportunityRecord(**values))
    rows = db.get_opportunities_by_status(OpportunityStatus.RAW_INGESTED)
    assert rows
    return rows[-1]


class _FakeFiller:
    def __init__(self, receipt: BrowserSubmissionReceipt) -> None:
        self.receipt = receipt
        self.calls = 0

    def fill_and_submit_application(self, **kwargs):
        self.calls += 1
        return self.receipt

    def inspect_live_url_with_browser(self, url):  # pragma: no cover - not used
        raise AssertionError("not expected for https URLs")


def _receipt(status: str, ref: str = "") -> BrowserSubmissionReceipt:
    return BrowserSubmissionReceipt(
        status=status,
        confirmation_reference=ref,
        confirmation_page_text="",
        pre_submit_screenshot_path="",
        post_submit_screenshot_path="",
        filled_dom_fields_count=1,
        uploaded_files_count=0,
        notes="test receipt",
    )


def test_telegram_admin_allowlist_parsing(monkeypatch):
    from telegram_bot import _parse_admin_chat_ids, load_bot_config

    assert _parse_admin_chat_ids("123, 456;789") == [123, 456, 789]
    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_IDS", "111,222")
    assert load_bot_config()["admin_chat_ids"] == [111, 222]


def test_telegram_denies_unknown_chat(tmp_path, monkeypatch):
    from telegram_bot import ZCOTelegramBotService

    service = ZCOTelegramBotService(db_path=tmp_path / "tg.db")
    service.admin_chat_ids = [999]

    update = MagicMock()
    update.effective_chat.id = 123
    update.effective_user.username = "attacker"
    update.effective_user.first_name = "Attacker"
    update.callback_query = None
    update.effective_message.reply_text = AsyncMock()
    update.effective_message.text = "/start"

    asyncio.run(service.start_command(update, MagicMock()))

    assert update.effective_message.reply_text.await_count == 1
    sent = update.effective_message.reply_text.call_args[0][0]
    assert "خاص" in sent
    assert "123" in sent
    # Unknown chat must not be registered as a subscriber.
    assert service.db.get_telegram_subscribers() == []


def test_telegram_card_escapes_scraped_html():
    from telegram_bot import format_opportunity_card

    opp = {
        "id": 1,
        "opportunity_code": "TEST-1",
        "title": "<script>alert(1)</script>",
        "organizer": "<img src=x onerror=alert(2)>",
        "location_city": "KL",
        "location_country": "Malaysia",
        "is_inside_malaysia": 1,
        "match_score": 90,
        "status": OpportunityStatus.VERIFIED_ELIGIBLE,
        "deadline_iso": "2027-01-01",
        "apply_url": "javascript:alert(3)",
        "raw_description": "Cleanup",
        "financial_coverage_json": json.dumps({"coverage_summary_ar": "<b>free</b>"}),
    }
    text, _markup = format_opportunity_card(opp)

    assert "<script>" not in text
    assert "<img" not in text
    assert "&lt;script&gt;" in text
    assert "javascript:alert" not in text


def test_no_submit_without_explicit_permission(tmp_path):
    db = OpportunityDatabase(tmp_path / "no_submit.db")
    vault = CandidateMemoryVault(db)
    applicant = AutonomousApplicantEngine(db, vault)
    filler = _FakeFiller(_receipt("APPLIED_AUTOMATICALLY", "REF-SHOULD-NOT-BE-USED"))
    applicant.browser_filler = filler
    opp = _ingest_opp(db, required_form_fields_json='["full_name"]')

    result = applicant.attempt_auto_application(opp, allow_submit=False)

    assert result["application_status"] == OpportunityStatus.READY_FOR_REVIEW
    assert filler.calls == 0
    assert db.get_opportunity_by_code(opp["opportunity_code"])["status"] == OpportunityStatus.READY_FOR_REVIEW


@pytest.mark.parametrize(
    ("receipt_status", "ref", "expected"),
    [
        ("SUBMITTED_UNCONFIRMED", "", OpportunityStatus.SUBMITTED_UNCONFIRMED),
        ("APPLIED_AUTOMATICALLY", "", OpportunityStatus.SUBMITTED_UNCONFIRMED),
        ("PAUSED_AT_CAPTCHA", "", OpportunityStatus.PAUSED_AT_CAPTCHA),
        ("READY_FOR_SUBMISSION", "", OpportunityStatus.READY_FOR_REVIEW),
    ],
)
def test_receipt_status_mapping_never_fakes_success(tmp_path, receipt_status, ref, expected):
    db = OpportunityDatabase(tmp_path / f"{receipt_status}.db")
    vault = CandidateMemoryVault(db)
    applicant = AutonomousApplicantEngine(db, vault)
    applicant.browser_filler = _FakeFiller(_receipt(receipt_status, ref))
    opp = _ingest_opp(db, required_form_fields_json='["full_name"]')

    result = applicant.attempt_auto_application(opp, allow_submit=True)

    assert result["application_status"] == expected
    if expected != OpportunityStatus.APPLIED_AUTOMATICALLY:
        assert result["confirmation_ref"] == ""


def test_confirmed_receipt_is_kept(tmp_path):
    db = OpportunityDatabase(tmp_path / "confirmed.db")
    vault = CandidateMemoryVault(db)
    applicant = AutonomousApplicantEngine(db, vault)
    applicant.browser_filler = _FakeFiller(
        _receipt("APPLIED_AUTOMATICALLY", "REF-REAL-2027-0001")
    )
    opp = _ingest_opp(db, required_form_fields_json='["full_name"]')

    result = applicant.attempt_auto_application(opp, allow_submit=True)

    assert result["application_status"] == OpportunityStatus.APPLIED_AUTOMATICALLY
    assert result["confirmation_ref"] == "REF-REAL-2027-0001"


def test_cv_failure_blocks_submission(tmp_path, monkeypatch):
    db = OpportunityDatabase(tmp_path / "cv_fail.db")
    vault = CandidateMemoryVault(db)
    applicant = AutonomousApplicantEngine(db, vault)
    filler = _FakeFiller(_receipt("APPLIED_AUTOMATICALLY", "REF-CV-FAIL"))
    applicant.browser_filler = filler

    def _failed_cv(opp, force=True):
        return {"status": "failed", "pdf_path": None, "error": "typst missing"}

    monkeypatch.setattr(
        "typst_agentic_cv_engine.synthesize_tailored_typst_cv", _failed_cv
    )
    opp = _ingest_opp(
        db,
        title="Global Research Fellowship 2027",
        raw_description="Fellowship requiring a CV upload.",
        required_form_fields_json='["full_name", "cv_pdf_path"]',
    )

    result = applicant.attempt_auto_application(opp, allow_submit=True)

    assert result["application_status"] == OpportunityStatus.APPLICATION_FAILED
    assert filler.calls == 0


def test_quarantine_synthetic_receipts(tmp_path):
    db = OpportunityDatabase(tmp_path / "quarantine.db")
    opp = _ingest_opp(db)
    db.record_application_attempt(
        opportunity_id=opp["id"],
        opportunity_code=opp["opportunity_code"],
        new_status=OpportunityStatus.APPLIED_AUTOMATICALLY,
        filled_payload={"full_name": "Test"},
        missing_fields=[],
        confirmation_ref="DOM-SUB-TEST-ABCD1234",
    )

    preview = db.quarantine_unverified_submissions(dry_run=True)
    assert len(preview) == 1
    assert db.get_opportunity_by_code(opp["opportunity_code"])["status"] == OpportunityStatus.APPLIED_AUTOMATICALLY

    applied = db.quarantine_unverified_submissions()
    assert len(applied) == 1
    row = db.get_opportunity_by_code(opp["opportunity_code"])
    assert row["status"] == OpportunityStatus.SUBMITTED_UNCONFIRMED
    assert json.loads(row["submission_receipt_json"])["confirmation_ref"] == ""


def test_quarantine_local_testbed_receipts(tmp_path):
    db = OpportunityDatabase(tmp_path / "quarantine_testbed.db")
    opp = _ingest_opp(
        db,
        apply_url="file:///tmp/testbed.html",
        source_feed_id="local_testbed_portal",
    )
    db.record_application_attempt(
        opportunity_id=opp["id"],
        opportunity_code=opp["opportunity_code"],
        new_status=OpportunityStatus.APPLIED_AUTOMATICALLY,
        filled_payload={"full_name": "Test"},
        missing_fields=[],
        confirmation_ref="REF-FRIM-GAI-2027-8841",
    )

    applied = db.quarantine_unverified_submissions()
    assert len(applied) == 1
    row = db.get_opportunity_by_code(opp["opportunity_code"])
    assert row["status"] == OpportunityStatus.SUBMITTED_UNCONFIRMED
    receipt = json.loads(row["submission_receipt_json"])
    assert receipt["confirmation_ref"] == ""
    assert "testbed" in receipt["notes"].lower()
    with db.connect() as conn:
        history = conn.execute(
            "SELECT submission_status, confirmation_ref FROM application_submissions "
            "WHERE opportunity_id = ?",
            (opp["id"],),
        ).fetchall()
    assert history
    assert all(h["submission_status"] == OpportunityStatus.SUBMITTED_UNCONFIRMED for h in history)
    assert all(h["confirmation_ref"] == "" for h in history)


def test_dashboard_requires_auth_and_sets_cookie():
    from fastapi.testclient import TestClient
    import web_dashboard

    client = TestClient(web_dashboard.app)
    token = web_dashboard.DASHBOARD_AUTH_TOKEN

    assert client.get("/healthz").status_code == 200
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers={"X-Dashboard-Token": "wrong"}).status_code == 401
    ok = client.get("/api/status", headers={"X-Dashboard-Token": token})
    assert ok.status_code == 200

    page = client.get(f"/?token={token}")
    assert page.status_code == 200
    assert web_dashboard.AUTH_COOKIE_NAME in page.cookies

    cross_origin = client.post(
        "/api/audit",
        headers={"X-Dashboard-Token": token, "Origin": "https://evil.example"},
    )
    assert cross_origin.status_code == 403


def test_dashboard_html_uses_escaping_helpers():
    source = (BASE_DIR / "web_dashboard.py").read_text(encoding="utf-8")
    assert "function escHtml(" in source
    assert "function safeHttpUrl(" in source
    assert "${opp.title}" not in source
    assert "${opp.organizer}" not in source
    assert "${opp.explanation_ar}" not in source
