#!/usr/bin/env python3
"""
ZCO-Engine v4.0 — Master Service Supervisor & Background Daemon Manager (`supervisor.py`)
========================================================================================
Controls and monitors all 24/7 background components:
1. `crawler`: 24/7 AsyncOpportunityCrawler daemon (polls 7 sources every 20 mins)
2. `telegram_bot`: @Uiii007bot interactive Telegram Bot with Approval/Decline buttons
3. `auditor`: 6-hour batch audit & auto-applicant background scheduler

Commands:
  python3 supervisor.py --start       # Starts all daemons in the background
  python3 supervisor.py --status      # Checks health, PIDs, and uptime of all services
  python3 supervisor.py --stop        # Gracefully stops all daemons
  python3 supervisor.py --restart     # Restarts all daemons
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
from typing import Any, Dict, Optional

_VENV_PYTHON = pathlib.Path(__file__).resolve().parent / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and pathlib.Path(sys.executable).resolve() != _VENV_PYTHON.resolve():
    if "-c" not in sys.argv:
        os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON)] + sys.argv)

BASE_DIR = pathlib.Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = BASE_DIR / "data" / "supervisor_state.json"

# Load environment configuration
def _load_local_env() -> None:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass

_load_local_env()

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = os.environ.get("PORT", "8080")

SERVICES: Dict[str, Dict[str, Any]] = {
    "crawler": {
        "name": "24/7 Async Opportunity Crawler",
        "command": [str(_VENV_PYTHON), str(BASE_DIR / "async_crawler.py"), "--daemon", "--poll-interval-minutes", "20"],
        "log_file": LOG_DIR / "crawler_daemon.log",
    },
    "batch_auditor": {
        "name": "6-Hour Periodic Opportunity Auditor Daemon",
        "command": [str(_VENV_PYTHON), str(BASE_DIR / "server.py"), "--daemon-auditor", "--interval-hours", "6"],
        "log_file": LOG_DIR / "batch_auditor.log",
    },
    "telegram_bot": {
        "name": "ZCO Interactive Telegram Approval Bot (@Uiii007bot)",
        "command": [str(_VENV_PYTHON), str(BASE_DIR / "telegram_bot.py")],
        "log_file": LOG_DIR / "telegram_bot.log",
    },
    "web_dashboard": {
        "name": f"ZCO Web Dashboard (http://{HOST}:{PORT})",
        "command": [str(_VENV_PYTHON), str(BASE_DIR / "web_dashboard.py"), "--host", HOST, "--port", PORT],
        "log_file": LOG_DIR / "web_dashboard.log",
    },
}


def load_state() -> Dict[str, Any]:
    if PID_FILE.exists():
        try:
            return json.loads(PID_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"services": {}}


def save_state(state: Dict[str, Any]) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def start_service(svc_key: str, svc_info: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    current_pid = state.get("services", {}).get(svc_key, {}).get("pid")
    if current_pid and is_pid_running(current_pid):
        return {
            "status": "already_running",
            "pid": current_pid,
            "name": svc_info["name"],
        }

    log_path = svc_info["log_file"]
    log_fd = open(log_path, "a", encoding="utf-8")

    proc = subprocess.Popen(
        svc_info["command"],
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        cwd=str(BASE_DIR),
        start_new_session=True,
    )

    svc_state = {
        "pid": proc.pid,
        "name": svc_info["name"],
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "log_file": str(log_path),
    }
    state.setdefault("services", {})[svc_key] = svc_state
    save_state(state)
    return {"status": "started", "pid": proc.pid, "name": svc_info["name"]}


def stop_service(svc_key: str, state: Dict[str, Any]) -> Dict[str, Any]:
    svc_data = state.get("services", {}).get(svc_key, {})
    pid = svc_data.get("pid")
    if not pid or not is_pid_running(pid):
        state.get("services", {}).pop(svc_key, None)
        save_state(state)
        return {"status": "not_running", "pid": pid}

    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(25):
            time.sleep(0.1)
            if not is_pid_running(pid):
                break
        if is_pid_running(pid):
            os.kill(pid, signal.SIGKILL)
    except Exception as exc:
        pass

    state.get("services", {}).pop(svc_key, None)
    save_state(state)
    return {"status": "stopped", "pid": pid}


def get_all_status() -> Dict[str, Any]:
    state = load_state()
    statuses: Dict[str, Any] = {}
    for key, info in SERVICES.items():
        svc_data = state.get("services", {}).get(key, {})
        pid = svc_data.get("pid")
        running = pid is not None and is_pid_running(pid)
        statuses[key] = {
            "name": info["name"],
            "running": running,
            "pid": pid if running else None,
            "started_at": svc_data.get("started_at") if running else None,
            "log_file": str(info["log_file"]),
        }
    return {
        "supervisor_active": any(s["running"] for s in statuses.values()),
        "services": statuses,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ZCO-Engine v4.0 Daemon Supervisor")
    parser.add_argument("--start", action="store_true", help="Start all daemons")
    parser.add_argument("--stop", action="store_true", help="Stop all daemons")
    parser.add_argument("--restart", action="store_true", help="Restart all daemons")
    parser.add_argument("--status", action="store_true", help="Check status of all daemons")
    args = parser.parse_args()

    state = load_state()

    if args.stop or args.restart:
        for key in list(SERVICES.keys()):
            res = stop_service(key, state)
            print(f"[{key}] {res['status']} (PID: {res.get('pid')})")

    if args.start or args.restart:
        for key, info in SERVICES.items():
            res = start_service(key, info, state)
            print(f"[{key}] {res['status']} (PID: {res.get('pid')}) - {res['name']}")

    if args.status or (not args.start and not args.stop and not args.restart):
        print(json.dumps(get_all_status(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
