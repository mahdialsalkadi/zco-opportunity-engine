#!/usr/bin/env python3
"""
ZCO-Engine v4.0 — Zero-Cost Gatekeeper, Tri-Jurisdiction Eligibility Engine,
Persistent Self-Learning Memory Vault, Real Chromium DOM Auto-Filler & PDF Inspector
(`engines_and_auditor.py`)
====================================================================================
Production-ready core engine combining:
1. `PdfGuidelinesExtractor` & `DeepPageAndPdfInspector`:
   - Extracts full text from attached guideline PDFs (`pdfplumber` / `pypdf`) and live
     rendered HTML pages (`BeautifulSoup` + Headless Chromium).
   - Inspects real HTML `<form>` DOM trees (`<input>`, `<textarea>`, `<select>`,
     `<input type="file">`) and automatically maps them to `CandidateMemoryVault` keys.
   - Detects CAPTCHA / Cloudflare Turnstile / Login walls (`g-recaptcha`, `h-captcha`,
     `cf-turnstile`).

2. `ZeroCostGatekeeper` & `TriJurisdictionEligibilityEngine`:
   - Audits both webpage text AND extracted PDF guidelines to catch hidden fees (> $0).
   - Evaluates eligibility across Syria (`SY`), Malaysia UTM AI Student Pass (`MY`),
     and Kuwait Residency (`KW`).

3. `CandidateMemoryVault` & `RealBrowserFormAutoFiller` + `AutonomousApplicantEngine`:
   - Self-learning persistent SQLite + JSON vault that never asks the same question twice.
   - Opens real Headless Chromium (`/usr/bin/chromium` + `/usr/bin/chromedriver` via Selenium)
     with optional persistent Chrome profile (`--user-data-dir`), fills every DOM field,
     uploads PDF documents (`cv_pdf_path`, `utm_enrollment_pdf_path`), captures Pre-Submit
     and Post-Submit PNG screenshots, and clicks the real Submit button!
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import io
import json
import logging
import os
import pathlib
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("zco_engines")

def _load_env_if_needed() -> None:
    env_file = pathlib.Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass

_load_env_if_needed()

from bs4 import BeautifulSoup
from database import OpportunityDatabase, OpportunityStatus
from file_utils import atomic_write_json, atomic_write_text
from paths import CANDIDATE_PROFILE_PATH
from portfolio_and_docs_engine import PortfolioManager


DEFAULT_CANDIDATE_PROFILE: Dict[str, Any] = {
    "candidate": {
        "full_name": "Mohammad Mahdi",
        "gender": "male",
        "age": 20,
        "birth_year": 2006,
    },
    "jurisdictions": {
        "nationality": {
            "country_code": "SY",
            "country_name": "Syria",
            "eligible_regions": [
                "MENA",
                "Middle East",
                "Arab States",
                "Developing Countries",
                "Global South",
                "MEDA",
                "Mediterranean Partner Countries",
            ],
        },
        "primary_academic_residency": {
            "country_code": "MY",
            "country_name": "Malaysia",
            "status": "International Student (Valid Malaysia Student Pass)",
            "university": "Universiti Teknologi Malaysia (UTM)",
            "departure_hub": "KUL (Kuala Lumpur / Johor Bahru)",
            "eligible_scopes": [
                "Inside Malaysia (Domestic)",
                "Borneo / Sabah / Sarawak Field Camps",
                "ASEAN-Hosted Open to Residents",
                "Malaysian University Undergraduate Tracks",
            ],
        },
        "secondary_legal_residency": {
            "country_code": "KW",
            "country_name": "Kuwait",
            "status": "Valid Residency Permit (Iqama)",
            "eligible_scopes": [
                "GCC Residents Youth Tracks",
                "Arab Youth Center Initiatives",
                "Kuwait Foundations",
            ],
        },
    },
    "academic_profile": {
        "university": "Universiti Teknologi Malaysia (UTM)",
        "degree_level": "Undergraduate (Bachelor's)",
        "current_year": 1,
        "major": "Artificial Intelligence",
        "core_tracks": [
            "NATURE_ECO_CONSERVATION",
            "GREEN_AI_CLIMATE_TECH",
            "CORE_AI_HACKATHONS",
            "OUTDOOR_LEADERSHIP_CAMPS",
            "COMMUNITY_VOLUNTEERING_EXCHANGE",
            "MENA_GCC_ASEAN_SPECIAL",
        ],
    },
}


STANDARD_FIELD_CATALOG: Dict[str, Dict[str, str]] = {
    "full_name": {
        "label_ar": "الاسم الكامل (كما في جواز السفر)",
        "category": "identity",
    },
    "age": {
        "label_ar": "العمر الحالي",
        "category": "identity",
    },
    "nationality": {
        "label_ar": "الجنسية (جواز السفر)",
        "category": "jurisdiction",
    },
    "primary_residency_country": {
        "label_ar": "بلد الإقامة الأكاديمية الحالي",
        "category": "jurisdiction",
    },
    "malaysia_visa_type": {
        "label_ar": "نوع الإقامة في ماليزيا",
        "category": "jurisdiction",
    },
    "secondary_residency_country": {
        "label_ar": "بلد الإقامة القانونية الثانية",
        "category": "jurisdiction",
    },
    "university_name": {
        "label_ar": "اسم الجامعة الحالية",
        "category": "academic",
    },
    "degree_and_major": {
        "label_ar": "الدرجة العلمية والتخصص الدقيق",
        "category": "academic",
    },
    "academic_year": {
        "label_ar": "السنة الدراسية الحالية",
        "category": "academic",
    },
    "departure_airport": {
        "label_ar": "مطار المغادرة المفضل لحجز تذاكر الطيران",
        "category": "logistics",
    },
    "email_address": {
        "label_ar": "البريد الإلكتروني الرسمي للتقديم واستلام القبول",
        "category": "contact",
    },
    "phone_whatsapp_my": {
        "label_ar": "رقم الهاتف / واتساب الماليزي للتواصل السريع",
        "category": "contact",
    },
    "passport_number": {
        "label_ar": "رقم جواز السفر السوري وتاريخ انتهائه",
        "category": "documents",
    },
    "utm_matric_number": {
        "label_ar": "الرقم الجامعي في جامعة UTM (Matric Number)",
        "category": "academic",
    },
    "current_cgpa": {
        "label_ar": "المعدل التراكمي الحالي (CGPA) أو معدل الثانوية لطلبة السنة الأولى",
        "category": "academic",
    },
    "github_or_portfolio_url": {
        "label_ar": "رابط حساب GitHub أو LinkedIn أو معرض مشاريع الذكاء الاصطناعي",
        "category": "academic",
    },
    "dietary_preference": {
        "label_ar": "تفضيلات الطعام في المعسكرات والمؤتمرات (مثلاً: حلال / بدون قيود)",
        "category": "logistics",
    },
    "tshirt_and_gear_size": {
        "label_ar": "مقاس القميص والمعدات الميدانية للمعسكرات البيئية والهاكاثونات (S/M/L/XL)",
        "category": "logistics",
    },
    "activity_preferences": {
        "label_ar": "تفضيلات أنواع الأنشطة (طبيعة، ذكاء اصطناعي أخضر، هاكاثونات، معسكرات، تطوع)",
        "category": "preferences",
    },
    "location_preference": {
        "label_ar": "تفضيل موقع الفرصة (داخل ماليزيا / خارج ماليزيا / الاثنان)",
        "category": "preferences",
    },
    "availability_from": {
        "label_ar": "تاريخ بداية الإتاحة للمشاركة في الأنشطة",
        "category": "availability",
    },
    "availability_to": {
        "label_ar": "تاريخ نهاية الإتاحة للمشاركة في الأنشطة",
        "category": "availability",
    },
    "swimming_and_outdoor_fitness": {
        "label_ar": "مستوى اللياقة الميدانية والقدرة على السباحة (للمعسكرات البحرية والغابات)",
        "category": "outdoor",
    },
    "emergency_contact_info": {
        "label_ar": "بيانات شخص للتواصل في حالات الطوارئ (الاسم، صلة القرابة، الرقم)",
        "category": "logistics",
    },
    "cv_pdf_path": {
        "label_ar": "مسار ملف السيرة الذاتية بصيغة PDF للرفع التلقائي في الاستمارة",
        "category": "documents",
    },
    "utm_enrollment_pdf_path": {
        "label_ar": "مسار ملف إثبات القيد الجامعي من UTM بصيغة PDF",
        "category": "documents",
    },
}


INITIAL_KNOWN_VAULT_SEED: Dict[str, str] = {
    "full_name": "Mohammad Mahdi",
    "age": "20",
    "nationality": "Syrian (SY)",
    "primary_residency_country": "Malaysia (MY)",
    "malaysia_visa_type": "Valid International Student Pass (UTM)",
    "secondary_residency_country": "Kuwait (Valid Residency / Iqama)",
    "university_name": "Universiti Teknologi Malaysia (UTM)",
    "degree_and_major": "Bachelor of Artificial Intelligence (B.Sc. AI)",
    "academic_year": "Year 1 (Undergraduate)",
    "departure_airport": "Kuala Lumpur International Airport (KUL) / Senai (JHB)",
}


DEFAULT_REQUIRED_FIELDS_BY_TRACK: Dict[str, List[str]] = {
    "NATURE_ECO_CONSERVATION": [
        "full_name",
        "age",
        "nationality",
        "primary_residency_country",
        "university_name",
        "departure_airport",
        "email_address",
        "phone_whatsapp_my",
        "dietary_preference",
        "tshirt_and_gear_size",
        "swimming_and_outdoor_fitness",
    ],
    "GREEN_AI_CLIMATE_TECH": [
        "full_name",
        "age",
        "nationality",
        "primary_residency_country",
        "university_name",
        "degree_and_major",
        "academic_year",
        "departure_airport",
        "email_address",
        "phone_whatsapp_my",
        "github_or_portfolio_url",
        "current_cgpa",
    ],
    "CORE_AI_HACKATHONS": [
        "full_name",
        "age",
        "nationality",
        "university_name",
        "degree_and_major",
        "academic_year",
        "utm_matric_number",
        "email_address",
        "phone_whatsapp_my",
        "github_or_portfolio_url",
        "tshirt_and_gear_size",
    ],
    "OUTDOOR_LEADERSHIP_CAMPS": [
        "full_name",
        "age",
        "nationality",
        "primary_residency_country",
        "departure_airport",
        "email_address",
        "phone_whatsapp_my",
        "dietary_preference",
        "swimming_and_outdoor_fitness",
        "emergency_contact_info",
    ],
    "COMMUNITY_VOLUNTEERING_EXCHANGE": [
        "full_name",
        "age",
        "nationality",
        "primary_residency_country",
        "university_name",
        "departure_airport",
        "email_address",
        "phone_whatsapp_my",
        "passport_number",
        "dietary_preference",
    ],
    "MENA_GCC_ASEAN_SPECIAL": [
        "full_name",
        "age",
        "nationality",
        "primary_residency_country",
        "secondary_residency_country",
        "university_name",
        "degree_and_major",
        "departure_airport",
        "email_address",
        "phone_whatsapp_my",
        "passport_number",
    ],
}


DOM_ATTRIBUTE_TO_VAULT_KEY_RULES: List[Tuple[str, List[str]]] = [
    ("full_name", ["full_name", "fullname", "full name", "candidate_name", "candidate", "applicant_name", "your name", "name as in passport", "first and last name", "الاسم الكامل"]),
    ("email_address", ["email", "e-mail", "mail", "البريد الإلكتروني"]),
    ("phone_whatsapp_my", ["phone", "mobile", "whatsapp", "contact_number", "telephone", "رقم الهاتف"]),
    ("age", ["age", "your age", "العمر"]),
    ("nationality", ["nationality", "citizenship", "passport_country", "country of citizenship", "الجنسية"]),
    ("primary_residency_country", ["country_of_residence", "current_country", "residency", "living_in", "بلد الإقامة"]),
    ("secondary_residency_country", ["secondary_residency", "gcc_residency", "other_residency", "إقامة ثانية"]),
    ("utm_matric_number", ["matric", "student_id", "matric_number", "enrollment_number", "الرقم الجامعي"]),
    ("current_cgpa", ["cgpa", "gpa", "grade_point", "academic_score", "المعدل"]),
    ("academic_year", ["year_of_study", "academic_year", "study_year", "current_year", "السنة الدراسية"]),
    ("degree_and_major", ["major", "field_of_study", "degree", "program_of_study", "department", "التخصص"]),
    ("university_name", ["university", "institution", "college", "school_name", "الجامعة"]),
    ("tailored_motivation_essay", ["why do you want", "why apply", "motivation", "statement_of_purpose", "essay", "cover_letter", "رسالة الدافع"]),
    ("github_or_portfolio_url", ["github", "github_url", "github_profile"]),
    ("departure_airport", ["airport", "departure_city", "departure_hub", "nearest_airport", "مطار المغادرة"]),
    ("passport_number", ["passport_no", "passport_number", "passport_id", "رقم جواز السفر"]),
    ("dietary_preference", ["diet", "dietary", "food_preference", "meal_preference", "halal", "allergies"]),
    ("tshirt_and_gear_size", ["tshirt", "t-shirt", "shirt_size", "apparel_size", "gear_size"]),
    ("activity_preferences", ["activity_preference", "activity preferences", "preferred activities", "type of activities", "activity types", "نوع النشاط", "تفضيلات الأنشطة"]),
    ("location_preference", ["location_preference", "location preference", "preferred location", "opportunity location preference", "تفضيل الموقع", "موقع الفرصة"]),
    ("availability_from", ["availability_from", "available_from", "available from", "availability start", "متاح من"]),
    ("availability_to", ["availability_to", "available_to", "available to", "availability end", "متاح حتى"]),
    ("swimming_and_outdoor_fitness", ["swimming", "fitness", "physical_condition", "outdoor_experience"]),
    ("emergency_contact_info", ["emergency", "next_of_kin", "emergency_contact"]),
    ("tailored_motivation_essay", ["motivation", "statement_of_purpose", "why_apply", "essay", "cover_letter", "رسالة الدافع"]),
    ("cv_pdf_path", ["cv", "resume", "curriculum_vitae", "upload_cv"]),
    ("utm_enrollment_pdf_path", ["enrollment", "verification_letter", "transcript", "student_letter", "bonafide"]),
]


@dataclasses.dataclass
class DiscoveredFormField:
    dom_selector: str
    tag_name: str
    input_type: str
    dom_name: str
    dom_id: str
    label_text: str
    required: bool
    mapped_vault_key: str
    options: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class PageInspectionReport:
    url: str
    page_title: str
    extracted_full_text: str
    extracted_pdf_texts: List[str]
    discovered_fields: List[DiscoveredFormField]
    required_vault_keys: List[str]
    has_captcha_or_login_wall: bool
    captcha_type: str = ""


@dataclasses.dataclass
class BrowserSubmissionReceipt:
    status: str  # "APPLIED_AUTOMATICALLY" | "SUBMITTED_UNCONFIRMED" | "READY_FOR_SUBMISSION" | "PAUSED_AT_CAPTCHA"
    confirmation_reference: str
    confirmation_page_text: str
    pre_submit_screenshot_path: str
    post_submit_screenshot_path: str
    filled_dom_fields_count: int
    uploaded_files_count: int
    notes: str = ""


class PdfGuidelinesExtractor:
    """Extracts full text from local or remote PDF files using `pdfplumber` or `pypdf`."""

    @staticmethod
    def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
        try:
            import pdfplumber

            pages_text: List[str] = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text() or ""
                    if t.strip():
                        pages_text.append(t)
            if pages_text:
                return "\n\n".join(pages_text)
        except Exception:
            pass

        try:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            return "\n\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as exc:
            return f"[PDF extraction error: {exc}]"

    @classmethod
    def extract_text_from_pdf_path_or_url(cls, path_or_url: str, timeout: int = 15) -> str:
        if path_or_url.startswith("file://"):
            local_path = pathlib.Path(urllib.parse.unquote(path_or_url.replace("file://", "")))
            if local_path.exists():
                return cls.extract_text_from_pdf_bytes(local_path.read_bytes())
        elif pathlib.Path(path_or_url).exists():
            return cls.extract_text_from_pdf_bytes(pathlib.Path(path_or_url).read_bytes())
        elif path_or_url.startswith(("http://", "https://")):
            req = urllib.request.Request(
                path_or_url,
                headers={"User-Agent": "ZCO-Antigravity-Inspector/4.0"},
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return cls.extract_text_from_pdf_bytes(resp.read())
            except Exception as exc:
                return f"[Remote PDF fetch error: {exc}]"
        return ""


class DeepPageAndPdfInspector:
    """
    Inspects live HTML pages (and linked PDFs) to extract the complete Terms & Conditions
    and automatically discover all `<form>` fields and map them to `CandidateMemoryVault` keys.
    """

    @staticmethod
    def map_control_to_vault_key(
        dom_name: str, dom_id: str, label_text: str, placeholder: str, input_type: str
    ) -> str:
        haystack = f"{dom_name} {dom_id} {label_text} {placeholder}".lower()
        for vault_key, keywords in DOM_ATTRIBUTE_TO_VAULT_KEY_RULES:
            for kw in keywords:
                if kw.lower() in haystack:
                    return vault_key

        if input_type == "email":
            return "email_address"
        if input_type == "tel":
            return "phone_whatsapp_my"
        if input_type == "file":
            return "cv_pdf_path"
        raw_ident = (dom_name or dom_id or label_text or "custom_field").strip().lower()
        clean_ident = re.sub(r"[^a-z0-9]+", "_", raw_ident).strip("_")
        return clean_ident[:48] or "custom_field"

    @classmethod
    def inspect_html_content(
        cls,
        html_text: str,
        base_url: str = "",
        resolve_linked_pdfs: bool = True,
    ) -> PageInspectionReport:
        soup = BeautifulSoup(html_text, "html.parser")
        page_title = (soup.title.string if soup.title and soup.title.string else "").strip()

        html_lower = html_text.lower()
        captcha_type = ""
        if "g-recaptcha" in html_lower or "recaptcha/api.js" in html_lower:
            captcha_type = "Google reCAPTCHA"
        elif "h-captcha" in html_lower or "hcaptcha.com" in html_lower:
            captcha_type = "hCaptcha"
        elif "cf-turnstile" in html_lower or "challenges.cloudflare.com" in html_lower:
            captcha_type = "Cloudflare Turnstile"

        pdf_texts: List[str] = []
        if resolve_linked_pdfs:
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].strip()
                if href.lower().endswith(".pdf"):
                    if base_url.startswith("file://") and not href.startswith(("file://", "http")):
                        base_dir = pathlib.Path(urllib.parse.unquote(base_url.replace("file://", ""))).parent
                        full_pdf_url = f"file://{base_dir / href}"
                    else:
                        full_pdf_url = urllib.parse.urljoin(base_url, href) if base_url else href
                    extracted_pdf = PdfGuidelinesExtractor.extract_text_from_pdf_path_or_url(
                        full_pdf_url
                    )
                    if extracted_pdf.strip():
                        pdf_texts.append(extracted_pdf)

        labels_by_for: Dict[str, str] = {}
        for lbl in soup.find_all("label"):
            for_attr = (lbl.get("for") or "").strip()
            if for_attr:
                labels_by_for[for_attr] = lbl.get_text(" ", strip=True)

        discovered_fields: List[DiscoveredFormField] = []
        required_vault_keys: List[str] = []

        # Collect standard form controls as well as ARIA / SPA form widgets (Google Forms, MS Forms, Typeform, Airtable)
        all_controls = soup.find_all(
            lambda t: t.name in ["input", "textarea", "select"]
            or t.get("role") in ["radio", "checkbox", "textbox"]
        )

        for control in all_controls:
            tag_name = control.name.lower()
            role_attr = (control.get("role") or "").lower()
            input_type = (
                control.get("type")
                or role_attr
                or ("text" if tag_name == "input" else tag_name)
            ).lower()
            if input_type in ("hidden", "submit", "button", "reset", "image"):
                continue

            dom_name = (control.get("name") or "").strip()
            dom_id = (control.get("id") or "").strip()
            placeholder = (control.get("placeholder") or "").strip()
            is_required = control.has_attr("required") or (
                control.get("aria-required") == "true"
            )

            label_text = labels_by_for.get(dom_id, "")
            if not label_text:
                parent_label = control.find_parent("label")
                if parent_label:
                    label_text = parent_label.get_text(" ", strip=True)

            # Inspect ARIA / SPA question container (Google Forms, Microsoft Forms, Typeform, Airtable)
            parent_container = control.find_parent(
                lambda t: t.get("role") == "listitem"
                or (
                    t.get("class")
                    and any(
                        k in str(c)
                        for c in t.get("class")
                        for k in ["freebird", "M7eMe", "ge-item", "ItemItem", "airtable"]
                    )
                )
                or t.has_attr("data-params")
            )
            if parent_container:
                if parent_container.find(
                    lambda t: t.get("aria-label") == "Required question"
                    or t.get("aria-required") == "true"
                    or "*" in t.get_text(strip=True)
                ):
                    is_required = True

                if not label_text:
                    heading_el = parent_container.find(
                        lambda t: t.get("role") == "heading"
                        or (
                            t.get("class")
                            and any(
                                k in str(t.get("class"))
                                for k in [
                                    "M7eMe",
                                    "ItemTitle",
                                    "title",
                                    "heading",
                                    "label",
                                    "HoG1xd",
                                    "question",
                                ]
                            )
                        )
                    )
                    if heading_el:
                        label_text = heading_el.get_text(" ", strip=True)

            # Fallback to aria-label or aria-labelledby
            if not label_text and control.get("aria-label"):
                label_text = control.get("aria-label", "").strip()
            elif not label_text and control.get("aria-labelledby"):
                ref_id = control.get("aria-labelledby")
                ref_el = soup.find(id=ref_id)
                if ref_el:
                    label_text = ref_el.get_text(" ", strip=True)

            if input_type == "checkbox" and any(
                w in f"{dom_name} {dom_id} {label_text}".lower()
                for w in ["agree", "terms", "confirm", "consent"]
            ):
                selector = f"#{dom_id}" if dom_id else f"[name='{dom_name}']"
                discovered_fields.append(
                    DiscoveredFormField(
                        dom_selector=selector,
                        tag_name=tag_name,
                        input_type=input_type,
                        dom_name=dom_name,
                        dom_id=dom_id,
                        label_text=label_text,
                        required=is_required,
                        mapped_vault_key="__auto_agree_checkbox__",
                    )
                )
                continue

            mapped_key = cls.map_control_to_vault_key(
                dom_name=dom_name,
                dom_id=dom_id,
                label_text=label_text,
                placeholder=placeholder,
                input_type=input_type,
            )

            options: List[str] = []
            if tag_name == "select":
                for opt in control.find_all("option"):
                    val = (opt.get("value") or opt.get_text(strip=True)).strip()
                    if val:
                        options.append(val)
            elif role_attr == "radio":
                opt_val = control.get("aria-label") or control.get_text(" ", strip=True)
                if opt_val:
                    options.append(opt_val)

            # Build resilient selector
            if dom_id:
                selector = f"#{dom_id}"
            elif dom_name:
                selector = f"[name='{dom_name}']"
            elif control.get("aria-labelledby"):
                selector = f"[aria-labelledby='{control.get('aria-labelledby')}']"
            elif control.get("jsname"):
                selector = f"[jsname='{control.get('jsname')}']"
            elif control.get("aria-label"):
                selector = f"[aria-label='{control.get('aria-label')}']"
            elif role_attr:
                selector = f"[role='{role_attr}']"
            else:
                selector = tag_name

            discovered_fields.append(
                DiscoveredFormField(
                    dom_selector=selector,
                    tag_name=tag_name,
                    input_type=input_type,
                    dom_name=dom_name,
                    dom_id=dom_id,
                    label_text=label_text,
                    required=is_required,
                    mapped_vault_key=mapped_key,
                    options=options,
                )
            )
            if (
                is_required
                and mapped_key not in required_vault_keys
                and mapped_key != "tailored_motivation_essay"
            ):
                required_vault_keys.append(mapped_key)

        visible_text = soup.get_text(" ", strip=True)
        return PageInspectionReport(
            url=base_url,
            page_title=page_title,
            extracted_full_text=visible_text,
            extracted_pdf_texts=pdf_texts,
            discovered_fields=discovered_fields,
            required_vault_keys=required_vault_keys,
            has_captcha_or_login_wall=bool(captcha_type),
            captcha_type=captcha_type,
        )


@dataclasses.dataclass
class ApplicationPreflightResult:
    """Result of checking an application URL before launching a browser."""

    ok: bool
    apply_url: str
    final_url: str = ""
    status_code: int = 0
    page_title: str = ""
    form_count: int = 0
    field_count: int = 0
    required_field_count: int = 0
    has_application_form: bool = False
    redirected_to_homepage: bool = False
    has_captcha_or_login_wall: bool = False
    captcha_type: str = ""
    required_vault_keys: List[str] = dataclasses.field(default_factory=list)
    reason: str = ""
    warnings: List[str] = dataclasses.field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "apply_url": self.apply_url,
            "final_url": self.final_url,
            "status_code": self.status_code,
            "page_title": self.page_title,
            "form_count": self.form_count,
            "field_count": self.field_count,
            "required_field_count": self.required_field_count,
            "has_application_form": self.has_application_form,
            "redirected_to_homepage": self.redirected_to_homepage,
            "has_captcha_or_login_wall": self.has_captcha_or_login_wall,
            "captcha_type": self.captcha_type,
            "required_vault_keys": self.required_vault_keys,
            "reason": self.reason,
            "warnings": self.warnings,
        }


def preflight_application_url(
    apply_url: str,
    deadline_iso: str = "",
    expected_title: str = "",
    timeout: int = 15,
) -> ApplicationPreflightResult:
    """Open an application URL and verify it is a real, fillable form.

    This is deliberately a read-only check. It never clicks Submit and runs
    before Chromium is launched, so a generic homepage, a news article, or a
    dead link can no longer be recorded as a prepared or submitted application.
    """
    apply_url = str(apply_url or "").strip()
    result = ApplicationPreflightResult(ok=False, apply_url=apply_url)

    if not apply_url:
        result.reason = "لا يوجد رابط تقديم محفوظ لهذه الفرصة."
        return result

    parsed = urllib.parse.urlparse(apply_url)
    if parsed.scheme.lower() not in ("http", "https", "file"):
        result.reason = f"رابط التقديم يستخدم مخططاً غير مدعوم: {parsed.scheme or 'بدون مخطط'}"
        return result

    if deadline_iso:
        try:
            deadline = dt.date.fromisoformat(str(deadline_iso)[:10])
            if deadline < dt.date.today():
                result.reason = f"انتهى آخر موعد للتسجيل في {deadline.isoformat()}؛ لن يتم تقديم طلب جديد."
                return result
        except ValueError:
            pass

    html_text = ""
    final_url = apply_url
    try:
        if parsed.scheme.lower() == "file":
            local_path = pathlib.Path(urllib.parse.unquote(parsed.path))
            if not local_path.is_file():
                result.reason = f"ملف الاستمارة المحلي غير موجود: {local_path}"
                return result
            html_text = local_path.read_text(encoding="utf-8", errors="replace")
            result.status_code = 200
            result.final_url = apply_url
        else:
            is_local = any(
                parsed.netloc.startswith(h)
                for h in ("127.0.0.1", "localhost", "0.0.0.0")
            )
            # Use Obscura headless browser for live external portals (JS rendering + anti-bot stealth)
            if not is_local:
                try:
                    import obscura_engine

                    if obscura_engine.is_obscura_available():
                        rendered = obscura_engine.fetch_rendered_html(apply_url, timeout=timeout)
                        if rendered and len(rendered.strip()) > 50:
                            html_text = rendered
                            result.status_code = 200
                            result.final_url = apply_url
                except Exception as exc:
                    logger.debug("Obscura preflight fetch failed for %s: %s", apply_url, exc)

            if not html_text:
                req = urllib.request.Request(
                    apply_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; ZCO-ApplicationPreflight/1.0)",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    result.status_code = int(getattr(resp, "status", 200) or 200)
                    final_url = resp.geturl() or apply_url
                    charset = resp.headers.get_content_charset() or "utf-8"
                    html_text = resp.read(2_000_000).decode(charset, errors="replace")
                result.final_url = final_url
    except urllib.error.HTTPError as exc:
        result.status_code = int(exc.code)
        result.reason = f"رابط التقديم أعاد HTTP {exc.code}."
        return result
    except Exception as exc:
        result.reason = f"تعذر فتح رابط التقديم: {exc}"
        return result

    if result.status_code >= 400:
        result.reason = f"رابط التقديم أعاد HTTP {result.status_code}."
        return result

    inspection = DeepPageAndPdfInspector.inspect_html_content(
        html_text=html_text,
        base_url=final_url,
        resolve_linked_pdfs=False,
    )
    soup = BeautifulSoup(html_text, "html.parser")
    visible_text = inspection.extracted_full_text or ""

    result.page_title = inspection.page_title
    result.form_count = len(soup.find_all("form"))
    result.field_count = len(inspection.discovered_fields)
    result.required_field_count = sum(1 for f in inspection.discovered_fields if f.required)
    result.required_vault_keys = list(inspection.required_vault_keys)
    result.has_captcha_or_login_wall = inspection.has_captcha_or_login_wall
    result.captcha_type = inspection.captcha_type

    orig_path = urllib.parse.urlparse(apply_url).path.rstrip("/") or "/"
    final_path = urllib.parse.urlparse(final_url).path.rstrip("/") or "/"
    result.redirected_to_homepage = orig_path != "/" and final_path == "/"

    has_password_field = bool(soup.find("input", {"type": "password"}))
    is_direct_form_host = any(
        dom in apply_url.lower()
        for dom in (
            "airtable.com",
            "forms.gle",
            "docs.google.com/forms",
            "forms.office.com",
            "forms.cloud.microsoft",
            "tally.so",
            "typeform.com",
            "formtitan.com",
            "sirop.org",
            "applyweb.com",
            "slideroom.com",
            "myworkdayjobs.com",
        )
    )

    embedded_form_urls = [
        str(iframe.get("src") or "")
        for iframe in soup.find_all("iframe")
        if any(
            host in str(iframe.get("src") or "").lower()
            for host in (
                "docs.google.com/forms",
                "forms.office.com",
                "tally.so",
                "typeform.com",
                "airtable.com",
            )
        )
    ]

    if has_password_field:
        result.has_captcha_or_login_wall = True
        result.captcha_type = result.captcha_type or "Login wall"
        result.reason = "صفحة التقديم تتطلب تسجيل دخول؛ لا يمكن تقديم النموذج تلقائياً بأمان."
        return result

    if embedded_form_urls and result.field_count == 0 and not is_direct_form_host:
        result.reason = (
            "الاستمارة مدمجة داخل iframe خارجي ولا يمكن تعبئتها بأمان من هذه الصفحة. "
            "افتح رابط الاستمارة المباشر أولاً."
        )
        return result

    if result.field_count == 0:
        if is_direct_form_host:
            # Trusted direct form portal (SPA client-side hydration)
            result.has_application_form = True
            result.ok = True
            result.field_count = max(result.field_count, 1)
            result.reason = "تم التحقق من وجود استمارة تقديم تفاعلية عبر منصة الاستمارات الرسمية المباشرة."
            return result

        if result.redirected_to_homepage:
            result.reason = (
                "رابط التقديم يعيد التوجيه إلى الصفحة الرئيسية ولا يحتوي على أي استمارة تقديم. "
                "لم يتم فتح المتصفح ولم يتم تسجيل أي تقديم."
            )
        else:
            result.reason = (
                "الصفحة لا تحتوي على أي حقول استمارة تفاعلية (مقال إخباري أو صفحة تعريفية). "
                "لم يتم فتح المتصفح ولم يتم تسجيل أي تقديم."
            )
        if result.page_title:
            result.reason += f" عنوان الصفحة: {result.page_title}"
        return result

    if result.has_captcha_or_login_wall:
        result.warnings.append(
            f"الصفحة تتضمن حاجز {result.captcha_type or 'CAPTCHA/تسجيل دخول'}؛ سيتم التوقف قبل الضغط على Submit."
        )

    if not soup.find_all("button") and not soup.find_all("input", {"type": "submit"}):
        result.warnings.append("لم يتم العثور على زر Submit واضح في الصفحة.")

    expected_tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z]{4,}", expected_title or "")
        if token.lower() not in {"with", "from", "this", "that", "program", "fully", "funded", "2027", "2026"}
    ]
    if expected_tokens:
        page_haystack = f"{result.page_title} {final_url} {visible_text[:3000]}".lower()
        if not any(token in page_haystack for token in expected_tokens[:6]):
            result.warnings.append(
                "عنوان الصفحة ورابطها لا يذكران اسم الفرصة؛ تحقق يدوياً من أنها صفحة التقديم الصحيحة."
            )

    result.has_application_form = True
    result.ok = True
    result.reason = "تم التحقق من وجود استمارة تقديم تفاعلية."
    return result


def preflight_application(opp: Dict[str, Any], timeout: int = 15) -> ApplicationPreflightResult:
    """Convenience wrapper around :func:`preflight_application_url` for a DB row."""
    return preflight_application_url(
        apply_url=str(opp.get("apply_url") or ""),
        deadline_iso=str(opp.get("deadline_iso") or ""),
        expected_title=str(opp.get("title") or ""),
        timeout=timeout,
    )


class RealBrowserFormAutoFiller:
    """
    Uses real Headless Chromium (`/usr/bin/chromium` + `/usr/bin/chromedriver` via Selenium)
    to inspect live pages, fill all `<form>` controls from `CandidateMemoryVault`, upload PDF
    files, capture pre/post-submit screenshots, and click Submit!
    """

    def __init__(
        self,
        screenshots_dir: pathlib.Path,
        chrome_user_data_dir: Optional[pathlib.Path] = None,
        headless: bool = True,
    ) -> None:
        self.screenshots_dir = screenshots_dir
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.chrome_user_data_dir = chrome_user_data_dir
        self.headless = headless

    def _create_chromium_driver(self) -> Any:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1440,1200")
        if self.chrome_user_data_dir:
            self.chrome_user_data_dir.mkdir(parents=True, exist_ok=True)
            options.add_argument(f"--user-data-dir={self.chrome_user_data_dir}")

        bin_candidates = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            shutil.which("google-chrome"),
        ]
        # Search ms-playwright cached chromium if available
        playwright_cache = pathlib.Path.home() / ".cache" / "ms-playwright"
        if playwright_cache.exists():
            bin_candidates.extend(str(p) for p in playwright_cache.glob("chromium-*/chrome-linux64/chrome"))
            bin_candidates.extend(str(p) for p in playwright_cache.glob("chromium-*/chrome-linux/chrome"))

        for bin_candidate in bin_candidates:
            if bin_candidate and pathlib.Path(bin_candidate).exists():
                options.binary_location = bin_candidate
                break

        service = (
            Service("/usr/bin/chromedriver")
            if pathlib.Path("/usr/bin/chromedriver").exists()
            else Service()
        )
        return webdriver.Chrome(service=service, options=options)

    def inspect_live_url_with_browser(self, url: str) -> PageInspectionReport:
        driver = self._create_chromium_driver()
        try:
            driver.get(url)
            time.sleep(0.4)
            html_source = driver.page_source
            return DeepPageAndPdfInspector.inspect_html_content(
                html_text=html_source, base_url=url, resolve_linked_pdfs=True
            )
        finally:
            driver.quit()

    def fill_and_submit_application(
        self,
        opportunity_code: str,
        apply_url: str,
        vault_values: Dict[str, str],
        tailored_motivation_essay: str,
        auto_click_submit: bool = True,
        engine: str = "auto",
    ) -> BrowserSubmissionReceipt:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import Select, WebDriverWait

        allowed_prefixes = ("http://", "https://", "file://")
        if not str(apply_url or "").startswith(allowed_prefixes):
            raise ValueError(
                f"Refusing to open unsupported application URL scheme: {apply_url!r}"
            )

        # Use Obscura engine for external live portals when available
        if engine in ("auto", "obscura") and apply_url.startswith(("http://", "https://")):
            try:
                import obscura_engine

                if obscura_engine.is_obscura_available():
                    return obscura_engine.obscura_fill_and_submit(
                        opportunity_code=opportunity_code,
                        apply_url=apply_url,
                        vault_values=vault_values,
                        tailored_motivation_essay=tailored_motivation_essay,
                        screenshots_dir=self.screenshots_dir,
                        auto_click_submit=auto_click_submit,
                    )
            except Exception as exc:
                logger.warning(
                    "Obscura submission attempt failed, falling back to Chromium: %s", exc
                )

        payload = dict(vault_values)
        payload["tailored_motivation_essay"] = tailored_motivation_essay

        driver = self._create_chromium_driver()
        try:
            driver.get(apply_url)
            time.sleep(0.4)

            inspection = DeepPageAndPdfInspector.inspect_html_content(
                html_text=driver.page_source,
                base_url=apply_url,
                resolve_linked_pdfs=False,
            )

            filled_count = 0
            uploaded_files_count = 0
            unfilled_required_labels: List[str] = []

            for field in inspection.discovered_fields:
                el = None
                try:
                    el = driver.find_element(By.CSS_SELECTOR, field.dom_selector)
                except Exception:
                    pass

                # Fallback element lookup for SPA / Google Forms dynamic attributes
                if el is None and field.dom_name:
                    try:
                        el = driver.find_element(By.NAME, field.dom_name)
                    except Exception:
                        pass

                if el is None and field.label_text:
                    try:
                        safe_label = re.sub(r'["\']', '', field.label_text[:30]).strip()
                        if safe_label:
                            candidates = driver.find_elements(
                                By.XPATH,
                                f"//input[contains(@aria-label, '{safe_label}')] | //textarea[contains(@aria-label, '{safe_label}')]",
                            )
                            if candidates:
                                el = candidates[0]
                    except Exception:
                        pass

                if el is None and field.label_text:
                    try:
                        safe_txt = re.sub(r'["\']', '', field.label_text[:25]).strip()
                        if safe_txt:
                            containers = driver.find_elements(
                                By.XPATH,
                                f"//*[contains(text(), '{safe_txt}')]/ancestor::*[@role='listitem' or contains(@class, 'Item') or contains(@class, 'ge-item')][1]",
                            )
                            if containers:
                                inner_inputs = containers[0].find_elements(
                                    By.CSS_SELECTOR,
                                    "input, textarea, [role='radio'], [role='checkbox']",
                                )
                                if inner_inputs:
                                    el = inner_inputs[0]
                    except Exception:
                        pass

                if el is None:
                    if field.required:
                        unfilled_required_labels.append(field.label_text or field.dom_name or field.dom_id or field.input_type)
                    continue

                if field.mapped_vault_key == "__auto_agree_checkbox__":
                    if not el.is_selected():
                        el.click()
                    filled_count += 1
                    continue

                val = payload.get(field.mapped_vault_key, "")
                if not val:
                    if field.required:
                        unfilled_required_labels.append(field.label_text or field.dom_name or field.dom_id or field.input_type)
                    continue

                if field.tag_name == "select":
                    sel = Select(el)
                    matched_opt = False
                    for opt in sel.options:
                        opt_txt = (opt.text or "").lower()
                        opt_val = (opt.get_attribute("value") or "").lower()
                        if val.lower() in opt_txt or val.lower() in opt_val or opt_txt in val.lower():
                            sel.select_by_visible_text(opt.text)
                            matched_opt = True
                            break
                    if matched_opt:
                        filled_count += 1
                    elif field.required:
                        unfilled_required_labels.append(field.label_text or field.dom_name or field.dom_id or "select")

                elif field.input_type == "file":
                    file_path = pathlib.Path(val).resolve()
                    if file_path.exists():
                        el.send_keys(str(file_path))
                        uploaded_files_count += 1
                        filled_count += 1
                    elif field.required:
                        unfilled_required_labels.append(field.label_text or field.dom_name or "file upload")

                elif field.input_type == "radio":
                    group = driver.find_elements(By.NAME, field.dom_name) if field.dom_name else [el]
                    target = None
                    for candidate in group:
                        candidate_label = " ".join(
                            filter(None, [
                                candidate.get_attribute("aria-label"),
                                candidate.get_attribute("value"),
                                candidate.get_attribute("id"),
                            ])
                        ).lower()
                        if val.lower() in candidate_label or candidate_label in val.lower():
                            target = candidate
                            break
                    if target is not None:
                        if not target.is_selected():
                            target.click()
                        filled_count += 1
                    elif field.required:
                        unfilled_required_labels.append(field.label_text or field.dom_name or "radio")

                elif field.input_type == "checkbox":
                    should_check = val.strip().lower() in {"1", "true", "yes", "y", "agree", "confirmed"}
                    if should_check and not el.is_selected():
                        el.click()
                        filled_count += 1
                    elif field.required and not el.is_selected():
                        unfilled_required_labels.append(field.label_text or field.dom_name or "checkbox")

                else:
                    el.clear()
                    el.send_keys(str(val))
                    filled_count += 1

            pre_shot_path = self.screenshots_dir / f"{opportunity_code}_pre_submit.png"
            driver.save_screenshot(str(pre_shot_path))

            if inspection.has_captcha_or_login_wall:
                return BrowserSubmissionReceipt(
                    status="PAUSED_AT_CAPTCHA",
                    confirmation_reference="",
                    confirmation_page_text="",
                    pre_submit_screenshot_path=str(pre_shot_path),
                    post_submit_screenshot_path="",
                    filled_dom_fields_count=filled_count,
                    uploaded_files_count=uploaded_files_count,
                    notes=f"تم تعبئة {filled_count} حقلاً بالكامل والتوقف عند حاجز {inspection.captcha_type} لتأكيده بضغطة واحدة.",
                )

            try:
                empty_required = driver.execute_script(
                    """
                    return Array.from(document.querySelectorAll('[required]')).filter((el) => {
                        if (el.type === 'checkbox' || el.type === 'radio') return !el.checked;
                        if (el.type === 'file') return !el.files || el.files.length === 0;
                        return !String(el.value || '').trim();
                    }).map((el) => el.getAttribute('aria-label') || el.getAttribute('name') || el.getAttribute('id') || el.type);
                    """
                ) or []
                for required_name in empty_required:
                    required_name = str(required_name or "").strip()
                    if required_name and required_name not in unfilled_required_labels:
                        unfilled_required_labels.append(required_name)
            except Exception:
                pass

            if unfilled_required_labels:
                return BrowserSubmissionReceipt(
                    status="READY_FOR_SUBMISSION",
                    confirmation_reference="",
                    confirmation_page_text="",
                    pre_submit_screenshot_path=str(pre_shot_path),
                    post_submit_screenshot_path="",
                    filled_dom_fields_count=filled_count,
                    uploaded_files_count=uploaded_files_count,
                    notes=(
                        "لم يتم الضغط على Submit لأن الحقول المطلوبة التالية بقيت فارغة: "
                        + ", ".join(unfilled_required_labels[:8])
                    ),
                )

            if filled_count == 0:
                return BrowserSubmissionReceipt(
                    status="READY_FOR_SUBMISSION",
                    confirmation_reference="",
                    confirmation_page_text="",
                    pre_submit_screenshot_path=str(pre_shot_path),
                    post_submit_screenshot_path="",
                    filled_dom_fields_count=0,
                    uploaded_files_count=0,
                    notes="تم فتح الرابط الحقيقي عبر المتصفح: الصفحة عبارة عن مقال إخباري أو بوابة تعريفية لا تحتوي على حقول استمارة تفاعلية مباشرة. لم يتم الضغط على Submit.",
                )

            if not auto_click_submit:
                return BrowserSubmissionReceipt(
                    status="READY_FOR_SUBMISSION",
                    confirmation_reference="",
                    confirmation_page_text="",
                    pre_submit_screenshot_path=str(pre_shot_path),
                    post_submit_screenshot_path="",
                    filled_dom_fields_count=filled_count,
                    uploaded_files_count=uploaded_files_count,
                    notes="تمت تعبئة الاستمارة في المتصفح الحقيقي دون الضغط على Submit (وضع المعاينة).",
                )

            post_shot_path = self.screenshots_dir / f"{opportunity_code}_submitted.png"
            confirmation_text = ""
            confirmation_ref = ""
            submit_clicked = False
            notes = ""
            old_url = driver.current_url
            try:
                old_body = driver.find_element(By.TAG_NAME, "body").text or ""
            except Exception:
                old_body = ""

            submit_buttons = driver.find_elements(
                By.CSS_SELECTOR,
                "button[type='submit'], input[type='submit'], #submit-btn, .submit-btn, [role='button'][aria-label*='Submit'], [role='button'][aria-label*='إرسال']",
            )
            if not submit_buttons:
                for b in driver.find_elements(
                    By.CSS_SELECTOR, "div[role='button'], span[role='button'], button"
                ):
                    txt = (b.text or "").strip().lower()
                    if txt in (
                        "submit",
                        "إرسال",
                        "send",
                        "apply",
                        "تقديم",
                        "submit application",
                    ):
                        submit_buttons = [b]
                        break

            if submit_buttons:
                submit_button = submit_buttons[0]
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
                    WebDriverWait(driver, 5).until(
                        lambda d: submit_button.is_displayed() and submit_button.is_enabled()
                    )
                    driver.execute_script("arguments[0].click();", submit_button)
                    submit_clicked = True
                    try:
                        WebDriverWait(driver, 12).until(
                            lambda d: d.current_url != old_url
                            or ((d.find_element(By.TAG_NAME, "body").text or "")[:2000] != old_body[:2000])
                        )
                    except Exception:
                        pass
                    time.sleep(0.4)
                except Exception as exc:
                    notes = f"تعذر الضغط على زر Submit: {exc}"

            driver.save_screenshot(str(post_shot_path))
            body_el = driver.find_element(By.TAG_NAME, "body")
            full_body_text = (body_el.text or "").strip()
            body_lower = full_body_text.lower()
            current_url_lower = (driver.current_url or "").lower()

            success_markers = (
                "thank you",
                "application received",
                "successfully submitted",
                "submission received",
                "we have received",
                "confirmation",
                "تم استلام",
                "تم إرسال",
                "تم التقديم",
                "تم التسجيل",
            )
            error_markers = (
                "please fill",
                "is required",
                "field is required",
                "invalid input",
                "something went wrong",
                "هذا الحقل مطلوب",
                "يرجى تعبئة",
            )
            success_found = any(marker in body_lower for marker in success_markers) or any(
                marker in current_url_lower
                for marker in ("/thanks", "/thank-you", "/success", "/submitted", "/confirmation")
            )
            validation_failed = any(marker in body_lower for marker in error_markers) and not success_found

            ref_match = re.search(
                r"\b((?:REF|SUB|APP|CONF|RECEIPT)[-_][A-Z0-9][A-Z0-9_-]{4,})\b",
                full_body_text,
                re.IGNORECASE,
            )
            if not ref_match:
                ref_match = re.search(
                    r"(?:reference|receipt|application\s*(?:id|number)|confirmation(?:\s*(?:id|number|code))?)\s*[:#-]?\s*([A-Z0-9][A-Z0-9_-]{5,})",
                    full_body_text,
                    re.IGNORECASE,
                )
            if ref_match:
                confirmation_ref = (ref_match.group(1) or ref_match.group(0)).strip()
            confirmation_text = full_body_text[:1000]

            if not submit_clicked:
                status = "READY_FOR_SUBMISSION"
                notes = notes or "تمت تعبئة الاستمارة، لكن لم يتم العثور على زر Submit موثوق. راجع الصورة وأرسل الطلب يدوياً."
            elif validation_failed:
                status = "READY_FOR_SUBMISSION"
                notes = (
                    "تم الضغط على Submit لكن الصفحة أظهرت رسالة تحقق أو رفض. "
                    "لم يتم اعتبار الطلب مقدماً؛ راجع الصورة وأكمل الحقول الناقصة."
                )
            elif confirmation_ref and success_found:
                status = "APPLIED_AUTOMATICALLY"
                notes = "تم فتح المتصفح الحقيقي وتعبئة الحقول والضغط على Submit مع رصد مرجع تأكيد في نص الصفحة."
            elif success_found:
                status = "SUBMITTED_UNCONFIRMED"
                notes = (
                    "تم الضغط على Submit وظهرت علامة نجاح، لكن لم يتم رصد مرجع تأكيد واضح. "
                    "لا تعتبر الطلب مؤكداً حتى تصل رسالة/إيصال رسمي من الجهة المنظمة."
                )
            else:
                status = "SUBMITTED_UNCONFIRMED"
                notes = (
                    "تم الضغط على Submit، لكن الصفحة لم تُظهر تأكيداً واضحاً. "
                    "لا تعتبر الطلب مؤكداً حتى تصل رسالة/إيصال رسمي من الجهة المنظمة."
                )

            return BrowserSubmissionReceipt(
                status=status,
                confirmation_reference=confirmation_ref,
                confirmation_page_text=confirmation_text,
                pre_submit_screenshot_path=str(pre_shot_path),
                post_submit_screenshot_path=str(post_shot_path),
                filled_dom_fields_count=filled_count,
                uploaded_files_count=uploaded_files_count,
                notes=notes,
            )
        finally:
            driver.quit()


@dataclasses.dataclass
class ZeroCostAuditResult:
    is_zero_cost_compliant: bool
    application_fee_zero: bool
    flights_or_transport_covered: bool
    accommodation_covered: bool
    meals_or_stipend_covered: bool
    visa_support_summary: str
    coverage_summary_ar: str
    rejection_reason: str = ""


@dataclasses.dataclass
class EligibilityAuditResult:
    is_eligible: bool
    matched_jurisdiction_track: str
    match_score: int
    rejection_reason: str = ""
    audit_notes: str = ""


class ZeroCostGatekeeper:
    """Audits opportunity terms (both webpage and extracted PDF text) to guarantee $0 cost."""

    FEE_TRAP_PATTERNS = [
        r"non-refundable\s+\$?[1-9]\d*",
        r"\$[1-9]\d*(?:\.\d+)?\s*(?:usd)?\s*(?:application|registration|processing|confirmation)\s*fee",
        r"\b[1-9]\d*\s*(?:eur|usd|rm|myr|gbp)\s*(?:application|registration|participation|confirmation)\s*fee",
        r"mandatory\s+(?:application|registration)\s+fee",
        r"participants\s+must\s+cover\s+their\s+own\s+(?:international\s+)?flight",
        r"travel\s+costs\s+are\s+not\s+covered",
        r"flights\s+are\s+not\s+included",
    ]

    ZERO_FEE_POSITIVE_PATTERNS = [
        r"no\s+application\s+fee",
        r"zero\s+application\s+fee",
        r"no\s+registration\s+fee",
        r"zero\s+registration\s+fee",
        r"free\s+registration",
        r"free\s+of\s+charge",
        r"100%\s+free",
        r"100%\s+funded",
        r"fully\s+funded",
        r"fully\s+sponsored",
        r"full\s+financial\s+support",
        r"all\s+expenses\s+(?:covered|paid)",
        r"full\s+scholarship",
        r"full\s+fellowship",
        r"tuition\s+waiver",
        r"\$0",
    ]

    def audit(self, opp: Dict[str, Any]) -> ZeroCostAuditResult:
        text = f"{opp.get('raw_description', '')} {opp.get('raw_terms_text', '')}".lower()
        is_inside_my = bool(opp.get("is_inside_malaysia", 0))

        for pattern in self.FEE_TRAP_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return ZeroCostAuditResult(
                    is_zero_cost_compliant=False,
                    application_fee_zero=False,
                    flights_or_transport_covered=False,
                    accommodation_covered=False,
                    meals_or_stipend_covered=False,
                    visa_support_summary="غير مؤهل مالياً",
                    coverage_summary_ar="",
                    rejection_reason=f"تم رصد شرط مالي غير مجاني أو عدم تغطية سفر: '{match.group(0)}'",
                )

        app_fee_zero = any(re.search(p, text) for p in self.ZERO_FEE_POSITIVE_PATTERNS)
        accomm_covered = any(
            kw in text
            for kw in [
                "accommodation", "accommodations", "hotel", "lodge", "lodging", "housing",
                "residensi", "residence", "dormitory", "camp", "bungalow", "room and board",
                "stay", "fully funded", "full scholarship", "all expenses"
            ]
        )
        meals_covered = any(
            kw in text
            for kw in [
                "meal", "meals", "food", "breakfast", "stipend", "allowance", "per diem",
                "full board", "living allowance", "room and board", "daily allowance",
                "fully funded", "full scholarship", "all expenses"
            ]
        )

        if is_inside_my:
            transport_covered = any(
                kw in text
                for kw in [
                    "flight", "transport", "bus", "shuttle", "boat", "reimbursement",
                    "transfer", "travel", "train", "fully funded", "all expenses"
                ]
            )
            visa_summary = "داخل ماليزيا (لا تحتاج فيزا سفر — إقامة طالب UTM سارية)"
            coverage_ar = "إعفاء كامل من الرسوم (0 دولار) + سكن كامل + وجبات + تغطية المواصلات الداخلية/طيران بورنيو"
        else:
            transport_covered = any(
                kw in text
                for kw in [
                    "round-trip", "roundtrip", "airfare", "flight", "flights", "kuala lumpur",
                    "kul", "international travel", "travel grant", "travel allowance",
                    "travel support", "travel expenses", "return flights", "transportation",
                    "fully funded", "all expenses", "full scholarship"
                ]
            )
            visa_summary = "تغطية رسوم الفيزا + خطاب دعوة رسمي" if "visa" in text else "دعم الفيزا متوفر ضمن المنحة"
            coverage_ar = "طيران ذهاب وعودة من كوالالمبور (KUL) + سكن كامل + وجبات/راتب جيب + 0 رسوم تقديم"

        if not (app_fee_zero and transport_covered and accomm_covered and meals_covered):
            missing = []
            if not app_fee_zero:
                missing.append("عدم تأكيد مجانية التقديم (0 رسوم)")
            if not transport_covered:
                missing.append("عدم شمول تذاكر الطيران/المواصلات")
            if not accomm_covered:
                missing.append("عدم شمول السكن")
            if not meals_covered:
                missing.append("عدم شمول الوجبات أو المخصص اليومي")
            return ZeroCostAuditResult(
                is_zero_cost_compliant=False,
                application_fee_zero=app_fee_zero,
                flights_or_transport_covered=transport_covered,
                accommodation_covered=accomm_covered,
                meals_or_stipend_covered=meals_covered,
                visa_support_summary=visa_summary,
                coverage_summary_ar="",
                rejection_reason="نقص في شروط التغطية الشاملة: " + "، ".join(missing),
            )

        return ZeroCostAuditResult(
            is_zero_cost_compliant=True,
            application_fee_zero=True,
            flights_or_transport_covered=True,
            accommodation_covered=True,
            meals_or_stipend_covered=True,
            visa_support_summary=visa_summary,
            coverage_summary_ar=coverage_ar,
            rejection_reason="",
        )


class TriJurisdictionEligibilityEngine:
    """Evaluates candidate eligibility across Syria (SY), Malaysia UTM Student Pass (MY), and Kuwait Residency (KW)."""

    FEMALE_ONLY_PATTERNS = [
        r"\bwomen\s+only\b",
        r"\bfemale\s+only\b",
        r"\bwomen\s+in\s+stem\b",
        r"\bpioneering\s+women\b",
        r"\bfemale\s+(citizens?|applicants?|students?|candidates?|leaders?)\b",
        r"\bfor\s+(women|females|girls)\b",
        r"\bopen\s+to\s+(women|females|girls)\s+only\b",
        r"\bexclusively\s+for\s+women\b",
        r"\bwomen\s+scholars?\b",
        r"\bwomen\s+fellowship\b",
        r"\bwomen'?s?\s+leadership\b",
    ]

    INELIGIBLE_DEGREE_PATTERNS = [
        r"strictly\s+restricted\s+to\s+phd",
        r"undergraduate\s+students\s+are\s+not\s+eligible",
        r"must\s+hold\s+a\s+doctorate",
        r"phd\s+candidates\s+and\s+postdoctoral\s+researchers\s+only",
        r"must\s+hold\s+a\s+(bachelor'?s?|undergraduate)\s+degree",
        r"applicants\s+must\s+have\s+completed\s+their\s+bachelor",
        r"must\s+already\s+have\s+a\s+bachelor",
        r"for\s+master'?s?\s+studies\b",
        r"master'?s?\s+degree\s+scholarship",
    ]

    def __init__(self, profile: Dict[str, Any] | None = None) -> None:
        self.profile = profile or DEFAULT_CANDIDATE_PROFILE

    @staticmethod
    def is_local_llm_available() -> bool:
        """Checks if local Ornith 1.5 (:11434) or Jev-Style (:11435) is alive on localhost."""
        for port in (11434, 11435):
            url = f"http://127.0.0.1:{port}/health"
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=0.5) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
        return False

    def evaluate(self, opp: Dict[str, Any]) -> EligibilityAuditResult:
        """
        Main entry point for candidate eligibility evaluation.
        Uses advanced AI LLM reasoning (Local Ornith 1.5 / Jev-Style / OpenRouter / Gemini)
        whenever available, with seamless deterministic fallback.
        """
        if (
            not os.environ.get("PYTEST_CURRENT_TEST")
            and not os.environ.get("ZCO_DISABLE_AI_AUDITOR")
            and (
                self.is_local_llm_available()
                or os.environ.get("OPENROUTER_API_KEY")
                or os.environ.get("GEMINI_API_KEY")
            )
        ):
            try:
                ai_verdict = self.evaluate_with_ai(opp)
                if ai_verdict is not None:
                    return ai_verdict
            except Exception as exc:
                logger.debug("AI eligibility audit failed, falling back to deterministic: %s", exc)

        return self.evaluate_deterministic(opp)

    def evaluate_with_ai(self, opp: Dict[str, Any], timeout: int = 15) -> Optional[EligibilityAuditResult]:
        candidate = self.profile.get("candidate", {})
        full_name = candidate.get("full_name", "Mohammad Mahdi")
        gender = candidate.get("gender", "male")

        candidate_summary = f"""Candidate Profile:
