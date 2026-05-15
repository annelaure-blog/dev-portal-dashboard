#!/usr/bin/env python3
"""
Internal broken link checker using ReadMe API content (no crawling).

Fetches pages from ReadMe branches, extracts internal links, and checks them.

Usage:
  python scripts/broken_links_api.py --project retail-media --json-out UI/broken_links.json
"""

import argparse
import json
import os
import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import requests

README_BASE = "https://api.readme.com/v2"

ASSET_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".css", ".js", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp4", ".webm", ".mp3", ".wav", ".pdf", ".zip", ".tar", ".gz",
}

# Project presets
PROJECTS = {
    "retail-media": {
        "token": os.getenv("README_TOKEN_RETAIL_MEDIA", ""),
        "branch": "v2026.01",
        "label": "Retail Media API",
        "host": "developers.criteo.com",
        "scope_prefixes": ["/retail-media/v2026.01", "/retail-media"],
    },
    "retailer-integration": {
        "token": os.getenv("README_TOKEN_RETAILER_INTEGRATION", ""),
        "branch": "v2026.01",
        "label": "Retailer Integration",
        "host": "developers.criteo.com",
        "scope_prefixes": ["/retailer-integration/v2026.01", "/retailer-integration"],
    },
    "marketing-solutions": {
        "token": os.getenv("README_TOKEN_MARKETING_SOLUTIONS_STABLE", ""),
        "branch": "v2026.01",
        "label": "Marketing Solutions API",
        "host": "developers.criteo.com",
        "scope_prefixes": ["/marketing-solutions/v2026.01", "/marketing-solutions"],
    },
}


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in ("script", "style"):
            self._skip = True
            return
        if tag in ("a", "link"):
            for k, v in attrs:
                if k == "href" and v:
                    self.links.append(v)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False


MD_LINK_RE = re.compile(r"\[.+?\]\(([^)\s]+)\)")
LOCALHOST_PREFIXES = (
    "http://localhost:3000",
    "https://localhost:3000",
    "http://127.0.0.1:3000",
    "https://127.0.0.1:3000",
)


def extract_links_from_markdown(markdown: str) -> List[str]:
    return [m.group(1) for m in MD_LINK_RE.finditer(markdown or "")]


def is_asset(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in ASSET_EXTENSIONS)


def normalize_link(base: str, href: str) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith("#"):
        return None
    if href.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return None
    # Ignore ReadMe internal doc: scheme so we don't flag it as broken
    if href.lower().startswith("doc:"):
        return None
    return urljoin(base, href)


def get_categories(token: str, branch: str, section: str) -> List[Dict]:
    url = f"{README_BASE}/branches/{branch}/categories/{section}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", []) or []


def list_pages_in_category(token: str, branch: str, section: str, title: str) -> List[Dict]:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{README_BASE}/branches/{branch}/categories/{section}/{requests.utils.quote(title, safe='')}/pages"
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", []) or []


