# AI-VAPT — OpenCode & Subscription Integration Feasibility Review

**Date:** 2026-11-16
**Method:** Inspection-only review. No code, configuration, or dependency changes were made.
**Scope:** Verify the proposed OpenCode / ChatGPT-subscription / Gemini integration approaches against the
actual codebase, the installed OpenCode runtime (v2.2.1), and each vendor's current, published rules.

Legend used throughout:

| Tag | Meaning |
|---|---|
| ✅ Documented | Verified against source code, a live OpenAPI spec, an observed HTTP response, or official vendor docs |
| 🔶 Assumed   | Plausible but **not** verified in this review; treat as unknown until tested |
| ❌ Blocked   | Verified as impossible, not offered, or explicitly prohibited |

---

## 0. Executive summary

1. **The proposed OpenCode session-API bridge is not feasible as a faithful integration.** The installed
   OpenCode v2.2.1 server API (verified from its live OpenAPI 3.1 spec, 170 operations) exposes **no endpoint
   that accepts foreign tool definitions, a system prompt, or a caller-supplied conversation history**. Its
   `prompt` endpoint "schedules agent-loop execution" inside OpenCode with OpenCode's own tools — which would
   let OpenCode, not Strix, execute security actions. Verdict: **do not build it.**
2. **OpenCode free models are not eligible for use from external clients.** OpenCode's own docs state
   "Free-tier chat models require OpenCode; use paid models or Go from other clients," and a live external
   probe returned **HTTP 429 `FreeUsageLimitError`**. Using them from AI-VAPT is unsupported by OpenCode's
   rules; this report does not propose any bypass.
3. **ChatGPT-subscription usage already exists in the codebase** (`strix/config/codex.py`) via the
   Codex-CLI-style OAuth flow to `chatgpt.com/backend-api/codex`. It is functional (login CLI works; refresh,
   routing, guardrail handling all implemented and unit-tested) but rests on an **unofficial** endpoint for a
   third-party app. The **official** alternative now exists: OpenAI's **Sign in with ChatGPT → ChatGPT plan
   usage** program, which explicitly supports open-source apps calling the **public Responses API**
   (`api.openai.com/v1/responses`) on the user's plan — with function/custom tools supported. It requires a
   client-ID request and app integration work.
