#!/usr/bin/env python3
"""
ReadMe Top Search Terms — last 30 days (per project)

Fetches top search terms for each project.
Uses Basic auth with the project API key as the username and a blank password.
"""

import argparse
import base64
import json
import os
from typing import Any, Dict, List

import requests

SEARCH_URL = "https://metrics.readme.io/v2/search/top-search-terms"
DEFAULT_LIMIT = 10
DEFAULT_RANGE_LENGTH = 90

# Configure your projects here (token + label)
PROJECTS = {
    "retail-media": {
        "token": os.getenv("README_TOKEN_RETAIL_MEDIA_STABLE", ""),
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


def _basic_auth_header(token: str) -> str:
    # Basic Auth: username = token, password = blank
    basic = base64.b64encode(f"{token}:".encode("utf-8")).decode("utf-8")
    return f"Basic {basic}"


def _extract_items(data: Any) -> List[Dict[str, Any]]:
    """
    Observed response shape from this endpoint is typically:

      {
        "search": [
          { "searchTerm": "creative", "count": 14 },
          ...
        ]
      }

    Some older/docs UIs show nested shapes; keep a couple fallbacks just in case.
    """
    if not isinstance(data, dict):
        return []

    v = data.get("search")
    if isinstance(v, list):
        return v

    if isinstance(v, dict):
        breakdown = v.get("breakdown")
        if isinstance(breakdown, list):
            return breakdown

    for key in ("breakdown", "terms", "items", "data"):
        v2 = data.get(key)
        if isinstance(v2, list):
            return v2

    return []


def fetch_terms(token: str, limit: int, range_length: int) -> List[Dict[str, Any]]:
    headers = {
        "Authorization": _basic_auth_header(token),
        "Accept": "application/json",
        "User-Agent": "search-terms-script",
    }

    # NOTE: do NOT send `project` — the API key scopes the project already.
    params = {
        "rangeLength": range_length,
        "limit": limit,
    }

    resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    items = _extract_items(data)

    banned = {
        "e",
        "can i ask you a question please?is it ok if i upload an image?",
    }

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        term = (
            item.get("searchTerm")
            or item.get("term")
            or item.get("query")
            or item.get("search")
            or ""
        )
        count = (
            item.get("count")
            or item.get("total")
            or item.get("searches")
            or item.get("value")
            or 0
        )

        if not term:
            continue

        try:
            count_int = int(count)
        except Exception:
            count_int = 0

        results.append({"term": term, "count": count_int})

    filtered = [
        r for r in results
        if r["term"].lower().strip() not in banned
        and "can i ask you a question please?is it ok if i upload an image?" not in r["term"].lower()
    ]

    return filtered[:limit]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--range-length", type=int, default=DEFAULT_RANGE_LENGTH)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--merge", action="store_true", help="Merge all projects into a single top list")
    args = parser.parse_args()

    payload: Dict[str, Any] = {
        "projects": {},
        "limit": args.limit,
        "rangeLength": args.range_length,
    }
    merged: Dict[str, Any] = {}

    for slug, cfg in PROJECTS.items():
        token = (cfg.get("token") or "").strip()
        label = cfg.get("label") or slug

        print(f"🔍 {label} (top {args.limit} search terms, last {args.range_length} days)")

        if not token:
            print("   ❌ Missing token\n")
            payload["projects"][slug] = {"label": label, "error": "missing token"}
            continue

        try:
            terms = fetch_terms(token, args.limit, args.range_length)
            payload["projects"][slug] = {"label": label, "items": terms}

            if not terms:
                print("   (no results)\n")
                continue

            for i, t in enumerate(terms, 1):
                print(f"   {i:>2}. {t['term']} — {t['count']} searches")
            print()

            if args.merge:
                for t in terms:
                    term_key = t["term"]
                    merged[term_key] = merged.get(term_key, 0) + int(t["count"])

        except requests.HTTPError as exc:
            body = ""
            try:
                body = (exc.response.text or "")[:1000]
            except Exception:
                pass
            print(f"   ❌ HTTP Error: {exc}\n   Body: {body}\n")
            payload["projects"][slug] = {"label": label, "error": str(exc), "body": body}

        except Exception as exc:
            print(f"   ❌ Error: {exc}\n")
            payload["projects"][slug] = {"label": label, "error": str(exc)}

    if args.merge:
        merged_items = sorted(
            [{"term": k, "count": v} for k, v in merged.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[: args.limit]
        payload["merged"] = {"label": "All projects", "items": merged_items}

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"💾 Wrote JSON metric to {args.json_out}")


if __name__ == "__main__":
    main()
