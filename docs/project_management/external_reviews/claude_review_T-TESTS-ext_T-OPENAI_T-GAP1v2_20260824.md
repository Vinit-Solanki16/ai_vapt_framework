# READ-ONLY Review — T-TESTS extension, T-OPENAI, T-GAP1-VALID v2 (2026-08-24)

_Reviewer: Claude Code (read-only). Reviewed: uncommitted working-tree changes
per Hermes dispatch._

## Scope reviewed
- core/exploit_assessor.py (provider branch only) — T-OPENAI
- tests/test_openai_provider.py (NEW, 144 lines) — T-OPENAI
- tests/test_ttests_gaps.py (NEW, 5 tests) — T-TESTS extension
- tests/ablation.py (NEW) + data/ablation_epss_only.csv — T-GAP1-VALID v2
- requirements.txt (+pytest), 07_TEST_STATUS.md, 09_BENCHMARK_EVIDENCE.md

## Verdict: APPROVE
Core changes are conformity-compliant; findings rigorously validated.

## Hermes (PM) re-verification notes (independent of this review)
- `python -m pytest tests/ -q` → **21 passed** (13 test_core + 5 test_ttests_gaps + 3 test_openai_provider). Green, no regression.
- `python tests/evaluate.py` → SMART 5 req / 0 loops, DUMB 21 req / 2 loops. Canonical benchmark intact (DUMB=2, NOT the rejected DUMB=16 — no scope leak from the reverted loop-instrumentation work).
- `python tests/ablation.py` → deterministic: A wastes 0 before foothold, B wastes 2; total waste 14=14; completion 100% both. Claim "GAP-1 proven for routing efficiency (not total-attempt parity)" is supported and honestly caveated (simulation, synthetic EPSS inputs, stubbed assessor).

## Two review-administrative notes REJECTED by Hermes (do not action)
1. "Run tests/tcorpus_gaps.py" — that file does not exist; hallucinated. T-CORPUS verification is already satisfied by the committed 12-CVE corpus (ecdf814).
2. "Anonymize CVEs in labels.json" — HARMFUL. core/poc_corpus.py:39-41 resolves corpus files as `{cve}.py`, so the CVE id is the filename. Renaming would break corpus resolution. Real CVE IDs are correct for a reproducible thesis corpus. Rejected.

## Legitimate caveat (already documented, no action)
Real-world GAP-1 efficacy depends on production assessor accuracy on unseen CVEs — this is a best-case proof-of-mechanism, not real-world efficacy. Recorded in 09_BENCHMARK_EVIDENCE.md and gap1_ablation.py caveat.
