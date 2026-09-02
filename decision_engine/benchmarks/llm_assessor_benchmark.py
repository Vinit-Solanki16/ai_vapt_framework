"""LLM Assessor Benchmark — Measures LLM assessor quality against VAPT corpus labels.

Runs the LLM assessor on each CVE in the VAPT corpus, compares the predicted
usability_rank with the corpus's reliability label, and computes accuracy.
"""

import json
import statistics
from pathlib import Path
from typing import Dict, List, Tuple

from decision_engine.adapters.vapt_adapter import vapt_assess_fn
from decision_engine.core.schemas import ActionCandidate, QualityRank


def load_corpus_labels() -> Dict[str, dict]:
    """Load the VAPT corpus labels from data/poc_corpus/labels.json."""
    labels_path = Path(__file__).parent.parent.parent / "data" / "poc_corpus" / "labels.json"
    with open(labels_path) as f:
        return json.load(f)


def load_correspondence() -> Dict[str, str]:
    """Map CVE ID to its ground-truth reliability label.

    The reliability field in labels.json ('HIGH', 'MEDIUM', 'LOW') serves as
    the gold standard for assessing the LLM assessor.
    """
    labels = load_corpus_labels()
    return {cve: labels[cve]["reliability"] for cve in labels}


def predict_usability_rank(cve_id: str) -> QualityRank:
    """Run the LLM assessor on a single CVE and return its usability_rank.

    Args:
        cve_id: The CVE identifier (e.g., 'CVE-2021-44228').

    Returns:
        QualityRank.HIGH, QualityRank.MEDIUM, or QualityRank.LOW.
    """
    assess_fn = vapt_assess_fn(use_llm=True)
    candidate = ActionCandidate(id=cve_id, probability=0.5)
    return assess_fn(candidate)


def compute_accuracy(
    cves: List[str],
    predictions: List[QualityRank],
    reliabilities: List[str]
) -> Dict[str, float]:
    """Compute classification accuracy comparing predictions to ground truth.

    Args:
        cves: List of CVE identifiers.
        predictions: List of QualityRank values from the assessor.
        reliabilities: List of ground-truth reliability strings ('HIGH', 'MEDIUM', 'LOW').

    Returns:
        Dictionary mapping each CVE to its accuracy (0.0–1.0).
    """
    accuracies = {}
    for cve, pred, rel in zip(cves, predictions, reliabilities):
        # Map usability_rank to numeric quality for comparison
        pred_num = {
            QualityRank.HIGH: 1.0,
            QualityRank.MEDIUM: 0.6,
            QualityRank.LOW: 0.3,
        }.get(pred, 0.0)
        rel_num = {
            "HIGH": 1.0,
            "MEDIUM": 0.6,
            "LOW": 0.3,
        }.get(rel, 0.0)
        # Correct prediction if the numerical quality matches
        correct = abs(pred_num - rel_num) < 0.001
        accuracies[cve] = correct
    return accuracies


def run_llm_assessor_benchmark() -> dict:
    """Main entry point for the benchmark.

    Loads the VAPT corpus, runs the LLM assessor on each CVE, and computes
    accuracy against the ground-truth reliability labels.

    Returns:
        A dictionary with keys:
        - 'cves': list of CVE identifiers
        - 'predictions': list of QualityRank values
        - 'accuracies': dict mapping CVE -> accuracy (bool)
        - 'overall_accuracy': float (average accuracy across all CVEs)
    """
    # Load ground-truth reliability from the VAPT corpus labels
    reliabilities = load_correspondence()
    
    # Get all CVE identifiers from the labels
    cves = list(reliabilities.keys())
    
    # Run the LLM assessor on each CVE
    predictions = []
    for cve in cves:
        pred = predict_usability_rank(cve)
        predictions.append(pred)
    
    # Compute accuracy
    accuracies = compute_accuracy(cves, predictions, reliabilities)
    
    # Calculate overall accuracy (fraction of correct predictions)
    overall = sum(1 for acc in accuracies.values() if acc) / len(cves)
    
    return {
        "cves": cves,
        "predictions": predictions,
        "accuracies": accuracies,
        "overall_accuracy": round(overall, 4),
    }


if __name__ == "__main__":
    result = run_llm_assessor_benchmark()
    print(json.dumps(result, indent=2))
