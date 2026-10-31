"""Contract tests for adapters/capi/live.py (CAPI_BACKEND=live) against httpx.MockTransport serving fixtures/capi/*.json,
whose shapes are copied from Meta's documentation (ASSUMED until a recorded response replaces each at go-live). No call
leaves the process. Covers the request contract (endpoint, form fields, test_event_code, event_id), hashed user_data
passing through untouched, retries that lean on Meta's event_id dedup, and errors that name variables, never values.
FR-33, DR-4."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from adapters.capi import CapiError, get_capi, hash_user_field
from adapters.capi.live import DEFAULT_API_VERSION, LiveCapi
from adapters.meta.live import DEFAULT_API_VERSION as META_DEFAULT_API_VERSION
from adapters.env import MissingEnvVar

ME_DIR = Path(__file__).resolve().parent.parent
FIX = ME_DIR / "fixtures" / "capi"
TOKEN = "EAAC-capi-token-never-printed"
PIXEL = "123456789012345"
NOW = 1_800_000_000
EMAIL_HASH = hash_user_field("Person@Example.com")
EVENT = dict(
    event_name="QuizComplete", event_id="lead-1:QuizComplete", event_time=NOW - 5,
    event_source_url="https://go.upclicklabs.com/quiz", action_source="website",
    user_data={"external_id": [hash_user_field("lead-1")], "em": [EMAIL_HASH], "client_ip_address": "203.0.113.7",
               "client_user_agent": "Mozilla/5.0", "fbc": "fb.1.1800000000000.IwAR0abc"},
    custom_data={"utm_content": "c1", "quiz_version": "v1"},
)


def fixture(name: str) -> tuple[int, dict]:
    raw = json.loads((FIX / f"{name}.json").read_text())
    assert raw.pop("_shape").startswith("ASSUMED SHAPE from https://developers.facebook.com/")
    return raw.pop("_status", 200), raw


class Graph:
    """The /events edge as a stub: replies in order (the last repeats), each a fixture name or an exception to raise."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        spec = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(spec, Exception):
            raise spec
        status, body = fixture(spec) if isinstance(spec, str) else (200, spec)
        return httpx.Response(status, json=body)


def form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode(), keep_blank_values=True).items()}


@pytest.fixture
def sleeps():
    return []


def live(graph, sleeps, **kw) -> LiveCapi:
    return LiveCapi(pixel_id=PIXEL, token=TOKEN, transport=httpx.MockTransport(graph), sleep=sleeps.append,
                    clock=lambda: NOW, **kw)


def test_send_posts_one_event_to_the_pixel_events_edge(sleeps):
    graph = Graph("events_received")
    res = live(graph, sleeps).send(**EVENT, test_event_code="TEST123")
    assert res == {"events_received": 1, "fbtrace_id": "AbCdEfGhIjKlMnOp123", "event_id": "lead-1:QuizComplete", "messages": []}
    [req] = graph.requests
    assert req.method == "POST" and str(req.url) == f"https://graph.facebook.com/{DEFAULT_API_VERSION}/{PIXEL}/events"
    assert TOKEN not in str(req.url) and req.headers["content-type"] == "application/x-www-form-urlencoded"
    body = form(req)
    assert body["access_token"] == TOKEN and body["test_event_code"] == "TEST123"
    [event] = json.loads(body["data"])
    assert event == {**{k: EVENT[k] for k in ("event_name", "event_id", "event_time", "event_source_url", "action_source",
                                               "user_data", "custom_data")}}
    assert event["user_data"]["em"] == [hash_user_field("person@example.com")]   # the caller's hash, not hashed again
    assert event["user_data"]["fbc"] == "fb.1.1800000000000.IwAR0abc" and event["user_data"]["client_ip_address"] == "203.0.113.7"
    assert sleeps == []


def test_default_version_is_the_shared_graph_version_and_meta_api_version_overrides(monkeypatch, sleeps):
    # one META_API_VERSION default for the Marketing API and CAPI adapters (adapters/graph.py)
    assert DEFAULT_API_VERSION == META_DEFAULT_API_VERSION == "v26.0"
    graph = Graph("events_received")
    monkeypatch.setenv("META_PIXEL_ID", PIXEL)
    monkeypatch.setenv("META_CAPI_TOKEN", TOKEN)
    monkeypatch.setenv("META_API_VERSION", "v25.0")
    monkeypatch.delenv("META_TEST_EVENT_CODE", raising=False)
    LiveCapi.from_env(transport=httpx.MockTransport(graph), clock=lambda: NOW).send(**EVENT)
    assert graph.requests[0].url.path == f"/v25.0/{PIXEL}/events"
    assert "test_event_code" not in form(graph.requests[0])
    monkeypatch.setenv("META_API_VERSION", "latest")
    with pytest.raises(CapiError, match="META_API_VERSION"):
        LiveCapi.from_env(transport=httpx.MockTransport(graph))


def test_test_event_code_comes_from_meta_test_event_code_when_the_caller_passes_none(monkeypatch):
    graph = Graph("events_received")
    monkeypatch.setenv("META_PIXEL_ID", PIXEL)
    monkeypatch.setenv("META_CAPI_TOKEN", TOKEN)
    monkeypatch.setenv("META_TEST_EVENT_CODE", "TEST999")
    monkeypatch.delenv("META_API_VERSION", raising=False)
    capi = LiveCapi.from_env(transport=httpx.MockTransport(graph), clock=lambda: NOW)
    capi.send(**EVENT)
    capi.send(**EVENT, test_event_code="TEST123")
    assert [form(r)["test_event_code"] for r in graph.requests] == ["TEST999", "TEST123"]
    assert graph.requests[0].url.path == f"/{DEFAULT_API_VERSION}/{PIXEL}/events"


