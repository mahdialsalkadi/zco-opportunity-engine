#!/usr/bin/env python3
"""Load simple KEY=VALUE pairs from the repository ``.env`` file."""

from __future__ import annotations

import os
import pathlib


def load_local_env(base_dir: pathlib.Path | None = None) -> None:
    env_file = (base_dir or pathlib.Path(__file__).resolve().parent) / ".env"
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        return