4. **Gemini: the sanctioned free path is the Gemini Developer API free tier with an API key** (the app's
   existing `google` provider; a working key already exists in the user's OpenCode credentials).
   **Gemini CLI OAuth token reuse/proxying is explicitly excluded** — Google's own Gemini CLI terms state that
   accessing the Code Assist service with third-party software "is a violation of applicable terms and
   policies" and "may be grounds for suspension or termination of your account."
5. **Recommended order of adoption:** (1) keep the existing OpenRouter free-model route (already wired and
   benchmarked), (2) enable the Gemini API free tier with the existing key (zero code, sanctioned),
   (3) enable the built-in ChatGPT subscription path knowing its guardrail and unofficial-API risks, and
   (4) make the **only** new code investment worth making: the official SIWC ChatGPT-plan-usage integration.

---

## 1. Verified existing architecture

Every architectural claim below was re-checked in the working tree on 2026-11-16.

### 1.1 Model selection and routing

| Claim | Verdict | Evidence |
|---|---|---|
| `STRIX_LLM` (aliases `AI_VAPT_LLM`) selects the model; persisted in `~/.strix/cli-config.json` | ✅ | `strix/config/settings.py:32-35` (validation_alias), `strix/core/runtime_credentials.py:256-286` (`get_runtime_model` precedence: override → in-memory → env → CLI config) |
| Any non-`openai/` prefixed model falls through to LiteLLM | ✅ | `strix/config/models.py:563-611` (`StrixProvider._resolve_prefixed_model` → `_get_fallback_provider("litellm")`), `models.py:1045-1058` (`routes_through_litellm`) |
| The installed LiteLLM does **not** recognize an `opencode/` prefix | ✅ | Live check: `litellm.get_llm_provider("opencode/glm-5.3-flash-free")` → `BadRequestError: LLM Provider NOT provided`; `openrouter/z-ai/glm-5.3` resolves correctly |
| The `cloud_hosted`/`custom` provider adapts any OpenAI-compatible endpoint (base URL + optional key, model forced to `openai/<model>`, `STRIX_API_TYPE=chat_completions`) | ✅ | `strix/llm/router.py:160-192`, `strix/interface/api.py:1928-1950`, validate endpoint `api.py:1539-1558` |
| Web-console provider cards: openrouter, openai, anthropic, google, ollama, cloud_hosted | ✅ | `strix/interface/web/js/app.js:290-296`, `api.py:1416-1585` (per-provider validate endpoints) |
| Runtime credentials are in-memory, redacted, and synced to `os.environ` for LiteLLM/subprocesses | ✅ | `strix/core/runtime_credentials.py:73-139, 178-253` |

### 1.2 Tool-calling and multi-turn execution (this is what any bridge must preserve)

| Claim | Verdict | Evidence |
|---|---|---|
| The agent loop is the OpenAI Agents SDK `Runner.run_streamed(...)`; tool execution happens **inside Strix** | ✅ | `strix/core/execution.py:815-838`; the SDK executes `FunctionTool`/`CustomTool` registered in `strix/agents/factory.py:23-85` |
| Strix ships ~30 security tools (proxy, shell/scanner, reporting, subagents, notes/todo/coverage/threat-model, web search, MCP) | ✅ | Imports in `strix/agents/factory.py:23-85`; per-tool modules under `strix/tools/` |
| Provider tool-call quirks are actively managed (per-turn ID rewriting, malformed-argument repair, per-turn call caps) | ✅ | `strix/config/tool_call_ids.py`, `tool_call_arguments.py`, `tool_call_limits.py`; tests `test_tool_call_ids_providers.py:310-377`, `test_tool_call_arguments.py`, `test_tool_call_limits.py` |
| Streaming, idle/first-event/total stream timeouts, non-streaming fallback mode exist | ✅ | `strix/config/models.py:171-248` (`_NonStreamingModel`), `models.py:420-479` (`_with_timeouts`), settings `settings.py:87-102` |
| Compaction / context budgeting run between turns | ✅ | `strix/core/execution.py:802-814` (`_compact_session`, image budget), `strix/llm/compaction.py`, `context_budget.py` |
| Provider validate/ discovery schemas exist for google/openrouter/anthropic/ollama/custom/openai + cloud_hosted profiles | ✅ | `strix/interface/schemas.py:311-423`, `api.py:1965-2098`; tests `test_multi_model_router.py`, `test_openrouter_integration.py` (18 tests), `test_multi_provider_routing_and_resume.py`, `test_frontend_ux_and_provider_panels.py` |

**Consequence for any "bridge":** Strix speaks OpenAI **Responses/Chat-Completions** semantics — it sends its
own tool schemas and its own full conversation history each turn, and expects structured `tool_calls` back.
A bridge must reproduce that protocol faithfully or Strix's loop breaks.

### 1.3 ChatGPT subscription bridge (already implemented)

| Claim | Verdict | Evidence |
|---|---|---|
| OAuth 2.0 + PKCE against `auth.openai.com` using OpenAI's Codex CLI client ID | ✅ | `strix/config/codex.py:41-58` (`CLIENT_ID`, `AUTHORIZE_URL`, `REDIRECT_URI`, `SCOPE`) |
| Inference routed to `chatgpt.com/backend-api/codex` with `STRIX_LLM=chatgpt/<model>` | ✅ | `codex.py:50` (`CODEX_BASE_URL`), `codex.py:394-406` (`subscription_model`, `auth_mode`), `models.py:86-134` (`_CodexResponsesModel`, always streamed, `store=false`, reasoning-effort clamping) |
| Token refresh with single-use rotation + cross-process locking and race recovery | ✅ | `codex.py:106-127` (`_refresh_guard`, flock), `codex.py:325-348` (`get_valid_token`); tests `test_codex_auth.py:165-306` (refresh rotation, peer-rotation recovery, race re-raise, not-signed-in) |
| Content-guardrail detection for cybersecurity-flagged responses | ✅ | `codex.py:130-160` (`CodexContentGuardrailError`, markers `"flagged for possible cybersecurity risk"`, `"trusted access for cyber"`); test `test_codex_auth.py:109-127`; retry policy excludes retrying guardrail errors (`models.py:76-83`) |
| CLI commands `strix auth login chatgpt | status | logout` | ✅ | `strix/interface/auth_cli.py:38-66`; **live check:** `.venv/bin/strix auth status` → `Not signed in. Run strix auth login chatgpt to sign in.` (CLI functional; no tokens displayed) |
| Subscription errors produce actionable hints (plan-gated model, expired sign-in) | ✅ | `strix/interface/main.py:95-115` (`_subscription_error_hint`) |
| Zero-cost ledger for subscription usage reporting | ✅ | `tests/test_usage_subscription.py:19-39` |
| The file itself declares the approach unofficial for third-party use | ✅ | `codex.py:4-8`: "Using a ChatGPT subscription outside OpenAI's own products is not officially supported by OpenAI; the user chooses this path knowingly." |

**Status:** implemented and tested, **not currently signed in** on this machine. Nothing here was modified.

---

## 2. OpenCode bridge feasibility

### 2.1 What the installed OpenCode v2.2.1 server actually documents

Method: `opencode serve` was started locally on a throwaway port purely to export its **OpenAPI 3.1 spec**
(`/openapi.json`, 170 operations / 501 schemas) and then stopped. No sessions were created; the
auto-generated local server password was used only to read the spec of that temporary instance. Cross-checked
against https://opencode.ai/docs/api/ (the published reference for the same surface) and the v1-era server
docs.

Relevant documented endpoints (all ✅ from the live spec):

| Endpoint | Documented behavior |
|---|---|
| `POST /api/session` | Create session |
| `POST /api/session/{id}/model` | Switch session model — body is **only** `{ model: Model.Ref }` |
| `POST /api/session/{id}/agent` | Switch session agent (agents are locally configured) |
| `POST /api/session/{id}/prompt` | "Durably admit one session input and **schedule agent-loop execution**" — body is **only** `{ id?, text, files?, agents?, skills?, metadata?, delivery?, resume? }` |
| `GET /api/session/{id}/message` / `GET /api/session/{id}/message/{messageID}` | Fetch messages (assistant content types: `Text \| Reasoning \| Tool`) |
| `GET /api/event` | SSE event stream (session/step/text/tool events) |
| `POST /api/session/{id}/permission` … `/reply` | OpenCode's own permission-gating for its own tools |
| `POST /api/experimental/generate/text` | Stateless one-shot: body **only** `{ prompt: string, model? }` → text |
| `GET /api/experimental/usage/limits` | Usage-limit introspection (schema includes a `UsageLimits.Go` budget) |

**Absent from the documented surface (❌):** any `/v1/chat/completions`- or `/v1/responses`-style passthrough;
any endpoint accepting tool **definitions**; any per-request **system prompt** or **caller-supplied message
history** on the session path. (Historical note: the v1-era docs listed `system` and `tools` fields on the old
message endpoint; their exact semantics were not independently verified in this review — the v1 source fetch
failed — and the installed v2.2.1 spec, which supersedes it, has neither.)

### 2.2 Criterion-by-criterion bridge assessment

| Requirement | Session-API bridge | `experimental/generate/text` |
|---|---|---|
| System messages preserved | ❌ No parameter exists; OpenCode injects its own system prompt (agent config) | ❌ Single `prompt` string only |
| User/assistant messages preserved | 🔶 Only indirectly — OpenCode manages its own history; the bridge cannot inject assistant/tool-result turns as conversation state | ❌ Stateless |
| Tool definitions (Strix's ~30 security tools) | ❌ Not accepted anywhere | ❌ Not accepted |
| Structured tool calls back to Strix | ❌ Tool calls, if any, are OpenCode's own tools, executed or permission-gated inside OpenCode (`Session.Message.Assistant.Tool`, permission endpoints) | ❌ Text only |
| Tool-call IDs | ❌ OpenCode-internal IDs, not the OpenAI protocol Strix's rewriter/repair layers manage | ❌ |
| Tool arguments | ❌ Same as above | ❌ |
| Tool results (Strix → model) | ❌ No input path; cannot feed results back into the next model turn as tool messages | ❌ |
| Multi-turn continuation | 🔶 Possible only by letting OpenCode own the whole conversation (per-run session = `POST /api/session`, per turn = `prompt`) — but then the loop is OpenCode's, not Strix's | ❌ |
| Streaming | 🔶 OpenCode's SSE (`session.text.delta`, `session.tool.*`) — not OpenAI-format deltas; would need lossy translation | ❌ |
| Usage/token metadata | 🔶 `session.usage.recorded` events + `/usage/limits` — not OpenAI `usage` blocks | ✅ `Generate.Usage` on the response |
| Errors / rate limits | 🔶 Provider errors surface as OpenCode session events (`session.step.failed`, `session.retry.scheduled`), not OpenAI error shapes | ✅ Documented error codes (401/404/422/502/503) |

### 2.3 Can a session be maintained per AI-VAPT run? Can Strix keep ownership?

- **Mechanically:** yes — create one OpenCode session per run, set its model to `opencode/<model>`, and drive
  it with `prompt` + read messages/events. ✅ documented.
- **Substantively:** no. Each `prompt` runs **OpenCode's agent loop** with **OpenCode's tools** on the host
  where OpenCode runs. Even if the bridge configured a tool-less OpenCode agent (via local `opencode.json` —
  an assumption about config behavior, 🔶), the model's replies would be plain text; Strix's tool-call
  exchange (IDs, arguments, results, streaming deltas) would have to be simulated through prompt-text
  conventions. That is a **degraded, brittle proxy** — not the protocol Strix's execution, retry, ID-repair,
  and reporting layers are built on.
- **"Strix owns all security tools and execution decisions":** only the degraded variant even attempts this,
  and it cannot be guaranteed through the documented API. Any other variant has OpenCode independently
  performing actions — which the review constraints forbid. ❌

### 2.4 OpenCode free-model eligibility (verified)

| Question | Finding |
|---|---|
| Do free models work through the local OpenCode runtime? | ✅ Yes — the local OpenCode client (v2.2.1) is actively serving a free model (`opencode/glm-5.3-flash-free`) on this machine with **no OpenCode Console key stored** (local credential store holds only OpenRouter and Google keys; names/lengths checked, values never displayed) |
| Do external clients receive HTTP 403? | ✅ No — live probe of `https://opencode.ai/inference/openai/v1/chat/completions` with model `glm-5.3-flash-free` returned **HTTP 429** `FreeUsageLimitError` ("Free usage limit reached. Free models work in OpenCode …; subscribe to OpenCode Go to keep going"); a paid model (`glm-5.3-flash`) without a key returned **HTTP 401** `AuthError` ("Missing API key.") |
| Can OpenCode sessions be controlled by a local bridge? | ✅ Mechanically (documented endpoints above); ❌ not in a way that preserves Strix's tool-calling protocol (§2.2) |
| What usage limits apply? | ✅ Free models are quota-limited (429 observed); `longcat-2.5-free` documented at 100 requests/day; OpenCode Go subscription raises/∞-s certain models; local runtime exposes `GET /api/experimental/usage/limits`. Exact per-identity vs per-IP accounting of the anonymous 429 is 🔶 not documented |
| Is the approach permitted by OpenCode's policies? | ✅ Policy is explicit: "Free-tier chat models require OpenCode; use paid models or Go from other clients" (Console models docs). Using free models from AI-VAPT (an external client) is therefore **outside the documented allowed use**; paid models/Go **are** allowed from other clients with a Console API key |

**Bridge verdict — REJECT.** The documented API cannot carry Strix's tool protocol; the degraded
text-simulation variant is brittle and, insofar as it exists to reach free-model quota from a non-OpenCode
client, it is exactly the kind of free-tier restriction circumvention this review must not propose. If
OpenCode models are wanted from AI-VAPT at all, the supported route is a **Console API key with paid models
(or Go)** via the app's existing Custom-Endpoint adapter — which works today with zero code changes and uses
no free-tier allowance.

---

## 3. ChatGPT subscription integration

### 3.1 Existing implementation (verified in §1.3)

- **Login works:** the CLI is functional (live `strix auth status` responds correctly; currently not signed
  in). The OAuth flow is PKCE against `auth.openai.com` with a local `localhost:1455` callback (and a
  `--manual` paste fallback). ✅
- **Token refresh works:** single-use refresh-token rotation with in-process locking, cross-process `flock`
  serialization, and explicit recovery paths for peer-rotation races — all unit-tested. ✅
- **Model routing works:** `chatgpt/<model>` → `_CodexResponsesModel` → ChatGPT backend, always streamed,
  `store=false`, reasoning-effort clamped to backend-accepted values. ✅
- **Credential safety:** OAuth tokens live in `~/.strix/subscription-auth.json` (separate from
  `cli-config.json` so tokens never land in env-var config); runtime credentials are masked in UI/log output;
  this review displayed none. ✅

### 3.2 Is it a supported public API? Is the usage permitted?

- ❌ **Not a public API.** `chatgpt.com/backend-api/codex` is the Codex CLI's internal backend. OpenAI's own
  SIWC documentation for third-party plan usage instructs implementers to use the public
  `https://api.openai.com/v1/responses` and to **not** point the flow at ChatGPT `backend-api` endpoints.
  The codebase itself acknowledges the approach is not officially supported outside OpenAI products
  (`codex.py:4-8`).
- 🔶 **Permission risk.** Because the client-ID used is OpenAI's Codex CLI client, a third-party app
  presenting as Codex is outside the sanctioned pattern; enforcement is at OpenAI's discretion. There is no
  documented AI-VAPT-specific authorization.
- ⚠️ **Cybersecurity policy blocks are likely.** The codebase already implements detection for ChatGPT
  content guardrails flagging "possible cybersecurity risk" / "trusted access for cyber" content, treats them
  as terminal (non-retryable), and surfaces a "set STRIX_LLM to a model that isn't blocked" message — strong
  evidence the authors observed such blocks in practice. A VAPT agent's prompts are precisely the profile
  those guardrails target; expect interruptions on sensitive targets/payloads.

### 3.3 Official alternative: Sign in with ChatGPT — "ChatGPT plan usage" (✅ documented, recommended direction)

OpenAI now publishes a program that does exactly what this project wants, officially:

| Aspect | Documented facts (developers.openai.com/siwc, retrieved 2026-11-16) |
|---|---|
| Who it is for | "In your open-source app: Let eligible users use their ChatGPT plan for AI requests in your app." (paid/remotely-hosted apps require an interest form) |
| Registration | Client registration during the user's sign-in (dynamic flow); a client-ID request process exists (`/siwc/request-client-id`); each issued `client_id` is bound to user + workspace |
| Host identity | Per-host stable `ext_agent_host_id` (RFC-9278 JWK-thumbprint URN recommended; `urn:uuid:` supported), chosen and persisted **before** first sign-in |
| Inference endpoint | **Public** `POST https://api.openai.com/v1/responses`, OAuth access token as Bearer; **must** send `store:false`, `stream:true`; `input` as an array carrying full history; `instructions`/developer messages allowed, explicit system-role items rejected |
| Tools | **Function/custom tools supported** (group in namespaces or via `additional_tools`); unsupported: image gen, file search, Code Interpreter, native computer use, hosted MCP/connectors, `tool_search` |
| Unsupported fields | `background, conversation, max_output_tokens, max_tool_calls, metadata, moderation, multi_agent, prompt, prompt_cache_retention, safety_identifier, temperature, top_logprobs, top_p, truncation, user`; no `previous_response_id` over HTTP |
| Model catalog | `GET /v1/models` with the same token; keep entries with `visibility == "list"`; pass `slug` as `model` |
| Usage limits | Usage-limit errors arrive as `response.failed` with `subscription_sharing_usage_limit_exceeded` / `subscription_sharing_usage_unavailable` (recovery documented); numeric caps not stated in the reviewed pages 🔶 |
| Token renewal | App must refresh the OAuth token and restart/re-inject the new token (Codex app-server config documented for this) |

**Strix compatibility assessment:** structurally high. Strix already runs on the Responses API for its
subscription path (`_CodexResponsesModel`), already forces `store:false` + streaming, already owns client-side
tool execution, and its per-turn ID-rewriter/argument-repair layers exist precisely to survive strict
Responses providers. Gaps to build (future code work, not this review): SIWC OAuth sign-in UI/CLI, client-ID
acquisition, host-ID persistence, model-catalog surfacing in the web console, mapping Strix's toolset into
namespaced function tools, and handling the two `subscription_sharing_*` error codes. Note: unsupported
fields (`temperature`, `top_p`, `max_output_tokens`, …) must be omitted — Strix's `ModelSettings` defaults are
compatible, but the dedupe judge's settings need checking.

**Program caveats:** "open-source" eligibility for a Strix fork should be confirmed during the client-ID
request; the program is in preview; plan usage is still rate-limited per the user's plan; model availability
is account-dependent.

---

## 4. Gemini integration

### 4.1 Existing app support (verified)

- `google` provider is first-class: `router.py:134-148` (prefix `gemini/`|`google/`, key from
  `GEMINI_API_KEY`/`GOOGLE_API_KEY`), env sync in `runtime_credentials.py:100-103`, validate + model
  discovery endpoints (`api.py:1416-1453`, `1602-…`), web-console card. ✅

### 4.2 Official free tier (verified against ai.google.dev, retrieved 2026-11-16)

- The Gemini Developer API has a documented **Free usage tier** ("Active project or free trial; some projects
  need verification"; spend-rate limit N/A). ✅
- Limits are **per model and per tier** (RPM/TPM/RPD; RPD resets midnight Pacific; limits viewable in AI
  Studio's rate-limit page; "Specified rate limits are not guaranteed"). Example free-tier entry in the
  current docs: Gemini Decision 1 — 200 RPM / 50k TPM / 10k RPD; several flagship models show "not supported"
  on Free. Exact numbers for `gemini-2.5-flash`-class models must be read from the AI Studio rate-limit page
  for the specific project 🔶. Practical expectation: workable for interactive/dev runs, too tight for
  sustained multi-agent overnight scans.
- **Terms:** free (unpaid) tier is governed by "Gemini API Terms of Service — Unpaid Services"; unpaid-tier
  prompts may be used by Google to improve products (data-usage caveat relevant when scanning client
  targets). ✅ documented terms split; the exact unpaid-tier data-use sentence is on the ToS page referenced
  by the CLI docs 🔶 (page not fetched in this review).

### 4.3 Gemini CLI OAuth reuse — EXCLUDED ❌

Google's Gemini CLI documentation (geminicli.com "Terms and privacy", last updated 2026-04-10) states
verbatim:

> "Directly accessing the services powering Gemini CLI (for example, the Gemini Code Assist service) using
> third-party software, tools, or services (for example, using OpenClaw with Gemini CLI OAuth) is a violation
> of applicable terms and policies. Such actions may be grounds for suspension or termination of your
> account."

This squarely covers CLIProxyAPI-style OAuth-token reuse/proxying of the Gemini CLI identity. Additionally,
the free-individual OAuth path itself moved: as of **June 18, 2026**, free individual access and Google AI
Pro/Ultra plans migrated from Gemini CLI to **Antigravity CLI**; Gemini CLI remains for enterprise Code
Assist Standard/Enterprise licenses. **Per the review constraints, this approach is excluded from the
recommendation** — no proxying of Gemini CLI/Antigravity OAuth tokens, and no third-party OAuth bridges
(CLIProxyAPI et al.) for Google identities.

**Sanctioned Gemini conclusion:** use the Gemini Developer API free tier with an API key through the app's
existing `google` provider — an API *key*, not a premium subscription, and officially supported for
third-party clients.

---

## 5. Comparison of options

| Option | Sub/API-key requirement | Cost | Free quota | Auth method | Tool-calling compat | Multi-turn compat | Strix compat | Terms/policy risk | Maintenance |
|---|---|---|---|---|---|---|---|---|---|
| **OpenRouter free models** (existing default) | OpenRouter API key (already held) | $0 | Provider-dependent `:free` pool (per-model daily caps) | API key | ✅ Native (LiteLLM route, already benchmarked) | ✅ | ✅ Zero change | Low — sanctioned client | Low |
| **OpenCode bridge** (session API) | None (rides local OpenCode) | $0 | Free models are OpenCode-client-only | Local OpenCode identity | ❌ Cannot carry Strix tool schemas | ❌ Loop owned by OpenCode | ❌ | **High** — unsupported use + possible circumvention | High, undocumented edges | 
| **OpenCode gateway, paid/Go** (Custom-Endpoint adapter) | OpenCode Console API key | Pay-as-you-go credits or Go $10/mo | None for free tier (external clients not permitted) | API key | ✅ OpenAI-compatible chat completions | ✅ | ✅ Zero change (`cloud_hosted`) | Low — documented for other clients | Low |
| **ChatGPT subscription — existing codex path** | ChatGPT Plus/Pro | Already paid (plan) | Plan rate limits (5h/weekly windows) | OAuth (Codex-CLI client ID) | ✅ Implemented (`_CodexResponsesModel`) | ✅ | ✅ Zero change | **Medium-high** — unofficial endpoint; content guardrails flag cybersecurity work (code already detects terminal blocks) | Low (already maintained by upstream) |
| **ChatGPT plan usage — official SIWC** | ChatGPT Plus/Pro + OpenAI client-ID approval | Already paid (plan) | Plan limits; `subscription_sharing_usage_limit_exceeded` handling documented | Official OAuth + host ID | ✅ Function/custom tools supported (namespaces / `additional_tools`) | ✅ (history in `input`, no `previous_response_id`) | ✅ High (Responses-native) — needs integration code | **Low** — sanctioned program (confirm OSS eligibility at registration; preview) | Medium (new OAuth flow, catalog UI, error mapping) |
| **Gemini API free tier** (existing `google` provider) | Gemini API key (already held) | $0 | Per-model RPM/TPM/RPD on Free tier | API key | ✅ Native via LiteLLM `gemini/` route | ✅ | ✅ Zero change | Low — sanctioned; unpaid-tier data-use caveat | Low |
| **Gemini CLI/Antigravity OAuth bridging** | Google account | $0 (free tier moved to Antigravity) | n/a | OAuth token reuse | ❓ (bridge-dependent) | ❓ | ❓ | **Prohibited** — Google ToS: third-party access to Code Assist services is a violation; excluded from recommendation | n/a — excluded |
| **Local Ollama** (already supported) | None | $0 (local hardware) | Unlimited local | None | ✅ (`ollama_chat/` LiteLLM route) | ✅ | ✅ Zero change | None | Medium (hardware/GPU ops) |

---

## 6. Recommended architecture

**Keep Strix/AI-VAPT as the sole owner of tool execution. Do not proxy the app through another agent
harness.** Configure and, where necessary, integrate in this order:

1. **Tier 0 — already working (zero changes):** OpenRouter free models via the existing key
   (`openrouter/<free-model>`); local Ollama for offline/air-gapped runs.
2. **Tier 1 — zero-change, sanctioned, free:** Gemini Developer API free tier using the existing Google API
   key through the `google` provider (`STRIX_LLM=google/<flash-model>`). Accept its RPM/RPD ceilings; use for
   interactive runs and as an outage fallback, not overnight deep scans.
3. **Tier 1 — zero-change, strongest model quality:** built-in ChatGPT subscription path
   (`strix auth login chatgpt`, `STRIX_LLM=chatgpt/<model>`), used knowingly with its unofficial-endpoint and
   guardrail risks; keep OpenRouter/Gemini fallbacks configured for guardrail-blocked runs.
4. **Tier 2 — the one new code investment worth making:** **official SIWC ChatGPT plan usage** — request a
   client ID, implement the OSS sign-in flow (host-ID persistence, token refresh, `/v1/models` catalog),
   route inference to public `api.openai.com/v1/responses` (`store:false`, `stream:true`, namespaced function
   tools), and surface it as a first-class "ChatGPT (subscription)" provider in the web console. This converts
   the "ChatGPT without API billing" goal into a sanctioned, supported integration.
5. **Tier 2 — optional, paid:** OpenCode Console paid/Go models via the existing Custom-Endpoint adapter if
   its curated model catalog is ever wanted — never via free-tier models.
6. **Excluded:** OpenCode session-API bridge; Gemini CLI/Antigravity OAuth reuse.

---

## 7. Risks and limitations

| Risk | Severity | Detail |
|---|---|---|
| Unofficial ChatGPT endpoint | Medium-high | Third-party embedding of the Codex-CLI client/endpoint is unsupported by OpenAI; enforcement at their discretion; SIWC docs explicitly steer plan usage to the public Responses API |
| Content guardrails | High (for this workload) | ChatGPT backend flags cybersecurity content; existing code treats it as terminal and non-retryable — expect blocked runs on some targets; always keep a non-subscription fallback model configured |
| Free-tier exhaustion / rotation | Medium | OpenRouter `:free` pool and OpenCode free models rotate and throttle (OpenCode deprecation list changes monthly; one `:free` model was previously disqualified in the project's own benchmark report for agentic-harness gating); Gemini Free RPD caps are low for multi-agent scans |
| Free-tier data usage | Medium | Unpaid Gemini API terms and some free models (e.g., OpenCode's Inkling/Big Pickle/Iceman free periods) permit provider use/retention of prompts — avoid scanning confidential client data on free tiers |
| SIWC preview constraints | Medium | Program in preview; open-source eligibility must be confirmed via client-ID request; unsupported Responses fields must be pruned; plan-level rate limits still apply |
| LiteLLM prefix coverage | Low | Unknown prefixes (`opencode/…`) fail routing; the `cloud_hosted` adapter or a LiteLLM-registered custom provider would be required for any new gateway |
| Credential hygiene | Low | OAuth tokens already stored outside env-var config; runtime keys in-memory only; this review extracted/displayed nothing |
| Review blind spots | — | Not verified here: exact per-identity accounting of OpenCode's anonymous free quota; numeric SIWC rate limits; v1 OpenCode `tools`/`system` field semantics (v1 source unavailable); Gemini unpaid-tier data-use sentence (ToS page not fetched) |

---

## 8. Proposed implementation sequence (future work — none performed in this review)

1. **Now (configuration only):** confirm OpenRouter free route; add the existing Google key to the `google`
   provider card; run `strix auth login chatgpt` when subscription capacity is wanted; verify each with
   `curl /system/readiness` and a `--scan-mode quick` headless probe.
2. **Short term:** pin a fallback chain (e.g., primary `openrouter/<free>`, fallback `google/<flash>`,
   manual switch to `chatgpt/<model>`), and document guardrail-block remediation for operators.
3. **Medium term:** implement the official **SIWC ChatGPT plan usage** integration (client-ID request →
   sign-in flow + host-ID persistence → Responses-API provider mode → console provider card → usage-limit
   error mapping). Reuse `codex.py` patterns (token store, refresh guard) and `models.py` Responses plumbing.
4. **Deliberately not pursued:** OpenCode bridge (protocol-infeasible + policy), Gemini CLI OAuth reuse
   (prohibited), any free-tier circumvention.

---

## 9. Final recommendation

**Implement first: the ChatGPT subscription route you already own** — it is fully built, fully tested, and
requires only `strix auth login chatgpt` plus `STRIX_LLM=chatgpt/<model>` — **while keeping the OpenRouter
free route as the default and the Gemini API free tier (existing key) as the sanctioned free fallback.** Use
the subscription path with eyes open: it is unofficial, and its content guardrails will occasionally refuse
cybersecurity payloads, at which point operators should switch to the fallback route for that run.

**For new engineering, prioritize the official Sign in with ChatGPT "ChatGPT plan usage" integration** — it
is the only route that delivers "ChatGPT plan powers AI-VAPT, no API billing" under an OpenAI-sanctioned
program, and its documented Responses-API contract (function/custom tools, `store:false`, streaming, history
in `input`) matches Strix's architecture almost exactly.

**Do not build the OpenCode session bridge** (documented API cannot preserve Strix's tool protocol; free
models are out of policy for external clients) and **do not proxy Gemini CLI/Antigravity OAuth tokens**
(explicit ToS violation). Everything achievable with zero code changes today is configuration, not code.

---

*Artifacts produced by this review: this document only. A temporary local `opencode serve` instance was used
to export the OpenAPI spec and was stopped afterwards; no OpenCode sessions were created; no credentials,
tokens, or API keys were read, displayed, or moved; no files under `strix/`, `tests/`, or configuration were
modified; nothing was committed.*
