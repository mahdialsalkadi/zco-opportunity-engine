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
  python3 supervisor.py --status      # Checks health, PIDs, restart counts, and uptime
  python3 supervisor.py --stop        # Gracefully stops all daemons
  python3 supervisor.py --restart     # Restarts all daemons
  python3 supervisor.py --monitor     # Foreground health loop with restart backoff & log rotation
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

from file_utils import atomic_write_json
from paths import LOG_DIR, SUPERVISOR_STATE_FILE

BASE_DIR = pathlib.Path(__file__).resolve().parent
LOG_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = SUPERVISOR_STATE_FILE
MAX_LOG_BYTES = int(os.environ.get("ZCO_LOG_MAX_BYTES", str(10 * 1024 * 1024)))
LOG_BACKUPS = int(os.environ.get("ZCO_LOG_BACKUPS", "3"))
MAX_RESTARTS = int(os.environ.get("ZCO_MAX_RESTARTS", "5"))

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

import shutil

if shutil.which("obscura"):
    SERVICES["obscura"] = {
        "name": "Obscura Headless Browser CDP Server (:9222)",
        "command": [
            shutil.which("obscura") or "obscura",
            "serve",
            "--port",
            "9222",
            "--stealth",
            "--allow-private-network",
        ],
        "log_file": LOG_DIR / "obscura_cdp.log",
    }

_ORNITH_PATH = pathlib.Path(os.environ.get("ORNITH_MODEL_PATH", "/home/mahdi/Downloads/Ornith-1.5-9B-Q4_K_M.gguf"))
_JEV_PATH = pathlib.Path(os.environ.get("JEV_MODEL_PATH", "/home/mahdi/models/Jev-Style-Qwen3.5-2B-Decision-Q8_0.gguf"))
_LLAMA_SERVER = shutil.which("llama-server") or "/usr/bin/llama-server"

if pathlib.Path(_LLAMA_SERVER).exists():
    if _ORNITH_PATH.exists():
        SERVICES["ornith_llm"] = {
            "name": "Local Ornith 1.5 9B LLM (:11434 on Vulkan GPU)",
            "command": [
                _LLAMA_SERVER,
                "-m",
                str(_ORNITH_PATH),
                "-ngl",
                "99",
                "--port",
                "11434",
                "-c",
                "4096",
                "--threads",
                "4",
                "--alias",
                "ornith-1.5",
            ],
            "log_file": LOG_DIR / "ornith_llm.log",
        }
    if _JEV_PATH.exists():
        SERVICES["jev_classifier"] = {
            "name": "Local Jev-Style 2B Classifier (:11435 on Vulkan GPU)",
            "command": [
                _LLAMA_SERVER,
                "-m",
                str(_JEV_PATH),
                "-ngl",
                "99",
                "--port",
                "11435",
                "-c",
                "2048",
                "--threads",
                "4",
                "--alias",
                "jev-decision",
            ],
            "log_file": LOG_DIR / "jev_classifier.log",
        }


def load_state() -> Dict[str, Any]:
    if PID_FILE.exists():
        try:
            return json.loads(PID_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"services": {}}


def save_state(state: Dict[str, Any]) -> None:
    atomic_write_json(PID_FILE, state)


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def rotate_log(log_path: pathlib.Path, max_bytes: int = MAX_LOG_BYTES) -> bool:
    """Rotate a log file once it exceeds ``max_bytes``, keeping ``LOG_BACKUPS`` files."""
    try:
        if not log_path.exists() or log_path.stat().st_size < max_bytes:
            return False
        for index in range(LOG_BACKUPS - 1, 0, -1):
            src = pathlib.Path(f"{log_path}.{index}")
            dst = pathlib.Path(f"{log_path}.{index + 1}")
            if src.exists():
                os.replace(src, dst)
        os.replace(log_path, pathlib.Path(f"{log_path}.1"))
        return True
    except OSError as exc:
        print(f"[log-rotation] failed for {log_path}: {exc}", file=sys.stderr)
        return False


