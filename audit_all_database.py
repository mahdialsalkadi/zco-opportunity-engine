#!/usr/bin/env python3
"""
Audit all opportunities in the database using the master ZeroCostGatekeeper
and the new Local AI Semantic Engine (Ornith 1.5 / Jev-Style on Vulkan GPU).
"""
import os
import sys
import time
import json
import sqlite3
import pathlib

# Ensure project root is in sys.path
BASE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Remove test environment variable if present
os.environ.pop("PYTEST_CURRENT_TEST", None)

import paths
from database import OpportunityDatabase, OpportunityStatus
from engines_and_auditor import (
    ZeroCostGatekeeper,
    TriJurisdictionEligibilityEngine,
    audit_opportunity_record
)

def run_full_database_ai_audit():
    db = OpportunityDatabase(paths.DB_PATH)
    gate = ZeroCostGatekeeper()
    ai_engine = TriJurisdictionEligibilityEngine()

    print(f"[*] Local AI Auditor Available: {ai_engine.is_local_llm_available()}", flush=True)

    conn = sqlite3.connect(paths.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM opportunities ORDER BY id ASC")
    all_rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    total = len(all_rows)
    print(f"[*] Total opportunities in database: {total}", flush=True)

    cost_rejected = 0
    ai_eligible = 0
    ai_ineligible = 0

    results_summary = []

    for idx, opp in enumerate(all_rows, 1):
        opp_id = opp["id"]
        code = opp.get("opportunity_code") or f"ID-{opp_id}"
        title = opp.get("title", "Untitled")

        # 1. Zero-Cost Audit Gate
        cost_res = gate.audit(opp)
        if not cost_res.is_zero_cost_compliant:
            cost_rejected += 1
            db.commit_audit_verdict(
                opportunity_id=opp_id,
                status=OpportunityStatus.REJECTED_COST,
                match_score=0,
                matched_jurisdiction_track="",
                visa_support_summary=cost_res.visa_support_summary,
                financial_coverage=cost_res.__dict__,
                rejection_reason=cost_res.rejection_reason,
            )
            print(f"[{idx}/{total}] {code} (Cost Fail): {title[:40]}... -> REJECTED_COST", flush=True)
            continue

        # 2. AI Semantic Eligibility Audit (Ornith 1.5 / Jev Local GPU)
        t_start = time.time()
        elig_res = ai_engine.evaluate(opp)
        elapsed = time.time() - t_start

        if elig_res.is_eligible:
            ai_eligible += 1
            # If it was APPLICATION_FAILED, preserve review/ready state
            new_status = OpportunityStatus.READY_FOR_REVIEW
            db.commit_audit_verdict(
                opportunity_id=opp_id,
                status=new_status,
                match_score=elig_res.match_score,
                matched_jurisdiction_track=elig_res.matched_jurisdiction_track,
                visa_support_summary=cost_res.visa_support_summary,
                financial_coverage=cost_res.__dict__,
                rejection_reason="",
                audit_notes=elig_res.audit_notes,
            )
            print(f"[{idx}/{total}] {code} (AI Eligible {elig_res.match_score}% - {elapsed:.1f}s): {title[:40]}... -> READY_FOR_REVIEW", flush=True)
            results_summary.append({
                "code": code,
                "title": title,
                "status": "ELIGIBLE",
                "score": elig_res.match_score,
                "track": elig_res.matched_jurisdiction_track,
                "notes": elig_res.audit_notes
            })
        else:
            ai_ineligible += 1
            db.commit_audit_verdict(
                opportunity_id=opp_id,
                status=OpportunityStatus.REJECTED_INELIGIBLE,
                match_score=0,
                matched_jurisdiction_track="",
                visa_support_summary=cost_res.visa_support_summary,
                financial_coverage=cost_res.__dict__,
                rejection_reason=elig_res.rejection_reason,
                audit_notes=elig_res.audit_notes,
            )
            print(f"[{idx}/{total}] {code} (AI Ineligible - {elapsed:.1f}s): {title[:40]}... -> REJECTED_INELIGIBLE ({elig_res.rejection_reason[:50]})", flush=True)
            results_summary.append({
                "code": code,
                "title": title,
                "status": "INELIGIBLE",
                "reason": elig_res.rejection_reason,
                "notes": elig_res.audit_notes
            })

    print("\n" + "="*60, flush=True)
    print(f"[*] AUDIT COMPLETE:", flush=True)
    print(f"    - Total Processed: {total}", flush=True)
    print(f"    - Cost Rejected (Non Zero-Cost): {cost_rejected}", flush=True)
    print(f"    - AI Semantic Ineligible: {ai_ineligible}", flush=True)
    print(f"    - AI Semantic Eligible (Ready for Review): {ai_eligible}", flush=True)
    print("="*60 + "\n", flush=True)

    # Re-render dashboard
    from server import ZCOEngineController
    ctrl = ZCOEngineController(paths.DB_PATH)
    dash = ctrl.render_categorized_dashboard()
    print(f"[*] Updated Dashboard rendered at: {dash}", flush=True)

if __name__ == "__main__":
    run_full_database_ai_audit()
