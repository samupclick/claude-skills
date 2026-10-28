"""INSPO_BACKEND=scrapecreators (FR-4, FR-5, FR-8; CRUCIBLE A19): contract tests on httpx.MockTransport against
fixtures/scrapecreators/ (ASSUMED SHAPE until go-live step 4). Never the network, never a real key; the end-to-end
test runs the intel worker's pull against the throwaway warehouse with this backend plugged in."""
from __future__ import annotations

import importlib.util
import io
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import httpx
import psycopg
import pytest
from PIL import Image
from psycopg.rows import dict_row

from adapters.env import ME_DIR, MissingEnvVar
from adapters.inspo import FIXTURE_DIR, get_inspo
from adapters.inspo.fixture import FixtureAdLibrary
from adapters.inspo.scrapecreators import IMAGE_HOSTS, ScrapeCreatorsAdLibrary, ScrapeCreatorsError, normalise

FIX = ME_DIR / "fixtures" / "scrapecreators"
KEY = "sc-test-key-not-real"
AD_KEYS = {"source", "ad_id", "brand", "page_name", "start_date", "end_date", "is_active", "body", "title", "link_url",
           "cta", "display_format", "images", "videos", "raw"}


def exchange(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text())


def respond(name: str) -> httpx.Response:
    ex = exchange(name)
    return httpx.Response(ex["status"], json=ex["body"], headers=ex.get("headers"))


def jpeg(size=(64, 48), colour=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="JPEG")
    return buf.getvalue()


class Vendor:
    """The scrapecreators API and the Facebook CDN as fixtures; every request is recorded."""

    def __init__(self, **overrides):
        self.requests: list[httpx.Request] = []
        self.overrides = overrides

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path, params = request.url.path, request.url.params
        if path in self.overrides:
            out = self.overrides[path]
            return out(request) if callable(out) else out
        if request.url.host == "api.scrapecreators.com":
            if path == "/v1/facebook/adLibrary/search/companies":
                return respond("search-companies")
            if path == "/v1/facebook/adLibrary/company/ads":
                return respond("company-ads-page-2" if params.get("cursor") == "fx-cursor-page-2" else "company-ads-page-1")
        if request.url.host.endswith("fbcdn.net"):
            return httpx.Response(200, content=jpeg(), headers={"content-type": "image/jpeg"})
        return httpx.Response(404, json={"message": "not in the fixture"})

    def api(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == "api.scrapecreators.com"]


