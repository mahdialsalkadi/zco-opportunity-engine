#!/usr/bin/env python3
"""Quarantine legacy submission receipts that have no verified confirmation.

Earlier versions generated synthetic receipt IDs (``SUB-...`` / ``DOM-SUB-...``)
after clicking Submit without seeing a confirmation page. Those rows must not be
reported as confirmed applications.

Usage:
    python scripts/quarantine_unverified_submissions.py            # dry run
    python scripts/quarantine_unverified_submissions.py --apply    # mutate DB
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database import OpportunityDatabase
from paths import DB_PATH


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        default=str(DB_PATH),
        help="Path to the SQLite database",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the quarantine (default is a read-only dry run)",
    )
    args = parser.parse_args()

    db = OpportunityDatabase(pathlib.Path(args.db_path))
    rows = db.quarantine_unverified_submissions(dry_run=not args.apply)
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "count": len(rows),
                "rows": rows,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
