#!/usr/bin/env python3
"""
Unit and Integration Test Suite for ZCO-Engine v4.0
===================================================
Tests all core components:
1. OpportunityDatabase (schema, ingest, dedup, status transitions, vault)
2. ZeroCostGatekeeper ($0 fees + flights + accommodation + meals vs fee traps)
3. TriJurisdictionEligibilityEngine (SY + MY UTM AI Student + KW Iqama)
4. CandidateMemoryVault (learning, persistence, profile JSON synchronization)
5. DeepPageAndPdfInspector & PdfGuidelinesExtractor (form introspection, PDF text)
6. RealBrowserFormAutoFiller (Headless Chromium form filling and submission)
7. AutonomousApplicantEngine (automatic apply vs pause on missing fields)
8. ZCOEngineController (batch audit, status, matrix rendering)
"""

import json
import pathlib
import sys
import tempfile
import pytest

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database import OpportunityDatabase, OpportunityStatus, RawOpportunityRecord
from engines_and_auditor import (
    AutonomousApplicantEngine,
    CandidateMemoryVault,
    DeepPageAndPdfInspector,
    PdfGuidelinesExtractor,
    RealBrowserFormAutoFiller,
    TriJurisdictionEligibilityEngine,
    ZeroCostGatekeeper,
    audit_opportunity_record,
)
from server import ZCOEngineController


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_opps.db"
    return OpportunityDatabase(db_file)


def test_database_initialization_and_ingestion(temp_db):
    rec = RawOpportunityRecord(
        title="Test ASEAN AI Fellowship",
        organizer="ASEAN AI Network",
        source_url="https://example.org/source",
        apply_url="https://example.org/apply",
        location_country="Malaysia",
        location_city="Kuala Lumpur",
        is_inside_malaysia=True,
        track_category="CORE_AI_HACKATHONS",
        raw_description="A fully funded fellowship for AI undergraduates.",
        raw_terms_text="0 application fee, accommodation and meals fully covered.",
        deadline_iso="2027-01-01",
        source_feed_id="test_feed",
    )
    inserted_id = temp_db.ingest_raw_opportunity(rec)
    assert inserted_id is not None
    assert inserted_id > 0

    # Test deduplication
    duplicate_id = temp_db.ingest_raw_opportunity(rec)
    assert duplicate_id is None

    # Verify query
    queued = temp_db.fetch_unprocessed_batch(window_hours=24.0)
    assert len(queued) == 1
    assert queued[0]["title"] == "Test ASEAN AI Fellowship"


def test_zero_cost_gatekeeper():
    gatekeeper = ZeroCostGatekeeper()

    # Valid fully funded inside Malaysia
    valid_my = {
        "is_inside_malaysia": 1,
        "raw_description": "Fully funded conservation camp in Borneo. Free registration.",
        "raw_terms_text": "No application fee ($0). Domestic flight included, eco-lodge accommodation and meals provided.",
    }
    res_my = gatekeeper.audit(valid_my)
    assert res_my.is_zero_cost_compliant is True
    assert res_my.application_fee_zero is True
    assert res_my.flights_or_transport_covered is True

    # Trap: Non-refundable fee
    trap_fee = {
        "is_inside_malaysia": 0,
        "raw_description": "International Youth Forum.",
        "raw_terms_text": "Non-refundable $45 application fee required to process your admission.",
    }
    res_trap = gatekeeper.audit(trap_fee)
    assert res_trap.is_zero_cost_compliant is False
    assert "تم رصد شرط مالي غير مجاني" in res_trap.rejection_reason

    # Missing flights
    no_flight = {
        "is_inside_malaysia": 0,
        "raw_description": "Fully funded camp in Europe. No application fee.",
        "raw_terms_text": "Accommodation and meals covered. Participants must cover their own international flight.",
    }
    res_no_flight = gatekeeper.audit(no_flight)
    assert res_no_flight.is_zero_cost_compliant is False


