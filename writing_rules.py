#!/usr/bin/env python3
"""Writing rules for grounded motivation statements.

The rules exist because a language model will happily invent a prize, a
metric, or a childhood story to make an essay sound better. Essays produced
here must use only facts present in ``master_profile.yaml`` and the
opportunity record, stay inside a useful length, and avoid the stock phrases
that make an application read like a template.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

WORD_RANGE: Tuple[int, int] = (180, 280)

BANNED_PHRASES: Tuple[str, ...] = (
    "i am writing to express my enthusiastic application",
    "pivotal milestone",
    "delve",
    "leverage",
    "testament",
    "tapestry",
    "crucible",
    "passionate",
    "dream come true",
    "ever since i was a child",
    "not only",
    "but also",
    "in today's rapidly evolving",
    "it is worth noting",
    "navigate the complexities",
    "unlock my potential",
    "complete energy",
    "unique perspective",
    "i am thrilled",
    "i am eager to embark",
)

SENSITIVE_TERMS: Tuple[str, ...] = (
    "matric",
    "passport",
    "tshirt",
    "t-shirt",
    "apparel",
    "student id",
)

_KUWAIT_MARKERS: Tuple[str, ...] = (
    "kuwait",
    "gcc",
    "gulf countries",
    "الكويت",
    "الخليج",
    "مجلس التعاون",
)


def count_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _first_sentence(text: str, limit: int = 260) -> str:
    cleaned = _clean(text)
    if not cleaned:
        return ""
    match = re.match(r"(.+?[.!?])(?:\s|$)", cleaned)
    sentence = match.group(1) if match else cleaned
    if len(sentence) > limit:
        sentence = sentence[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "."
    return sentence


def _corpus(profile: Dict[str, Any]) -> str:
    parts: List[str] = []
    for section in ("personal", "education", "skills", "projects", "experience", "awards"):
        value = profile.get(section)
        if value is not None:
            parts.append(repr(value))
    return " ".join(parts).lower()


def _project_text(project: Dict[str, Any]) -> str:
    return " ".join(
        [
            _clean(project.get("title")),
            _clean(project.get("role")),
            _clean(project.get("summary")),
            " ".join(str(x) for x in project.get("category_tags", [])),
            " ".join(str(x) for x in project.get("technologies", [])),
            " ".join(str(x) for x in project.get("raw_bullet_points", [])),
        ]
    ).lower()


def _rank_projects(profile: Dict[str, Any], keywords: List[str]) -> List[Dict[str, Any]]:
    projects = [p for p in profile.get("projects", []) if isinstance(p, dict)]
    def score(project: Dict[str, Any]) -> int:
        text = _project_text(project)
        return sum(1 for keyword in keywords if keyword.lower() in text)
    return sorted(projects, key=score, reverse=True)


def _experience_for(profile: Dict[str, Any], domain: str) -> Optional[Dict[str, Any]]:
    experiences = [e for e in profile.get("experience", []) if isinstance(e, dict)]
    if not experiences:
        return None
    if domain == "ECO_CONSERVATION":
        for experience in experiences:
            if "outdoor_conservation_readiness" == str(experience.get("id", "")).lower():
                return experience
    for experience in experiences:
        if "utm_student_engagement" == str(experience.get("id", "")).lower():
            return experience
    return experiences[0]


def _domain(title: str, description: str, track: str) -> str:
    corpus = f"{title} {description} {track}".lower()
    if any(word in corpus for word in ("marine", "coastal", "beach", "turtle", "conservation", "wildlife", "rainforest", "eco")):
        return "ECO_CONSERVATION"
    if any(word in corpus for word in ("governance", "policy", "safety", "ethics")):
        return "AI_POLICY"
    if any(word in corpus for word in ("research", "laboratory", "lab", "fellowship")):
        return "RESEARCH_LAB"
    if any(word in corpus for word in ("community", "volunteer", "education", "youth", "children")):
        return "COMMUNITY_VOLUNTEERING"
    return "GENERAL"


def _as_sentence(text: str) -> str:
    """Turn a profile bullet such as 'Trained...' into 'I trained...'."""
    cleaned = _clean(text)
    if not cleaned:
        return cleaned
    first_word = cleaned.split()[0].lower()
    action_words = {
        "trained", "architected", "built", "developed", "implemented", "engineered",
        "designed", "created", "conducted", "optimized", "analysed", "analyzed",
        "automated", "documented", "maintained", "organized", "organised",
    }
    if first_word in action_words:
        return "I " + cleaned[0].lower() + cleaned[1:]
    return cleaned


def build_motivation_letter(opp: Dict[str, Any], profile: Dict[str, Any]) -> str:
    """Build a specific, factual 180-280 word motivation statement.

    The letter uses one project with a real metric, one real experience, and a
    clear statement of what the candidate wants to learn. It deliberately does
    not claim marine, policy, or teaching experience that is absent from the
    profile.
    """
    personal = profile.get("personal", {}) or {}
    education = profile.get("education", {}) or {}
    title = _clean(opp.get("title")) or "this program"
    organizer = _clean(opp.get("organizer")) or "the selection committee"
    city = _clean(opp.get("location_city"))
    description = _clean(opp.get("raw_description"))
    track = _clean(opp.get("track_category"))
    domain = _domain(title, description, track)

    keywords_by_domain = {
        "ECO_CONSERVATION": ["green_ai", "bioacoustic", "conservation", "sensor", "edge", "environment"],
        "AI_POLICY": ["audit", "verification", "governance", "safety", "autonomous", "policy"],
        "RESEARCH_LAB": ["pytorch", "deep learning", "research", "algorithm", "tensor"],
        "COMMUNITY_VOLUNTEERING": ["community", "education", "peer", "collaboration", "leadership"],
        "GENERAL": ["python", "automation", "systems"],
    }
    ranked = _rank_projects(profile, keywords_by_domain.get(domain, []))
    primary = ranked[0] if ranked else {}
    secondary = next((p for p in ranked[1:] if p.get("title") != primary.get("title")), None)
    experience = _experience_for(profile, domain)

    project_title = _clean(primary.get("title"))
    project_bullets = [
        _clean(b) for b in primary.get("raw_bullet_points", []) if _clean(b)
    ]
    project_bullet = _as_sentence(
        project_bullets[0] if project_bullets else _clean(primary.get("summary"))
    )

    if domain == "ECO_CONSERVATION":
        mission_sentence = (
            "Its focus on coastal conservation, beach cleanups, and field monitoring"
            + (f" in {city}" if city else "")
            + " is the reason I am applying."
        )
        field_paragraph = (
            "My field experience is modest but real. I camp and trek in Malaysian heat and rain, "
            "I swim, and I am comfortable with long days outdoors. I have not worked on a marine "
            "site before, and I would rather say that plainly. What I bring is careful record-keeping "
            "and a willingness to learn your marine protocols."
        )
    elif domain == "AI_POLICY":
        mission_sentence = "Its work on AI governance and technical safety is the reason I am applying."
        field_paragraph = (
            "Building verification and audit workflows has taught me that a confident model output "
            "is not the same as a correct one. I want to learn how policy teams test that distinction "
            "in practice, especially where autonomous systems affect public institutions. My coursework "
            "gives me a technical base, but I still need supervised experience in policy analysis."
        )
    elif domain == "RESEARCH_LAB":
        mission_sentence = (
            "The chance to join a laboratory team and test computational ideas against real data "
            "is the reason I am applying."
        )
        coursework = ", ".join((education.get("core_coursework") or [])[:3])
        field_paragraph = (
            f"My coursework in {coursework or 'algorithms and AI fundamentals'} gives me the basic "
            "vocabulary, and my PyTorch experiments have taught me how quickly a result can change "
            "when a split or metric is wrong. I want to learn how a research group designs a question "
            "and checks a result. I am at the beginning of that training and ready to do the careful work."
        )
    elif domain == "COMMUNITY_VOLUNTEERING":
        mission_sentence = "Its work with young people and community education is the reason I am applying."
        experience_detail = ""
        if experience:
            details = [_clean(d) for d in experience.get("details", []) if _clean(d)]
            experience_detail = details[0] if details else ""
        field_paragraph = (
            f"At UTM I work in mixed Malaysian and international teams. {experience_detail} "
            "That is not the same as running a classroom, but it has taught me to explain technical "
            "ideas without jargon and to ask what a learner already knows. I want to learn how "
            "community educators plan a session and measure whether it was useful."
        )
    else:
        mission_sentence = f"The program is run by {organizer}, and I want to contribute to it."
        field_paragraph = (
            "My work so far has been small in scale but practical. I build systems, test them against "
            "real inputs, and write down what failed. I want to apply that habit where the results "
            "matter to people outside the project."
        )

    name = _clean(personal.get("full_name_en")) or "Mohammad Mahdi Alsalkadi"
    degree = _clean(education.get("degree")) or "Bachelor of Computer Science (Artificial Intelligence)"
    university = _clean(education.get("institution")) or "Universiti Teknologi Malaysia"
    cgpa = _clean(education.get("cgpa"))
    year = _clean(education.get("academic_year")) or "first-year"
    email = _clean(personal.get("email"))
    phone = _clean(personal.get("phone_my"))

    paragraphs: List[str] = []
    paragraphs.append(
        f"Dear {organizer} Selection Committee,\n\n"
        f"I am applying for {title}. {mission_sentence} I am a {year} student studying "
        f"{degree} at {university}"
        + (f", where I maintain a {cgpa} CGPA" if cgpa else "")
        + "."
    )

    if project_title and project_bullet:
        project_paragraph = f"My closest relevant work is {project_title}. {project_bullet}"
        project_paragraph += (
            " That work taught me to keep data collection, rules, and reporting separate so "
            "each step can be checked."
        )
        paragraphs.append(project_paragraph)

    paragraphs.append(field_paragraph)
    paragraphs.append(
        "I want supervised practice, direct feedback from people who do this work, and a chance "
        "to see whether a computational background can help beyond a laptop. I can commit to the "
        "full dates and the physical work. Thank you for considering my application."
    )

    signature = f"Sincerely,\n{name}"
    if degree:
        signature += f"\n{degree}, {university}"
    contact = " | ".join(part for part in (email, phone) if part)
    if contact:
        signature += f"\n{contact}"
    paragraphs.append(signature)

    return _clean_text("\n\n".join(paragraphs))


def _clean_text(text: str) -> str:
    """Normalize whitespace while preserving paragraph breaks."""
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in text.split("\n\n")]
    return "\n\n".join(p for p in paragraphs if p)


def find_style_issues(text: str, word_range: Tuple[int, int] = WORD_RANGE) -> List[str]:
    issues: List[str] = []
    words = count_words(text)
    if words < word_range[0]:
        issues.append(f"too short: {words} words (minimum {word_range[0]})")
    if words > word_range[1]:
        issues.append(f"too long: {words} words (maximum {word_range[1]})")
    lowered = _clean(text).lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            issues.append(f"banned phrase: {phrase}")
    for term in SENSITIVE_TERMS:
        if term in lowered:
            issues.append(f"private or irrelevant term: {term}")
    return issues


def find_unsupported_metrics(text: str, profile: Dict[str, Any]) -> List[str]:
    source = _corpus(profile)
    unsupported: List[str] = []
    for metric in set(re.findall(r"\b\d+(?:\.\d+)?%", text or "")):
        if metric.lower() not in source:
            unsupported.append(metric)
    return sorted(unsupported)


def validate_motivation_essay(
    text: str,
    profile: Dict[str, Any],
    opp: Dict[str, Any],
    word_range: Tuple[int, int] = WORD_RANGE,
) -> Dict[str, Any]:
    issues = find_style_issues(text, word_range=word_range)
    issues.extend(f"unsupported metric: {m}" for m in find_unsupported_metrics(text, profile))

    corpus = f"{_clean(opp.get('title'))} {_clean(opp.get('raw_description'))} {_clean(opp.get('raw_terms_text'))}".lower()
    kuwait_mandated = any(marker in corpus for marker in _KUWAIT_MARKERS)
    if not kuwait_mandated and "kuwait" in (text or "").lower():
        issues.append("mentions Kuwait when the opportunity does not require it")

    github_mandated = "github" in corpus or "code repository" in corpus
    if not github_mandated and "github" in (text or "").lower():
        issues.append("mentions GitHub when it is not mandated")

    return {
        "ok": not issues,
        "word_count": count_words(text),
        "issues": issues,
    }


def build_motivation_prompt(
    opp: Dict[str, Any],
    profile: Dict[str, Any],
    word_range: Tuple[int, int] = WORD_RANGE,
) -> str:
    """Build a constrained prompt for an optional LLM writer."""
    personal = profile.get("personal", {}) or {}
    education = profile.get("education", {}) or {}
    projects = [
        {
            "title": _clean(p.get("title")),
            "summary": _clean(p.get("summary")),
            "bullets": [_clean(b) for b in p.get("raw_bullet_points", []) if _clean(b)],
            "technologies": p.get("technologies", []),
        }
        for p in profile.get("projects", [])
        if isinstance(p, dict)
    ]
    experiences = [
        {
            "organization": _clean(e.get("organization")),
            "role": _clean(e.get("role")),
            "details": [_clean(d) for d in e.get("details", []) if _clean(d)],
        }
        for e in profile.get("experience", [])
        if isinstance(e, dict)
    ]
    return (
        f"Write a {word_range[0]}-{word_range[1]} word motivation statement for "
        f"{_clean(personal.get('full_name_en')) or 'the candidate'} applying to "
        f"'{_clean(opp.get('title'))}' organized by '{_clean(opp.get('organizer'))}' "
        f"in {_clean(opp.get('location_city'))}, {_clean(opp.get('location_country'))}.\n\n"
        f"Opportunity description:\n{_clean(opp.get('raw_description'))[:1400]}\n\n"
        f"Candidate facts. These are the only facts you may use:\n"
        f"- Education: {_clean(education.get('degree'))} at {_clean(education.get('institution'))}, "
        f"{_clean(education.get('academic_year'))}, CGPA {_clean(education.get('cgpa'))}.\n"
        f"- Projects: {projects}\n"
        f"- Experience: {experiences}\n\n"
        "Rules:\n"
        "- Use one concrete project and one concrete experience. Do not list every project.\n"
        "- Use a number only if it appears in the candidate facts above.\n"
        "- Do not invent awards, jobs, publications, marine experience, teaching experience, or policy experience.\n"
        "- Do not mention Kuwait, GitHub, passport numbers, matric numbers, t-shirt sizes, or age.\n"
        "- Do not use these phrases: " + "; ".join(BANNED_PHRASES) + ".\n"
        "- Avoid em dashes, three-item rhetorical lists, and generic closing lines.\n"
        "- Write in plain, specific English. Prefer short sentences. No headings.\n"
        f"- Return only the statement, {word_range[0]}-{word_range[1]} words."
    )
