#!/usr/bin/env python3
"""
OAS vs Guides Coverage — Retail Media + Marketing Solutions

Compares operations from the OAS to calls referenced in guide pages (ReadMe API),
per project, and writes a JSON payload for the dashboard.
"""

import argparse
import json
import os
import re
from typing import Dict, List, Set, Tuple

import requests

BASE_URL = "https://api.readme.com/v2"

PROJECTS = {
    "retail-media": {
        "token": os.getenv("README_TOKEN_RETAIL_MEDIA_STABLE", ""),
        "branch": "v2026.01",
        "label": "Retail Media API",
        "oas_url": "https://api.criteo.com/2026-01/RetailMedia/open-api-specifications.json",
        "guide_categories": ["Guides for Retail Media API"],
        "path_prefix": "retail-media",
    },
    "marketing-solutions": {
        "token": os.getenv("README_TOKEN_MARKETING_SOLUTIONS_STABLE", ""),
        "branch": "v2026.01",
        "label": "Marketing Solutions API",
        "oas_url": "https://api.criteo.com/2026-01/MarketingSolutions/open-api-specifications.json",
        "guide_categories": [
            "Guides for Marketing Solutions API",
            "Guides for Marketing Solutions",
        ],
        "path_prefix": "marketing-solutions",
    },
}

API_URL_PATTERN = re.compile(
    r"https://api\\.criteo\\.com/(?P<version>[^/\\s\"'`()<>]+)/(?P<path>[^,\\s\"'`()<>]+)",
    re.IGNORECASE,
)

PATH_INLINE_PATTERN = re.compile(
    r"`?(/(?:\\d{4}-\\d{2}/)?[A-Za-z0-9{}._-]+(?:/[A-Za-z0-9{}._-]+)*)`?",
    re.IGNORECASE,
)

METHOD_BADGE_TAG_PATTERN = re.compile(
    r"<BadgeHTTP(?P<method>GET|POST|PUT|PATCH|DELETE)\\s*/?>",
    re.IGNORECASE,
)

METHOD_BADGE_IMG_PATTERN = re.compile(
    r'class="http-btn"[^>]*src="[^"]*(?P<method>get|post|put|patch|delete)[^"]*"',
    re.IGNORECASE,
)

METHOD_BOLD_PATTERN = re.compile(
    r"\\*\\*(GET|POST|PUT|PATCH|DELETE)\\*\\*",
    re.IGNORECASE,
)

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}"
)


def normalize_path(path: str) -> str:
    if not isinstance(path, str):
        return "/"

    path = path.split("?", 1)[0].strip()
    m_ver = re.match(r"^\d{4}-\d{2}/(.+)$", path)
    if m_ver:
        path = m_ver.group(1)
    path = path.lstrip("/").rstrip("/")
    path = re.sub(r"\{[^}]+\}", "{}", path)

    segments: List[str] = []
    for seg in path.split("/"):
        if not seg:
            continue
        if seg.isdigit() or UUID_PATTERN.fullmatch(seg):
            segments.append("{}")
        else:
            segments.append(seg)

    out = "/".join(segments) or "/"
    return out.lower()


def get_categories(token: str, branch: str, section: str) -> List[str]:
    url = f"{BASE_URL}/branches/{branch}/categories/{section}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return [c.get("title") for c in data.get("data", []) if c.get("title")]


def list_pages_in_category(token: str, branch: str, section: str, title: str) -> List[Dict]:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/branches/{branch}/categories/{section}/{requests.utils.quote(title, safe='')}/pages"
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", []) or []


def get_guide_page_content(token: str, branch: str, slug: str) -> Dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/branches/{branch}/guides/{requests.utils.quote(slug, safe='')}"
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    raw = resp.json()
    obj = raw.get("data", raw)
    content = obj.get("content", {})
    return {"raw": raw, "body": content.get("body") or ""}


def get_filtered_guide_pages(token: str, branch: str, categories: List[str]) -> List[Dict]:
    filtered: List[Dict] = []
    guide_categories = get_categories(token, branch, "guides")
    matched = False
    for cat in guide_categories:
        if categories and cat not in categories:
            continue
        pages = list_pages_in_category(token, branch, "guides", cat)
        filtered.extend(pages)
        matched = True
    # Fallback to all guides if no category matched
    if categories and not matched:
        for cat in guide_categories:
            pages = list_pages_in_category(token, branch, "guides", cat)
            filtered.extend(pages)
    return filtered


