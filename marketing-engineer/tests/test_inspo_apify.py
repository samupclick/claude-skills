"""INSPO_BACKEND=apify (FR-4, FR-5, FR-8; CRUCIBLE A19; Sam's vendor choice of 2026-10-31): contract tests on
httpx.MockTransport against fixtures/apify/ (ASSUMED SHAPE until a real run is saved). Never the network, never a real
token. Apify's own actor runs on the brand's Facebook page, the run is polled to its end and its dataset read; every
run is capped in ads and dollars; the token travels in a header only and never reaches the ad CDN."""
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
from adapters.inspo import get_inspo
from adapters.inspo.apify import ACTOR, ApifyAdLibrary, ApifyError

FIX = ME_DIR / "fixtures" / "apify"
TOKEN = "apify_api_test_token_not_real"
PAGE = "https://www.facebook.com/fixturebrand"
AD_KEYS = {"source", "ad_id", "brand", "page_name", "start_date", "end_date", "is_active", "body", "title", "link_url",
           "cta", "display_format", "images", "videos", "raw"}
RUNS = f"/v2/actors/{ACTOR}/runs"
RUN = "/v2/actor-runs/fx-run-1"
ITEMS = "/v2/datasets/fx-dataset-1/items"


def exchange(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text())


def respond(name: str) -> httpx.Response:
    ex = exchange(name)
    return httpx.Response(ex["status"], json=ex["body"])


def jpeg(size=(64, 48), colour=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="JPEG")
    return buf.getvalue()


class Apify:
    """The Apify API and the Facebook CDN as fixtures; every request is recorded. `states` are the run's answers to
    successive polls (the last one repeats)."""

    def __init__(self, states=("run-succeeded",), items=None, **overrides):
        self.requests: list[httpx.Request] = []
        self.states = list(states)
        self.items = items
        self.overrides = overrides

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path in self.overrides:
            out = self.overrides[path]
            return out(request) if callable(out) else out
        if request.url.host == "api.apify.com":
            if request.method == "POST" and path == RUNS:
                return respond("run-started")
            if request.method == "GET" and path == RUN:
                return respond(self.states.pop(0) if len(self.states) > 1 else self.states[0])
            if request.method == "POST" and path == f"{RUN}/abort":
                return httpx.Response(200, json={"data": {"id": "fx-run-1", "status": "ABORTING"}})
            if request.method == "GET" and path == ITEMS:
                return httpx.Response(200, json=self.items if self.items is not None else exchange("dataset-items")["body"])
        if request.url.host.endswith("fbcdn.net"):
            return httpx.Response(200, content=jpeg(), headers={"content-type": "image/jpeg"})
        return httpx.Response(404, json={"error": {"type": "record-not-found", "message": "not in the fixture"}})

    def api(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == "api.apify.com"]


def library(apify: Apify, sleeps: list[float] | None = None, **kw) -> ApifyAdLibrary:
    return ApifyAdLibrary(TOKEN, transport=httpx.MockTransport(apify),
                          sleep=(sleeps.append if sleeps is not None else lambda s: None), **kw)


def test_every_fixture_declares_its_assumed_shape_and_source():
    for f in sorted(FIX.glob("*.json")):
        shape = json.loads(f.read_text())["_shape"]
        assert shape.startswith("SEEN SHAPE in real runs of https://apify.com/apify/facebook-ads-scraper"), f
        assert "2026-10-31" in shape and "SYNTHETIC" in shape and "no third-party ad is committed" in shape, f
    assert not [p for p in FIX.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".mp4")]


