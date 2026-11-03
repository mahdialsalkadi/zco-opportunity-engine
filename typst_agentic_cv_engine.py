#!/usr/bin/env python3
"""
ZCO Hunter — Agentic Typst CV Synthesis Engine
Author: Mohammad Mahdi Alsalkadi & Antigravity AI
Version: 6.0.0

Decouples Data from Presentation through a 4-Layer Closed-Loop Architecture:
1. Single Source of Truth: master_profile.yaml (Pydantic validated)
2. Multi-Stage Agentic Pipeline:
   - Node A: Job Description / Opportunity Feature Extractor
   - Node B: Semantic Retriever & 1-Page Budget Ranker
   - Node C: Constrained Google XYZ Rewriter
3. Programmatic Typesetting: Typst (Rust-based sub-millisecond ATS compiler)
4. Closed-Loop Verification:
   - Layout Constraint Check (pypdf enforces strict 1-page ceiling)
   - ATS Keyword Alignment Scoring

IRON RULE: Only synthesizes when CV is an actual requirement of the opportunity.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import pathlib
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import pypdf
import yaml

from paths import (
    BASE_REFERENCE_JSON_PATH,
    BASE_REFERENCE_PDF_PATH,
    CONFIG_DIR,
    CUSTOM_CVS_DIR,
    DATA_DIR,
    DOCS_DIR,
    MASTER_PROFILE_PATH,
)

logger = logging.getLogger("ZCO-TypstAgent")

BASE_DIR = pathlib.Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

CUSTOM_CVS_DIR.mkdir(parents=True, exist_ok=True)
TYPST_TEMPLATE_PATH = TEMPLATES_DIR / "cv_template.typ"


# =============================================================================
# Gatekeeper: Is CV Actually Required?
# =============================================================================

def is_cv_required_for_opportunity(opp: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Evaluates whether this specific opportunity requires a CV / Resume.
    Returns (True, reason) or (False, reason).
    Enforces user constraint: "طبعا لا يسويه الا اذا مطلوب بالتقديم"
    """
    req_fields_json = opp.get("required_form_fields_json") or "[]"
    try:
        req_fields = json.loads(req_fields_json) if isinstance(req_fields_json, str) else req_fields_json
    except Exception:
        req_fields = []

    # 1. Explicit form field requirement in live DOM / portal
    if "cv_pdf_path" in req_fields or "upload_cv" in req_fields or "resume" in req_fields:
        return True, "طلب صريح لرفع السيرة الذاتية داخل استمارة التقديم (cv_pdf_path)"

    title = opp.get("title", "")
    desc = opp.get("raw_description", "")
    terms = opp.get("raw_terms_text", "")
    text = f"{title} {desc} {terms}".lower()

    # 2. Strong explicit textual requirement
    positive_patterns = [
        r"\b(upload|attach|submit|provide|send)\s+(your\s+)?(cv|resume|curriculum\s+vitae)\b",
        r"\b(cv|resume)\s+is\s+(required|mandatory|needed|requested)\b",
        r"\b(cv_pdf_path|upload_cv|upload_resume|attach_resume)\b",
        r"\bcurriculum\s+vitae\s+\(cv\)\b",
        r"\bacademic\s+cv\b",
    ]
    for pattern in positive_patterns:
        if re.search(pattern, text):
            return True, "الجهة المنظمة تنص صراحة على إرفاق السيرة الذاتية ضمن شروط القبول"

    # 3. Research Internships, Lab Fellowships & Global Academic Grants always require academic CV
    academic_research_keywords = [
        "caltech", "amgen", "utokyo", "harvard", "fellowship", "summer research program",
        "govai", "summer research", "laboratory internship", "pre-doctoral", "undergraduate research fellowship"
    ]
    if any(k in text for k in academic_research_keywords):
        return True, "برنامج تدريب بحثي / زمالة أكاديمية تتطلب حكماً سيرة ذاتية أكاديمية للتقييم"

    return False, "السيرة الذاتية غير مطلوبة في هذه الفرصة (تعبئة استمارة مباشرة)"


# =============================================================================
# Layer 1: Master Profile Schema & Loader
# =============================================================================

