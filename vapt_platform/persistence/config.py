"""Persistence configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# Default storage location
DEFAULT_STORAGE_DIR = os.path.join(os.path.expanduser("~"), ".ai_vapt_framework", "runs")


@dataclass
class PersistenceConfig:
    """Configuration for run persistence."""
    storage_dir: str = DEFAULT_STORAGE_DIR
    max_runs: int = 1000  # Maximum number of runs to retain

    def __post_init__(self) -> None:
        """Ensure storage directory exists."""
        Path(self.storage_dir).mkdir(parents=True, exist_ok=True)

    @property
    def index_file(self) -> str:
        """Path to the run index file."""
        return os.path.join(self.storage_dir, "index.json")


# Global config instance
_config = PersistenceConfig()


def get_config() -> PersistenceConfig:
    """Get the global persistence configuration."""
    return _config


def set_config(config: PersistenceConfig) -> None:
    """Set the global persistence configuration."""
    global _config
    _config = config
