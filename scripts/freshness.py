#!/usr/bin/env python3
"""
ReadMe — OAS Freshness (last update per project)

Checks how long ago the OpenAPI definition was last updated
for each configured project.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://api.readme.com/v2"

PROJECTS = [
    {
        "slug": "retail-media-stable",
        "name": "Retail Media (stable)",
        "label": "Retail Media API (stable)",
        "token_env": "README_TOKEN_RETAIL_MEDIA",
        "branch": "v2026.01",
    },
    {
        "slug": "retail-media-preview",
        "name": "Retail Media (preview)",
        "label": "Retail Media API (preview)",
        "token_env": "README_TOKEN_RETAIL_MEDIA_PREVIEW",
        "branch": "v2026-preview",
    },
    {
        "slug": "marketing-solutions-stable",
        "name": "Marketing Solutions (stable)",
        "label": "Marketing Solutions API (stable)",
        "token_env": "README_TOKEN_MARKETING_SOLUTIONS_STABLE",
        "branch": "v2026.01",
    },
    {
        "slug": "marketing-solutions-preview",
        "name": "Marketing Solutions (preview)",
        "label": "Marketing Solutions API (preview)",
        "token_env": "README_TOKEN_MARKETING_SOLUTIONS_PREVIEW",
        "branch": "v2026-preview",
    },
]


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def request_json(url: str, token: str) -> Any:
    headers = {"Authorization": f"Bearer {token.strip()}"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code >= 400:
        print(f"HTTP {resp.status_code} → {resp.url}")
        print(resp.text[:2000])
        resp.raise_for_status()
    return resp.json()


def normalize_items(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict):
        items = data.get("data") or data.get("items") or []
        return items if isinstance(items, list) else []
    return data if isinstance(data, list) else []


def check_project(slug: str, project: Dict[str, str], now: datetime) -> Dict[str, Any]:
    name = project["name"]
    label = project.get("label", name)
    token = os.getenv(project["token_env"], "")

    if not token:
        print(f"  ⚠️  No token for {name} ({project['token_env']} not set) — skipping.")
        return {"label": label, "error": "missing token"}

    branch = project["branch"]
    url = f"{BASE_URL}/branches/{branch}/apis"
    data = request_json(url, token)
    items = normalize_items(data)

    enriched = []
    for it in items:
        updated = parse_dt(
            it.get("updated_at") or it.get("updatedAt")
            or it.get("last_updated") or it.get("lastUpdated")
        )
        enriched.append((updated, it))

    enriched.sort(
        key=lambda t: (t[0] is None, t[0] or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )

    if not enriched:
        return {"label": label, "branch": branch, "error": "no API definitions found"}

    newest_dt, _ = enriched[0]
    return {
        "label": label,
        "branch": branch,
        "last_updated": newest_dt.isoformat() if newest_dt else None,
        "days_since": (now - newest_dt).days if newest_dt else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", dest="json_out", default=None)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    projects_out: Dict[str, Any] = {}

    for project in PROJECTS:
        slug = project["slug"]
        print(f"\n🔍 Checking {project['name']}…")
        result = check_project(slug, project, now)
        projects_out[slug] = result

        if "error" not in result:
            print(f"   Last updated: {result['last_updated']}")
            print(f"   Days since  : {result['days_since']}")

    output = {"generated_at": now.isoformat(), "projects": projects_out}

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        print(f"\n💾 Wrote JSON to {args.json_out}")


if __name__ == "__main__":
    main()
