"""Fixture Ad Library: reads fixtures/ad_library/<brand-slug>.json; images are placeholder PNGs.

The files imitate the scrapecreators response, so they go through the live backend's shape functions
(`page_rows`, `normalise` in adapters/inspo/scrapecreators.py): one place to fix when the real shape lands.

Failure injection for FR-8 tests: `INSPO_FIXTURE_FAIL=<brand-slug>[,<brand-slug>...]` makes `fetch_ads`
raise for those brands on every attempt (so a retry fails too); `fetch_ads_calls` counts attempts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from adapters.image.placeholder import render_placeholder
from adapters.inspo import brand_slug
from adapters.inspo.scrapecreators import normalise, page_rows


class FixtureAdLibrary:
    def __init__(self, fixture_dir: Path):
        self.fixture_dir = fixture_dir
        self.fail_brands = {b for b in (os.environ.get("INSPO_FIXTURE_FAIL") or "").split(",") if b}
        self.fetch_ads_calls: dict[str, int] = {}

    def fetch_ads(self, brand: str, limit: int = 50, *, page: str | None = None) -> list[dict[str, Any]]:
        slug = brand_slug(brand)
        self.fetch_ads_calls[slug] = self.fetch_ads_calls.get(slug, 0) + 1
        if slug in self.fail_brands:
            raise ConnectionError(f"INSPO_FIXTURE_FAIL: simulated source failure for {brand!r}")
        path = self.fixture_dir / f"{slug}.json"
        if not path.exists():
            raise FileNotFoundError(f"no ad_library fixture for {brand!r}: expected {path}")
        payload = json.loads(path.read_text())
        return [normalise(row, brand, source="fixture") for row in page_rows(payload)[:limit]]

    def fetch_image(self, url: str) -> bytes:
        if not url.startswith("fixture://"):
            raise ValueError(f"fixture ad library does not fetch the network: {url}")
        return render_placeholder(url, size=(600, 600))
