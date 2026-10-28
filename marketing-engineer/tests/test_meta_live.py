"""Contract tests for adapters/meta/live.py (META_BACKEND=live) against httpx.MockTransport serving fixtures/meta/*.json,
whose shapes are copied from Meta's documentation (ASSUMED until one recorded response replaces each at go-live). No
call leaves the process. Covers the MetaAds protocol, minor-unit budgets, image upload by hash, async insights with
polling, throttle mapping and backoff (NFR-4), review status (FR-37), and the read/write token split (NFR-1)."""
from __future__ import annotations

import base64
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from adapters.env import MissingEnvVar
from adapters.meta import MetaApiError, MetaThrottled, get_meta, review_status
from adapters.meta.live import DEFAULT_API_VERSION, LiveMeta

ME_DIR = Path(__file__).resolve().parent.parent
FIX = ME_DIR / "fixtures" / "meta"
TOKEN = "EAAB-test-token-never-printed"
ACCOUNT = "100000000000001"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
CONVERSIONS = {"QuizStart": "300000000000001", "QuizComplete": "300000000000002"}


def fixture(name):
    raw = json.loads((FIX / f"{name}.json").read_text())
    raw.pop("_shape")
    return raw.pop("_status", 200), raw.pop("_headers", {}), raw


class Clock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


class Graph:
    """The Graph API as a stub: routes (method, path regex) to fixture names, bodies or callables, consumed in order
    (the last one repeats), and records every request."""

    def __init__(self):
        self.routes: list[tuple[str, re.Pattern, list]] = []
        self.requests: list[httpx.Request] = []
        self.on("GET", rf"/act_{ACCOUNT}$", "account")

    def on(self, method, pattern, *responses):
        self.routes.insert(0, (method, re.compile(pattern), list(responses)))
        return self

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for method, pattern, responses in self.routes:
            if method == request.method and pattern.search(request.url.path):
                spec = responses.pop(0) if len(responses) > 1 else responses[0]
                if callable(spec):
                    spec = spec(request)
                if isinstance(spec, httpx.Response):
                    return spec
                status, headers, body = fixture(spec) if isinstance(spec, str) else (200, {}, spec)
                return httpx.Response(status, headers=headers, json=body)
        return httpx.Response(404, json={"error": {"message": f"stub has no route for {request.method} {request.url.path}", "code": 803}})

    def calls(self, method=None, pattern=""):
        return [r for r in self.requests if (method is None or r.method == method) and re.search(pattern, r.url.path)]


def form(request: httpx.Request) -> dict:
    out = {k: v[0] for k, v in parse_qs(request.content.decode(), keep_blank_values=True).items()}
    return {k: _json_or_str(v) for k, v in out.items()}


def query(request: httpx.Request) -> dict:
    return {k: _json_or_str(v) for k, v in request.url.params.items()}


def _json_or_str(v):
    """JSON-encoded objects, lists and booleans are decoded; everything else (ids, minor-unit budgets) stays the string sent."""
    return json.loads(v) if v[:1] in ("[", "{") or v in ("true", "false", "null") else v


@pytest.fixture
def graph():
    return Graph()


@pytest.fixture
def clock():
    return Clock()


def live(graph, clock, *, write=True, **kw):
    args = dict(token=TOKEN, ad_account_id=ACCOUNT, page_id="400000000000001", pixel_id="200000000000001", write=write,
                transport=httpx.MockTransport(graph.handler), sleep=clock.sleep, clock=clock.now,
                fetch_image=lambda url: PNG, custom_conversions=dict(CONVERSIONS))
    args.update(kw)
    return LiveMeta(**args)


# ---------- selection and secrets ----------

