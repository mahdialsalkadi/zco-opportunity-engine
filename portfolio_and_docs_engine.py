#!/usr/bin/env python3
"""
ZCO Hunter - Comprehensive Portfolio & Document Synthesis Engine
Author: Mohammad Mahdi Alsalkadi & Antigravity AI
Version: 5.1.0

Manages authentic candidate profile, ATS-compliant CV generation,
and context-tailored Motivation Letters / Statements of Purpose.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import threading
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import yaml

from file_utils import atomic_write_json, atomic_write_text
from paths import (
    CONFIG_DIR,
    CV_MD_FILE,
    CV_PDF_FILE,
    DATA_DIR,
    DOCS_DIR,
    PORTFOLIO_FILE,
)

logger = logging.getLogger("ZCO-PortfolioDocs")

BASE_DIR = pathlib.Path(__file__).resolve().parent


ACTIVITY_PREFERENCE_OPTIONS_AR: Dict[str, str] = {
    "NATURE_ECO_CONSERVATION": "الطبيعة والبيئة والحفظ البيئي",
    "GREEN_AI_CLIMATE_TECH": "الذكاء الاصطناعي الأخضر وتقنيات المناخ",
    "CORE_AI_HACKATHONS": "هاكاثونات ومسابقات الذكاء الاصطناعي",
    "OUTDOOR_LEADERSHIP_CAMPS": "المعسكرات الميدانية والقيادة الخارجية",
    "COMMUNITY_VOLUNTEERING_EXCHANGE": "التطوع المجتمعي والتبادل الثقافي",
    "MENA_GCC_ASEAN_SPECIAL": "فرص الشرق الأوسط والخليج وآسيان",
}

LOCATION_PREFERENCE_OPTIONS_AR: Dict[str, str] = {
    "INSIDE_MALAYSIA": "داخل ماليزيا فقط",
    "OUTSIDE_MALAYSIA": "خارج ماليزيا فقط",
    "ANY": "داخل وخارج ماليزيا",
}


AUTHENTIC_PORTFOLIO: Dict[str, Any] = {
    "personal": {
        "full_name_en": "Mohammad Mahdi Alsalkadi",
        "full_name_ar": "محمد مهدي السلقدي",
        "email": "candidate@example.com",
        "personal_email": "candidate@example.com",
        "phone_my": "+60 11-0000 0000",
        "phone_kw": "+000 0000 0000",
        "date_of_birth": "2000-01-01",
        "age": 20,
        "nationality": "Syrian",
        "nationality_ar": "سوري",
        "passport_number": "N00000000",
        "residency_kuwait": "Valid Kuwait Residency (Iqama)",
        "malaysia_pass": "Valid International Student Pass (UTM)",
        "address_my": "Kuala Lumpur, Malaysia",
        "address_kw": "State of Kuwait (Valid Residency)",
        "departure_airport": "KUL (Kuala Lumpur International Airport)",
        "linkedin_url": "",
        "github_url": "",
        "portfolio_url": "",
        "dietary_preference": "Halal (حلال)",
        "tshirt_size": "M (Medium)",
        "activity_preferences": "",
        "location_preference": "",
        "availability_from": "",
        "availability_to": "",
        "swimming_fitness": "Capable swimmer, enthusiastic outdoor camper & trekker",
        "emergency_contact": "Family Contact - Kuwait"
    },
    "education": {
        "current_institution": "Universiti Teknologi Malaysia (UTM)",
        "institution_ar": "جامعة التكنولوجيا ماليزيا (UTM)",
        "faculty": "Faculty of Computing",
        "degree": "Bachelor of Computer Science (Artificial Intelligence) with Honours",
        "degree_ar": "بكالوريوس علوم الحاسوب (الذكاء الاصطناعي) مع مرتبة الشرف",
        "academic_year": "Year 1 (Undergraduate)",
        "academic_year_ar": "السنة الأولى (بكالوريوس)",
        "matric_number": "A00000000",
        "cgpa": "3.53 / 4.00",
        "graduation_expected": "2028",
        "english_proficiency": "",
        "key_coursework": [
            "Programming Fundamentals (Python / C++)",
            "Discrete Structures",
            "Data Structures & Algorithmic Problem Solving",
            "Linear Algebra & Calculus for Computing",
            "Artificial Intelligence Fundamentals",
            "Computer Organization and Architecture"
        ]
    },
    "skills": {
        "programming_languages": ["Python (Foundational / Intermediate)", "C++ (Basic)", "SQL", "Bash"],
        "ai_machine_learning": [
            "PyTorch (Actively Learning & Experimenting)",
            "Machine Learning Fundamentals",
            "Data Preprocessing & Analysis (NumPy, Pandas)",
            "Prompt Engineering & Agentic Workflow Design"
        ],
        "developer_tools": ["Git & GitHub", "Linux / Command Line", "VS Code", "Jupyter Notebook", "Selenium Automation"],
        "languages": [
            {"language": "Arabic", "proficiency": "Native (اللغة الأم)"},
            {"language": "English", "proficiency": "Intermediate / Academic Working (IELTS 5.5)"}
        ],
        "outdoor_and_personal_strengths": [
            "Outdoor Camping & Trekking Resilience",
            "Swimming Capability",
            "High Eagerness to Learn & Fast Adaptation",
            "Multi-Cultural Background (Syrian Citizen, Kuwait Resident, Studying in Malaysia)"
        ]
    },
    "projects": [
        {
            "title": "Autonomous Zero-Cost Opportunity Hunter (ZCO-Hunter)",
            "role": "Creator & Student Developer",
            "period": "2025 - Present",
            "tech_stack": ["Python", "AsyncIO", "SQLite", "Telegram Bot API", "Selenium"],
            "description": "Building an autonomous agentic pipeline designed to monitor global portals for 100% fully-funded scholarships, research internships, and biodiversity youth camps, assisting international students with automated verification.",
            "impact": "Engineered real-time Telegram approval workflows, multi-jurisdictional criteria audits, and headless browser form verification."
        },
        {
            "title": "UTM AI & Computing Academic Coursework Repository",
            "role": "Developer",
            "period": "2024 - 2025",
            "tech_stack": ["Python", "C++", "Algorithms", "Git"],
            "description": "Implemented foundational algorithmic solutions, object-oriented concepts, and computational problem-solving exercises as part of the Year 1 Artificial Intelligence curriculum at UTM.",
            "impact": "Maintained a strong academic record with a CGPA of 3.53 with Honours."
        },
        {
            "title": "PyTorch Machine Learning Experiments",
            "role": "Learner & Experimenter",
            "period": "2025",
            "tech_stack": ["Python", "PyTorch", "Jupyter", "Matplotlib"],
            "description": "Actively building and training introductory neural networks, exploring supervised classification pipelines, loss functions, and optimization techniques.",
            "impact": "Developing practical intuition for deep learning workflows and edge AI applications."
        }
    ],
    "experience_and_volunteering": [
        {
            "organization": "Universiti Teknologi Malaysia (Faculty of Computing)",
            "role": "Year 1 Artificial Intelligence Undergraduate",
            "period": "2024 - Present",
            "location": "Kuala Lumpur / Johor Bahru, Malaysia",
            "details": "Active engagement in university computing events, collaborative peer study groups, and hands-on coding challenges."
        },
        {
            "organization": "Outdoor & Field Conservation Readiness",
            "role": "Outdoor Enthusiast & Nature Explorer",
            "period": "Ongoing",
            "location": "Malaysia",
            "details": "Enthusiastic about wilderness camping, tropical forest hiking, and eco-conservation field expeditions. Fully capable in swimming and outdoor group coordination."
        }
    ],
    "awards_and_honors": [
        {
            "title": "Bachelor of Computer Science (AI) with Honours Candidacy",
            "issuer": "Universiti Teknologi Malaysia (UTM)",
            "year": "2024 - 2025",
            "details": "Admitted to the competitive Artificial Intelligence Honours track at UTM, achieving a 3.53 CGPA."
        }
    ],
    "research_interests": [
        "Foundational Deep Learning & PyTorch Development",
        "Green AI & Ecological Computing (AI for Rainforest & Biodiversity Protection)",
        "Agentic AI & Automated Workflow Systems",
        "Applied AI for Sustainable Development"
    ]
}


PROFILE_FIELD_LOCATIONS: Dict[str, Tuple[str, str]] = {
    "full_name_en": ("personal", "full_name_en"),
    "email": ("personal", "email"),
    "phone_my": ("personal", "phone_my"),
    "passport_number": ("personal", "passport_number"),
    "address_my": ("personal", "address_my"),
    "activity_preferences": ("personal", "activity_preferences"),
    "location_preference": ("personal", "location_preference"),
    "availability_from": ("personal", "availability_from"),
    "availability_to": ("personal", "availability_to"),
    "cgpa": ("education", "cgpa"),
    "matric_number": ("education", "matric_number"),
    "github_url": ("personal", "github_url"),
}

VAULT_KEY_BY_PROFILE_FIELD: Dict[str, str] = {
    "full_name_en": "full_name",
    "email": "email_address",
    "phone_my": "phone_whatsapp_my",
    "passport_number": "passport_number",
    "address_my": "residential_address_my",
    "activity_preferences": "activity_preferences",
    "location_preference": "location_preference",
    "availability_from": "availability_from",
    "availability_to": "availability_to",
    "cgpa": "current_cgpa",
    "matric_number": "utm_matric_number",
    "github_url": "github_or_portfolio_url",
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+0-9()\-\s]{6,30}$")
_PASSPORT_RE = re.compile(r"^[A-Za-z0-9-]{5,20}$")
_MATRIC_RE = re.compile(r"^[A-Za-z0-9-]{3,30}$")
_CGPA_RE = re.compile(r"^\d{1,2}(\.\d{1,2})?(\s*/\s*\d{1,2}(\.\d{1,2})?)?$")


def normalize_profile_updates(
    values: Dict[str, Any],
) -> Tuple[Dict[str, str], List[str]]:
    """Trim and validate fields explicitly supplied by the dashboard.

    Empty strings are preserved so the caller can distinguish "clear this
    field" from "leave it untouched". The model's ``model_fields_set`` is the
    source of that distinction, not truthiness.
    """
    cleaned: Dict[str, str] = {}
    errors: List[str] = []
    for field, raw in values.items():
        if raw is None:
            continue
        value = str(raw).strip()
        cleaned[field] = value
        if not value:
            continue

        if field == "full_name_en":
            if len(value) > 120:
                errors.append("full_name_en must be 120 characters or fewer.")
            if any(ord(ch) < 32 for ch in value):
                errors.append("full_name_en contains control characters.")
        elif field == "email":
            if len(value) > 254 or not _EMAIL_RE.match(value):
                errors.append("email is not a valid address.")
        elif field == "phone_my":
            if not _PHONE_RE.match(value):
                errors.append("phone_my must contain only digits, spaces, +, -, or parentheses.")
        elif field == "passport_number":
            if not _PASSPORT_RE.match(value):
                errors.append("passport_number must be 5-20 letters, digits, or hyphens.")
        elif field == "matric_number":
            if not _MATRIC_RE.match(value):
                errors.append("matric_number must be 3-30 letters, digits, or hyphens.")
        elif field == "cgpa":
            if not _CGPA_RE.match(value):
                errors.append("cgpa must look like 3.53 or 3.53 / 4.00.")
        elif field == "address_my":
            if len(value) > 300:
                errors.append("address_my must be 300 characters or fewer.")
        elif field == "activity_preferences":
            tracks = [part.strip() for part in value.split(",") if part.strip()]
            unknown = [
                track for track in tracks if track not in ACTIVITY_PREFERENCE_OPTIONS_AR
            ]
            if unknown:
                errors.append(
                    "activity_preferences contains unknown tracks: "
                    + ", ".join(unknown)
                )
            elif len(set(tracks)) != len(tracks):
                errors.append("activity_preferences contains duplicate tracks.")
            else:
                cleaned[field] = ", ".join(tracks)
        elif field == "location_preference":
            if value not in LOCATION_PREFERENCE_OPTIONS_AR:
                errors.append(
                    "location_preference must be INSIDE_MALAYSIA, "
                    "OUTSIDE_MALAYSIA, or ANY."
                )
        elif field in ("availability_from", "availability_to"):
            try:
                dt.date.fromisoformat(value)
            except ValueError:
                errors.append(f"{field} must be a valid ISO date (YYYY-MM-DD).")
        elif field == "github_url":
            if len(value) > 300:
                errors.append("github_url must be 300 characters or fewer.")
            else:
                parsed = urlparse(value)
                if parsed.scheme not in ("http", "https") or not parsed.netloc:
                    errors.append("github_url must be an absolute http(s) URL.")
        else:
            errors.append(f"Unknown profile field: {field}")

    start = cleaned.get("availability_from", "")
    end = cleaned.get("availability_to", "")
    if start and end:
        try:
            if dt.date.fromisoformat(start) > dt.date.fromisoformat(end):
                errors.append("availability_from must be on or before availability_to.")
        except ValueError:
            pass
    return cleaned, errors


class PortfolioManager:
    """Manages profile persistence, CV generation, and Motivation Letter drafting."""

    def __init__(
        self,
        portfolio_path: Optional[pathlib.Path] = None,
        config_dir: Optional[pathlib.Path] = None,
    ) -> None:
        self.config_dir = pathlib.Path(config_dir) if config_dir else CONFIG_DIR
        self.portfolio_path = (
            pathlib.Path(portfolio_path)
            if portfolio_path
            else self.config_dir / "comprehensive_portfolio.json"
        )
        self._lock = threading.RLock()
        self.data: Dict[str, Any] = {}
        self.load_or_initialize()

    def load_or_initialize(self) -> Dict[str, Any]:
        """Loads portfolio from JSON or initializes with authentic template."""
        if self.portfolio_path.exists():
            try:
                with open(self.portfolio_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    raise ValueError("portfolio JSON root must be an object")
                self.data = loaded
                # Ensure updated fields are merged
                self._ensure_updated_fields()
                return self.data
            except Exception as e:
                logger.error("Failed to load portfolio: %s", e)
                stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup = self.portfolio_path.with_name(
                    f"{self.portfolio_path.name}.corrupt-{stamp}"
                )
                try:
                    shutil.copy2(self.portfolio_path, backup)
                    logger.error("Preserved unreadable portfolio at %s", backup)
                except OSError as backup_exc:
                    logger.error("Could not preserve unreadable portfolio: %s", backup_exc)

        self.data = json.loads(json.dumps(AUTHENTIC_PORTFOLIO))
        self.save()
        return self.data

    def _ensure_updated_fields(self) -> None:
        """Merge new keys from AUTHENTIC_PORTFOLIO without overwriting user edits."""
        import copy

        def _merge_missing(target: Dict[str, Any], defaults: Dict[str, Any]) -> None:
            for key, default_value in defaults.items():
                if key not in target:
                    target[key] = copy.deepcopy(default_value)
                elif isinstance(default_value, dict) and isinstance(target.get(key), dict):
                    _merge_missing(target[key], default_value)

        for section, defaults in AUTHENTIC_PORTFOLIO.items():
            if section not in self.data:
                self.data[section] = copy.deepcopy(defaults)
            elif isinstance(defaults, dict) and isinstance(self.data.get(section), dict):
                _merge_missing(self.data[section], defaults)

    def save(self) -> None:
        """Persist portfolio data and sync derived private profiles atomically."""
        with self._lock:
            atomic_write_json(self.portfolio_path, self.data)
            try:
                self._sync_candidate_profile()
            except Exception as exc:
                logger.warning("Could not sync candidate_profile.json: %s", exc)
            try:
                self._sync_master_profile()
            except Exception as exc:
                logger.warning("Could not sync master_profile.yaml: %s", exc)

    def update_profile(self, values: Dict[str, str]) -> Dict[str, Any]:
        """Apply normalized profile fields, including explicit empty clears."""
        with self._lock:
            for field, value in values.items():
                location = PROFILE_FIELD_LOCATIONS.get(field)
                if location is None:
                    continue
                section, key = location
                self.data.setdefault(section, {})[key] = value
                if field == "email":
                    self.data.setdefault("personal", {})["personal_email"] = value
            self.save()
            return dict(self.data)

    @staticmethod
    def vault_keys_to_clear(values: Dict[str, str]) -> set[str]:
        """Vault keys whose dashboard values were explicitly emptied."""
        return {
            VAULT_KEY_BY_PROFILE_FIELD[field]
            for field, value in values.items()
            if field in VAULT_KEY_BY_PROFILE_FIELD and value == ""
        }

    def _sync_candidate_profile(self) -> None:
        candidate_path = self.config_dir / "candidate_profile.json"
        example_path = self.config_dir / "candidate_profile.example.json"
        cfg: Dict[str, Any] = {}
        source_path = candidate_path if candidate_path.exists() else example_path
        if source_path.exists():
            cfg = json.loads(source_path.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            cfg = {}
        candidate = cfg.setdefault("candidate", {})
        personal = self.data.get("personal", {})
        education = self.data.get("education", {})
        mapping = {
            "full_name": personal.get("full_name_en"),
            "email": personal.get("email"),
            "phone": personal.get("phone_my"),
            "passport_number": personal.get("passport_number"),
            "matric_number": education.get("matric_number"),
            "cgpa": education.get("cgpa"),
            "github": personal.get("github_url"),
            "address": personal.get("address_my"),
            "activity_preferences": personal.get("activity_preferences"),
            "location_preference": personal.get("location_preference"),
            "availability_from": personal.get("availability_from"),
            "availability_to": personal.get("availability_to"),
        }
        for key, value in mapping.items():
            if value is not None:
                candidate[key] = value
        atomic_write_json(candidate_path, cfg)

    def _sync_master_profile(self) -> bool:
        master_path = self.config_dir / "master_profile.yaml"
        if not master_path.exists():
            return False
        ydata = yaml.safe_load(master_path.read_text(encoding="utf-8")) or {}
        if not isinstance(ydata, dict):
            raise ValueError("master_profile.yaml root must be a mapping")
        personal = ydata.setdefault("personal", {})
        education = ydata.setdefault("education", {})
        source_personal = self.data.get("personal", {})
        source_education = self.data.get("education", {})
        personal_mapping = {
            "full_name_en": "full_name_en",
            "email": "email",
            "phone_my": "phone_my",
            "passport_number": "passport_number",
            "github_url": "github_url",
            "address_my": "current_residence",
            "activity_preferences": "activity_preferences",
            "location_preference": "location_preference",
            "availability_from": "availability_from",
            "availability_to": "availability_to",
        }
        for source_key, target_key in personal_mapping.items():
            if source_key in source_personal:
                personal[target_key] = source_personal[source_key]
        for source_key, target_key in (
            ("matric_number", "matric_number"),
            ("cgpa", "cgpa"),
        ):
            if source_key in source_education:
                education[target_key] = source_education[source_key]
        atomic_write_text(
            master_path,
            yaml.safe_dump(ydata, allow_unicode=True, sort_keys=False),
        )
        return True

    def sync_to_sqlite_vault(
        self, db_conn, clear_keys: Optional[set[str]] = None
    ) -> None:
        """Syncs all key fields from portfolio into SQLite candidate_vault table.

        ``clear_keys`` contains vault field keys the user explicitly emptied in
        the dashboard. Those rows are deleted instead of silently retaining the
        previous value.
        """
        p = self.data.get("personal", {})
        edu = self.data.get("education", {})

        mappings = [
            ("full_name", p.get("full_name_en", ""), "identity", "الاسم الكامل بالإنجليزية"),
            ("full_name_ar", p.get("full_name_ar", ""), "identity", "الاسم الكامل بالعربية"),
            ("age", str(p.get("age", "") or ""), "identity", "العمر"),
            ("date_of_birth", p.get("date_of_birth", ""), "identity", "تاريخ الميلاد"),
            ("nationality", (f"{p.get('nationality')} ({p.get('nationality_code', 'SY')})" if p.get("nationality") else ""), "jurisdiction", "الجنسية"),
            ("primary_residency_country", "Malaysia (MY)", "jurisdiction", "دولة الإقامة الأساسية"),
            ("residential_address_my", p.get("address_my", ""), "contact", "عنوان السكن في كوالالمبور"),
            ("malaysia_visa_type", p.get("malaysia_pass", ""), "jurisdiction", "نوع التأشيرة في ماليزيا"),
            ("secondary_residency_country", "Kuwait (Valid Residency / Iqama)", "jurisdiction", "دولة الإقامة الثانوية (الكويت)"),
            ("university_name", edu.get("current_institution", ""), "academic", "اسم الجامعة"),
            ("degree_and_major", edu.get("degree", ""), "academic", "الدرجة والتخصص"),
            ("academic_year", edu.get("academic_year", ""), "academic", "المرحلة الدراسية"),
            ("utm_matric_number", edu.get("matric_number", ""), "academic", "الرقم الجامعي (UTM Matric)"),
            ("current_cgpa", edu.get("cgpa", ""), "academic", "المعدل التراكمي (CGPA)"),
            ("english_proficiency", edu.get("english_proficiency", ""), "academic", "مستوى اللغة الإنجليزية"),
            ("departure_airport", p.get("departure_airport", ""), "logistics", "مطار المغادرة المفضل"),
            ("email_address", p.get("email", ""), "contact", "البريد الإلكتروني الرسمي"),
            ("phone_whatsapp_my", p.get("phone_my", ""), "contact", "رقم الهاتف / واتساب"),
            ("passport_number", p.get("passport_number", ""), "identity", "رقم جواز السفر"),
            ("github_or_portfolio_url", p.get("github_url", ""), "academic", "رابط GitHub أو المعرض البرمجي"),
            ("dietary_preference", p.get("dietary_preference", ""), "logistics", "التفضيلات الغذائية"),
            ("tshirt_and_gear_size", p.get("tshirt_size", ""), "logistics", "مقاس القميص والمعدات الميدانية"),
            ("activity_preferences", p.get("activity_preferences", ""), "preferences", "تفضيلات أنواع الأنشطة"),
            ("location_preference", p.get("location_preference", ""), "preferences", "تفضيل موقع الفرصة (داخل/خارج ماليزيا)"),
            ("availability_from", p.get("availability_from", ""), "availability", "تاريخ بداية الإتاحة"),
            ("availability_to", p.get("availability_to", ""), "availability", "تاريخ نهاية الإتاحة"),
            ("swimming_and_outdoor_fitness", p.get("swimming_fitness", ""), "outdoor", "اللياقة الميدانية والسباحة والتخييم"),
            ("cv_pdf_path", str(CV_PDF_FILE), "documents", "مسار ملف السيرة الذاتية PDF"),
        ]

        cursor = db_conn.cursor()
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        clear_keys = clear_keys or set()
        for key, val, cat, label_ar in mappings:
            if val in (None, ""):
                if key in clear_keys:
                    cursor.execute(
                        "DELETE FROM candidate_vault WHERE field_key = ?", (key,)
                    )
                continue
            cursor.execute(
                """
                INSERT INTO candidate_vault (field_key, field_label_ar, field_value, category, source, updated_at)
                VALUES (?, ?, ?, ?, 'user_input_verified', ?)
                ON CONFLICT(field_key) DO UPDATE SET
                    field_value = excluded.field_value,
                    field_label_ar = excluded.field_label_ar,
                    category = excluded.category,
                    updated_at = excluded.updated_at
                """,
                (key, label_ar, str(val), cat, now_iso),
            )
        db_conn.commit()

    def update_field(self, section: str, key: str, value: Any) -> None:
        """Updates a specific field in the portfolio and saves."""
        if section not in self.data:
            self.data[section] = {}
        self.data[section][key] = value
        self.save()

    # =========================================================================
    # ATS-Compliant Professional CV / Resume Generator (General & Tailored)
    # =========================================================================

    def _discover_chromium_binary(self) -> str:
        """Discovers available Chromium or Chrome executable binary."""
        candidates = [
            pathlib.Path.home() / ".cache/ms-playwright/chromium-1234/chrome-linux64/chrome",
            pathlib.Path("/usr/bin/chromium"),
            pathlib.Path("/usr/bin/chromium-browser"),
            pathlib.Path("/usr/bin/google-chrome"),
        ]
        playwright_dir = pathlib.Path.home() / ".cache/ms-playwright"
        if playwright_dir.exists():
            for p in playwright_dir.glob("chromium-*/chrome-linux64/chrome"):
                if p.is_file():
                    candidates.insert(0, p)
        for cand in candidates:
            if cand.exists() and os.access(cand, os.X_OK):
                return str(cand)
        raise FileNotFoundError("Could not locate Chromium binary to render CV PDF")

    def generate_cv_html(self, opp: Optional[Dict[str, Any]] = None) -> str:
        """
        Generates modern, elegant, single-page printable HTML for CV.
        If an opportunity dict (opp) is passed, customizes the subtitle, target objective,
        project ordering, and skill priorities specifically for that opportunity!
        """
        p = self.data.get("personal", {})
        edu = self.data.get("education", {})
        skills = self.data.get("skills", {})
        projects = list(self.data.get("projects", []))
        experience = list(self.data.get("experience_and_volunteering", []))
        awards = self.data.get("awards_and_honors", [])

        # Default values
        subtitle = f"{edu.get('degree')} | Universiti Teknologi Malaysia (UTM)"
        objective_html = ""

        # Opportunity-Specific Tailoring
        if opp:
            title = opp.get("title", "")
            title_upper = title.upper()
            organizer = opp.get("organizer", "")
            track_upper = str(opp.get("track_category", "")).upper()
            opp_code = opp.get("opportunity_code", "")

            # Tailor Subtitle
            subtitle = f"Target Candidate: {title} | Universiti Teknologi Malaysia"

            # 1. Scientific Research Internships (Caltech, UTokyo, Amgen, Harvard)
            if any(k in title_upper or k in track_upper for k in ["CALTECH", "AMGEN", "UTOKYO", "HARVARD", "RESEARCH"]):
                objective_text = (
                    f"First-year Artificial Intelligence honours undergraduate at Universiti Teknologi Malaysia (CGPA 3.53) "
                    f"with strong foundations in algorithmic problem solving and active deep learning development with PyTorch. "
                    f"Specifically seeking the {title} ({organizer}) to contribute high dedication, mathematical rigor, and "
                    f"collaborative inquiry to university laboratory research."
                )
                # Prioritize PyTorch and academic algorithms
                projects.sort(key=lambda prj: 0 if "PyTorch" in prj["title"] or "Academic" in prj["title"] else 1)

            # 2. AI Governance, Safety & Policy (GovAI London)
            elif any(k in title_upper or k in track_upper for k in ["GOVAI", "GOVERNANCE", "POLICY", "SAFETY", "ETHICS"]):
                objective_text = (
                    f"First-year Artificial Intelligence honours student at UTM with strong foundations in autonomous systems and algorithmic auditing. "
                    f"Dedicated to the safety, ethical alignment, and international governance of advanced AI systems. "
                    f"Applying for the {title} in London to analyze systemic AI deployment trajectories across emerging and developing economies."
                )
                # Prioritize autonomous systems, rule engines, and agentic workflows
                projects.sort(key=lambda prj: 0 if "ZCO-Hunter" in prj["title"] or "Autonomous" in prj["title"] else 1)

            # 3. Nature, Conservation & Green-AI Camps (FRIM, Borneo)
            elif any(k in title_upper or k in track_upper for k in ["NATURE", "CONSERVATION", "GREEN", "ECO", "FOREST", "FRIM", "WILDLIFE"]):
                objective_text = (
                    f"Artificial Intelligence undergraduate at UTM combining technical computing with high outdoor resilience, "
                    f"wilderness camping passion, and swimming capability. Enthusiastic applicant for {title}, eager to apply "
                    f"lightweight edge AI and sensor monitoring to tropical rainforest biodiversity preservation and field conservation."
                )
                # Prioritize field readiness and ZCO-Hunter
                experience.sort(key=lambda exp: 0 if "Outdoor" in exp.get("organization", "") else 1)

            # 4. Global Leadership & Youth Summits (Universal Youth Leadership, Mastercard)
            else:
                objective_text = (
                    f"Ambitious Artificial Intelligence student at Universiti Teknologi Malaysia (CGPA 3.53 with Honours). "
                    f"Multilingual (Arabic native, English academic) with a multicultural bridge connecting the Arab world and Southeast Asia. "
                    f"Applying for {title} to contribute technical innovation, youth leadership, and cross-border collaboration."
                )

            objective_html = f"""
            <div class="section-title">Candidate Focus & Program Alignment</div>
            <div class="objective-box">
                <p class="item-desc"><strong>Target Opportunity:</strong> <em>{title} ({organizer})</em></p>
                <p class="item-desc" style="margin-top:2px;">{objective_text}</p>
            </div>
            """

        projects_html = ""
        for prj in projects:
            tech_badges = "".join(f"<span class='badge'>{t}</span>" for t in prj.get("tech_stack", []))
            projects_html += f"""
            <div class="item">
                <div class="item-header">
                    <span class="item-title">{prj['title']}</span>
                    <span class="item-period">{prj.get('period', '')}</span>
                </div>
                <div class="item-subtitle">{prj.get('role', '')}</div>
                <p class="item-desc">{prj['description']}</p>
                <div class="item-meta">
                    <strong>Highlight:</strong> {prj.get('impact', '')}
                </div>
                <div class="tech-stack">{tech_badges}</div>
            </div>
            """

        exp_html = ""
        for exp in experience:
            exp_html += f"""
            <div class="item">
                <div class="item-header">
                    <span class="item-title">{exp['organization']}</span>
                    <span class="item-period">{exp.get('period', '')}</span>
                </div>
                <div class="item-subtitle">{exp.get('role', '')} | {exp.get('location', '')}</div>
                <p class="item-desc">{exp.get('details', '')}</p>
            </div>
            """

        awards_html = ""
        for aw in awards:
            awards_html += f"""
            <div class="award-item">
                <span class="award-title">🏆 {aw['title']}</span> — <span class="award-issuer">{aw['issuer']}</span> ({aw.get('year', '')})
                <div class="award-desc">{aw.get('details', '')}</div>
            </div>
            """

        prog_langs = ", ".join(skills.get("programming_languages", []))
        ai_ml = ", ".join(skills.get("ai_machine_learning", []))
        tools = ", ".join(skills.get("developer_tools", []))
        langs = ", ".join(f"{l['language']} ({l['proficiency']})" for l in skills.get("languages", []))
        strengths = ", ".join(skills.get("outdoor_and_personal_strengths", []))

        # Kuwait residency is strictly contingent on explicit GCC / Kuwait mandate
        is_gcc_mandated = any(
            k in f"{opp.get('title', '')} {opp.get('raw_description', '')} {opp.get('raw_terms_text', '')}".lower()
            for k in ["kuwait", "gcc", "gulf countries", "الكويت", "الخليج", "مجلس التعاون"]
        ) if opp else False
        residency_badge = "<span>🌍 Syrian Citizen (Kuwait Resident)</span>" if is_gcc_mandated else "<span>🌍 Syrian Citizen</span>"

        github_contact_html = (
            f'<span>🌐 <a href="{p.get("github_url")}">github.com/mahdialsalkadi</a></span>'
            if (opp and opp.get("is_github_mandated"))
            else ""
        )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
    @page {{
        size: A4;
        margin: 11mm 13mm 11mm 13mm;
    }}
    * {{
        box-sizing: border-box;
        margin: 0;
        padding: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }}
    body {{
        color: #222;
        background: #fff;
        line-height: 1.38;
        font-size: 10pt;
    }}
    .header {{
        text-align: center;
        border-bottom: 2px solid #1a365d;
        padding-bottom: 6px;
        margin-bottom: 8px;
    }}
    .header h1 {{
        font-size: 20pt;
        color: #1a365d;
        font-weight: 700;
        letter-spacing: -0.5px;
        margin-bottom: 2px;
    }}
    .header .subtitle {{
        font-size: 10.5pt;
        color: #2b6cb0;
        font-weight: 600;
        margin-bottom: 4px;
    }}
    .contact-line {{
        font-size: 8.6pt;
        color: #4a5568;
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 10px;
    }}
    .contact-line a {{
        color: #2b6cb0;
        text-decoration: none;
    }}
    .section-title {{
        font-size: 10.2pt;
        font-weight: 700;
        text-transform: uppercase;
        color: #1a365d;
        border-bottom: 1px solid #cbd5e0;
        padding-bottom: 2px;
        margin-top: 8px;
        margin-bottom: 5px;
        letter-spacing: 0.5px;
    }}
    .objective-box {{
        background: #f7fafc;
        border-left: 3px solid #2b6cb0;
        padding: 6px 10px;
        margin-bottom: 6px;
        border-radius: 2px;
    }}
    .item {{
        margin-bottom: 6px;
    }}
    .item-header {{
        display: flex;
        justify-content: space-between;
        align-items: baseline;
    }}
    .item-title {{
        font-weight: 700;
        color: #2d3748;
        font-size: 10pt;
    }}
    .item-period {{
        font-size: 8.6pt;
        color: #718096;
        font-weight: 500;
    }}
    .item-subtitle {{
        font-size: 9pt;
        color: #4a5568;
        font-style: italic;
        margin-bottom: 2px;
    }}
    .item-desc {{
        font-size: 8.8pt;
        color: #333;
        line-height: 1.35;
        text-align: justify;
    }}
    .item-meta {{
        font-size: 8.6pt;
        color: #2c5282;
        margin-top: 2px;
    }}
    .tech-stack {{
        margin-top: 2px;
    }}
    .badge {{
        display: inline-block;
        background: #edf2f7;
        color: #2d3748;
        font-size: 7.2pt;
        padding: 1px 4px;
        border-radius: 3px;
        margin-right: 3px;
        font-weight: 500;
    }}
    .skills-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 8.8pt;
    }}
    .skills-table td {{
        padding: 2px 0;
        vertical-align: top;
    }}
    .skills-table .label {{
        width: 24%;
        font-weight: 600;
        color: #2d3748;
    }}
    .skills-table .val {{
        color: #4a5568;
    }}
    .award-item {{
        margin-bottom: 3px;
        font-size: 8.8pt;
    }}
    .award-title {{
        font-weight: 600;
        color: #2d3748;
    }}
    .award-issuer {{
        color: #4a5568;
        font-style: italic;
    }}
    .award-desc {{
        font-size: 8.2pt;
        color: #718096;
    }}
</style>
</head>
<body>

<div class="header">
    <h1>{p.get('full_name_en', 'Mohammad Mahdi Alsalkadi')}</h1>
    <div class="subtitle">{subtitle}</div>
    <div class="contact-line">
        <span>📍 Kuala Lumpur, Malaysia</span>
        <span>📧 <a href="mailto:{p.get('email')}">{p.get('email')}</a></span>
        <span>📱 {p.get('phone_my')}</span>
        {github_contact_html}
        {residency_badge}
    </div>
</div>

{objective_html}

<div class="section-title">Education & Academic Foundation</div>
<div class="item">
    <div class="item-header">
        <span class="item-title">{edu.get('current_institution')}</span>
        <span class="item-period">{edu.get('academic_year')} (Graduation: {edu.get('graduation_expected')})</span>
    </div>
    <div class="item-subtitle">{edu.get('degree')} — {edu.get('faculty')} | CGPA: <strong>{edu.get('cgpa')}</strong></div>
    <p class="item-desc"><strong>Core Coursework:</strong> {', '.join(edu.get('key_coursework', []))}</p>
    <p class="item-desc" style="margin-top:2px;"><strong>English Language Proficiency:</strong> {edu.get('english_proficiency')}</p>
</div>

<div class="section-title">Applied Projects & Practical Systems</div>
{projects_html}

<div class="section-title">Field Readiness, Activities & Leadership</div>
{exp_html}

<div class="section-title">Technical Skills & Competencies</div>
<table class="skills-table">
    <tr>
        <td class="label">Programming:</td>
        <td class="val">{prog_langs}</td>
    </tr>
    <tr>
        <td class="label">Machine Learning:</td>
        <td class="val">{ai_ml}</td>
    </tr>
    <tr>
        <td class="label">Developer Tools:</td>
        <td class="val">{tools}</td>
    </tr>
    <tr>
        <td class="label">Languages:</td>
        <td class="val">{langs}</td>
    </tr>
    <tr>
        <td class="label">Field & Strengths:</td>
        <td class="val">{strengths}</td>
    </tr>
</table>

</body>
</html>"""
        return html

    def render_cv_pdf(self, output_pdf_path: Optional[pathlib.Path] = None, opp: Optional[Dict[str, Any]] = None) -> pathlib.Path:
        """Renders the CV to a professional PDF using headless Chromium."""
        target_path = output_pdf_path or CV_PDF_FILE
        target_path.parent.mkdir(parents=True, exist_ok=True)

        html_content = self.generate_cv_html(opp=opp)
        temp_html_path = target_path.parent / f"temp_{target_path.stem}.html"
        with open(temp_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        binary = self._discover_chromium_binary()
        cmd = [
            binary,
            "--headless",
            "--disable-gpu",
            f"--print-to-pdf={target_path}",
            "--print-to-pdf-no-header",
            temp_html_path.as_uri(),
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        if temp_html_path.exists():
            temp_html_path.unlink()

        if res.returncode != 0 or not target_path.exists():
            raise RuntimeError(f"Chromium failed to render PDF: {res.stderr.decode('utf-8', errors='ignore')}")

        logger.info("Successfully generated CV PDF at %s (%d bytes)", target_path, target_path.stat().st_size)
        return target_path

    def render_custom_cv_for_opportunity(self, opp: Dict[str, Any], force: bool = True) -> pathlib.Path:
        """
        Renders a fully customized, tailored PDF CV specifically optimized for this opportunity
        using the 4-layer Typst Agentic Engine.
        """
        try:
            from typst_agentic_cv_engine import synthesize_tailored_typst_cv
            res = synthesize_tailored_typst_cv(opp, force=force)
            if res.get("pdf_path") and pathlib.Path(res["pdf_path"]).exists():
                return pathlib.Path(res["pdf_path"])
        except Exception as e:
            logger.warning("Typst synthesis failed, falling back to legacy renderer: %s", e)

        opp_code = opp.get("opportunity_code") or f"ID-{opp.get('id', 'opp')}"
        clean_code = re.sub(r"[^A-Za-z0-9_-]", "_", opp_code)
        custom_dir = DOCS_DIR / "custom_cvs"
        custom_dir.mkdir(parents=True, exist_ok=True)
        target_path = custom_dir / f"CV_Mohammad_Alsalkadi_{clean_code}.pdf"

        return self.render_cv_pdf(output_pdf_path=target_path, opp=opp)

    # =========================================================================
    # High-Impact Dynamic Motivation Letter & SOP Synthesizer
    # =========================================================================

    def synthesize_tailored_motivation_letter(self, opp: Dict[str, Any]) -> str:
        """Return a grounded motivation statement built from the real profile.

        The old template opened with "I am writing to express my enthusiastic
        application" and padded the essay with generic claims. The writer now
        selects one real project and one real experience, states the candidate's
        limits honestly, and is validated by :mod:`writing_rules`.
        """
        from writing_rules import build_motivation_letter

        try:
            from typst_agentic_cv_engine import MasterProfileManager

            profile = MasterProfileManager().data
        except Exception:
            profile = self.data
        return build_motivation_letter(opp, profile)


# =============================================================================
# Simplified Arabic Explanation Generator for Telegram Cards
# =============================================================================

def get_opportunity_arabic_explanation(opp: Dict[str, Any]) -> str:
    """
    Generates a concise, friendly, and informative Arabic explanation of the opportunity
    for display in Telegram cards and notifications.
    """
    code = opp.get("opportunity_code", "")
    title = opp.get("title", "")
    organizer = opp.get("organizer", "")
    city = opp.get("location_city", "")
    country = opp.get("location_country", "")
    track = opp.get("track_category", "")
    desc = opp.get("raw_description", "")

    # Curated high-precision Arabic descriptions for key opportunities
    if "CALTECH" in title.upper():
        return (
            "برنامج تدريب بحثي صيفي مرموق مدفوع التكاليف بالكامل لمدة 10 أسابيع في معهد كاليفورنيا للتكنولوجيا (Caltech) بأمريكا. "
            "يتيح لطلبة البكالوريوس إجراء أبحاث علمية وهندسية متقدمة في مختبرات الجامعة تحت إشراف أساتذة عالميين، "
            "مع تغطية كاملة لتذاكر الطيران، السكن الجامعي، ومكافأة مالية سخية (راتب شهري يقارب $7,000)."
        )
    if "UTOKYO" in title.upper() or "AMGEN" in title.upper():
        return (
            "برنامج تدريب بحثي صيفي رائد وممول بالكامل في جامعة طوكيو باليابان لطلبة البكالوريوس عبر مؤسسة أمجن (Amgen Scholars). "
            "يشمل العمل العملي في أحدث المعامل البحثية باليابان، تغطية تذاكر السفر ذهاباً وإياباً، السكن المجاني، "
            "بدل معيشة شهري، والمشاركة في المؤتمر الختامي لعلماء أمجن في آسيا."
        )
    if "GOVAI" in title.upper():
        return (
            "زمالة صيفية ممولة بالكامل لمدة 3 أشهر في العاصمة البريطانية لندن متخصصة في حوكمة وأمان وسياسات الذكاء الاصطناعي (AI Governance & Safety). "
            "فرصة استثنائية لطلاب الذكاء الاصطناعي للعمل جنباً إلى جنب مع كبار الباحثين في المملكة المتحدة، "
            "وتغطي تكاليف السفر إلى لندن، السكن، وتوفر راتباً شهرياً مجزياً وتأشيرة بريطانية."
        )
    if "UNIVERSAL YOUTH LEADERSHIP" in title.upper() or "MALAYSIA 2027" in title.upper():
        return (
            "قمة قيادية شبابية دولية ممولة بالكامل تُعقد هنا في كوالالمبور بماليزيا. تجمع قادة الشباب والطلاب من جميع أنحاء العالم "
            "للمشاركة في ورش عمل القيادة وحل المشكلات العالمية، مع تغطية كاملة للإقامة الفندقية، الوجبات، وتكاليف المؤتمر."
        )
    if "HARVARD" in title.upper():
        return (
            "دليل ومنح جامعة هارفارد الأمريكية الممولة بالكامل للطلبة الدوليين. تضمن تغطية الرسوم الدراسية 100% "
            "مع توفير سكن جامعي وتأمين صحي ومصروف شهري يضمن الدراسة في أرقى جامعة عالمية دون أي أعباء مالية."
        )
    if "MASTERCARD" in title.upper():
        return (
            "برنامج منح مؤسسة ماستركارد المرموقة، يقدم منحاً دراسية شاملة 100% للطلاب المتميزين من الدول النامية. "
            "تشمل الرسوم الدراسية، السكن، تذاكر الطيران السنوية، الكتب، ومصروف جيب شهري كامل."
        )
    if "WWF" in title.upper() or "BEACH CLEANUP" in title.upper():
        return (
            "معسكر تطوعي ميداني ممول بالكامل لحماية السواحل والشعاب المرجانية وتنظيف الشواطئ في جزر تيومان ولنكاوي بماليزيا. "
            "يشمل التخييم الميداني، ومسح الكائنات البحرية، وإزالة المخلفات البلاستيكية مع تغطية كاملة للإقامة والوجبات ومعدات الحماية ومواصلات القوارب."
        )
    if "TURTLE" in title.upper() or "JUARA" in title.upper():
        return (
            "مخيم بيئي تطوعي على شواطئ جزيرة تيومان بماليزيا يركز على حماية السلاحف البحرية ومراقبة وتفقيس الأعشاش وتنظيف الشواطئ، "
            "مع توفير سكن مجاني كامل، وجبات يومية، ومعدات الغطس والأنشطة الميدانية المناسبة لمحبي السباحة والتخييم."
        )
    if "SOLS" in title.upper() or "CHILD DIGITAL" in title.upper() or "COMMUNITY YOUTH" in title.upper():
        return (
            "برنامج زمالة وتطوع مجتمعي ممول بالكامل في كوالالمبور وسيلانجور (قريب من سكنك في سيماراك)، "
            "يركز على تعليم أطفال المجتمعات الأقل حظاً واليافعين أساسيات الحاسوب واللغة الإنجليزية، مع توفير سكن وبدل معيشة شهري وبطاقة مواصلات مجانية."
        )
    if "FOREST HERITAGE" in title.upper() or "BIO-MONITORING" in title.upper():
        return (
            "مخيم تطوعي بيئي وتخييم غابي لمدة 5 أيام في محمية FRIM الطبيعية بسيلانجور. "
            "يركز على صيانة المسارات البيئية، مراقبة الطيور والحياة البرية الاستوائية، والتخييم الجماعي في الطبيعة مع تغطية كاملة للإقامة والطعام والمعدات."
        )
    if "UN VOLUNTEERS" in title.upper() or "UNV" in title.upper():
        return (
            "برنامج تبادل وتطوع شبابي دولي ممول بالكامل تابع لبرنامج متطوعي الأمم المتحدة (UNV) في جنوب شرق آسيا. "
            "يركز على التوعية المناخية الميدانية، تنظيف السواحل والعمل المجتمعي، ويشمل تذاكر الطيران من كوالالمبور والإقامة الفندقية وبدلاً شهرياً كاملاً."
        )
    if "DPOA" in title.upper() or "QATAR" in title.upper():
        return (
            "زمالة دولية ممولة بالكامل تابعة للأمم المتحدة تُعقد في الدوحة بقطر، تركز على قضايا التنمية، الإعلام الرقمي، والتحول التكنولوجي. "
            "تغطي تذاكر الطيران للدوحة والإقامة الفندقية وبدلاً يومياً."
        )
    if "FRIM" in title.upper() or "GREEN-AI" in title.upper():
        return (
            "هاكاثون ومخيم بيئي تفاعلي في معهد أبحاث الغابات الماليزي (FRIM) يجمع بين الذكاء الاصطناعي وحماية الغابات الاستوائية. "
            "يشمل التخييم في قلب المحمية الطبيعية وتطوير نماذج ذكية مع تغطية كاملة للإقامة والوجبات."
        )
    if "SCHOLARSHIPS FOR INTERNATIONAL" in title.upper():
        return (
            "قائمة فرص ومنح دراسية عالمية ممولة بالكامل للطلبة الدوليين تغطي كافة نفقات الدراسة والمعيشة وتذاكر السفر."
        )

    # Dynamic fallback generator based on fields
    scope = f"في {city}، {country}" if city and country else "دولية"
    return (
        f"فرصة {track.replace('_', ' ')} متميزة وممولة بالكامل 100% {scope} تنظمها {organizer}. "
        f"تستهدف الشباب والطلبة المتميزين وتشمل تغطية نفقات السفر والإقامة ومصروف المعيشة بدون أي رسوم تقديم."
    )


if __name__ == "__main__":
    pm = PortfolioManager()
    pdf_path = pm.render_cv_pdf()
    print(f"Generated Updated PDF CV: {pdf_path} (Size: {pdf_path.stat().st_size} bytes)")
    
    sample_opp = {
        "opportunity_code": "INT-AI-044",
        "title": "CALTECH Summer Research Program 2027 in USA (Fully Funded)",
        "organizer": "California Institute of Technology (Caltech)",
        "location_city": "Pasadena, California",
        "location_country": "USA",
        "track_category": "RESEARCH_AI",
        "raw_description": "Caltech Summer Research Program is a 10-week summer internship..."
    }
    explanation = get_opportunity_arabic_explanation(sample_opp)
    print("\nSample Arabic Explanation:\n", explanation)
    
    essay = pm.synthesize_tailored_motivation_letter(sample_opp)
    print("\nSample Tailored Motivation Essay:\n", essay[:400] + "...")
