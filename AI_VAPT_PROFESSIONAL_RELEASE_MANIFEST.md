# AI-VAPT v1.7.0 RC1 — Professional Release Manifest
## Target Branch: `ai-vapt-release`
**Date:** 2026-11-17 | **Auditor & Release Engineer:** Antigravity Autonomous Engine | **Release Baseline:** v1.7.0 RC1

---

## 1. Executive Overview & Scope

The `ai-vapt-release` branch is the **curated, clean, production-grade distribution** of the AI-VAPT framework designed for external users, security researchers, and enterprise evaluation. 

This branch is **independently cloneable, installable, and runnable**. It provides the complete functional application runtime, all agent frameworks, multi-provider LLM support, Docker sandbox automation, testing suites, professional documentation, and unified launchers. All internal thesis notes, developmental phase reports, forensic debug traces, and machine-local artifacts are cleanly excluded.

> [!IMPORTANT]
> The professional distribution is curated from the complete development source **without deleting any development files** from the working branch `ai-vapt-full-application`.

---

## 2. Professional Distribution Physical File Inventory (648 Files Total)

A physical filesystem audit of the verified clean package confirms exactly **648 files** in the curated professional distribution:

| Subsystem / Directory | Physical File Count | Description |
| :--- | :---: | :--- |
| **Application Runtime (`strix/`)** | **404** | Complete multi-agent graph, core decision engine, scanner, crawler, fuzzer, in-memory credential vault, tools, skills, TUI, viewer, and Web Console SPA assets |
| **Automated Testing Suite (`tests/`)** | **152** | Full regression harness (142 tracked + 10 new regression test modules) |
| **Curated Public Documentation (`docs/`)** | **36** | Production documentation covering usage, security tools, LLM providers, cloud, and integrations |
| **Packaging & Production Scripts (`scripts/`)** | **13** | Critical Hatchling build hook (`tui_sidecar_hook.py`), Docker helpers, and lab automation |
| **Root Configuration & Launchers** | **14** | Operational launchers (`ai-vapt.sh`, `juice-shop.sh`, `setup.sh`, `start.sh`, `stop.sh`), build configuration (`pyproject.toml`, `uv.lock`, `.gitignore`), license (`LICENSE`), and guides (`README.md`, `AI_VAPT_SETUP_GUIDE.md`, `CHANGELOG.md`, `AGENTS.md`, `.env.example`) |
| **GitHub Automation (`.github/`)** | **13** | Issue templates, CI/CD setup-python action, Dependabot configuration, and logo |
| **Consumer Agent Skills (`skills/`)** | **9** | Standalone agent workflow skills (API security, OWASP Top 10, code auditing) |
| **Web Console UI Screenshots (`screenshots/`)**| **5** | Clean UI panels: `active_assessment.png`, `history.png`, `new_assessment.png`, `reports.png`, `settings.png` |
| **Docker Container Specs (`containers/`)** | **2** | Sandbox container specifications (`Dockerfile`, `docker-entrypoint.sh`) |
| **Total Physical Files** | **648** | **100% Curated, Functional & Self-Contained** |

### Reconciliation of Documentation & Script Differences
1. **Curated Public Documentation (36 Files vs 179 Files):**
   - The development repository contains 179 files under `docs/`.
   - 143 files reside in internal academic directories (`docs/project_management/`, `docs/research/`, `docs/ai_vapt_integration/`, `docs/strix_ai_vapt_integration/`, and `docs/AI_VAPT_*.md`). These contain university supervisor notes, M.Tech thesis logs, and developmental path references (including local `/home/vinit/` paths and `vinit` usernames).
   - In `ai-vapt-release`, these 143 internal files are cleanly excluded, retaining precisely the **36 curated public documentation files** (`docs/usage/`, `docs/tools/`, `docs/llm-providers/`, `docs/cloud/`, `docs/integrations/`, `docs/advanced/`, `docs/images/`, `docs/logo/`, root `.md` / `.mdx`).
2. **Production Scripts (13 Files vs 14 Files):**
   - `scripts/generate_docx_report.py` contains hardcoded thesis author metadata and is retained exclusively on `ai-vapt-full-application`.
   - The remaining 13 scripts (including the Hatchling build hook `tui_sidecar_hook.py`, Docker entrypoint builders, and lab launchers) are included in `ai-vapt-release`.

