"""Run-scoped GAP-1 / GAP-2 state service.

This is the integrated GAP service that the Strix runner drives. It is
separate from the optional, file-based ``gap_bridge`` that the legacy
AI-VAPT adapter used; this is the Strix-native implementation and it is what
the report artifacts draw on when they render GAP-1/GAP-2 progress.

GAP-1 candidates are each tracked with a lifecycle status:

    discovered -> investigated -> validated | abandoned | unresolved

GAP-2 records real adaptive decisions only, never artificial counts:

    probe_outcome  : positive | negative | inconclusive | error
    retry_reason   : why a probe was retried
    alternative    : the candidate selected as a result of a negative probe
    pivot_executed : True only when a real pivot ran
    pivot_result   : the outcome of that pivot

Nothing here fabricates a pivot: ``record_pivot`` is the only way a pivot count
is incremented, and it only happens when a real alternative candidate and a
real probe result are supplied.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

_CANDIDATE_STATUSES = (
    "discovered",
    "investigated",
    "validated",
    "abandoned",
    "unresolved",
    "blocked",
)
_PROBE_OUTCOMES = ("positive", "negative", "inconclusive", "error", "blocked")
_PIVOT_RESULTS = ("positive", "negative", "inconclusive", "skipped")


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


class GapRunError(ValueError):
    """Raised when a GAP event is invalid for the run."""


class GapRun:
    """Per-run GAP state that lives next to the report state.

    Attributes:
        run_id: identifier of the scan this GAP state belongs to.
        candidates: {candidate_id: GapCandidate} — includes metadata needed for
            the report (title, endpoint, category, rank/score).
        probe_outcomes: [{candidate_id, outcome, detail, retry_reason,
            alternative_candidate, pivot_executed, pivot_result, at}]
        decision_trace: the ordered list of events that produced the current
            GAP state (honest audit trail).
    """

    def __init__(self, run_id: str, state_dir: Path, threshold: int = 2):
        self.run_id = run_id
        self.state_dir = state_dir
        self.threshold = max(1, threshold)
        self._path = state_dir / "gap_state.json"
        self.candidates: dict[str, GapCandidate] = {}
        self.probe_outcomes: list[dict[str, Any]] = []
        self.decision_trace: list[dict[str, Any]] = []
        self._decision_engine: Any = None

    # -- persistence -------------------------------------------------------

    def save(self) -> None:
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "candidates": {cid: c.to_dict() for cid, c in self.candidates.items()},
            "probe_outcomes": self.probe_outcomes,
            "decision_trace": self.decision_trace,
        }
        try:
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            logger.info(
                "GAP state saved for run %s (%d candidates)", self.run_id, len(self.candidates)
            )
        except OSError as exc:
            logger.warning("GAP state save failed for run %s: %s", self.run_id, exc)

    @classmethod
    def load(cls, run_id: str, state_dir: Path) -> GapRun:
        gap = cls(run_id, state_dir)
        path = state_dir / "gap_state.json"
        if not path.exists():
            return gap
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("GAP state unreadable for run %s: %s", run_id, exc)
            return gap
        if isinstance(data, dict):
            for cid, cd in (data.get("candidates") or {}).items():
                if isinstance(cd, dict):
                    gap.candidates[cid] = GapCandidate.from_dict(cid, cd)
            gap.probe_outcomes = [e for e in data.get("probe_outcomes", []) if isinstance(e, dict)]
            gap.decision_trace = [e for e in data.get("decision_trace", []) if isinstance(e, dict)]
        return gap

    # -- GAP-1 lifecycle ---------------------------------------------------

    def attach_candidate(
        self,
        candidate_id: str,
        title: str,
        endpoint: str,
        category: str,
        *,
        score: float = 0.0,
        rank: int = 0,
        target: str = "",
        max_attempts: int = 2,
        attempts: int = 0,
    ) -> GapCandidate:
        """Materialise one discovery as a tracked GAP-1 candidate."""
        if candidate_id in self.candidates:
            logger.warning("GAP-1 candidate %s already attached", candidate_id)
            cand = self.candidates[candidate_id]
            if target and not cand.target:
                cand.target = target
            return cand
        cand = GapCandidate(
            candidate_id=candidate_id,
            title=title,
            endpoint=endpoint,
            category=category,
            score=score,
            rank=rank,
            target=target,
            max_attempts=max_attempts,
            attempts=attempts,
        )
        self.candidates[candidate_id] = cand
        self._record(
            "candidate_added",
            candidate_id=candidate_id,
            title=title,
            endpoint=endpoint,
            category=category,
            score=score,
            rank=rank,
            target=target,
        )
        self.save()
        return cand

    def record_investigation(
        self, candidate_id: str, *, outcome: str, detail: str = ""
    ) -> dict[str, Any]:
        """Move a candidate to 'investigated' and record the outcome.

        outcome: validated | abandoned | inconclusive | blocked
        """
        cand = self.candidates.get(candidate_id)
        if cand is None:
            raise GapRunError(f"GAP-1 candidate {candidate_id!r} does not exist")
        if outcome not in ("validated", "abandoned", "inconclusive", "blocked"):
            raise GapRunError(
                f"outcome must be validated/abandoned/inconclusive/blocked, got {outcome!r}"
            )
        cand.status = "investigated" if outcome != "blocked" else "blocked"
        cand.last_investigated_at = _now()
        cand.investigation_outcome = outcome
        self._record("investigation", candidate_id=candidate_id, outcome=outcome, detail=detail)
        self.save()
        return cand.to_dict()

    def record_validity(
        self,
        candidate_id: str,
        *,
        evidence: str,
        confirmed: bool,
        actual_impact: str = "",
    ) -> dict[str, Any]:
        """Move a candidate to 'validated' (or back to 'unresolved')."""
        cand = self.candidates.get(candidate_id)
        if cand is None:
            raise GapRunError(f"GAP-1 candidate {candidate_id!r} does not exist")
        cand.verification_evidence = evidence
        cand.actual_impact = actual_impact
        cand.status = "validated" if confirmed else "unresolved"
        cand.investigation_outcome = "validated" if confirmed else "unresolved"
        self._record(
            "validated",
            candidate_id=candidate_id,
            verified=confirmed,
            evidence=evidence,
            actual_impact=actual_impact,
        )
        self.save()
        return cand.to_dict()

    def abandon(self, candidate_id: str, reason: str) -> dict[str, Any]:
        cand = self.candidates.get(candidate_id)
        if cand is None:
            raise GapRunError(f"GAP-1 candidate {candidate_id!r} does not exist")
        cand.status = "abandoned"
        cand.investigation_outcome = "abandoned"
        cand.abandoned_at = _now()
        cand.abandon_reason = reason
        self._record("abandoned", candidate_id=candidate_id, reason=reason)
        self.save()
        return cand.to_dict()

    def record_blocked(self, candidate_id: str, reason: str) -> dict[str, Any]:
        cand = self.candidates.get(candidate_id)
        if cand is None:
            raise GapRunError(f"GAP-1 candidate {candidate_id!r} does not exist")
        cand.status = "blocked"
        cand.investigation_outcome = "blocked"
        cand.abandon_reason = reason
        self._record("blocked", candidate_id=candidate_id, reason=reason)
        self.save()
        return cand.to_dict()

    def set_unresolved(self, candidate_id: str, reason: str) -> dict[str, Any]:
        cand = self.candidates.get(candidate_id)
        if cand is None:
            raise GapRunError(f"GAP-1 candidate {candidate_id!r} does not exist")
        cand.status = "unresolved"
        cand.abandon_reason = reason
        self._record("unresolved", candidate_id=candidate_id, reason=reason)
        self.save()
        return cand.to_dict()

    # -- GAP-2 (real adaptive pivots) --------------------------------------

    def record_probe_outcome(
        self,
        candidate_id: str,
        *,
        outcome: str,
        detail: str = "",
        retry_reason: str = "",
        alternative_candidate: str = "",
        pivot_executed: bool = False,
        pivot_result: str = "",
    ) -> dict[str, Any]:
        """Record one probe of one candidate.

        Only records real events: a pivot is incremented only when
        ``pivot_executed`` is True and both an alternative candidate and a real
        probe result are supplied. Artificial pivot counts are impossible by
        construction.
        """
        cand = self.candidates.get(candidate_id)
        if cand is None:
            cand = self.attach_candidate(
                candidate_id=candidate_id,
                title=detail or candidate_id,
                endpoint="/",
                category="general",
            )
        if outcome not in _PROBE_OUTCOMES:
            raise GapRunError(
                f"probe_outcome must be one of {list(_PROBE_OUTCOMES)}, got {outcome!r}"
            )
        if pivot_executed and (not alternative_candidate or not pivot_result):
            raise GapRunError("a pivot requires an alternative_candidate and a pivot_result")

        cand.attempts += 1
        cand.last_investigated_at = _now()
        if cand.status == "abandoned":
            pass
        elif outcome in ("blocked", "error"):
            cand.status = "blocked"
            cand.investigation_outcome = "blocked"
            if detail:
                cand.abandon_reason = detail
        elif outcome == "negative":
            if cand.attempts >= cand.max_attempts:
                cand.status = "abandoned"
                cand.investigation_outcome = "abandoned"
                cand.abandon_reason = retry_reason or f"Threshold {cand.max_attempts} reached"
                cand.abandoned_at = _now()
            elif cand.status == "discovered":
                cand.status = "investigated"
                cand.investigation_outcome = "attempting"
        elif cand.status == "discovered":
            cand.status = "investigated"
            cand.investigation_outcome = outcome

        entry = {
            "candidate_id": candidate_id,
            "outcome": outcome,
            "detail": detail,
            "retry_reason": retry_reason,
            "alternative_candidate": alternative_candidate,
            "pivot_executed": pivot_executed,
            "pivot_result": pivot_result,
            "at": _now(),
        }
        self.probe_outcomes.append(entry)
        self.decision_trace.append(entry)
        if pivot_executed:
            self.record_pivot(candidate_id, alternative_candidate, pivot_result, detail)
        self.save()
        return entry

    def record_pivot(
        self,
        candidate_id: str,
        alternative_candidate: str,
        result: str,
        detail: str = "",
    ) -> dict[str, Any]:
        """Record an actual pivot to an alternative candidate. Only this method
        increments the pivot count, so the count is always a real pivot."""
        if result not in _PIVOT_RESULTS:
            raise GapRunError(f"pivot_result must be one of {list(_PIVOT_RESULTS)}, got {result!r}")
        if not alternative_candidate:
            raise GapRunError("record_pivot requires an alternative_candidate")

        self.decision_trace.append(
            {
                "type": "pivot",
                "candidate_id": candidate_id,
                "alternative_candidate": alternative_candidate,
                "result": result,
                "detail": detail,
                "at": _now(),
            }
        )
        self.save()
        return {
            "candidate_id": candidate_id,
            "alternative_candidate": alternative_candidate,
            "result": result,
            "detail": detail,
            "pivot_executed": True,
        }

    def pivot_count(self) -> int:
        return sum(1 for e in self.decision_trace if e.get("type") == "pivot")

    # -- summaries for reporting -------------------------------------------

    @property
    def dispatched(self) -> int:
        return len(self.candidates)

    @property
    def investigated(self) -> int:
        return int(self.summary["candidates_investigated"])

    @property
    def not_tested(self) -> int:
        return int(self.summary["candidates_not_tested"])

    @property
    def blocked(self) -> int:
        return int(self.summary["candidates_blocked"])

    @property
    def summary(self) -> dict[str, Any]:
        total = len(self.candidates)
        # Accounting equation: dispatched is sum of investigated, not_tested, and blocked
        investigated = [
            c
            for c in self.candidates.values()
            if c.status in ("investigated", "validated", "abandoned")
            and c.investigation_outcome != "blocked"
        ]
        blocked = [
            c
            for c in self.candidates.values()
            if c.status in ("blocked", "unresolved") or c.investigation_outcome == "blocked"
        ]
        not_tested = [
            c for c in self.candidates.values() if c not in investigated and c not in blocked
        ]
        dispatched = total
        # Invariant must hold
        assert dispatched == len(investigated) + len(not_tested) + len(blocked)

        under_investigation = [c for c in self.candidates.values() if c.status == "investigated"]
        validated = [c for c in self.candidates.values() if c.status == "validated"]
        abandoned = [c for c in self.candidates.values() if c.status == "abandoned"]
        unresolved = [c for c in self.candidates.values() if c.status == "unresolved"]

        return {
            "candidates_identified": total,
            "candidates_dispatched": dispatched,
            "candidates_investigated": len(investigated),
            "candidates_blocked": len(blocked),
            "candidates_not_tested": len(not_tested),
            "invariant_holds": dispatched == (len(investigated) + len(not_tested) + len(blocked)),
            "candidates_under_investigation": len(under_investigation),
            "candidates_validated": len(validated),
            "candidates_abandoned": len(abandoned),
            "candidates_unresolved": len(unresolved),
            "discovered": [c.id for c in not_tested],
            "investigated": [c.id for c in investigated],
            "validated": [c.id for c in self.candidates.values() if c.status == "validated"],
            "abandoned": [c.id for c in self.candidates.values() if c.status == "abandoned"],
            "unresolved": [c.id for c in self.candidates.values() if c.status == "unresolved"],
            "blocked": [c.id for c in blocked],
            "pivots_executed": self.pivot_count(),
        }

    @property
    def decision_engine(self) -> Any:
        if self._decision_engine is None:
            self.sync_decision_engine()
        return self._decision_engine

    def sync_decision_engine(self, authorized_targets: list[str] | None = None) -> Any:
        """Create or synchronize a GAP-2 DecisionEngine matching this GapRun."""
        from strix.core.decision_engine.engine import DecisionEngine
        from strix.core.decision_engine.schemas import ActionCandidate, CandidateState

        if self._decision_engine is None:
            self._decision_engine = DecisionEngine(pivot_threshold=self.threshold)
        if authorized_targets is not None:
            self._decision_engine.authorized_targets = authorized_targets

        engine_cands = []
        for c in self.candidates.values():
            if c.status == "validated":
                st = CandidateState.VALIDATED
            elif c.status == "abandoned":
                st = CandidateState.ABANDONED
            elif c.status in ("blocked", "unresolved"):
                st = CandidateState.BLOCKED
            elif c.status == "investigated" or c.attempts > 0:
                st = CandidateState.ATTEMPTING
            else:
                st = CandidateState.PENDING

            engine_cands.append(
                ActionCandidate(
                    id=c.id,
                    name=c.title,
                    target=c.target or "",
                    endpoint=c.endpoint or "/",
                    attempts=c.attempts,
                    max_attempts=c.max_attempts,
                    state=st,
                    detail=c.investigation_outcome or "",
                    reproducible_request=c.reproducible_request or None,
                    reproducible_response=c.verification_response or None,
                    verification_procedure=c.verification_procedure or None,
                    demonstrated_impact=c.demonstrated_impact or None,
                    timestamp=c.last_investigated_at or None,
                )
            )
        self._decision_engine.initialize(engine_cands)
        return self._decision_engine

    def _record(self, event: str, **fields: Any) -> None:
        self.decision_trace.append({"type": event, **fields, "at": _now()})


class GapCandidate:
    """One GAP-1 candidate with its full lifecycle metadata."""

    def __init__(
        self,
        candidate_id: str,
        title: str,
        endpoint: str,
        category: str,
        score: float = 0.0,
        rank: int = 0,
        target: str = "",
        max_attempts: int = 2,
        attempts: int = 0,
    ):
        self.id = candidate_id
        self.title = title
        self.endpoint = endpoint
        self.category = category
        self.score = score
        self.rank = rank
        self.target = target
        self.max_attempts = max_attempts
        self.attempts = attempts
        self.status: str = "discovered"
        self.investigation_outcome: str = ""
        self.verification_evidence: str = ""
        self.verification_state: str = "candidate"
        self.reproducible_request: str = ""
        self.verification_response: str = ""
        self.verification_procedure: str = ""
        self.demonstrated_impact: str = ""
        self.evidence_timestamp: str = ""
        self.actual_impact: str = ""
        self.abandon_reason: str = ""
        self.abandoned_at: str | None = None
        self.last_investigated_at: str = ""
        self.discovered_at: str = _now()

    @classmethod
    def from_dict(cls, candidate_id: str, data: dict[str, Any]) -> GapCandidate:
        c = cls(
            candidate_id=candidate_id,
            title=str(data.get("title", "")),
            endpoint=str(data.get("endpoint", "")),
            category=str(data.get("category", "")),
            score=float(data.get("score", 0.0)),
            rank=int(data.get("rank", 0)),
            target=str(data.get("target", "")),
            max_attempts=int(data.get("max_attempts", 2)),
            attempts=int(data.get("attempts", 0)),
        )
        c.status = str(data.get("status", "discovered"))
        c.investigation_outcome = str(data.get("investigation_outcome", ""))
        c.verification_evidence = str(data.get("verification_evidence", ""))
        c.verification_state = str(data.get("verification_state", "candidate"))
        c.reproducible_request = str(data.get("reproducible_request", ""))
        c.verification_response = str(data.get("verification_response", ""))
        c.verification_procedure = str(data.get("verification_procedure", ""))
        c.demonstrated_impact = str(data.get("demonstrated_impact", ""))
        c.evidence_timestamp = str(data.get("evidence_timestamp", ""))
        c.actual_impact = str(data.get("actual_impact", ""))
        c.abandon_reason = str(data.get("abandon_reason", ""))
        c.abandoned_at = data.get("abandoned_at")
        c.last_investigated_at = str(data.get("last_investigated_at", ""))
        c.discovered_at = str(data.get("discovered_at", _now()))
        return c

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "endpoint": self.endpoint,
            "category": self.category,
            "score": self.score,
            "rank": self.rank,
            "target": self.target,
            "max_attempts": self.max_attempts,
            "attempts": self.attempts,
            "status": self.status,
            "investigation_outcome": self.investigation_outcome,
            "verification_evidence": self.verification_evidence,
            "verification_state": self.verification_state,
            "reproducible_request": self.reproducible_request,
            "verification_response": self.verification_response,
            "verification_procedure": self.verification_procedure,
            "demonstrated_impact": self.demonstrated_impact,
            "evidence_timestamp": self.evidence_timestamp,
            "actual_impact": self.actual_impact,
            "abandon_reason": self.abandon_reason,
            "abandoned_at": self.abandoned_at,
            "last_investigated_at": self.last_investigated_at,
            "discovered_at": self.discovered_at,
        }
