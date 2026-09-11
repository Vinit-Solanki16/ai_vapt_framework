"""Mentor-facing CLI for the decision engine prototype.

Uses the canonical VAPTApplication workflow service.
"""
from __future__ import annotations

import argparse
import sys

from vapt_platform.application import VAPTRequest, get_application
from prototype.report_generator import (
    save_json_report,
    save_text_report,
)
from prototype.trace_formatter import (
    format_candidate_ranking,
    format_engine_trace,
    format_execution_results,
)


def _display_output(
    scenario_name: str,
    result,
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

    # Access domain result
    domain = result.domain if hasattr(result, 'domain') else result

    print("CANDIDATE RANKING")
    print("-" * 40)
    # Reconstruct final_state from result for trace formatters
    final_state = {
        "candidates": domain.candidates,
        "results": domain.execution_results,
        "logs": domain.decision_trace,
        "_presentation": {
            "total_attempts": domain.total_attempts,
            "pivot_count": domain.pivot_count,
            "candidates_processed": domain.candidates_processed,
        },
    }
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
    print(f"Status:         {domain.final_status}")
    print(f"Total Attempts: {domain.total_attempts}")
    print(f"Pivot Count:    {domain.pivot_count}")
    cids = domain.candidates_processed
    print(f"Candidates Processed: {len(cids)} ({', '.join(cids) if cids else '(none)'})")
    print()

    print("=" * 64)
    print("SAFETY / EVIDENCE TIER")
    print("=" * 64)
    if mode == "lab":
        print("LAB MODE (DOCKER OBSERVED)")
        print("Outcomes are observed from the Docker-isolated emulator (real HTTP responses).")
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
    path: str = "/vuln",
    assessor: str = "deterministic",
    scan_file: str | None = None,
) -> dict:
    # Explicit allowlist validation for lab mode (fail-closed)
    if mode == "lab" and target:
        from prototype.lab_runner import _validate_target
        try:
            _validate_target(target)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(400)

    # Build unified request
    request = VAPTRequest(
        scenario=scenario_name,
        mode=mode,
        target=target,
        port=port,
        path=path,
        assessor_mode="ai" if assessor == "llm" else "deterministic",
        max_attempts=max_attempts,
        scan_file=scan_file,
    )

    # Run canonical workflow
    application = get_application()
    result = application.run(request)

    # Display output
    _display_output(scenario_name, result, max_attempts, mode)

    # Save reports
    domain = result.domain if hasattr(result, 'domain') else result
    json_path = f"./report_{scenario_name}_vapt.json"
    txt_path = f"./report_{scenario_name}_vapt.txt"
    save_json_report(scenario_name, {
        "candidates": domain.candidates,
        "results": domain.execution_results,
        "logs": domain.decision_trace,
        "_presentation": {
            "total_attempts": domain.total_attempts,
            "pivot_count": domain.pivot_count,
            "candidates_processed": domain.candidates_processed,
        },
    }, json_path, max_attempts, mode)
    save_text_report(scenario_name, {
        "candidates": domain.candidates,
        "results": domain.execution_results,
        "logs": domain.decision_trace,
        "_presentation": {
            "total_attempts": domain.total_attempts,
            "pivot_count": domain.pivot_count,
            "candidates_processed": domain.candidates_processed,
        },
    }, txt_path, max_attempts, mode)

    print(f"\nReports written: {json_path}, {txt_path}")

    return {
        "run_id": domain.run_id,
        "status": domain.final_status,
        "candidates": domain.candidates,
        "execution_results": domain.execution_results,
        "decision_trace": domain.decision_trace,
        "total_attempts": domain.total_attempts,
        "pivot_count": domain.pivot_count,
        "candidates_processed": domain.candidates_processed,
        "evidence_tier": domain.evidence_tier,
        "assessment": domain.assessment,
        "safety_notice": domain.safety_notice,
        "report": result.report if hasattr(result, 'report') else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI VAPT Decision Engine — Mentor Prototype CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run a scenario")
    run_parser.add_argument(
        "--scenario", "-s",
        default="failure_pivot",
        help="Scenario name (success, failure_pivot, multi_candidate, docker_vuln, docker_fail, docker_pivot, docker_multi, or corpus)",
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
        help="Execution mode: simulation (default) or lab (Docker emulator, DOCKER OBSERVED)",
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
        "--path", "-P",
        default="/vuln",
        help="Lab target path (default: /vuln)",
    )

    version_parser = sub.add_parser("version", help="Print version")

    resume_parser = sub.add_parser("resume", help="Resume from checkpoint")
    resume_parser.add_argument(
        "--path", "-p",
        required=True,
        help="Path to checkpoint file to resume from",
    )

    args = parser.parse_args()

    if args.command == "version":
        from prototype import __version__
        print(f"AI VAPT Prototype v{__version__}")
        return

    if args.command == "run":
        _run_scenario(
            args.scenario,
            args.max_attempts,
            mode=args.mode,
            target=args.target,
            port=args.port,
            path=args.path,
            assessor=args.assessor,
            scan_file=args.scan,
        )

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
