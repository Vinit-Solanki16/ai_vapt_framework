"""Execution layer (Phase 2, Tasks 2.1 & 2.3).

This module REPLACES the prototype's hardcoded ``execution_success = False``.
The pivot logic is only meaningful if it reacts to a genuine outcome signal.

Two backends:

1. SIMULATION (default, offline):
   Uses a ground-truth label file (data/poc_corpus/labels.json) to emit
   deterministic exploit outcomes (success / timeout / syntax / dependency).
   This is what we benchmark with. It is clearly *labelled* as simulation so
   no result is overstated. The pivot engine reacts to these REAL signals
   (just sourced from a curated corpus rather than a live exploit).

2. REAL mode (default ``real``): connectivity-ONLY probe.
   Performs a genuinely non-destructive TCP connectivity check (a real network
   request, counted honestly). It does NOT send any exploit payload and does
   NOT shell out to the corpus PoC modules. This is a SAFE connectivity-only
   probe: it reports reachability and, when no exploit is executed, an explicit
   "not exploited" outcome. No offensive traffic is generated in default
   ``real`` mode.

   OPT-IN DANGEROUS PATH (``danger_mode=True`` only):
   For explicit, sandboxed, authorised-lab use only, a corpus exploit module
   MAY be executed in an isolated subprocess and the module's ACTUAL
   stdout/stderr is parsed to derive the outcome (labels.json is NOT trusted).
   This path is OFF by default and must be enabled explicitly. It prints a
   prominent warning and is intended solely for an isolated, authorised testbed
   (see T-DOCKER). Never run it against targets you are not authorised to test.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import warnings
from typing import Iterable, Optional

from core.schemas import ExecutionOutcome, ExecutionResult, Finding, UsabilityRank

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "poc_corpus")

# Tokens that, if present in a module's captured output, indicate a successful
# exploitation (opt-in danger_mode only). This is a minimal, documented contract
# for parsing REAL module output instead of trusting labels.json. It is a
# placeholder until T-DOCKER defines a formal module-output protocol.
_SUCCESS_TOKENS = ("EXPLOIT_SUCCESS", "VULNERABLE", "exploit success", "[+] vulnerable")
_DEP_TOKENS = ("ModuleNotFoundError", "ImportError", "No module named", "command not found")


class Executor:
    def __init__(self, mode: str = "simulation", timeout: float = 3.0,
                 danger_mode: bool = False,
                 target_allowlist: Optional[Iterable[str]] = None):
        """
        mode: "simulation" (ground-truth labels) or "real" (live probe).

        danger_mode: ONLY relevant when mode == "real". When False (default),
        real mode is connectivity-ONLY and never executes a corpus exploit
        module. When True, an explicit, opt-in, sandboxed path may execute a
        corpus PoC module and parse its real output. Enabling this prints a
        prominent warning — use only in an authorised, isolated lab.

        target_allowlist: T-DOCKER Stage B, fail-closed authorisation for
        danger_mode. ONLY hosts listed here may be attacked when
        danger_mode=True. The DEFAULT (empty) allowlist refuses EVERY target:
        nothing is executed until an operator explicitly authorises hosts.
        Entries are matched after stripping surrounding whitespace and
        case-folding. Ignored outside danger_mode.
        """
        self.mode = mode
        self.timeout = timeout
        self.danger_mode = danger_mode
        # Fail-closed: normalise to a stripped/case-folded set. None or empty
        # => danger_mode is authorised against NOTHING until set explicitly.
        self.target_allowlist = {
            str(h).strip().casefold() for h in (target_allowlist or [])
            if str(h).strip()
        }
        self._labels = self._load_labels()
        if self.mode == "real" and self.danger_mode:
            warnings.warn(
                "DANGER MODE ENABLED: real executor will shell out to corpus "
                "exploit PoC modules and send live offensive traffic. Use ONLY "
                "against an authorised, isolated testbed (e.g. Docker). "
                "Never run against targets you are not authorised to test.",
                stacklevel=2,
            )
            print(
                "[T-SAFE WARNING] danger_mode=True: live exploit execution "
                "enabled. Authorised, isolated lab target only.",
                file=sys.stderr,
            )

    @staticmethod
    def _load_labels() -> dict:
        path = os.path.join(CORPUS_DIR, "labels.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return {}

    # ------------------------------------------------------------------
    # Real, non-destructive connectivity probe (always counts as a request)
    # ------------------------------------------------------------------
    def _connectivity_probe(self, host: str, port: Optional[int]) -> tuple[bool, str]:
        """Genuinely non-destructive TCP connectivity check.

        This is a real network request (counted honestly) but it sends NO
        exploit payload — it only opens and closes a TCP connection to verify
        the host/port is reachable. It is safe by construction.
        """
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
    # Outcome resolution (SIMULATION only — labels are NOT trusted in real mode)
    # ------------------------------------------------------------------
    def _outcome_from_label(self, cve: str) -> ExecutionOutcome:
        label = self._labels.get(cve.strip().upper(), {})
        outcome = str(label.get("outcome", "fail_timeout")).strip().upper()
        try:
            return ExecutionOutcome[outcome]
        except KeyError:
            return ExecutionOutcome.FAIL_TIMEOUT

    # ------------------------------------------------------------------
    # Opt-in dangerous path: run the corpus module, parse REAL output
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_module_output(stdout: str, stderr: str, returncode: int) -> ExecutionOutcome:
        """Derive the outcome from a corpus module's ACTUAL output.

        Replaces the old behaviour of trusting labels.json. Heuristic, minimal
        contract (placeholder until T-DOCKER formalises a module-output spec):
          * non-zero exit OR traceback in stderr -> FAIL_SYNTAX
          * dependency-style error in stderr -> FAIL_DEPENDENCY
          * explicit success token in output -> SUCCESS
          * ran cleanly but no success token -> FAIL_TIMEOUT (unconfirmed)
        """
        out = (stdout or "") + (stderr or "")
        if returncode != 0 or "Traceback (most recent call last)" in (stderr or ""):
            if any(tok in (stderr or "") for tok in _DEP_TOKENS):
                return ExecutionOutcome.FAIL_DEPENDENCY
            return ExecutionOutcome.FAIL_SYNTAX
        for tok in _SUCCESS_TOKENS:
            if tok.lower() in out.lower():
                return ExecutionOutcome.SUCCESS
        return ExecutionOutcome.FAIL_TIMEOUT

    # ------------------------------------------------------------------
    # Public API used by the agent graph
    # ------------------------------------------------------------------
    def execute(self, finding: Finding, target: str) -> ExecutionResult:
        """Execute one attempt for a finding. Returns a real ExecutionResult.

        SIMULATION: resolves the outcome purely from the ground-truth label
        (representing what *would* happen on the intended target). No live
        network activity — this is what we benchmark the agent's logic against.

        REAL (default, danger_mode=False): connectivity-ONLY. Performs a safe
        TCP connectivity probe (honestly counted as a network request). It does
        NOT execute any corpus exploit module and sends NO offensive payload.
        If the host is unreachable we report FAIL_NO_TARGET. If reachable, since
        live exploitation is disabled by default, we report SKIPPED with an
        explicit note that no exploit was sent. To actually run a corpus PoC you
        must construct the Executor with danger_mode=True (opt-in, sandboxed,
        authorised-lab-only).

        REAL (opt-in danger_mode=True): runs the corpus exploit module for the
        CVE in an isolated subprocess and parses its REAL stdout/stderr to set
        the outcome. A prominent warning is emitted at construction time.
        T-DOCKER Stage B: even with danger_mode=True, ONLY hosts explicitly
        present in target_allowlist are attacked — any other host is refused
        (FAIL_NO_TARGET, "target not allowlisted"). The default empty
        allowlist is fail-closed: danger_mode refuses EVERYTHING until
        targets are explicitly authorised.
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
        # Safety gate: never execute a LOW-usability exploit, even in danger
        # mode — low-rank PoCs are too unreliable/risky to fire.
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

        # Host is reachable. Default real mode is connectivity-only: do NOT
        # shell out to the corpus PoC. Report honestly that no exploit ran.
        if not self.danger_mode:
            return ExecutionResult(
                cve=cve, outcome=ExecutionOutcome.SKIPPED,
                request_count=1,
                detail=(
                    "reachable; live PoC execution DISABLED by default (safe "
                    "mode) - no exploit was sent. Set danger_mode=True to opt "
                    "in to sandboxed exploitation in an authorised lab."
                ),
            )

        # ---- Opt-in dangerous path (danger_mode=True) ----
        # T-DOCKER Stage B gate (fail-closed, BEFORE any subprocess.run):
        # danger_mode only ever fires against explicitly authorised hosts.
        # Default allowlist is empty => refuse EVERYTHING until the operator
        # authorises targets via Executor(target_allowlist=[...]).
        if str(host).strip().casefold() not in self.target_allowlist:
            return ExecutionResult(
                cve=cve, outcome=ExecutionOutcome.FAIL_NO_TARGET,
                request_count=1,
                detail=(
                    f"target not allowlisted ({host}); danger_mode refused. "
                    "Add the host to Executor(target_allowlist=[...]) to "
                    "explicitly authorise exploitation."
                ),
            )

        module = os.path.join(CORPUS_DIR, f"{cve}.py")
        if not os.path.exists(module):
            return ExecutionResult(
                cve=cve, outcome=ExecutionOutcome.FAIL_NO_TARGET,
                request_count=1,
                detail=f"reachable; no corpus module for {cve} (danger_mode).",
            )
        try:
            proc = subprocess.run(
                ["python", module, host, str(port or "")],
                timeout=self.timeout + 2,
                capture_output=True, check=False,
            )
            outcome = self._parse_module_output(
                proc.stdout.decode(errors="replace"),
                proc.stderr.decode(errors="replace"),
                proc.returncode,
            )
            detail = (
                f"danger_mode: ran {os.path.basename(module)} "
                f"(rc={proc.returncode}); outcome parsed from module output"
            )
        except Exception as e:
            outcome = ExecutionOutcome.FAIL_SYNTAX
            detail = f"danger_mode: module error {e}"
        return ExecutionResult(
            cve=cve, outcome=outcome, request_count=1, detail=detail,
        )


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from core.schemas import finding_from_dict
    from vapt_platform.scanners import get_scanner_registry

    def _to_core_finding(cf):
        meta = cf.metadata or {}
        return finding_from_dict({
            "cve": meta.get("cve") or "UNKNOWN-CVE",
            "port": cf.port or None,
            "service": meta.get("service"),
            "description": cf.description,
            "epss_score": meta.get("epss_score", 0.0),
        })

    target = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    findings = [_to_core_finding(cf) for cf in get_scanner_registry().parse("data/sample_scan.json")]
    ex = Executor(mode="simulation")
    for f in findings:
        r = ex.execute(f, target)
        print(f"{f.cve}: {r.outcome.value} (reqs={r.request_count}) - {r.detail}")