def test_fetch_ads_runs_the_actor_on_the_page_reads_the_dataset_and_normalises():
    apify = Apify()
    lib = library(apify)
    ads = lib.fetch_ads("Fixture Pillow", limit=20, page=PAGE)

    start, poll, items = apify.api()
    assert (start.method, start.url.path) == ("POST", RUNS)
    assert json.loads(start.content) == {"startUrls": [{"url": PAGE}], "resultsLimit": 20}
    assert start.url.params["maxItems"] == "20" and float(start.url.params["maxTotalChargeUsd"]) == lib.max_charge_usd
    assert (poll.method, poll.url.path, poll.url.params["waitForFinish"]) == ("GET", RUN, "60")
    assert (items.url.path, items.url.params["clean"], items.url.params["format"], items.url.params["limit"]) == (ITEMS, "true", "json", "20")
    for r in apify.requests:
        assert r.headers["authorization"] == f"Bearer {TOKEN}" and TOKEN not in str(r.url), "the token travels in a header only"

    assert [a["ad_id"] for a in ads] == ["fx-ap-2001", "fx-ap-2002", "fx-ap-2003"]
    assert all(set(a) == AD_KEYS and a["source"] == "apify" and a["brand"] == "Fixture Pillow" for a in ads)
    image_ad, dco_ad, video_ad = ads
    assert (image_ad["start_date"], image_ad["end_date"], image_ad["is_active"]) == ("2026-08-01", None, True)
    assert image_ad["body"] == "SYNTHETIC: Hulls that hold their shape all night."
    assert (image_ad["title"], image_ad["link_url"], image_ad["cta"], image_ad["display_format"]) == (
        "SYNTHETIC: The pillow that stays put", "https://shop.example/products/pillow", "Shop now", "IMAGE")
    assert image_ad["images"] == ["https://scontent.xx.fbcdn.net/v/fx-ap-2001.jpg"] and image_ad["page_name"] == "Fixture Pillow Co"
    assert dco_ad["images"] == ["https://scontent.xx.fbcdn.net/v/fx-ap-2002-a.jpg", "https://scontent.xx.fbcdn.net/v/fx-ap-2002-b-s.jpg"]
    assert (dco_ad["title"], dco_ad["link_url"], dco_ad["cta"]) == ("SYNTHETIC: Sleep cool", "https://shop.example/products/pillow?v=2", "Learn more")
    assert dco_ad["body"] == "SYNTHETIC: Cool side up, every night.", "a template placeholder body falls back to the first card"
    assert (video_ad["is_active"], video_ad["end_date"]) == (False, "2026-06-21")
    assert video_ad["images"] == ["https://scontent.xx.fbcdn.net/v/fx-ap-2003-preview.jpg"], "a video ad is judged on its preview frame"
    assert video_ad["videos"] == ["https://video.xx.fbcdn.net/v/fx-ap-2003-hd.mp4"]
    assert video_ad["raw"]["adArchiveID"] == "fx-ap-2003"
    assert lib.usage() == {"backend": "apify", "api_calls": 3, "runs": 1, "items": 3, "usage_usd": 0.0174, "image_fetches": 0}


def test_a_running_run_is_polled_until_it_ends():
    apify, sleeps = Apify(states=("run-running", "run-running", "run-succeeded")), []
    assert len(library(apify, sleeps).fetch_ads("Fixture Pillow", page=PAGE)) == 3
    assert [r.url.path for r in apify.api()].count(RUN) == 3 and len(sleeps) == 2


def test_a_run_that_never_ends_is_aborted_and_raised():
    apify = Apify(states=("run-running",))
    with pytest.raises(ApifyError, match=r"did not finish.*aborted"):
        library(apify, max_polls=4).fetch_ads("Fixture Pillow", page=PAGE)
    assert [r.url.path for r in apify.api()].count(RUN) == 4
    assert apify.api()[-1].url.path == f"{RUN}/abort", "a run we give up on stops billing"


def test_a_failed_run_is_an_error_naming_the_brand_and_the_status():
    with pytest.raises(ApifyError, match=r"'Fixture Pillow'.*FAILED.*could not be loaded"):
        library(Apify(states=("run-failed",))).fetch_ads("Fixture Pillow", page=PAGE)


@pytest.mark.parametrize("page", [None, "", "http://www.facebook.com/fixturebrand", "https://evil.example/fixturebrand",
                                  "https://www.facebook.com.evil.example/x"])
def test_no_page_or_one_off_facebook_is_refused_before_any_call(page):
    apify = Apify()
    with pytest.raises(ApifyError, match="clients.config.inspo.pages"):
        library(apify).fetch_ads("Fixture Pillow", page=page)
    assert apify.requests == []


def test_a_refused_token_names_the_variable_never_the_value():
    apify = Apify(**{RUNS: httpx.Response(401, json={"error": {"type": "token-not-valid", "message": f"bad token {TOKEN}"}})})
    with pytest.raises(ApifyError) as exc:
        library(apify).fetch_ads("Fixture Pillow", page=PAGE)
    assert "APIFY_TOKEN" in str(exc.value) and TOKEN not in str(exc.value)


def test_server_errors_after_the_retries_raise_without_the_token():
    apify = Apify(**{RUNS: httpx.Response(500, json={"error": {"type": "internal-error", "message": f"oops {TOKEN}"}})})
    with pytest.raises(ApifyError) as exc:
        library(apify).fetch_ads("Fixture Pillow", page=PAGE)
    assert "HTTP 500" in str(exc.value) and TOKEN not in str(exc.value)
    assert [r.url.path for r in apify.api()] == [RUNS] * 3


def test_limit_trims_and_a_repeated_ad_counts_once():
    items = exchange("dataset-items")["body"]
    ads = library(Apify(items=[items[0], items[0], items[1], items[2]])).fetch_ads("Fixture Pillow", limit=2, page=PAGE)
    assert [a["ad_id"] for a in ads] == ["fx-ap-2001", "fx-ap-2002"]


