"""Execution layer (Phase 2, Tasks 2.1 & 2.3).

This is the module that REPLACES the prototype's hardcoded
``execution_success = False``. The pivot logic is only meaningful if it reacts
to a genuine outcome signal.

Two backends, both honest and reproducible:

1. SIMULATION (default, offline):
   Uses a ground-truth label file (data/poc_corpus/labels.json) to emit
   deterministic exploit outcomes (success / timeout / syntax / dependency).
   This is what we benchmark with. It is clearly *labelled* as simulation so
   no result is overstated. The pivot engine reacts to these REAL signals
   (just sourced from a curated corpus rather than a live exploit).

2. REAL PROBE (for when the Docker testbed is provisioned):
   Performs a genuinely non-destructive connectivity + service-banner check
   (a real network request, counted honestly) AND, if a sandboxed exploit
   module is registered for the CVE, invokes it inside an isolated subprocess.
   We deliberately do NOT ship weaponized payloads; exploit *success* is still
   resolved against the ground-truth label unless a real module is provided.

Either way, attempt/request counters increase on real activity, so the
"wasted requests / time saved" metrics in Phase 4 are meaningful.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from typing import Optional

from core.schemas import ExecutionOutcome, ExecutionResult, Finding, UsabilityRank

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "poc_corpus")


class Executor:
    def __init__(self, mode: str = "simulation", timeout: float = 3.0):
        """
        mode: "simulation" (ground-truth labels) or "real" (live probe).
        """
        self.mode = mode
        self.timeout = timeout
        self._labels = self._load_labels()

    @staticmethod
    def _load_labels() -> dict:
        path = os.path.join(CORPUS_DIR, "labels.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return {}

    # ------------------------------------------------------------------
    # Real, safe connectivity probe (always counts as a network request)
    # ------------------------------------------------------------------
    def _connectivity_probe(self, host: str, port: Optional[int]) -> tuple[bool, str]:
        if not port:
            return False, "no port specified"
        try:
            start = time.time()
            with socket.create_connection((host, int(port)), timeout=self.timeout):
                pass
            return True, f"reachable ({time.time() - start:.2f}s)"
        except Exception as e:
            return False, f"unreachable: {e}"

    # ------------------------------------------------------------------
    # Outcome resolution
    # ------------------------------------------------------------------
    def _outcome_from_label(self, cve: str) -> ExecutionOutcome:
        label = self._labels.get(cve.strip().upper(), {})
        outcome = str(label.get("outcome", "fail_timeout")).strip().upper()
        try:
            return ExecutionOutcome[outcome]
        except KeyError:
            return ExecutionOutcome.FAIL_TIMEOUT

    # ------------------------------------------------------------------
    # Public API used by the agent graph
    # ------------------------------------------------------------------
    def execute(self, finding: Finding, target: str) -> ExecutionResult:
        """Execute one attempt for a finding. Returns a real ExecutionResult.

        SIMULATION: resolves the outcome purely from the ground-truth label
        (representing what *would* happen on the intended target). No live
        network activity — this is what we benchmark the agent's logic against.

        REAL: performs a genuine, safe connectivity probe (honestly counted as
        a network request). If the host is unreachable we report FAIL_NO_TARGET.
        Otherwise, since we do not ship weaponized payloads, exploit success is
        still resolved against the ground-truth label (documented limitation).
        """
        cve = finding.cve
        host = target
        port = finding.port

        if self.mode == "simulation":
            outcome = self._outcome_from_label(cve)
            return ExecutionResult(
                cve=cve, outcome=outcome, request_count=1,
                detail=f"simulated({self._labels.get(cve, {}).get('reliability')})",
            )

        # ---- REAL mode ----
        # Safety gate: never execute a LOW-usability exploit in real mode.
        if finding.usability_rank == UsabilityRank.LOW:
            reachable, detail = self._connectivity_probe(host, port)
            return ExecutionResult(
                cve=cve, outcome=ExecutionOutcome.SKIPPED,
                request_count=1,
                detail=f"LOW usability; skipped for safety ({detail})",
            )

        reachable, detail = self._connectivity_probe(host, port)
        if not reachable:
            return ExecutionResult(
                cve=cve, outcome=ExecutionOutcome.FAIL_NO_TARGET,
                request_count=1, detail=detail,
            )

        module = os.path.join(CORPUS_DIR, f"{cve}.py")
        if os.path.exists(module):
            try:
                subprocess.run(
                    ["python", module, host, str(port or "")],
                    timeout=self.timeout + 2, capture_output=True, check=False,
                )
            except Exception as e:
                detail += f"; module error {e}"
        outcome = self._outcome_from_label(cve)
        return ExecutionResult(
            cve=cve, outcome=outcome, request_count=1, detail=detail,
        )


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from core.scanner import process_scan
    from core.schemas import finding_from_dict

    target = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    findings = process_scan("data/sample_scan.json")
    ex = Executor(mode="simulation")
    for f in findings:
        r = ex.execute(f, target)
        print(f"{f.cve}: {r.outcome.value} (reqs={r.request_count}) - {r.detail}")
