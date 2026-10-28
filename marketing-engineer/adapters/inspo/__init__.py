"""Ad Library source (scrapecreators). INSPO_BACKEND=fixture|scrapecreators.

`fetch_ads(brand)` returns normalised ads: source, ad_id, brand, page_name, start_date (ISO), end_date,
is_active, body, title, link_url, cta, display_format, images (urls), videos, raw (the vendor row, kept
for re-normalisation). `fetch_image(url)` returns the snapshot bytes (PNG). The scrapecreators backend
(`SCRAPECREATORS_API_KEY`) also has `usage()`, the vendor calls made, which the intel worker writes to
`runs.counts.inspo_usage`. The vendor shape is an ASSUMPTION until one real response is saved (CRUCIBLE §4,
T13 step 4); the fixture backend and the live one share its shape functions in `scrapecreators.py`.
"""
from __future__ import annotations

import re
from typing import Any, Protocol

from adapters.env import ME_DIR, choose_backend

FIXTURE_DIR = ME_DIR / "fixtures" / "ad_library"


class AdLibrary(Protocol):
    def fetch_ads(self, brand: str, limit: int = 50) -> list[dict[str, Any]]: ...
    def fetch_image(self, url: str) -> bytes: ...


def brand_slug(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")


def get_inspo() -> AdLibrary:
    from adapters.inspo.fixture import FixtureAdLibrary
    from adapters.inspo.scrapecreators import ScrapeCreatorsAdLibrary

    return choose_backend("INSPO_BACKEND", {
        "fixture": lambda: FixtureAdLibrary(FIXTURE_DIR),
        "scrapecreators": ScrapeCreatorsAdLibrary.from_env,
    })
