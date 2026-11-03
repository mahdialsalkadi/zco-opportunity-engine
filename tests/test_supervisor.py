#!/usr/bin/env python3
"""Phase 1 supervisor tests: log rotation and restart backoff."""

from __future__ import annotations

import pathlib
import sys

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import supervisor  # noqa: E402


def test_log_rotation_keeps_backups(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "LOG_BACKUPS", 2)
    log_file = tmp_path / "service.log"
    log_file.write_text("x" * 50, encoding="utf-8")

    assert supervisor.rotate_log(log_file, max_bytes=10) is True
    assert not log_file.exists()
    assert (tmp_path / "service.log.1").exists()

    (tmp_path / "service.log.1").write_text("old", encoding="utf-8")
    log_file.write_text("y" * 50, encoding="utf-8")
    assert supervisor.rotate_log(log_file, max_bytes=10) is True
    assert (tmp_path / "service.log.1").read_text(encoding="utf-8") == "y" * 50
    assert (tmp_path / "service.log.2").read_text(encoding="utf-8") == "old"


def test_monitor_once_restarts_dead_service(monkeypatch):
    started = {}

    def _fake_start(key, info, state):
        state.setdefault("services", {}).setdefault(key, {})["pid"] = 4242
        started[key] = True
        return {"status": "started"}

    monkeypatch.setattr(supervisor, "SERVICES", {"fake": {"name": "Fake", "log_file": pathlib.Path("/tmp/fake.log")}})
    monkeypatch.setattr(supervisor, "save_state", lambda state: None)
    monkeypatch.setattr(supervisor, "start_service", _fake_start)
    monkeypatch.setattr(supervisor, "is_pid_running", lambda pid: False)

    state = {"services": {"fake": {"pid": 999, "consecutive_failures": 2}}}
    actions = supervisor.monitor_once(state, interval_seconds=10, max_restarts=5)

    assert actions["fake"] == "started"
    assert started["fake"] is True
    assert state["services"]["fake"]["consecutive_failures"] == 3
    assert state["services"]["fake"]["next_retry_at"]


def test_monitor_gives_up_after_max_restarts(monkeypatch):
    monkeypatch.setattr(supervisor, "SERVICES", {"fake": {"name": "Fake", "log_file": pathlib.Path("/tmp/fake.log")}})
    monkeypatch.setattr(supervisor, "save_state", lambda state: None)
    monkeypatch.setattr(supervisor, "is_pid_running", lambda pid: False)

    state = {"services": {"fake": {"pid": 999, "consecutive_failures": 5}}}
    actions = supervisor.monitor_once(state, interval_seconds=10, max_restarts=5)

    assert actions["fake"] == "gave_up"
