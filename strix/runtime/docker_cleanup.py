"""Docker Container Cleanup and Sandbox Preservation for AI-VAPT.

Provides safe detection and reaping of orphaned sandbox containers left behind
after abrupt host crashes, unhandled exceptions, or SIGKILL events, while strictly:
1. Identifying ownership through explicit labels ('ai-vapt-managed', 'strix-managed',
   'strix-run-id', 'ai-vapt-run-id').
2. NEVER removing unrelated Docker containers (e.g. Juice Shop, user services, databases).
3. Preserving RUNNING containers by default across restarts, parallel workers, and transient
   in-memory disconnects (Finding D03 fix). Only genuinely dead/exited containers are
   cleaned automatically.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any


logger = logging.getLogger("strix.runtime.docker_cleanup")

# Ownership label markers applied to all AI-VAPT sandbox containers
OWNERSHIP_LABELS = (
    "ai-vapt-managed",
    "strix-managed",
    "ai-vapt-run-id",
    "strix-run-id",
)

# Known lab / testbed image keywords that must NEVER be touched by cleanup
PROTECTED_IMAGE_KEYWORDS = (
    "juice-shop",
    "bkimminich/juice-shop",
    "dvwa",
    "mutillidae",
    "webgoat",
    "postgres",
    "mysql",
    "redis",
    "mongo",
)


def is_container_owned_by_app(container: Any) -> bool:
    """Return True only if the container possesses explicit AI-VAPT ownership labels."""
    try:
        # Check image tag safety first
        image_tags = []
        try:
            image = getattr(container, "image", None)
            if image:
                image_tags = getattr(image, "tags", []) or []
        except Exception:
            pass

        attrs = getattr(container, "attrs", {}) or {}
        config = attrs.get("Config", {}) if isinstance(attrs, dict) else {}
        image_name = str(config.get("Image", "")).lower()

        for tag in image_tags:
            tag_lower = str(tag).lower()
            if any(prot in tag_lower for prot in PROTECTED_IMAGE_KEYWORDS):
                return False
        if any(prot in image_name for prot in PROTECTED_IMAGE_KEYWORDS):
            return False

        labels = getattr(container, "labels", None)
        if not isinstance(labels, dict):
            labels = config.get("Labels") or {}
        if not isinstance(labels, dict):
            return False

        if labels.get("ai-vapt-managed") == "true" or labels.get("strix-managed") == "true":
            return True
        if "strix-run-id" in labels or "ai-vapt-run-id" in labels:
            return True
        return labels.get("app") == "ai-vapt"
    except Exception:
        logger.debug("Failed to inspect container labels for ownership check", exc_info=True)
        return False


def get_container_run_id(container: Any) -> str | None:
    """Extract associated assessment run_id from container labels if present."""
    try:
        labels = getattr(container, "labels", None)
        if not isinstance(labels, dict):
            attrs = getattr(container, "attrs", {}) or {}
            labels = attrs.get("Config", {}).get("Labels") or {}
        if isinstance(labels, dict):
            return labels.get("ai-vapt-run-id") or labels.get("strix-run-id")
    except Exception:
        pass
    return None


def get_container_age_seconds(container: Any) -> float:
    """Calculate the age in seconds of a container from its created timestamp."""
    try:
        attrs = getattr(container, "attrs", {}) or {}
        created_str = attrs.get("Created")
        if not created_str:
            return 0.0
        normalized = created_str.split(".")[0].rstrip("Z")
        dt = datetime.fromisoformat(normalized).replace(tzinfo=UTC)
        return (datetime.now(UTC) - dt).total_seconds()
    except Exception:
        return 0.0


def reap_orphaned_containers(
    docker_client: Any | None = None,
    active_run_ids: set[str] | list[str] | None = None,
    min_age_seconds: int = 120,
    dry_run: bool = False,
    preserve_running: bool = True,
    force_running_reap: bool = False,
) -> dict[str, Any]:
    """Inspect and reap orphaned containers owned by AI-VAPT.

    D03 Hardening:
    - Running containers are preserved by default (`preserve_running=True`).
    - Exited/dead containers owned by AI-VAPT are safely removed if age >= min_age_seconds.
    - Unrelated containers (Juice Shop, databases, host services) are never touched.

    Args:
        docker_client: Optional docker.DockerClient instance; instantiated from environment if None.
        active_run_ids: Set of currently active assessment run IDs to preserve.
        min_age_seconds: Grace period in seconds; containers younger than this are preserved.
        dry_run: When True, identifies containers without stopping or removing them.
        preserve_running: When True (default), never kills running containers.
        force_running_reap: Requires explicit admin opt-in along with preserve_running=False to kill running containers.

    Returns:
        Structured summary of the cleanup operation.
    """
    summary: dict[str, Any] = {
        "status": "ok",
        "scanned": 0,
        "owned": 0,
        "reaped": 0,
        "preserved": 0,
        "errors": 0,
        "dry_run": dry_run,
        "reaped_containers": [],
        "preserved_containers": [],
    }

    client = docker_client
    owns_client = False
    if client is None:
        try:
            import docker

            client = docker.from_env()
            owns_client = True
        except Exception as e:
            logger.warning("Docker daemon is unreachable or docker package missing: %s", e)
            summary["status"] = "docker_unavailable"
            summary["error"] = str(e)
            return summary

    try:
        containers = client.containers.list(all=True)
    except Exception as e:
        logger.exception("Failed to query Docker containers list")
        summary["status"] = "error"
        summary["error"] = str(e)
        if owns_client:
            try:
                client.close()
            except Exception:
                pass
        return summary

    summary["scanned"] = len(containers)
    active_set = set(active_run_ids or [])

    for c in containers:
        c_id = getattr(c, "short_id", getattr(c, "id", "unknown"))
        # 1. Ownership check: Strictly filter for AI-VAPT managed containers
        if not is_container_owned_by_app(c):
            continue

        summary["owned"] += 1
        run_id = get_container_run_id(c)
        status = getattr(c, "status", "").lower()
        age_seconds = get_container_age_seconds(c)

        # 2. Check if active run assessment matches
        if run_id and run_id in active_set:
            summary["preserved"] += 1
            summary["preserved_containers"].append(
                {"id": c_id, "run_id": run_id, "reason": "active_run"}
            )
            continue

        # 3. Grace period check
        if age_seconds < min_age_seconds:
            summary["preserved"] += 1
            summary["preserved_containers"].append(
                {
                    "id": c_id,
                    "run_id": run_id,
                    "reason": f"grace_period ({int(age_seconds)}s < {min_age_seconds}s)",
                }
            )
            continue

        # 4. Preservation of running containers (D03 fix)
        # Never terminate a running sandbox unless preserve_running is explicitly False AND force_running_reap is True
        if status == "running" and (preserve_running or not force_running_reap):
            summary["preserved"] += 1
            summary["preserved_containers"].append(
                {
                    "id": c_id,
                    "run_id": run_id,
                    "reason": "running_sandbox_preserved_by_default",
                }
            )
            continue

        # 5. Container is dead/exited or explicitly confirmed for reap
        if dry_run:
            summary["reaped"] += 1
            summary["reaped_containers"].append(
                {"id": c_id, "run_id": run_id, "status": status, "action": "would_remove"}
            )
            continue

        try:
            if status == "running":
                logger.info("Reaping running orphaned container %s (run_id: %s)", c_id, run_id)
                try:
                    c.kill()
                except Exception as k_err:
                    logger.debug("Failed to kill container %s: %s", c_id, k_err)
            c.remove(force=True)
            summary["reaped"] += 1
            summary["reaped_containers"].append(
                {"id": c_id, "run_id": run_id, "status": status, "action": "removed"}
            )
        except Exception as r_err:
            logger.warning("Failed to remove container %s: %s", c_id, r_err)
            summary["errors"] += 1

    if owns_client:
        try:
            client.close()
        except Exception:
            pass

    return summary


async def reap_orphaned_containers_async(
    active_run_ids: set[str] | list[str] | None = None,
    min_age_seconds: int = 120,
    dry_run: bool = False,
    preserve_running: bool = True,
    force_running_reap: bool = False,
) -> dict[str, Any]:
    """Asynchronous wrapper for reap_orphaned_containers offloaded to worker thread."""
    return await asyncio.to_thread(
        reap_orphaned_containers,
        active_run_ids=active_run_ids,
        min_age_seconds=min_age_seconds,
        dry_run=dry_run,
        preserve_running=preserve_running,
        force_running_reap=force_running_reap,
    )
