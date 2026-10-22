"""Lightweight environment file loader for configuration variables.

Zero-dependency standard-library loader that populates `os.environ` from `.env`
using `setdefault` semantics (never overwrites existing variables).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def load_env(env_path: Optional[str] = None) -> None:
    """Load configuration variables from .env if present.

    - Uses setdefault (does not overwrite existing environment variables).
    - Ignores blank lines and comments.
    - Strips surrounding quotes.
    - Safe: silently ignores missing or inaccessible file.
    - When auto-discovering (env_path is None), skips during pytest test runs
      to prevent local untracked developer .env files from polluting unit tests.
    """
    if env_path is None:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        cwd = Path.cwd()
        repo_root = Path(__file__).resolve().parent.parent
        candidates = [
            cwd / ".env",
            repo_root / ".env",
        ]
        target: Optional[Path] = None
        for c in candidates:
            if c.is_file():
                target = c
                break
        if target is None:
            return
        env_file = target
    else:
        env_file = Path(env_path)
        if not env_file.is_file():
            return

    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key:
                        os.environ.setdefault(key, val)
    except OSError:
        pass
