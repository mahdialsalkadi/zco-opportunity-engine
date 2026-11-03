#!/usr/bin/env python3
"""Phase 1 reliability tests: migrations, provenance, and confidence."""

from __future__ import annotations

import json
import pathlib
import sqlite3
import subprocess
import sys

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database import OpportunityDatabase, RawOpportunityRecord  # noqa: E402


def _record(**overrides) -> RawOpportunityRecord:
    values = dict(
        title="Coastal Cleanup",
        organizer="Reef Watch",
        source_url="https://example.org/post",
        apply_url="https://example.org/apply",
        location_country="Malaysia",
        location_city="Kuala Lumpur",
        is_inside_malaysia=True,
        track_category="NATURE_ECO_CONSERVATION",
        raw_description="Volunteer coastal cleanup.",
        raw_terms_text="No fee.",
        deadline_iso="2027-03-01",
        source_feed_id="rss_nature",
        source_type="rss",
        deadline_confidence=0.7,
        program_start_iso="2027-06-01",
        program_end_iso="2027-08-31",
    )
    values.update(overrides)
    return RawOpportunityRecord(**values)


def _old_opportunities_table(db_path: pathlib.Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL DEFAULT 'RAW_INGESTED',
            ingested_at TEXT NOT NULL DEFAULT '',
            is_inside_malaysia INTEGER NOT NULL DEFAULT 0,
            track_category TEXT NOT NULL DEFAULT '',
            match_score INTEGER DEFAULT 0,
            source_feed_id TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            apply_url TEXT NOT NULL DEFAULT '',
            deadline_iso TEXT NOT NULL DEFAULT '',
            organizer TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        "INSERT INTO opportunities (status, ingested_at) VALUES ('RAW_INGESTED', '2026-01-01')"
    )
    conn.commit()
    conn.close()


def test_schema_migration_is_additive_and_idempotent(tmp_path):
    db_path = tmp_path / "old.db"
    _old_opportunities_table(db_path)

    db = OpportunityDatabase(db_path)
    with db.connect() as conn:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(opportunities)")
        }
    assert {
        "source_type",
        "source_confidence",
        "deadline_confidence",
        "provenance_json",
        "program_start_iso",
        "program_end_iso",
    } <= columns

    with db.connect() as conn:
        versions = [
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
        ]
    assert versions == [1, 2, 3, 4]

    # Re-opening must not re-apply or fail.
    OpportunityDatabase(db_path)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 4


def test_ingest_records_provenance_and_dedupes(tmp_path):
    db = OpportunityDatabase(tmp_path / "provenance.db")
    record = _record()

    assert db.ingest_raw_opportunity(record) is not None
    row = db.get_opportunities_by_status("RAW_INGESTED")[0]
    assert row["source_type"] == "rss"
    assert 0.5 <= row["source_confidence"] <= 1.0
    assert row["deadline_confidence"] == 0.7
    assert row["program_start_iso"] == "2027-06-01"
    assert row["program_end_iso"] == "2027-08-31"
    assert row["last_seen_at"]

    provenance = json.loads(row["provenance_json"])
    assert provenance["source_feed_id"] == "rss_nature"
    assert provenance["deadline_confidence"] == 0.7
    assert provenance["program_start_iso"] == "2027-06-01"
    assert provenance["program_end_iso"] == "2027-08-31"

    # Same fingerprint is idempotent; it refreshes last_seen_at instead of duplicating.
    assert db.ingest_raw_opportunity(record) is None
    assert len(db.get_opportunities_by_status("RAW_INGESTED")) == 1


def test_local_testbed_source_has_low_confidence(tmp_path):
    db = OpportunityDatabase(tmp_path / "testbed.db")
    record = _record(
        title="[Local Interactive Testbed] Demo",
        apply_url="file:///tmp/demo.html",
        source_feed_id="local_testbed_portal",
        source_type="",
        deadline_confidence=None,
    )

    db.ingest_raw_opportunity(record)
    row = db.get_opportunities_by_status("RAW_INGESTED")[0]
    assert row["source_type"] == "local_testbed"
    assert row["source_confidence"] <= 0.2


def test_private_data_checker_passes():
    if not (BASE_DIR / ".git").exists():
        import pytest

        pytest.skip("not a git checkout")
    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "scripts" / "check_no_private_data.py")],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
