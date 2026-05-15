#!/usr/bin/env python3
"""
ReadMe Top Pages — last year (per project)

Fetches top pages for each project over the last 365 days.
Requires a ReadMe API token per project (Basic auth).
"""

import argparse
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

import requests

TOP_URL = "https://metrics.readme.io/v2/pageview/top"
WINDOW_DAYS = 365
LIMIT = 10

# Configure your projects here (token + label)
PROJECTS = {
    "retail-media": {
        "token": os.getenv("README_TOKEN_RETAIL_MEDIA", ""),
        "label": "Retail Media API",
    },
    "retailer-integration": {
        "token": os.getenv("README_TOKEN_RETAILER_INTEGRATION", ""),
        "label": "Retailer Integration",
    },
    "marketing-solutions": {
        "token": os.getenv("README_TOKEN_MARKETING_SOLUTIONS_STABLE", ""),
        "label": "Marketing Solutions API",
    },
}


def date_range() -> (str, str):
    today = datetime.now(timezone.utc).date()
    start = today.replace(year=today.year - 1, month=1, day=1)
    end = today.replace(month=1, day=1)
    return start.isoformat(), end.isoformat()


def fetch_top(token: str, project: str, start: str, end: str, limit: int = LIMIT) -> List[Dict[str, Any]]:
    basic = base64.b64encode(f"{token}:".encode("utf-8")).decode("utf-8")
    headers = {"Authorization": f"Basic {basic}", "User-Agent": "top-pages-script"}
    params = {
        "rangeStart": start,
        "rangeEnd": end,
        "resolution": "day",
        "limit": limit,
    }
    resp = requests.get(TOP_URL, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Expecting {"topPageviews":[{path,count},...]} or {"items":[...]} or list fallback
    if isinstance(data, dict):
        items = data.get("topPageviews") or data.get("items") or data.get("data") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []

    results = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        views = item.get("count") or item.get("views") or item.get("total") or 0
        title = item.get("title") or item.get("name") or item.get("slug") or item.get("path") or "(untitled)"
        path = item.get("slug") or item.get("path") or ""
        results.append({"title": title, "views": int(views) if isinstance(views, (int, float)) else 0, "path": path})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", default=None, help="Write top pages as JSON to this file")
    args = parser.parse_args()

    start, end = date_range()
    payload: Dict[str, Any] = {"projects": {}, "range": {"start": start, "end": end, "days": WINDOW_DAYS}, "limit": LIMIT}

    for slug, cfg in PROJECTS.items():
        token = cfg.get("token", "")
        label = cfg.get("label") or slug
        print(f"🔍 {label} (top {LIMIT}, {start} → {end})")

        if not token or "API TOKEN" in token:
            print("   ❌ Missing token\n")
            payload["projects"][slug] = {"label": label, "error": "missing token"}
            continue

        try:
            items = fetch_top(token, slug, start, end, LIMIT)
            payload["projects"][slug] = {"label": label, "items": items}
            for i, it in enumerate(items, 1):
                print(f"   {i:>2}. {it['title']} — {it['views']} views")
            if not items:
                print("   (no results)")
            print()
        except Exception as exc:
            print(f"   ❌ Error: {exc}\n")
            payload["projects"][slug] = {"label": label, "error": str(exc)}

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"💾 Wrote JSON metric to {args.json_out}")


if __name__ == "__main__":
    main()
