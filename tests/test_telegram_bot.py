#!/usr/bin/env python3
"""
Unit tests for ZCO Telegram Bot formatting, callbacks, and database integration
"""

import json
import pathlib
import sys
import pytest

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database import OpportunityDatabase, OpportunityStatus, RawOpportunityRecord
from telegram_bot import ZCOTelegramBotService, format_opportunity_card, load_bot_config


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_tg.db"
    return OpportunityDatabase(db_file)


def test_telegram_config_loading():
    cfg = load_bot_config()
    assert "bot_token" in cfg
    assert cfg["bot_username"] == "Uiii007bot"


def test_format_opportunity_card():
    sample_opp = {
        "id": 1,
        "opportunity_code": "MY-GAI-002",
        "title": "Malaysia Green-AI & Smart Rainforest Monitoring Hackathon 2027",
        "organizer": "FRIM & AI Malaysia",
        "location_city": "Kepong & Kuala Lumpur",
        "location_country": "Malaysia",
        "is_inside_malaysia": 1,
        "match_score": 99,
        "status": OpportunityStatus.VERIFIED_ELIGIBLE,
        "deadline_iso": "2026-12-05",
        "apply_url": "https://www.frim.gov.my/",
        "financial_coverage_json": json.dumps(
            {"coverage_summary_ar": "إعفاء كامل من الرسوم (0 دولار) + سكن كامل + وجبات"}
        ),
    }

    text, markup = format_opportunity_card(sample_opp)
    assert "MY-GAI-002" in text
    assert "Green-AI" in text
    assert "99%" in text

    # Verify buttons
    callback_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "approve:MY-GAI-002" in callback_data
    assert "decline:MY-GAI-002" in callback_data
    assert "kit:MY-GAI-002" in callback_data


def test_subscriber_registration_and_notification(temp_db):
    temp_db.register_telegram_subscriber(chat_id=12345678, username="test_user", first_name="Mahdi")
    subs = temp_db.get_telegram_subscribers()
    assert len(subs) == 1
    assert subs[0]["chat_id"] == 12345678
    assert subs[0]["username"] == "test_user"

    # Add opportunity
    rec = RawOpportunityRecord(
        title="Test Opportunity",
        organizer="Org",
        source_url="https://example.org",
        apply_url="https://example.org/apply",
        location_country="Malaysia",
        location_city="KL",
        is_inside_malaysia=True,
        track_category="CORE_AI_HACKATHONS",
        raw_description="Description",
        raw_terms_text="0 fee, hotel covered",
        deadline_iso="2027-01-01",
        source_feed_id="feed1",
    )
    temp_db.ingest_raw_opportunity(rec)
    opp = temp_db.fetch_unprocessed_batch(window_hours=24.0)[0]
    temp_db.commit_audit_verdict(
        opportunity_id=opp["id"],
        status=OpportunityStatus.VERIFIED_ELIGIBLE,
        match_score=95,
        matched_jurisdiction_track="UTM",
        visa_support_summary="None needed",
        financial_coverage={},
        rejection_reason="",
    )

    unnotified = temp_db.get_unnotified_opportunities_for_chat(12345678)
    assert len(unnotified) == 1
    opp_code = unnotified[0]["opportunity_code"]

    # Record notification
    first_record = temp_db.record_telegram_notification(opp_code, 12345678)
    assert first_record is True
    # Deduplication check
    second_record = temp_db.record_telegram_notification(opp_code, 12345678)
    assert second_record is False

    # Now unnotified should be empty
    unnotified_after = temp_db.get_unnotified_opportunities_for_chat(12345678)
    assert len(unnotified_after) == 0


def test_decline_opportunity(temp_db):
    rec = RawOpportunityRecord(
        title="Declined Opp",
        organizer="Org",
        source_url="https://example.org",
        apply_url="https://example.org/apply2",
        location_country="Malaysia",
        location_city="KL",
        is_inside_malaysia=True,
        track_category="CORE_AI_HACKATHONS",
        raw_description="Description",
        raw_terms_text="0 fee",
        deadline_iso="2027-01-01",
        source_feed_id="feed1",
    )
    temp_db.ingest_raw_opportunity(rec)
    opp = temp_db.fetch_unprocessed_batch(window_hours=24.0)[0]
    code = opp["opportunity_code"]

    res = temp_db.update_opportunity_status(code, OpportunityStatus.DECLINED_BY_USER, "User declined via Telegram")
    assert res is True

    updated = temp_db.get_opportunity_by_code(code)
    assert updated["status"] == OpportunityStatus.DECLINED_BY_USER
    assert updated["rejection_reason"] == "User declined via Telegram"
