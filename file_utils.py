#!/usr/bin/env python3
"""Small filesystem helpers for private runtime files."""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
from typing import Any


def atomic_write_text(
    path: pathlib.Path | str,
    text: str,
    *,
    mode: int = 0o600,
    encoding: str = "utf-8",
) -> pathlib.Path:
    """Write text beside ``path`` and atomically replace the destination.

    Private profiles, tokens, and vault snapshots should never be left half
    written if the process crashes mid-save.
    """
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target


def atomic_write_json(
    path: pathlib.Path | str,
    payload: Any,
    *,
    mode: int = 0o600,
    indent: int = 2,
) -> pathlib.Path:
    text = json.dumps(payload, indent=indent, ensure_ascii=False) + "\n"
    return atomic_write_text(path, text, mode=mode)
