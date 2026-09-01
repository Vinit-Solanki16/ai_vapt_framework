# Reference Engine Baseline Manifest

This document records the verified, frozen state of the reference engine
immediately prior to any further prototype or development work. It is the
canonical evidence anchor for the prequalification baseline.

## 1. Baseline name

`reference-engine-prequalification-2026-09-01`

## 2. Git commit

`4dc059916f3c0b36b35ec7914ca52f1f2bb09393` (short: `4dc0599`)

## 3. Git tag

`reference-engine-prequalification-2026-09-01` (annotated tag pointing to
`4dc059916f3c0b36b35ec7914ca52f1f2bb09393`)

## 4. Date

`2026-09-01`

## 5. Python version

`Python 3.10.12`

## 6. pytest version

`pytest 9.1.1`

## 7. PYTHONPATH requirement

`PYTHONPATH=/home/vinit/ai_vapt_framework` is required for both the test
suite and all benchmark invocations. The repository root must appear on
`PYTHONPATH` so that the top-level `decision_engine` package is
importable.

## 8. TRACK0 result

`pytest tests/ -q` -> `39 passed`

## 9. TRACK1 result

`pytest decision_engine/tests/ -q` -> `16 passed`

## 10. Combined result

`pytest decision_engine/tests/ tests/ -q` -> `55 passed in 0.23s`

## 11. VAPT benchmark command

```
PYTHONPATH=/home/vinit/ai_vapt_framework \
python decision_engine/benchmarks/fair_vapt_benchmark.py \
  --seeds 30 --caps 1 2 3 5
```

## 12. VAPT +77/+200 results

`fair_vapt_benchmark.py` is the VAPT-domain benchmark. Verified
decomposition output:

| Cap T | priority (Gap-1) | pivot (Gap-2) | total |
|------:|-----------------:|--------------:|------:|
| 1     | +0.0             | +36.0         | +36.0 |
| 2     | +0.0             | +77.0         | +77.0 |
| 3     | +0.0             | +118.0        | +118.0|
| 5     | +0.0             | +200.0        | +200.0|

- VAPT T=2 pivot component: **+77.0**
- VAPT T=5 pivot component: **+200.0**

## 13. Gap-1 = 0

The priority (Gap-1) component of the VAPT decomposition is **+0.0** at
every measured cap T in {1, 2, 3, 5}. This is an honest, negative result:
priority-only ranking does not improve on dumb enumeration in this
benchmark.

## 14. Synthetic sparse_success +772.1

`fair_benchmark.py` is the synthetic-domain benchmark. Verified with:

```
PYTHONPATH=/home/vinit/ai_vapt_framework \
python -m decision_engine.benchmarks.fair_benchmark \
  --families sparse_success --caps 5 --seeds 30
```

At T=5 the pivot component over the `sparse_success` family is **+772.1**.
This benchmark is provided as a synthetic sanity-check of the
decomposition logic; it is not a VAPT claim.

## 15. Engine directories included in the baseline

The following directories and files constitute the frozen reference
implementation as of commit `4dc0599`:

- `decision_engine/core/`
  - `__init__.py`
  - `assessor.py`
  - `engine.py`
  - `executor.py`
  - `schemas.py`
- `decision_engine/adapters/`
  - `vapt_adapter.py`
- `decision_engine/benchmarks/`
  - `agnostic_benchmark.py`
  - `fair_benchmark.py`
  - `fair_vapt_benchmark.py`
- `tests/`
- `decision_engine/tests/`
- `datasets/`

## 16. Frozen reference implementation

This baseline is the **frozen reference implementation**. The engine
source, tests, datasets, and benchmark logic must not be modified under
this tag. Any change to these artefacts will invalidate this baseline and
will not be reflected in `reference-engine-prequalification-2026-09-01`.

## 17. Development must occur outside the reference baseline

All future prototype and development work must occur **outside** the
reference baseline. Any new package, prototype, or experimental branch
must be created as a separate directory tree, branch, or fork. The
frozen reference state at `4dc0599` must remain reproducible and
re-verifiable against this manifest indefinitely.

## 18. Known limitations

- The priority (Gap-1) component of the VAPT benchmark is 0.0. This is a
  measured result, not a placeholder, and the VAPT benchmark on the
  current 12-CVE corpus is unable to detect any contribution from a
  priority-only ranker. The 12-CVE corpus and 5/12 (41.7%) true-success
  rate bound the statistical resolution of the benchmark.
- The synthetic `sparse_success` benchmark is not a VAPT-domain claim; it
  is reported only as a decomposition-logic sanity check.
- The VAPT benchmark numbers (+36, +77, +118, +200 at T=1..5) are corpus-
  specific and may shift if the underlying CVE set changes.
- The frozen environment assumes Linux, Python 3.10.12, and pytest 9.1.1.
  The baseline is not guaranteed to reproduce on other Python or pytest
  versions without independent re-verification.

## SHA256 manifest (frozen implementation files)

Hashes computed against commit `4dc0599`:

| File | SHA256 |
|------|--------|
| `decision_engine/core/__init__.py`        | `67e5843d3e5e40fcb9713081c341abe409fbf752da77c30bb2953aa4cfddbd7b` |
| `decision_engine/core/assessor.py`        | `cef631f8f134dc701dcaf60636f7e39e877c54aa4901efe0197ed17c9ce69180` |
| `decision_engine/core/engine.py`          | `69f325d220784f8d2a97d6aba4859ee05f79650e423bfd3345e152e3476258ed` |
| `decision_engine/core/executor.py`        | `fbcdc1e4b61346f28577dbddd6940d8a36ff9b8d90d9d2ee649cf2cfe01d37c2` |
| `decision_engine/core/schemas.py`         | `7257fe4a161482e29afa6454a2edf252fe8ac26512ee9b5d804bd4be9f6634d3` |
| `decision_engine/adapters/vapt_adapter.py`| `906050beb0e642d8384a0dce6d62181989ba3c196a20c9702fd1fa7c71f2ed9c` |
| `decision_engine/benchmarks/agnostic_benchmark.py`     | `a444a0d1464bf40b4742ffca4e228ff12cbc6ba58e5c8bea75aab6642f2700ad` |
| `decision_engine/benchmarks/fair_benchmark.py`         | `68889cf864636d78c23fa58d741ba95e35897b95e43042445e87e8c9ac780069` |
| `decision_engine/benchmarks/fair_vapt_benchmark.py`    | `3db4a0aac451f4302ec6f2e2af1712d9106893fbb6d2985ca18d62a59b61f3ee` |

## Verification command summary

```
export PYTHONPATH=/home/vinit/ai_vapt_framework
pytest decision_engine/tests/ tests/ -q
# -> 55 passed

python decision_engine/benchmarks/fair_vapt_benchmark.py \
    --seeds 30 --caps 1 2 3 5
# -> T=2 pivot = +77.0, T=5 pivot = +200.0, priority = 0.0

python -m decision_engine.benchmarks.fair_benchmark \
    --families sparse_success --caps 5 --seeds 30
# -> sparse_success T=5 pivot = +772.1
```
