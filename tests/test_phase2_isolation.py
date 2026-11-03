#!/usr/bin/env python3
"""Phase 2 tests: isolated paths, atomic writes, honest coverage, safe edits."""

from __future__ import annotations

import json
import os
import pathlib
import sys

import yaml

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import paths  # noqa: E402
from coverage_utils import UNKNOWN_COVERAGE_AR, coverage_summary  # noqa: E402
from database import OpportunityDatabase  # noqa: E402
from file_utils import atomic_write_json, atomic_write_text  # noqa: E402
from portfolio_and_docs_engine import (  # noqa: E402
    PortfolioManager,
    normalize_profile_updates,
)


def test_runtime_paths_are_isolated_from_the_repository():
    assert paths.DATA_DIR != BASE_DIR / "data"
    assert paths.CONFIG_DIR != BASE_DIR / "config"
    assert paths.DATA_DIR == pathlib.Path(os.environ["ZCO_DATA_DIR"]).resolve()
    assert paths.CONFIG_DIR == pathlib.Path(os.environ["ZCO_CONFIG_DIR"]).resolve()
    for child in (
        paths.DB_PATH,
        paths.LOG_DIR,
        paths.DOCS_DIR,
        paths.CUSTOM_CVS_DIR,
        paths.DASHBOARD_PATH,
    ):
        assert paths.DATA_DIR in child.parents


def test_coverage_summary_never_invents_funding():
    assert coverage_summary(None) == (UNKNOWN_COVERAGE_AR, False)
    assert coverage_summary({}) == (UNKNOWN_COVERAGE_AR, False)
    assert coverage_summary({"coverage_summary_ar": "   "}) == (UNKNOWN_COVERAGE_AR, False)
    assert coverage_summary("100% covered") == (UNKNOWN_COVERAGE_AR, False)
    assert coverage_summary({"coverage_summary_ar": "تغطية كاملة"}) == ("تغطية كاملة", True)


def test_normalize_profile_updates_validates_and_preserves_clears():
    cleaned, errors = normalize_profile_updates(
        {
            "full_name_en": "  Mohammad Mahdi  ",
            "email": "mahdi@example.org",
            "phone_my": "+60 11-0000 0000",
            "cgpa": "3.53 / 4.00",
            "github_url": "https://github.com/example",
            "address_my": "",
            "activity_preferences": " NATURE_ECO_CONSERVATION , OUTDOOR_LEADERSHIP_CAMPS ",
            "location_preference": "INSIDE_MALAYSIA",
            "availability_from": "2027-06-01",
            "availability_to": "2027-08-31",
        }
    )
    assert errors == []
    assert cleaned["full_name_en"] == "Mohammad Mahdi"
    assert cleaned["address_my"] == ""
    assert (
        cleaned["activity_preferences"]
        == "NATURE_ECO_CONSERVATION, OUTDOOR_LEADERSHIP_CAMPS"
    )
    assert cleaned["location_preference"] == "INSIDE_MALAYSIA"
    assert cleaned["availability_from"] == "2027-06-01"
    assert cleaned["availability_to"] == "2027-08-31"

    _cleaned, errors = normalize_profile_updates(
        {
            "email": "not-an-email",
            "github_url": "javascript:alert(1)",
            "cgpa": "3.53.1",
            "activity_preferences": "NATURE_ECO_CONSERVATION, UNKNOWN_TRACK",
            "location_preference": "MOON",
            "availability_from": "2027-13-01",
            "unknown_field": "x",
        }
    )
    assert len(errors) == 7

    _cleaned, errors = normalize_profile_updates(
        {"availability_from": "2027-09-01", "availability_to": "2027-06-01"}
    )
    assert errors == ["availability_from must be on or before availability_to."]