def test_fetch_image_returns_png_and_never_sends_the_token_to_the_cdn():
    apify = Apify()
    lib = library(apify)
    png = lib.fetch_image("https://scontent.xx.fbcdn.net/v/fx-ap-2001.jpg")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    (cdn,) = [r for r in apify.requests if r.url.host.endswith("fbcdn.net")]
    assert "authorization" not in cdn.headers and TOKEN not in str(cdn.url)
    with pytest.raises(ApifyError, match="not https on an ad CDN host"):
        lib.fetch_image("https://evil.example/x.jpg")
    assert lib.usage()["image_fetches"] == 2


def test_selector_needs_the_token_and_names_it(monkeypatch):
    monkeypatch.setenv("INSPO_BACKEND", "apify")
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    with pytest.raises(MissingEnvVar, match="APIFY_TOKEN"):
        get_inspo()
    monkeypatch.setenv("APIFY_TOKEN", TOKEN)
    assert isinstance(get_inspo(), ApifyAdLibrary)


# ---------- end to end: the intel worker on this backend against the warehouse ----------

pi_spec = importlib.util.spec_from_file_location("pull_inspo_apify", ME_DIR / "scripts" / "pull_inspo.py")
pi = importlib.util.module_from_spec(pi_spec)
pi_spec.loader.exec_module(pi)
MINE = "recipe->'source'->>'backend' = 'apify'"


@pytest.fixture
def apify_env(db_env, dev_root, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")

    def clean():
        with psycopg.connect(db_env["WAREHOUSE_URL_ADMIN"], autocommit=True) as admin:
            admin.execute(f"delete from patterns where {MINE}")
            admin.execute("delete from raw_ingest where source = 'ad_library' and payload->>'backend' = 'apify'")
            admin.execute("delete from runs where worker = 'intel' and counts->'inspo_usage'->>'backend' = 'apify'")

    clean()
    yield db_env
    clean()


def test_pull_inspo_on_the_apify_backend_uses_the_configured_page_and_the_per_brand_limit(apify_env, dev_root):
    from adapters.model.fixture import FixtureModel
    from adapters.storage import get_storage
    from warehouse import client as wh

    apify = Apify()
    lib = library(apify)
    with wh.connect("worker", job="test") as conn:
        client = wh.client_by_slug(conn, "upclicklabs")
        with wh.run(conn, pi.WORKER, client["id"]) as r:
            pi.pull(conn, r, brands=["Fixture Pillow"], pages={"Fixture Pillow": PAGE}, per_brand=2, inspo=lib,
                    storage=get_storage(), model=FixtureModel(ME_DIR / "fixtures" / "model"), today=date(2026, 10, 31))
    start = apify.api()[0]
    assert json.loads(start.content) == {"startUrls": [{"url": PAGE}], "resultsLimit": 2}
    with psycopg.connect(apify_env["WAREHOUSE_URL_ADMIN"], row_factory=dict_row) as conn:
        run = conn.execute("select * from runs where id = %s", (r.id,)).fetchone()
        pats = conn.execute(f"select * from patterns where {MINE} order by source_url").fetchall()
    assert run["status"] == "ok" and run["counts"]["sources_ok"] == ["Fixture Pillow"] and run["counts"]["patterns_new"] == 2
    usage = run["counts"]["inspo_usage"]
    assert (usage["backend"], usage["runs"], usage["image_fetches"]) == ("apify", 1, 3)
    storage_root = (dev_root / "storage").resolve()
    assert {p["source_brand"] for p in pats} == {"Fixture Pillow"}
    for p in pats:
        assert p["source_url"].startswith("https://www.facebook.com/ads/library/?id=fx-ap-")
        path = Path(url2pathname(urlparse(p["source_image_url"]).path))
        assert path.is_relative_to(storage_root) and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", "our Storage copy (FR-5)"


# ---------- shapes first seen in real runs on 2026-10-31 ----------

def test_a_page_with_no_ads_answers_one_summary_item_and_that_is_zero_ads():
    summary = exchange("dataset-page-summary")["body"]
    lib = library(Apify(items=summary))
    assert lib.fetch_ads("Fixture Pillow", page=PAGE) == []
    assert lib.usage()["items"] == 0


def test_a_summary_item_that_carries_results_yields_its_ads():
    ad = exchange("dataset-items")["body"][0]
    summary = exchange("dataset-page-summary")["body"][0]
    ads = library(Apify(items=[{**summary, "totalCount": 1, "results": [ad]}])).fetch_ads("Fixture Pillow", page=PAGE)
    assert [a["ad_id"] for a in ads] == ["fx-ap-2001"]


def test_an_error_item_fails_the_source_with_the_actors_code():
    errors = exchange("dataset-error")["body"]
    with pytest.raises(ApifyError, match=r"'Fixture Pillow'.*no_items.*Empty or private data"):
        library(Apify(items=errors)).fetch_ads("Fixture Pillow", page=PAGE)
