"""Decision intelligence for transparent candidate scoring.

Provides explainable scoring that factors in:
- Base probability (EPSS)
- Severity (CVSS, KEV)
- Asset exposure (from graph)
- AI assessment quality

Every score is transparent and explainable. No opaque "AI scores."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from vapt_platform.normalization import severity_rank


# ---------------------------------------------------------------------------
# Scoring factors
# ---------------------------------------------------------------------------

@dataclass
class ScoreFactors:
    """Transparent scoring factors for a candidate.

    Each factor is 0.0 to 1.0. The final score is a weighted combination.
    """
    base_probability: float = 0.0
    severity_score: float = 0.0
    kev_boost: float = 0.0
    asset_exposure: float = 0.0
    ai_quality: float = 0.0
    final_score: float = 0.0
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_probability": round(self.base_probability, 4),
            "severity_score": round(self.severity_score, 4),
            "kev_boost": round(self.kev_boost, 4),
            "asset_exposure": round(self.asset_exposure, 4),
            "ai_quality": round(self.ai_quality, 4),
            "final_score": round(self.final_score, 4),
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Decision intelligence
# ---------------------------------------------------------------------------

class DecisionIntelligence:
    """Transparent decision scoring for VAPT candidates.

    Computes explainable scores using multiple factors.
    Does NOT modify the frozen Gap-2 mechanism.
    """

    # Weights for each factor (sum to 1.0)
    WEIGHTS = {
        "base_probability": 0.30,
        "severity": 0.25,
        "kev": 0.15,
        "asset_exposure": 0.15,
        "ai_quality": 0.15,
    }

    def compute_score(
        self,
        candidate: dict,
        graph: Any = None,
    ) -> ScoreFactors:
        """Compute transparent score for a candidate.

        Args:
            candidate: Candidate dict with metadata
            graph: Optional VAPTGraph for asset exposure

        Returns:
            ScoreFactors with all factor values
        """
        factors = ScoreFactors()
        metadata = candidate.get("metadata", {})

        # Base probability (EPSS)
        factors.base_probability = float(candidate.get("probability", 0.0))

        # Severity score (CVSS/KEV-based)
        severity = metadata.get("severity", "unknown")
        cvss = metadata.get("cvss_score")
        factors.severity_score = self._severity_to_score(severity, cvss)

        # KEV boost
        factors.kev_boost = 1.0 if metadata.get("cisa_kev", False) else 0.0

        # Asset exposure (from graph)
        if graph is not None:
            factors.asset_exposure = self._compute_asset_exposure(candidate, graph)

        # AI quality (from assessment)
        quality = candidate.get("quality_rank")
        factors.ai_quality = self._quality_to_score(quality)

        # Final score (weighted combination)
        factors.final_score = (
            self.WEIGHTS["base_probability"] * factors.base_probability
            + self.WEIGHTS["severity"] * factors.severity_score
            + self.WEIGHTS["kev"] * factors.kev_boost
            + self.WEIGHTS["asset_exposure"] * factors.asset_exposure
            + self.WEIGHTS["ai_quality"] * factors.ai_quality
        )

        # Build explanation
        factors.explanation = self._build_explanation(factors, metadata)

        return factors

    def rank_candidates(
        self,
        candidates: list[dict],
        graph: Any = None,
    ) -> list[tuple[dict, ScoreFactors]]:
        """Rank candidates by transparent score.

        Args:
            candidates: List of candidate dicts
            graph: Optional VAPTGraph

        Returns:
            List of (candidate, score_factors) sorted by final_score descending
        """
        scored = []
        for c in candidates:
            factors = self.compute_score(c, graph=graph)
            scored.append((c, factors))

        # Sort by final score descending
        scored.sort(key=lambda x: x[1].final_score, reverse=True)
        return scored

    def _severity_to_score(self, severity: str, cvss: Optional[float]) -> float:
        """Convert severity to 0-1 score."""
        if cvss is not None:
            return min(cvss / 10.0, 1.0)

        severity_map = {
            "critical": 1.0,
            "high": 0.75,
            "medium": 0.5,
            "low": 0.25,
            "informational": 0.1,
            "none": 0.0,
            "unknown": 0.0,
        }
        return severity_map.get(severity.lower(), 0.0)

    def _compute_asset_exposure(self, candidate: dict, graph: Any) -> float:
        """Compute asset exposure score from graph.

        Higher score = more exposed/important asset.
        """
        if graph is None:
            return 0.0

        host = candidate.get("host", "")
        if not host:
            return 0.0

        # Check if host is in graph
        host_id = f"host:{host}"
        if not graph.has_node(host_id):
            return 0.0

        # Count vulnerabilities on this host
        vulns = graph.get_critical_vulns(host, min_severity="low")
        if not vulns:
            return 0.1

        # More vulns = higher exposure
        return min(0.1 + 0.1 * len(vulns), 1.0)

    def _quality_to_score(self, quality: Optional[str]) -> float:
        """Convert quality rank to 0-1 score."""
        if quality is None:
            return 0.0
        quality_map = {
            "HIGH": 1.0,
            "MEDIUM": 0.6,
            "LOW": 0.3,
            "NONE": 0.0,
        }
        return quality_map.get(quality.upper(), 0.0)

    def _build_explanation(self, factors: ScoreFactors, metadata: dict) -> str:
        """Build human-readable explanation for the score."""
        parts = []

        if factors.base_probability > 0:
            parts.append(f"EPSS={factors.base_probability:.2f}")

        if factors.severity_score > 0:
            severity = metadata.get("severity", "unknown")
            parts.append(f"severity={severity}")

        if factors.kev_boost > 0:
            parts.append("KEV=yes")

        if factors.asset_exposure > 0:
            parts.append(f"exposure={factors.asset_exposure:.2f}")

        if factors.ai_quality > 0:
            parts.append(f"AI_quality={factors.ai_quality:.2f}")

        if not parts:
            return "No intelligence available"

        return " | ".join(parts)


# Singleton instance
_decision_intelligence = DecisionIntelligence()


def get_decision_intelligence() -> DecisionIntelligence:
    """Get the singleton decision intelligence instance."""
    return _decision_intelligence
