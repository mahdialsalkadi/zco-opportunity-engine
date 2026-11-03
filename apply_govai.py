#!/usr/bin/env python3
"""Safe application runner for one opportunity.

This file used to be a hard-coded GOVAI submission script. It filled a live
form, clicked Submit unconditionally, and wrote a synthetic
``DOM-SUB-...`` receipt even when no confirmation was observed. It now uses the
same preflight and state machine as the rest of the engine:

    python apply_govai.py MY-ECO-491 --preflight-only
    python apply_govai.py MY-ECO-491              # prepare a draft only
    python apply_govai.py MY-ECO-491 --submit     # explicit submit attempt

A submission is only reported as confirmed when the browser sees a real
confirmation reference. A clicked but unconfirmed form is recorded as
``SUBMITTED_UNCONFIRMED``.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from database import OpportunityDatabase
from engines_and_auditor import AutonomousApplicantEngine, CandidateMemoryVault, preflight_application
from paths import DB_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("opportunity_code", help="Opportunity code, e.g. MY-ECO-491")
    parser.add_argument(
        "--db-path",
        default=str(DB_PATH),
        help="SQLite database path (default: data/opportunities.db)",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Explicitly allow one Submit click. Default is draft-only.",
    )
    parser.add_argument(
        "--force-resubmit",
        action="store_true",
        help="Allow a new attempt for a record already marked submitted.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Only check the apply URL and form; do not prepare or submit.",
    )
    args = parser.parse_args()

    db = OpportunityDatabase(pathlib.Path(args.db_path))
    opp = db.get_opportunity_by_code(args.opportunity_code)
    if not opp:
        print(json.dumps({"status": "error", "message": "Opportunity not found."}, ensure_ascii=False))
        return 2

    if args.preflight_only:
        result = preflight_application(opp)
        print(
            json.dumps(
                {
                    "status": "ok" if result.ok else "blocked",
                    "opportunity_code": opp["opportunity_code"],
                    **result.summary(),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0 if result.ok else 1

    vault = CandidateMemoryVault(db)
    applicant = AutonomousApplicantEngine(db, vault)
    result = applicant.attempt_auto_application(
        opp,
        allow_submit=bool(args.submit),
        force_resubmit=bool(args.force_resubmit),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    status = result.get("application_status", "")
    if status == "APPLIED_AUTOMATICALLY":
        return 0
    if status == "SUBMITTED_UNCONFIRMED":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
