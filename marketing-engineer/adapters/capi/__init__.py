"""Meta Conversions API. CAPI_BACKEND=fake|live. `send(...)` per event, `event_id` for pixel dedup. FR-33, DR-4."""
from __future__ import annotations

import hashlib
from typing import Any, Protocol

from adapters.env import choose_backend, dev_root


class CapiError(RuntimeError):
    """A server event was not accepted. Names Meta's code and fbtrace_id, never a token or a user_data value."""

    def __init__(self, message: str, *, code: int | None = None, fbtrace_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.fbtrace_id = fbtrace_id


class Capi(Protocol):
    def send(self, *, event_name: str, event_id: str, event_time: int, event_source_url: str | None = None,
             action_source: str = "website", user_data: dict[str, Any] | None = None,
             custom_data: dict[str, Any] | None = None, test_event_code: str | None = None) -> dict[str, Any]: ...


def hash_user_field(value: str) -> str:
    """Meta's user_data normalisation: trim, lowercase, sha256 hex."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def get_capi() -> Capi:
    def fake() -> Capi:
        from adapters.capi.fake import FakeCapi

        return FakeCapi(dev_root() / "capi.jsonl")

    def live() -> Capi:
        from adapters.capi.live import LiveCapi

        return LiveCapi.from_env()

    return choose_backend("CAPI_BACKEND", {"fake": fake, "live": live})
