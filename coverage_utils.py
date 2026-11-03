#!/usr/bin/env python3
"""User-facing coverage labels that never invent a funding claim."""

from __future__ import annotations

from typing import Any, Dict, Tuple

UNKNOWN_COVERAGE_AR = "غير محدد — تحقق من الجهة قبل التقديم"


def coverage_summary(cov: Dict[str, Any] | None) -> Tuple[str, bool]:
    """Return ``(summary, is_known)`` for a financial coverage payload.

    Missing or blank summaries must stay visibly unknown. Earlier dashboard and
    bot versions printed a reassuring "100% covered" fallback even when the
    crawl never verified the funding terms.
    """
    if not isinstance(cov, dict):
        return UNKNOWN_COVERAGE_AR, False
    summary = str(cov.get("coverage_summary_ar") or "").strip()
    if not summary:
        return UNKNOWN_COVERAGE_AR, False
    return summary, True
