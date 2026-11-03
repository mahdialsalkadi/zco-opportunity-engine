#!/usr/bin/env python3
"""
ZCO-Engine v3.0 — SQLite Concurrent State Machine & Persistent Memory Vault Layer
=================================================================================
Manages concurrent read/write operations between:
1. The 24/7 background `async_crawler.py` Sidecar daemon (`RAW_INGESTED`).
2. The 6-hour scheduled Antigravity Agent auditor (`VERIFIED_ELIGIBLE` | `REJECTED_*`).
3. The Autonomous Application & Self-Learning Memory Vault Engine (`auto_applicant.py`):
   - Prepares applications and marks them `READY_FOR_REVIEW` by default. Only an
     explicit human approval (or `ZCO_AUTO_SUBMIT=1`) may click Submit.
   - Marks `APPLIED_AUTOMATICALLY` only when a real confirmation reference exists;
     clicked-but-unconfirmed submissions become `SUBMITTED_UNCONFIRMED`.
   - Temporarily pauses at `PAUSED_NEEDS_USER_INPUT` when new fields are encountered.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional


class OpportunityStatus:
    RAW_INGESTED = "RAW_INGESTED"
    AUDITING_IN_PROGRESS = "AUDITING_IN_PROGRESS"
    VERIFIED_ELIGIBLE = "VERIFIED_ELIGIBLE"
    PAUSED_NEEDS_USER_INPUT = "PAUSED_NEEDS_USER_INPUT"
    PAUSED_AT_CAPTCHA = "PAUSED_AT_CAPTCHA"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    SUBMITTED_UNCONFIRMED = "SUBMITTED_UNCONFIRMED"
    APPLIED_AUTOMATICALLY = "APPLIED_AUTOMATICALLY"
    APPLICATION_FAILED = "APPLICATION_FAILED"
    REJECTED_COST = "REJECTED_COST"
    REJECTED_INELIGIBLE = "REJECTED_INELIGIBLE"
    SHORTLISTED_BY_USER = "SHORTLISTED_BY_USER"
    DECLINED_BY_USER = "DECLINED_BY_USER"


@dataclass
class RawOpportunityRecord:
    title: str
    organizer: str
    source_url: str
    apply_url: str
    location_country: str
    location_city: str
    is_inside_malaysia: bool
    track_category: str
    raw_description: str
    raw_terms_text: str
    deadline_iso: str
    source_feed_id: str
    required_form_fields: Optional[List[str]] = None


class OpportunityDatabase:
    """Thread-safe and multiprocess-safe SQLite database with WAL + FUSE/Cloud VFS fallback."""

    def __init__(self, db_path: str | pathlib.Path) -> None:
        self.db_path = pathlib.Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._use_unix_none_vfs = False
        self._probe_filesystem_locking()
        self._initialize_schema()

    def _probe_filesystem_locking(self) -> None:
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("CREATE TABLE IF NOT EXISTS _probe (id INT);")
            conn.close()
        except sqlite3.OperationalError:
            self._use_unix_none_vfs = True

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        if self._use_unix_none_vfs:
            uri = f"file:{self.db_path}?vfs=unix-none"
            conn = sqlite3.connect(uri, uri=True, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=MEMORY;")
            conn.execute("PRAGMA synchronous=OFF;")
        else:
            conn = sqlite3.connect(str(self.db_path), timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")

        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opportunity_code TEXT UNIQUE,
                    fingerprint_sha256 TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    organizer TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    apply_url TEXT NOT NULL,
                    location_country TEXT NOT NULL,
                    location_city TEXT NOT NULL,
                    is_inside_malaysia INTEGER NOT NULL DEFAULT 0,
                    track_category TEXT NOT NULL,
                    raw_description TEXT NOT NULL,
                    raw_terms_text TEXT NOT NULL DEFAULT '',
                    deadline_iso TEXT NOT NULL,
                    source_feed_id TEXT NOT NULL,
                    required_form_fields_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'RAW_INGESTED',
                    ingested_at TEXT NOT NULL,
                    audited_at TEXT,
                    applied_at TEXT,
                    match_score INTEGER DEFAULT 0,
                    matched_jurisdiction_track TEXT DEFAULT '',
                    visa_support_summary TEXT DEFAULT '',
                    financial_coverage_json TEXT DEFAULT '{}',
                    missing_fields_json TEXT DEFAULT '[]',
                    submission_receipt_json TEXT DEFAULT '{}',
                    rejection_reason TEXT DEFAULT '',
                    audit_notes TEXT DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_opp_status_ingested
                    ON opportunities(status, ingested_at);

                CREATE INDEX IF NOT EXISTS idx_opp_location_track
                    ON opportunities(is_inside_malaysia, track_category, match_score DESC);

                CREATE TABLE IF NOT EXISTS crawler_heartbeats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_started_at TEXT NOT NULL,
                    cycle_finished_at TEXT NOT NULL,
                    sources_polled INTEGER NOT NULL,
                    new_items_ingested INTEGER NOT NULL,
                    duplicates_skipped INTEGER NOT NULL,
                    errors_count INTEGER NOT NULL DEFAULT 0,
                    notes TEXT DEFAULT ''
                );

                -- Persistent Self-Learning Candidate Memory Vault (Structured Fields & Files)
                CREATE TABLE IF NOT EXISTS candidate_vault (
                    field_key TEXT PRIMARY KEY,
                    field_label_ar TEXT NOT NULL,
                    field_value TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    source TEXT NOT NULL DEFAULT 'initial_profile',
                    updated_at TEXT NOT NULL
                );

                -- Persistent Learned Essay & Short-Answer Bank (Semantic Topic Reuse)
                CREATE TABLE IF NOT EXISTS learned_qa_bank (
                    question_key TEXT PRIMARY KEY,
                    question_prompt_ar TEXT NOT NULL,
                    answer_text TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    times_reused INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );

                -- Full Audit Log of Autonomous Submissions & Paused Drafts
                CREATE TABLE IF NOT EXISTS application_submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opportunity_id INTEGER NOT NULL,
                    opportunity_code TEXT NOT NULL,
                    submission_status TEXT NOT NULL,
                    filled_payload_json TEXT NOT NULL,
                    missing_fields_json TEXT NOT NULL DEFAULT '[]',
                    confirmation_ref TEXT DEFAULT '',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
                );

                -- Telegram Bot Subscribers & Interactive Approval Tracking
                CREATE TABLE IF NOT EXISTS telegram_subscribers (
                    chat_id INTEGER PRIMARY KEY,
                    username TEXT DEFAULT '',
                    first_name TEXT DEFAULT '',
                    registered_at TEXT NOT NULL,
                    notifications_enabled INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS telegram_notifications_sent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opportunity_code TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    sent_at TEXT NOT NULL,
                    message_id INTEGER,
                    UNIQUE(opportunity_code, chat_id)
                );
                """
            )

    @staticmethod
    def compute_fingerprint(title: str, apply_url: str, deadline_iso: str) -> str:
        normalized = f"{title.strip().lower()}|{apply_url.strip().lower()}|{deadline_iso.strip()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def ingest_raw_opportunity(self, record: RawOpportunityRecord) -> Optional[int]:
        fingerprint = self.compute_fingerprint(
            record.title, record.apply_url, record.deadline_iso
        )
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        req_fields_json = json.dumps(record.required_form_fields or [], ensure_ascii=False)

        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO opportunities (
                    fingerprint_sha256, title, organizer, source_url, apply_url,
                    location_country, location_city, is_inside_malaysia,
                    track_category, raw_description, raw_terms_text,
                    deadline_iso, source_feed_id, required_form_fields_json,
                    status, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fingerprint,
                    record.title,
                    record.organizer,
                    record.source_url,
                    record.apply_url,
                    record.location_country,
                    record.location_city,
                    1 if record.is_inside_malaysia else 0,
                    record.track_category,
                    record.raw_description,
                    record.raw_terms_text,
                    record.deadline_iso,
                    record.source_feed_id,
                    req_fields_json,
                    OpportunityStatus.RAW_INGESTED,
                    now_iso,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row_id = cursor.lastrowid
            prefix = "MY" if record.is_inside_malaysia else "INT"
            track_short = self._track_short_code(record.track_category)
            opp_code = f"{prefix}-{track_short}-{row_id:03d}"
            conn.execute(
                "UPDATE opportunities SET opportunity_code = ? WHERE id = ?",
                (opp_code, row_id),
            )
            return row_id

    @staticmethod
    def _track_short_code(track_category: str) -> str:
        mapping = {
            "NATURE_ECO_CONSERVATION": "ECO",
            "GREEN_AI_CLIMATE_TECH": "GAI",
            "CORE_AI_HACKATHONS": "AI",
            "OUTDOOR_LEADERSHIP_CAMPS": "OUT",
            "COMMUNITY_VOLUNTEERING_EXCHANGE": "VOL",
            "MENA_GCC_ASEAN_SPECIAL": "REG",
        }
        return mapping.get(track_category, "GEN")

    def fetch_unprocessed_batch(
        self, window_hours: float = 6.0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        now = dt.datetime.now(dt.timezone.utc)
        cutoff = (now - dt.timedelta(hours=window_hours)).isoformat()
        stale_cutoff = (now - dt.timedelta(hours=2)).isoformat()
        with self.connect() as conn:
            # Recover jobs stuck in AUDITING_IN_PROGRESS after a crash or hang.
            conn.execute(
                """
                UPDATE opportunities
                SET status = ?
                WHERE status = ?
                  AND (audited_at IS NULL OR audited_at < ?)
                """,
                (
                    OpportunityStatus.RAW_INGESTED,
                    OpportunityStatus.AUDITING_IN_PROGRESS,
                    stale_cutoff,
                ),
            )
            rows = conn.execute(
                """
                SELECT * FROM opportunities
                WHERE status = ?
                  AND ingested_at >= ?
                ORDER BY ingested_at DESC
                LIMIT ?
                """,
                (OpportunityStatus.RAW_INGESTED, cutoff, limit),
            ).fetchall()

            if len(rows) < limit:
                remaining = limit - len(rows)
                existing_ids = {r["id"] for r in rows}
                older_rows = conn.execute(
                    """
                    SELECT * FROM opportunities
                    WHERE status = ?
                    ORDER BY ingested_at ASC
                    LIMIT ?
                    """,
                    (OpportunityStatus.RAW_INGESTED, remaining),
                ).fetchall()
                for r in older_rows:
                    if r["id"] not in existing_ids:
                        rows.append(r)

            results = [dict(r) for r in rows]
            if results:
                ids = [r["id"] for r in results]
                placeholders = ",".join("?" for _ in ids)
                conn.execute(
                    f"UPDATE opportunities SET status = ?, audited_at = ? WHERE id IN ({placeholders})",
                    [OpportunityStatus.AUDITING_IN_PROGRESS, now.isoformat(), *ids],
                )
            return results

    def commit_audit_verdict(
        self,
        opportunity_id: int,
        status: str,
        match_score: int,
        matched_jurisdiction_track: str,
        visa_support_summary: str,
        financial_coverage: Dict[str, Any],
        rejection_reason: str = "",
        audit_notes: str = "",
    ) -> None:
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE opportunities
                SET status = ?,
                    audited_at = ?,
                    match_score = ?,
                    matched_jurisdiction_track = ?,
                    visa_support_summary = ?,
                    financial_coverage_json = ?,
                    rejection_reason = ?,
                    audit_notes = ?
                WHERE id = ?
                """,
                (
                    status,
                    now_iso,
                    match_score,
                    matched_jurisdiction_track,
                    visa_support_summary,
                    json.dumps(financial_coverage, ensure_ascii=False),
                    rejection_reason,
                    audit_notes,
                    opportunity_id,
                ),
            )

    def record_application_attempt(
        self,
        opportunity_id: int,
        opportunity_code: str,
        new_status: str,
        filled_payload: Dict[str, Any],
        missing_fields: List[Dict[str, str]],
        confirmation_ref: str = "",
        notes: str = "",
    ) -> None:
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        applied_at = now_iso if new_status == OpportunityStatus.APPLIED_AUTOMATICALLY else None
        receipt_obj = {
            "confirmation_ref": confirmation_ref,
            "applied_at": applied_at,
            "filled_fields_count": len(filled_payload),
            "verification_status": new_status,
            "notes": notes,
            "pre_submit_screenshot_path": filled_payload.get("pre_submit_screenshot", ""),
            "post_submit_screenshot_path": filled_payload.get("post_submit_screenshot", ""),
        }
        with self.connect() as conn:
            existing_row = conn.execute(
                "SELECT submission_receipt_json FROM opportunities WHERE id = ?",
                (opportunity_id,),
            ).fetchone()
            try:
                previous_receipt = json.loads(
                    (existing_row["submission_receipt_json"] if existing_row else "") or "{}"
                )
            except (TypeError, ValueError):
                previous_receipt = {}
            previous_ref = str(previous_receipt.get("confirmation_ref") or "").strip()
            if previous_ref and not confirmation_ref:
                receipt_obj["previous_confirmation_ref"] = previous_ref
                receipt_obj["previous_verification_status"] = previous_receipt.get(
                    "verification_status", ""
                )
            conn.execute(
                """
                UPDATE opportunities
                SET status = ?,
                    applied_at = COALESCE(?, applied_at),
                    missing_fields_json = ?,
                    submission_receipt_json = ?
                WHERE id = ?
                """,
                (
                    new_status,
                    applied_at,
                    json.dumps(missing_fields, ensure_ascii=False),
                    json.dumps(receipt_obj, ensure_ascii=False),
                    opportunity_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO application_submissions (
                    opportunity_id, opportunity_code, submission_status,
                    filled_payload_json, missing_fields_json, confirmation_ref, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    opportunity_id,
                    opportunity_code,
                    new_status,
                    json.dumps(filled_payload, ensure_ascii=False),
                    json.dumps(missing_fields, ensure_ascii=False),
                    confirmation_ref,
                    now_iso,
                ),
            )

    def quarantine_unverified_submissions(self, dry_run: bool = False) -> List[Dict[str, Any]]:
        """Downgrade legacy synthetic/unverified 'applied' rows to SUBMITTED_UNCONFIRMED.

        Earlier versions generated receipt codes like ``SUB-...`` / ``DOM-SUB-...``
        even when no confirmation page was observed, and local testbed fixtures could
        carry a realistic-looking reference. Those rows must not be shown as confirmed
        applications.
        """
        quarantined: List[Dict[str, Any]] = []
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, opportunity_code, source_feed_id, apply_url, "
                "submission_receipt_json FROM opportunities "
                "WHERE status = ?",
                (OpportunityStatus.APPLIED_AUTOMATICALLY,),
            ).fetchall()
            for row in rows:
                try:
                    receipt = json.loads(row["submission_receipt_json"] or "{}")
                except (TypeError, ValueError):
                    receipt = {}
                ref = str(receipt.get("confirmation_ref") or "").strip()
                is_local_testbed = (
                    str(row["source_feed_id"] or "") == "local_testbed_portal"
                    or str(row["apply_url"] or "").startswith("file://")
                )
                is_synthetic = (
                    is_local_testbed
                    or not ref
                    or ref.startswith("SUB-")
                    or ref.startswith("DOM-SUB-")
                )
                if not is_synthetic:
                    continue
                receipt["confirmation_ref"] = ""
                receipt["verification_status"] = OpportunityStatus.SUBMITTED_UNCONFIRMED
                receipt["notes"] = (
                    "Demo/testbed submission is not a real application."
                    if is_local_testbed
                    else "Legacy submission receipt was synthetic or missing a verified "
                    "confirmation reference; marked as unconfirmed."
                )
                if not dry_run:
                    conn.execute(
                        "UPDATE opportunities SET status = ?, submission_receipt_json = ?, "
                        "rejection_reason = ? WHERE id = ?",
                        (
                            OpportunityStatus.SUBMITTED_UNCONFIRMED,
                            json.dumps(receipt, ensure_ascii=False),
                            "بانتظار تأكيد رسمي من الجهة المنظمة (إيصال قديم غير موثّق)",
                            row["id"],
                        ),
                    )
                quarantined.append(
                    {
                        "id": row["id"],
                        "opportunity_code": row["opportunity_code"],
                        "old_reference": ref,
                    }
                )
            if not dry_run:
                # Keep the audit history consistent with the downgraded opportunity rows.
                conn.execute(
                    """
                    UPDATE application_submissions
                    SET submission_status = ?, confirmation_ref = ''
                    WHERE submission_status = ?
                      AND (
                        confirmation_ref = ''
                        OR confirmation_ref LIKE 'SUB-%'
                        OR confirmation_ref LIKE 'DOM-SUB-%'
                        OR opportunity_id IN (
                            SELECT id FROM opportunities
                            WHERE source_feed_id = 'local_testbed_portal'
                               OR apply_url LIKE 'file://%'
                        )
                      )
                    """,
                    (
                        OpportunityStatus.SUBMITTED_UNCONFIRMED,
                        OpportunityStatus.APPLIED_AUTOMATICALLY,
                    ),
                )
        return quarantined

    def get_verified_opportunities(
        self,
        is_inside_malaysia: Optional[bool] = None,
        track_category: Optional[str] = None,
        min_score: int = 0,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT * FROM opportunities
            WHERE status IN (?, ?, ?, ?, ?, ?, ?, ?)
              AND match_score >= ?
        """
        params: List[Any] = [
            OpportunityStatus.VERIFIED_ELIGIBLE,
            OpportunityStatus.PAUSED_NEEDS_USER_INPUT,
            OpportunityStatus.PAUSED_AT_CAPTCHA,
            OpportunityStatus.READY_FOR_REVIEW,
            OpportunityStatus.SUBMITTED_UNCONFIRMED,
            OpportunityStatus.APPLIED_AUTOMATICALLY,
            OpportunityStatus.APPLICATION_FAILED,
            OpportunityStatus.SHORTLISTED_BY_USER,
            min_score,
        ]
        if is_inside_malaysia is not None:
            query += " AND is_inside_malaysia = ?"
            params.append(1 if is_inside_malaysia else 0)
        if track_category:
            query += " AND track_category = ?"
            params.append(track_category)

        query += " ORDER BY is_inside_malaysia DESC, track_category ASC, match_score DESC, deadline_iso ASC"
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_opportunities_by_status(self, status: str) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM opportunities WHERE status = ? ORDER BY match_score DESC",
                (status,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_opportunity_by_code(self, opportunity_code: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM opportunities WHERE UPPER(opportunity_code) = UPPER(?)",
                (opportunity_code.strip(),),
            ).fetchone()
            return dict(row) if row else None

    # --- Vault Operations ---

    def upsert_vault_field(
        self,
        field_key: str,
        field_value: str,
        field_label_ar: str = "",
        category: str = "learned_from_user",
        source: str = "user_interactive_input",
    ) -> None:
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO candidate_vault (field_key, field_label_ar, field_value, category, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(field_key) DO UPDATE SET
                    field_value = excluded.field_value,
                    field_label_ar = COALESCE(NULLIF(excluded.field_label_ar, ''), candidate_vault.field_label_ar),
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (field_key.strip().lower(), field_label_ar or field_key, str(field_value).strip(), category, source, now_iso),
            )

    def get_all_vault_fields(self) -> Dict[str, Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM candidate_vault ORDER BY field_key ASC").fetchall()
            return {r["field_key"]: dict(r) for r in rows}

    def upsert_learned_qa(
        self,
        question_key: str,
        question_prompt_ar: str,
        answer_text: str,
        tags: Optional[List[str]] = None,
    ) -> None:
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO learned_qa_bank (question_key, question_prompt_ar, answer_text, tags_json, times_reused, updated_at)
                VALUES (?, ?, ?, ?, 0, ?)
                ON CONFLICT(question_key) DO UPDATE SET
                    answer_text = excluded.answer_text,
                    updated_at = excluded.updated_at
                """,
                (
                    question_key.strip().lower(),
                    question_prompt_ar,
                    answer_text.strip(),
                    json.dumps(tags or [], ensure_ascii=False),
                    now_iso,
                ),
            )

    def get_all_learned_qa(self) -> Dict[str, Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM learned_qa_bank").fetchall()
            return {r["question_key"]: dict(r) for r in rows}

    def increment_qa_reuse(self, question_key: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE learned_qa_bank SET times_reused = times_reused + 1 WHERE question_key = ?",
                (question_key,),
            )

    def record_crawler_heartbeat(
        self,
        started_at: str,
        finished_at: str,
        sources_polled: int,
        new_items: int,
        duplicates: int,
        errors: int = 0,
        notes: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO crawler_heartbeats (
                    cycle_started_at, cycle_finished_at, sources_polled,
                    new_items_ingested, duplicates_skipped, errors_count, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (started_at, finished_at, sources_polled, new_items, duplicates, errors, notes),
            )

    def get_daemon_status_summary(self) -> Dict[str, Any]:
        with self.connect() as conn:
            last_hb = conn.execute(
                "SELECT * FROM crawler_heartbeats ORDER BY id DESC LIMIT 1"
            ).fetchone()
            counts = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM opportunities
                GROUP BY status
                """
            ).fetchall()
            vault_count = conn.execute("SELECT COUNT(*) as c FROM candidate_vault").fetchone()["c"]
            qa_count = conn.execute("SELECT COUNT(*) as c FROM learned_qa_bank").fetchone()["c"]
            status_map = {r["status"]: r["count"] for r in counts}
            return {
                "database_path": str(self.db_path),
                "vfs_mode": "unix-none (cloud/FUSE safe)" if self._use_unix_none_vfs else "WAL (native POSIX)",
                "last_heartbeat": dict(last_hb) if last_hb else None,
                "queue_counts": status_map,
                "total_tracked": sum(status_map.values()),
                "vault_stored_fields_count": vault_count,
                "learned_qa_count": qa_count,
            }

    def register_telegram_subscriber(
        self, chat_id: int, username: str = "", first_name: str = ""
    ) -> None:
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO telegram_subscribers (chat_id, username, first_name, registered_at, notifications_enabled)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(chat_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    notifications_enabled = 1
                """,
                (chat_id, username, first_name, now_iso),
            )

    def get_telegram_subscribers(self) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM telegram_subscribers WHERE notifications_enabled = 1"
            ).fetchall()
            return [dict(r) for r in rows]

    def record_telegram_notification(
        self, opportunity_code: str, chat_id: int, message_id: Optional[int] = None
    ) -> bool:
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        with self.connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO telegram_notifications_sent (opportunity_code, chat_id, sent_at, message_id)
                    VALUES (?, ?, ?, ?)
                    """,
                    (opportunity_code, chat_id, now_iso, message_id),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def get_unnotified_opportunities_for_chat(self, chat_id: int) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM opportunities
                WHERE status IN ('VERIFIED_ELIGIBLE', 'PAUSED_NEEDS_USER_INPUT')
                  AND opportunity_code NOT IN (
                      SELECT opportunity_code FROM telegram_notifications_sent WHERE chat_id = ?
                  )
                ORDER BY match_score DESC, id ASC
                """,
                (chat_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_opportunity_status(
        self, opportunity_code: str, new_status: str, rejection_reason: str = ""
    ) -> bool:
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE opportunities
                SET status = ?,
                    audited_at = ?,
                    rejection_reason = CASE WHEN ? != '' THEN ? ELSE rejection_reason END
                WHERE opportunity_code = ?
                """,
                (new_status, now_iso, rejection_reason, rejection_reason, opportunity_code),
            )
            return cur.rowcount > 0