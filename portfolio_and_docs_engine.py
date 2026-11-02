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
import subprocess
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ZCO-PortfolioDocs")

BASE_DIR = pathlib.Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = DATA_DIR / "documents"
CONFIG_DIR = BASE_DIR / "config"
PORTFOLIO_FILE = DATA_DIR / "comprehensive_portfolio.json"
CV_PDF_FILE = DOCS_DIR / "cv_mohammad_mahdi.pdf"
CV_MD_FILE = DOCS_DIR / "cv_mohammad_mahdi.md"


AUTHENTIC_PORTFOLIO: Dict[str, Any] = {
    "personal": {
        "full_name_en": "Mohammad Mahdi Alsalkadi",
        "full_name_ar": "محمد مهدي السلقدي",
        "email": "***REMOVED-EMAIL***",
        "personal_email": "***REMOVED-EMAIL***",
        "phone_my": "***REMOVED-PHONE***",  # Can be updated by user via telegram anytime
        "phone_kw": "***REMOVED-PHONE***",
        "date_of_birth": "2006-10-25",
        "age": 20,
        "nationality": "Syrian",
        "nationality_ar": "سوري",
        "passport_number": "***REMOVED-PASSPORT***",
        "residency_kuwait": "Valid Kuwait Residency (Iqama)",
        "malaysia_pass": "Valid International Student Pass (UTM)",
        "address_my": "***REMOVED-ADDRESS***",
        "address_kw": "State of Kuwait (Valid Residency)",
        "departure_airport": "KUL (Kuala Lumpur International Airport)",
        "linkedin_url": "https://linkedin.com/in/mahdialsalkadi",
        "github_url": "https://github.com/mahdialsalkadi",
        "portfolio_url": "https://github.com/mahdialsalkadi",
        "dietary_preference": "Halal (حلال)",
        "tshirt_size": "M (Medium)",
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
        "matric_number": "***REMOVED-MATRIC***",
        "cgpa": "3.53 / 4.00",
        "graduation_expected": "2028",
        "english_proficiency": "IELTS Academic (Band 5.5)",
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


class PortfolioManager:
    """Manages profile persistence, CV generation, and Motivation Letter drafting."""

    def __init__(self, portfolio_path: Optional[pathlib.Path] = None) -> None:
        self.portfolio_path = portfolio_path or PORTFOLIO_FILE
        self.data: Dict[str, Any] = {}
        self.load_or_initialize()

    def load_or_initialize(self) -> Dict[str, Any]:
        """Loads portfolio from JSON or initializes with authentic template."""
        if self.portfolio_path.exists():
            try:
                with open(self.portfolio_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                # Ensure updated fields are merged
                self._ensure_updated_fields()
                return self.data
            except Exception as e:
                logger.error("Failed to load portfolio: %s", e)

        self.data = json.loads(json.dumps(AUTHENTIC_PORTFOLIO))
        self.save()
        return self.data

    def _ensure_updated_fields(self) -> None:
        """Merges new keys from AUTHENTIC_PORTFOLIO into existing data."""
        p = self.data.setdefault("personal", {})
        edu = self.data.setdefault("education", {})
        
        # Always prioritize verified user inputs
        p["full_name_en"] = "Mohammad Mahdi Alsalkadi"
        p["full_name_ar"] = "محمد مهدي السلقدي"
        p["nationality"] = "Syrian"
        p["date_of_birth"] = "2006-10-25"
        p["address_my"] = "***REMOVED-ADDRESS***"
        p["email"] = "***REMOVED-EMAIL***"
        p["github_url"] = "https://github.com/mahdialsalkadi"
        p["tshirt_size"] = "M (Medium)"
        p["swimming_fitness"] = "Capable swimmer, enthusiastic outdoor camper & trekker"

        edu["current_institution"] = "Universiti Teknologi Malaysia (UTM)"
        edu["degree"] = "Bachelor of Computer Science (Artificial Intelligence) with Honours"
        edu["matric_number"] = "***REMOVED-MATRIC***"
        edu["cgpa"] = "3.53 / 4.00"
        edu["english_proficiency"] = "IELTS Academic (Band 5.5)"

        self.data["skills"] = AUTHENTIC_PORTFOLIO["skills"]
        self.data["projects"] = AUTHENTIC_PORTFOLIO["projects"]
        self.save()

    def save(self) -> None:
        """Persists portfolio data to JSON and syncs with candidate_profile.json."""
        self.portfolio_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.portfolio_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

        # Sync to candidate_profile.json
        candidate_json_path = CONFIG_DIR / "candidate_profile.json"
        if candidate_json_path.exists():
            try:
                with open(candidate_json_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)

                cfg.setdefault("candidate", {})
                cfg["candidate"]["full_name"] = self.data["personal"]["full_name_en"]
                cfg["candidate"]["email"] = self.data["personal"]["email"]
                cfg["candidate"]["matric_number"] = self.data["education"]["matric_number"]
                cfg["candidate"]["cgpa"] = self.data["education"]["cgpa"]
                cfg["candidate"]["github"] = self.data["personal"]["github_url"]
                cfg["candidate"]["address"] = self.data["personal"]["address_my"]

                with open(candidate_json_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning("Could not sync candidate_profile.json: %s", e)

    def sync_to_sqlite_vault(self, db_conn) -> None:
        """Syncs all key fields from portfolio into SQLite candidate_vault table."""
        p = self.data.get("personal", {})
        edu = self.data.get("education", {})

        mappings = [
            ("full_name", p.get("full_name_en", "Mohammad Mahdi Alsalkadi"), "identity", "الاسم الكامل بالإنجليزية"),
            ("full_name_ar", p.get("full_name_ar", "محمد مهدي السلقدي"), "identity", "الاسم الكامل بالعربية"),
            ("age", str(p.get("age", 20)), "identity", "العمر"),
            ("date_of_birth", p.get("date_of_birth", "2006-10-25"), "identity", "تاريخ الميلاد"),
            ("nationality", f"{p.get('nationality', 'Syrian')} (SY)", "jurisdiction", "الجنسية"),
            ("primary_residency_country", "Malaysia (MY)", "jurisdiction", "دولة الإقامة الأساسية"),
            ("residential_address_my", p.get("address_my", "***REMOVED-ADDRESS***"), "contact", "عنوان السكن في كوالالمبور"),
            ("malaysia_visa_type", p.get("malaysia_pass", "Valid International Student Pass (UTM)"), "jurisdiction", "نوع التأشيرة في ماليزيا"),
            ("secondary_residency_country", "Kuwait (Valid Residency / Iqama)", "jurisdiction", "دولة الإقامة الثانوية (الكويت)"),
            ("university_name", edu.get("current_institution", "Universiti Teknologi Malaysia (UTM)"), "academic", "اسم الجامعة"),
            ("degree_and_major", edu.get("degree", "Bachelor of Computer Science (Artificial Intelligence) with Honours"), "academic", "الدرجة والتخصص"),
            ("academic_year", edu.get("academic_year", "Year 1 (Undergraduate)"), "academic", "المرحلة الدراسية"),
            ("utm_matric_number", edu.get("matric_number", "***REMOVED-MATRIC***"), "academic", "الرقم الجامعي (UTM Matric)"),
            ("current_cgpa", edu.get("cgpa", "3.53 / 4.00"), "academic", "المعدل التراكمي (CGPA)"),
            ("english_proficiency", edu.get("english_proficiency", "IELTS Academic (Band 5.5)"), "academic", "مستوى اللغة الإنجليزية"),
            ("departure_airport", p.get("departure_airport", "KUL"), "logistics", "مطار المغادرة المفضل"),
            ("email_address", p.get("email", "***REMOVED-EMAIL***"), "contact", "البريد الإلكتروني الرسمي"),
            ("phone_whatsapp_my", p.get("phone_my", "***REMOVED-PHONE***"), "contact", "رقم الهاتف / واتساب"),
            ("github_or_portfolio_url", p.get("github_url", "https://github.com/mahdialsalkadi"), "academic", "رابط GitHub أو المعرض البرمجي"),
            ("dietary_preference", p.get("dietary_preference", "Halal"), "logistics", "التفضيلات الغذائية"),
            ("tshirt_and_gear_size", p.get("tshirt_size", "M"), "logistics", "مقاس القميص والمعدات الميدانية"),
            ("swimming_and_outdoor_fitness", p.get("swimming_fitness", "Capable swimmer, enthusiastic outdoor camper & trekker"), "outdoor", "اللياقة الميدانية والسباحة والتخييم"),
            ("cv_pdf_path", str(CV_PDF_FILE), "documents", "مسار ملف السيرة الذاتية PDF"),
        ]

        cursor = db_conn.cursor()
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        for key, val, cat, label_ar in mappings:
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
        """
        Synthesizes an authentic, compelling 4-paragraph Statement of Purpose
        specifically customized for the opportunity's domain and host institution.
        """
        p = self.data.get("personal", {})
        edu = self.data.get("education", {})
        skills = self.data.get("skills", {})

        title = opp.get("title", "International Academic Opportunity")
        organizer = opp.get("organizer", "the Selection Committee")
        city = opp.get("location_city", "Host City")
        country = opp.get("location_country", "Host Country")
        track = opp.get("track_category", "ACADEMIC")

        full_name = p.get("full_name_en", "Mohammad Mahdi Alsalkadi")
        degree = edu.get("degree", "Bachelor of Computer Science (Artificial Intelligence) with Honours")
        university = edu.get("current_institution", "Universiti Teknologi Malaysia (UTM)")
        year = edu.get("academic_year", "Year 1")
        cgpa = edu.get("cgpa", "3.53 / 4.00")

        # Candidate strict directive: Never mention Kuwait / GCC residency unless explicitly demanded by the opportunity!
        corpus = f"{title} {opp.get('raw_description', '')} {opp.get('raw_terms_text', '')}".lower()
        is_gcc_mandated = any(k in corpus for k in ["kuwait", "gcc", "gulf countries", "الكويت", "الخليج", "مجلس التعاون"])

        bg_text = (
            "being a Syrian national with valid family residency in Kuwait and currently undertaking university studies in Malaysia"
            if is_gcc_mandated
            else "being a Syrian national currently undertaking university studies in Artificial Intelligence with honours in Malaysia"
        )

        # Paragraph 1: Sincere Introduction & Academic Motivation
        p1 = (
            f"Dear Selection Committee of {organizer},\n\n"
            f"I am writing to express my enthusiastic application for {title} in {city}, {country}. "
            f"As a {year} undergraduate pursuing a {degree} at {university} (currently maintaining a CGPA of {cgpa}), "
            f"my academic journey is grounded in resilience, high ambition, and technical focus—{bg_text}. "
            f"This background has instilled in me a disciplined work ethic and a genuine drive to master modern "
            f"computational tools to solve real-world challenges. Participating in {title} represents "
            f"a pivotal milestone in my academic development."
        )

        # Paragraph 2: Technical Grounding & Learning Trajectory
        p2 = (
            f"Throughout my foundational coursework at UTM, I have built a solid grasp of programming in Python and C++, data structures, and algorithmic logic. "
            f"Currently, I am actively expanding my practical skills into deep learning frameworks, specifically experimenting with PyTorch. "
            f"Driven by a passion to apply technology meaningfully, I have also developed 'ZCO-Hunter'—a Python-based agentic pipeline that automates "
            f"opportunity monitoring and eligibility audits for international students. I recognize that I am at the beginning of my research journey, "
            f"which makes me all the more eager to absorb mentorship, tackle hands-on laboratory or collaborative challenges, and learn from leading domain experts."
        )

        # Paragraph 3: Specific Alignment with the Host Program
        if "NATURE" in track or "CONSERVATION" in track:
            p3 = (
                f"What specifically excites me about {title} is its tangible commitment to environmental conservation and field engagement. "
                f"Beyond computing, I have an authentic love for the outdoors, wilderness camping, trekking, and swimming. I am eager to combine my field readiness "
                f"with my growing technical knowledge in AI, exploring how automated models can support biodiversity protection and tropical ecosystem monitoring. "
                f"I am fully prepared for the physical demands of field camp expeditions and look forward to contributing actively to group initiatives."
            )
        elif "FELLOWSHIP" in track or "GOV" in track or "POLICY" in track:
            p3 = (
                f"The distinctive focus of {title} on AI governance, safety, and societal impact strongly aligns with my intellectual curiosities. "
                f"As AI systems evolve rapidly, understanding the ethical boundaries and policy frameworks governing their deployment is paramount. "
                f"My background across the Arab world and Southeast Asia allows me to contribute a fresh, inclusive perspective to your cohort's discussions "
                f"on how artificial intelligence can be responsibly stewarded across diverse developing economies."
            )
        else:
            p3 = (
                f"The exceptional academic environment of {organizer} provides the ideal crucible to elevate my research methodology and practical acumen. "
                f"I am enthusiastic about immersing myself in high-standard academic inquiry, collaborating alongside motivated international peers, and "
                f"gaining direct exposure to advanced problem-solving techniques. The mentorship offered through {title} will provide foundational preparation "
                f"for my future academic trajectory and prospective graduate studies."
            )

        # Paragraph 4: Commitment & Closing
        p4 = (
            f"I am fully committed to dedicating my complete energy, curiosity, and collaborative spirit to every aspect of {title}. "
            f"Thank you very much for your time, consideration, and dedication to fostering aspiring students.\n\n"
            f"Sincerely,\n"
            f"{full_name}\n"
            f"{degree}, Universiti Teknologi Malaysia\n"
            f"Email: {p.get('email')} | Phone: {p.get('phone_my')}"
        )

        return f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}"


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
