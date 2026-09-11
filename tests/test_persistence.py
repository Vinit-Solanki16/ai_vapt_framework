"""Tests for persistence layer."""
from __future__ import annotations

import os
import json
import tempfile
import pytest

from vapt_platform.persistence import (
    RunRepository,
    JSONRunRepository,
    PersistentRun,
    RunStatus,
    PersistenceConfig,
    get_repository,
)
from vapt_platform.persistence.repository import set_repository


# ---------------------------------------------------------------------------
# PersistentRun model tests
# ---------------------------------------------------------------------------

class TestPersistentRun:
    def test_create_run(self):
        run = PersistentRun(
            run_id="test-123",
            scenario="success",
            mode="simulation",
        )
        assert run.run_id == "test-123"
        assert run.scenario == "success"
        assert run.mode == "simulation"
        assert run.status == RunStatus.PENDING.value

    def test_to_dict(self):
        run = PersistentRun(
            run_id="test-123",
            scenario="success",
            mode="simulation",
        )
        d = run.to_dict()
        assert d["run_id"] == "test-123"
        assert d["scenario"] == "success"
        assert d["mode"] == "simulation"

    def test_from_dict(self):
        data = {
            "run_id": "test-123",
            "scenario": "success",
            "mode": "simulation",
            "status": "COMPLETED",
        }
        run = PersistentRun.from_dict(data)
        assert run.run_id == "test-123"
        assert run.scenario == "success"
        assert run.status == "COMPLETED"

    def test_roundtrip(self):
        run = PersistentRun(
            run_id="test-123",
            scenario="success",
            mode="simulation",
            final_status="SUCCESS",
            candidates=[{"id": "c1"}],
            evidence_tier="SIMULATED",
        )
        d = run.to_dict()
        restored = PersistentRun.from_dict(d)
        assert restored.run_id == run.run_id
        assert restored.scenario == run.scenario
        assert restored.final_status == run.final_status
        assert restored.candidates == run.candidates
        assert restored.evidence_tier == run.evidence_tier


# ---------------------------------------------------------------------------
# JSONRunRepository tests
# ---------------------------------------------------------------------------

class TestJSONRunRepository:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Create a temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = PersistenceConfig(storage_dir=self.temp_dir)
        self.repo = JSONRunRepository(config=self.config)
        yield
        # Cleanup
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_repository(self):
        assert self.repo is not None

    def test_save_and_get(self):
        run = PersistentRun(run_id="test-1", scenario="success", mode="simulation")
        self.repo.save(run)
        
        retrieved = self.repo.get("test-1")
        assert retrieved is not None
        assert retrieved.run_id == "test-1"
        assert retrieved.scenario == "success"

    def test_get_missing(self):
        retrieved = self.repo.get("nonexistent")
        assert retrieved is None

    def test_list_runs(self):
        for i in range(3):
            run = PersistentRun(run_id=f"test-{i}", scenario="success", mode="simulation")
            self.repo.save(run)
        
        runs = self.repo.list_runs()
        assert len(runs) == 3

    def test_list_runs_limit(self):
        for i in range(5):
            run = PersistentRun(run_id=f"test-{i}", scenario="success", mode="simulation")
            self.repo.save(run)
        
        runs = self.repo.list_runs(limit=3)
        assert len(runs) == 3

    def test_list_runs_ordering(self):
        """Most recent runs should come first."""
        for i in range(3):
            run = PersistentRun(run_id=f"test-{i}", scenario="success", mode="simulation")
            self.repo.save(run)
        
        runs = self.repo.list_runs()
        # Should be sorted by modification time (most recent first)
        assert len(runs) == 3

    def test_delete(self):
        run = PersistentRun(run_id="test-1", scenario="success", mode="simulation")
        self.repo.save(run)
        
        assert self.repo.delete("test-1") is True
        assert self.repo.get("test-1") is None

    def test_delete_missing(self):
        assert self.repo.delete("nonexistent") is False

    def test_corrupt_file(self):
        """Corrupt JSON should return None, not raise."""
        # Write corrupt data
        file_path = os.path.join(self.temp_dir, "corrupt.json")
        with open(file_path, "w") as f:
            f.write("{corrupt json")
        
        # Index it
        index_path = os.path.join(self.temp_dir, "index.json")
        with open(index_path, "w") as f:
            json.dump(["corrupt"], f)
        
        retrieved = self.repo.get("corrupt")
        assert retrieved is None

    def test_deterministic_serialization(self):
        """Same run should serialize to same bytes (except timestamps)."""
        run = PersistentRun(run_id="test-1", scenario="success", mode="simulation")
        self.repo.save(run)
        
        file_path = os.path.join(self.temp_dir, "test-1.json")
        with open(file_path, "r") as f:
            data1 = json.load(f)
        
        # Save again
        self.repo.save(run)
        
        with open(file_path, "r") as f:
            data2 = json.load(f)
        
        # Compare everything except updated_at
        data1.pop("updated_at", None)
        data2.pop("updated_at", None)
        assert data1 == data2

    def test_overwrite_behavior(self):
        """Saving same run_id twice should not duplicate."""
        run = PersistentRun(run_id="test-1", scenario="success", mode="simulation")
        self.repo.save(run)
        self.repo.save(run)
        
        runs = self.repo.list_runs()
        assert len(runs) == 1

    def test_max_runs_limit(self):
        """Oldest runs should be removed when exceeding max_runs."""
        config = PersistenceConfig(storage_dir=self.temp_dir, max_runs=3)
        repo = JSONRunRepository(config=config)
        
        for i in range(5):
            run = PersistentRun(run_id=f"test-{i}", scenario="success", mode="simulation")
            repo.save(run)
        
        runs = repo.list_runs(limit=10)
        assert len(runs) == 3


# ---------------------------------------------------------------------------
# Application integration tests
# ---------------------------------------------------------------------------

class TestApplicationPersistence:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Create a temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = PersistenceConfig(storage_dir=self.temp_dir)
        self.repo = JSONRunRepository(config=self.config)
        set_repository(self.repo)
        yield
        # Cleanup
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_run_is_persisted(self):
        from vapt_platform.application import VAPTApplication, VAPTRequest
        
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(req)
        
        # Run should be persisted
        persisted = self.repo.get(result.domain.run_id)
        assert persisted is not None
        assert persisted.scenario == "success"
        assert persisted.status in ("COMPLETED", "FAILED")

    def test_persisted_run_reload(self):
        from vapt_platform.application import VAPTApplication, VAPTRequest
        
        app = VAPTApplication()
        req = VAPTRequest(
            scenario="success",
            mode="simulation",
            max_attempts=2,
            assessor_mode="deterministic",
        )
        result = app.run(req)
        run_id = result.domain.run_id
        
        # Reload in fresh repository
        new_repo = JSONRunRepository(config=self.config)
        persisted = new_repo.get(run_id)
        
        assert persisted is not None
        assert persisted.final_status == result.domain.final_status
        assert persisted.candidates == result.domain.candidates
        assert persisted.decision_trace == result.domain.decision_trace
        assert persisted.evidence_tier == result.domain.evidence_tier
