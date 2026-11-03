#!/usr/bin/env python3
"""Central filesystem paths.

Production uses the repository's ``config/`` and ``data/`` directories. Tests
and isolated deployments can override them with ``ZCO_CONFIG_DIR`` and
``ZCO_DATA_DIR`` before importing this module.
"""

from __future__ import annotations

import os
import pathlib

from env_loader import load_local_env

BASE_DIR = pathlib.Path(__file__).resolve().parent

load_local_env(BASE_DIR)


def _resolve(env_var: str, default: pathlib.Path) -> pathlib.Path:
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return default
    return pathlib.Path(raw).expanduser().resolve()


CONFIG_DIR = _resolve("ZCO_CONFIG_DIR", BASE_DIR / "config")
DATA_DIR = _resolve("ZCO_DATA_DIR", BASE_DIR / "data")

DOCS_DIR = DATA_DIR / "documents"
CUSTOM_CVS_DIR = DOCS_DIR / "custom_cvs"
LOG_DIR = DATA_DIR / "logs"
DASHBOARD_DIR = DATA_DIR / "dashboards"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"

DB_PATH = DATA_DIR / "opportunities.db"
DASHBOARD_TOKEN_FILE = DATA_DIR / "dashboard_token.txt"
SUPERVISOR_STATE_FILE = DATA_DIR / "supervisor_state.json"
DASHBOARD_PATH = DASHBOARD_DIR / "verified_opportunities_matrix.md"

PORTFOLIO_FILE = CONFIG_DIR / "comprehensive_portfolio.json"
CANDIDATE_PROFILE_PATH = CONFIG_DIR / "candidate_profile.json"
CANDIDATE_PROFILE_EXAMPLE_PATH = CONFIG_DIR / "candidate_profile.example.json"
MASTER_PROFILE_PATH = CONFIG_DIR / "master_profile.yaml"
MASTER_PROFILE_EXAMPLE_PATH = CONFIG_DIR / "master_profile.example.yaml"
TELEGRAM_CONFIG_PATH = CONFIG_DIR / "telegram_config.json"

CV_PDF_FILE = DOCS_DIR / "cv_mohammad_mahdi.pdf"
CV_MD_FILE = DOCS_DIR / "cv_mohammad_mahdi.md"
BASE_REFERENCE_PDF_PATH = DOCS_DIR / "CV_Mohammad_Mahdi_Alsalkadi_Reference.pdf"
BASE_REFERENCE_JSON_PATH = CUSTOM_CVS_DIR / "data_base_reference.json"


def ensure_runtime_dirs() -> None:
    """Create the directories the services write to at runtime."""
    for directory in (
        DATA_DIR,
        DOCS_DIR,
        CUSTOM_CVS_DIR,
        LOG_DIR,
        DASHBOARD_DIR,
        SCREENSHOTS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