def test_tri_jurisdiction_eligibility_engine():
    engine = TriJurisdictionEligibilityEngine()

    # Eligible: Malaysia UTM Student
    opp_utm = {
        "title": "UTM National AI Hackathon",
        "is_inside_malaysia": 1,
        "track_category": "CORE_AI_HACKATHONS",
        "raw_description": "Open to all undergraduate students residing in Malaysia with a valid Student Pass at UTM.",
        "raw_terms_text": "Fully funded for UTM students.",
    }
    res_utm = engine.evaluate(opp_utm)
    assert res_utm.is_eligible is True
    assert "إقامة طالب في ماليزيا" in res_utm.matched_jurisdiction_track

    # Eligible: Syrian National / Developing Countries
    opp_sy = {
        "title": "Euro-Med Youth Climate Summit",
        "is_inside_malaysia": 0,
        "track_category": "GREEN_AI_CLIMATE_TECH",
        "raw_description": "Open to youth from Mediterranean partner countries and Syria / Developing Countries.",
        "raw_terms_text": "Round-trip flights from KUL provided, full visa support.",
    }
    res_sy = engine.evaluate(opp_sy)
    assert res_sy.is_eligible is True
    assert "الجنسية السورية" in res_sy.matched_jurisdiction_track

    # Ineligible: PhD only
    opp_phd = {
        "title": "Senior Postdoc Fellowship",
        "is_inside_malaysia": 0,
        "track_category": "CORE_AI_HACKATHONS",
        "raw_description": "Strictly restricted to PhD holders.",
        "raw_terms_text": "Doctoral degree required.",
    }
    res_phd = engine.evaluate(opp_phd)
    assert res_phd.is_eligible is False
    assert "دكتوراه" in res_phd.rejection_reason


def test_candidate_memory_vault_learning(temp_db, tmp_path):
    profile_json = tmp_path / "candidate_profile.json"
    vault = CandidateMemoryVault(temp_db, profile_json_path=profile_json)

    # Initial seed should exist
    known = vault.get_known_fields()
    assert "full_name" in known
    assert known["full_name"] == "Mohammad Mahdi"
    assert known["nationality"] == "Syrian (SY)"

    # Learn new fields
    new_answers = {
        "email_address": "mohammad.mahdi@graduate.utm.my",
        "phone_whatsapp_my": "***REMOVED-PHONE***",
        "tshirt_and_gear_size": "L",
    }
    learn_res = vault.learn_from_user_answers(new_answers)
    assert learn_res["learned_fields_count"] == 3

    # Check updated known fields
    updated_known = vault.get_known_fields()
    assert updated_known["email_address"] == "mohammad.mahdi@graduate.utm.my"
    assert updated_known["tshirt_and_gear_size"] == "L"

    # Verify JSON synchronization
    assert profile_json.exists()
    saved_profile = json.loads(profile_json.read_text(encoding="utf-8"))
    assert "learned_memory_vault" in saved_profile
    assert saved_profile["learned_memory_vault"]["email_address"] == "mohammad.mahdi@graduate.utm.my"


def test_pdf_guidelines_extractor():
    pdf_path = BASE_DIR / "data" / "documents" / "cv_mohammad_mahdi.pdf"
    if not pdf_path.exists():
        from typst_agentic_cv_engine import synthesize_base_reference_typst_cv
        res = synthesize_base_reference_typst_cv()
        pdf_path = pathlib.Path(res["pdf_path"])
    assert pdf_path.exists()
    text = PdfGuidelinesExtractor.extract_text_from_pdf_path_or_url(str(pdf_path))
    assert "UTM" in text or "Universiti Teknologi Malaysia" in text


def test_html_form_introspection():
    html_content = """
    <html>
      <head><title>Test Hackathon Application</title></head>
      <body>
        <form>
          <label for="name_input">Full Name</label>
          <input type="text" id="name_input" name="full_name" required />
          <label for="email_input">Official Email</label>
          <input type="email" id="email_input" name="email_address" required />
          <label for="cv_file">Upload CV (PDF)</label>
          <input type="file" id="cv_file" name="applicant_cv" required />
          <label><input type="checkbox" id="terms" name="agree_terms" required /> Agree to terms</label>
          <button type="submit">Submit</button>
        </form>
      </body>
    </html>
    """
    report = DeepPageAndPdfInspector.inspect_html_content(html_content, base_url="https://example.org/apply")
    assert report.page_title == "Test Hackathon Application"
    assert "full_name" in report.required_vault_keys
    assert "email_address" in report.required_vault_keys
    assert "cv_pdf_path" in report.required_vault_keys
    assert report.has_captcha_or_login_wall is False


