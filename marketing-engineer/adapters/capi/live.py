"""Live Meta Conversions API backend (CAPI_BACKEND=live): one server event per `send`, POSTed to
https://graph.facebook.com/<META_API_VERSION>/<META_PIXEL_ID>/events with plain httpx. FR-33, DR-4.

- request: form fields `data` (a JSON array holding the one event), `access_token` (META_CAPI_TOKEN, in the body so it
  never appears in a URL or a log line) and `test_event_code` (the caller's, else META_TEST_EVENT_CODE); the shape of
  conversions-api/using-the-api, read 2026-10-28
- reply: `events_received`, `messages`, `fbtrace_id`; anything but one event received raises CapiError
- user_data goes out exactly as the caller built it. The fields Meta requires hashed (em, ph, fn, ln, db, ge, ct, st,
  zp, country) and external_id must already be sha256 hex (adapters.capi.hash_user_field): a plain value is refused
  before any request, so PII never leaves unhashed
- dedup: every event carries its event_id and Meta keeps the first copy per (event_id, event_name), which makes a retry
  safe. Network errors, 5xx, `is_transient` and codes 1, 2, 4, 17, 341, 613 are retried with short waits; any other
  error raises at once with Meta's code and fbtrace_id
- version: META_API_VERSION, default v24.0
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable

import httpx

from adapters.capi import CapiError
from adapters.env import require

DEFAULT_API_VERSION = "v24.0"
GRAPH_HOST = "https://graph.facebook.com"
HASHED_FIELDS = ("em", "ph", "fn", "ln", "db", "ge", "ct", "st", "zp", "country", "external_id")
ACTION_SOURCES = frozenset({"email", "website", "app", "phone_call", "chat", "physical_store", "system_generated",
                            "business_messaging", "other"})
RETRY_CODES = frozenset({1, 2, 4, 17, 341, 613})
MAX_AGE_SECONDS = 7 * 86400
SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def _hashed(value: Any) -> bool:
    values = value if isinstance(value, list) else [value]
    return bool(values) and all(isinstance(v, str) and SHA256_HEX.fullmatch(v) for v in values)


def _json(res: httpx.Response) -> Any:
    try:
        return res.json()
    except ValueError:
        return None


class LiveCapi:
    def __init__(self, *, pixel_id: str, token: str, api_version: str = DEFAULT_API_VERSION,
                 test_event_code: str | None = None, transport: httpx.BaseTransport | None = None,
                 timeout: float = 5.0, attempts: int = 3, backoff: float = 0.5,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.time):
        if not re.fullmatch(r"\d{1,30}", str(pixel_id or "")):
            raise CapiError("META_PIXEL_ID must be the numeric pixel (dataset) id from Events Manager")
        if not re.fullmatch(r"v\d+\.\d+", api_version or ""):
            raise CapiError(f"META_API_VERSION must name a Graph API version such as {DEFAULT_API_VERSION}")
        self.pixel_id, self.api_version = str(pixel_id), api_version
        self.test_event_code = test_event_code or None
        self.attempts, self.backoff = max(1, attempts), backoff
        self._token = token
        self._sleep, self._clock = sleep, clock
        self._http = httpx.Client(base_url=f"{GRAPH_HOST}/{api_version}/", transport=transport, timeout=timeout)

    @classmethod
    def from_env(cls, **kw: Any) -> "LiveCapi":
        env = require("capi (quiz funnel)", "META_PIXEL_ID", "META_CAPI_TOKEN")
        return cls(pixel_id=env["META_PIXEL_ID"], token=env["META_CAPI_TOKEN"],
                   api_version=os.environ.get("META_API_VERSION") or DEFAULT_API_VERSION,
                   test_event_code=os.environ.get("META_TEST_EVENT_CODE") or None, **kw)

    def close(self) -> None:
        self._http.close()

    def send(self, *, event_name, event_id, event_time, event_source_url=None, action_source="website",
             user_data=None, custom_data=None, test_event_code=None) -> dict[str, Any]:
        event = self._event(event_name, event_id, event_time, event_source_url, action_source, user_data or {},
                            custom_data or {})
        form = {"data": json.dumps([event], separators=(",", ":")), "access_token": self._token}
        code = test_event_code or self.test_event_code
        if code:
            form["test_event_code"] = code
        body = self._post(form, event_id)
        if body.get("events_received") != 1:
            raise CapiError(f"Meta CAPI received {body.get('events_received')} of 1 events for {event_id} "
                            f"(fbtrace_id {body.get('fbtrace_id')})", fbtrace_id=body.get("fbtrace_id"))
        return {"events_received": 1, "fbtrace_id": body.get("fbtrace_id"), "event_id": event_id,
                "messages": list(body.get("messages") or [])}

    def _event(self, name: Any, eid: Any, when: Any, url: str | None, source: str, user_data: dict[str, Any],
               custom_data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise CapiError("event_name is required")
        if not isinstance(eid, str) or not eid.strip():
            raise CapiError(f"event_id is required for {name}: the pixel and the server deduplicate on it")
        try:
            when = int(when)
        except (TypeError, ValueError):
            raise CapiError(f"event_time for {eid} must be a Unix timestamp in seconds") from None
        if when < self._clock() - MAX_AGE_SECONDS:
            raise CapiError(f"event_time for {eid} is more than 7 days old; Meta rejects the whole request")
        if source not in ACTION_SOURCES:
            raise CapiError(f"action_source for {eid} must be one of {sorted(ACTION_SOURCES)}")
        if source == "website":
            if not url:
                raise CapiError(f"event_source_url is required for website events ({eid})")
            if not user_data.get("client_user_agent"):
                raise CapiError(f"user_data.client_user_agent is required for website events ({eid})")
        for key in HASHED_FIELDS:
            if key in user_data and not _hashed(user_data[key]):
                raise CapiError(f"user_data.{key} must be lowercase sha256 hex (adapters.capi.hash_user_field); "
                                f"refusing to send {eid}")
        event: dict[str, Any] = {"event_name": name, "event_id": eid, "event_time": when, "action_source": source,
                                 "user_data": dict(user_data)}
        if url:
            event["event_source_url"] = url
        if custom_data:
            event["custom_data"] = dict(custom_data)
        return event

    def _post(self, form: dict[str, str], event_id: str) -> dict[str, Any]:
        last: CapiError | None = None
        for attempt in range(self.attempts):
            if attempt:
                self._sleep(self.backoff * 2 ** (attempt - 1))
            try:
                res = self._http.post(f"{self.pixel_id}/events", data=form)
            except httpx.HTTPError as exc:
                last = CapiError(self._scrub(f"Meta CAPI unreachable for {event_id} ({type(exc).__name__}: {exc})"))
                continue
            body = _json(res)
            if res.status_code == 200 and isinstance(body, dict) and "error" not in body:
                return body
            err = body.get("error") if isinstance(body, dict) else None
            if not isinstance(err, dict):
                last = CapiError(f"Meta CAPI answered {res.status_code} with a body that is not JSON for {event_id}")
                if res.status_code >= 500:
                    continue
                raise last
            code = err.get("code")
            sub = f"/{err['error_subcode']}" if err.get("error_subcode") else ""
            detail = err.get("error_user_msg") or err.get("message") or ""
            last = CapiError(self._scrub(f"Meta CAPI error code {code}{sub} ({err.get('type')}) for {event_id}: {detail} "
                                         f"(fbtrace_id {err.get('fbtrace_id')})"),
                             code=code if isinstance(code, int) else None, fbtrace_id=err.get("fbtrace_id"))
            if res.status_code >= 500 or err.get("is_transient") is True or code in RETRY_CODES:
                continue
            raise last
        assert last is not None
        raise last

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "[META_CAPI_TOKEN]") if self._token else text
