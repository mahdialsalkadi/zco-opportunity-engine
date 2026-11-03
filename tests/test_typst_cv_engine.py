import pathlib
import sys

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import pypdf
import pytest
from typst_agentic_cv_engine import (
    is_cv_required_for_opportunity,
    synthesize_tailored_typst_cv,
    synthesize_base_reference_typst_cv,
    JobDescriptionParser,
    SemanticProfileRanker,
    ConstrainedXYZRewriter,
    MasterProfileManager,
    ClosedLoopVerifier,
    JobOpportunityFeatures,
)

PRIVATE_MATRIC = (
    MasterProfileManager().data.get("education", {}).get("matric_number", "") or ""
)


def _assert_no_matric(text: str) -> None:
    if PRIVATE_MATRIC:
        assert PRIVATE_MATRIC not in text


def test_is_cv_required_gatekeeper():
    # Beach cleanup / simple community form -> False
    beach_opp = {
        "title": "Juara Turtle Project Sea Turtle Beach Cleanup Volunteer Camp",
        "raw_description": "Sign up for weekend beach cleanup and turtle patrol.",
        "required_form_fields_json": '["full_name", "phone_whatsapp_my", "tshirt_size"]',
    }
    req, reason = is_cv_required_for_opportunity(beach_opp)
    assert req is False
    assert "السيرة الذاتية غير مطلوبة" in reason

    # Caltech research -> True
    caltech_opp = {
        "title": "CALTECH Summer Research Program 2027 in USA (Fully Funded)",
        "raw_description": "Submit academic CV and statement of purpose for 10-week summer research laboratory internship.",
        "required_form_fields_json": '["full_name", "email_address", "cv_pdf_path"]',
    }
    req, reason = is_cv_required_for_opportunity(caltech_opp)
    assert req is True

def test_typst_cv_synthesis_guaranteed_one_page():
    caltech_opp = {
        "opportunity_code": "TEST-CALTECH-001",
        "title": "CALTECH Summer Research Program 2027 in USA (Fully Funded)",
        "organizer": "Caltech Laboratory",
        "track_category": "RESEARCH_AI",
        "raw_description": "Undergraduate research fellowship focusing on neural systems and algorithms. Academic CV required.",
        "required_form_fields_json": '["full_name", "cv_pdf_path"]',
    }
    res = synthesize_tailored_typst_cv(caltech_opp)
    assert res["cv_required"] is True
    assert res["status"] == "generated"
    assert res["page_count"] == 1
    assert res["ats_score"] >= 80.0
    assert pathlib.Path(res["pdf_path"]).exists()

def test_master_profile_truth_and_xyz_rewriting():
    profile = MasterProfileManager().data
    assert "personal" in profile
    assert "education" in profile
    assert "Universiti Teknologi Malaysia" in profile["education"]["institution"]
    assert "3.53" in str(profile["education"]["cgpa"])


def test_base_reference_cv_synthesis_and_sanitization():
    res = synthesize_base_reference_typst_cv(force_recompile=True)
    assert res["status"] in ["generated", "ready"]
    assert res["page_count"] == 1
    assert pathlib.Path(res["pdf_path"]).exists()

    reader = pypdf.PdfReader(res["pdf_path"])
    full_text = " ".join(p.extract_text() for p in reader.pages)

    # Must contain essential academic info
    assert "Universiti Teknologi Malaysia" in full_text
    assert "3.53" in full_text

    # MUST NOT contain private or internal IDs like matric number or t-shirt size, and omit GitHub
    assert _assert_no_matric(full_text) is None
    assert "Matric" not in full_text
    assert "tshirt" not in full_text.lower()
    assert "apparel" not in full_text.lower()
    assert "github.com" not in full_text


def test_eco_cv_uses_real_profile_projects_not_fabricated_ones():
    opp = {
        "opportunity_code": "TEST-WWF-ECO-001",
        "title": "WWF Malaysia Marine Conservation & Beach Cleanup Expedition 2027",
        "organizer": "WWF Malaysia & Marine Parks Department",
        "track_category": "NATURE_ECO_CONSERVATION",
        "raw_description": (
            "Coastal marine conservation, beach cleanups, coral reef monitoring, and sea turtle protection. "
            "CV optional; field volunteers welcome."
        ),
        "required_form_fields_json": "[]",
    }
    res = synthesize_tailored_typst_cv(opp, force=True)
    assert res["status"] == "generated"
    assert res["page_count"] == 1

    text = " ".join(p.extract_text() for p in pypdf.PdfReader(res["pdf_path"]).pages)
    assert "Environmental Bioacoustics" in text
    assert "Environmental Data Automation" not in text
    assert "Expedition Team Member" not in text
    assert "github.com" not in text.lower()
    assert _assert_no_matric(text) is None

    project_ids = {
        str(prj.get("id")) for prj in MasterProfileManager().data.get("projects", [])
    }
    if "green_ai_bioacoustics" in project_ids:
        assert "Green-AI Rainforest Wildlife" in text
        assert "91.4%" in text


