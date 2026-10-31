"""Contract tests for adapters/turnstile/live.py (TURNSTILE_BACKEND=live) against httpx.MockTransport serving
fixtures/turnstile/*.json, copied from Cloudflare's siteverify documentation (ASSUMED until a recorded response replaces
each at go-live). No call leaves the process. Covers the request contract (secret, response, remoteip,
idempotency_key), single-use tokens, retries that reuse the idempotency key, and failing closed. FR-33 abuse controls,
CRUCIBLE A12."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from adapters.env import MissingEnvVar
from adapters.turnstile import PassTurnstile, get_turnstile
from adapters.turnstile.live import SITEVERIFY_URL, LiveTurnstile

ME_DIR = Path(__file__).resolve().parent.parent
FIX = ME_DIR / "fixtures" / "turnstile"
SECRET = "0x4AAAA-turnstile-secret-never-printed"
TOKEN = "0.turnstile-token-from-the-widget"


def fixture(name: str) -> dict:
    raw = json.loads((FIX / f"{name}.json").read_text())
    assert raw.pop("_shape").startswith("ASSUMED SHAPE from https://developers.cloudflare.com/turnstile/")
    return raw


class Siteverify:
    """siteverify as a stub: replies in order (the last repeats), each a fixture name, an httpx.Response, or an
    exception to raise."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        spec = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(spec, Exception):
            raise spec
        if isinstance(spec, httpx.Response):
            return spec
        return httpx.Response(200, json=fixture(spec) if isinstance(spec, str) else spec)

    def forms(self) -> list[dict[str, str]]:
        return [{k: v[0] for k, v in parse_qs(r.content.decode()).items()} for r in self.requests]


@pytest.fixture
def logs():
    return []


def live(stub, logs, **kw) -> LiveTurnstile:
    return LiveTurnstile(secret=SECRET, transport=httpx.MockTransport(stub), sleep=lambda s: None,
                         log=lambda event, **f: logs.append({"event": event, **f}), **kw)


def test_verify_posts_secret_token_ip_and_an_idempotency_key(logs):
    stub = Siteverify("success")
    assert live(stub, logs).verify(TOKEN, remote_ip="203.0.113.7") is True
    [req] = stub.requests
    assert req.method == "POST" and str(req.url) == SITEVERIFY_URL == "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    assert req.headers["content-type"] == "application/x-www-form-urlencoded"
    [form] = stub.forms()
    assert form["secret"] == SECRET and form["response"] == TOKEN and form["remoteip"] == "203.0.113.7"
    assert uuid.UUID(form["idempotency_key"]).version == 4
    assert logs == []


def test_each_verification_gets_its_own_key_and_remote_ip_is_optional(logs):
    stub = Siteverify("success")
    t = live(stub, logs)
    assert t.verify(TOKEN) and t.verify(TOKEN + "2", remote_ip="2001:db8::1")
    first, second = stub.forms()
    assert "remoteip" not in first and second["remoteip"] == "2001:db8::1"
    assert first["idempotency_key"] != second["idempotency_key"]


@pytest.mark.parametrize("reply", ["invalid_response", "timeout_or_duplicate"])
def test_rejected_and_replayed_tokens_fail_without_a_retry(reply, logs):
    stub = Siteverify(reply)
    assert live(stub, logs).verify(TOKEN, remote_ip="203.0.113.7") is False
    assert len(stub.requests) == 1
    assert logs == [{"event": "turnstile_rejected", "error_codes": fixture(reply)["error-codes"], "hostname": None}]
    assert SECRET not in json.dumps(logs) and TOKEN not in json.dumps(logs)


def test_a_bad_secret_fails_closed_and_names_the_variable(logs):
    stub = Siteverify("invalid_secret")
    assert live(stub, logs).verify(TOKEN) is False
    assert logs[0]["event"] == "turnstile_misconfigured" and logs[0]["variable"] == "TURNSTILE_SECRET_KEY"
    assert SECRET not in json.dumps(logs)


def test_internal_error_is_retried_with_the_same_idempotency_key(logs):
    stub = Siteverify("internal_error", "success")
    assert live(stub, logs).verify(TOKEN) is True
    keys = [f["idempotency_key"] for f in stub.forms()]
    assert len(keys) == 2 and keys[0] == keys[1]


@pytest.mark.parametrize("failure", [
    httpx.ConnectError(f"cannot reach siteverify with {SECRET}"),
    httpx.ReadTimeout("siteverify timed out"),
    httpx.Response(502, text="bad gateway"),
    httpx.Response(200, text="<html>not json</html>"),
])
def test_network_trouble_fails_closed(failure, logs):
    stub = Siteverify(failure)
    assert live(stub, logs).verify(TOKEN, remote_ip="203.0.113.7") is False
    assert len(stub.requests) == 2   # one retry with the same key, then closed
    assert len({f["idempotency_key"] for f in stub.forms()}) == 1
    assert logs[-1]["event"] == "turnstile_unavailable" and SECRET not in json.dumps(logs)


def test_success_must_be_literally_true(logs):
    stub = Siteverify({"success": "true", "error-codes": []})
    assert live(stub, logs).verify(TOKEN) is False


@pytest.mark.parametrize("token", ["", None, "x" * 2049])
def test_empty_or_oversized_tokens_never_reach_cloudflare(token, logs):
    stub = Siteverify("success")
    assert live(stub, logs).verify(token) is False
    assert stub.requests == []


def test_expected_hostname_is_checked_when_configured(logs):
    assert live(Siteverify("success"), logs, expected_hostname="go.upclicklabs.com").verify(TOKEN) is True
    assert live(Siteverify("success"), logs, expected_hostname="quiz.example.com").verify(TOKEN) is False
    assert logs[-1] == {"event": "turnstile_rejected", "error_codes": ["hostname-mismatch"], "hostname": "go.upclicklabs.com"}


def test_from_env_and_the_selector(monkeypatch):
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    monkeypatch.setenv("TURNSTILE_BACKEND", "live")
    with pytest.raises(MissingEnvVar, match="TURNSTILE_SECRET_KEY"):
        get_turnstile()
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", SECRET)
    monkeypatch.setenv("TURNSTILE_EXPECTED_HOSTNAME", "go.upclicklabs.com")
    t = get_turnstile()
    assert isinstance(t, LiveTurnstile) and t.expected_hostname == "go.upclicklabs.com"
    monkeypatch.setenv("TURNSTILE_BACKEND", "pass")
    assert isinstance(get_turnstile(), PassTurnstile)
