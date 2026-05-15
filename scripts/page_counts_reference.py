#!/usr/bin/env python3
"""
ReadMe Page Counter — API reference only (live endpoints)

Counts only reference pages for configured projects/branches.
Requires ReadMe API tokens (Bearer) for each project.
"""

import argparse
import json
import os
from typing import Dict, Any
from urllib.parse import quote

import requests

BASE_URL = "https://api.readme.com/v2"

# -------------------------------------------------------------
# Configure your projects + branches here
# (replace "API TOKEN" with your real project tokens)
# -------------------------------------------------------------
PROJECTS = {
    "retail-media-stable": {
        "token_env": "README_TOKEN_RETAIL_MEDIA_STABLE",
        "branch": "v2026.01",
        "label": "Retail Media API (stable)",
    },
    "retail-media-preview": {
        "token_env": "README_TOKEN_RETAIL_MEDIA_PREVIEW",
        "branch": "v2026-preview",
        "label": "Retail Media API (preview)",
    },
    "retailer-integration-stable": {
        "token_env": "README_TOKEN_RETAILER_INTEGRATION",
        "branch": "v2025.10",
        "label": "Retailer Integration (stable)",
    },
    "retailer-integration-preview": {
        "token_env": "README_TOKEN_RETAILER_INTEGRATION",
        "branch": "v2026.01",
        "label": "Retailer Integration (preview)",
    },
    "marketing-solutions": {
        "token_env": "README_TOKEN_MARKETING_SOLUTIONS_STABLE",
        "branch": "v2026.01",
        "label": "Marketing Solutions (stable)",
    },
    "marketing-solutions-preview": {
        "token_env": "README_TOKEN_MARKETING_SOLUTIONS_PREVIEW",
        "branch": "v2026-preview",
        "label": "Marketing Solutions (preview)",
    },
}


def get_categories(token: str, branch: str, section: str):
    url = f"{BASE_URL}/branches/{branch}/categories/{section}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [c.get("title") for c in data.get("data", []) if c.get("title")]


def get_pages_in_category(token: str, branch: str, section: str, title: str) -> int:
    headers = {"Authorization": f"Bearer {token}"}
    title_enc = quote(title, safe="")
    url = f"{BASE_URL}/branches/{branch}/categories/{section}/{title_enc}/pages"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return len(data.get("data", []))


def count_reference_pages(token: str, branch: str):
    total_reference = 0
    for section in ("reference",):
        categories = get_categories(token, branch, section)
        for cat_title in categories:
            total_reference += get_pages_in_category(token, branch, section, cat_title)
    return {"reference": total_reference, "total": total_reference}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", default=None, help="Write totals as JSON to this file")
    args = parser.parse_args()

    print("\n📘 ReadMe Page Counter — API reference only\n")
    grand_total = 0
    payload: Dict[str, Any] = {"projects": {}, "grand_total": 0}

    for name, cfg in PROJECTS.items():
        token = cfg.get("token") or os.getenv(cfg.get("token_env", ""), "")
        branch = cfg["branch"]
        label = cfg.get("label") or name
        print(f"🔍 {label} (branch: {branch})")

        if not token or "API TOKEN" in token:
            print("   ❌ Missing token\n")
            payload["projects"][name] = {
                "branch": branch,
                "label": label,
                "error": "missing token",
            }
            continue

        try:
            counts = count_reference_pages(token, branch)
            print(
                f"   • Reference: {counts['reference']}\n"
                f"   → TOTAL:     {counts['total']}\n"
            )
            grand_total += counts["total"]
            payload["projects"][name] = {
                "branch": branch,
                "label": label,
                **counts,
            }
        except Exception as e:
            print(f"   ❌ Error: {e}\n")
            payload["projects"][name] = {
                "branch": branch,
                "label": label,
                "error": str(e),
            }

    payload["grand_total"] = grand_total
    print(f"📊 TOTAL across all projects (reference only): {grand_total} pages\n")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"💾 Wrote JSON metric to {args.json_out}")


if __name__ == "__main__":
    main()
