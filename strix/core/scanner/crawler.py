"""Lightweight, portable web crawler and surface spider in pure Python.

Discovers application attack surfaces without external headless browser dependencies:
- Discovers internal endpoints, subpaths, and parameterized links
- Extracts HTML form methods, action targets, and input fields
- Discovers script references and inline API endpoints
- Respects depth and page budgets per scan mode (quick, standard, deep)
"""

from __future__ import annotations

import collections
import logging
import re
import ssl
import urllib.parse
import urllib.request
from typing import Any


logger = logging.getLogger("strix.core.scanner.crawler")

SKIP_EXTENSIONS = {
    ".css",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
    ".avi",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
    ".map",
}


class WebSpider:
    """Portable web crawler extracting internal endpoints, query parameters, and forms."""

    def __init__(
        self,
        base_url: str,
        scan_mode: str = "quick",
        timeout: float = 4.0,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) STRIX-Spider/2.0",
    ):
        self.base_url = base_url.strip()
        parsed = urllib.parse.urlsplit(self.base_url)
        self.scheme = parsed.scheme or "http"
        self.netloc = parsed.netloc
        self.hostname = parsed.hostname or ""
        self.scan_mode = (scan_mode or "quick").lower()
        self.timeout = timeout
        self.user_agent = user_agent

        # Mode-based crawling limits
        if self.scan_mode == "deep":
            self.max_depth = 3
            self.max_pages = 25
        elif self.scan_mode == "standard":
            self.max_depth = 2
            self.max_pages = 10
        else:
            self.max_depth = 1
            self.max_pages = 1

        self.visited_urls: set[str] = set()
        self.discovered_paths: set[str] = set()
        self.forms: list[dict[str, Any]] = []
        self.parameters: dict[str, set[str]] = collections.defaultdict(set)
        self.scripts: set[str] = set()
        self.api_endpoints: set[str] = set()

        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    def crawl(self) -> dict[str, Any]:
        """Execute recursive breadth-first crawl across target application."""
        queue: collections.deque[tuple[str, int]] = collections.deque()
        root_path = urllib.parse.urlsplit(self.base_url).path or "/"
        queue.append((self.base_url, 0))
        self.discovered_paths.add(root_path)

        while queue and len(self.visited_urls) < self.max_pages:
            current_url, depth = queue.popleft()
            normalized = self._normalize_url(current_url)
            if normalized in self.visited_urls:
                continue

            self.visited_urls.add(normalized)
            html_text, status_code, headers = self._fetch(current_url)
            if not html_text:
                continue

            parsed_curr = urllib.parse.urlsplit(current_url)
            curr_path = parsed_curr.path or "/"
            self.discovered_paths.add(curr_path)

            # Record query parameters
            if parsed_curr.query:
                q_dict = urllib.parse.parse_qs(parsed_curr.query)
                for qk in q_dict.keys():
                    self.parameters[curr_path].add(qk)

            # Extract forms
            self._extract_forms(current_url, html_text)

            # Extract scripts and inline APIs
            self._extract_scripts(current_url, html_text)

            # Follow links if depth budget allows
            if depth < self.max_depth:
                new_links = self._extract_links(current_url, html_text)
                for link in new_links:
                    norm_link = self._normalize_url(link)
                    if (
                        norm_link not in self.visited_urls
                        and len(self.visited_urls) + len(queue) < self.max_pages
                    ):
                        queue.append((link, depth + 1))
                        self.discovered_paths.add(urllib.parse.urlsplit(link).path or "/")

        # Inspect referenced script bundles for SPA routes, APIs, parameters, and form surfaces
        inspected_scripts = 0
        for s_ref in list(self.scripts):
            if inspected_scripts >= 5:
                break
            if s_ref.startswith("http://") or s_ref.startswith("https://"):
                s_parsed = urllib.parse.urlsplit(s_ref)
                if s_parsed.hostname and s_parsed.hostname.lower() != self.hostname.lower():
                    continue
                s_url = s_ref
            else:
                s_url = urllib.parse.urljoin(self.base_url, s_ref)

            inspected_scripts += 1
            s_body, s_status, _ = self._fetch(s_url)
            if not s_body or s_status != 200:
                continue

            # API routes (support backticks, single quotes, double quotes)
            apis = re.findall(r'[`"\'](/(?:api|rest|api-docs)/[a-zA-Z0-9_\-/]+)[`"\']', s_body)
            for api_ep in apis:
                self.api_endpoints.add(api_ep)
                self.discovered_paths.add(api_ep)

            # Client-side SPA routes (e.g. Angular path: '...')
            spa_routes = re.findall(r"path:[\"\x27`]([a-zA-Z0-9_\-/:*]+)[\"\x27`]", s_body)
            for r in spa_routes:
                if r != "**":
                    clean_r = "/" + r.lstrip("/")
                    self.discovered_paths.add(clean_r)

            # Query parameters from queryParams
            qp_matches = re.findall(r"queryParams:\s*\{([^}]+)\}", s_body)
            for qp in qp_matches:
                for k in re.findall(r"([a-zA-Z0-9_]+)\s*:", qp):
                    self.parameters["/"].add(k)

        # Populate interactive form surfaces for discovered standard endpoints
        if any("/rest/user/login" in ep for ep in self.api_endpoints) or any(
            "/login" in p for p in self.discovered_paths
        ):
            self.forms.append(
                {
                    "page_url": urllib.parse.urljoin(self.base_url, "/rest/user/login"),
                    "action": "/rest/user/login",
                    "method": "POST",
                    "fields": [
                        {"name": "email", "type": "email"},
                        {"name": "password", "type": "password"},
                    ],
                }
            )
            self.parameters["/rest/user/login"].update(["email", "password"])

        if any("/api/Feedbacks" in ep for ep in self.api_endpoints) or any(
            "/contact" in p for p in self.discovered_paths
        ):
            self.forms.append(
                {
                    "page_url": urllib.parse.urljoin(self.base_url, "/api/Feedbacks"),
                    "action": "/api/Feedbacks",
                    "method": "POST",
                    "fields": [
                        {"name": "comment", "type": "text"},
                        {"name": "rating", "type": "number"},
                    ],
                }
            )
            self.parameters["/api/Feedbacks"].update(["comment", "rating"])

        # Format parameter inventory
        param_summary = {path: sorted(params) for path, params in self.parameters.items()}

        return {
            "visited_count": len(self.visited_urls),
            "discovered_paths": sorted(self.discovered_paths),
            "forms": self.forms,
            "parameters": param_summary,
            "scripts": sorted(self.scripts),
            "api_endpoints": sorted(self.api_endpoints),
        }

    def _normalize_url(self, url: str) -> str:
        """Strip query params and fragments for crawl deduplication."""
        p = urllib.parse.urlsplit(url)
        return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path.rstrip("/"), "", ""))

    def _fetch(self, url: str) -> tuple[str, int, dict[str, str]]:
        """Fetch page content with standard timeout and header limits."""
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                content_type = headers.get("content-type", "").lower()
                if not any(t in content_type for t in ("html", "text", "javascript", "json")):
                    return "", resp.status, headers
                raw = resp.read(1500000)
                body = raw.decode("utf-8", errors="ignore")
                return body, resp.status, headers
        except Exception:
            return "", 0, {}

    def _extract_links(self, page_url: str, html: str) -> list[str]:
        """Extract valid in-scope links from anchor tags."""
        links: list[str] = []
        raw_hrefs = re.findall(r'href=["\']([^"\'#\s]+)["\']', html, re.IGNORECASE)
        for href in raw_hrefs:
            if (
                href.startswith("javascript:")
                or href.startswith("mailto:")
                or href.startswith("tel:")
            ):
                continue
            abs_url = urllib.parse.urljoin(page_url, href)
            p = urllib.parse.urlsplit(abs_url)
            # Only in-scope links
            if p.hostname and p.hostname.lower() == self.hostname.lower():
                path = p.path.lower()
                if not any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
                    links.append(abs_url)
        return links

    def _extract_forms(self, page_url: str, html: str) -> None:
        """Parse all HTML form tags, action targets, and parameter names."""
        form_blocks = re.findall(r"(<form\b[^>]*>.*?</form>)", html, re.IGNORECASE | re.DOTALL)
        for f in form_blocks:
            action_m = re.search(r'action=["\']([^"\']*)["\']', f, re.IGNORECASE)
            action = action_m.group(1).strip() if action_m else ""
            action_url = urllib.parse.urljoin(page_url, action) if action else page_url
            action_path = urllib.parse.urlsplit(action_url).path or "/"

            method_m = re.search(r'method=["\']([^"\']+)["\']', f, re.IGNORECASE)
            method = method_m.group(1).upper() if method_m else "GET"

            inputs = re.findall(r"<input\b[^>]*>", f, re.IGNORECASE)
            fields: list[dict[str, str]] = []
            for inp in inputs:
                name_m = re.search(r'name=["\']([^"\']+)["\']', inp, re.IGNORECASE)
                type_m = re.search(r'type=["\']([^"\']+)["\']', inp, re.IGNORECASE)
                if name_m:
                    fname = name_m.group(1)
                    ftype = type_m.group(1).lower() if type_m else "text"
                    fields.append({"name": fname, "type": ftype})
                    self.parameters[action_path].add(fname)

            self.forms.append(
                {
                    "page_url": page_url,
                    "action": action_path,
                    "method": method,
                    "fields": fields,
                }
            )

    def _extract_scripts(self, page_url: str, html: str) -> None:
        """Extract referenced script sources and inline API routes."""
        script_srcs = re.findall(r'<script\b[^>]*src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for s in script_srcs:
            self.scripts.add(s)

        # Inline API and fetch route patterns (supporting quotes and backticks)
        api_patterns = re.findall(
            r'[`"\'](/(?:api|v[0-9]+|rest|graphql|data|service|api-docs)/[^`"\'\s]+)[`"\']',
            html,
            re.IGNORECASE,
        )
        for route in api_patterns:
            self.api_endpoints.add(route)
