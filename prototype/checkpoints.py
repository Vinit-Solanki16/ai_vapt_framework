"""Checkpoint utilities for the prototype.

Provides a thin wrapper around the engine's checkpointing functions.
Engine checkpointing is preserved as-is; no reimplementation here.
"""

from typing import Optional

from decision_engine.core.engine import (
    save_checkpoint as _save_checkpoint,
    load_checkpoint as _load_checkpoint,
)


def save_run_checkpoint(state: dict, path: str) -> str:
    """Save a run state to a checkpoint file.

    Delegates directly to decision_engine.core.engine.save_checkpoint().

    Args:
        state: The engine state dict to save
        path: File path to write the checkpoint

    Returns:
        The path the checkpoint was written to
    """
    return _save_checkpoint(state, path)


def load_run_checkpoint(path: str) -> dict:
    """Load a run state from a checkpoint file.

    Delegates directly to decision_engine.core.engine.load_checkpoint().

    Args:
        path: File path of the checkpoint to load

    Returns:
        The restored engine state dict
    """
    return _load_checkpoint(path)