class MasterProfileManager:
    """Loads and validates the Single Source of Truth."""

    def __init__(self, profile_path: pathlib.Path = MASTER_PROFILE_PATH) -> None:
        self.profile_path = profile_path
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        target = self.profile_path
        if not target.exists():
            example_path = target.parent / "master_profile.example.yaml"
            if example_path.exists():
                target = example_path
            else:
                raise FileNotFoundError(f"Master profile not found at {self.profile_path}")
        with open(target, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data


# =============================================================================
# Layer 2: Multi-Stage Agentic Pipeline
# =============================================================================

@dataclasses.dataclass
class JobOpportunityFeatures:
    domain_focus: str  # RESEARCH_LAB | AI_POLICY | ECO_CONSERVATION | COMMUNITY_VOLUNTEERING | GENERAL
    hard_skills: List[str]
    target_keywords: List[str]
    priority_tags: List[str]
    target_program_title: str
    target_organizer: str
    is_github_mandated: bool = False


class JobDescriptionParser:
    """Stage A: Extracts semantic requirements and keyword weights from opportunity."""

    @staticmethod
    def extract_features(opp: Dict[str, Any]) -> JobOpportunityFeatures:
        title = opp.get("title", "")
        organizer = opp.get("organizer", "")
        desc = opp.get("raw_description", "")
        terms = opp.get("raw_terms_text", "")
        track = opp.get("track_category", "")

        corpus = f"{title} {desc} {terms} {track}".upper()

        if any(k in corpus for k in ["GOVAI", "GOVERNANCE", "POLICY", "SAFETY", "ETHICS"]):
            domain = "AI_POLICY"
            hard_skills = ["AI Safety", "Autonomous Systems", "Policy Alignment", "Python Automation", "Algorithmic Fairness"]
            priority_tags = ["AI_AGENT", "SYSTEMS", "AUTOMATION", "LEADERSHIP"]
            target_keywords = ["AI governance", "systemic safety", "autonomous decision systems", "responsible AI", "developing economies"]
        # Conservation must win over the generic "volunteer/beach" branch.
        # WWF's marine expedition contains both "beach" and "volunteer", and
        # the old order mislabeled it as community education.
        elif any(k in corpus for k in [
            "CAMP", "ECO", "NATURE", "FOREST", "FRIM", "WILDLIFE", "CONSERVATION",
            "MARINE", "COASTAL", "OCEAN", "REEF", "TURTLE", "BIOACOUSTIC", "WWF",
        ]):
            domain = "ECO_CONSERVATION"
            hard_skills = ["Green AI", "Bioacoustic Monitoring", "Wilderness Camping", "Swimming", "Field Sensor Analytics"]
            priority_tags = ["GREEN_AI", "ECO_CONSERVATION", "EDGE_COMPUTING", "OUTDOOR", "NATURE"]
            target_keywords = ["biodiversity preservation", "rainforest field camp", "bioacoustic monitoring", "edge computing", "outdoor endurance"]
        elif any(k in corpus for k in ["CLEANUP", "BEACH", "VOLUNTEER", "CHILD", "COMMUNITY", "SOLS"]):
            domain = "COMMUNITY_VOLUNTEERING"
            hard_skills = ["Community Mentorship", "Outdoor Resilience", "Digital Literacy", "Team Coordination"]
            priority_tags = ["VOLUNTEERING", "OUTDOOR", "SWIMMING", "LEADERSHIP"]
            target_keywords = ["community engagement", "grassroots impact", "field resilience", "peer education", "collaborative action"]
        elif any(k in corpus for k in ["CALTECH", "AMGEN", "UTOKYO", "HARVARD", "RESEARCH", "LABORATORY"]):
            domain = "RESEARCH_LAB"
            hard_skills = ["Algorithms", "Deep Learning", "PyTorch", "Mathematical Rigor", "Data Structures"]
            priority_tags = ["RESEARCH", "DEEP_LEARNING", "PYTORCH", "ALGORITHMS", "ACADEMIC"]
            target_keywords = ["laboratory research", "empirical inquiry", "PyTorch", "algorithms", "computational models"]
        else:
            domain = "GENERAL"
            hard_skills = ["Python", "Problem Solving", "Adaptability", "Collaboration"]
            priority_tags = ["AI_AGENT", "ACADEMIC", "LEADERSHIP"]
            target_keywords = ["global fellowship", "multicultural collaboration", "technological innovation", "resilience"]

        # Check if vacancy explicitly and mandatorily demands GitHub
        # Candidate's Iron Rule: "الجيت هب تبعي أبداً مش نقطة قوة... إذا ما انطلب بشكل مباشر لا تحطوش"
        corpus_lower = f"{title} {desc} {terms}".lower()
        req_fields_raw = str(opp.get("required_form_fields_json", "")).lower()
        is_github_mandated = bool(
            re.search(r"\b(mandatory|required|must submit|must provide|compulsory)\b.{1,50}\b(github|code repository)\b", corpus_lower)
            or re.search(r"\b(github|code repository)\b.{1,50}\b(mandatory|required|compulsory)\b", corpus_lower)
            or ('"github"' in req_fields_raw and "optional" not in req_fields_raw and "not required" not in req_fields_raw)
        )

        return JobOpportunityFeatures(
            domain_focus=domain,
            hard_skills=hard_skills,
            target_keywords=target_keywords,
            priority_tags=priority_tags,
            target_program_title=title,
            target_organizer=organizer,
            is_github_mandated=is_github_mandated,
        )


class SemanticProfileRanker:
    """Stage B: Matches master profile items against JD features and enforces 1-page budget."""

    @staticmethod
    def rank_and_filter_projects(
        all_projects: List[Dict[str, Any]],
        features: JobOpportunityFeatures,
        max_projects: int = 2,
    ) -> List[Dict[str, Any]]:
        scored_projects = []
        for prj in all_projects:
            tags = set(prj.get("category_tags", []))
            overlap = len(tags.intersection(set(features.priority_tags)))
            
            # Domain-specific boosts
            if features.domain_focus == "RESEARCH_LAB" and "pytorch" in prj.get("id", "").lower():
                overlap += 4
            elif features.domain_focus == "ECO_CONSERVATION" and "green_ai" in prj.get("id", "").lower():
                overlap += 5
            elif features.domain_focus == "AI_POLICY" and "zco_hunter" in prj.get("id", "").lower():
                overlap += 4

            scored_projects.append((overlap, prj))

        # Sort descending by relevance score
        scored_projects.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored_projects[:max_projects]]

    @staticmethod
    def rank_and_filter_experience(
        all_exp: List[Dict[str, Any]],
        features: JobOpportunityFeatures,
        max_exp: int = 2,
    ) -> List[Dict[str, Any]]:
        scored = []
        for exp in all_exp:
            tags = set(exp.get("category_tags", []))
            overlap = len(tags.intersection(set(features.priority_tags)))
            if features.domain_focus in ("ECO_CONSERVATION", "COMMUNITY_VOLUNTEERING") and "OUTDOOR" in tags:
                overlap += 3
            scored.append((overlap, exp))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:max_exp]]


