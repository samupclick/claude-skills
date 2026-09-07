#!/usr/bin/env python3
"""Regenerate the assumed-shape Ad Library fixtures. Deterministic; run from anywhere."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BRANDS = ["AG1", "Liquid Death", "HexClad", "Ridge", "Dr. Squatch"]
FORMATS = ["IMAGE", "IMAGE", "VIDEO", "CAROUSEL", "IMAGE", "IMAGE"]
ANCHOR = datetime(2026, 9, 1, tzinfo=timezone.utc)
HERE = Path(__file__).resolve().parent


def slug(brand: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")


def ad(brand: str, n: int) -> dict:
    s = slug(brand)
    ad_id = f"fx-{s}-{n:03d}"
    start = ANCHOR - timedelta(days=[3, 12, 27, 45, 90, 200][n % 6])
    active = n % 3 != 2
    fmt = FORMATS[n % len(FORMATS)]
    images = [{"original_image_url": f"fixture://ad_library/{s}/{ad_id}-1.png",
               "resized_image_url": f"fixture://ad_library/{s}/{ad_id}-1-resized.png"}] if fmt != "VIDEO" else []
    cards = [{"title": f"FIXTURE card {i}", "original_image_url": f"fixture://ad_library/{s}/{ad_id}-card{i}.png"}
             for i in (1, 2, 3)] if fmt == "CAROUSEL" else []
    videos = [{"video_hd_url": f"fixture://ad_library/{s}/{ad_id}.mp4",
               "video_preview_image_url": f"fixture://ad_library/{s}/{ad_id}-poster.png"}] if fmt == "VIDEO" else []
    if fmt == "VIDEO":
        images = [{"original_image_url": f"fixture://ad_library/{s}/{ad_id}-poster.png"}]
    return {
        "ad_archive_id": ad_id,
        "page_name": brand,
        "page_id": f"fx-page-{s}",
        "start_date": int(start.timestamp()),
        "end_date": None if active else int((start + timedelta(days=14)).timestamp()),
        "is_active": active,
        "publisher_platform": ["facebook", "instagram"],
        "snapshot": {
            "body": {"text": f"FIXTURE ad body {n} for {brand}: synthetic text in an assumed shape, not a real ad."},
            "title": f"FIXTURE title {n} ({brand})",
            "link_url": f"https://example.invalid/{s}/fixture-{n}",
            "cta_text": ["Shop now", "Learn more", "Get offer"][n % 3],
            "display_format": fmt,
            "images": images,
            "videos": videos,
            "cards": cards,
        },
    }


def main() -> None:
    for brand in BRANDS:
        payload = {
            "_shape": "ASSUMED shape of a scrapecreators Meta Ad Library company-ads response; replace with a real "
                      "response (real-001.json, go-live step 4) and fix adapters/inspo/fixture.py::normalise if it differs",
            "brand": brand,
            "searchResults": [ad(brand, n) for n in range(1, 7)],
            "cursor": None,
        }
        (HERE / f"{slug(brand)}.json").write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