def test_atomic_write_is_private_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "nested" / "profile.json"

    atomic_write_json(target, {"a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    assert (target.stat().st_mode & 0o777) == 0o600
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))

    atomic_write_text(target, "updated\n")
    assert target.read_text(encoding="utf-8") == "updated\n"
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_portfolio_syncs_private_profiles_and_clears_vault_values(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "candidate_profile.example.json").write_text(
        json.dumps({"candidate": {"full_name": "Example Person"}}), encoding="utf-8"
    )
    (config_dir / "master_profile.yaml").write_text(
        "personal:\n  full_name_en: Example Person\neducation:\n  cgpa: '0.00'\n",
        encoding="utf-8",
    )

    pm = PortfolioManager(config_dir=config_dir)
    pm.update_profile(
        {
            "email": "mahdi@example.org",
            "cgpa": "3.53 / 4.00",
            "activity_preferences": "NATURE_ECO_CONSERVATION, OUTDOOR_LEADERSHIP_CAMPS",
            "location_preference": "OUTSIDE_MALAYSIA",
            "availability_from": "2027-06-01",
            "availability_to": "2027-08-31",
        }
    )

    candidate = json.loads(
        (config_dir / "candidate_profile.json").read_text(encoding="utf-8")
    )
    assert candidate["candidate"]["email"] == "mahdi@example.org"
    assert candidate["candidate"]["cgpa"] == "3.53 / 4.00"
    assert (
        candidate["candidate"]["activity_preferences"]
        == "NATURE_ECO_CONSERVATION, OUTDOOR_LEADERSHIP_CAMPS"
    )
    assert candidate["candidate"]["location_preference"] == "OUTSIDE_MALAYSIA"
    assert candidate["candidate"]["availability_from"] == "2027-06-01"
    assert candidate["candidate"]["availability_to"] == "2027-08-31"

    master = yaml.safe_load(
        (config_dir / "master_profile.yaml").read_text(encoding="utf-8")
    )
    assert master["personal"]["email"] == "mahdi@example.org"
    assert (
        master["personal"]["activity_preferences"]
        == "NATURE_ECO_CONSERVATION, OUTDOOR_LEADERSHIP_CAMPS"
    )
    assert master["personal"]["location_preference"] == "OUTSIDE_MALAYSIA"
    assert master["personal"]["availability_from"] == "2027-06-01"
    assert master["personal"]["availability_to"] == "2027-08-31"
    assert master["education"]["cgpa"] == "3.53 / 4.00"

    db = OpportunityDatabase(tmp_path / "vault.db")
    with db.connect() as conn:
        pm.sync_to_sqlite_vault(conn)
        row = conn.execute(
            "SELECT field_value FROM candidate_vault WHERE field_key = 'email_address'"
        ).fetchone()
        assert row["field_value"] == "mahdi@example.org"
        activities = conn.execute(
            "SELECT field_value FROM candidate_vault WHERE field_key = 'activity_preferences'"
        ).fetchone()
        assert (
            activities["field_value"]
            == "NATURE_ECO_CONSERVATION, OUTDOOR_LEADERSHIP_CAMPS"
        )
        location = conn.execute(
            "SELECT field_value FROM candidate_vault WHERE field_key = 'location_preference'"
        ).fetchone()
        assert location["field_value"] == "OUTSIDE_MALAYSIA"
        available_from = conn.execute(
            "SELECT field_value FROM candidate_vault WHERE field_key = 'availability_from'"
        ).fetchone()
        assert available_from["field_value"] == "2027-06-01"
        available_to = conn.execute(
            "SELECT field_value FROM candidate_vault WHERE field_key = 'availability_to'"
        ).fetchone()
        assert available_to["field_value"] == "2027-08-31"

    pm.update_profile({"email": ""})
    with db.connect() as conn:
        pm.sync_to_sqlite_vault(
            conn, clear_keys=pm.vault_keys_to_clear({"email": ""})
        )
        row = conn.execute(
            "SELECT field_value FROM candidate_vault WHERE field_key = 'email_address'"
        ).fetchone()
        assert row is None


def test_corrupt_portfolio_is_preserved_before_reinitializing(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    portfolio_path = config_dir / "comprehensive_portfolio.json"
    portfolio_path.write_text("{not json", encoding="utf-8")

    PortfolioManager(config_dir=config_dir)

    backups = list(config_dir.glob("comprehensive_portfolio.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not json"
    assert isinstance(json.loads(portfolio_path.read_text(encoding="utf-8")), dict)
