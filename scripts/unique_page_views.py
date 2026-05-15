#!/usr/bin/env python3
"""
ReadMe Unique Page Views — long-range (default: 720 days)

Fetches total unique page views for configured projects using the Metrics API.
Requires a ReadMe API token per project (Basic auth).
"""

import argparse
import base64
import json
import os
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Tuple

import requests

UNIQUE_URL = "https://metrics.readme.io/v2/pageview/unique"
DEFAULT_RANGE_LENGTH = 720
DEFAULT_RESOLUTION = "month"

# Configure your projects here (token + optional label)
PROJECTS = {
    "retail-media": {
        "token_env": "README_TOKEN_RETAIL_MEDIA_STABLE",
        "label": "Retail Media API",
        "group": "retail-media",
    },
    "retail-media-preview": {
        "token_env": "README_TOKEN_RETAIL_MEDIA_PREVIEW",
        "label": "Retail Media API (preview)",
        "group": "retail-media",
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
        "label": "Marketing Solutions API (preview)",
        "group": "marketing-solutions",
    },
}


def _basic_auth(token: str) -> str:
    basic = base64.b64encode(f"{token}:".encode("utf-8")).decode("utf-8")
    return f"Basic {basic}"


def _extract_total(payload: Any) -> int:
    if isinstance(payload, (int, float)):
        return int(payload)
    if isinstance(payload, dict):
        for key in ("unique", "total", "count", "pageviews", "pageViews"):
            if key in payload and isinstance(payload[key], (int, float)):
                return int(payload[key])
    return 0


def fetch_unique_views(token: str, project: str, range_length: int = None, resolution: str = DEFAULT_RESOLUTION, start: str = None, end: str = None) -> int:
    headers = {
        "Authorization": _basic_auth(token),
        "Accept": "application/json",
        "User-Agent": "unique-page-views-script",
    }
    params = {
        "project": project,
        "rangeLength": range_length,
        "resolution": resolution,
    }
    if start:
        params["rangeStart"] = start
    if end:
        params["rangeEnd"] = end
    resp = requests.get(UNIQUE_URL, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return _extract_total(data)


def _month_starts(days: int) -> List[date]:
    today = datetime.now(timezone.utc).date()
    start_cutoff = today - timedelta(days=days)
    current = today.replace(day=1)
    months: List[date] = []
    while current >= start_cutoff:
        months.append(current)
        prev_month = (current.replace(day=1) - timedelta(days=1)).replace(day=1)
        current = prev_month
    months.reverse()
    return months


def _month_end(start: date, today: date) -> date:
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    end = next_month - timedelta(days=1)
    return min(end, today)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--range-length",
        type=int,
        default=DEFAULT_RANGE_LENGTH,
        help="Number of days to include (default 720, max 720)",
    )
    parser.add_argument(
        "--resolution",
        default=DEFAULT_RESOLUTION,
        help="Resolution bucket (hour|day|week|month|year)",
    )
    parser.add_argument("--json-out", default=None, help="Write unique page views as JSON to this file")
    args = parser.parse_args()

    range_length = max(1, min(args.range_length, DEFAULT_RANGE_LENGTH))

    today = datetime.now(timezone.utc).date()
    month_starts = _month_starts(range_length)
    payload: Dict[str, Any] = {
        "projects": {},
        "rangeLength": range_length,
        "resolution": "month",
        "months": [m.isoformat() for m in month_starts],
        "totals_by_month": {},
        "total": 0,
    }
    for m in month_starts:
        payload["totals_by_month"][m.isoformat()] = 0

    for slug, cfg in PROJECTS.items():
        token = cfg.get("token") or os.getenv(cfg.get("token_env", ""), "")
        group = cfg.get("group") or slug
        label = cfg.get("label") or group

        print(f"🔍 {label} (last {range_length} days)")

        if not token or "API TOKEN" in token:
            print("   ❌ Missing token\n")
            payload["projects"][group] = {"label": label, "error": "missing token"}
            continue

        try:
            buckets: List[Dict[str, Any]] = []
            for start in month_starts:
                end = _month_end(start, today)
                total_for_month = fetch_unique_views(
                    token,
                    slug,
                    range_length=None,
                    resolution="day",
                    start=start.isoformat(),
                    end=end.isoformat(),
                )
                buckets.append({"date": start.isoformat(), "value": total_for_month})
                payload["totals_by_month"][start.isoformat()] += total_for_month

            total = sum(b["value"] for b in buckets)
            existing = payload["projects"].get(group)
            if existing and isinstance(existing, dict):
                # Merge preview into stable if both share the same group
                existing_total = existing.get("total", 0)
                existing_buckets = existing.get("buckets") or []
                merged_buckets = []
                bucket_map = {}
                for b in existing_buckets + buckets:
                    date_key = b.get("date")
                    if not date_key:
                        continue
                    bucket_map.setdefault(date_key, 0)
                    bucket_map[date_key] += b.get("value", 0)
                merged_buckets = [{"date": k, "value": v} for k, v in bucket_map.items()]
                merged_buckets.sort(key=lambda b: b["date"])
                total = existing_total + total
                buckets = merged_buckets
            payload["projects"][group] = {"label": label if not existing else existing.get("label", label), "buckets": buckets, "total": total}
            payload["total"] += total
            print(f"   • Unique views (sum): {total}\n")
        except requests.HTTPError as exc:
            body = ""
            try:
                body = (exc.response.text or "")[:1000]
            except Exception:
                pass
            print(f"   ❌ HTTP Error: {exc}\n   Body: {body}\n")
            payload["projects"][group] = {"label": label, "error": str(exc), "body": body}
        except Exception as exc:
            print(f"   ❌ Error: {exc}\n")
            payload["projects"][group] = {"label": label, "error": str(exc)}

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"💾 Wrote JSON metric to {args.json_out}")


if __name__ == "__main__":
    main()
