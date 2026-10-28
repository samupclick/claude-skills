"""Live Cloudflare Turnstile backend (TURNSTILE_BACKEND=live): every quiz POST's token is checked at siteverify with
TURNSTILE_SECRET_KEY, plain httpx. FR-33 abuse controls, CRUCIBLE A12.

- request: form fields secret, response (the widget token), remoteip (the visitor's IP when known) and idempotency_key
  (a fresh UUID per verification, reused on its retry so a lost reply never burns the single-use token), per
  turnstile/get-started/server-side-validation, read 2026-10-28
- pass only on `"success": true` (and, when TURNSTILE_EXPECTED_HOSTNAME is set, that hostname); tokens are single-use,
  so a replay comes back `timeout-or-duplicate` and fails
- fail closed: a network error, a timeout, a 5xx or a reply that is not JSON is retried once and then fails; nothing
  passes without Cloudflare's yes
- logs one JSON line per failure with the error codes; never the token, never the secret
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any, Callable

import httpx

from adapters.env import require

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
MAX_TOKEN = 2048
RETRY_CODES = frozenset({"internal-error"})
SECRET_CODES = frozenset({"missing-input-secret", "invalid-input-secret"})


def _stderr(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, default=str), file=sys.stderr, flush=True)


class LiveTurnstile:
    def __init__(self, *, secret: str, expected_hostname: str | None = None, transport: httpx.BaseTransport | None = None,
                 timeout: float = 5.0, attempts: int = 2, backoff: float = 0.25,
                 sleep: Callable[[float], None] = time.sleep, log: Callable[..., None] = _stderr):
        self.expected_hostname = expected_hostname or None
        self.attempts, self.backoff = max(1, attempts), backoff
        self._secret = secret
        self._sleep, self._log = sleep, log
        self._http = httpx.Client(transport=transport, timeout=timeout)

    @classmethod
    def from_env(cls, **kw: Any) -> "LiveTurnstile":
        env = require("turnstile (quiz funnel)", "TURNSTILE_SECRET_KEY")
        return cls(secret=env["TURNSTILE_SECRET_KEY"],
                   expected_hostname=os.environ.get("TURNSTILE_EXPECTED_HOSTNAME") or None, **kw)

    def close(self) -> None:
        self._http.close()

    def verify(self, token: str, remote_ip: str | None = None) -> bool:
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN:
            self._log("turnstile_rejected", error_codes=["invalid-input-response"], hostname=None)
            return False
        form = {"secret": self._secret, "response": token, "idempotency_key": str(uuid.uuid4())}
        if remote_ip:
            form["remoteip"] = remote_ip
        reason = "no attempt"
        for attempt in range(self.attempts):
            if attempt:
                self._sleep(self.backoff)
            try:
                res = self._http.post(SITEVERIFY_URL, data=form)
            except httpx.HTTPError as exc:
                reason = type(exc).__name__
                continue
            try:
                body = res.json()
            except ValueError:
                body = None
            if res.status_code >= 500 or not isinstance(body, dict):
                reason = f"http {res.status_code}" + ("" if isinstance(body, dict) else ", not JSON")
                continue
            codes = [str(c) for c in body.get("error-codes") or []]
            if body.get("success") is True:
                if self.expected_hostname and body.get("hostname") != self.expected_hostname:
                    self._log("turnstile_rejected", error_codes=["hostname-mismatch"], hostname=body.get("hostname"))
                    return False
                return True
            if RETRY_CODES & set(codes) and attempt + 1 < self.attempts:
                reason = ",".join(codes)
                continue
            if SECRET_CODES & set(codes):
                self._log("turnstile_misconfigured", variable="TURNSTILE_SECRET_KEY", error_codes=codes)
            else:
                self._log("turnstile_rejected", error_codes=codes, hostname=body.get("hostname"))
            return False
        self._log("turnstile_unavailable", reason=reason, attempts=self.attempts)
        return False
