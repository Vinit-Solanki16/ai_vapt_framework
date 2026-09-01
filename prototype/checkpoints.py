"""Checkpoint utilities for the prototype.

Provides:
  - save_run_checkpoint / load_run_checkpoint (thin wrappers around engine)
  - auto_checkpoint(): context manager that saves on exit
  - resume_from_checkpoint(): loads a checkpoint and regenerates the report
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Optional

from decision_engine.core.engine import (
    save_checkpoint as _save_checkpoint,
    load_checkpoint as _load_checkpoint,
)


def save_run_checkpoint(state: dict, path: str) -> str:
    """Save a run state to a checkpoint file.

    Delegates directly to decision_engine.core.engine.save_checkpoint().
    """
    return _save_checkpoint(state, path)


def load_run_checkpoint(path: str) -> dict:
    """Load a run state from a checkpoint file.

    Delegates directly to decision_engine.core.engine.load_checkpoint().
    """
    return _load_checkpoint(path)


@contextmanager
def auto_checkpoint(state: dict, path: str):
    """Context manager that saves a checkpoint on exit (even on exception).

    Usage:
        with auto_checkpoint(final_state, "./ckpt.json") as ckpt_path:
            # do something with state
            pass
        # ckpt.json is saved here
    """
    yield path
    save_run_checkpoint(state, path)


def resume_from_checkpoint(path: str) -> dict:
    """Load a checkpoint and return its state for report generation.

    Args:
        path: Path to the checkpoint JSON file.

    Returns:
        The restored engine state dict.

    Raises:
        FileNotFoundError: if checkpoint doesn't exist.
        ValueError: if checkpoint version is unsupported.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Checkpoint not found: {path}")
    return load_run_checkpoint(path)
