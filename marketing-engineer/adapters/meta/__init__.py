"""Meta Marketing API behind one interface. META_BACKEND=fake|live.

Only scripts/apply_actions.py may call a create/update; workers read (get, find_by_name, insights).
Objects are plain dicts with Meta-like fields: id, name, status, effective_status, ad_review_feedback.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Protocol

from adapters.env import choose_backend, dev_root, not_built


class MetaApiError(RuntimeError):
    """A Meta call failed (in dev: injected via META_FAKE_FAIL=<step>[:after])."""


class MetaThrottled(MetaApiError):
    """Rate limited; `headers` carries x-business-use-case-usage like the real API."""

    def __init__(self, message: str, headers: dict[str, str]):
        super().__init__(message)
        self.headers = headers


class MetaAds(Protocol):
    last_headers: dict[str, str]

    def create_campaign(self, name: str, *, objective: str, status: str = "PAUSED",
                        daily_budget: float | None = None) -> dict[str, Any]: ...
    def create_adset(self, name: str, *, campaign_id: str, daily_budget: float, optimization_event: str,
                     targeting: dict[str, Any], status: str = "PAUSED") -> dict[str, Any]: ...
    def create_creative(self, name: str, *, image_url: str, body: str, title: str, link_url: str,
                        page_id: str = "") -> dict[str, Any]: ...
    def create_ad(self, name: str, *, adset_id: str, creative_id: str, status: str = "PAUSED") -> dict[str, Any]: ...
    def find_by_name(self, kind: str, name: str) -> dict[str, Any] | None: ...
    def get(self, kind: str, object_id: str) -> dict[str, Any]: ...
    def update(self, kind: str, object_id: str, **fields: Any) -> dict[str, Any]: ...
    def insights(self, *, level: str, since: date, until: date, ids: list[str] | None = None) -> list[dict[str, Any]]: ...
    def account_spend_today(self, on: date | None = None) -> float: ...


def get_meta() -> MetaAds:
    from adapters.meta.fake import FakeMeta

    return choose_backend("META_BACKEND", {
        "fake": lambda: FakeMeta(dev_root() / "meta" / "account.json", seed=int(os.environ.get("META_FAKE_SEED") or 0)),
        "live": not_built("META_BACKEND", "live", "T13"),
    })
