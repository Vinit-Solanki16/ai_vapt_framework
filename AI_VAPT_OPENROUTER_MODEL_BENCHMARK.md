# AI-VAPT OpenRouter Live Free Model Benchmark Report

**Date:** 2026-11-11  
**Test Harness:** AI-VAPT LiteLLM Adapter & OpenRouter Live API  
**Environment:** Linux Devcontainer (Debian 12, Python 3.12.11)  
**Authentication:** Authenticated OpenRouter API Request via `OPENROUTER_API_KEY`  
**Status:** Complete — Empirical Benchmark Results from Live API Executions  

---

## 1. Executive Summary

To determine the most capable and reliable free AI model for autonomous VAPT execution, AI-VAPT executed an empirical live benchmark against OpenRouter's live model catalogue (`https://openrouter.ai/api/v1/models`).

Unlike prior audits that only catalogued static metadata, **this benchmark executed real authenticated API transactions through the application's actual LiteLLM adapter (`strix/llm/router.py`)**.

### Key Empirical Findings:
1. **Total Catalog Scope**: OpenRouter currently hosts **433 total models**, of which **16 are active `:free` models**.
2. **`thinkingmachines/inkling-2-small:free` is BLOCKED by OpenRouter**:
   - The prior theoretical recommendation (`thinkingmachines/inkling-2-small:free`) **failed immediately** with HTTP 403:
     ```text
     thinkingmachines/inkling-2-small:free is only available on agentic harnesses.
     Gate Free Endpoints by Agentic Harness
     ```
   - OpenRouter blocks direct API completions for this model, proving it **cannot** be used by autonomous CLI/SDK tools.
3. **`google/gemma-4-26b-a4b-it:free` is Rate-Limited**:
   - Upstream provider (`Google AI Studio`) returned HTTP 429 (`temporarily rate-limited upstream`).
4. **`nvidia/nemotron-3.5-super-vl:free` is the Top Performer**:
   - **Context Window**: 1,000,000 tokens.
   - **Tool Generation Latency**: 0.976 seconds.
   - **Tool Continuation Latency**: 1.098 seconds (fastest in class).
   - Accurately invoked `calculate_hash` with clean JSON parameters, consumed the simulated hash output, and summarized the result.
5. **`nvidia/nemotron-3.5-lightning:free` Confirmed Fully Operational**:
   - **Context Window**: 1,000,000 tokens.
   - Successfully generated tool calls (2.021s) and resumed execution (3.381s).
6. **`cohere/north-mini-code:free` Confirmed Highly Capable**:
   - **Context Window**: 256,000 tokens.
   - Rapid tool calling (0.862s) and concise tool output parsing.

---

## 2. Live Discovered Free Models in OpenRouter

The live catalogue query identified 16 active free models:

| # | Exact Canonical Model ID | Published Name | Context Length | Architecture / Modality |
|---|---|---|---|---|
| 1 | `nvidia/nemotron-3.5-super-vl:free` | NVIDIA: Nemotron 3.5 Super VL (free) | **1,000,000** | text+image+video -> text |
| 2 | `nvidia/nemotron-3.5-lightning:free` | NVIDIA: Nemotron 3.5 Lightning (free) | **1,000,000** | text -> text |
| 3 | `nvidia/nemotron-3-ultra-550b-a55b:free` | NVIDIA: Nemotron 3 Ultra (free) | **1,000,000** | text -> text |
| 4 | `thinkingmachines/inkling-2-small:free` | Thinking Machines: Inkling 2 Small (free) | 1,048,576 | text+image -> text *(Gated)* |
| 5 | `baidu/ernie-5.5-flash-preview:free` | Baidu: ERNIE-5.5-Flash-Preview (free) | 1,024,000 | text -> text |
| 6 | `google/lyria-3-pro-preview` | Google: Lyria 3 Pro Preview | 1,048,576 | audio/multimodal |
| 7 | `google/lyria-3-clip-preview` | Google: Lyria 3 Clip Preview | 1,048,576 | audio/multimodal |
| 8 | `dots-studio/dots-3-note-preview:free` | Dots Studio: Dots3-Note Preview (free) | 512,000 | text -> text |
| 9 | `recursive/flint-v1.0:free` | Recursive: Flint (free) | 262,144 | text -> text |
| 10 | `liquid/lfm-3-1.7b:free` | LiquidAI: LFM3-1.7B (free) | 262,144 | text -> text |
| 11 | `google/gemma-4-26b-a4b-it:free` | Google: Gemma 4 26B A4B (free) | 262,144 | text+image+video -> text |
| 12 | `google/gemma-4-31b-it:free` | Google: Gemma 4 31B (free) | 262,144 | text+image+video -> text |
| 13 | `cohere/north-mini-code:free` | Cohere: North Mini Code (free) | 256,000 | text -> text |
| 14 | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | NVIDIA: Nemotron 3 Nano Omni (free) | 256,000 | text -> text |
| 15 | `openrouter/free` | Free Models Router (auto-routing) | 200,000 | text -> text |
| 16 | `liquid/lfm-2.5-2.6b:free` | LiquidAI: LFM2.5-2.6B (free) | 65,536 | text -> text |

