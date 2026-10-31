"""Retry with backoff for the live HTTP adapters (FR-8 retry discipline, polite sources).

`send` retries 429 and 5xx answers and transport errors a bounded number of times, honouring `Retry-After` and
Reddit's `X-Ratelimit-Reset`, and returns the last response for the caller to judge. Read-only sources, image
generation and Supabase Storage (idempotent upserts) use it; nothing here ever writes to a vendor on its own. The Meta,
CAPI and Turnstile adapters keep their own loops because they decide on error codes inside the body (and Meta never
re-sends a write).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import httpx

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def header_seconds(value: str | None) -> float | None:
    """Seconds from a `Retry-After` / `X-Ratelimit-Reset` value: a number, or an HTTP date."""
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max((when - datetime.now(timezone.utc)).total_seconds(), 0.0)


def wait_seconds(response: httpx.Response, fallback: float, cap: float) -> float:
    """How long to wait before retrying `response`: Retry-After, else (on a 429) X-Ratelimit-Reset, else `fallback`;
    capped at `cap`."""
    names = ("retry-after", "x-ratelimit-reset") if response.status_code == 429 else ("retry-after",)
    for name in names:
        seconds = header_seconds(response.headers.get(name))
        if seconds is not None:
            return min(seconds, cap)
    return min(fallback, cap)


def send(client: httpx.Client, method: str, url: str, *, attempts: int = 3, base_delay: float = 1.0,
         max_delay: float = 60.0, sleep: Callable[[float], None] = time.sleep,
         on_attempt: Callable[[], None] | None = None, **kwargs: Any) -> httpx.Response:
    """`client.request(method, url, **kwargs)` up to `attempts` times. A transport error on the last try propagates."""
    for attempt in range(1, attempts + 1):
        if on_attempt is not None:
            on_attempt()
        fallback = base_delay * 2 ** (attempt - 1)
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt == attempts:
                raise
            sleep(min(fallback, max_delay))
            continue
        if response.status_code not in RETRY_STATUSES or attempt == attempts:
            return response
        sleep(wait_seconds(response, fallback, max_delay))
    raise AssertionError("unreachable")