def library(vendor: Vendor, sleeps: list[float] | None = None) -> ScrapeCreatorsAdLibrary:
    return ScrapeCreatorsAdLibrary(KEY, transport=httpx.MockTransport(vendor),
                                   sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_every_fixture_declares_its_assumed_shape_and_source():
    files = sorted(FIX.glob("*.json"))
    assert len(files) >= 3
    for f in files:
        shape = json.loads(f.read_text())["_shape"]
        assert shape.startswith("ASSUMED SHAPE from https://"), f
        assert "read 2026-10-28" in shape and "replace with a recorded response at go-live" in shape, f
    assert "ASSUMED" in (FIX / "README.md").read_text()


def test_fetch_ads_finds_the_page_follows_the_cursor_and_normalises():
    vendor = Vendor()
    lib = library(vendor)
    ads = lib.fetch_ads("AG1")
    search, page1, page2 = vendor.api()
    assert search.url.path.endswith("/search/companies") and search.url.params["query"] == "AG1"
    assert page1.url.params["pageId"] == "fx-page-200", "the exact-name page wins over the first search result"
    assert "cursor" not in page1.url.params and page2.url.params["cursor"] == "fx-cursor-page-2"
    for r in vendor.api():
        assert r.method == "GET" and r.headers["x-api-key"] == KEY
    assert [a["ad_id"] for a in ads] == ["fx-sc-1001", "fx-sc-1002", "fx-sc-1003", "fx-sc-1004", "fx-sc-1005"]
    for a in ads:
        assert set(a) == AD_KEYS
        assert a["source"] == "scrapecreators" and a["brand"] == "AG1" and a["page_name"] == "AG1"
        assert len(a["start_date"]) == 10 and a["start_date"][4] == "-" and isinstance(a["is_active"], bool)
        assert a["images"], "every ad needs at least one still for FR-5"
        assert all(urlparse(u).hostname.endswith("fbcdn.net") for u in a["images"])
        assert a["raw"]["ad_archive_id"] == a["ad_id"], "the vendor row is kept for re-normalisation"
    by_id = {a["ad_id"]: a for a in ads}
    assert by_id["fx-sc-1001"]["start_date"] == "2026-07-20" and by_id["fx-sc-1001"]["end_date"] is None
    assert by_id["fx-sc-1001"]["images"] == ["https://scontent-fixture.xx.fbcdn.net/v/t39/fx-sc-1001-original.jpg"]
    assert by_id["fx-sc-1001"]["body"].startswith("SYNTHETIC") and by_id["fx-sc-1001"]["cta"] == "Shop now"
    assert by_id["fx-sc-1002"]["images"] == ["https://scontent-fixture.xx.fbcdn.net/v/t15/fx-sc-1002-preview.jpg"], \
        "a video ad's preview image is its still"
    assert by_id["fx-sc-1002"]["videos"] == ["https://video-fixture.xx.fbcdn.net/v/t42/fx-sc-1002-hd.mp4"]
    assert len(by_id["fx-sc-1003"]["images"]) == 2 and by_id["fx-sc-1003"]["end_date"] == "2026-07-01"
    assert by_id["fx-sc-1004"]["start_date"] == "2026-09-03" and by_id["fx-sc-1004"]["body"].startswith("SYNTHETIC")
    assert by_id["fx-sc-1005"]["is_active"] is False and by_id["fx-sc-1005"]["end_date"] == "2026-09-03"
    assert lib.usage() == {"backend": "scrapecreators", "api_calls": 3, "search_companies": 1, "company_ads": 2,
                           "image_fetches": 0}


def test_limit_stops_paging_and_the_page_id_is_looked_up_once_per_brand():
    vendor = Vendor()
    lib = library(vendor)
    assert [a["ad_id"] for a in lib.fetch_ads("AG1", limit=2)] == ["fx-sc-1001", "fx-sc-1002"]
    assert len(vendor.api()) == 2, "one search and one page: the limit was reached on page 1"
    lib.fetch_ads("AG1", limit=2)
    assert [r.url.path.rsplit("/", 1)[-1] for r in vendor.api()] == ["companies", "ads", "ads"], "page id cached"
    assert lib.usage()["api_calls"] == 3


def test_a_cursor_that_repeats_stops_the_paging():
    looping = exchange("company-ads-page-1")
    vendor = Vendor(**{"/v1/facebook/adLibrary/company/ads": lambda r: httpx.Response(200, json=looping["body"])})
    ads = library(vendor).fetch_ads("AG1", limit=500)
    assert len(vendor.api()) == 3, "search, page, the same cursor once more, then stop"
    assert [a["ad_id"] for a in ads] == ["fx-sc-1001", "fx-sc-1002", "fx-sc-1003"], "duplicates across pages dropped"


def test_unknown_brand_is_an_error_not_an_empty_list():
    vendor = Vendor(**{"/v1/facebook/adLibrary/search/companies": httpx.Response(200, json={"searchResults": []})})
    with pytest.raises(ScrapeCreatorsError, match="Nobody Inc"):
        library(vendor).fetch_ads("Nobody Inc")


def test_429_is_retried_with_retry_after_and_every_attempt_is_counted():
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "2"}, json={"message": "slow down"})
        return respond("search-companies")

    sleeps: list[float] = []
    vendor = Vendor(**{"/v1/facebook/adLibrary/search/companies": flaky})
    lib = library(vendor, sleeps)
    assert len(lib.fetch_ads("AG1")) == 5
    assert sleeps == [2.0] and lib.usage()["search_companies"] == 2 and lib.usage()["api_calls"] == 4


def test_a_refused_key_names_the_variable_never_the_value():
    vendor = Vendor(**{"/v1/facebook/adLibrary/search/companies": httpx.Response(401, json={"message": "Invalid API key"})})
    with pytest.raises(ScrapeCreatorsError) as exc:
        library(vendor).fetch_ads("AG1")
    assert "SCRAPECREATORS_API_KEY" in str(exc.value) and KEY not in str(exc.value)


def test_server_errors_after_the_retries_raise_without_the_key():
    sleeps: list[float] = []
    vendor = Vendor(**{"/v1/facebook/adLibrary/search/companies": httpx.Response(503, json={"message": "down"})})
    with pytest.raises(ScrapeCreatorsError, match="503") as exc:
        library(vendor, sleeps).fetch_ads("AG1")
    assert KEY not in str(exc.value) and len(sleeps) == 2 and len(vendor.api()) == 3


def test_fetch_image_returns_png_and_never_sends_the_key_to_the_cdn():
    vendor = Vendor()
    lib = library(vendor)
    url = lib.fetch_ads("AG1")[0]["images"][0]
    data = lib.fetch_image(url)
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "stored as .png by pull_inspo, so the adapter hands over PNG"
    assert Image.open(io.BytesIO(data)).size == (64, 48)
    cdn = [r for r in vendor.requests if r.url.host.endswith("fbcdn.net")]
    assert len(cdn) == 1 and "x-api-key" not in cdn[0].headers
    assert lib.usage()["image_fetches"] == 1 and lib.usage()["api_calls"] == 3, "CDN fetches are not vendor credits"


@pytest.mark.parametrize("url", [
    "http://scontent-fixture.xx.fbcdn.net/v/t39/x.jpg",          # not https
    "https://169.254.169.254/latest/meta-data/",                  # not a CDN host
    "https://fbcdn.net.evil.example/x.jpg",                       # suffix trick
    "fixture://ad_library/ag1/fx-ag1-001-1.png",
])
def test_fetch_image_refuses_anything_but_https_on_the_ad_cdn(url):
    vendor = Vendor()
    with pytest.raises(ScrapeCreatorsError):
        library(vendor).fetch_image(url)
    assert vendor.requests == []