def test_missing_variables_are_named_never_their_values(monkeypatch):
    monkeypatch.setenv("META_CAPI_TOKEN", TOKEN)
    monkeypatch.delenv("META_PIXEL_ID", raising=False)
    with pytest.raises(MissingEnvVar) as exc:
        LiveCapi.from_env()
    assert "META_PIXEL_ID" in str(exc.value) and TOKEN not in str(exc.value)
    monkeypatch.delenv("META_CAPI_TOKEN")
    with pytest.raises(MissingEnvVar, match="META_PIXEL_ID, META_CAPI_TOKEN"):
        LiveCapi.from_env()
    with pytest.raises(CapiError, match="META_PIXEL_ID") as exc:
        LiveCapi(pixel_id="../act_1/ads", token=TOKEN)
    assert "act_1" not in str(exc.value)


def test_capi_backend_live_is_wired_in_the_selector(monkeypatch):
    monkeypatch.setenv("CAPI_BACKEND", "live")
    monkeypatch.setenv("META_PIXEL_ID", PIXEL)
    monkeypatch.setenv("META_CAPI_TOKEN", TOKEN)
    assert isinstance(get_capi(), LiveCapi)


@pytest.mark.parametrize("field", ["em", "ph", "fn", "ln", "ct", "zp", "country", "external_id"])
def test_unhashed_customer_information_is_refused_before_any_request(field, sleeps):
    graph = Graph("events_received")
    plain = "Person@Example.com"
    with pytest.raises(CapiError, match=f"user_data.{field}") as exc:
        live(graph, sleeps).send(**{**EVENT, "user_data": {**EVENT["user_data"], field: [plain]}})
    assert plain not in str(exc.value) and plain.lower() not in str(exc.value)
    with pytest.raises(CapiError, match=f"user_data.{field}"):
        live(graph, sleeps).send(**{**EVENT, "user_data": {**EVENT["user_data"], field: EMAIL_HASH.upper()}})
    assert graph.requests == []


@pytest.mark.parametrize("change, named", [
    ({"event_id": ""}, "event_id"),
    ({"event_name": ""}, "event_name"),
    ({"event_time": NOW - 8 * 86400}, "event_time"),
    ({"action_source": "carrier_pigeon"}, "action_source"),
    ({"event_source_url": None}, "event_source_url"),
    ({"user_data": {k: v for k, v in EVENT["user_data"].items() if k != "client_user_agent"}}, "client_user_agent"),
])
def test_events_meta_would_reject_are_refused_locally(change, named, sleeps):
    graph = Graph("events_received")
    with pytest.raises(CapiError, match=named):
        live(graph, sleeps).send(**{**EVENT, **change})
    assert graph.requests == []


def test_system_generated_events_need_no_browser_fields(sleeps):
    graph = Graph("events_received")
    live(graph, sleeps).send(event_name="Schedule", event_id="lead-1:Schedule", event_time=NOW, action_source="system_generated",
                             user_data={"external_id": [hash_user_field("lead-1")]}, custom_data={"utm_content": "c1"})
    [event] = json.loads(form(graph.requests[0])["data"])
    assert event["action_source"] == "system_generated" and "event_source_url" not in event


def test_meta_errors_raise_with_code_and_trace_and_are_not_retried(sleeps):
    graph = Graph("error_invalid_token")
    with pytest.raises(CapiError) as exc:
        live(graph, sleeps).send(**EVENT)
    msg = str(exc.value)
    assert "190" in msg and "QrStUvWxYz0123456" in msg and "lead-1:QuizComplete" in msg and TOKEN not in msg
    assert exc.value.code == 190 and exc.value.fbtrace_id == "QrStUvWxYz0123456"
    assert len(graph.requests) == 1 and sleeps == []
    graph = Graph("error_invalid_parameter")
    with pytest.raises(CapiError, match="code 100.*The event is missing a required parameter"):
        live(graph, sleeps).send(**EVENT)
    assert len(graph.requests) == 1


def test_transient_errors_are_retried_with_the_same_event_id(sleeps):
    graph = Graph("error_transient", "events_received")
    res = live(graph, sleeps).send(**EVENT)
    assert res["events_received"] == 1 and len(graph.requests) == 2 and sleeps == [0.5]
    ids = [json.loads(form(r)["data"])[0]["event_id"] for r in graph.requests]
    assert ids == ["lead-1:QuizComplete", "lead-1:QuizComplete"]   # Meta keeps the first copy per (event_id, event_name)


def test_network_errors_retry_then_raise_without_the_token(sleeps):
    graph = Graph(httpx.ConnectError(f"connect failed for access_token={TOKEN}"))
    with pytest.raises(CapiError) as exc:
        live(graph, sleeps).send(**EVENT)
    assert TOKEN not in str(exc.value) and "ConnectError" in str(exc.value)
    assert len(graph.requests) == 3 and sleeps == [0.5, 1.0]


def test_a_reply_that_did_not_receive_the_event_is_an_error(sleeps):
    graph = Graph({"events_received": 0, "messages": ["dropped"], "fbtrace_id": "Zero123"})
    with pytest.raises(CapiError, match="received 0 of 1.*Zero123"):
        live(graph, sleeps).send(**EVENT)
    html = LiveCapi(pixel_id=PIXEL, token=TOKEN, clock=lambda: NOW, sleep=sleeps.append,
                    transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>gateway</html>")))
    with pytest.raises(CapiError, match="not JSON"):
        html.send(**EVENT)