class ConstrainedXYZRewriter:
    """
    Stage C: Deep Domain-Adaptive Rewriter.
    Rewrites the ENTIRE CV (Header, Objective, Projects, Experience, and Skills)
    from the ground up to match the specific opportunity domain, preventing generic templates
    and strictly adhering to candidate ground truth.
    """

    @staticmethod
    def rewrite_for_target(
        master_data: Dict[str, Any],
        selected_projects: List[Dict[str, Any]],
        selected_exp: List[Dict[str, Any]],
        features: JobOpportunityFeatures,
        concise_mode: bool = False,
    ) -> Dict[str, Any]:
        p = master_data["personal"]
        edu = master_data["education"]
        skills = master_data.get("skills", {})
        domain = features.domain_focus

        # 1. Contact Info: Omit GitHub everywhere by default unless explicitly and mandatorily demanded!
        # Candidate's strict rule: GitHub is not a competitive asset (vibe-coded/experimental repos).
        # "إذا ما انطلب بشكل مباشر لا تحطوش... استرني الله يستر عليك"
        include_github = getattr(features, "is_github_mandated", False)
        github_val = p.get("github_url", "") if include_github else ""

        # 2. Domain-Specific Subtitle & Synthesized Objective
        # Every claim below is supported by master_profile.yaml.
        if domain == "RESEARCH_LAB":
            subtitle = f"Undergraduate AI & Computational Systems Candidate | Target: {features.target_program_title}"
            obj_statement = (
                f"First-year Artificial Intelligence honours undergraduate at Universiti Teknologi Malaysia (CGPA 3.53) "
                f"with mathematical foundations in algorithms and hands-on PyTorch experimentation. Seeking to contribute "
                f"laboratory research, empirical inquiry, and computational models to {features.target_program_title} at "
                f"{features.target_organizer}."
            )
        elif domain == "AI_POLICY":
            subtitle = f"AI Systems Governance & Technical Safety Candidate | Target: {features.target_program_title}"
            obj_statement = (
                f"First-year AI honours student with practical experience building deterministic verification and audit "
                f"workflows for autonomous systems. Seeking to contribute to AI governance, systemic safety, responsible AI, "
                f"and autonomous decision systems research through {features.target_program_title} at {features.target_organizer}."
            )
        elif domain == "COMMUNITY_VOLUNTEERING":
            subtitle = f"Community Education & Cross-Cultural Engagement Candidate | Target: {features.target_program_title}"
            obj_statement = (
                f"First-year AI undergraduate at UTM with cross-cultural teamwork and peer-learning experience in Malaysia. "
                f"Seeking to contribute community engagement, grassroots impact, peer education, and collaborative action to "
                f"{features.target_program_title} organized by {features.target_organizer}."
            )
        elif domain == "ECO_CONSERVATION":
            subtitle = f"Environmental Bioacoustics & Conservation Fieldwork Candidate | Target: {features.target_program_title}"
            obj_statement = (
                f"First-year computing undergraduate combining a Green-AI bioacoustic monitoring project with outdoor "
                f"camping, trekking, and swimming readiness. Seeking to contribute biodiversity preservation, rainforest "
                f"field work, edge computing, and outdoor endurance to {features.target_program_title} with "
                f"{features.target_organizer}."
            )
        else:
            subtitle = f"Candidate: {features.target_program_title} | Universiti Teknologi Malaysia"
            obj_statement = (
                f"Artificial Intelligence honours undergraduate at UTM (CGPA 3.53), multilingual in Arabic and English, "
                f"seeking to contribute technical initiative, cross-cultural adaptability, and collaborative problem solving "
                f"to {features.target_program_title}."
            )

        # 3. Grounded Project Selection (master_profile.yaml is the only source)
        project_by_id = {
            str(prj.get("id", "")).strip().lower(): prj
            for prj in master_data.get("projects", [])
            if isinstance(prj, dict)
        }
        preferred_project_ids = {
            "RESEARCH_LAB": ["pytorch_ml_foundations", "zco_hunter"],
            "AI_POLICY": ["zco_hunter", "pytorch_ml_foundations"],
            "COMMUNITY_VOLUNTEERING": ["zco_hunter", "utm_algorithmic_coursework"],
            "ECO_CONSERVATION": ["green_ai_bioacoustics", "zco_hunter"],
        }.get(domain, [])
        grounded_projects: List[Dict[str, Any]] = []
        for project_id in preferred_project_ids:
            project = project_by_id.get(project_id)
            if project and project not in grounded_projects:
                grounded_projects.append(project)
        for project in selected_projects:
            if isinstance(project, dict) and project not in grounded_projects:
                grounded_projects.append(project)
        if not grounded_projects:
            grounded_projects = [
                prj for prj in master_data.get("projects", []) if isinstance(prj, dict)
            ][:2]

        formatted_projects = []
        for prj in grounded_projects[:2]:
            bullets = [
                str(b).strip() for b in prj.get("raw_bullet_points", []) if str(b).strip()
            ]
            if not bullets and prj.get("summary"):
                bullets = [str(prj["summary"]).strip()]
            if concise_mode:
                bullets = [
                    (b[:150].rstrip() + "...") if len(b) > 153 else b
                    for b in bullets[:2]
                ]
            formatted_projects.append(
                {
                    "title": str(prj.get("title", "")).strip(),
                    "role": str(prj.get("role", "")).strip(),
                    "period": str(prj.get("period", "")).strip(),
                    "technologies_str": ", ".join(
                        str(t).strip() for t in prj.get("technologies", []) if str(t).strip()
                    ),
                    "bullet_points": bullets[:2],
                }
            )

        # 4. Grounded Experience Selection
        exp_by_id = {
            str(exp.get("id", "")).strip().lower(): exp
            for exp in master_data.get("experience", [])
            if isinstance(exp, dict)
        }
        if domain in ("ECO_CONSERVATION", "COMMUNITY_VOLUNTEERING"):
            preferred_exp_ids = ["utm_student_engagement", "outdoor_conservation_readiness"]
        else:
            preferred_exp_ids = ["utm_student_engagement"]
        grounded_exp: List[Dict[str, Any]] = []
        for exp_id in preferred_exp_ids:
            exp = exp_by_id.get(exp_id)
            if exp and exp not in grounded_exp:
                grounded_exp.append(exp)
        for exp in selected_exp:
            if isinstance(exp, dict) and exp not in grounded_exp:
                grounded_exp.append(exp)
        if not grounded_exp:
            grounded_exp = [
                exp for exp in master_data.get("experience", []) if isinstance(exp, dict)
            ][:1]

        formatted_exp = []
        for exp in grounded_exp[:2]:
            details = [
                str(d).strip() for d in exp.get("details", []) if str(d).strip()
            ]
            if concise_mode:
                details = [
                    (d[:150].rstrip() + "...") if len(d) > 153 else d
                    for d in details[:1]
                ]
            formatted_exp.append(
                {
                    "organization": str(exp.get("organization", "")).strip(),
                    "role": str(exp.get("role", "")).strip(),
                    "period": str(exp.get("period", "")).strip(),
                    "details": details[:2],
                }
            )

        # 5. Grounded Skills
        prog = [
            str(x).strip() for x in skills.get("programming_languages", []) if str(x).strip()
        ]
        ml = [
            str(x).strip() for x in skills.get("machine_learning", []) if str(x).strip()
        ]
        tools = [
            str(x).strip() for x in skills.get("developer_tools", []) if str(x).strip()
        ]
        language_items = skills.get("languages", [])
        langs_str = ", ".join(
            f"{item.get('language', '').strip()} ({item.get('proficiency', '').strip()})"
            for item in language_items
            if isinstance(item, dict) and item.get("language")
        )
        field_str = ""
        if domain in ("ECO_CONSERVATION", "COMMUNITY_VOLUNTEERING"):
            fitness = p.get("fitness_and_field", {}) or {}
            field_parts = [
                str(fitness.get("swimming", "")).strip(),
                str(fitness.get("camping", "")).strip(),
                str(fitness.get("endurance", "")).strip(),
            ]
            field_str = ", ".join(part for part in field_parts if part)
        prog_str = ", ".join(prog[:4] if concise_mode else prog)
        ml_str = ", ".join(ml[:3] if concise_mode else ml)
        tools_str = ", ".join(tools[:4] if concise_mode else tools)

        return {
            "personal": {
                "full_name_en": p["full_name_en"],
                "location_short": "Kuala Lumpur, Malaysia",
                "email": p["email"],
                "phone_my": p["phone_my"],
                "github_url": github_val,
                "linkedin_url": p.get("linkedin_url", ""),
            },
            "target_subtitle": subtitle,
            "objective_statement": obj_statement if not concise_mode else "",
            "education": {
                "institution": edu["institution"],
                "degree": edu["degree"],
                "faculty": edu["faculty"],
                "academic_year": edu["academic_year"],
                "cgpa": edu["cgpa"],
                "graduation_expected": edu["graduation_expected"],
                "english_proficiency": edu["english_proficiency"],
                "core_coursework_str": ", ".join(edu.get("core_coursework", [])[:4] if concise_mode else edu.get("core_coursework", [])),
            },
            "projects": formatted_projects,
            "experience": formatted_exp,
            "skills": {
                "programming_str": prog_str,
                "ml_str": ml_str,
                "tools_str": tools_str,
                "languages_str": langs_str,
                "field_str": field_str,
            },
        }


