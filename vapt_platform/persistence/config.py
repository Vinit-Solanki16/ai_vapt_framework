"""Persistence configuration."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _default_storage_dir() -> str:
    env_dir = os.environ.get("VAPT_STORAGE_DIR")
    if env_dir:
        return env_dir
    user_home = os.path.expanduser("~")
    home_dir = os.path.join(user_home, ".ai_vapt_framework", "runs")
    try:
        os.makedirs(home_dir, exist_ok=True)
        return home_dir
    except OSError:
        tmp_dir = os.path.join(tempfile.gettempdir(), ".ai_vapt_framework", "runs")
        try:
            os.makedirs(tmp_dir, exist_ok=True)
        except OSError:
            pass
        return tmp_dir


# Default storage location
DEFAULT_STORAGE_DIR = _default_storage_dir()


@dataclass
class PersistenceConfig:
    """Configuration for run persistence."""
    storage_dir: str = DEFAULT_STORAGE_DIR
    max_runs: int = 1000  # Maximum number of runs to retain

    def __post_init__(self) -> None:
        """Ensure storage directory exists."""
        try:
            Path(self.storage_dir).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

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
