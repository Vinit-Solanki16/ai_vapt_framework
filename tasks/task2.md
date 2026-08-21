# Role: Vulnerability & LLM Security Researcher
Refactor `core/exploit_assessor.py` to address the "Exploit Usability Gap" (Lu et al., 2024; Gap 1).

## Technical Requirements
1. `fetch_github_poc(cve_id)` only runs when `GITHUB_TOKEN` is set (unauthenticated code search returns 401). Never returns dummy code.
2. `get_poc(cve_id)` resolves from the LOCAL corpus first (`data/poc_corpus/`), then optional GitHub. This keeps scoring reproducible (thesis requirement).
3. `ExploitAssessment` (core/schemas.py) is an enum-constrained Pydantic model:
   - exploit_found: bool
   - syntax_valid: bool
   - os_dependencies: str
   - privileges_required: Literal["none","user","root"]
   - network_noise: Literal["low","medium","high"]
   - complexity_score: int 1..10
   - prerequisites_met: bool
   - usability_rank: Literal["HIGH","MEDIUM","LOW"]
   - reasoning: str
4. `assess_exploit_quality(cve_id, code_sample, provider)` uses `llm.with_structured_output(ExploitAssessment)` for both ChatOpenAI and ChatOllama (llama3.2:3b).

## Done criteria
- `python -m core.exploit_assessor CVE-2021-44228` returns a valid enum-ranked assessment (no "}" garbage).
- Scoring uses REAL corpus code, not a placeholder.
