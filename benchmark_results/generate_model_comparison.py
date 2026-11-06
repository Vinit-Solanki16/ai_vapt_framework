import csv

fieldnames = [
    "model_name", "served_identifier", "hosting_provider", "architecture",
    "context_window", "first_token_latency_s", "tokens_per_second",
    "tool_call_success_rate", "malformed_rate", "multi_turn_reasoning",
    "api_stability", "recommendation_verdict"
]

rows = [
    {
        "model_name": "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M",
        "served_identifier": "kaggle-model",
        "hosting_provider": "Cloud Hosted (Remote llama.cpp via ngrok)",
        "architecture": "30.5B MoE / Dense GGUF Q4_K_M (llamacpp)",
        "context_window": "131,072 tokens (128K)",
        "first_token_latency_s": "1.56",
        "tokens_per_second": "40.16",
        "tool_call_success_rate": "100.0%",
        "malformed_rate": "0.0%",
        "multi_turn_reasoning": "EXCELLENT — Successfully plans multi-step recon, executes bash tools, invokes coverage updates, spawns subagents, handles child completion.",
        "api_stability": "HIGH — 100% uptime, zero HTTP 429 quota exhaustion errors, consistent JSON schema adherence.",
        "recommendation_verdict": "HIGHLY RECOMMENDED — Best performing model for Autonomous AI-VAPT."
    },
    {
        "model_name": "Qwen2.5-1.5B-Instruct-Q4_K_M",
        "served_identifier": "qwen2.5:1.5b",
        "hosting_provider": "Local Ollama (127.0.0.1:11434)",
        "architecture": "1.5B Dense GGUF Q4_K_M",
        "context_window": "32,768 tokens (32K)",
        "first_token_latency_s": "1.37",
        "tokens_per_second": "49.65",
        "tool_call_success_rate": "100.0%",
        "malformed_rate": "0.0%",
        "multi_turn_reasoning": "LIMITED — Fast on single-turn function calls, but lacks reasoning depth for large 100K+ agent system prompts; prone to context truncation in long autonomous traces.",
        "api_stability": "HIGH — Local offline process, zero network latency, zero quota constraints.",
        "recommendation_verdict": "ADEQUATE FOR TRIAGE ONLY — Suitable for Fast Web Audit and simple heuristic checks, inadequate for Deep Autonomous multi-agent pentests."
    },
    {
        "model_name": "OpenRouter API Gateway Hub (Various Remote Models)",
        "served_identifier": "openrouter/auto",
        "hosting_provider": "OpenRouter Public API Gateway",
        "architecture": "API Gateway / Multi-Provider Proxy (Not a single model architecture)",
        "context_window": "128,000 - 200,000 tokens",
        "first_token_latency_s": "N/A (Blocked)",
        "tokens_per_second": "N/A (Blocked)",
        "tool_call_success_rate": "N/A (Preflight Quota Block)",
        "malformed_rate": "N/A",
        "multi_turn_reasoning": "UNAVAILABLE — Preflight credential validation failed due to upstream account quota exhaustion (HTTP 402/429); underlying models could not be tested.",
        "api_stability": "LOW (Quota-Constrained) — Subject to upstream token billing quotas and rate limits.",
        "recommendation_verdict": "OPERATIONAL BLOCKER — Requires active paid credit balance; unsuitable as free unmetered backend for high-turn autonomous VAPT."
    }
]

out_path = "/home/vinit/STRIX/strix/benchmark_results/model_comparison.csv"
with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(rows)} models to {out_path}")
