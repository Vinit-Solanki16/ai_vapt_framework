"""Persistence layer for VAPT run history.

Provides a clean abstraction for storing and retrieving completed VAPT runs.
Initial implementation uses JSON file storage.

Architecture:
    VAPTApplication ──> RunRepository ──> JSON files on disk
"""
from __future__ import annotations

from .repository import RunRepository, JSONRunRepository, get_repository
from .models import PersistentRun, RunStatus
from .config import PersistenceConfig, get_config

__all__ = [
    "RunRepository",
    "JSONRunRepository",
    "get_repository",
    "PersistentRun",
    "RunStatus",
    "PersistenceConfig",
    "get_config",
]
