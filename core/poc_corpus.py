"""Local labeled PoC corpus + online fallback fetcher (Phase 1, Task 1.2).

Why a local corpus?
  The project plan calls for live GitHub / Exploit-DB retrieval. In practice:
   - GitHub *code search* requires an authenticated token (returns 401 unauthed).
   - Exploit-DB is frequently unreachable from restricted lab networks.
   - A thesis must be reproducible. Relying on live, rate-limited, third-party
     endpoints makes results non-deterministic and hard to defend.

Design decision (reproducible + honest):
  1. PRIMARY source: a version-controlled local corpus under data/poc_corpus/
     with a sidecar labels.json mapping each CVE to a curated reliability label.
     The LLM scores the REAL file content, not a dummy placeholder.
  2. OPTIONAL online fetch: only attempted if GITHUB_TOKEN is provided; otherwise
     we transparently fall back to the local corpus. No silent dummy code.
"""
from __future__ import annotations

import json
import os
import requests
from typing import Optional

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "poc_corpus")


def _labels() -> dict:
    path = os.path.join(CORPUS_DIR, "labels.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def corpus_lookup(cve_id: str) -> Optional[str]:
    """Return local PoC source for a CVE if it exists in the corpus."""
    cve = cve_id.strip().upper()
    candidates = [
        os.path.join(CORPUS_DIR, f"{cve}.py"),
        os.path.join(CORPUS_DIR, f"{cve}.txt"),
        os.path.join(CORPUS_DIR, f"{cve}.sh"),
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c) as f:
                return f.read()
    return None


def corpus_label(cve_id: str) -> Optional[dict]:
    return _labels().get(cve_id.strip().upper())


def fetch_github_poc(cve_id: str, token: Optional[str] = None,
                     timeout: int = 6, max_chars: int = 2000) -> Optional[str]:
    """Best-effort GitHub code search. Returns raw code or None.

    Requires GITHUB_TOKEN (set in env) because unauthenticated code search
    returns HTTP 401. Never returns dummy code.
    """
    token = token or os.getenv("GITHUB_TOKEN")
    if not token:
        return None
    headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"}
    try:
        r = requests.get(
            "https://api.github.com/search/code",
            params={"q": f"{cve_id} filename:exploit OR filename:poc", "per_page": 3},
            headers=headers, timeout=timeout,
        )
        if r.status_code != 200:
            return None
        items = r.json().get("items", [])
        for it in items:
            raw_url = (it["html_url"].replace("github.com", "raw.githubusercontent.com")
                       .replace("/blob/", "/"))
            rr = requests.get(raw_url, headers=headers, timeout=timeout)
            if rr.status_code == 200 and rr.text.strip():
                return rr.text[:max_chars]
    except Exception as e:  # pragma: no cover - network dependent
        print(f"[-] GitHub fetch failed for {cve_id}: {e}")
    return None


def get_poc(cve_id: str, online: bool = True, token: Optional[str] = None) -> str:
    """Resolve exploit source: local corpus first, then optional GitHub."""
    local = corpus_lookup(cve_id)
    if local:
        return local
    if online:
        gh = fetch_github_poc(cve_id, token=token)
        if gh:
            return gh
    raise RuntimeError(
        f"No PoC available for {cve_id}. Add it to data/poc_corpus/ "
        f"or supply GITHUB_TOKEN for live GitHub search."
    )
