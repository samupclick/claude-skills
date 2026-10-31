import json
from pathlib import Path

import pytest

from adapters.inspo import FIXTURE_DIR, get_inspo

BRANDS = ["AG1", "Liquid Death", "HexClad", "Ridge", "Dr. Squatch"]


@pytest.fixture
def inspo(monkeypatch):
    monkeypatch.setenv("INSPO_BACKEND", "fixture")
    return get_inspo()


def test_fixture_has_five_seed_brands_with_five_ads_each_normalised(inspo):
    for brand in BRANDS:
        ads = inspo.fetch_ads(brand)
        assert len(ads) >= 5, brand
        for ad in ads:
            assert ad["brand"] == brand
            assert ad["ad_id"] and ad["source"] == "fixture"
            assert len(ad["start_date"]) == 10 and ad["start_date"][4] == "-"
            assert isinstance(ad["is_active"], bool)
            assert ad["images"], "every ad needs a snapshot image"
            assert ad["raw"], "raw response kept for re-normalisation"


def test_fixture_files_declare_assumed_shape():
    files = sorted(FIXTURE_DIR.glob("*.json"))
    assert len(files) >= 5
    for f in files:
        assert "assumed" in json.loads(f.read_text())["_shape"].lower(), f
    assert "assum" in (FIXTURE_DIR / "README.md").read_text().lower()


def test_fetch_image_is_deterministic_bytes_for_fixture_urls(inspo):
    url = inspo.fetch_ads("Ridge")[0]["images"][0]
    assert url.startswith("fixture://")
    a, b = inspo.fetch_image(url), inspo.fetch_image(url)
    assert a == b and a[:8] == b"\x89PNG\r\n\x1a\n"


def test_unknown_brand_is_an_error_not_an_empty_list(inspo):
    with pytest.raises(FileNotFoundError, match="ad_library"):
        inspo.fetch_ads("Nobody Inc")
