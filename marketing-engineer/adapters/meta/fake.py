"""Fake Meta ad account persisted as JSON under DEV_ROOT/meta (shared across processes, file-locked).

- create_* assigns ids; find_by_name mirrors the name lookup the executor does before every create
- effective_status follows the parent chain (ADSET_PAUSED, CAMPAIGN_PAUSED) like the real API
- insights synthesise impressions/clicks/spend/actions per (seed, ad, day) for days on which the ad, its
  ad set and its campaign were all ACTIVE (`active_periods`, closed when status leaves ACTIVE), so the
  loop (T10) gets rows, a kill stops spend, and re-runs get identical numbers
- every call sets last_headers['x-business-use-case-usage']; META_FAKE_THROTTLE_AFTER=<n> raises MetaThrottled
- META_FAKE_FAIL=<step> fails before the step; <step>:after performs it, persists, then fails (a crash after create)
- ads are approved instantly: review_status APPROVED, ad_review_feedback {}; `update("ad", id,
  review_status="DISAPPROVED", ad_review_feedback={...})` is the dev knob that plays Meta's review turning an
  ad down after creation (FR-37 fixtures); the executor only ever reads those two fields back
"""
from __future__ import annotations

import fcntl
import json
import os
import random
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from adapters.meta import MetaApiError, MetaThrottled

KINDS = ("campaign", "adset", "creative", "ad")
ID_BASE = 120_000_000_000_000
EMPTY_STATE: dict[str, Any] = {"objects": {k: {} for k in KINDS}, "next_id": 0, "calls": 0}