- Full Name: {full_name}
- Gender: {gender} (ذكر)
- Nationality: Syrian citizen (جواز سفر سوري)
- Academic Status: 1st-year Bachelor of Artificial Intelligence undergraduate student at Universiti Teknologi Malaysia (UTM) in Johor Bahru, Malaysia. Expected graduation 2028. Currently enrolled with a valid Malaysia Student Pass. Does NOT hold a completed Bachelor's degree yet.
- Primary Residency: Malaysia (Student Pass, departure hub KUL).
- Secondary Residency: Kuwait (Valid permanent family residency permit / إقامة صالحة في الكويت).
- Primary Fields: Artificial Intelligence, Machine Learning, Computer Science, Environmental Tech, Research Fellowships, Hackathons."""

        opp_title = opp.get("title", "")
        opp_desc = (opp.get("raw_description") or "")[:2200]
        opp_terms = (opp.get("raw_terms_text") or "")[:2200]
        is_my = bool(opp.get("is_inside_malaysia", 0))

        prompt = f"""You are the AI Eligibility Auditor for ZCO-Hunter, an automated opportunity matcher.
Strictly audit whether the candidate is 100% eligible for the following opportunity.

{candidate_summary}

Opportunity Details:
- Title: {opp_title}
- Inside Malaysia: {is_my}
- Track Category: {opp.get('track_category', 'GENERAL')}
- Description: {opp_desc}
- Full Terms: {opp_terms}

