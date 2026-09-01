"""One-command demonstration of the mentor-facing prototype.

Runs the strongest scenario (failure_pivot) by default,
because this most clearly demonstrates the research contribution:
bounded failure → pivot → next candidate → success → completion.

This script uses the real decision_engine.run_engine() —
no simulated engine, no faked output.
"""

from __future__ import annotations

import sys

from prototype.demo_data import failure_pivot_scenario, success_scenario, multi_candidate_scenario
from prototype.engine_integration import run_decision_scenario
from prototype.report_generator import save_text_report, save_json_report
from prototype.trace_formatter import format_engine_trace, format_candidate_ranking, format_execution_results


DEFAULT_SCENARIO = "failure_pivot"


def run_demo(scenario_name: str = DEFAULT_SCENARIO, max_attempts: int = 2) -> dict:
    """Run a demo scenario through the real engine and display results.

    Args:
        scenario_name: Name of the scenario to run
        max_attempts: Pivot threshold

    Returns:
        Final engine state dict
    """
    scenarios = {
        "success": success_scenario,
        "failure_pivot": failure_pivot_scenario,
        "multi_candidate": multi_candidate_scenario,
    }

    if scenario_name not in scenarios:
        print(f"Unknown scenario: {scenario_name!r}. Choose from {list(scenarios.keys())}")
        sys.exit(1)

    candidates = scenarios[scenario_name]()

    # Run through the real engine
    final_state = run_decision_scenario(
        candidates,
        max_attempts=max_attempts,
        mode="simulation",
    )

    # Display mentor-readable output
    _display_output(scenario_name, final_state, max_attempts)

    # Save reports
    json_path = f"./demo_report_{scenario_name}_vapt.json"
    txt_path = f"./demo_report_{scenario_name}_vapt.txt"
    save_json_report(scenario_name, final_state, json_path, max_attempts, "simulation")
    save_text_report(scenario_name, final_state, txt_path, max_attempts, "simulation")

    print(f"\nReports written: {json_path}, {txt_path}")
    return final_state


def _display_output(scenario_name: str, final_state: dict, max_attempts: int) -> None:
    """Display mentor-readable output for the demo."""
    print("\n" + "=" * 64)
    print("AI VAPT DECISION ENGINE — MENTOR PROTOTYPE — LIVE DEMO")
    print("=" * 64)
    print(f"Scenario:  {scenario_name}")
    print(f"Mode:      simulation")
    print(f"Max Attempts: {max_attempts}")
    print()

    print("CANDIDATE RANKING")
    print("-" * 40)
    print(format_candidate_ranking(final_state))
    print()

    print("ENGINE EXECUTION")
    print("-" * 40)
    print(format_execution_results(final_state))
    print()

    print("DECISION TRACE")
    print("-" * 40)
    print(format_engine_trace(final_state))
    print()

    print("FINAL RESULT")
    print("-" * 40)
    status = final_state.get("status", "UNKNOWN")
    presentation = final_state.get("_presentation", {})
    print(f"Status:         {status}")
    print(f"Total Attempts: {presentation.get('total_attempts', 0)}")
    print(f"Pivot Count:    {presentation.get('pivot_count', 0)}")
    cids = presentation.get("candidates_processed", [])
    print(f"Candidates Processed: {len(cids)} ({', '.join(cids) if cids else '(none)'})")
    print()

    print("=" * 64)
    print("SAFETY")
    print("=" * 64)
    print("SIMULATION MODE")
    print("Outcomes are resolved from supplied demo ground truth.")
    print("No external targets contacted. No real vulnerabilities validated.")
    print("=" * 64)


if __name__ == "__main__":
    import sys as _sys
    scenario = _sys.argv[1] if len(_sys.argv) > 1 else DEFAULT_SCENARIO
    max_attempts = int(_sys.argv[2]) if len(_sys.argv) > 2 else 2
    run_demo(scenario_name=scenario, max_attempts=max_attempts)