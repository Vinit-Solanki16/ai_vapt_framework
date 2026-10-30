#!/usr/bin/env python3
"""Run the full AI-VAPT experiment suite and save results."""
from __future__ import annotations

import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from experiments.harness import run_full_suite


def main():
    print("=" * 60)
    print("AI-VAPT Research Experiment Suite")
    print("=" * 60)
    print()

    results = run_full_suite()

    print()
    print("=" * 60)
    print(f"Completed {len(results)} experiments")
    print("Results saved to: experiments/results/")
    print("=" * 60)

    # Summary
    print()
    print("Summary:")
    for name, res_list in results.items():
        r = res_list[0]
        print(f"  {name}: attempts={r.total_attempts}, pivots={r.pivot_count}, status={r.final_status}")


if __name__ == "__main__":
    main()