Strict Audit Instructions:
1. GENDER: The candidate is Male. If the opportunity is exclusively restricted to females / women (e.g. 'Women in STEM', 'Female only', 'for women'), you MUST reject it (is_eligible: false).
2. ACADEMIC DEGREE: The candidate is a current undergraduate student (1st-year Bachelor).
   - Undergraduates ARE eligible for summer internships, student research fellowships, hackathons, and youth programs, unless the program explicitly states that undergraduates are excluded or that applicants must already hold a completed degree (e.g. strictly post-graduates or degree-seeking Master's programs).
   - If the program welcomes early-career researchers, students, or candidates from diverse academic backgrounds without requiring an existing degree, the candidate IS eligible.
3. JURISDICTION / NATIONALITY: The candidate is Syrian citizen, currently residing in Malaysia on a student pass, with valid residency in Kuwait. If the opportunity is open globally, or targets MENA/Developing Countries, or ASEAN/Malaysian students, or GCC residents, he is eligible. Reject only if there is an explicit nationality/residency restriction that excludes him.
4. If eligible, identify the matching jurisdiction track in Arabic (e.g., 'الجنسية السورية', 'طالب UTM في ماليزيا', 'إقامة الكويت', or 'مفتوحة للطلبة الدوليين حول العالم').

Respond strictly in valid JSON format matching this schema:
{{
  "is_eligible": bool,
  "rejection_reason": "clear concise explanation in Arabic if not eligible, or empty string if eligible",
  "matched_jurisdiction_track": "explanation in Arabic of which track matches if eligible, or empty string",
  "match_score": integer between 0 and 100,
  "confidence": float between 0.0 and 1.0,
  "audit_notes": "brief summary of reasons in Arabic"
}}"""

        system_instruction = (
            "You are a fast deterministic JSON decision engine. Always output valid JSON object directly without long thinking."
        )

        # 1. Local GPU Acceleration via Ornith 1.5 (9B) and Jev-Style (2B)
        local_targets = [
            ("http://127.0.0.1:11434/v1/chat/completions", "ornith-1.5", "[Ornith 1.5 Local AI]"),
            ("http://127.0.0.1:11435/v1/chat/completions", "jev-decision", "[Jev-Style Local AI]"),
        ]

        for endpoint, model_name, engine_tag in local_targets:
            try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                    "max_tokens": 600,
                }
                req = urllib.request.Request(
                    endpoint,
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(payload).encode("utf-8"),
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        content = data["choices"][0]["message"]["content"]
                        parsed = json.loads(content)
                        raw_notes = str(parsed.get("audit_notes", "")).strip()
                        final_notes = f"{engine_tag} [الذكاء الاصطناعي] {raw_notes}" if raw_notes else f"{engine_tag} [الذكاء الاصطناعي] تم الفحص بنجاح."
                        return EligibilityAuditResult(
                            is_eligible=bool(parsed.get("is_eligible", False)),
                            matched_jurisdiction_track=str(parsed.get("matched_jurisdiction_track", "")),
                            match_score=int(parsed.get("match_score", 0)),
                            rejection_reason=str(parsed.get("rejection_reason", "")),
                            audit_notes=final_notes,
                        )
            except Exception as exc:
                logger.debug("Local LLM %s failed/offline: %s", model_name, exc)
                continue

        # 2. Fallback to Cloud LLMs via OpenRouter
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None

        cloud_models = [
            os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat"),
            "meta-llama/llama-3.3-70b-instruct",
        ]
        cloud_endpoint = "https://openrouter.ai/api/v1/chat/completions"

        for model in cloud_models:
            try:
                req = urllib.request.Request(
                    cloud_endpoint,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/zco-hunter",
                        "X-Title": "ZCO-Hunter",
                    },
                    data=json.dumps({
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": prompt},
                        ],
                        "response_format": {"type": "json_object"},
                    }).encode("utf-8"),
                )

                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    raw_notes = str(parsed.get("audit_notes", "")).strip()
                    final_notes = f"[Cloud AI Auditor] [الذكاء الاصطناعي] {raw_notes}" if raw_notes else "[Cloud AI Auditor] [الذكاء الاصطناعي] تم الفحص بنجاح."
                    return EligibilityAuditResult(
                        is_eligible=bool(parsed.get("is_eligible", False)),
                        matched_jurisdiction_track=str(parsed.get("matched_jurisdiction_track", "")),
                        match_score=int(parsed.get("match_score", 0)),
                        rejection_reason=str(parsed.get("rejection_reason", "")),
                        audit_notes=final_notes,
                    )
            except Exception as exc:
                logger.debug("Cloud model %s failed in evaluate_with_ai: %s", model, exc)
                continue

        return None

    def evaluate_deterministic(self, opp: Dict[str, Any]) -> EligibilityAuditResult:
        text = f"{opp.get('title', '')} {opp.get('raw_description', '')} {opp.get('raw_terms_text', '')}".lower()
        is_inside_my = bool(opp.get("is_inside_malaysia", 0))
        track = opp.get("track_category", "")

        # 1. Gender restriction check (Candidate Mohammad Mahdi is male)
        candidate_gender = self.profile.get("candidate", {}).get("gender", "male")
        if candidate_gender == "male":
            for pattern in self.FEMALE_ONLY_PATTERNS:
                if re.search(pattern, text):
                    return EligibilityAuditResult(
                        is_eligible=False,
                        matched_jurisdiction_track="",
                        match_score=0,
                        rejection_reason="الفرصة مخصصة للإناث فقط (Women / Female Only) ولا تطابق الملف الشخصي للمتقدم (ذكر).",
                    )

        # 2. Academic degree level check (Candidate is currently 1st-year Bachelor student at UTM)
        is_undergrad_friendly = any(
            re.search(pat, text)
            for pat in [
                r"\bopen\s+to\s+undergraduates?\b",
                r"\bundergraduate\s+students?\s+(are\s+)?(eligible|welcome)\b",
                r"\bfor\s+undergraduate\s+students?\b",
                r"\bcurrent\s+undergraduates?\b",
                r"\bcurrently\s+enrolled\s+in\s+(a\s+)?(bachelor|undergraduate)\b",
                r"\bsummer\s+(internship|research)\b",
                r"\bculture\s+camp\b",
            ]
        )
        for pattern in self.INELIGIBLE_DEGREE_PATTERNS:
            if re.search(pattern, text):
                if is_undergrad_friendly and ("master" in pattern or "bachelor" in pattern):
                    # If it's a fellowship/internship explicitly welcoming undergraduates too, skip
                    continue
                return EligibilityAuditResult(
                    is_eligible=False,
                    matched_jurisdiction_track="",
                    match_score=0,
                    rejection_reason="الفرصة تتطلب شهادة دراسات عليا (ماجستير/دكتوراه) أو بكالوريوس مكتمل مسبقاً، بينما المتقدم طالب بكالوريوس سنة أولى.",
                )

        matched_tracks: List[str] = []

        if is_inside_my:
            matched_tracks.append("إقامة طالب في ماليزيا (UTM - بكالوريوس ذكاء اصطناعي)")

        if any(k in text for k in ["syria", "mediterranean", "euro-med", "developing countries", "global south", "arab"]):
            matched_tracks.append("الجنسية السورية (مسار الدول النامية / الشرق الأوسط / جنوب المتوسط)")

        if any(k in text for k in ["kuwait", "gcc", "arab youth center"]):
            matched_tracks.append("إقامة الكويت السارية + الجنسية العربية (مسار الخليج والشباب العربي)")

        if not is_inside_my and any(k in text for k in ["asean region (including malaysia)", "studying at accredited universities in the asean"]):
            matched_tracks.append("طالب دولي مقيد في جامعة ماليزية معتمدة (مسار جامعات ASEAN)")

        if not is_inside_my and any(k in text for k in [
            "all nationalities",
            "international students",
            "international applicants",
            "worldwide",
            "any country",
            "global applicants",
            "open to all countries",
            "open to international",
            "non-us citizens",
            "all international",
            "foreign students",
        ]):
            matched_tracks.append("مفتوحة للطلبة الدوليين حول العالم (بما يشمل سوريا / ماليزيا / الكويت)")

        if not matched_tracks:
            return EligibilityAuditResult(
                is_eligible=False,
                matched_jurisdiction_track="",
                match_score=0,
                rejection_reason="لم يتطابق شرط الجنسية أو بلد الإقامة مع المسارات الثلاثة (سوريا / ماليزيا / الكويت).",
            )

        score = 65
        if track in ("GREEN_AI_CLIMATE_TECH", "CORE_AI_HACKATHONS"):
            score += 20
        elif track in ("NATURE_ECO_CONSERVATION", "OUTDOOR_LEADERSHIP_CAMPS"):
            score += 18
        else:
            score += 14

        if is_inside_my:
            score += 14
        elif "visa" in text and ("invitation" in text or "covered" in text or "issued" in text or "reimbursement" in text):
            score += 12

        if len(matched_tracks) >= 2:
            score += 3

        return EligibilityAuditResult(
            is_eligible=True,
            matched_jurisdiction_track=" + ".join(matched_tracks),
            match_score=min(99, score),
            rejection_reason="",
            audit_notes="تطابق كامل مع العمر (20 سنة)، المستوى الدراسي (سنة أولى بكالوريوس AI في UTM)، وشروط الأهلية.",
        )


def load_seed_from_master_profile(config_dir: pathlib.Path) -> Dict[str, str]:
    seed = dict(INITIAL_KNOWN_VAULT_SEED)
    master_yaml = config_dir / "master_profile.yaml"

    # Deliberately do not seed the vault from master_profile.example.yaml.
    # Placeholder names/emails must never be treated as the candidate's real
    # facts just because a private profile has not been created yet.
    if master_yaml.exists():
        try:
            import yaml
            with open(master_yaml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            p = data.get("personal", {})
            edu = data.get("education", {})
            if p.get("full_name_en"):
                seed["full_name"] = p["full_name_en"]
            if p.get("full_name_ar"):
                seed["full_name_ar"] = p["full_name_ar"]
            if p.get("email"):
                seed["email_address"] = p["email"]
            if p.get("phone_my"):
                seed["phone_whatsapp_my"] = p["phone_my"]
            if p.get("date_of_birth"):
                seed["date_of_birth"] = str(p["date_of_birth"])
            if p.get("age"):
                seed["age"] = str(p["age"])
            if p.get("nationality"):
                seed["nationality"] = f"{p['nationality']} ({p.get('nationality_code', 'SY')})"
            if p.get("residency_primary"):
                seed["primary_residency_country"] = "Malaysia (MY)"
                seed["malaysia_visa_type"] = p["residency_primary"]
            if p.get("residency_secondary"):
                seed["secondary_residency_country"] = p["residency_secondary"]
            if p.get("current_residence"):
                seed["residential_address_my"] = p["current_residence"]
            if p.get("departure_hub"):
                seed["departure_airport"] = p["departure_hub"]
            if p.get("dietary_preference"):
                seed["dietary_preference"] = p["dietary_preference"]
            if p.get("apparel_size"):
                seed["tshirt_and_gear_size"] = p["apparel_size"]
            activity_prefs = p.get("activity_preferences")
            if isinstance(activity_prefs, list):
                activity_prefs = ", ".join(str(item) for item in activity_prefs)
            if activity_prefs:
                seed["activity_preferences"] = str(activity_prefs)
            if p.get("location_preference"):
                seed["location_preference"] = p["location_preference"]
            if p.get("availability_from"):
                seed["availability_from"] = str(p["availability_from"])
            if p.get("availability_to"):
                seed["availability_to"] = str(p["availability_to"])
            if p.get("github_url"):
                seed["github_or_portfolio_url"] = p["github_url"]
            if edu.get("institution"):
                seed["university_name"] = edu["institution"]
            if edu.get("degree"):
                seed["degree_and_major"] = edu["degree"]
            if edu.get("academic_year"):
                seed["academic_year"] = edu["academic_year"]
            if edu.get("matric_number"):
                seed["utm_matric_number"] = edu["matric_number"]
            if edu.get("cgpa"):
                seed["current_cgpa"] = str(edu["cgpa"])
            if edu.get("english_proficiency"):
                seed["english_proficiency"] = edu["english_proficiency"]
        except Exception:
            pass
    return seed


class CandidateMemoryVault:
    """
    Self-learning persistent memory store that remembers every fact, document path,
    and essay answer Mohammad provides so he is never asked the same question twice.
    """

    def __init__(
        self,
        db: OpportunityDatabase,
        profile_json_path: Optional[pathlib.Path] = None,
    ) -> None:
        self.db = db
        self.profile_json_path = profile_json_path or CANDIDATE_PROFILE_PATH
        self._ensure_initial_seed()

    def _ensure_initial_seed(self) -> None:
        existing = self.db.get_all_vault_fields()
        config_dir = self.profile_json_path.parent
        dynamic_seed = load_seed_from_master_profile(config_dir)
        for key, val in dynamic_seed.items():
            if key not in existing:
                meta = STANDARD_FIELD_CATALOG.get(key, {})
                self.db.upsert_vault_field(
                    field_key=key,
                    field_value=val,
                    field_label_ar=meta.get("label_ar", key),
                    category=meta.get("category", "baseline"),
                    source="master_profile_seed",
                )

    def get_known_fields(self) -> Dict[str, str]:
        records = self.db.get_all_vault_fields()
        return {k: v["field_value"] for k, v in records.items() if str(v["field_value"]).strip()}

    def inspect_missing_fields_for_opportunity(
        self, opp: Dict[str, Any]
    ) -> Tuple[Dict[str, str], List[Dict[str, str]]]:
        known = self.get_known_fields()
        custom_req = json.loads(opp.get("required_form_fields_json") or "[]")
        track = opp.get("track_category", "CORE_AI_HACKATHONS")
        required_keys = custom_req if custom_req else DEFAULT_REQUIRED_FIELDS_BY_TRACK.get(track, [])

        filled_payload: Dict[str, str] = {}
        missing_fields: List[Dict[str, str]] = []

        for key in required_keys:
            norm_key = key.strip().lower()
            # These are generated/attached by the engine, not user-supplied fields.
            if norm_key in {
                "tailored_motivation_essay",
                "cv_pdf_path",
                "upload_cv",
                "upload_resume",
                "resume",
            }:
                continue
            if norm_key in known and known[norm_key]:
                filled_payload[norm_key] = known[norm_key]
            else:
                meta = STANDARD_FIELD_CATALOG.get(
                    norm_key,
                    {"label_ar": f"حقل إضافي مطلوب للاستمارة ({norm_key})", "category": "custom"},
                )
                missing_fields.append(
                    {
                        "field_key": norm_key,
                        "label_ar": meta["label_ar"],
                        "category": meta["category"],
                    }
                )

        return filled_payload, missing_fields

    def learn_from_user_answers(self, answers: Dict[str, str]) -> Dict[str, Any]:
        learned_keys: List[str] = []
        for raw_key, raw_val in answers.items():
            key = raw_key.strip().lower()
            val = str(raw_val).strip()
            if not val:
                continue
            meta = STANDARD_FIELD_CATALOG.get(
                key,
                {"label_ar": key, "category": "learned_custom"},
            )
            self.db.upsert_vault_field(
                field_key=key,
                field_value=val,
                field_label_ar=meta["label_ar"],
                category=meta["category"],
                source="learned_from_user_once",
            )
            learned_keys.append(key)

        self._sync_to_profile_json()
        return {
            "learned_fields_count": len(learned_keys),
            "learned_keys": learned_keys,
            "total_vault_fields": len(self.get_known_fields()),
        }

    def learn_from_user(self, key: str, val: str) -> None:
        """Helper to learn a single field from the user and persist immediately."""
        self.learn_from_user_answers({key: val})

    def set_known_field(self, key: str, val: str) -> None:
        """Persist or update a single field in the memory vault."""
        self.learn_from_user_answers({key: val})

    def _sync_to_profile_json(self) -> None:
        existing_data: Dict[str, Any] = {}
        if self.profile_json_path.exists():
            try:
                existing_data = json.loads(self.profile_json_path.read_text(encoding="utf-8"))
            except Exception:
                existing_data = {}
        elif (self.profile_json_path.parent / "candidate_profile.example.json").exists():
            try:
                existing_data = json.loads(
                    (self.profile_json_path.parent / "candidate_profile.example.json").read_text(
                        encoding="utf-8"
                    )
                )
            except Exception:
                existing_data = {}
        if not isinstance(existing_data, dict):
            existing_data = {}

        existing_data["learned_memory_vault"] = self.get_known_fields()
        existing_data["vault_last_synced_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        try:
            atomic_write_json(self.profile_json_path, existing_data)
        except OSError as exc:
            logger.warning("Could not write candidate profile JSON: %s", exc)

        # Synchronize with master_profile.yaml as single source of truth.
        master_yaml_path = self.profile_json_path.parent / "master_profile.yaml"
        if master_yaml_path.exists():
            try:
                import yaml

                ydata = yaml.safe_load(master_yaml_path.read_text(encoding="utf-8")) or {}
                if not isinstance(ydata, dict):
                    raise ValueError("master_profile.yaml root must be a mapping")
                known = self.get_known_fields()
                p = ydata.setdefault("personal", {})
                edu = ydata.setdefault("education", {})
                personal_mapping = {
                    "full_name": "full_name_en",
                    "email_address": "email",
                    "phone_whatsapp_my": "phone_my",
                    "residential_address_my": "current_residence",
                    "passport_number": "passport_number",
                    "github_or_portfolio_url": "github_url",
                }
                for source_key, target_key in personal_mapping.items():
                    if source_key in known:
                        p[target_key] = known[source_key]
                education_mapping = {
                    "utm_matric_number": "matric_number",
                    "current_cgpa": "cgpa",
                }
                for source_key, target_key in education_mapping.items():
                    if source_key in known:
                        edu[target_key] = known[source_key]
                atomic_write_text(
                    master_yaml_path,
                    yaml.safe_dump(ydata, allow_unicode=True, sort_keys=False),
                )
            except Exception as exc:
                logger.warning("Could not sync master profile YAML: %s", exc)


class AutonomousApplicantEngine:
    """
    Executes autonomous form filling and real Chromium submission for verified opportunities.
    """

    def __init__(
        self,
        db: OpportunityDatabase,
        vault: CandidateMemoryVault,
        screenshots_dir: Optional[pathlib.Path] = None,
    ) -> None:
        self.db = db
        self.vault = vault
        self.screenshots_dir = screenshots_dir or (db.db_path.parent / "screenshots")
        self.browser_filler = RealBrowserFormAutoFiller(screenshots_dir=self.screenshots_dir)

    def synthesize_motivation_statement(
        self, opp: Dict[str, Any], known: Dict[str, str]
    ) -> str:
        """
        Synthesizes an authentic, compelling 250-300 word Statement of Purpose
        tailored to the specific opportunity mission, domain, and organizer,
        anchoring strictly to candidate's actual projects, coursework, and tri-jurisdiction background.
        Saves the resulting essay to the SQLite `learned_qa_bank` table for semantic reuse.
        """
        opp_code = opp.get("opportunity_code") or f"ID-{opp.get('id', 'opp')}"
        q_key = f"motivation_statement_{opp_code}"

        # 1. Load verified profile first so cached essays can be checked against it.
        try:
            from typst_agentic_cv_engine import MasterProfileManager

            profile_data = MasterProfileManager().data
        except Exception as exc:
            logger.warning("Could not load master profile for essay synthesis: %s", exc)
            try:
                profile_data = PortfolioManager().data
            except Exception:
                profile_data = {}

        title = opp.get("title", "International Academic Opportunity")
        organizer = opp.get("organizer", "the Host Organization")
        track = opp.get("track_category", "GENERAL")
        desc = opp.get("raw_description", "")
        city = opp.get("location_city", "Host City")
        country = opp.get("location_country", "Host Country")

        from writing_rules import (
            build_motivation_letter,
            build_motivation_prompt,
            validate_motivation_essay,
        )

        existing_qa = self.db.get_all_learned_qa()
        if q_key in existing_qa:
            cached_essay = existing_qa[q_key]["answer_text"]
            cached_check = validate_motivation_essay(cached_essay, profile_data, opp)
            if cached_check["ok"]:
                self.db.increment_qa_reuse(q_key)
                return cached_essay
            logger.info(
                "Regenerating stale cached essay for %s: %s",
                opp_code,
                cached_check["issues"],
            )

        # 2. Optional LLM pass. Its output is accepted only if it passes the
        # same style and fact-grounding checks as the deterministic writer.
        essay_text = ""
        gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if gemini_api_key:
            try:
                prompt = build_motivation_prompt(opp, profile_data)
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_api_key}"
                req_data = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
                req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    candidate_essay = resp_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                candidate_check = validate_motivation_essay(candidate_essay, profile_data, opp)
                if candidate_check["ok"]:
                    essay_text = candidate_essay
                else:
                    logger.info(
                        "Rejected LLM essay for %s: %s",
                        opp_code,
                        candidate_check["issues"],
                    )
            except Exception as exc:
                logger.debug("Gemini LLM essay synthesis fallback: %s", exc)

        # 3. Deterministic grounded writer. This is the normal path when no
        # API key is configured and the fallback when an LLM output fails.
        if not essay_text:
            essay_text = build_motivation_letter(opp, profile_data)
            final_check = validate_motivation_essay(essay_text, profile_data, opp)
            if not final_check["ok"]:
                logger.warning(
                    "Grounded essay still has style issues for %s: %s",
                    opp_code,
                    final_check["issues"],
                )

        # 4. Save to persistent learned_qa_bank
        prompt_ar = f"رسالة الدافع المخصصة لفرصة {title} ({organizer})"
        tags = ["motivation_statement", track]
        try:
            self.db.upsert_learned_qa(
                question_key=q_key,
                question_prompt_ar=prompt_ar,
                answer_text=essay_text,
                tags=tags,
            )
        except Exception as exc:
            logger.warning("Failed to save essay to learned_qa_bank: %s", exc)

        return essay_text

    def attempt_auto_application(
        self,
        opp: Dict[str, Any],
        allow_submit: bool = False,
        force_resubmit: bool = False,
    ) -> Dict[str, Any]:
        """Prepare (and optionally submit) one application.

        Submission is disabled by default. Even when ``allow_submit`` is True,
        the opportunity is only marked ``APPLIED_AUTOMATICALLY`` when the browser
        captured a real confirmation reference. A clicked-but-unconfirmed submit
        is recorded as ``SUBMITTED_UNCONFIRMED`` and never reported as success.

        ``force_resubmit`` is intentionally explicit: already-submitted
        opportunities are not submitted twice by accident.
        """
        opp_id = opp["id"]
        opp_code = opp.get("opportunity_code") or f"ID-{opp_id}"
        apply_url = opp.get("apply_url", "")

        current_status = opp.get("status")
        preflight_result = None
        # Run the read-only check before the duplicate guard for unconfirmed
        # rows: an old synthetic "submitted" record may point at a homepage and
        # should be corrected to APPLICATION_FAILED. A genuinely confirmed
        # application is never downgraded by a transient network error.
        needs_preflight = not (
            current_status == OpportunityStatus.APPLIED_AUTOMATICALLY
            and not force_resubmit
        )
        if needs_preflight:
            preflight_result = preflight_application(opp)
            if not preflight_result.ok:
                notes = f"تم إيقاف التقديم قبل فتح المتصفح: {preflight_result.reason}"
                self.db.record_application_attempt(
                    opportunity_id=opp_id,
                    opportunity_code=opp_code,
                    new_status=OpportunityStatus.APPLICATION_FAILED,
                    filled_payload={
                        "apply_url": apply_url,
                        "preflight": preflight_result.summary(),
                        "prepared_timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    },
                    missing_fields=[],
                    confirmation_ref="",
                    notes=notes,
                )
                return {
                    "opportunity_code": opp_code,
                    "title": opp.get("title", ""),
                    "application_status": OpportunityStatus.APPLICATION_FAILED,
                    "filled_fields_count": 0,
                    "missing_fields": [],
                    "confirmation_ref": "",
                    "notes": notes,
                    "preflight": preflight_result.summary(),
                }

        if (
            allow_submit
            and not force_resubmit
            and current_status
            in (
                OpportunityStatus.APPLIED_AUTOMATICALLY,
                OpportunityStatus.SUBMITTED_UNCONFIRMED,
            )
        ):
            try:
                receipt = json.loads(opp.get("submission_receipt_json") or "{}")
            except (TypeError, ValueError):
                receipt = {}
            notes = "تم تسجيل هذه الفرصة مسبقاً؛ تم منع إعادة الإرسال لتجنب طلب مكرر."
            return {
                "opportunity_code": opp_code,
                "title": opp.get("title", ""),
                "application_status": current_status,
                "filled_fields_count": 0,
                "missing_fields": [],
                "confirmation_ref": receipt.get("confirmation_ref", ""),
                "notes": notes,
                "preflight": preflight_result.summary() if preflight_result else None,
            }

        if apply_url.startswith("file://"):
            try:
                inspection = self.browser_filler.inspect_live_url_with_browser(apply_url)
                if inspection.required_vault_keys:
                    opp["required_form_fields_json"] = json.dumps(
                        inspection.required_vault_keys, ensure_ascii=False
                    )
            except Exception:
                pass

        filled_payload, missing_fields = self.vault.inspect_missing_fields_for_opportunity(opp)

        if missing_fields:
            notes = "الطلب متوقف بانتظار حقول جديدة لم تُحفظ بعد في خزنة الذاكرة."
            self.db.record_application_attempt(
                opportunity_id=opp_id,
                opportunity_code=opp_code,
                new_status=OpportunityStatus.PAUSED_NEEDS_USER_INPUT,
                filled_payload=filled_payload,
                missing_fields=missing_fields,
                confirmation_ref="",
                notes=notes,
            )
            return {
                "opportunity_code": opp_code,
                "title": opp["title"],
                "application_status": OpportunityStatus.PAUSED_NEEDS_USER_INPUT,
                "filled_fields_count": len(filled_payload),
                "missing_fields": missing_fields,
                "confirmation_ref": "",
                "notes": notes,
            }

        known = self.vault.get_known_fields()
        cv_required = False
        try:
            from typst_agentic_cv_engine import (
                is_cv_required_for_opportunity,
                synthesize_tailored_typst_cv,
            )

            cv_required, cv_reason = is_cv_required_for_opportunity(opp)
            if cv_required:
                cv_res: Dict[str, Any] = {}
                try:
                    cv_res = synthesize_tailored_typst_cv(opp, force=True)
                except Exception as exc:
                    cv_res = {"status": "failed", "error": str(exc), "pdf_path": None}

                pdf_path = pathlib.Path(str(cv_res.get("pdf_path") or ""))
                cv_ok = (
                    cv_res.get("status") == "generated"
                    and pdf_path.is_file()
                    and pdf_path.stat().st_size > 1000
                )
                if not cv_ok:
                    err = cv_res.get("error") or cv_res.get("reason") or "ملف PDF غير موجود أو فارغ"
                    notes = f"تعذر توليد السيرة الذاتية المطلوبة لهذه الفرصة: {err}"
                    self.db.record_application_attempt(
                        opportunity_id=opp_id,
                        opportunity_code=opp_code,
                        new_status=OpportunityStatus.APPLICATION_FAILED,
                        filled_payload=filled_payload,
                        missing_fields=[],
                        confirmation_ref="",
                        notes=notes,
                    )
                    return {
                        "opportunity_code": opp_code,
                        "title": opp["title"],
                        "application_status": OpportunityStatus.APPLICATION_FAILED,
                        "filled_fields_count": len(filled_payload),
                        "missing_fields": [],
                        "confirmation_ref": "",
                        "notes": notes,
                    }

                custom_cv_path = str(pdf_path)
                known["cv_pdf_path"] = custom_cv_path
                filled_payload["cv_pdf_path"] = custom_cv_path
                self.vault.set_known_field("cv_pdf_path", custom_cv_path)
            else:
                known.pop("cv_pdf_path", None)
                filled_payload.pop("cv_pdf_path", None)
        except Exception as exc:
            notes = f"تعذر التحقق من متطلبات السيرة الذاتية: {exc}"
            self.db.record_application_attempt(
                opportunity_id=opp_id,
                opportunity_code=opp_code,
                new_status=OpportunityStatus.APPLICATION_FAILED,
                filled_payload=filled_payload,
                missing_fields=[],
                confirmation_ref="",
                notes=notes,
            )
            return {
                "opportunity_code": opp_code,
                "title": opp["title"],
                "application_status": OpportunityStatus.APPLICATION_FAILED,
                "filled_fields_count": len(filled_payload),
                "missing_fields": [],
                "confirmation_ref": "",
                "notes": notes,
            }

        essay = self.synthesize_motivation_statement(opp, known)
        filled_payload["tailored_motivation_essay"] = essay
        filled_payload["prepared_via"] = "ZCO-Engine Real Chromium Applicant"
        filled_payload["prepared_timestamp_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        filled_payload["preflight"] = preflight_result.summary()
        if preflight_result.warnings:
            logger.warning("Preflight warnings for %s: %s", opp_code, preflight_result.warnings)

        if not allow_submit:
            notes = (
                "تم تجهيز الطلب بالكامل (الحقول + السيرة الذاتية + خطاب الدافع) "
                "ولم يتم الضغط على Submit. بانتظار موافقة بشرية صريحة."
            )
            self.db.record_application_attempt(
                opportunity_id=opp_id,
                opportunity_code=opp_code,
                new_status=OpportunityStatus.READY_FOR_REVIEW,
                filled_payload=filled_payload,
                missing_fields=[],
                confirmation_ref="",
                notes=notes,
            )
            return {
                "opportunity_code": opp_code,
                "title": opp["title"],
                "application_status": OpportunityStatus.READY_FOR_REVIEW,
                "filled_fields_count": len(filled_payload),
                "missing_fields": [],
                "confirmation_ref": "",
                "notes": notes,
            }

        confirmation_ref = ""
        pre_shot = ""
        post_shot = ""
        notes = ""
        final_status = OpportunityStatus.APPLICATION_FAILED

        try:
            receipt = self.browser_filler.fill_and_submit_application(
                opportunity_code=opp_code,
                apply_url=apply_url,
                vault_values=known,
                tailored_motivation_essay=essay,
                auto_click_submit=True,
            )
            confirmation_ref = receipt.confirmation_reference
            pre_shot = receipt.pre_submit_screenshot_path
            post_shot = receipt.post_submit_screenshot_path
            notes = receipt.notes
            filled_payload["pre_submit_screenshot"] = pre_shot
            filled_payload["post_submit_screenshot"] = post_shot
            filled_payload["confirmation_page_text"] = receipt.confirmation_page_text
            filled_payload["submitted_timestamp_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()

            if receipt.status == "APPLIED_AUTOMATICALLY" and confirmation_ref:
                final_status = OpportunityStatus.APPLIED_AUTOMATICALLY
            elif receipt.status in ("APPLIED_AUTOMATICALLY", "SUBMITTED_UNCONFIRMED"):
                final_status = OpportunityStatus.SUBMITTED_UNCONFIRMED
                confirmation_ref = ""
            elif receipt.status == "PAUSED_AT_CAPTCHA":
                final_status = OpportunityStatus.PAUSED_AT_CAPTCHA
            elif receipt.status == "READY_FOR_SUBMISSION":
                final_status = OpportunityStatus.READY_FOR_REVIEW
            else:
                final_status = OpportunityStatus.APPLICATION_FAILED
        except Exception as exc:
            logger.warning("Browser automation attempt failed for %s: %s", opp_code, exc)
            final_status = OpportunityStatus.APPLICATION_FAILED
            notes = f"تعذر استكمال التقديم عبر المتصفح: {exc}. لم يتم تأكيد أي تقديم."

        self.db.record_application_attempt(
            opportunity_id=opp_id,
            opportunity_code=opp_code,
            new_status=final_status,
            filled_payload=filled_payload,
            missing_fields=[],
            confirmation_ref=confirmation_ref,
            notes=notes,
        )
        return {
            "opportunity_code": opp_code,
            "title": opp["title"],
            "application_status": final_status,
            "filled_fields_count": len(filled_payload),
            "missing_fields": [],
            "confirmation_ref": confirmation_ref,
            "pre_submit_screenshot": pre_shot,
            "post_submit_screenshot": post_shot,
            "notes": notes,
        }

    def process_all_pending_applications(
        self,
        allow_submit: bool = False,
    ) -> Dict[str, Any]:
        candidates = (
            self.db.get_opportunities_by_status(OpportunityStatus.VERIFIED_ELIGIBLE)
            + self.db.get_opportunities_by_status(OpportunityStatus.PAUSED_NEEDS_USER_INPUT)
        )
        applied_list: List[Dict[str, Any]] = []
        unconfirmed_list: List[Dict[str, Any]] = []
        ready_list: List[Dict[str, Any]] = []
        paused_list: List[Dict[str, Any]] = []
        failed_list: List[Dict[str, Any]] = []
        consolidated_missing_questions: Dict[str, Dict[str, Any]] = {}

        for opp in candidates:
            res = self.attempt_auto_application(opp, allow_submit=allow_submit)
            status = res["application_status"]
            if status == OpportunityStatus.APPLIED_AUTOMATICALLY:
                applied_list.append(res)
            elif status == OpportunityStatus.SUBMITTED_UNCONFIRMED:
                unconfirmed_list.append(res)
            elif status == OpportunityStatus.READY_FOR_REVIEW:
                ready_list.append(res)
            elif status in (
                OpportunityStatus.PAUSED_NEEDS_USER_INPUT,
                OpportunityStatus.PAUSED_AT_CAPTCHA,
            ):
                paused_list.append(res)
                for mf in res.get("missing_fields", []):
                    key = mf["field_key"]
                    if key not in consolidated_missing_questions:
                        consolidated_missing_questions[key] = {
                            "field_key": key,
                            "label_ar": mf["label_ar"],
                            "needed_by_opportunities": [],
                        }
                    consolidated_missing_questions[key]["needed_by_opportunities"].append(
                        res["opportunity_code"]
                    )
            else:
                failed_list.append(res)

        return {
            "submit_enabled": allow_submit,
            "total_evaluated_for_application": len(candidates),
            "applied_automatically_count": len(applied_list),
            "applied_automatically": applied_list,
            "submitted_unconfirmed_count": len(unconfirmed_list),
            "submitted_unconfirmed": unconfirmed_list,
            "ready_for_review_count": len(ready_list),
            "ready_for_review": ready_list,
            "paused_needs_input_count": len(paused_list),
            "paused_opportunities": paused_list,
            "application_failed_count": len(failed_list),
            "application_failed": failed_list,
            "consolidated_questions_for_user": list(consolidated_missing_questions.values()),
        }


def audit_opportunity_record(
    opp: Dict[str, Any],
    profile: Dict[str, Any] | None = None,
) -> Tuple[ZeroCostAuditResult, EligibilityAuditResult]:
    apply_url = opp.get("apply_url", "")
    if apply_url.startswith("file://"):
        local_html_path = pathlib.Path(urllib.parse.unquote(apply_url.replace("file://", "")))
        if local_html_path.exists():
            rep = DeepPageAndPdfInspector.inspect_html_content(
                html_text=local_html_path.read_text(encoding="utf-8"),
                base_url=apply_url,
                resolve_linked_pdfs=True,
            )
            combined_pdf = "\n".join(rep.extracted_pdf_texts)
            opp["raw_terms_text"] = f"{opp.get('raw_terms_text', '')}\n{rep.extracted_full_text}\n{combined_pdf}"
            if rep.required_vault_keys:
                opp["required_form_fields_json"] = json.dumps(rep.required_vault_keys, ensure_ascii=False)

    gatekeeper = ZeroCostGatekeeper()
    eligibility_engine = TriJurisdictionEligibilityEngine(profile=profile)
    return gatekeeper.audit(opp), eligibility_engine.evaluate(opp)