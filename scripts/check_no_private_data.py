#!/usr/bin/env python3
"""Fail CI when private runtime data or obvious secrets are tracked by git."""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

FORBIDDEN_PARTS = {
    "config/candidate_profile.json",
    "config/master_profile.yaml",
    "config/comprehensive_portfolio.json",
    "data/dashboard_token.txt",
    "verified_opportunities_matrix.md",
}
FORBIDDEN_PREFIXES = (
    "config/private/",
    "data/dashboards/",
    "data/documents/",
    "data/screenshots/",
    "data/logs/",
)
FORBIDDEN_SUFFIXES = (".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".log")

SECRET_PATTERNS = (
    ("telegram bot token", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)


def tracked_files() -> list[pathlib.Path]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=BASE_DIR, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [BASE_DIR / item.decode("utf-8") for item in output.split(b"\0") if item]


def path_violation(rel_path: str) -> str:
    if rel_path in FORBIDDEN_PARTS:
        return "private runtime file is tracked"
    if rel_path.startswith(FORBIDDEN_PREFIXES) and not rel_path.endswith(".gitkeep"):
        return "private runtime directory is tracked"
    if rel_path.endswith(FORBIDDEN_SUFFIXES):
        return "database/log artifact is tracked"
    return ""


def main() -> int:
    failures: list[str] = []
    for path in tracked_files():
        rel_path = path.relative_to(BASE_DIR).as_posix()
        violation = path_violation(rel_path)
        if violation:
            failures.append(f"{rel_path}: {violation}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"{rel_path}: possible {label}")

    if failures:
        print("Private data check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("Private data check passed: tracked files contain no known private runtime data or secrets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