def test_real_browser_form_auto_filler(tmp_path):
    portal_path = BASE_DIR / "data" / "live_portals" / "frim_green_ai_portal.html"
    assert portal_path.exists()

    filler = RealBrowserFormAutoFiller(screenshots_dir=tmp_path / "screenshots")
    vault_values = {
        "full_name": "Mohammad Mahdi",
        "email_address": "mohammad.mahdi@graduate.utm.my",
        "phone_whatsapp_my": "***REMOVED-PHONE***",
        "nationality": "Syrian (SY)",
        "university_name": "Universiti Teknologi Malaysia (UTM)",
        "degree_and_major": "Bachelor of Artificial Intelligence",
        "current_cgpa": "3.92 / 4.00",
        "github_or_portfolio_url": "https://github.com/mohammad-mahdi-ai",
    }
    receipt = filler.fill_and_submit_application(
        opportunity_code="TEST-MY-GAI",
        apply_url=f"file://{portal_path.resolve()}",
        vault_values=vault_values,
        tailored_motivation_essay="I want to leverage AI acoustics to protect Malaysian rainforests.",
        auto_click_submit=True,
    )
    assert receipt.status == "APPLIED_AUTOMATICALLY"
    assert "REF-FRIM-GAI-2027-8841" in receipt.confirmation_reference
    assert pathlib.Path(receipt.pre_submit_screenshot_path).exists()
    assert pathlib.Path(receipt.post_submit_screenshot_path).exists()
    assert receipt.filled_dom_fields_count >= 8


def test_full_controller_batch_and_dashboard(tmp_path):
    db_file = tmp_path / "test_ctrl.db"
    dashboard_file = tmp_path / "verified_opportunities_matrix.md"
    controller = ZCOEngineController(db_path=db_file, dashboard_path=dashboard_file)

    # Ingest a seed item
    rec = RawOpportunityRecord(
        title="Malaysia Green-AI Rainforest Hackathon 2027",
        organizer="FRIM & AI Malaysia",
        source_url="https://www.frim.gov.my/",
        apply_url=f"file://{(BASE_DIR / 'data' / 'live_portals' / 'frim_green_ai_portal.html').resolve()}",
        location_country="Malaysia",
        location_city="Kuala Lumpur",
        is_inside_malaysia=True,
        track_category="GREEN_AI_CLIMATE_TECH",
        raw_description="Fully funded hackathon for UTM AI undergraduates.",
        raw_terms_text="0 application fee ($0), hotel and meals covered.",
        deadline_iso="2026-12-05",
        source_feed_id="test_gai",
    )
    controller.db.ingest_raw_opportunity(rec)

    # First audit: should verify eligible but pause because custom contact fields are missing
    audit_res1 = controller.run_six_hour_batch_audit(window_hours=24.0, auto_apply=True)
    assert audit_res1["verified_eligible_count"] == 1
    report1 = audit_res1["autonomous_application_report"]
    assert report1["paused_needs_input_count"] == 1

    # Learn the missing contact fields
    answers = {
        "email_address": "mohammad.mahdi@graduate.utm.my",
        "phone_whatsapp_my": "***REMOVED-PHONE***",
        "github_or_portfolio_url": "https://github.com/mohammad-mahdi-ai",
        "current_cgpa": "3.92 / 4.00",
    }
    learn_res = controller.learn_and_resume_applications(answers)
    report2 = learn_res["autonomous_application_report"]
    assert report2["applied_automatically_count"] == 1
    assert report2["paused_needs_input_count"] == 0

    # Verify dashboard file generated
    assert dashboard_file.exists()
    content = dashboard_file.read_text(encoding="utf-8")
    assert "تم التقديم تلقائياً" in content
    assert "FRIM" in content
