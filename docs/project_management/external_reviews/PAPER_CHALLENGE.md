# A4 — Independent Paper Challenge Review

_Review agent (read-only). Source: THESIS_DRAFT_v0.1.md, R3_CLAIM_REGISTER.md,
MASTER_RESEARCH_PROJECT_REPORT.md, 12_GO_NO_GO.md. HEAD 4f345d4.
Written by Hermes verification after the dispatched review agent returned WITHOUT
producing this file (it surfaced the key finding in its reasoning but did not write
the deliverable). Hermes completed the review from the agent's verified investigation
plus direct file inspection._

## Verdict

**ACCEPT WITH CORRECTIONS (minor).** Claim discipline is strong: no actual C-prohibited
wording is used (the only matches for "faster / Docker-validated / better than all" are
explicit "never claim / PROHIBITED" guard sentences). Gap-2 leads as the primary
contribution; the Gap-1 null result (priority component = 0 under fair cap) is reported
honestly. One real file:line misattribution was found and corrected in the draft
(safety/allowlist anchor). No research conclusion is changed.

## Findings

### F1 (real, corrected) — A3 safety anchor misattributed to the generalized engine
- **Draft location:** §13 Safety protocol cited `executor.py:42, 220-229, 236-245`;
  traceability row #3 cited `engine.py:236-245`.
- **R3 item:** A3 (framework safely bounds execution; opt-in fail-closed dangerous path).
- **Problem:** `decision_engine/core/engine.py` is 190 lines and has NO danger_mode or
  allowlist (grep confirms). `decision_engine/core/executor.py` is only 57 lines and is a
  pluggable, domain-independent backend with NO safety gate. The fail-closed
  `danger_mode` + `target_allowlist` lives in the ORIGINAL VAPT executor
  `core/executor.py:56-72` (constructor, empty allowlist refuses all) and
  `core/executor.py:219-245` (safe-mode SKIPPED / danger gate).
- **Why it matters:** leaving the anchor on the generalized engine would falsely imply the
  domain-independent core implements the safety boundary. It does not — safety is a
  VAPT-domain concern in `core/executor.py`, exercised by `tests/test_executor_allowlist.py`
  and `tests/test_danger_mode_mock.py`.
- **Correction applied:** both §13 and traceability row #3 now cite `core/executor.py:56-72`
  and `core/executor.py:219-245`, and §13 clarifies the generalized executor delegates to
  a pluggable `execute_fn` and does not itself implement danger_mode.

### F2 (checked, OK) — All other mechanism anchors resolve
- engine.py:_evaluate at :112 (threshold pivot) ✓; engine.py:_pivot_node at :98 (advance +
  reset) ✓; engine.py:172/183 (save/load_checkpoint) ✓; schemas.py:77 (priority_score) ✓;
  schemas.py:26 (QUALITY_WEIGHT) ✓; assessor.py:19/28 (deterministic_assessor /
  assess_candidates) ✓; vapt_adapter.py:52 (corpus→candidate) ✓. All verified against source.

### F3 (checked, OK) — No L1/L2 misstatement
- Loopback is consistently scoped as "controlled loopback observed validation (Level 2),
  assessor stubbed, not container-isolated, not real-world" (§15 Results 3/4; §17; §18).
- Biased 5-vs-21 / 8-vs-17 figures are explicitly retiered and NOT cited as evidence (§16).
- "real VAPT corpus" is correctly framed as curated 12-CVE PoC corpus with SYNTHETIC STUB
  modules (§14, §17), never "real exploitation".

### F4 (checked, OK) — Gap-1 null result reported, not hidden
- Six explicit statements that the priority component = 0 under fair per-visit cap, tied to
  B1 with its exact caveat (§5, §10, §16, traceability rows #10/#11). This is the correct
  honest handling; no upgrade to A attempted.

### F5 (observation, not a defect) — Related-work novelty is self-limited
- §4 correctly states deep novelty differentiation vs named-but-unread agents is "not
  established from repository evidence" (R1 title-inspected them). This is honest but means
  the novelty claim rests on the fair-cap ablation methodology, not a literature sweep.
  Acceptable for an M.Tech mechanism paper; a supervisor may ask for one deeper related-work
  read. Optional, not blocking.

## Threats to Validity (concrete)

1. **T-VAPT-safety-anchor (was F1):** if uncorrected, a reader infers the domain-independent
   engine enforces the fail-closed boundary — it does not. Corrected.
2. **T-stubbed-assessor:** L2 observed success used a stubbed assessor; LLM accuracy on
   unseen CVEs remains unvalidated (C2). Paper states this; cannot be removed.
3. **T-L2-not-L3:** loopback only; container-isolation unproven (C5). Paper states this.
4. **T-cross-domain-thin:** agnostic evidence = Gap-2 on one synthetic family (B2). Paper
   states architectural independence separately; acceptable but weaker than multiple domains.
5. **T-Gap1-null:** under fair cap Gap-1 shows no independent win; if a reviewer expects
   Gap-1 to be a contribution, the paper must hold the B1 line. It does.

## Conclusion
The draft is claim-disciplined and evidence-anchored. After the F1 correction, every A/B
claim maps to a real, correct file:line or artifact, and every C-claim is omitted. The
paper is ready for A5 (cosmetic correction already applied) → A6 (final evidence review) →
A7 (thesis assembly). No structural rewrite needed.
