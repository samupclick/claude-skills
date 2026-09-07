"""Fixture Ad Library: reads fixtures/ad_library/<brand-slug>.json; images are placeholder PNGs.

Failure injection for FR-8 tests: `INSPO_FIXTURE_FAIL=<brand-slug>[,<brand-slug>...]` makes `fetch_ads`
raise for those brands on every attempt (so a retry fails too); `fetch_ads_calls` counts attempts.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adapters.image.placeholder import render_placeholder
from adapters.inspo import brand_slug


class FixtureAdLibrary:
    def __init__(self, fixture_dir: Path):
        self.fixture_dir = fixture_dir
        self.fail_brands = {b for b in (os.environ.get("INSPO_FIXTURE_FAIL") or "").split(",") if b}
        self.fetch_ads_calls: dict[str, int] = {}

    def fetch_ads(self, brand: str, limit: int = 50) -> list[dict[str, Any]]:
        slug = brand_slug(brand)
        self.fetch_ads_calls[slug] = self.fetch_ads_calls.get(slug, 0) + 1
        if slug in self.fail_brands:
            raise ConnectionError(f"INSPO_FIXTURE_FAIL: simulated source failure for {brand!r}")
        path = self.fixture_dir / f"{slug}.json"
        if not path.exists():
            raise FileNotFoundError(f"no ad_library fixture for {brand!r}: expected {path}")
        payload = json.loads(path.read_text())
        return [normalise(row, brand) for row in payload.get("searchResults", [])[:limit]]

    def fetch_image(self, url: str) -> bytes:
        if not url.startswith("fixture://"):
            raise ValueError(f"fixture ad library does not fetch the network: {url}")
        return render_placeholder(url, size=(600, 600))


def normalise(row: dict[str, Any], brand: str) -> dict[str, Any]:
    """Assumed scrapecreators shape -> our ad dict. Adjust here (only here) when the real shape differs."""
    snap = row.get("snapshot") or {}
    body = snap.get("body")
    images = [i.get("original_image_url") or i.get("resized_image_url") for i in snap.get("images") or []]
    images += [c.get("original_image_url") for c in snap.get("cards") or [] if c.get("original_image_url")]
    return {
        "source": "fixture",
        "ad_id": str(row.get("ad_archive_id")),
        "brand": brand,
        "page_name": row.get("page_name"),
        "start_date": _iso_date(row.get("start_date")),
        "end_date": _iso_date(row.get("end_date")),
        "is_active": bool(row.get("is_active")),
        "body": body.get("text") if isinstance(body, dict) else body,
        "title": snap.get("title"),
        "link_url": snap.get("link_url"),
        "cta": snap.get("cta_text"),
        "display_format": snap.get("display_format"),
        "images": [u for u in images if u],
        "videos": [v.get("video_hd_url") or v.get("video_sd_url") for v in snap.get("videos") or []],
        "raw": row,
    }


def _iso_date(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
    return str(value)[:10]