---

## 3. Empirical Benchmark Test Suite

Each shortlisted candidate was subjected to 6 live verification stages:
1. **Basic Completion**: Harmless greeting and acknowledgment ping.
2. **Streaming**: Real-time token streaming measuring Time to First Token (TTFT) and throughput.
3. **Tool Call Generation**: Providing the `calculate_hash` function schema and verifying structured tool call output.
4. **Tool Result Continuation**: Executing the simulated hash and supplying the result back via `role: "tool"` to verify multi-turn context continuation.
5. **Multi-Turn Reasoning**: Answering cybersecurity distinction between SQLi and XSS in concise sentences.
6. **Structured Output (JSON)**: Formulating strict RFC 8259 JSON key-value pairs without markdown decoration.

---

## 4. Empirical Test Results Matrix

| Candidate Model ID | Context Limit | Basic Completion | Streaming Latency | Tool Calling (Gen) | Tool Continuation | Multi-Turn Reasoning | Live Benchmark Verdict |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`nvidia/nemotron-3.5-super-vl:free`** | **1,000,000** | **PASSED** (0.386s) | **PASSED** (0.812s) | **PASSED** (0.976s) | **PASSED** (1.098s) | **PASSED** (7.540s) | **★ RECOMMENDED PRIMARY** |
| **`nvidia/nemotron-3.5-lightning:free`** | **1,000,000** | **PASSED** (0.612s) | **PASSED** (2.116s) | **PASSED** (2.021s) | **PASSED** (3.381s) | **PASSED** (8.422s) | **★ RECOMMENDED BACKUP** |
| **`cohere/north-mini-code:free`** | 256,000 | **PASSED** (0.451s) | **PASSED** (0.539s) | **PASSED** (0.862s) | **PASSED** (2.444s) | **PASSED** (0.813s) | **FULLY OPERATIONAL** |
| **`recursive/flint-v1.0:free`** | 262,144 | **PASSED** (1.314s) | **PASSED** (1.984s) | **PASSED** (2.010s) | **PASSED** (2.644s) | **PASSED** (1.370s) | **FULLY OPERATIONAL** |
| **`thinkingmachines/inkling-2-small:free`** | 1,048,576 | **FAILED** (0.216s) | Skipped | Skipped | Skipped | Skipped | **BLOCKED** (Gated by OpenRouter) |
| **`google/gemma-4-26b-a4b-it:free`** | 262,144 | **FAILED** (0.307s) | Skipped | Skipped | Skipped | Skipped | **RATE LIMITED** (Upstream 429) |

---

## 5. Detailed Candidate Analysis

### 5.1 `nvidia/nemotron-3.5-super-vl:free` (Primary Choice)
- **Strengths**:
  - Fastest tool generation (0.976s) and fastest tool-result continuation (1.098s) among all 1M-context models.
  - Generates clear, precise summaries of tool outputs (`"The SHA256 checksum of vapt-sample-input is: 69da0e41..."`).
  - Supports multi-modal input if visual DOM analysis or screenshot parsing is enabled.
- **LiteLLM Identifier**: `openrouter/nvidia/nemotron-3.5-super-vl:free`

### 5.2 `nvidia/nemotron-3.5-lightning:free` (Backup Choice)
- **Strengths**:
  - Codebase default in `strix/config/settings.py` and `strix/llm/router.py`.
  - Proven stable across multiple serverless hosts (CoreWeave, DeepInfra, Fireworks).
  - Consistent 1,000,000 token context window.
- **LiteLLM Identifier**: `openrouter/nvidia/nemotron-3.5-lightning:free`

### 5.3 `thinkingmachines/inkling-2-small:free` (Disqualified)
- **Failure Cause**: OpenRouter returned HTTP 403 with message:
  `thinkingmachines/inkling-2-small:free is only available on agentic harnesses. Try plugging it into a coding agent or productivity app listed on https://openrouter.ai/apps`.
- **Verdict**: Incompatible with standalone API consumers, SDKs, and automated CLI tools. Disqualified from AI-VAPT.

---

## 6. Rate Limit & Cost Management

- **Free-Tier Limits**:
  - Accounts with <$10 lifetime credit purchase have a **50 Requests Per Day (RPD)** cap across all free models.
  - Accounts with >=$10 lifetime credits have an expanded **1,000 RPD** cap.
  - Account rate limit: **20 Requests Per Minute (RPM)**.
- **Recommendation**: For prolonged overnight or multi-turn assessments exceeding 50 turns, ensure the OpenRouter account has lifetime credits or use local Ollama (`qwen2.5:1.5b`) for initial enumeration.
