#!/usr/bin/env python3
"""
ZCO-Engine v3.0 — Turnkey Google Antigravity Plugin & Sidecar Installer (`install_zco_plugin.py`)
=================================================================================================
Generates and wires up the complete Google Antigravity Plugin directory structure for v3.0:
- `plugin.json` (Antigravity Plugin manifest)
- `mcp.json` (Model Context Protocol server configuration)
- `sidecars/crawler-daemon/sidecar.json` (24/7 continuous `async_crawler.py` background daemon)
- `sidecars/six-hour-auditor/sidecar.json` (6-hour cron `0 */6 * * *` via `schedule` + `agentapi`
  that audits new items and prepares applications using `CandidateMemoryVault`; submission is opt-in)
- `config/candidate_profile.json` (Mohammad Mahdi's Tri-Jurisdiction Profile + Learned Vault)
- `.agents/skills/zco-hunter/SKILL.md` (Agent Skill orchestration for draft preparation & Vault Learning)
- `.agents/subagents/guidelines_inspector.md` (Deep terms, hidden-fee & form field inspector)
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict

from engines_and_auditor import DEFAULT_CANDIDATE_PROFILE


PLUGIN_MANIFEST: Dict[str, Any] = {
    "name": "zco-opportunity-engine",
    "version": "3.0.0",
    "description": "24/7 Background Opportunity Crawler + 6-Hour Zero-Cost Auditor + Self-Learning Memory Vault & human-approved Applicant for Mohammad Mahdi",
    "author": "Mohammad Mahdi",
    "mcp": "mcp.json",
    "skills": [".agents/skills/zco-hunter"],
    "sidecars": [
        "sidecars/crawler-daemon",
        "sidecars/six-hour-auditor",
    ],
}

MCP_CONFIG: Dict[str, Any] = {
    "mcpServers": {
        "zco-opportunity-engine": {
            "command": "python3",
            "args": ["server.py"],
            "env": {
                "PYTHONUNBUFFERED": "1",
            },
        }
    }
}

CRAWLER_SIDECAR_CONFIG: Dict[str, Any] = {
    "name": "crawler-daemon",
    "description": "Runs async_crawler.py continuously in the background (24/7) to ingest opportunities across all 6 tracks into SQLite storage",
    "command": "python3",
    "args": [
        "../../async_crawler.py",
        "--daemon",
        "--poll-interval-minutes",
        "20",
    ],
    "restartPolicy": "always",
}

AUDITOR_SIDECAR_CONFIG: Dict[str, Any] = {
    "name": "six-hour-auditor",
    "description": "Wakes up the Antigravity Agent every 6 hours (0 */6 * * *) to audit newly queued opportunities, prepare applications from the Memory Vault, and ask once for any newly encountered fields. Submit clicks stay disabled unless explicitly approved.",
    "command": "schedule",
    "args": [
        "0 */6 * * *",
        "agentapi",
        "new-conversation",
        "Run /zco-hunter in 6-hour batch audit & draft-preparation mode: execute run_six_hour_batch_audit(window_hours=6.0, allow_submit=false). Prepare applications for all verified 100% zero-cost opportunities where all required fields exist in CandidateMemoryVault. Do NOT click Submit unless the human explicitly approves a specific opportunity (or the operator sets ZCO_AUTO_SUBMIT=1). If any new form fields are missing from the Vault, list the consolidated questions for Mohammad Mahdi so that once answered, they are saved forever and the paused applications are re-prepared.",
    ],
    "restartPolicy": "always",
}

SKILL_MD_CONTENT = """---
name: zco-hunter
description: Audits, categorizes, and autonomously applies to 100% zero-cost scholarships, AI hackathons, nature/eco-conservation camps, and volunteering opportunities for Mohammad Mahdi (Syrian national, 1st-year AI student at UTM Malaysia, Kuwait resident, age 20) using a persistent self-learning Memory Vault.
---

# ZCO-Hunter v3.0 — Autonomous Opportunity Auditor, Self-Learning Vault & Human-Approved Applicant

## 1. Execution Modes

