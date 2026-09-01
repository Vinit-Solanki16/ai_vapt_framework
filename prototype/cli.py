"""Mentor-facing CLI for the decision engine prototype.

Usage:
    python prototype/cli.py run --scenario success --max-attempts 2
    python prototype/cli.py run --scenario failure_pivot --max-attempts 2
    python prototype/cli.py run --scenario multi_candidate --max-attempts 2
    python prototype/cli.py run --corpus --max-attempts 2

Supports:
- Scenario selection (success / failure_pivot / multi_candidate)
- Corpus mode (from VAPT data via adapter)
- Simulation mode (no external network access)
"""

from __future__ import annotations

import argparse
import sys

from prototype.demo_data import SCENARIOS
from prototype.engine_integration import (
    load_vapt_corpus_scenario,
    run_decision_scenario,
    validate_scenario,
)
from prototype.report_generator import (
    save_json_report,
    save_text_report,
)
from prototype.trace_formatter import (
    format_candidate_ranking,
    format_engine_trace,
    format_execution_results,
)


def _validate_scenario(candidates: list) -> None:
    try:
        validate_scenario(candidates)
    except ValueError as e:
        print(f"Invalid scenario: {e}", file=sys.stderr)
        sys.exit(1)


def _display_output(
    scenario_name: str,
    final_state: dict,
    max_attempts: int,
    mode: str,
) -> None:
    print("\n" + "=" * 64)
    print("AI VAPT DECISION ENGINE — MENTOR PROTOTYPE")
    print("=" * 64)
    print(f"Scenario:  {scenario_name}")
    print(f"Mode:      {mode}")
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


def _run_scenario(scenario_name: str, max_attempts: int, mode: str = "simulation") -> None:
    if scenario_name in SCENARIOS:
        fn, kwargs = SCENARIOS[scenario_name]
        candidates = fn(**kwargs)
    elif scenario_name == "corpus":
        candidates = load_vapt_corpus_scenario()
    else:
        print(
            f"Unknown scenario: {scenario_name!r}. "
            f"Choose from: {', '.join(list(SCENARIOS.keys()) + ['corpus'])}",
            file=sys.stderr,
        )
        sys.exit(1)

    _validate_scenario(candidates)

    final_state = run_decision_scenario(
        candidates,
        max_attempts=max_attempts,
        mode=mode,
    )

    _display_output(scenario_name, final_state, max_attempts, mode)

    json_path = f"./report_{scenario_name}_vapt.json"
    txt_path = f"./report_{scenario_name}_vapt.txt"
    save_json_report(scenario_name, final_state, json_path, max_attempts, mode)
    save_text_report(scenario_name, final_state, txt_path, max_attempts, mode)

    print(f"\nReports written: {json_path}, {txt_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI VAPT Decision Engine — Mentor Prototype CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run a scenario")
    run_parser.add_argument(
        "--scenario", "-s",
        choices=list(SCENARIOS.keys()) + ["corpus"],
        help="Scenario name: success, failure_pivot, multi_candidate, or corpus",
    )
    run_parser.add_argument(
        "--max-attempts", "-m",
        type=int,
        default=2,
        help="Maximum attempts per candidate before pivot",
    )

    version_parser = sub.add_parser("version", help="Print version")

    args = parser.parse_args()

    if args.command == "version":
        from prototype import __version__
        print(f"AI VAPT Prototype v{__version__}")
        return

    if args.command == "run":
        if args.scenario is None:
            print("--scenario is required for 'run' command", file=sys.stderr)
            sys.exit(1)
        _run_scenario(args.scenario, args.max_attempts)


if __name__ == "__main__":
    main()