"""Meta Conversions API. CAPI_BACKEND=fake|live. `send(...)` per event, `event_id` for pixel dedup."""
from __future__ import annotations

import hashlib
from typing import Any, Protocol

from adapters.env import choose_backend, dev_root, not_built


class Capi(Protocol):
    def send(self, *, event_name: str, event_id: str, event_time: int, event_source_url: str | None = None,
             action_source: str = "website", user_data: dict[str, Any] | None = None,
             custom_data: dict[str, Any] | None = None, test_event_code: str | None = None) -> dict[str, Any]: ...


def hash_user_field(value: str) -> str:
    """Meta's user_data normalisation: trim, lowercase, sha256 hex."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def get_capi() -> Capi:
    from adapters.capi.fake import FakeCapi

    return choose_backend("CAPI_BACKEND", {
        "fake": lambda: FakeCapi(dev_root() / "capi.jsonl"),
        "live": not_built("CAPI_BACKEND", "live", "T13"),
    })