def test_a_redirect_off_the_cdn_is_refused_before_it_is_followed():
    def bounce(request):
        if request.url.host.endswith("fbcdn.net"):
            return httpx.Response(302, headers={"location": "https://169.254.169.254/latest/"})
        return httpx.Response(200, content=jpeg())

    vendor = Vendor()
    vendor.overrides["/v/t39/x.jpg"] = bounce
    with pytest.raises(ScrapeCreatorsError):
        library(vendor).fetch_image("https://scontent-fixture.xx.fbcdn.net/v/t39/x.jpg")
    assert all(r.url.host.endswith("fbcdn.net") for r in vendor.requests)
    assert "fbcdn.net" in IMAGE_HOSTS


def test_a_cdn_answer_that_is_not_an_image_is_an_error():
    vendor = Vendor()
    vendor.overrides["/v/t39/x.jpg"] = httpx.Response(200, content=b"<html>login</html>", headers={"content-type": "text/html"})
    with pytest.raises(ScrapeCreatorsError, match="not an image"):
        library(vendor).fetch_image("https://scontent-fixture.xx.fbcdn.net/v/t39/x.jpg")


def test_selector_needs_the_key_and_names_it(monkeypatch):
    monkeypatch.setenv("INSPO_BACKEND", "scrapecreators")
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", "")
    with pytest.raises(MissingEnvVar, match="SCRAPECREATORS_API_KEY"):
        get_inspo()
    monkeypatch.setenv("SCRAPECREATORS_API_KEY", KEY)
    assert isinstance(get_inspo(), ScrapeCreatorsAdLibrary)


def test_the_fixture_backend_uses_the_same_normaliser():
    """One place to fix when the real shape lands: the dev fixtures and the live backend share `normalise`."""
    row = json.loads((FIXTURE_DIR / "ag1.json").read_text())["searchResults"][0]
    via_fixture = FixtureAdLibrary(FIXTURE_DIR).fetch_ads("AG1")[0]
    assert via_fixture == {**normalise(row, "AG1"), "source": "fixture"}
    assert normalise(row, "AG1", source="fixture") == via_fixture


# ---------- end to end: the intel worker on this backend against the warehouse ----------

pi_spec = importlib.util.spec_from_file_location("pull_inspo_sc", ME_DIR / "scripts" / "pull_inspo.py")
pi = importlib.util.module_from_spec(pi_spec)
pi_spec.loader.exec_module(pi)
MINE = "recipe->'source'->>'backend' = 'scrapecreators'"


@pytest.fixture
def sc_env(db_env, dev_root, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")

    def clean():
        with psycopg.connect(db_env["WAREHOUSE_URL_ADMIN"], autocommit=True) as admin:
            admin.execute(f"delete from patterns where {MINE}")
            admin.execute("delete from raw_ingest where source = 'ad_library' and payload->>'backend' = 'scrapecreators'")
            admin.execute("delete from runs where worker = 'intel' and counts ? 'inspo_usage'")

    clean()
    yield db_env
    clean()


def test_pull_inspo_on_the_scrapecreators_backend_stores_png_copies_and_records_vendor_calls(sc_env, dev_root):
    from adapters.model.fixture import FixtureModel
    from adapters.storage import get_storage
    from warehouse import client as wh

    lib = library(Vendor())
    with wh.connect("worker", job="test") as conn:
        client = wh.client_by_slug(conn, "upclicklabs")
        with wh.run(conn, pi.WORKER, client["id"]) as r:
            pi.pull(conn, r, brands=["AG1"], inspo=lib, storage=get_storage(),
                    model=FixtureModel(ME_DIR / "fixtures" / "model"), today=date(2026, 9, 7))
    with psycopg.connect(sc_env["WAREHOUSE_URL_ADMIN"], row_factory=dict_row) as conn:
        run = conn.execute("select * from runs where id = %s", (r.id,)).fetchone()
        pats = conn.execute(f"select * from patterns where {MINE} order by source_url").fetchall()
        raw = conn.execute("select payload from raw_ingest where source = 'ad_library' and payload->>'backend' = 'scrapecreators'").fetchall()
    assert run["status"] == "ok" and run["counts"]["sources_ok"] == ["AG1"] and run["counts"]["patterns_new"] == 5
    assert run["counts"]["inspo_usage"] == {"backend": "scrapecreators", "api_calls": 3, "search_companies": 1,
                                            "company_ads": 2, "image_fetches": 6}
    assert len(raw) == 5 and all(p["payload"]["ad"]["raw"]["ad_archive_id"] for p in raw)
    assert len(pats) == 5 and {p["source_brand"] for p in pats} == {"AG1"}
    storage_root = (dev_root / "storage").resolve()
    for p in pats:
        assert p["source_url"].startswith("https://www.facebook.com/ads/library/?id=fx-sc-")
        assert p["source_image_url"].startswith("file://"), "our Storage copy, never the CDN URL (FR-5)"
        path = Path(url2pathname(urlparse(p["source_image_url"]).path))
        assert path.is_relative_to(storage_root) and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert all(i["cdn_url"].startswith("https://") for i in p["recipe"]["source"]["images"])