def test_backend_selector_builds_live_from_env_and_names_missing_variables(monkeypatch):
    monkeypatch.setenv("META_BACKEND", "live")
    for var in ("META_ACCESS_TOKEN", "META_READ_TOKEN", "META_AD_ACCOUNT_ID", "META_API_VERSION", "META_CUSTOM_CONVERSIONS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("META_ACCESS_TOKEN", TOKEN)
    with pytest.raises(MissingEnvVar) as exc:
        get_meta(write=True)
    assert "META_AD_ACCOUNT_ID" in str(exc.value) and TOKEN not in str(exc.value)
    monkeypatch.setenv("META_AD_ACCOUNT_ID", f"act_{ACCOUNT}")
    meta = get_meta(write=True)
    assert isinstance(meta, LiveMeta) and meta.write and meta.account == f"act_{ACCOUNT}" and meta.api_version == DEFAULT_API_VERSION
    with pytest.raises(MissingEnvVar) as exc:                       # a worker never borrows the executor's write token
        get_meta()
    assert "META_READ_TOKEN" in str(exc.value) and TOKEN not in str(exc.value)
    monkeypatch.setenv("META_READ_TOKEN", "EAAB-read-only")
    monkeypatch.setenv("META_API_VERSION", "v25.0")
    monkeypatch.setenv("META_CUSTOM_CONVERSIONS", "QuizStart=301, QuizComplete=302")
    reader = get_meta()
    assert not reader.write and reader.api_version == "v25.0" and reader.custom_conversions == {"QuizStart": "301", "QuizComplete": "302"}
    monkeypatch.setenv("META_API_VERSION", "26")
    with pytest.raises(MetaApiError, match="META_API_VERSION"):
        get_meta()
    monkeypatch.setenv("META_API_VERSION", "v26.0")
    monkeypatch.setenv("META_CUSTOM_CONVERSIONS", "QuizStart")
    with pytest.raises(MetaApiError, match="META_CUSTOM_CONVERSIONS"):
        get_meta()


def test_only_the_executor_asks_for_the_write_client():
    """SKILL.md §4 rule 1 at the adapter boundary: `get_meta(write=True)` appears in scripts/apply_actions.py only."""
    writers = sorted(str(p.relative_to(ME_DIR)) for p in ME_DIR.rglob("*.py")
                     if p.parts[len(ME_DIR.parts)] not in ("tests", "adapters", ".dev") and "get_meta(write=True)" in p.read_text())
    assert writers == ["scripts/apply_actions.py"]
    assert "get_meta(write" not in (ME_DIR / "scripts" / "meta_insights.py").read_text()


def test_default_version_is_the_current_marketing_api_and_the_token_rides_in_a_header(graph, clock):
    assert DEFAULT_API_VERSION == "v26.0"
    graph.on("GET", r"/120200000000000010$", "campaign")
    obj = live(graph, clock).get("campaign", "120200000000000010")
    req = graph.requests[-1]
    assert req.url.host == "graph.facebook.com" and req.url.path == "/v26.0/120200000000000010"
    assert req.headers["authorization"] == f"Bearer {TOKEN}" and TOKEN not in str(req.url)
    assert set(query(req)["fields"].split(",")) >= {"id", "name", "status", "effective_status", "daily_budget"}
    assert obj == {"id": "120200000000000010", "name": "ucl-new_recipes-b1", "status": "PAUSED", "effective_status": "PAUSED",
                   "objective": "OUTCOME_LEADS", "daily_budget": None, "created_time": "2026-10-27T09:10:02+0000"}
    graph.on("GET", r"/v25.0/120200000000000010$", "campaign")
    live(graph, clock, api_version="v25.0").get("campaign", "120200000000000010")
    assert graph.requests[-1].url.path == "/v25.0/120200000000000010"


def test_read_only_client_refuses_every_write_before_any_request(graph, clock):
    meta = live(graph, clock, write=False)
    calls = [lambda: meta.create_campaign("x", objective="OUTCOME_LEADS"),
             lambda: meta.create_adset("x", campaign_id="1", daily_budget=15, optimization_event="QuizStart", targeting={"geo": ["GB"]}),
             lambda: meta.create_creative("x", image_url="file:///x.png", body="b", title="t", link_url="https://go.example/quiz"),
             lambda: meta.create_ad("x", adset_id="1", creative_id="2"),
             lambda: meta.update("ad", "1", status="PAUSED")]
    for call in calls:
        with pytest.raises(MetaApiError, match="META_ACCESS_TOKEN"):
            call()
    assert graph.requests == []


def test_errors_name_codes_never_the_token(graph, clock):
    def echo_token(request):
        return httpx.Response(400, json={"error": {"message": f"Malformed access token {TOKEN}", "type": "OAuthException", "code": 190}})
    graph.on("GET", r"/1$", echo_token)
    with pytest.raises(MetaApiError) as exc:
        live(graph, clock).get("ad", "1")
    assert "190" in str(exc.value) and TOKEN not in str(exc.value) and not isinstance(exc.value, MetaThrottled)
    graph.on("GET", r"/2$", "error_invalid_parameter")
    with pytest.raises(MetaApiError) as exc:
        live(graph, clock).get("ad", "2")
    assert "100" in str(exc.value) and "1885272" in str(exc.value) and "Budget Too Low" in str(exc.value)
    assert getattr(exc.value, "code", None) == 100


# ---------- creates: budgets, targeting, promoted object, image upload ----------

def test_create_campaign_sends_adset_budgets_and_reads_the_object_back(graph, clock):
    graph.on("POST", rf"/act_{ACCOUNT}/campaigns$", "created").on("GET", r"/120200000000000010$", "campaign")
    obj = live(graph, clock).create_campaign("ucl-new_recipes-b1", objective="OUTCOME_LEADS")
    body = form(graph.calls("POST")[0])
    assert body["name"] == "ucl-new_recipes-b1" and body["objective"] == "OUTCOME_LEADS" and body["status"] == "PAUSED"
    assert body["special_ad_categories"] == [] and body["is_adset_budget_sharing_enabled"] is False and "daily_budget" not in body
    assert obj["id"] == "120200000000000010" and obj["status"] == "PAUSED" and obj["daily_budget"] is None


def test_budgets_cross_the_boundary_in_minor_units(graph, clock):
    graph.on("POST", rf"/act_{ACCOUNT}/campaigns$", "created").on("GET", r"/120200000000000010$", {**fixture("campaign")[2], "daily_budget": "4500"})
    camp = live(graph, clock).create_campaign("scaling", objective="OUTCOME_LEADS", daily_budget=45)
    body = form(graph.calls("POST")[-1])
    assert body["daily_budget"] == "4500" and "is_adset_budget_sharing_enabled" not in body and camp["daily_budget"] == 45.0
    meta = live(graph, clock)
    assert meta.to_minor(15) == 1500 and meta.to_minor(18.0) == 1800 and meta.to_minor("15.555") == 1556
    assert meta.from_minor("1500") == 15.0 and meta.from_minor(None) is None
    with pytest.raises(MetaApiError, match="positive"):
        meta.to_minor(0)
    yen = Graph().on("GET", rf"/act_{ACCOUNT}$", {"id": f"act_{ACCOUNT}", "currency": "JPY"})
    jp = live(yen, clock)
    assert jp.to_minor(1500) == 1500 and jp.from_minor("1500") == 1500.0, "JPY has offset 1 in Meta's currency table"
    odd = Graph().on("GET", rf"/act_{ACCOUNT}$", {"id": f"act_{ACCOUNT}", "currency": "XYZ"})
    with pytest.raises(MetaApiError, match="XYZ"):
        live(odd, clock).to_minor(10)


def test_create_adset_maps_our_targeting_budget_and_optimisation_event(graph, clock):
    graph.on("POST", rf"/act_{ACCOUNT}/adsets$", lambda r: {"id": "120200000000000020"}).on("GET", r"/120200000000000020$", "adset")
    meta = live(graph, clock)
    obj = meta.create_adset("ucl-new_recipes-b1-as1", campaign_id="120200000000000010", daily_budget=15.0, optimization_event="QuizStart",
                            targeting={"geo": ["GB", "IE", "NL", "DE"], "age_min": 25, "age_max": 65})
    body = form(graph.calls("POST")[0])
    assert body["daily_budget"] == "1500" and body["campaign_id"] == "120200000000000010" and body["status"] == "PAUSED"
    assert body["optimization_goal"] == "OFFSITE_CONVERSIONS" and body["billing_event"] == "IMPRESSIONS"
    assert body["destination_type"] == "WEBSITE" and body["bid_strategy"] == "LOWEST_COST_WITHOUT_CAP"
    assert body["promoted_object"] == {"pixel_id": "200000000000001", "custom_event_type": "OTHER", "custom_conversion_id": "300000000000001"}
    assert body["targeting"] == {"geo_locations": {"countries": ["GB", "IE", "NL", "DE"]}, "age_min": 25, "age_max": 65,
                                 "targeting_automation": {"advantage_audience": 0}}
    assert obj == {"id": "120200000000000020", "name": "ucl-new_recipes-b1-as1", "status": "PAUSED", "effective_status": "CAMPAIGN_PAUSED",
                   "campaign_id": "120200000000000010", "daily_budget": 15.0, "optimization_event": "QuizStart",
                   "targeting": {"geo": ["GB", "IE", "NL", "DE"], "age_min": 25, "age_max": 65}, "created_time": "2026-10-27T09:10:20+0000"}
    meta.create_adset("s", campaign_id="1", daily_budget=15, optimization_event="Schedule", targeting={"geo": ["GB"]})
    assert form(graph.calls("POST")[-1])["promoted_object"] == {"pixel_id": "200000000000001", "custom_event_type": "SCHEDULE"}
    sent = len(graph.requests)
    with pytest.raises(MetaApiError, match="META_CUSTOM_CONVERSIONS"):
        live(graph, clock, custom_conversions={}).create_adset("q", campaign_id="1", daily_budget=15, optimization_event="QuizComplete",
                                                               targeting={"geo": ["GB"]})
    with pytest.raises(MissingEnvVar, match="META_PIXEL_ID"):
        live(graph, clock, pixel_id="").create_adset("q", campaign_id="1", daily_budget=15, optimization_event="QuizStart", targeting={"geo": ["GB"]})
    assert len(graph.requests) == sent, "both refusals happen before any request"


def test_create_creative_uploads_the_storage_image_and_references_its_hash(graph, clock):
    fetched = []
    graph.on("POST", rf"/act_{ACCOUNT}/adimages$", "adimages").on("POST", rf"/act_{ACCOUNT}/adcreatives$", {"id": "120200000000000030"}) \
         .on("GET", r"/120200000000000030$", "creative")
    meta = live(graph, clock, fetch_image=lambda url: fetched.append(url) or PNG)
    link = "http://localhost:8788/quiz?utm_source=facebook&utm_medium=paid&utm_campaign=ucl-new_recipes-b1&utm_content=c1"
    obj = meta.create_creative("ucl-new_recipes-b1-cr1", image_url="https://store.example/creatives/c1/1080x1080.png",
                               body="Is ChatGPT naming your competitors instead of you?", title="Free 15-minute AI visibility audit", link_url=link)
    assert fetched == ["https://store.example/creatives/c1/1080x1080.png"]
    upload = form(graph.calls("POST", "adimages")[0])
    assert base64.b64decode(upload["bytes"]) == PNG
    spec = form(graph.calls("POST", "adcreatives")[0])["object_story_spec"]
    assert spec == {"page_id": "400000000000001", "link_data": {
        "image_hash": "0f3b5c1e9a7d4c2b8e6f1a0d3c5b7e9f", "link": link, "message": "Is ChatGPT naming your competitors instead of you?",
        "name": "Free 15-minute AI visibility audit", "call_to_action": {"type": "LEARN_MORE", "value": {"link": link}}}}
    assert obj["id"] == "120200000000000030" and obj["image_hash"] == "0f3b5c1e9a7d4c2b8e6f1a0d3c5b7e9f" and obj["link_url"] == link
    assert obj["body"].startswith("Is ChatGPT") and obj["title"].startswith("Free") and obj["page_id"] == "400000000000001"
    with pytest.raises(MissingEnvVar, match="META_PAGE_ID"):
        live(graph, clock, page_id="").create_creative("x", image_url="u", body="b", title="t", link_url=link)


def test_create_ad_points_at_the_creative_and_reads_review_state(graph, clock):
    graph.on("POST", rf"/act_{ACCOUNT}/ads$", {"id": "120200000000000041"}).on("GET", r"/120200000000000041$", "ad_disapproved")
    obj = live(graph, clock).create_ad("ucl-new_recipes-b1-ad2", adset_id="120200000000000020", creative_id="120200000000000031")
    body = form(graph.calls("POST")[0])
    assert body["creative"] == {"creative_id": "120200000000000031"} and body["adset_id"] == "120200000000000020" and body["status"] == "PAUSED"
    assert obj["adset_id"] == "120200000000000020" and obj["creative_id"] == "120200000000000031" and obj["campaign_id"] == "120200000000000010"
    assert obj["review_status"] == "DISAPPROVED" and obj["ad_review_feedback"] == {"global": {"Personal Attributes": "Ads must not assert or imply personal attributes."}}


# ---------- reads ----------

def test_review_status_is_derived_from_effective_status_and_feedback(graph, clock):
    assert review_status("DISAPPROVED", {}) == "DISAPPROVED"
    assert review_status("PAUSED", {"global": {"x": "y"}}) == "DISAPPROVED"
    assert review_status("WITH_ISSUES", None) == "WITH_ISSUES" and review_status("ACTIVE", {"placement_specific": {"ig": {"x": "y"}}}) == "WITH_ISSUES"
    assert review_status("PENDING_REVIEW", {}) == "PENDING" and review_status("IN_PROCESS", {}) == "PENDING"
    assert review_status("ACTIVE", {}) == "APPROVED" and review_status("PREAPPROVED", None) == "APPROVED"
    assert review_status("PAUSED", {}) is None and review_status("ADSET_PAUSED", None) is None, "silent on review: the caller keeps what it had"
    graph.on("GET", r"/120200000000000040$", "ad_active")
    ad = live(graph, clock).get("ad", "120200000000000040")
    assert ad["review_status"] == "APPROVED" and ad["ad_review_feedback"] == {} and ad["status"] == "ACTIVE" and ad["effective_status"] == "ACTIVE"
    assert "ad_review_feedback" in query(graph.requests[-1])["fields"] and "creative{id}" in query(graph.requests[-1])["fields"]


def test_find_by_name_filters_pages_and_compares_exactly(graph, clock):
    graph.on("GET", rf"/act_{ACCOUNT}/campaigns$", "campaigns_page1", "campaigns_page2")
    found = live(graph, clock).find_by_name("campaign", "ucl-new_recipes-b1")
    assert found["id"] == "120200000000000010", "the near-namesake on page 1 is skipped"
    first, second = graph.calls("GET", "/campaigns$")
    q = query(first)
    assert q["filtering"] == [{"field": "name", "operator": "EQUAL", "value": "ucl-new_recipes-b1"}]
    assert "DELETED" not in q["effective_status"] and {"ACTIVE", "PAUSED", "ARCHIVED", "DISAPPROVED"} <= set(q["effective_status"])
    assert query(second)["after"] == "QVFIUmFmdGVy"
    graph.on("GET", rf"/act_{ACCOUNT}/ads$", {"data": [], "paging": {"cursors": {}}})
    assert live(graph, clock).find_by_name("ad", "nothing-here") is None
    graph.on("GET", rf"/act_{ACCOUNT}/adcreatives$", {"data": [{"id": "9", "name": "cr", "status": "ACTIVE"}]})
    assert live(graph, clock).find_by_name("creative", "cr")["id"] == "9"
    assert "effective_status" not in query(graph.requests[-1])
    with pytest.raises(MetaApiError, match="kind"):
        live(graph, clock).find_by_name("page", "x")


def test_find_by_name_falls_back_to_a_full_listing_when_the_filter_is_refused(graph, clock):
    def listing(request):
        if "filtering" in request.url.params:
            return httpx.Response(400, json={"error": {"message": "Filtering field name is invalid", "code": 100}})
        return httpx.Response(200, json={"data": [{"id": "77", "name": "as-1"}, {"id": "78", "name": "as-2"}]})
    graph.on("GET", rf"/act_{ACCOUNT}/adsets$", listing)
    meta = live(graph, clock)
    assert meta.find_by_name("adset", "as-2")["id"] == "78"
    assert meta.find_by_name("adset", "as-1")["id"] == "77"
    assert sum(1 for r in graph.calls("GET", "/adsets$") if "filtering" in r.url.params) == 1, "the refusal is remembered"


def test_update_sends_status_and_minor_unit_budget_and_refuses_review_fields(graph, clock):
    graph.on("POST", r"/120200000000000020$", "updated").on("GET", r"/120200000000000020$", {**fixture("adset")[2], "daily_budget": "1800"})
    meta = live(graph, clock)
    obj = meta.update("adset", "120200000000000020", daily_budget=18.0)
    assert form(graph.calls("POST")[-1]) == {"daily_budget": "1800"} and obj["daily_budget"] == 18.0
    graph.on("POST", r"/120200000000000040$", "updated").on("GET", r"/120200000000000040$", "ad_active")
    meta.update("ad", "120200000000000040", status="ACTIVE", on=date.today())
    assert form(graph.calls("POST")[-1]) == {"status": "ACTIVE"}
    sent = len(graph.requests)
    with pytest.raises(MetaApiError, match="review_status"):
        meta.update("ad", "120200000000000040", review_status="DISAPPROVED")
    with pytest.raises(MetaApiError, match="on="):
        meta.update("ad", "120200000000000040", status="PAUSED", on=date(2026, 9, 1))
    with pytest.raises(MetaApiError, match="kind"):
        meta.update("page", "1", status="PAUSED")
    assert len(graph.requests) == sent


# ---------- insights: async job, polling with backoff, paging, normalisation ----------

def test_insights_runs_an_async_job_polls_with_backoff_and_normalises_rows(graph, clock):
    graph.on("POST", rf"/act_{ACCOUNT}/insights$", "insights_report_run") \
         .on("GET", r"/6023920149050$", "report_run_running", "report_run_running", "report_run_completed") \
         .on("GET", r"/6023920149050/insights$", "insights_ad_page1", "insights_ad_page2")
    rows = live(graph, clock, write=False).insights(level="ad", since=date(2026, 10, 26), until=date(2026, 10, 27),
                                                    ids=["120200000000000040", "120200000000000041"])
    job = form(graph.calls("POST")[0])
    assert job["level"] == "ad" and job["time_range"] == {"since": "2026-10-26", "until": "2026-10-27"} and job["time_increment"] == "1"
    assert job["filtering"] == [{"field": "ad.id", "operator": "IN", "value": ["120200000000000040", "120200000000000041"]}]
    assert {"ad_id", "adset_id", "campaign_id", "impressions", "reach", "clicks", "inline_link_clicks", "spend", "frequency", "actions"} \
        <= set(job["fields"].split(","))
    assert len(graph.calls("GET", r"/6023920149050$")) == 3 and clock.sleeps[:3] == sorted(clock.sleeps[:3]) and clock.sleeps[0] > 0
    assert query(graph.calls("GET", "/insights$")[1])["after"] == "MQZDZD"
    assert [(r["date_start"], r["ad_id"]) for r in rows] == [("2026-10-26", "120200000000000040"), ("2026-10-26", "120200000000000041"),
                                                             ("2026-10-27", "120200000000000040")]
    first = rows[0]
    assert first == {"date_start": "2026-10-26", "date_stop": "2026-10-26", "ad_id": "120200000000000040", "ad_name": "ucl-new_recipes-b1-ad1",
                     "adset_id": "120200000000000020", "campaign_id": "120200000000000010", "impressions": 2104, "reach": 1733, "clicks": 52,
                     "link_clicks": 38, "spend": 14.52, "frequency": 1.214079, "video_3s": None,
                     "actions": [{"action_type": "QuizStart", "value": 21}, {"action_type": "QuizComplete", "value": 15},
                                 {"action_type": "Schedule", "value": 3}]}
    assert rows[2]["actions"] == [] and rows[2]["link_clicks"] == 24
    assert live(graph, clock).insights(level="ad", since=date(2026, 10, 26), until=date(2026, 10, 27), ids=[]) == []
    with pytest.raises(MetaApiError, match="level"):
        live(graph, clock).insights(level="campaign", since=date(2026, 10, 26), until=date(2026, 10, 27))


def test_account_spend_today_is_the_account_level_job_for_one_day(graph, clock):
    graph.on("POST", rf"/act_{ACCOUNT}/insights$", "insights_report_run").on("GET", r"/6023920149050$", "report_run_completed") \
         .on("GET", r"/6023920149050/insights$", "insights_account")
    assert live(graph, clock, write=False).account_spend_today(date(2026, 10, 28)) == 27.43
    job = form(graph.calls("POST")[0])
    assert job["level"] == "account" and job["time_range"] == {"since": "2026-10-28", "until": "2026-10-28"} and "filtering" not in job


def test_failed_or_endless_report_jobs_raise(graph, clock):
    graph.on("POST", rf"/act_{ACCOUNT}/insights$", "insights_report_run").on("GET", r"/6023920149050$", "report_run_failed")
    with pytest.raises(MetaApiError, match="Job Failed.*1487534"):
        live(graph, clock).insights(level="ad", since=date(2026, 10, 26), until=date(2026, 10, 27))
    graph.on("GET", r"/6023920149050$", "report_run_running")
    with pytest.raises(MetaApiError, match="still 'Job Running'"):
        live(graph, clock, insights_timeout=120).insights(level="ad", since=date(2026, 10, 26), until=date(2026, 10, 27))
    assert sum(clock.sleeps) <= 120 + 60


# ---------- throttling (NFR-4) ----------

@pytest.mark.parametrize("code", [4, 17, 32, 613, 80000, 80004, 80014])
def test_throttle_codes_raise_meta_throttled_with_the_usage_headers(graph, clock, code):
    status, headers, body = fixture("error_throttled")
    body["error"]["code"] = code
    graph.on("GET", r"/1$", lambda r: httpx.Response(status, headers=headers, json=body))
    with pytest.raises(MetaThrottled) as exc:
        live(graph, clock, max_wait=0).get("ad", "1")
    assert str(code) in str(exc.value) and "x-business-use-case-usage" in exc.value.headers and "x-ad-account-usage" in exc.value.headers
    assert json.loads(exc.value.headers["x-ad-account-usage"])["acc_id_util_pct"] == 100 and TOKEN not in str(exc.value.headers)


def test_throttled_call_backs_off_by_the_headers_then_succeeds(graph, clock):
    graph.on("GET", r"/120200000000000040$", "error_throttled", "ad_active")
    meta = live(graph, clock)
    assert meta.get("ad", "120200000000000040")["id"] == "120200000000000040"
    assert clock.sleeps and clock.sleeps[0] >= 60, "estimated_time_to_regain_access (1 min) / reset_time_duration (60 s) set the wait"
    assert "x-business-use-case-usage" not in meta.last_headers or json.loads(meta.last_headers["x-business-use-case-usage"]) != {}


def test_high_usage_headers_pace_the_next_call(graph, clock):
    busy = {"x-ad-account-usage": json.dumps({"acc_id_util_pct": 95, "reset_time_duration": 42})}
    graph.on("GET", r"/120200000000000040$", lambda r: httpx.Response(200, headers=busy, json=fixture("ad_active")[2]))
    meta = live(graph, clock)
    meta.get("ad", "120200000000000040")
    assert clock.sleeps == [] and json.loads(meta.last_headers["x-ad-account-usage"])["acc_id_util_pct"] == 95
    meta.get("ad", "120200000000000040")
    assert clock.sleeps == [42]


def test_high_usage_paces_even_when_the_headers_say_no_wait(graph, clock):
    """Meta sends estimated_time_to_regain_access in every x-business-use-case-usage entry, 0 until the caller is
    blocked, and reset_time_duration 0 below the limit: at 90% or more the next call still waits PACE_DEFAULT_WAIT."""
    from adapters.meta.live import PACE_DEFAULT_WAIT
    busy = {"x-business-use-case-usage": json.dumps({ACCOUNT: [{"type": "ads_management", "call_count": 95, "total_cputime": 20,
                                                                "total_time": 30, "estimated_time_to_regain_access": 0}]}),
            "x-ad-account-usage": json.dumps({"acc_id_util_pct": 96, "reset_time_duration": 0})}
    graph.on("GET", r"/120200000000000040$", lambda r: httpx.Response(200, headers=busy, json=fixture("ad_active")[2]))
    meta = live(graph, clock)
    for _ in range(3):
        meta.get("ad", "120200000000000040")
    assert clock.sleeps == [PACE_DEFAULT_WAIT, PACE_DEFAULT_WAIT]


def test_a_write_that_may_have_landed_is_never_resent_but_a_read_is_retried(graph, clock):
    def boom(request):
        raise httpx.ReadTimeout("timed out", request=request)
    graph.on("POST", rf"/act_{ACCOUNT}/campaigns$", boom)
    with pytest.raises(MetaApiError, match="name lookup"):
        live(graph, clock).create_campaign("c", objective="OUTCOME_LEADS")
    assert len(graph.calls("POST")) == 1
    graph.on("POST", rf"/act_{ACCOUNT}/ads$", lambda r: httpx.Response(500, json={"error": {"message": "An unknown error occurred", "code": 1, "is_transient": True}}))
    with pytest.raises(MetaApiError):
        live(graph, clock).create_ad("a", adset_id="1", creative_id="2")
    assert len(graph.calls("POST", "/ads$")) == 1
    graph.on("GET", r"/120200000000000040$", lambda r: httpx.Response(500, json={"error": {"message": "unknown", "code": 2, "is_transient": True}}),
             "ad_active")
    assert live(graph, clock).get("ad", "120200000000000040")["id"] == "120200000000000040"


def test_every_meta_fixture_carries_the_assumed_shape_note():
    files = sorted(FIX.glob("*.json"))
    assert len(files) >= 15
    for f in files:
        raw = json.loads(f.read_text())
        assert next(iter(raw)) == "_shape", f.name
        assert raw["_shape"].startswith("ASSUMED SHAPE from https://developers.facebook.com/") and "read 2026-10-28" in raw["_shape"] \
            and raw["_shape"].rstrip(".").find("replace with a recorded response at go-live") > 0, f.name