---

## 3. Explicit Exclusion List & Rationale

The following categories of files are **STRICTLY EXCLUDED** from the professional distribution branch:

| Excluded Category | Count / Pattern | Rationale |
| :--- | :---: | :--- |
| **Internal Thesis & Project Docs** | 143 files (`docs/project_management/`, `docs/research/`, etc.) | Academic thesis chapters, meeting notes, and local environment logs. |
| **Internal Thesis Report Generator** | 1 file (`scripts/generate_docx_report.py`) | Thesis author metadata and local docx formatting utilities. |
| **Internal Engineering Reports** | 46 files (`AI_VAPT_*.md`) | Internal development phase logs, root-cause investigations, and audit records preserved exclusively on `ai-vapt-full-application`. |
| **Forensic PDF Inspection Images** | 8 files (`screenshots/pdf_inspection_*/`) | Granular page-by-page visual inspection images used for academic and thesis verification. |
| **Benchmark & Research Experiments** | 79 files (`benchmarks/`, `benchmark_results/`, `experiments/`, `headless_qa_results/`) | Historical benchmark results, experimental prompts, and headless QA runs. |
| **Runtime Data & Local Caches** | `strix_runs/`, `agent_runs/`, `.venv/`, `logs/` | Local execution runs (239 directories, 18 MB), virtual environments, and server logs. Excluded by `.gitignore`. |

---

## 4. Independent Verification in Clean Isolated Working Copy

To verify that `ai-vapt-release` is independently functional, an isolated clean copy was assembled in `/tmp/ai_vapt_professional_test` and thoroughly validated:

1. **Physical File Parity:** Exactly **648 files** were assembled, representing the complete runtime application without any internal reports or debug traces.
2. **Secret Scanning:** An automated regex scan across all 648 distribution files found:
   - **0** active API keys or private keys.
   - **0** hardcoded Cloudflare Quick Tunnel URLs.
   - **0** local filesystem paths (`/home/vinit/`).
   - **0** unauthorized personal username mentions (only standard `pyproject.toml` author metadata and official GitHub repo URLs).
3. **Packaging Build & Install (`uv sync`):** Successfully built `strix-agent` wheel via `scripts/tui_sidecar_hook.py` and synchronized dependencies with exit code 0.
4. **Runtime Import Integrity:** All 16 primary application modules loaded with 100% success:
   - `strix.core.decision_engine.engine`, `strix.core.gap_bridge`, `strix.core.runtime_credentials`
   - `strix.core.runner`, `strix.core.scanner.crawler`, `strix.core.scanner.port_scanner`, `strix.core.scanner.full_scanner`
   - `strix.interface.api`, `strix.interface.readiness`, `strix.interface.viewer.report_pdf`
   - `strix.llm.router`, `strix.llm.cloud_provider`
   - `strix.report.builder`, `strix.report.evidence`, `strix.report.reconciliation`, `strix.report.verification`
5. **Launcher Smoke Test:** `./ai-vapt.sh start --port 8014` successfully launched the Web Console (PID 351182), responded `HTTP 200` on `/health` (`{"status":"ok","service":"ai-vapt-gateway"}`), and terminated cleanly with `./ai-vapt.sh stop`.
6. **Automated Test Suite Execution:** Running `pytest` on reporting suites in the clean copy achieved **228 passed tests in 143.53s** with zero failures.

---

## 5. Corrected Safe Branch Creation & Push Commands

> [!CAUTION]
> **OPERATOR APPROVAL REQUIRED:** This procedure uses an isolated temporary staging repository in `/tmp/ai_vapt_release_staging`. The development working directory `/home/vinit/AI_VAPT/ai_vapt_framework` remains 100% untouched on `ai-vapt-full-application`.

