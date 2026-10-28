"""Meta Marketing API behind one interface. META_BACKEND=fake|live. FR-30, FR-31, FR-37, FR-38, NFR-1, NFR-4.

Only scripts/apply_actions.py may call a create/update, and only it asks for `get_meta(write=True)`; workers read
(get, find_by_name, insights). The live backend holds the executor's META_ACCESS_TOKEN in write mode and a worker's
META_READ_TOKEN otherwise, and refuses every write in read mode; the fake ignores `write` (tests build accounts
through it). Objects are plain dicts with Meta-like fields: id, name, status, effective_status, ad_review_feedback,
and on ads `review_status` (the warehouse's enum, see `review_status()`). Budgets are currency units on this side of
the interface; the live backend converts to Meta's minor units.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Protocol

from adapters.env import choose_backend, dev_root

REVIEW_STATUSES = ("PENDING", "APPROVED", "DISAPPROVED", "WITH_ISSUES")


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


def review_status(effective_status: str | None, ad_review_feedback: Any) -> str | None:
    """FR-37: `ad_entities.review_status` from Meta's `effective_status` and `ad_review_feedback`. Global feedback is a
    disapproval, placement-specific feedback an issue. None when Meta's answer says nothing about review (a paused or
    archived ad without feedback): the caller keeps the status it had."""
    feedback = ad_review_feedback if isinstance(ad_review_feedback, dict) else {}
    if effective_status == "DISAPPROVED" or feedback.get("global"):
        return "DISAPPROVED"
    if effective_status == "WITH_ISSUES" or feedback.get("placement_specific"):
        return "WITH_ISSUES"
    if effective_status in ("PENDING_REVIEW", "IN_PROCESS"):
        return "PENDING"
    if effective_status in ("ACTIVE", "PREAPPROVED"):
        return "APPROVED"
    return None


def get_meta(*, write: bool = False) -> MetaAds:
    from adapters.meta.fake import FakeMeta

    def live() -> MetaAds:
        from adapters.meta.live import LiveMeta

        return LiveMeta.from_env(write=write)

    return choose_backend("META_BACKEND", {
        "fake": lambda: FakeMeta(dev_root() / "meta" / "account.json", seed=int(os.environ.get("META_FAKE_SEED") or 0)),
        "live": live,
    })
