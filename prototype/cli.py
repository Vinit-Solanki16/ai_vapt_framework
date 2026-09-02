"""Mentor-facing CLI for the decision engine prototype.

Usage:
    python prototype/cli.py run --scenario success --max-attempts 2
    python prototype/cli.py run --scenario failure_pivot --max-attempts 2
    python prototype/cli.py run --scenario multi_candidate --max-attempts 2
    python prototype/cli.py run --corpus --max-attempts 2
    python prototype/cli.py run --scenario success --mode lab --target 172.28.0.2 --port 8080

Supports:
- Scenario selection (success / failure_pivot / multi_candidate / corpus)
- Execution mode (simulation / lab)
- Lab mode targets the Docker emulator (OBSERVED outcomes)
"""

from __future__ import annotations

import argparse
import os
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
    print("SAFETY / EVIDENCE TIER")
    print("=" * 64)
    if mode == "lab":
        print("LAB MODE (OBSERVED)")
        print("Outcomes are observed from the Docker emulator (real HTTP responses).")
        print("Target is allowlisted. No external targets contacted.")
    else:
        print("SIMULATION MODE")
        print("Outcomes are resolved from supplied demo ground truth.")
        print("No external targets contacted. No real vulnerabilities validated.")
    print("=" * 64)


def _run_scenario(
    scenario_name: str,
    max_attempts: int,
    mode: str = "simulation",
    target: str | None = None,
    port: int = 8080,
    assessor: str = "deterministic",
    scan_file: str | None = None,
) -> dict:
    if scan_file:
        from decision_engine.adapters.scan_adapter import candidates_from_scan, candidates_to_scenario
        candidates = candidates_to_scenario(candidates_from_scan(scan_file))
        scenario_name = f"scan:{os.path.basename(scan_file)}"
    elif scenario_name in SCENARIOS:
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

    # Build executor kwargs based on mode
    executor_kwargs = {}
    if mode == "lab":
        if target is None:
            print(
                "--target is required for lab mode (e.g., --target 172.28.0.2)",
                file=sys.stderr,
            )
            sys.exit(1)
        
        # Explicit allowlist validation before creating executor
        from prototype.lab_runner import _validate_target
        try:
            _validate_target(target)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(400)

        from prototype.execution_layer import create_lab_executor

        executor_kwargs["executor"] = create_lab_executor(target, port)

    final_state = run_decision_scenario(
        candidates,
        max_attempts=max_attempts,
        mode=mode,
        executor=executor_kwargs.get("executor"),
        assessor=assessor,
    )

    _display_output(scenario_name, final_state, max_attempts, mode)

    json_path = f"./report_{scenario_name}_vapt.json"
    txt_path = f"./report_{scenario_name}_vapt.txt"
    save_json_report(scenario_name, final_state, json_path, max_attempts, mode)
    save_text_report(scenario_name, final_state, txt_path, max_attempts, mode)

    print(f"\nReports written: {json_path}, {txt_path}")

    return final_state


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
        "--scan", "-S",
        default=None,
        help="Path to scan file (Nmap XML/JSON or custom JSON). Overrides --scenario.",
    )
    run_parser.add_argument(
        "--max-attempts", "-m",
        type=int,
        default=2,
        help="Maximum attempts per candidate before pivot",
    )
    run_parser.add_argument(
        "--mode", "-M",
        choices=["simulation", "lab"],
        default="simulation",
        help="Execution mode: simulation (default) or lab (Docker emulator, OBSERVED)",
    )
    run_parser.add_argument(
        "--assessor", "-a",
        choices=["deterministic", "llm"],
        default="deterministic",
        help="Assessor: deterministic (default, offline) or llm (requires Ollama)",
    )
    run_parser.add_argument(
        "--target", "-t",
        default=None,
        help="Lab target IP (required for lab mode). Allowlisted: 127.0.0.1, 172.28.0.2",
    )
    run_parser.add_argument(
        "--port", "-p",
        type=int,
        default=8080,
        help="Lab target port (default: 8080)",
    )

    run_parser.add_argument(
        "--checkpoint", "-c",
        default=None,
        help="Path to save checkpoint after run (e.g., ./ckpt.json)",
    )

    resume_parser = sub.add_parser("resume", help="Resume from checkpoint")
    resume_parser.add_argument(
        "--path", "-p",
        required=True,
        help="Path to checkpoint file to resume from",
    )

    version_parser = sub.add_parser("version", help="Print version")

    args = parser.parse_args()

    if args.command == "version":
        from prototype import __version__
        print(f"AI VAPT Prototype v{__version__}")
        return

    if args.command == "run":
        if args.scenario is None and args.scan is None:
            print("--scenario or --scan is required for 'run' command", file=sys.stderr)
            sys.exit(1)
        final_state = _run_scenario(
            args.scenario,
            args.max_attempts,
            mode=args.mode,
            target=args.target,
            port=args.port,
            assessor=args.assessor,
            scan_file=args.scan,
        )
        if args.checkpoint and final_state:
            from prototype.checkpoints import save_run_checkpoint
            save_run_checkpoint(final_state, args.checkpoint)
            print(f"Checkpoint saved: {args.checkpoint}")

    elif args.command == "resume":
        _resume_from_checkpoint(args.path)


def _resume_from_checkpoint(checkpoint_path: str) -> None:
    """Resume a run from a checkpoint file."""
    from prototype.checkpoints import resume_from_checkpoint
    from prototype.report_generator import save_json_report, save_text_report
    from prototype.trace_formatter import format_engine_trace, format_candidate_ranking, format_execution_results
    from decision_engine.core.engine import build_graph, initial_state, EngineStatus

    state = resume_from_checkpoint(checkpoint_path)

    # Display the resumed state
    print("\n" + "=" * 64)
    print("AI VAPT DECISION ENGINE — RESUMED FROM CHECKPOINT")
    print("=" * 64)
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Status: {state.get('status', 'UNKNOWN')}")
    print(f"Current index: {state.get('current_index', 0)}")
    print(f"Attempt count: {state.get('attempt_count', 0)}")
    print()

    print("CANDIDATE RANKING")
    print("-" * 40)
    print(format_candidate_ranking(state))
    print()

    print("DECISION TRACE")
    print("-" * 40)
    print(format_engine_trace(state))
    print()

    # Save reports
    json_path = f"./report_resumed_vapt.json"
    txt_path = f"./report_resumed_vapt.txt"
    save_json_report("resumed", state, json_path, state.get("max_attempts", 2), state.get("mode", "simulation"))
    save_text_report("resumed", state, txt_path, state.get("max_attempts", 2), state.get("mode", "simulation"))
    print(f"\nReports written: {json_path}, {txt_path}")


if __name__ == "__main__":
    main()