```bash
# ==============================================================================
# SAFE OPERATOR PROCEDURE: RELEASE 2 (ai-vapt-release)
# EXECUTED IN AN ISOLATED TEMPORARY DIRECTORY (WORKING TREE PRESERVED)
# ==============================================================================

# 1. Ensure current working directory is untouched
cd /home/vinit/AI_VAPT/ai_vapt_framework
test $(git branch --show-current) = "ai-vapt-full-application"

# 2. Assemble curated professional distribution tree into temporary staging
rm -rf /tmp/ai_vapt_release_staging
mkdir -p /tmp/ai_vapt_release_staging

python3 - << 'EOF'
import os, shutil
from pathlib import Path

ROOT = Path("/home/vinit/AI_VAPT/ai_vapt_framework")
TARGET = Path("/tmp/ai_vapt_release_staging")

top_level = [
    ".env.example", ".gitignore", "AGENTS.md", "AI_VAPT_SETUP_GUIDE.md",
    "CHANGELOG.md", "LICENSE", "README.md", "ai-vapt.sh", "juice-shop.sh",
    "pyproject.toml", "setup.sh", "start.sh", "stop.sh", "uv.lock"
]
for f in top_level:
    shutil.copy2(ROOT / f, TARGET / f)

full_dirs = ["strix", "tests", "containers", "skills", ".github"]
ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "*.log", ".state")
for d in full_dirs:
    shutil.copytree(ROOT / d, TARGET / d, ignore=ignore)

internal_prefixes = ('project_management/', 'research/', 'ai_vapt_integration/', 'strix_ai_vapt_integration/')
docs_src = ROOT / "docs"
for p in docs_src.rglob("*"):
    if p.is_file() and not p.name.endswith(".pyc"):
        rel = p.relative_to(docs_src)
        rel_str = str(rel)
        if not rel_str.startswith(internal_prefixes) and not rel_str.startswith("AI_VAPT_"):
            dst = TARGET / "docs" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)

scripts_src = ROOT / "scripts"
(TARGET / "scripts").mkdir(parents=True, exist_ok=True)
for p in scripts_src.iterdir():
    if p.is_file() and p.name != "generate_docx_report.py":
        shutil.copy2(p, TARGET / "scripts" / p.name)

(TARGET / "screenshots").mkdir(parents=True, exist_ok=True)
for s in ["active_assessment.png", "history.png", "new_assessment.png", "reports.png", "settings.png"]:
    shutil.copy2(ROOT / "screenshots" / s, TARGET / "screenshots" / s)

for sh in ["ai-vapt.sh", "juice-shop.sh", "setup.sh", "start.sh", "stop.sh"]:
    (TARGET / sh).chmod(0o755)
for s in (TARGET / "scripts").glob("*.sh"):
    s.chmod(0o755)
EOF

# 3. Initialize fresh git repository on ai-vapt-release
cd /tmp/ai_vapt_release_staging
git init -b ai-vapt-release
git config user.name "AI-VAPT Release Engineer"
git config user.email "release@ai-vapt.org"

# 4. Verify staged release inventory (exactly 648 files)
git add --all
git status --short
test $(git ls-files | wc -l) -eq 648 && echo "[PASS] Exactly 648 files staged"

# 5. Commit professional release
git commit -m "feat(release): AI-VAPT v1.7.0 RC1 — clean professional distribution"

# 6. Push to GitHub (Requires Operator Authorization)
git remote add origin https://github.com/Vinit-Solanki16/ai_vapt_framework.git
git push origin ai-vapt-release

# 7. Clean up temporary staging
cd /home/vinit/AI_VAPT/ai_vapt_framework
rm -rf /tmp/ai_vapt_release_staging
```

---

## 6. Licensing & Legal Disclaimer

1. **Framework License:** The AI-VAPT framework is distributed under the **Apache License, Version 2.0**. This applies to original contributions and derivative works incorporated from upstream Strix (`usestrix/strix`, Apache 2.0).
2. **Third-Party Dependencies:** Third-party libraries specified in `pyproject.toml` and pinned in `uv.lock` are installed dynamically by the end user's package manager under their respective permissive open-source licenses (Apache 2.0, MIT, BSD, LGPL).
3. **Legal Disclaimer:** This technical review confirms license compatibility for open-source research and engineering use; it does not constitute formal legal counsel regarding worldwide commercial redistribution of bundled third-party binaries or trademarks.