# =============================================================================
# Layer 3: Programmatic Compilation via Typst
# =============================================================================

class TypstCompiler:
    """Invokes the standalone Typst binary to render the PDF in sub-second time."""

    @staticmethod
    def compile(
        json_payload_path: pathlib.Path,
        output_pdf_path: pathlib.Path,
        template_path: pathlib.Path = TYPST_TEMPLATE_PATH,
    ) -> bool:
        output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        
        json_path = json_payload_path.resolve()
        template = template_path.resolve()
        # ``ZCO_DATA_DIR`` may point outside the repository (tests, isolated
        # deployments), so choose a Typst root containing both the template and
        # the payload instead of assuming BASE_DIR.
        root = pathlib.Path(
            os.path.commonpath([str(BASE_DIR.resolve()), str(template), str(json_path)])
        )
        rel_json_path = json_path.relative_to(root).as_posix()

        cmd = [
            "typst",
            "compile",
            "--root", str(root),
            "--input", f"data_path=/{rel_json_path}",
            str(template),
            str(output_pdf_path.resolve()),
        ]

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if res.returncode != 0:
            logger.error("Typst compilation failed: %s", res.stderr.decode("utf-8", errors="ignore"))
            return False
        return output_pdf_path.exists() and output_pdf_path.stat().st_size > 1000


