# AGENT PROMPTS (ready to dispatch)

These are self-contained prompts for the writing/research agents you will
dispatch. Hermes prepared them; you (the authority) hand them to the agent and
feed back the result. After each returns, Hermes verifies (no source change,
no overclaim) then we commit one scoped doc.

CRITICAL HONESTY RULE for every agent:
- "Not identified in inspected materials" ≠ "proven not to exist".
- NEVER write a bare "No" for related work / novelty. Use the 5 honest
  qualifiers: Not inspected / Inspected, not found / Partially / Yes / N/A.
- Keep SIMULATION vs OBSERVED vs REAL distinct.
- All "Yes" novelty claims must cite file:line in the repo.

------------------------------------------------------------------------------
## R1 — Related Work + dated Strix snapshot
**Deliverable:** `docs/project_management/R1_RELATED_WORK.md`
**Prompt:**
You are a research-liability reviewer for an M.Tech thesis on an autonomous
decision-and-pivot engine for vulnerability testing. Write a RELATED WORK
section. Inspect the repo at /home/vinit/ai_vapt_framework (README, core/,
docs/project_management/, decision_engine/). Cover: (1) autonomous pentest
agents (e.g. Strix, PentestGPT, and any others you can name with dates), (2)
LLM-based exploit/action quality scoring, (3) failure-aware / pivot planning in
agents, (4) benchmark methodology (SMART vs DUMB, ablation). For each system use
the honest qualifiers (Not inspected / Inspected-not-found / Partially / Yes /
N/A) — NEVER a bare "No". Record a DATED Strix snapshot: state the version/date
you reference and that autonomous-pentest space moves fast. Output markdown with
a comparison table. Do NOT modify any source file. Under 600 words.

------------------------------------------------------------------------------
## R2 — Novelty / threat-to-novelty matrix
**Deliverable:** `docs/project_management/R2_NOVELTY_MATRIX.md`
**Prompt:**
Write a NOVELTY MATRIX for the same thesis. Columns: Mechanism | Our framework
(file:line evidence) | Related system | Differentiation (honest qualifier).
Mechanisms to cover: pre-execution candidate quality scoring (Gap-1);
per-candidate attempt counter + N-threshold pivot (Gap-2); priority =
probability × (0.5+0.5×quality); bounded termination / loop prevention;
simulation-vs-observed evidence tiers. Every "Yes our framework does X" MUST cite
file:line (e.g. decision_engine/core/engine.py:execute_node). Related systems use
the 5 honest qualifiers, never bare "No". Flag any claim that is NOT yet backed
by evidence as "UNPROVEN (needs R5–R7)". Do NOT modify source. Under 500 words.

------------------------------------------------------------------------------
## R3 — Approved thesis claim register
**Deliverable:** `docs/project_management/R3_CLAIM_REGISTER.md`
**Prompt:**
Produce the CONTROLLED CLAIM REGISTER that governs all thesis writing. Three
tiers: A) MAY claim (backed by evidence in repo, cite file:line); B) QUALIFY
(only with explicit caveat, state the caveat); C) PROHIBITED (must never be
claimed). Seed with these facts: LEVEL 1 simulation proven (benchmark + ablation);
LEVEL 2 loopback observed validation achieved (n=2); real LLM-assessor accuracy
on unseen CVEs NOT proven; Level 3 Docker-isolated NOT achieved; real-world
efficacy NOT proven; "better than all autonomous VAPT systems" PROHIBITED. The
register is the single source of truth for thesis claims. Do NOT modify source.
Under 500 words.

------------------------------------------------------------------------------
## R4 — Independent challenge review (after R1–R3)
**Deliverable:** `docs/project_management/external_reviews/R4_challenge.md`
**Prompt (read-only):**
Independently challenge R1–R3. Find the weakest claim, the biggest overclaim
risk, and any missing baseline. Explicitly test: does the agnostic benchmark
actually prove domain-independence, or just reuse the same pivot logic with
different labels? Is "SMART < DUMB attempts" a meaningful contribution or
trivial? List 3–5 concrete threats to novelty. Read-only; do not modify files.

------------------------------------------------------------------------------
## R5–R7 — Final authority review package + GO/NO-GO
**Deliverable:** `docs/project_management/12_GO_NO_GO.md`
**Prompt:**
Assemble the GO/NO-GO package: (1) consolidated evidence map (Level 1/2, what is
NOT proven), (2) the R3 register as the claim gate, (3) recommended venue fit
(be honest: credible research-prototype paper, not a "complete platform" claim),
(4) explicit GO/NO-GO recommendation for Phase 7 thesis writing. Tie every item
to file:line or a dataset in datasets/. Under 600 words.
