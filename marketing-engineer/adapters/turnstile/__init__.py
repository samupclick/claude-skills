"""Cloudflare Turnstile verification. TURNSTILE_BACKEND=pass|live. Rate limits are enforced elsewhere."""
from __future__ import annotations

from typing import Protocol

from adapters.env import choose_backend, not_built


class Turnstile(Protocol):
    def verify(self, token: str, remote_ip: str | None = None) -> bool: ...


class PassTurnstile:
    def verify(self, token: str, remote_ip: str | None = None) -> bool:
        return True


def get_turnstile() -> Turnstile:
    return choose_backend("TURNSTILE_BACKEND", {
        "pass": PassTurnstile,
        "live": not_built("TURNSTILE_BACKEND", "live", "T13"),
    })
