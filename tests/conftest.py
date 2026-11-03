#!/usr/bin/env python3
"""Shared test isolation.

Tests import production modules that create SQLite databases, portfolios, and
generated documents at import time. Point every one of those paths at a
throwaway session directory before any test module is imported, so a test run
can never migrate the real ``data/opportunities.db`` or overwrite a private
profile.
"""

from __future__ import annotations

import atexit
import os
import pathlib
import shutil
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
TEST_ROOT = pathlib.Path(
    tempfile.mkdtemp(prefix="zco-tests-", dir=tempfile.gettempdir())
)
TEST_DATA_DIR = TEST_ROOT / "data"
TEST_CONFIG_DIR = TEST_ROOT / "config"
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
TEST_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Environment must be set before ``paths`` (or any module importing it) loads.
os.environ["ZCO_DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["ZCO_CONFIG_DIR"] = str(TEST_CONFIG_DIR)
os.environ["DASHBOARD_AUTH_TOKEN"] = "phase2-test-dashboard-token-0123456789"
os.environ["TELEGRAM_ADMIN_CHAT_IDS"] = "12345"
os.environ["TELEGRAM_BOT_TOKEN"] = "phase2-test-telegram-token"
os.environ["ZCO_AUTO_SUBMIT"] = "0"

# Private profiles are intentionally not copied. The example files make the
# engines runnable without turning placeholder data into candidate facts.
for name in (
    "master_profile.example.yaml",
    "candidate_profile.example.json",
    "telegram_config.json",
):
    source = REPO_ROOT / "config" / name
    if source.exists():
        shutil.copy2(source, TEST_CONFIG_DIR / name)

# The FRIM portal is a tracked, fake-receipt testbed fixture used by the browser
# form tests. Copy it so tests never write into the repository data tree.
live_portals = REPO_ROOT / "data" / "live_portals"
if live_portals.is_dir():
    shutil.copytree(live_portals, TEST_DATA_DIR / "live_portals")

for directory in (
    TEST_DATA_DIR / "documents",
    TEST_DATA_DIR / "documents" / "custom_cvs",
    TEST_DATA_DIR / "logs",
    TEST_DATA_DIR / "dashboards",
    TEST_DATA_DIR / "screenshots",
):
    directory.mkdir(parents=True, exist_ok=True)


def _cleanup() -> None:
    if os.environ.get("ZCO_KEEP_TEST_ARTIFACTS", "").strip() == "1":
        return
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


atexit.register(_cleanup)
