# Prototype Development Baseline

This document is the canonical entry point for all future prototype and
development work. It is intentionally separate from the Golden Baseline
manifest and exists only on the development branch.

## 1. Development branch

`prototype-development`

## 2. Golden Baseline tag

`reference-engine-prequalification-2026-09-01`

## 3. Golden Baseline commit

`4dc059916f3c0b36b35ec7914ca52f1f2bb09393` (short: `4dc0599`)

## 4. Development starting commit

`1cdfa0098c949b39ecd0b69b1ce5e68a7b6a7479` (the documentation-only
manifest commit that was authored *after* the Golden Baseline tag, while
still on `master`)

## 5. Date

`2026-09-01`

## 6. Derivation

The `prototype-development` branch was branched from `master` immediately
after the post-baseline documentation commit `1cdfa00`. At the moment
of branching, `git diff reference-engine-prequalification-2026-09-01`
produced no differences in the frozen engine, tests, datasets, or
benchmark directories.

## 7. Frozen engine identity (verified at branch creation)

`git diff reference-engine-prequalification-2026-09-01 -- \
    decision_engine/core/ decision_engine/adapters/ \
    decision_engine/benchmarks/ tests/ decision_engine/tests/ \
    datasets/`

returned an empty diff. The `prototype-development` branch therefore
contains the **byte-identical** engine implementation as the Golden
Baseline at `4dc0599`.

## 8. The Golden Baseline must never be modified

`reference-engine-prequalification-2026-09-01` continues to point to
`4dc059916f3c0b36b35ec7914ca52f1f2bb09393` and must remain immutable.
The Golden Baseline manifest is at
`docs/project_management/REFERENCE_ENGINE_BASELINE.md` and is not
modified from this branch.

## 9. Scope statement

The `prototype-development` branch is a development copy. It is
intentionally outside the frozen research reference implementation. Any
change to engine source, tests, datasets, or benchmark logic that the
user makes in this branch:

- must be a deliberate, reviewed prototype change,
- must not be reflected back into the Golden Baseline tag, and
- must not be presented as research evidence unless explicitly
  re-verified and re-tagged.

## 10. Development rules

- No second importable Python package may be created under a name that
  shadows `decision_engine`. New modules must live under a clearly
  named subtree (e.g. `prototype/`, `frontend/`, `services/`) and must
  import `decision_engine` explicitly.
- The frozen engine directories
  (`decision_engine/core/`, `decision_engine/adapters/`,
  `decision_engine/benchmarks/`, `tests/`,
  `decision_engine/tests/`, `datasets/`) may only be modified as part
  of a reviewed prototype change. The Golden Baseline remains a clean
  reference to the pre-change engine state.
- PYTHONPATH must remain set to `/home/vinit/ai_vapt_framework` for the
  test suite and the existing benchmarks to import correctly.
- Any regression in the existing 55/55 test result or the documented
  benchmark decomposition values must be reported before further
  development proceeds.

## 11. Current test status (development branch, no changes applied)

- TRACK0 (`pytest tests/ -q`): **39 passed**
- TRACK1 (`pytest decision_engine/tests/ -q`): **16 passed**
- Combined (`pytest decision_engine/tests/ tests/ -q`): **55 passed**

## 12. Current benchmark reference values (development branch)

- VAPT (`fair_vapt_benchmark.py --seeds 30 --caps 1 2 3 5`)
  - T=2 pivot: **+77.0**
  - T=5 pivot: **+200.0**
  - Gap-1 priority: **+0.0** at every measured cap
- Synthetic (`fair_benchmark.py --families sparse_success --caps 5 --seeds 30`)
  - sparse_success T=5 pivot: **+772.1**

## 13. No prototype development has begun

This branch is a clean starting point only. No UI, frontend, backend,
Nmap integration, Nuclei integration, LLM integration, autonomous
scanner, exploitation logic, report generation, new agent, or new
decision logic has been implemented in this task. The next task will
design the mentor-facing prototype architecture and implementation plan
based on the frozen decision engine.

## 14. Verification commands

```
git rev-parse reference-engine-prequalification-2026-09-01^{commit}
# expected: 4dc059916f3c0b36b35ec7914ca52f1f2bb09393

git branch --show-current
# expected: prototype-development

git diff reference-engine-prequalification-2026-09-01 -- \
    decision_engine/core/ decision_engine/adapters/ \
    decision_engine/benchmarks/ tests/ decision_engine/tests/ \
    datasets/
# expected: empty
```
