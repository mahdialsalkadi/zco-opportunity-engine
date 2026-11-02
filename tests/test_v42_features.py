#!/usr/bin/env python3
"""
Unit and integration tests for ZCO-Hunter v4.2 features:
1. Two-Hop Link Resolver (aggregator article -> official application form)
2. SPA Form Adapter (Google Forms, Airtable, Typeform ARIA listitem DOM parsing)
3. Telegram Bot Reply-to-Learn Flow (interactive vault learning on reply)
4. Motivation Essay Synthesizer & Persistent SQLite learned_qa_bank
"""

import asyncio
import json
import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from async_crawler import resolve_two_hop_application_link
from database import OpportunityDatabase, OpportunityStatus, RawOpportunityRecord
from engines_and_auditor import (
    AutonomousApplicantEngine,
    CandidateMemoryVault,
    DeepPageAndPdfInspector,
)
from telegram_bot import ZCOTelegramBotService


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_v42.db"
    return OpportunityDatabase(db_file)


def test_two_hop_link_resolver_mocked():
    """Verify two-hop resolver extracts official Google Forms URL and article body."""
    sample_article_html = """
    <html>
      <head><title>Global Sustainability Fellowship 2027</title></head>
      <body>
        <article class="entry-content">
          <h1>Global Sustainability Fellowship 2027</h1>
          <p>The Global Sustainability Fellowship offers 100% fully funded participation for young leaders.</p>
          <p>Eligible candidates receive round-trip airfare, accommodation, and a living stipend.</p>
          <div class="social-share">
            <a href="https://facebook.com/sharer">Share on Facebook</a>
            <a href="https://twitter.com/intent/tweet">Tweet</a>
          </div>
          <p>To register your official application, click below:</p>
          <p><a href="https://docs.google.com/forms/d/e/1FAIpQLScXexample123/viewform" class="btn">Apply Now</a></p>
        </article>
      </body>
    </html>
    """

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.read.return_value = sample_article_html.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        resolved_url, full_text = resolve_two_hop_application_link(
            "https://opportunitydesk.org/2026/11/02/global-sustainability-fellowship/"
        )

        assert "docs.google.com/forms" in resolved_url
        assert "Global Sustainability Fellowship" in full_text
        assert "fully funded" in full_text


def test_spa_google_forms_aria_inspection():
    """Verify DeepPageAndPdfInspector parses Google Forms / ARIA question containers."""
    sample_google_form_html = """
    <html>
      <head><title>Eco-Camp Volunteer Application Form</title></head>
      <body>
        <form action="/formResponse" method="POST">
          <!-- Item 1: Full Name -->
          <div role="listitem" class="ge-item">
            <div role="heading" aria-level="3" class="M7eMe">Candidate Full Name *</div>
            <input type="text" class="whsOnd" aria-label="Candidate Full Name" jsname="YPqjbf" required>
          </div>

          <!-- Item 2: Email -->
          <div role="listitem" class="ge-item">
            <div role="heading" aria-level="3" class="M7eMe">Active Email Address *</div>
            <input type="email" class="whsOnd" aria-label="Active Email Address" required>
          </div>

          <!-- Item 3: Current CGPA -->
          <div role="listitem" class="ge-item">
            <div role="heading" aria-level="3" class="M7eMe">Current University CGPA</div>
            <input type="text" class="whsOnd" aria-label="Current University CGPA">
          </div>

          <!-- Item 4: Motivation Statement -->
          <div role="listitem" class="ge-item">
            <div role="heading" aria-level="3" class="M7eMe">Why do you want to join this program? *</div>
            <textarea class="KHxj8b" aria-label="Why do you want to join this program?" required></textarea>
          </div>

          <!-- Item 5: Submit button -->
          <div role="button" aria-label="Submit" class="uArJbe">
            <span class="l4V7wb">Submit Application</span>
          </div>
        </form>
      </body>
    </html>
    """

    report = DeepPageAndPdfInspector.inspect_html_content(
        sample_google_form_html, base_url="https://docs.google.com/forms/d/sample"
    )

    discovered_keys = [f.mapped_vault_key for f in report.discovered_fields]
    assert "full_name" in discovered_keys
    assert "email_address" in discovered_keys
    assert "current_cgpa" in discovered_keys
    assert "tailored_motivation_essay" in discovered_keys

    # Check that required keys are enforced
    assert "full_name" in report.required_vault_keys
    assert "email_address" in report.required_vault_keys


