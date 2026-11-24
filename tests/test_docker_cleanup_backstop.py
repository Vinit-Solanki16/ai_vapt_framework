"""Deterministic tests for the AI-VAPT Docker container cleanup backstop."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from strix.interface.api import app
from strix.runtime.docker_cleanup import (
    is_container_owned_by_app,
    reap_orphaned_containers,
)


class MockContainer:
    """Mock Docker Container object with simulated metadata and lifecycle methods."""

    def __init__(
        self,
        container_id: str,
        labels: dict[str, str] | None = None,
        status: str = "running",
        created_dt: datetime | None = None,
    ):
        self.id = container_id
        self.short_id = container_id[:12]
        self.labels = labels or {}
        self.status = status
        now = created_dt or datetime.now(UTC)
        self.attrs = {
            "Id": container_id,
            "Created": now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "Config": {"Labels": self.labels},
            "State": {"Status": status},
        }
        self.killed = False
        self.removed = False

    def kill(self):
        self.killed = True

    def remove(self, force: bool = False):
        self.removed = True


def test_is_container_owned_by_app_strict_labels():
    """Verify ownership check strictly accepts AI-VAPT markers and rejects unrelated containers."""
    c_owned1 = MockContainer("c1", labels={"ai-vapt-managed": "true"})
    c_owned2 = MockContainer("c2", labels={"strix-managed": "true"})
    c_owned3 = MockContainer("c3", labels={"strix-run-id": "run-abc"})
    c_owned4 = MockContainer("c4", labels={"ai-vapt-run-id": "run-xyz"})
    c_owned5 = MockContainer("c5", labels={"app": "ai-vapt"})

    assert is_container_owned_by_app(c_owned1) is True
    assert is_container_owned_by_app(c_owned2) is True
    assert is_container_owned_by_app(c_owned3) is True
    assert is_container_owned_by_app(c_owned4) is True
    assert is_container_owned_by_app(c_owned5) is True

    # Unrelated containers (must NEVER be considered owned)
    c_juice_shop = MockContainer("juice1", labels={"maintainer": "bkimminich", "app": "juice-shop"})
    c_postgres = MockContainer("pg1", labels={"postgres": "15"})
    c_empty = MockContainer("empty1", labels={})

    assert is_container_owned_by_app(c_juice_shop) is False
    assert is_container_owned_by_app(c_postgres) is False
    assert is_container_owned_by_app(c_empty) is False


def test_reap_orphaned_containers_never_touches_unrelated():
    """Ensure unrelated containers are never killed or removed."""
    unrelated_1 = MockContainer("unrelated-1", labels={"role": "database"}, status="running")
    unrelated_2 = MockContainer("unrelated-2", labels={"vendor": "redis"}, status="exited")

    mock_docker = MagicMock()
    mock_docker.containers.list.return_value = [unrelated_1, unrelated_2]

    res = reap_orphaned_containers(docker_client=mock_docker)

    assert res["status"] == "ok"
    assert res["scanned"] == 2
    assert res["owned"] == 0
    assert res["reaped"] == 0
    assert unrelated_1.killed is False
    assert unrelated_1.removed is False
    assert unrelated_2.killed is False
    assert unrelated_2.removed is False


def test_reap_orphaned_containers_preserves_active_assessments():
    """Containers associated with currently active assessments must be preserved."""
    active_run_id = "run-active-999"
    active_container = MockContainer(
        "c-active",
        labels={"ai-vapt-managed": "true", "strix-run-id": active_run_id},
        status="running",
        created_dt=datetime.now(UTC) - timedelta(seconds=600),
    )

    mock_docker = MagicMock()
    mock_docker.containers.list.return_value = [active_container]

    res = reap_orphaned_containers(
        docker_client=mock_docker,
        active_run_ids={active_run_id},
    )

    assert res["status"] == "ok"
    assert res["owned"] == 1
    assert res["preserved"] == 1
    assert res["reaped"] == 0
    assert active_container.killed is False
    assert active_container.removed is False


def test_reap_orphaned_containers_preserves_grace_period():
    """Running containers younger than min_age_seconds must be preserved to prevent race conditions."""
    young_container = MockContainer(
        "c-young",
        labels={"ai-vapt-managed": "true", "strix-run-id": "run-fresh"},
        status="running",
        created_dt=datetime.now(UTC) - timedelta(seconds=30),
    )

    mock_docker = MagicMock()
    mock_docker.containers.list.return_value = [young_container]

    res = reap_orphaned_containers(
        docker_client=mock_docker,
        active_run_ids=set(),
        min_age_seconds=120,
        preserve_running=False,
        force_running_reap=True,
    )

    assert res["status"] == "ok"
    assert res["owned"] == 1
    assert res["preserved"] == 1
    assert res["reaped"] == 0
    assert young_container.killed is False
    assert young_container.removed is False


def test_reap_orphaned_containers_reaps_dead_and_stale_containers():
    """Verify stale running container and exited orphaned container are cleaned up."""
    stale_running = MockContainer(
        "c-stale",
        labels={"ai-vapt-managed": "true", "strix-run-id": "run-crashed"},
        status="running",
        created_dt=datetime.now(UTC) - timedelta(seconds=900),
    )
    exited_orphan = MockContainer(
        "c-exited",
        labels={"ai-vapt-managed": "true", "strix-run-id": "run-done"},
        status="exited",
        created_dt=datetime.now(UTC) - timedelta(seconds=1200),
    )

    mock_docker = MagicMock()
    mock_docker.containers.list.return_value = [stale_running, exited_orphan]

    res = reap_orphaned_containers(
        docker_client=mock_docker,
        active_run_ids=set(),
        min_age_seconds=120,
        preserve_running=False,
        force_running_reap=True,
    )

    assert res["status"] == "ok"
    assert res["owned"] == 2
    assert res["reaped"] == 2
    assert stale_running.killed is True
    assert stale_running.removed is True
    assert exited_orphan.removed is True


def test_reap_orphaned_containers_dry_run_mode():
    """Dry-run mode inspects and identifies reaped targets without mutating containers."""
    stale_running = MockContainer(
        "c-dry",
        labels={"ai-vapt-managed": "true"},
        status="running",
        created_dt=datetime.now(UTC) - timedelta(seconds=500),
    )

    mock_docker = MagicMock()
    mock_docker.containers.list.return_value = [stale_running]

    res = reap_orphaned_containers(
        docker_client=mock_docker,
        active_run_ids=set(),
        min_age_seconds=120,
        dry_run=True,
        preserve_running=False,
        force_running_reap=True,
    )

    assert res["dry_run"] is True
    assert res["reaped"] == 1
    assert stale_running.killed is False
    assert stale_running.removed is False


def test_docker_cleanup_api_endpoint(monkeypatch):
    """Verify the /system/docker/cleanup FastAPI endpoint functions cleanly."""
    from strix.runtime import docker_cleanup

    mock_result = {
        "status": "ok",
        "scanned": 5,
        "owned": 2,
        "reaped": 1,
        "preserved": 1,
        "errors": 0,
        "dry_run": False,
        "reaped_containers": [{"id": "abc12345", "run_id": "run-old", "status": "exited"}],
        "preserved_containers": [],
    }

    async def mock_async_cleanup(**kwargs):
        return mock_result

    monkeypatch.setattr(docker_cleanup, "reap_orphaned_containers_async", mock_async_cleanup)

    client = TestClient(app)
    response = client.post("/system/docker/cleanup?dry_run=false")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["reaped"] == 1
    assert data["owned"] == 2
