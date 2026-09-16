# Safety & Ethics — AI-VAPT Framework

**Date:** 2026-09-16  
**Commit:** 9952d95 (post-Wave 12)

---

## 1. Safety Design Principles

### 1.1 Core Principles

1. **No live exploitation:** All experiments use simulation mode
2. **Fail-closed:** Execution fails safely on errors
3. **Allowlist-only:** Only explicitly allowed commands can execute
4. **No external targets:** Framework never targets real systems
5. **Bounded attempts:** Per-candidate attempt counters prevent infinite loops

### 1.2 Safety Controls

| Control | Implementation | Verified |
|---------|----------------|----------|
| Command allowlist | `tests/test_executor_allowlist.py` | ✓ |
| Fail-closed execution | `services/tests/test_safety.py` | ✓ |
| No external targets | Safety audit | ✓ |
| Bounded pivoting | GAP-2 experiments | ✓ |
| Simulation-only | All experiments | ✓ |

---

## 2. Ethical Considerations

### 2.1 Research Ethics

| Consideration | Status |
|---------------|--------|
| No live exploitation | ✓ Confirmed |
| No real vulnerabilities exploited | ✓ Confirmed |
| Responsible disclosure | ✓ N/A (simulation only) |
| IRB approval | Not required (simulation research) |

### 2.2 Potential Misuse

The framework is designed for **research purposes only**. Potential misuse scenarios:

| Scenario | Mitigation |
|----------|------------|
| Live exploitation | Simulation-only design |
| External targeting | No external target capability |
| Malicious PoC execution | Allowlist + fail-closed |

### 3.3 Responsible Research

- All experiments are reproducible and documented
- Safety controls are tested and verified
- No real systems are targeted
- Results are honestly reported with limitations

---

## 3. Safety Test Coverage

### 3.1 Test Files

| File | Tests | Purpose |
|------|-------|---------|
| `tests/test_executor_allowlist.py` | ~15 | Command allowlist enforcement |
| `services/tests/test_safety.py` | ~10 | Service-level safety controls |
| `prototype/tests/test_safety.py` | ~12 | Prototype safety boundaries |

### 3.2 Safety Scenarios Tested

1. **Allowlist enforcement:** Only allowed commands execute
2. **Fail-closed:** Errors result in safe failure, not unsafe execution
3. **No external targets:** Framework cannot target real systems
4. **Bounded attempts:** Infinite loops prevented by per-candidate counters

---

## 4. Limitations

### 4.1 What Is NOT Validated

1. **Real Docker execution:** Infrastructure unavailable
2. **Live exploit validation:** Safety design prevents this
3. **Production-scale:** Lab-scale only

### 4.2 Honest Reporting

All results are honestly reported:
- Simulation mode clearly labeled
- Limitations documented
- Unverified claims marked as such
- No fabricated results

---

## 5. Conclusion

The AI-VAPT framework demonstrates:
1. **Safety-first design:** Allowlist, fail-closed, no external targets
2. **Reproducible research:** All experiments documented and repeatable
3. **Honest reporting:** Limitations clearly stated
4. **Ethical research:** No live exploitation, responsible disclosure