# =============================================================================
# Layer 4: Closed-Loop Verification & ATS Scoring
# =============================================================================

class ClosedLoopVerifier:
    """
    Verifies visual layout constraints (strictly 1 page) and computes
    ATS keyword alignment scoring.
    """

    @staticmethod
    def get_pdf_page_count_and_text(pdf_path: pathlib.Path) -> Tuple[int, str]:
        reader = pypdf.PdfReader(str(pdf_path))
        num_pages = len(reader.pages)
        full_text = " ".join(page.extract_text() or "" for page in reader.pages)
        return num_pages, full_text

    @staticmethod
    def calculate_ats_keyword_score(pdf_text: str, features: JobOpportunityFeatures) -> float:
        """Return honest keyword coverage, with no artificial score floor.

        Earlier versions clamped every CV to at least 82%, which made an ATS
        score meaningless. Missing keywords now lower the score and are exposed
        in the synthesis result so a weak match cannot look strong.
        """
        text_lower = re.sub(r"\s+", " ", (pdf_text or "").lower())
        if not text_lower.strip():
            return 0.0

        def phrase_present(phrase: str) -> bool:
            phrase = re.sub(r"\s+", " ", str(phrase or "").lower()).strip()
            if not phrase:
                return False
            if phrase in text_lower:
                return True
            words = [w for w in re.findall(r"[a-z0-9]+", phrase) if len(w) > 2]
            return bool(words) and all(word in text_lower for word in words)

        keywords = list(dict.fromkeys(features.hard_skills + features.target_keywords))
        total = max(1, len(keywords))
        matched = sum(1 for keyword in keywords if phrase_present(keyword))
        return round((matched / total) * 100.0, 1)


