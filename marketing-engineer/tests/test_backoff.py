"""adapters/backoff.py: the bounded retry the live source and image adapters share (429 / 5xx / transport errors)."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from adapters.backoff import header_seconds, send, wait_seconds


def test_header_seconds_reads_numbers_and_http_dates():
    assert header_seconds("7") == 7.0 and header_seconds("0.5") == 0.5 and header_seconds("-3") == 0.0
    later = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=120), usegmt=True)
    assert 100 < header_seconds(later) <= 120
    assert header_seconds(None) is None and header_seconds("soon") is None


def test_reset_header_only_counts_on_a_429_and_every_wait_is_capped():
    assert wait_seconds(httpx.Response(429, headers={"x-ratelimit-reset": "30"}), 1.0, 60.0) == 30.0
    assert wait_seconds(httpx.Response(503, headers={"x-ratelimit-reset": "30"}), 1.0, 60.0) == 1.0
    assert wait_seconds(httpx.Response(503, headers={"retry-after": "900"}), 1.0, 60.0) == 60.0


def test_transport_errors_are_retried_then_raised_and_4xx_is_returned_at_once():
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json={"ok": True})

    sleeps = []
    with httpx.Client(transport=httpx.MockTransport(flaky)) as client:
        assert send(client, "GET", "https://example.invalid/x", sleep=sleeps.append).status_code == 200
    assert sleeps == [1.0, 2.0]

    def down(request):
        raise httpx.ConnectError("refused", request=request)

    with httpx.Client(transport=httpx.MockTransport(down)) as client, pytest.raises(httpx.ConnectError):
        send(client, "GET", "https://example.invalid/x", attempts=2, sleep=lambda s: None)

    seen = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as client:
        assert send(client, "GET", "https://example.invalid/x", on_attempt=lambda: seen.append(1)).status_code == 404
    assert seen == [1], "a 404 is the caller's to judge, never retried"
