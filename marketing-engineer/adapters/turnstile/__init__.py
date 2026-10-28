"""Cloudflare Turnstile verification. TURNSTILE_BACKEND=pass|live. Rate limits are enforced elsewhere (funnel/app.py)."""
from __future__ import annotations

from typing import Protocol

from adapters.env import choose_backend


class Turnstile(Protocol):
    def verify(self, token: str, remote_ip: str | None = None) -> bool: ...


class PassTurnstile:
    def verify(self, token: str, remote_ip: str | None = None) -> bool:
        return True


def get_turnstile() -> Turnstile:
    def live() -> Turnstile:
        from adapters.turnstile.live import LiveTurnstile

        return LiveTurnstile.from_env()

    return choose_backend("TURNSTILE_BACKEND", {"pass": PassTurnstile, "live": live})