### Mode A: Scheduled 6-Hour Batch Audit & Draft Preparation (Default Background Trigger)
1. Call `run_six_hour_batch_audit(window_hours=6.0, allow_submit=false)` (or run `python3 server.py --audit-batch --window-hours 6`).
2. The engine automatically:
   - Filters all `RAW_INGESTED` items from the past 6 hours through `ZeroCostGatekeeper` ($0 fees + flights/transport + accommodation + meals) and `TriJurisdictionEligibilityEngine` (Syrian nationality, Malaysia UTM 1st-year AI student age 20, valid Kuwait residency).
   - Runs `AutonomousApplicantEngine` on every eligible opportunity:
     - **If 100% of required form fields are already stored in `CandidateMemoryVault`**: Prepares the application, generates a tailored Motivation Letter, and records it as `READY_FOR_REVIEW` without clicking Submit. A human approval action (Telegram, dashboard, or `approve_and_submit_opportunity`) is required to submit.
     - **If one or more required form fields are encountered for the very first time**: Saves a pre-filled draft (`PAUSED_NEEDS_USER_INPUT`) and outputs a consolidated list of `consolidated_questions_for_user`.
3. Present the updated dashboard (`verified_opportunities_matrix.md`) and, if `consolidated_questions_for_user` is non-empty, ask Mohammad only those missing questions.

### Mode B: Self-Learning Vault Update & Application Re-Preparation
Whenever Mohammad provides answers to any missing questions in chat:
1. Call `provide_missing_answers_and_resume(answers_json, allow_submit=false)` (or run `python3 server.py --learn-answers '<JSON>'`).
2. The engine permanently writes those answers into `candidate_vault` (SQLite) and `config/candidate_profile.json` so **it will NEVER ask Mohammad for those fields again** in any future 6-hour cycle.
3. It re-prepares all `PAUSED_NEEDS_USER_INPUT` applications as `READY_FOR_REVIEW` and refreshes `verified_opportunities_matrix.md`. No submission occurs without explicit approval.
"""

SUBAGENT_MD_CONTENT = """---
name: guidelines_inspector
description: Specialized subagent that inspects official opportunity guidelines, FAQs, and application portals to detect hidden fees, verify tri-jurisdiction eligibility, and extract required form fields.
---

# Guidelines, Zero-Cost & Form Schema Inspector Subagent

When given an opportunity URL:
1. Verify $0 application/registration/confirmation fee and 100% travel/accommodation/meal coverage.
2. Verify eligibility across Syria (`SY`), Malaysia UTM AI Student Pass (`MY`), or Kuwait Residency (`KW`).
3. Extract the exact list of required form fields (`required_form_fields`) so `AutonomousApplicantEngine` can auto-fill them from `CandidateMemoryVault`.
"""


def scaffold_plugin_workspace(base_dir: pathlib.Path) -> Dict[str, str]:
    base_dir.mkdir(parents=True, exist_ok=True)
    created: Dict[str, str] = {}

    def _write_json(rel_path: str, data: Dict[str, Any]) -> None:
        target = base_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        created[rel_path] = str(target)

    def _write_text(rel_path: str, content: str) -> None:
        target = base_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created[rel_path] = str(target)

    _write_json("plugin.json", PLUGIN_MANIFEST)
    _write_json("mcp.json", MCP_CONFIG)
    _write_json("sidecars/crawler-daemon/sidecar.json", CRAWLER_SIDECAR_CONFIG)
    _write_json("sidecars/six-hour-auditor/sidecar.json", AUDITOR_SIDECAR_CONFIG)
    _write_json("config/candidate_profile.json", DEFAULT_CANDIDATE_PROFILE)
    _write_text(".agents/skills/zco-hunter/SKILL.md", SKILL_MD_CONTENT)
    _write_text(".agents/subagents/guidelines_inspector.md", SUBAGENT_MD_CONTENT)

    return created


if __name__ == "__main__":
    target_dir = (
        pathlib.Path(sys.argv[1]).resolve()
        if len(sys.argv) > 1
        else pathlib.Path(__file__).resolve().parent
    )
    files = scaffold_plugin_workspace(target_dir)
    print(json.dumps({"installed_root": str(target_dir), "created_files": files}, indent=2, ensure_ascii=False))