#!/usr/bin/env python3
"""
ReadMe Page Views — total page views per project

Fetches total page views for multiple time windows (last 30/90/365 days).
Requires a ReadMe API token per project.
"""

import argparse
import json
import base64
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

import requests

METRICS_URL = "https://metrics.readme.io/v2/pageview/total"

# Configure your projects here (token + optional label)
PROJECTS = {
    "retail-media": {
        "token_env": "README_TOKEN_RETAIL_MEDIA",
        "label": "Retail Media API",
    },
    "retailer-integration": {
        "token_env": "README_TOKEN_RETAILER_INTEGRATION",
        "label": "Retailer Integration",
    },
    "marketing-solutions": {
        "token_env": "README_TOKEN_MARKETING_SOLUTIONS_STABLE",
        "label": "Marketing Solutions API",
        "group": "marketing-solutions",
    },
    "marketing-solutions-preview": {
        "token_env": "README_TOKEN_MARKETING_SOLUTIONS_PREVIEW",
        "label": "Marketing Solutions API",
        "group": "marketing-solutions",  # collapse preview + stable into one display entry
    },
}

WINDOWS = [30, 90, 365]


def range_start(days: int) -> str:
    dt = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    return dt.isoformat()


def fetch_views(token: str, project: str, start_iso: str, end_iso: str) -> int:
    basic = base64.b64encode(f"{token}:".encode("utf-8")).decode("utf-8")
    headers = {
        "Authorization": f"Basic {basic}",
        "User-Agent": "page-views-script",
    }
    params = {
        "project": project,
        "resolution": "day",
        "rangeStart": start_iso,
        "rangeEnd": end_iso,
    }
    url = METRICS_URL
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # API returns {"total": number}
    if isinstance(data, dict) and isinstance(data.get("total"), (int, float)):
        return int(data["total"])
    if isinstance(data, (int, float)):
        return int(data)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", default=None, help="Write page views as JSON to this file")
    args = parser.parse_args()

    payload: Dict[str, Any] = {"projects": {}, "windows": WINDOWS, "totals": {w: 0 for w in WINDOWS}}

    for slug, cfg in PROJECTS.items():
        token = cfg.get("token") or os.getenv(cfg.get("token_env", ""), "")
        group = cfg.get("group") or slug
        label = cfg.get("label") or group

        # If we've already successfully captured this grouped project, skip extra duplicates
        if group in payload["projects"] and "views" in payload["projects"][group]:
            continue

        print(f"🔍 {label}")

        if not token or "API TOKEN" in token:
            print("   ❌ Missing token\n")
            if group not in payload["projects"]:
                payload["projects"][group] = {"label": label, "error": "missing token"}
            continue

        result: Dict[str, Any] = {"label": label, "views": {}}

        try:
            for days in WINDOWS:
                start = range_start(days)
                end = datetime.now(timezone.utc).date().isoformat()
                total = fetch_views(token, slug, start, end)
                result["views"][days] = total
                payload["totals"][days] = payload["totals"].get(days, 0) + total
                print(f"   • Last {days} days: {total}")
            print()
            payload["projects"][group] = result
        except Exception as exc:
            print(f"   ❌ Error: {exc}\n")
            if group not in payload["projects"]:
                payload["projects"][group] = {"label": label, "error": str(exc)}

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"💾 Wrote JSON metric to {args.json_out}")


if __name__ == "__main__":
    main()