def start_service(svc_key: str, svc_info: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    previous_state = state.get("services", {}).get(svc_key, {})
    current_pid = previous_state.get("pid")
    if current_pid and is_pid_running(current_pid):
        return {
            "status": "already_running",
            "pid": current_pid,
            "name": svc_info["name"],
        }

    log_path = svc_info["log_file"]
    rotate_log(log_path)
    log_fd = open(log_path, "a", encoding="utf-8")

    env_vars = {**os.environ, "PYTHONUNBUFFERED": "1"}

    proc = subprocess.Popen(
        svc_info["command"],
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        cwd=str(BASE_DIR),
        env=env_vars,
        start_new_session=True,
    )

    restart_count = int(previous_state.get("restart_count", 0))
    if previous_state.get("pid"):
        restart_count += 1
    svc_state = {
        "pid": proc.pid,
        "name": svc_info["name"],
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "log_file": str(log_path),
        "restart_count": restart_count,
        "consecutive_failures": 0,
        "next_retry_at": None,
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


def monitor_once(
    state: Dict[str, Any],
    interval_seconds: float = 30.0,
    max_restarts: int = MAX_RESTARTS,
) -> Dict[str, str]:
    """Check all services once and restart dead ones with capped backoff."""
    now = dt.datetime.now(dt.timezone.utc)
    actions: Dict[str, str] = {}
    for key, info in SERVICES.items():
        svc_data = state.setdefault("services", {}).setdefault(key, {})
        pid = svc_data.get("pid")
        if pid and is_pid_running(pid):
            svc_data["consecutive_failures"] = 0
            svc_data["next_retry_at"] = None
            actions[key] = "running"
            continue

        failures = int(svc_data.get("consecutive_failures", 0))
        next_retry_raw = svc_data.get("next_retry_at")
        if next_retry_raw:
            try:
                next_retry = dt.datetime.fromisoformat(next_retry_raw)
                if now < next_retry:
                    actions[key] = "backoff"
                    continue
            except (TypeError, ValueError):
                pass

        if failures >= max_restarts:
            actions[key] = "gave_up"
            continue

        res = start_service(key, info, state)
        svc_data = state["services"][key]
        svc_data["consecutive_failures"] = failures + 1
        svc_data["last_restart_at"] = now.isoformat()
        backoff_seconds = min(300.0, max(interval_seconds, interval_seconds * (2 ** min(failures, 4))))
        svc_data["next_retry_at"] = (
            now + dt.timedelta(seconds=backoff_seconds)
        ).isoformat()
        actions[key] = res["status"]
    save_state(state)
    return actions


def monitor_services(
    interval_seconds: float = 30.0,
    max_restarts: int = MAX_RESTARTS,
) -> None:
    print(
        f"[supervisor] monitoring every {interval_seconds:.0f}s "
        f"(max consecutive restarts: {max_restarts})",
        flush=True,
    )
    state = load_state()
    try:
        while True:
            actions = monitor_once(state, interval_seconds=interval_seconds, max_restarts=max_restarts)
            if any(action not in ("running", "backoff") for action in actions.values()):
                print(
                    f"[{dt.datetime.now(dt.timezone.utc).isoformat()}] {json.dumps(actions)}",
                    flush=True,
                )
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("[supervisor] monitor stopped", flush=True)


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
            "restart_count": int(svc_data.get("restart_count", 0)),
            "consecutive_failures": int(svc_data.get("consecutive_failures", 0)),
            "next_retry_at": svc_data.get("next_retry_at"),
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
    parser.add_argument("--monitor", action="store_true", help="Run a foreground health-monitor loop")
    parser.add_argument("--interval-seconds", type=float, default=30.0, help="Monitor check interval")
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=MAX_RESTARTS,
        help="Maximum consecutive restarts before a service is marked gave_up",
    )
    args = parser.parse_args()

    if args.monitor:
        monitor_services(
            interval_seconds=max(5.0, args.interval_seconds),
            max_restarts=max(1, args.max_restarts),
        )
        return

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
