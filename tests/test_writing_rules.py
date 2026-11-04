#!/usr/bin/env python3
"""Motivation statements must be grounded, readable, and free of stock phrases."""

from __future__ import annotations

import pathlib
import sys

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from typst_agentic_cv_engine import MasterProfileManager
from writing_rules import (
    BANNED_PHRASES,
    build_motivation_letter,
    build_motivation_prompt,
    count_words,
    validate_motivation_essay,
    humanize_text,
)

WWF_OPP = {
    "opportunity_code": "MY-ECO-491",
    "title": "WWF Malaysia Marine Conservation & Beach Cleanup Expedition 2027",
    "organizer": "WWF Malaysia & Marine Parks Department",
    "location_city": "Pulau Tioman & Langkawi",
    "location_country": "Malaysia",
    "track_category": "NATURE_ECO_CONSERVATION",
    "raw_description": (
        "Fully funded volunteer youth expedition focusing on coastal marine conservation, "
        "beach cleanups, coral reef restoration monitoring, and sea turtle sanctuary protection. "
        "Open to all university students residing in Malaysia."
    ),
    "raw_terms_text": "100% free. No application fee. Accommodation, meals and boat transfers covered.",
}


def test_wwf_letter_is_grounded_and_readable():
    profile = MasterProfileManager().data
    letter = build_motivation_letter(WWF_OPP, profile)
    check = validate_motivation_essay(letter, profile, WWF_OPP)

    assert check["ok"] is True, check["issues"]
    assert 180 <= count_words(letter) <= 280
    assert "WWF" in letter or "coastal" in letter
    assert "Kuwait" not in letter
    assert "github" not in letter.lower()
    assert "passport" not in letter.lower()
    for phrase in BANNED_PHRASES:
        assert phrase not in letter.lower()


def test_unsupported_metric_is_rejected():
    profile = MasterProfileManager().data
    essay = build_motivation_letter(WWF_OPP, profile)
    essay += " I also raised model accuracy to 97.3% on an unreported benchmark."
    check = validate_motivation_essay(essay, profile, WWF_OPP)

    assert check["ok"] is False
    assert any("97.3%" in issue for issue in check["issues"])


def test_prompt_contains_fact_and_style_constraints():
    profile = MasterProfileManager().data
    prompt = build_motivation_prompt(WWF_OPP, profile)

    assert "Do not invent awards" in prompt
    assert "Do not mention Kuwait" in prompt
    assert "Do not use these phrases" in prompt
    assert "180-280" in prompt


def test_humanize_text_removes_ai_tells():
    ai_raw = (
        "Here is my statement:\n\n"
        "In today's rapidly evolving world, I am applying for this program. "
        "The project — developed over six months — was not only efficient but also scalable. "
        "At its core, it helped users “seamlessly” organize data. I hope this helps!"
    )
    humanized = humanize_text(ai_raw)

    assert "Here is my statement" not in humanized
    assert "In today's rapidly evolving world" not in humanized
    assert "At its core" not in humanized
    assert "—" not in humanized
    assert "“" not in humanized
    assert "I hope this helps" not in humanized
    assert "not only" not in humanized.lower()
    assert "efficient and scalable" in humanized
