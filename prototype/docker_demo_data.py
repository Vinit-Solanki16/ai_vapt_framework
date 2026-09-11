"""Docker lab demonstration scenarios.

These scenarios are designed for real execution against the Docker
vulnerability emulator. They do NOT include ground_truth labels —
outcomes are determined by actual HTTP responses from the emulator.

This ensures the demo shows genuinely observed results, not simulation.
"""

from decision_engine.core.schemas import ActionCandidate, Outcome


def docker_vuln_scenario(max_attempts: int = 2) -> list[dict]:
    """Docker lab scenario: candidate hits /vuln endpoint (success).

    Expected: SUCCESS on first attempt (emulator returns "VULNERABLE").
    """
    return [
        {"id": "docker-vuln-1", "probability": 0.95, "path": "/vuln"},
    ]


def docker_fail_scenario(max_attempts: int = 2) -> list[dict]:
    """Docker lab scenario: candidate hits /fail endpoint (failure).

    Expected: FAIL_TIMEOUT (emulator returns "NOT_VULNERABLE").
    """
    return [
        {"id": "docker-fail-1", "probability": 0.85, "path": "/fail"},
    ]


def docker_pivot_scenario(max_attempts: int = 2) -> list[dict]:
    """Docker lab scenario: failure then pivot to success.

    Candidate A hits /fail (fails twice, then pivot).
    Candidate B hits /vuln (succeeds).
    """
    return [
        {"id": "docker-fail-pivot", "probability": 0.70, "path": "/fail"},
        {"id": "docker-vuln-success", "probability": 0.85, "path": "/vuln"},
    ]


def docker_multi_scenario(max_attempts: int = 2) -> list[dict]:
    """Docker lab scenario: multiple candidates with mixed outcomes."""
    return [
        {"id": "docker-multi-1", "probability": 0.90, "path": "/vuln"},
        {"id": "docker-multi-2", "probability": 0.75, "path": "/fail"},
        {"id": "docker-multi-3", "probability": 0.60, "path": "/vuln"},
    ]


# Registry for Docker lab scenarios
DOCKER_SCENARIOS = {
    "docker_vuln": (docker_vuln_scenario, {"max_attempts": 2}),
    "docker_fail": (docker_fail_scenario, {"max_attempts": 2}),
    "docker_pivot": (docker_pivot_scenario, {"max_attempts": 2}),
    "docker_multi": (docker_multi_scenario, {"max_attempts": 2}),
}