def extract_calls_with_methods(text: str, path_prefix: str = "") -> List[Dict[str, str]]:
    results = []
    current_method: str = ""

    if not text:
        return results

    for line in text.splitlines():
        badge = METHOD_BADGE_TAG_PATTERN.search(line)
        badge_img = METHOD_BADGE_IMG_PATTERN.search(line)
        method_bold = METHOD_BOLD_PATTERN.search(line)

        if badge:
            current_method = badge.group("method").upper()
        elif badge_img:
            current_method = badge_img.group("method").upper()
        elif method_bold:
            current_method = method_bold.group(1).upper()

        for m in API_URL_PATTERN.finditer(line):
            raw_path = m.group("path")
            raw_path = raw_path.split("/", 1)[1] if "/" in raw_path else raw_path
            path = normalize_path(raw_path)
            if path_prefix and not path.startswith(path_prefix):
                path = f"{path_prefix}/{path}".lstrip("/")
            if current_method not in ALLOWED_METHODS:
                continue
            results.append(
                {
                    "url": m.group(0),
                    "version": m.group("version"),
                    "path": path,
                    "method": current_method or "UNKNOWN",
                }
            )

        for pm in PATH_INLINE_PATTERN.finditer(line):
            raw_path = pm.group(1)
            start, end = pm.span(1)
            if (start > 0 and line[start - 1] == "<") or (end < len(line) and line[end] == ">"):
                continue
            if raw_path.lower().startswith("http"):
                continue
            if raw_path.lower().startswith(("/callout", "/htmlblock", "/table", "/request")):
                continue
            path = normalize_path(raw_path)
            if path_prefix and not path.startswith(path_prefix):
                path = f"{path_prefix}/{path}".lstrip("/")
            if not current_method:
                token_method = re.search(r"\b(GET|POST|PUT|PATCH|DELETE)\b", line, re.IGNORECASE)
                if token_method:
                    inferred = token_method.group(1).upper()
                else:
                    inferred = "UNKNOWN"
            else:
                inferred = current_method
            if inferred not in ALLOWED_METHODS:
                continue
            results.append(
                {
                    "url": raw_path,
                    "version": "",
                    "path": path,
                    "method": inferred,
                }
            )

    return results


def fetch_openapi_spec(oas_url: str) -> Dict:
    resp = requests.get(oas_url, timeout=30)
    resp.raise_for_status()
    raw = resp.json()
    return raw.get("data", raw)


def extract_ops_from_openapi(spec: Dict) -> Set[Tuple[str, str]]:
    paths = spec.get("paths", {}) or {}
    ops_out: Set[Tuple[str, str]] = set()
    for raw_path, ops in paths.items():
        sub = raw_path.lstrip("/")
        m = re.match(r"^\d{4}-\d{2}/(.+)$", sub)
        if m:
            sub = m.group(1)
        sub = normalize_path(sub)

        if not isinstance(ops, dict):
            continue
        for method_name in ops:
            if method_name.upper() in ALLOWED_METHODS:
                ops_out.add((method_name.upper(), sub))

    return ops_out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", default=None, help="Write coverage data to JSON")
    args = parser.parse_args()

    print("\n📘 Coverage Checker — OAS vs Guides\n")

    payload: Dict[str, object] = {"projects": {}}

    for name, cfg in PROJECTS.items():
        token = cfg.get("token", "")
        branch = cfg.get("branch", "")
        label = cfg.get("label") or name
        oas_url = cfg.get("oas_url")
        categories = cfg.get("guide_categories") or []
        path_prefix = cfg.get("path_prefix") or ""

        print(f"\n🔍 Project: {label}  (branch: {branch})")

        if not token:
            print("   ❌ Missing token, skipping.")
            payload["projects"][name] = {"label": label, "error": "missing token"}
            continue

        try:
            filtered_pages = get_filtered_guide_pages(token, branch, categories)
            print(f"   • Pages in categories {categories or ['all guides']}: {len(filtered_pages)}")

            doc_ops: Set[Tuple[str, str]] = set()
            for p in filtered_pages:
                slug = p.get("slug")
                if not slug:
                    continue
                page = get_guide_page_content(token, branch, slug)
                calls = extract_calls_with_methods(page["body"], path_prefix=path_prefix)
                for c in calls:
                    doc_ops.add((c["method"], c["path"]))

            print(f"   ✓ Extracted {len(doc_ops)} unique (METHOD, PATH) operations from guides")

            spec = fetch_openapi_spec(oas_url)
            oas_ops = extract_ops_from_openapi(spec)

            oas_paths = {p for (_, p) in oas_ops}
            doc_paths = {p for (_, p) in doc_ops}

            missing_ops = sorted(oas_ops - doc_ops)
            extra_ops = sorted(doc_ops - oas_ops)
            missing_paths = sorted(oas_paths - doc_paths)
            extra_paths = sorted(doc_paths - oas_paths)

            coverage_pct = round((1 - len(missing_ops) / len(oas_ops)) * 100, 2) if oas_ops else 0.0
            coverage_paths_pct = round((1 - len(missing_paths) / len(oas_paths)) * 100, 2) if oas_paths else 0.0

            payload["projects"][name] = {
                "label": label,
                "branch": branch,
                "oas_operations": len(oas_ops),
                "doc_operations": len(doc_ops),
                "coverage_pct": coverage_pct,
                "oas_paths": len(oas_paths),
                "doc_paths": len(doc_paths),
                "coverage_paths_pct": coverage_paths_pct,
                "missing_count": len(missing_ops),
                "missing": missing_ops,
                "extra_count": len(extra_ops),
                "extra": extra_ops,
                "missing_paths_count": len(missing_paths),
                "missing_paths": missing_paths,
                "extra_paths_count": len(extra_paths),
                "extra_paths": extra_paths,
            }

            print(f"   • OAS ops: {len(oas_ops)} | Guides ops: {len(doc_ops)} | Coverage: {coverage_pct}%")
        except Exception as exc:
            print(f"   ❌ Error: {exc}")
            payload["projects"][name] = {"label": label, "branch": branch, "error": str(exc)}

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"\n💾 Wrote coverage to {args.json_out}")


if __name__ == "__main__":
    main()