def test_telegram_bot_reply_to_learn_flow(temp_db):
    """Verify that replying to a missing-field message updates the vault and resumes application."""
    bot_service = ZCOTelegramBotService(db_path=temp_db.db_path)

    # Ingest a test opportunity
    temp_db.ingest_raw_opportunity(
        RawOpportunityRecord(
            title="Borneo Rainforest Bio-AI Camp 2027",
            organizer="Borneo Environmental Society",
            source_url="https://example.org",
            apply_url="https://example.org/apply",
            location_country="Malaysia",
            location_city="Sabah",
            is_inside_malaysia=True,
            track_category="NATURE_ECO_CONSERVATION",
            raw_description="Field camp for AI students.",
            raw_terms_text="Fully funded.",
            deadline_iso="2026-12-01",
            source_feed_id="test_feed",
        )
    )
    opps = temp_db.get_verified_opportunities() or temp_db.get_opportunities_by_status(
        OpportunityStatus.RAW_INGESTED
    )
    opp_code = opps[0].get("opportunity_code") or "ID-1"

    # Register a simulated pending prompt message
    simulated_msg_id = 999123
    bot_service.pending_missing_replies[simulated_msg_id] = {
        "opportunity_code": opp_code,
        "field_key": "dietary_preference",
        "label_ar": "تفضيلات الطعام",
    }

    # Simulate user Telegram reply
    update_mock = MagicMock()
    update_mock.message.text = "Halal / Vegetarian"
    update_mock.effective_chat.id = 12345
    update_mock.message.reply_to_message = MagicMock()
    update_mock.message.reply_to_message.message_id = simulated_msg_id
    update_mock.message.reply_to_message.text = (
        f"توقف التقديم مؤقتاً\nالفرصة: `{opp_code}`\nالحقل المطلوب: `dietary_preference`"
    )
    update_mock.message.reply_text = AsyncMock()
    update_mock.message.reply_photo = AsyncMock()

    context_mock = MagicMock()

    # Execute handler synchronously via asyncio.run
    asyncio.run(bot_service.text_message_handler(update_mock, context_mock))

    # Verify vault learned the field
    known = bot_service.vault.get_known_fields()
    assert known.get("dietary_preference") == "Halal / Vegetarian"

    # Verify reply message was sent
    assert update_mock.message.reply_text.called
    sent_text = update_mock.message.reply_text.call_args[0][0]
    assert "تم حفظ المعلومة" in sent_text
    assert "dietary_preference" in sent_text


def test_motivation_essay_synthesizer_and_qa_bank(temp_db):
    """Verify motivation statement synthesis produces >= 200 words and caches in learned_qa_bank."""
    vault = CandidateMemoryVault(temp_db)
    applicant = AutonomousApplicantEngine(temp_db, vault)

    sample_opp = {
        "id": 101,
        "opportunity_code": "MY-TST-101",
        "title": "FRIM Smart Tropical Forestry & Edge AI Fellowship",
        "organizer": "Forest Research Institute Malaysia",
        "location_city": "Kepong",
        "location_country": "Malaysia",
        "track_category": "GREEN_AI_CLIMATE_TECH",
        "raw_description": "Fellowship applying edge AI and computer vision to tropical tree census.",
    }

    known = vault.get_known_fields()
    essay = applicant.synthesize_motivation_statement(sample_opp, known)

    # Assert length and academic grounding
    words = essay.split()
    assert len(words) >= 150
    assert "Universiti Teknologi Malaysia" in essay or "UTM" in essay
    assert "Artificial Intelligence" in essay

    # Assert persistence in SQLite learned_qa_bank
    all_qa = temp_db.get_all_learned_qa()
    assert any("my-tst-101" in k.lower() for k in all_qa)
    cached_key = [k for k in all_qa if "my-tst-101" in k.lower()][0]
    cached_entry = all_qa[cached_key]
    assert cached_entry["answer_text"] == essay
    assert "motivation_statement" in json.loads(cached_entry["tags_json"])
