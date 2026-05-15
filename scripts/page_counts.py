#!/usr/bin/env python3
"""
ReadMe Page Counter — API v2 (real endpoints only)

Counts live pages (guides + reference + custom_pages) for configured projects/branches.
Requires ReadMe API tokens (Bearer) for each project.
"""

import argparse
import json
import os
from typing import Dict, Any

import requests
from urllib.parse import quote

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
    "cms-stable": {
        "token_env": "README_TOKEN_CMS_STABLE",
        "branch": "v2025.10",
        "label": "Retailer Integration (stable)",
    },
    "cms-preview": {
        "token_env": "README_TOKEN_CMS_PREVIEW",
        "branch": "v2026.01",
        "label": "Retailer Integration (preview)",
    },
    "retail-media-delivery": {
        "token_env": "README_TOKEN_RETAIL_MEDIA_DELIVERY",
        "branch": "v2026.01",
        "label": "Retail Media Delivery",
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


def get_pages_in_category(token: str, branch: str, section: str, title: str) -> Dict[str, int]:
    headers = {"Authorization": f"Bearer {token}"}
    title_enc = quote(title, safe="")
    url = f"{BASE_URL}/branches/{branch}/categories/{section}/{title_enc}/pages"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    pages = data.get("data", [])
    total = len(pages)
    hidden = 0
    if isinstance(pages, list):
        hidden = sum(1 for p in pages if isinstance(p, dict) and p.get("hidden") is True)
    return {"total": total, "hidden": hidden}


def count_custom_pages(token: str, branch: str) -> Dict[str, int]:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/branches/{branch}/custom_pages"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    hidden = 0
    if isinstance(data, dict):
        if "items" in data:
            items = data["items"]
            if isinstance(items, list):
                hidden = sum(1 for p in items if isinstance(p, dict) and p.get("hidden") is True)
                return {"total": len(items), "hidden": hidden}
            return {"total": 0, "hidden": 0}
        if "data" in data:
            items = data["data"]
            if isinstance(items, list):
                hidden = sum(1 for p in items if isinstance(p, dict) and p.get("hidden") is True)
                return {"total": len(items), "hidden": hidden}
            return {"total": 0, "hidden": 0}
    elif isinstance(data, list):
        hidden = sum(1 for p in data if isinstance(p, dict) and p.get("hidden") is True)
        return {"total": len(data), "hidden": hidden}
    return {"total": 0, "hidden": 0}


def count_all_pages_for_branch(token: str, branch: str):
    total_guides = total_reference = hidden_guides = hidden_reference = 0
    for section in ("guides", "reference"):
        categories = get_categories(token, branch, section)
        for cat_title in categories:
            count = get_pages_in_category(token, branch, section, cat_title)
            if section == "guides":
                total_guides += count["total"]
                hidden_guides += count["hidden"]
            else:
                total_reference += count["total"]
                hidden_reference += count["hidden"]
    custom = count_custom_pages(token, branch)
    hidden_custom = custom["hidden"]
    return {
        "guides": total_guides,
        "reference": total_reference,
        "custom": custom["total"],
        "hidden": hidden_guides + hidden_reference + hidden_custom,
        "hidden_guides": hidden_guides,
        "hidden_reference": hidden_reference,
        "hidden_custom": hidden_custom,
        "total": total_guides + total_reference + custom["total"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", default=None, help="Write totals as JSON to this file")
    args = parser.parse_args()

    print("\n📘 ReadMe Page Counter — API v2 (real endpoints only)\n")
    grand_total = 0
    payload: Dict[str, Any] = {"projects": {}, "grand_total": 0}

    for name, cfg in PROJECTS.items():
        token = cfg.get("token") or os.getenv(cfg.get("token_env", ""), "")
        branch = cfg["branch"]
        print(f"🔍 {name} (branch: {branch})")

        if not token or "API TOKEN" in token:
            print("   ❌ Missing token\n")
            payload["projects"][name] = {
                "branch": branch,
                "label": cfg.get("label") or name,
                "error": "missing token",
            }
            continue

        try:
            counts = count_all_pages_for_branch(token, branch)
            print(
                f"   • Guides:    {counts['guides']}\n"
                f"   • Reference: {counts['reference']}\n"
                f"   • Custom:    {counts['custom']}\n"
                f"   • Hidden:    {counts['hidden']}\n"
                f"   → TOTAL:     {counts['total']}\n"
            )
            grand_total += counts["total"]
            payload["projects"][name] = {
                "branch": branch,
                "label": cfg.get("label") or name,
                **counts,
            }
        except Exception as e:
            print(f"   ❌ Error: {e}\n")
            payload["projects"][name] = {
                "branch": branch,
                "label": cfg.get("label") or name,
                "error": str(e),
            }

    payload["grand_total"] = grand_total
    print(f"📊 TOTAL across all projects: {grand_total} pages\n")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"💾 Wrote JSON metric to {args.json_out}")


if __name__ == "__main__":
    main()