def get_page_content(token: str, branch: str, slug: str, section: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{README_BASE}/branches/{branch}/{section}/{requests.utils.quote(slug, safe='')}"
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    obj = resp.json().get("data") or resp.json()
    content = obj.get("content", {}) or {}
    return content.get("body") or ""


def collect_links_from_pages(token: str, branch: str, sections: List[str]) -> Dict[str, Set[str]]:
    """
    Return map of link -> set of source page slugs for traceability.
    """
    links: Dict[str, Set[str]] = {}
    for section in sections:
        try:
            cats = get_categories(token, branch, section)
        except Exception:
            continue
        for cat in cats:
            title = cat.get("title")
            if not title:
                continue
            try:
                pages = list_pages_in_category(token, branch, section, title)
            except Exception:
                continue
            for page in pages:
                slug = page.get("slug")
                if not slug:
                    continue
                try:
                    body = get_page_content(token, branch, slug, section)
                except Exception:
                    continue
                parser = LinkExtractor()
                try:
                    parser.feed(body)
                    for href in parser.links:
                        links.setdefault(href, set()).add(slug)
                except Exception:
                    pass
                for href in extract_links_from_markdown(body):
                    links.setdefault(href, set()).add(slug)
    return links


def filter_internal_links(raw_links: Dict[str, Set[str]], host: str, scope_prefixes: List[str]) -> Dict[str, Set[str]]:
    allowed_prefixes = [p if p.startswith("/") else f"/{p}" for p in scope_prefixes]
    filtered: Dict[str, Set[str]] = {}
    base = f"https://{host}"
    for href, sources in raw_links.items():
        url = normalize_link(base, href)
        if not url or is_asset(url):
            continue
        parsed = urlparse(url)
        if parsed.netloc != host:
            continue
        path = parsed.path
        if allowed_prefixes and not any(path.startswith(pref) for pref in allowed_prefixes):
            continue
        if url not in filtered:
            filtered[url] = set()
        filtered[url].update(sources)
    return filtered


def filter_external_links(raw_links: Dict[str, Set[str]], host: str, scope_prefixes: List[str]) -> Dict[str, Set[str]]:
    allowed_prefixes = [p if p.startswith("/") else f"/{p}" for p in scope_prefixes]
    filtered: Dict[str, Set[str]] = {}
    base = f"https://{host}"
    for href, sources in raw_links.items():
        url = normalize_link(base, href)
        if not url or is_asset(url):
            continue
        # Skip local dev links so they don't show as broken
        if url.lower().startswith(LOCALHOST_PREFIXES):
            continue
        parsed = urlparse(url)
        path = parsed.path
        # External means different host, or same host but outside allowed prefixes
        if parsed.netloc == host and allowed_prefixes and any(path.startswith(pref) for pref in allowed_prefixes):
            continue
        if url not in filtered:
            filtered[url] = set()
        filtered[url].update(sources)
    return filtered


def check_links(urls: Dict[str, Set[str]], timeout: int = 8) -> List[Dict[str, object]]:
    broken: List[Dict[str, str]] = []
    for url, sources in sorted(urls.items()):
        try:
            resp = requests.get(url, timeout=timeout, allow_redirects=True)
            if resp.status_code >= 400:
                broken.append(
                    {"url": url, "status": str(resp.status_code), "detail": resp.reason or "", "sources": sorted(sources)}
                )
        except Exception as exc:
            broken.append({"url": url, "status": "error", "detail": str(exc), "sources": sorted(sources)})
    return broken


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", action="append", choices=sorted(PROJECTS.keys()), required=True, help="Project preset to check (repeatable)")
    ap.add_argument("--json-out", default=None, help="Write results to JSON file")
    ap.add_argument("--timeout", type=int, default=8, help="HTTP timeout for link checks")
    ap.add_argument("--include-reference", action="store_true", help="Also include reference pages (default: only guides)")
    args = ap.parse_args()

    projects_payload: Dict[str, Dict[str, object]] = {}
    total_scanned = 0
    sections = ["guides", "reference"] if args.include_reference else ["guides"]

    for key in args.project:
        cfg = PROJECTS[key]
        token = cfg["token"]
        branch = cfg["branch"]
        label = cfg.get("label", key)
        host = cfg["host"]
        prefixes = cfg.get("scope_prefixes") or []

        print(f"🌐 Checking {label} (branch {branch})")

        raw_links = collect_links_from_pages(token, branch, sections)
        print(f"   • Extracted {len(raw_links)} raw links from {', '.join(sections)}")

        internal_links = filter_internal_links(raw_links, host, prefixes)
        print(f"   • Filtered to {len(internal_links)} internal scoped links")
        external_links = filter_external_links(raw_links, host, prefixes)
        print(f"   • Filtered to {len(external_links)} external links")

        broken = check_links(internal_links, timeout=args.timeout)
        broken_external = check_links(external_links, timeout=args.timeout)
        print(f"   • Broken links: {len(broken)}")
        print(f"   • Broken external links: {len(broken_external)}")

        projects_payload[key] = {
            "label": label,
            "branch": branch,
            "extracted_links": len(raw_links),
            "checked_links": len(internal_links),
            "external_links": len(external_links),
            "broken": [b["url"] for b in broken],
            "broken_detail": broken,
            "broken_external": [b["url"] for b in broken_external],
            "broken_external_detail": broken_external,
        }
        total_scanned += len(internal_links)

    if args.json_out:
        payload = {"projects": projects_payload, "scanned": total_scanned}
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"💾 Wrote JSON results to {args.json_out}")


if __name__ == "__main__":
    main()