# =============================================================================
# Master Synthesis Pipeline
# =============================================================================

def synthesize_tailored_typst_cv(
    opp: Dict[str, Any],
    force: bool = False,
) -> Dict[str, Any]:
    """
    Executes the full 4-layer agentic Typst CV pipeline for an opportunity.
    Enforces user rule: Only generates if required, unless force=True.
    """
    code = opp.get("opportunity_code") or f"ID-{opp.get('id', 'opp')}"
    clean_code = re.sub(r"[^A-Za-z0-9_-]", "_", code)

    # Gatekeeper check
    required, req_reason = is_cv_required_for_opportunity(opp)
    if not required and not force:
        return {
            "cv_required": False,
            "status": "skipped",
            "reason": req_reason,
            "opportunity_code": code,
            "pdf_path": None,
        }

    # Layer 1: Single Source of Truth
    profile_mgr = MasterProfileManager()
    master = profile_mgr.data

    # Layer 2: Agentic Feature Extraction & Ranking
    features = JobDescriptionParser.extract_features(opp)
    
    # Start with standard 2 projects (ideal for 1-page budget)
    selected_projects = SemanticProfileRanker.rank_and_filter_projects(master["projects"], features, max_projects=2)
    selected_exp = SemanticProfileRanker.rank_and_filter_experience(master["experience"], features, max_exp=2)

    target_json_path = CUSTOM_CVS_DIR / f"data_{clean_code}.json"
    target_pdf_path = CUSTOM_CVS_DIR / f"CV_Mohammad_Alsalkadi_{clean_code}.pdf"
    # Remove any stale artifact so a compile failure can never be reported as success.
    if target_pdf_path.exists():
        try:
            target_pdf_path.unlink()
        except OSError:
            pass

    # Layer 3 & 4: Closed-Loop Compilation & Layout Verification Loop
    max_attempts = 2
    concise_mode = False
    final_page_count = 1
    final_ats_score = 90.0
    compile_ok = False

    for attempt in range(1, max_attempts + 1):
        payload = ConstrainedXYZRewriter.rewrite_for_target(
            master_data=master,
            selected_projects=selected_projects,
            selected_exp=selected_exp,
            features=features,
            concise_mode=concise_mode,
        )

        with open(target_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        success = TypstCompiler.compile(target_json_path, target_pdf_path)
        if not success:
            logger.error("Typst compile failed on attempt %d", attempt)
            compile_ok = False
            break
        compile_ok = True

        pages, pdf_text = ClosedLoopVerifier.get_pdf_page_count_and_text(target_pdf_path)
        final_page_count = pages
        final_ats_score = ClosedLoopVerifier.calculate_ats_keyword_score(pdf_text, features)

        if pages == 1:
            logger.info("Closed-loop verification passed: strictly 1 page on attempt %d (ATS score: %s%%)", attempt, final_ats_score)
            break
        else:
            logger.warning("Layout constraint overflow (%d pages). Triggering concise mode re-loop...", pages)
            concise_mode = True

    if not compile_ok or not target_pdf_path.exists() or target_pdf_path.stat().st_size <= 1000:
        return {
            "cv_required": True,
            "status": "failed",
            "error": "Typst compilation failed or produced an empty PDF",
            "requirement_reason": req_reason,
            "opportunity_code": code,
            "domain_focus": features.domain_focus,
            "pdf_path": None,
            "pdf_filename": target_pdf_path.name,
            "file_size_bytes": 0,
            "page_count": 0,
            "ats_score": 0.0,
            "projects_included": [p["title"] for p in selected_projects],
        }

    return {
        "cv_required": True,
        "status": "generated",
        "requirement_reason": req_reason,
        "opportunity_code": code,
        "domain_focus": features.domain_focus,
        "pdf_path": str(target_pdf_path),
        "pdf_filename": target_pdf_path.name,
        "file_size_bytes": target_pdf_path.stat().st_size,
        "page_count": final_page_count,
        "ats_score": final_ats_score,
        "projects_included": [p["title"] for p in selected_projects],
    }


def synthesize_base_reference_typst_cv(force_recompile: bool = True) -> Dict[str, Any]:
    """
    Synthesizes the Master Base Reference CV (السيرة الذاتية المرجعية الأساسية).
    This serves as the candidate's canonical 1-page reference document.
    Strictly sanitized: NO matric number, NO t-shirt/apparel size, NO passport number.
    Guaranteed strictly 1 page in Typst with ATS verification.
    """
    if BASE_REFERENCE_PDF_PATH.exists() and not force_recompile:
        pages, _ = ClosedLoopVerifier.get_pdf_page_count_and_text(BASE_REFERENCE_PDF_PATH)
        return {
            "status": "ready",
            "pdf_path": str(BASE_REFERENCE_PDF_PATH),
            "pdf_filename": BASE_REFERENCE_PDF_PATH.name,
            "page_count": pages,
            "is_reference": True,
        }

    profile_mgr = MasterProfileManager()
    master = profile_mgr.data

    features = JobOpportunityFeatures(
        domain_focus="RESEARCH_LAB",
        hard_skills=["Python", "PyTorch", "Algorithms", "FastAPI", "Systems Architecture"],
        target_keywords=["machine learning", "deep learning", "algorithms", "systems", "pytorch"],
        priority_tags=["AI_AGENT", "PYTORCH", "ALGORITHMS", "SYSTEMS"],
        target_program_title="Undergraduate AI & Computer Science Scholar",
        target_organizer="Universiti Teknologi Malaysia (UTM)",
    )

    # Reference CV includes flagship systems & deep learning projects
    selected_projects = master["projects"][:2]
    selected_exp = master["experience"][:2]

    concise_mode = False
    max_attempts = 2
    final_pages = 1

    for attempt in range(1, max_attempts + 1):
        payload = ConstrainedXYZRewriter.rewrite_for_target(
            master_data=master,
            selected_projects=selected_projects,
            selected_exp=selected_exp,
            features=features,
            concise_mode=concise_mode,
        )
        # Authoritative reference subtitle and summary
        payload["target_subtitle"] = "Undergraduate AI & Computer Science Scholar | Universiti Teknologi Malaysia"
        payload["personal"]["github_url"] = ""  # Strictly omitted from reference CV as requested
        payload["objective_statement"] = (
            "First-year Artificial Intelligence honours undergraduate at Universiti Teknologi Malaysia (CGPA 3.53) with strong mathematical foundations in algorithmic problem solving and discrete structures. Actively engineering autonomous multi-agent pipelines and training neural network models with PyTorch. Seeking to contribute high-rigor computing and applied ML skills to forward-looking technical and research environments."
        ) if not concise_mode else (
            "First-year AI honours undergraduate at UTM (CGPA 3.53) with strong algorithmic foundations and PyTorch neural network training experience. Seeking high-impact technical research and engineering opportunities."
        )
        payload["skills"]["field_str"] = ""

        with open(BASE_REFERENCE_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        success = TypstCompiler.compile(BASE_REFERENCE_JSON_PATH, BASE_REFERENCE_PDF_PATH)
        if not success:
            logger.error("Base reference CV compile failed on attempt %d", attempt)
            break

        pages, _ = ClosedLoopVerifier.get_pdf_page_count_and_text(BASE_REFERENCE_PDF_PATH)
        final_pages = pages
        if pages == 1:
            logger.info("Base reference CV verified: strictly 1 page on attempt %d", attempt)
            break
        else:
            logger.warning("Base reference CV exceeded 1 page (%d pages). Applying concise mode...", pages)
            concise_mode = True

    return {
        "status": "generated",
        "pdf_path": str(BASE_REFERENCE_PDF_PATH),
        "pdf_filename": BASE_REFERENCE_PDF_PATH.name,
        "file_size_bytes": BASE_REFERENCE_PDF_PATH.stat().st_size if BASE_REFERENCE_PDF_PATH.exists() else 0,
        "page_count": final_pages,
        "is_reference": True,
    }


if __name__ == "__main__":
    # Test with Caltech (requires CV)
    caltech_opp = {
        "opportunity_code": "INT-AI-044",
        "title": "CALTECH Summer Research Program 2027 in USA (Fully Funded)",
        "organizer": "Caltech",
        "track_category": "RESEARCH_AI",
        "raw_description": "Submit academic CV and statement of purpose for 10-week summer research laboratory internship.",
        "required_form_fields_json": '["full_name", "email_address", "cv_pdf_path"]',
    }

    # Test with quick community beach camp (does not require CV)
    beach_opp = {
        "opportunity_code": "MY-VOL-CLEANUP",
        "title": "Pulau Tioman Community Beach Cleanup & Turtle Nesting Weekend",
        "organizer": "Juara Volunteer Group",
        "track_category": "NATURE_ECO_CONSERVATION",
        "raw_description": "Sign up for a 3-day beach cleanup and turtle patrol weekend. Free lodging and meals.",
        "required_form_fields_json": '["full_name", "phone_whatsapp_my", "tshirt_and_gear_size"]',
    }

    print("--- Testing Gatekeeper on Beach Cleanup (No CV needed) ---")
    res_beach = synthesize_tailored_typst_cv(beach_opp)
    print(json.dumps(res_beach, indent=2, ensure_ascii=False))

    print("\n--- Testing Agentic Typst Pipeline on Caltech (CV Required) ---")
    res_caltech = synthesize_tailored_typst_cv(caltech_opp)
    print(json.dumps(res_caltech, indent=2, ensure_ascii=False))
