"""Run repository abstraction and JSON implementation."""
from __future__ import annotations

import json
import os
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from .config import PersistenceConfig, get_config
from .models import PersistentRun, RunStatus


class RunRepository(ABC):
    """Abstract repository for persisting VAPT runs."""

    @abstractmethod
    def save(self, run: PersistentRun) -> str:
        """Save a run to the repository.
        
        Args:
            run: The run to persist.
            
        Returns:
            The run_id of the saved run.
        """
        ...

    @abstractmethod
    def get(self, run_id: str) -> Optional[PersistentRun]:
        """Retrieve a run by ID.
        
        Args:
            run_id: The unique run identifier.
            
        Returns:
            The PersistentRun if found, None otherwise.
        """
        ...

    @abstractmethod
    def list_runs(self, limit: int = 100) -> list[PersistentRun]:
        """List recent runs.
        
        Args:
            limit: Maximum number of runs to return.
            
        Returns:
            List of PersistentRun objects, most recent first.
        """
        ...

    @abstractmethod
    def delete(self, run_id: str) -> bool:
        """Delete a run by ID.
        
        Args:
            run_id: The unique run identifier.
            
        Returns:
            True if deleted, False if not found.
        """
        ...


class JSONRunRepository(RunRepository):
    """JSON-file-backed run repository.
    
    Each run is stored as a separate JSON file in the storage directory.
    An index file tracks all run IDs for fast listing.
    """

    def __init__(self, config: Optional[PersistenceConfig] = None) -> None:
        self._config = config or get_config()
        self._lock = threading.Lock()
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Ensure storage directory and index file exist."""
        os.makedirs(self._config.storage_dir, exist_ok=True)
        if not os.path.exists(self._config.index_file):
            self._write_index([])

    def _read_index(self) -> list[str]:
        """Read the run index."""
        try:
            with open(self._config.index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_index(self, run_ids: list[str]) -> None:
        """Write the run index."""
        with open(self._config.index_file, "w", encoding="utf-8") as f:
            json.dump(run_ids, f, indent=2)

    def _run_file_path(self, run_id: str) -> str:
        """Get the file path for a run."""
        return os.path.join(self._config.storage_dir, f"{run_id}.json")

    def save(self, run: PersistentRun) -> str:
        """Save a run to the repository."""
        with self._lock:
            # Update timestamps
            now = datetime.now(timezone.utc).isoformat()
            if not run.created_at:
                run.created_at = now
            run.updated_at = now

            # Write run file
            file_path = self._run_file_path(run.run_id)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(run.to_dict(), f, indent=2, sort_keys=True)

            # Update index
            run_ids = self._read_index()
            if run.run_id not in run_ids:
                run_ids.append(run.run_id)
            
            # Enforce max runs limit
            if len(run_ids) > self._config.max_runs:
                removed = run_ids[:len(run_ids) - self._config.max_runs]
                run_ids = run_ids[-self._config.max_runs:]
                for rid in removed:
                    try:
                        os.remove(self._run_file_path(rid))
                    except OSError:
                        pass
            
            self._write_index(run_ids)

        return run.run_id

    def get(self, run_id: str) -> Optional[PersistentRun]:
        """Retrieve a run by ID."""
        file_path = self._run_file_path(run_id)
        
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PersistentRun.from_dict(data)
        except (json.JSONDecodeError, OSError, KeyError):
            # Corrupt or unreadable file
            return None

    def list_runs(self, limit: int = 100) -> list[PersistentRun]:
        """List recent runs."""
        run_ids = self._read_index()
        
        # Get file modification times for sorting
        runs_with_mtime = []
        for run_id in run_ids:
            file_path = self._run_file_path(run_id)
            try:
                mtime = os.path.getmtime(file_path)
                runs_with_mtime.append((run_id, mtime))
            except OSError:
                continue
        
        # Sort by modification time, most recent first
        runs_with_mtime.sort(key=lambda x: x[1], reverse=True)
        
        # Load runs
        runs = []
        for run_id, _ in runs_with_mtime[:limit]:
            run = self.get(run_id)
            if run is not None:
                runs.append(run)
        
        return runs

    def delete(self, run_id: str) -> bool:
        """Delete a run by ID."""
        with self._lock:
            file_path = self._run_file_path(run_id)
            
            if not os.path.exists(file_path):
                return False

            try:
                os.remove(file_path)
                run_ids = self._read_index()
                if run_id in run_ids:
                    run_ids.remove(run_id)
                    self._write_index(run_ids)
                return True
            except OSError:
                return False


# Global repository instance
_repository: Optional[RunRepository] = None


def get_repository() -> RunRepository:
    """Get the global repository instance."""
    global _repository
    if _repository is None:
        _repository = JSONRunRepository()
    return _repository


def set_repository(repository: RunRepository) -> None:
    """Set the global repository instance."""
    global _repository
    _repository = repository
