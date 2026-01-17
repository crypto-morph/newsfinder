#!/usr/bin/env python3
"""Manage the News Finder UI process with PID tracking and auto-reload."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT_DIR / "logs"
PID_FILE = LOG_DIR / "ui.pid"
LOG_FILE = LOG_DIR / "ui.log"


def load_web_config() -> tuple[str, int]:
    config_path = ROOT_DIR / "config.yaml"
    host = "0.0.0.0"
    port = 5000
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
            web_cfg = data.get("web", {})
            host = web_cfg.get("host", host)
            port = int(web_cfg.get("port", port))
    return host, port


def read_pid() -> Optional[int]:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except ValueError:
        return None


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start() -> None:
    pid = read_pid()
    if pid and is_running(pid):
        print(f"UI already running (pid {pid})")
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    host, port = load_web_config()
    command = [
        sys.executable,
        "-m",
        "flask",
        "--app",
        "src.web.app:create_app",
        "--debug",
        "run",
        "--host",
        host,
        "--port",
        str(port),
    ]

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    with LOG_FILE.open("a", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT_DIR),
            stdout=log_handle,
            stderr=log_handle,
            env=env,
            preexec_fn=os.setsid,
        )

    PID_FILE.write_text(str(process.pid))
    print(f"UI started (pid {process.pid}) on {host}:{port}")


def stop() -> None:
    pid = read_pid()
    if not pid:
        print("UI not running")
        return

    if not is_running(pid):
        PID_FILE.unlink(missing_ok=True)
        print("UI not running (stale pid file removed)")
        return

    os.killpg(pid, signal.SIGTERM)
    for _ in range(20):
        if not is_running(pid):
            break
        time.sleep(0.2)

    if is_running(pid):
        os.killpg(pid, signal.SIGKILL)

    PID_FILE.unlink(missing_ok=True)
    print("UI stopped")


def status() -> None:
    pid = read_pid()
    if pid and is_running(pid):
        print(f"UI running (pid {pid})")
    else:
        print("UI not running")


def restart() -> None:
    stop()
    start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage News Finder UI")
    parser.add_argument("action", choices=["start", "stop", "restart", "status"])
    args = parser.parse_args()

    actions = {
        "start": start,
        "stop": stop,
        "restart": restart,
        "status": status,
    }
    actions[args.action]()


if __name__ == "__main__":
    main()
