# Role: Security Evaluation Specialist
Create `tests/evaluate.py` comparing the SMART agent vs a DUMB baseline (no scoring, no pivot) across four metrics (Deng et al., 2025).

## Technical Requirements
1. Run both agents against a 3-vuln labelled env: 1 valid (success), 1 broken (would loop), 1 low-severity.
2. Metrics: total runtime (s), total network requests, completion rate (%), loop events avoided.
3. Output a Pandas DataFrame saved to `data/benchmark_results.csv`.

## Done criteria
- `python tests/evaluate.py` prints the comparison and writes the CSV.
- SMART shows strictly fewer requests and zero loop events than DUMB.