def test_ats_score_has_no_artificial_floor():
    features = JobOpportunityFeatures(
        domain_focus="GENERAL",
        hard_skills=["Underwater Basket Weaving"],
        target_keywords=["Zebra Migration"],
        priority_tags=[],
        target_program_title="Test",
        target_organizer="Test",
    )
    assert ClosedLoopVerifier.calculate_ats_keyword_score("Python and PyTorch", features) == 0.0


def test_opportunity_tailored_cv_adapts_without_private_ids():
    # 1. Technical Research Lab (Caltech) -> Must have GitHub, PyTorch, Algorithms, strictly no camp skills
    caltech_opp = {
        "opportunity_code": "TEST-CALTECH-002",
        "title": "CALTECH Summer Research Program 2027 in USA (Fully Funded)",
        "organizer": "Caltech",
        "track_category": "RESEARCH_AI",
        "raw_description": "Submit academic CV and statement of purpose for 10-week summer research laboratory internship.",
        "required_form_fields_json": '["full_name", "email_address", "cv_pdf_path"]',
    }
    res_caltech = synthesize_tailored_typst_cv(caltech_opp)
    assert res_caltech["status"] == "generated"
    assert res_caltech["page_count"] == 1

    reader_caltech = pypdf.PdfReader(res_caltech["pdf_path"])
    caltech_text = " ".join(p.extract_text() for p in reader_caltech.pages)

    assert "CALTECH" in caltech_text
    assert "github.com" not in caltech_text  # Strict User Directive: GitHub omitted by default unless mandated!
    assert "PyTorch" in caltech_text
    assert _assert_no_matric(caltech_text) is None
    assert "Camping" not in caltech_text  # Irrelevant outdoor skills excluded from research lab

    # 2. Community Volunteering & Education (SOLS 24/7) -> Must NOT have GitHub, must highlight pedagogy/mentoring
    sols_opp = {
        "opportunity_code": "TEST-SOLS-001",
        "title": "SOLS 24/7 Community Youth & Child Digital Education Fellowship",
        "organizer": "SOLS Foundation",
        "track_category": "VOLUNTEERING",
        "raw_description": "Youth educational fellowship requiring tailored CV and statement of purpose for teaching children.",
        "required_form_fields_json": '["full_name", "cv_pdf_path"]',
    }
    res_sols = synthesize_tailored_typst_cv(sols_opp)
    assert res_sols["status"] == "generated"
    assert res_sols["page_count"] == 1

    reader_sols = pypdf.PdfReader(res_sols["pdf_path"])
    sols_text = " ".join(p.extract_text() for p in reader_sols.pages)

    assert "SOLS" in sols_text
    assert "github.com" not in sols_text  # User complaint fixed: No GitHub on community/volunteering vacancies!
    # The old CV invented a “Peer Coding Mentor” role. The grounded CV keeps
    # only real evidence: cross-cultural teamwork and peer learning at UTM.
    assert "Cross-Cultural" in sols_text or "Peer-learning" in sols_text
    assert "Community Education" in sols_text
    assert _assert_no_matric(sols_text) is None

    # 3. Explicit Mandatory GitHub Requirement -> ONLY here is GitHub included
    hack_opp = {
        "opportunity_code": "TEST-HACK-001",
        "title": "Open Source Systems Hackathon 2027",
        "organizer": "Linux Foundation",
        "track_category": "HACKATHON",
        "raw_description": "All applicants are required to provide their mandatory github code repository link.",
        "required_form_fields_json": '["full_name", "cv_pdf_path"]',
    }
    res_hack = synthesize_tailored_typst_cv(hack_opp)
    assert res_hack["status"] == "generated"
    reader_hack = pypdf.PdfReader(res_hack["pdf_path"])
    hack_text = " ".join(p.extract_text() for p in reader_hack.pages)
    assert "github.com" in hack_text
