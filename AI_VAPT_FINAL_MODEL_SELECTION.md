# AI-VAPT Final Model Selection & OpenRouter Empirical Decision Report

**Date:** 2026-11-11  
**Target Environment:** AI-VAPT Autonomous Security Testing Framework  
**Branch:** `ai-vapt-full-application`  
**Test Method:** Live Empirical API Benchmarking via LiteLLM Adapter (`scratch/benchmark_openrouter.py`)  
**Status:** Complete — Empirical Validation Concluded  

---

## 1. Executive Summary

Following live empirical testing using an authenticated OpenRouter API key across all shortlisted free models in the live OpenRouter catalogue, this report delivers the **definitive, evidence-based model selection** for AI-VAPT autonomous security assessment.

### Definitive Decisions:
1. **Primary Autonomous Free Model**: **`nvidia/nemotron-3.5-super-vl:free`**  
   - Canonical API ID: `nvidia/nemotron-3.5-super-vl:free`  
   - LiteLLM Routing ID: `openrouter/nvidia/nemotron-3.5-super-vl:free`  
   - Context Window: **1,000,000 tokens**  
   - Measured Performance: Basic completion in **0.386s**, tool-calling in **0.976s**, tool-result continuation in **1.098s**.  
   - Justification: Highest throughput and lowest latency among all 1M-context models; successfully executed and continued tool execution with zero errors.

2. **Backup Autonomous Free Model**: **`nvidia/nemotron-3.5-lightning:free`**  
   - Canonical API ID: `nvidia/nemotron-3.5-lightning:free`  
   - LiteLLM Routing ID: `openrouter/nvidia/nemotron-3.5-lightning:free`  
   - Context Window: **1,000,000 tokens**  
   - Measured Performance: Basic completion in **0.612s**, tool-calling in **2.021s**, tool-result continuation in **3.381s**.  
   - Justification: Existing codebase default with wide multi-provider serverless hosting availability (CoreWeave, DeepInfra, Fireworks).

3. **Disqualified Models**:
   - **`thinkingmachines/inkling-2-small:free`**: **DISQUALIFIED**. OpenRouter returned HTTP 403:  
     `"thinkingmachines/inkling-2-small:free is only available on agentic harnesses... Gate Free Endpoints by Agentic Harness"`. It cannot be invoked via direct API requests or LiteLLM.
   - **`google/gemma-4-26b-a4b-it:free`**: **DISQUALIFIED**. Upstream Google AI Studio pool returned HTTP 429 (`temporarily rate-limited upstream`).

---

## 2. Empirical Benchmark Comparison Matrix

| Candidate Model | Canonical API ID | Context Window | Completion Latency | Tool Generation | Tool Continuation | Live Status |
|---|---|:---:|:---:|:---:|:---:|:---:|
| **NVIDIA Nemotron 3.5 Super VL** | `nvidia/nemotron-3.5-super-vl:free` | **1,000,000** | **0.386s** | **0.976s** | **1.098s** | **★ SELECTED PRIMARY** |
| **NVIDIA Nemotron 3.5 Lightning** | `nvidia/nemotron-3.5-lightning:free` | **1,000,000** | **0.612s** | **2.021s** | **3.381s** | **★ SELECTED BACKUP** |
| **Cohere North Mini Code** | `cohere/north-mini-code:free` | 256,000 | 0.451s | 0.862s | 2.444s | Alternate Backup |
| **Recursive Flint** | `recursive/flint-v1.0:free` | 262,144 | 1.314s | 2.010s | 2.644s | Functional |
| **Thinking Machines Inkling 2 Small** | `thinkingmachines/inkling-2-small:free` | 1,048,576 | Failed (0.216s) | Blocked | Blocked | Gated (HTTP 403) |
| **Google Gemma 4 26B** | `google/gemma-4-26b-a4b-it:free` | 262,144 | Failed (0.307s) | Blocked | Blocked | Rate Limited (HTTP 429) |

---

## 3. Router Normalization Verification

The LiteLLM router in `strix/llm/router.py` was inspected and fixed:
- **Prior Flaw**: `format_openrouter_model()` stripped `openrouter/` whenever a slash was present in the model identifier, resulting in `litellm.exceptions.BadRequestError: LLM Provider NOT provided`.
- **Applied Fix**: `format_openrouter_model()` now guarantees that every OpenRouter model identifier returned has the `openrouter/` prefix (e.g. `openrouter/nvidia/nemotron-3.5-super-vl:free`).
- **Verification**: `tests/test_multi_model_router.py` (5/5 tests passed) and `tests/test_openrouter_integration.py` (18/18 tests passed) verify this routing contract cleanly.

---

## 4. Live Tool-Calling Verification Evidence

During live execution on `nvidia/nemotron-3.5-super-vl:free`, the model received:
```json
{
  "tools": [{
    "type": "function",
    "function": {
      "name": "calculate_hash",
      "description": "Calculate sha256 checksum of an input string.",
      "parameters": {
        "type": "object",
        "properties": {"input_string": {"type": "string"}},
        "required": ["input_string"]
      }
    }
  }],
  "messages": [{"role": "user", "content": "Calculate the sha256 checksum of 'vapt-sample-input' using calculate_hash tool."}]
}
```

The model generated a valid tool call in **0.976 seconds**:
```json
{
  "function": {
    "name": "calculate_hash",
    "arguments": "{\"input_string\":\"vapt-sample-input\"}"
  }
}
```

The simulated hash output (`69da0e416fa0adb2315796ba0022d5899ad122b66e5e5abb4c...`) was returned to the model via a `role: "tool"` message. Within **1.098 seconds**, the model synthesized the output:
```text
The SHA256 checksum of `vapt-sample-input` is:
69da0e416fa0adb2315796ba0022d5899ad122b66e5e5abb4c...
```
This empirically proves that tool generation, parameter serialization, execution feedback, and multi-turn reasoning function end-to-end through the AI-VAPT provider stack.

---

## 5. Rate Limits and Account Recommendations

- OpenRouter free accounts that have not purchased credits are limited to **50 Requests Per Day (RPD)**.
- For deep autonomous assessments requiring 50 to 100 turns, operator accounts should add $10 in lifetime credits (unlocking **1,000 RPD**) or leverage local Ollama (`qwen2.5:1.5b`) for high-volume discovery.