class FakeMeta:
    def __init__(self, state_path: Path | None, seed: int = 0):
        self.state_path = state_path
        self.seed = seed
        self.last_headers: dict[str, str] = {}
        self._memory = json.loads(json.dumps(EMPTY_STATE))

    # ---- state -------------------------------------------------------------------------------
    @contextmanager
    def _state(self, step: str) -> Iterator[dict[str, Any]]:
        if self.state_path is None:
            yield self._begin(self._memory, step)
            self._end(self._memory, step)
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path.with_suffix(".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.state_path.read_text()) if self.state_path.exists() else json.loads(json.dumps(EMPTY_STATE))
            try:
                yield self._begin(state, step)
            finally:
                tmp = self.state_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(state))
                os.replace(tmp, self.state_path)
            self._end(state, step)

    def _begin(self, state: dict[str, Any], step: str) -> dict[str, Any]:
        state["calls"] += 1
        pct = min(100, state["calls"])
        self.last_headers = {"x-business-use-case-usage": json.dumps(
            {"act_dev": [{"type": "ads_management", "call_count": pct, "total_cputime": pct, "total_time": pct,
                          "estimated_time_to_regain_access": 0}]})}
        throttle_after = os.environ.get("META_FAKE_THROTTLE_AFTER")
        if throttle_after and state["calls"] > int(throttle_after):
            raise MetaThrottled(f"injected throttle after {throttle_after} calls (META_FAKE_THROTTLE_AFTER)", self.last_headers)
        if os.environ.get("META_FAKE_FAIL", "") == step:
            raise MetaApiError(f"injected failure before {step} (META_FAKE_FAIL={step})")
        return state

    def _end(self, state: dict[str, Any], step: str) -> None:
        if os.environ.get("META_FAKE_FAIL", "") == f"{step}:after":
            raise MetaApiError(f"injected failure after {step} completed (META_FAKE_FAIL={step}:after)")

    def _new(self, state: dict[str, Any], kind: str, name: str, status: str, **fields: Any) -> dict[str, Any]:
        state["next_id"] += 1
        obj = {"id": str(ID_BASE + state["next_id"]), "name": name, "status": status,
               "created_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "activated_on": None, "active_periods": [], **fields}
        if status == "ACTIVE":
            _open_period(obj, date.today())
        state["objects"][kind][obj["id"]] = obj
        return json.loads(json.dumps(obj))

    # ---- writes (executor only) ----------------------------------------------------------------
    def create_campaign(self, name, *, objective, status="PAUSED", daily_budget=None):
        with self._state("create_campaign") as st:
            return self._new(st, "campaign", name, status, objective=objective,
                             daily_budget=None if daily_budget is None else float(daily_budget))

    def create_adset(self, name, *, campaign_id, daily_budget, optimization_event, targeting, status="PAUSED"):
        with self._state("create_adset") as st:
            self._require(st, "campaign", campaign_id)
            return self._new(st, "adset", name, status, campaign_id=campaign_id, daily_budget=float(daily_budget),
                             optimization_event=optimization_event, targeting=targeting)

    def create_creative(self, name, *, image_url, body, title, link_url, page_id=""):
        with self._state("create_creative") as st:
            return self._new(st, "creative", name, "ACTIVE", image_url=image_url, body=body, title=title,
                             link_url=link_url, page_id=page_id)

    def create_ad(self, name, *, adset_id, creative_id, status="PAUSED"):
        with self._state("create_ad") as st:
            self._require(st, "adset", adset_id)
            self._require(st, "creative", creative_id)
            return self._new(st, "ad", name, status, adset_id=adset_id, creative_id=creative_id,
                             review_status="APPROVED", ad_review_feedback={})

    def update(self, kind, object_id, **fields):
        """Fields: status, name, daily_budget; `on=<date>` dates a status change (default today). On an ad,
        `review_status` / `ad_review_feedback` simulate Meta's review outcome (a test fixture, never sent live)."""
        allowed = {"status", "name", "daily_budget", "on"}
        if kind == "ad":
            allowed |= {"review_status", "ad_review_feedback"}
        unknown = set(fields) - allowed
        if unknown:
            raise MetaApiError(f"fake Meta cannot update {sorted(unknown)} on {kind}")
        on = fields.pop("on", None) or date.today()
        if "daily_budget" in fields and fields["daily_budget"] is not None:
            fields["daily_budget"] = float(fields["daily_budget"])
        with self._state("update") as st:
            obj = self._require(st, kind, object_id)
            was_active = obj["status"] == "ACTIVE"
            obj.update(fields)
            if obj["status"] == "ACTIVE" and not was_active:
                _open_period(obj, on)
            elif obj["status"] != "ACTIVE" and was_active:
                obj["active_periods"][-1][1] = on.isoformat()
            return self._view(st, kind, obj)

    # ---- reads -------------------------------------------------------------------------------
    def find_by_name(self, kind, name):
        with self._state("find_by_name") as st:
            for obj in st["objects"][kind].values():
                if obj["name"] == name:
                    return self._view(st, kind, obj)
            return None

    def get(self, kind, object_id):
        with self._state("get") as st:
            return self._view(st, kind, self._require(st, kind, object_id))

    def insights(self, *, level, since, until, ids=None):
        if level not in ("ad", "account"):
            raise MetaApiError(f"fake Meta insights supports level=ad|account, got {level}")
        with self._state("insights") as st:
            rows = [self._row(st, ad, day) for day in _days(since, until)
                    for ad in st["objects"]["ad"].values() if _delivering(st, ad, day) and (ids is None or ad["id"] in ids)]
        rows.sort(key=lambda r: (r["date_start"], r["ad_id"]))
        if level == "account":
            return [{"date_start": d, "date_stop": d, "spend": round(sum(r["spend"] for r in rows if r["date_start"] == d), 2),
                     "impressions": sum(r["impressions"] for r in rows if r["date_start"] == d)}
                    for d in sorted({r["date_start"] for r in rows})]
        return rows

    def account_spend_today(self, on=None):
        on = on or date.today()
        return round(sum(r["spend"] for r in self.insights(level="ad", since=on, until=on)), 2)

    # ---- helpers -----------------------------------------------------------------------------
    @staticmethod
    def _require(state, kind, object_id):
        if kind not in KINDS:
            raise MetaApiError(f"unknown object kind {kind!r}")
        obj = state["objects"][kind].get(object_id)
        if obj is None:
            raise MetaApiError(f"{kind} {object_id} does not exist")
        return obj

    @staticmethod
    def _view(state, kind, obj):
        view = json.loads(json.dumps(obj))
        view["effective_status"] = _effective_status(state, kind, obj)
        return view

    def _row(self, state, ad, day):
        adset = state["objects"]["adset"][ad["adset_id"]]
        rng = random.Random(f"{self.seed}:{ad['id']}:{day.isoformat()}")
        budget = adset.get("daily_budget") or 10.0
        spend = round(budget * rng.uniform(0.6, 1.0), 2)
        cpm = rng.uniform(18, 32)
        impressions = int(spend / cpm * 1000)
        reach = int(impressions * rng.uniform(0.7, 0.95))
        clicks = int(impressions * rng.uniform(0.012, 0.03))
        link_clicks = int(clicks * rng.uniform(0.6, 0.9))
        quiz_starts = int(link_clicks * rng.uniform(0.4, 0.7))
        quiz_completes = int(quiz_starts * rng.uniform(0.6, 0.9))
        schedules = int(quiz_completes * rng.uniform(0.05, 0.25))
        return {"date_start": day.isoformat(), "date_stop": day.isoformat(), "ad_id": ad["id"], "ad_name": ad["name"],
                "adset_id": adset["id"], "campaign_id": adset["campaign_id"], "impressions": impressions, "reach": reach,
                "clicks": clicks, "link_clicks": link_clicks, "spend": spend,
                "frequency": round(impressions / reach, 3) if reach else None,
                "actions": [{"action_type": "QuizStart", "value": quiz_starts},
                            {"action_type": "QuizComplete", "value": quiz_completes},
                            {"action_type": "Schedule", "value": schedules}]}


def _effective_status(state, kind, obj):
    if obj["status"] != "ACTIVE":
        return obj["status"]
    if kind == "ad":
        adset = state["objects"]["adset"][obj["adset_id"]]
        if adset["status"] != "ACTIVE":
            return "ADSET_PAUSED"
        obj = adset
        kind = "adset"
    if kind == "adset" and state["objects"]["campaign"][obj["campaign_id"]]["status"] != "ACTIVE":
        return "CAMPAIGN_PAUSED"
    return "ACTIVE"


def _open_period(obj, on):
    obj["active_periods"].append([on.isoformat(), None])
    obj["activated_on"] = obj["activated_on"] or on.isoformat()


def _active_on(obj, day):
    return any(date.fromisoformat(start) <= day and (end is None or day < date.fromisoformat(end))
               for start, end in obj.get("active_periods", []))


def _delivering(state, ad, day):
    adset = state["objects"]["adset"][ad["adset_id"]]
    campaign = state["objects"]["campaign"][adset["campaign_id"]]
    return _active_on(ad, day) and _active_on(adset, day) and _active_on(campaign, day)


def _days(since, until):
    d = since
    while d <= until:
        yield d
        d += timedelta(days=1)
