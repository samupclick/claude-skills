#!/usr/bin/env python3
"""The executor (T8): the only process that performs a side effect. SKILL.md §6, FR-44 to FR-47.

    scripts/apply_actions.py [--client upclicklabs] [--reconcile] [--role executor|sam_admin] [--stale-minutes 15]

For every `actions` row in `approved` (or `proposed` whose type is at execute trust per `trust_streaks`):
one locked transaction re-checks the brakes, evaluates `check_daily_cap()` with the proposal's budgets
applied, applies the rate limits to autonomous rows, and commits `status='applying'` with this run's id
before any external call. The Meta call follows, the object is read back, the warehouse row is mirrored
from what Meta returned, and only then the action is `applied`. Any exception marks it `failed` with
`last_error` (after a best-effort read-back so the warehouse still mirrors Meta); three consecutive
failures of one type propose `set_pause_flag`. `--reconcile` settles `applying` rows older than
`--stale-minutes` by reading Meta, never by re-sending.

Roles: `executor` (WAREHOUSE_URL_EXECUTOR) applies pause / kill / activate / scale (build_campaign lands
in T9). `set_pause_flag`, `promote_trust`, `quote_release` are Sam-only by trigger; Sam runs this script
with `--role sam_admin` for those and it never touches Meta in that mode. The service role is never used.

Concurrency (CRUCIBLE A14): a session advisory lock serialises whole runs; each action additionally takes
`pg_advisory_xact_lock(hashtext('executor'))` and `select … for update skip locked`, so two executors
started together apply each action exactly once. Any `applying` row blocks the normal pass (SKILL.md §7).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from psycopg.types.json import Jsonb  # noqa: E402

from adapters.meta import MetaAds, MetaApiError, get_meta  # noqa: E402
from warehouse.client import client_by_slug, connect, format_where_are_we, insert, run, where_are_we  # noqa: E402

WORKER = "executor"
LOCK_KEY = "executor"
STALE_MINUTES = 15
EXECUTOR_TYPES = ("pause", "kill", "activate", "scale", "build_campaign")
ADMIN_TYPES = ("set_pause_flag", "promote_trust", "quote_release")
BUDGET_TYPES = ("build_campaign", "activate", "scale")   # SKILL.md §6 step 3
DESIRED_STATUS = {"pause": "PAUSED", "kill": "ARCHIVED", "activate": "ACTIVE"}
AD_STATUSES = ("PAUSED", "ACTIVE", "ARCHIVED", "DELETED")
CAMPAIGN_STATUSES = ("PAUSED", "ACTIVE", "ARCHIVED")
REVIEW_STATUSES = ("PENDING", "APPROVED", "DISAPPROVED", "WITH_ISSUES")
MAX_BUDGET_STEP = Decimal("0.20")                          # FR-31: budget changes in ≤20% steps
TRUTHY = ("1", "true", "yes", "on")


class ConfigError(RuntimeError):
    """clients.config lacks a key the executor refuses to run without (SKILL.md §0 step 1)."""


class Blocked(RuntimeError):
    """An `applying` row exists; only `--reconcile` may touch it (SKILL.md §7)."""


class Skip(Exception):
    """Leave the row exactly as it is; the reason goes to stdout and the run counts."""

    def __init__(self, reason: str, counter: str = "skipped"):
        super().__init__(reason)
        self.reason, self.counter = reason, counter


class Fail(Exception):
    """Mark the row `failed` with this `last_error` before any external call is made."""

    def __init__(self, last_error: str):
        super().__init__(last_error)
        self.last_error = last_error


def env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in TRUTHY


def check_config(client: dict[str, Any]) -> None:
    cfg = client.get("config") or {}
    targets = cfg.get("targets") or {}
    missing = [k for k, v in (("targets.ctr_floor", targets.get("ctr_floor")),
                              ("targets.kill_impressions", targets.get("kill_impressions")),
                              ("daily_cap", client.get("daily_cap")), ("currency", client.get("currency"))) if v is None]
    if missing:
        raise ConfigError(f"clients.config for {client['slug']!r} is missing {', '.join(missing)}; refusing to run")


def as_uuid(value: str) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise Fail(f"target_id {value!r} is not a uuid") from None


def ensure_object(meta: MetaAds, kind: str, name: str, create) -> tuple[dict[str, Any], bool]:
    """Name lookup before every Meta create (SKILL.md §6 step 6): returns (object, created). A crash after a
    previous create leaves an object with this name; the re-run finds and reuses it instead of a duplicate.
    `create` is a zero-argument callable that performs the create. The caller writes the external id to
    the warehouse immediately after this returns."""
    found = meta.find_by_name(kind, name)
    if found is not None:
        return found, False
    return create(), True


class Executor:
    def __init__(self, conn, client: dict[str, Any], role: str, run_, meta: MetaAds | None, stale_minutes: int):
        self.conn, self.client, self.role, self.run, self.meta = conn, client, role, run_, meta
        self.client_id = client["id"]
        self.cfg = client.get("config") or {}
        self.limits = self.cfg.get("rate_limits") or {}
        self.stale_minutes = stale_minutes
        self.spend_tripped = False
        self.types = ADMIN_TYPES if role == "sam_admin" else EXECUTOR_TYPES

    # ---------- passes ----------

    def reconcile(self) -> None:
        """§6 step 8: `applying` rows whose executor run started more than `stale_minutes` ago are compared
        against Meta (or the warehouse for admin types) and set to applied or failed. Never re-sent."""
        rows = self.conn.execute(
            "select a.id from actions a left join runs r on r.id = a.executor_run_id"
            " where a.client_id=%s and a.status='applying'"
            "   and coalesce(r.started_at, a.created_at) < now() - make_interval(mins => %s)"
            " order by a.created_at, a.id", (self.client_id, self.stale_minutes)).fetchall()
        self.conn.commit()
        for row in rows:
            self._reconcile_one(row["id"])
        young = self.conn.execute("select count(*) as n from actions where client_id=%s and status='applying'",
                                  (self.client_id,)).fetchone()["n"]
        self.conn.commit()
        if young:
            self.run.count("applying_recent", young)
            print(f"reconcile: {young} applying row(s) younger than {self.stale_minutes} min left alone")

    def _reconcile_one(self, action_id: UUID) -> None:
        self.conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
        a = self.conn.execute("select * from actions where id=%s and status='applying' for update skip locked", (action_id,)).fetchone()
        if a is None:
            self.conn.rollback()
            return
        if a["action_type"] not in self.types:
            self.conn.rollback()
            self._log(a, f"applying; reconcile needs --role {'sam_admin' if a['action_type'] in ADMIN_TYPES else 'executor'}")
            return   # counted once, in the trailing `applying` total
        try:
            target = self.load_target(a)
            obj = self.read_back(a, target)
            self.mirror(a, target, obj)
            ok, detail = self.matches(a, target, obj)
        except (Fail, MetaApiError) as exc:
            ok, detail = False, str(getattr(exc, "last_error", exc))
        if ok:
            self.conn.execute("update actions set status='applied', applied_at=now(), last_error=null where id=%s", (a["id"],))
            self.run.count("reconciled_applied")
            self._log(a, f"reconciled → applied ({detail})")
        else:
            self.conn.execute("update actions set status='failed', last_error=%s where id=%s", (f"reconcile: {detail}"[:2000], a["id"]))
            self.run.count("reconciled_failed")
            self._log(a, f"reconciled → failed ({detail})")
        self.conn.commit()

    def apply_all(self) -> None:
        stuck = self.conn.execute("select count(*) as n from actions where client_id=%s and status='applying'", (self.client_id,)).fetchone()["n"]
        self.conn.commit()
        if stuck:
            raise Blocked(f"{stuck} action(s) in 'applying' block the executor; run apply_actions.py --reconcile")
        if self.paused():
            print("paused: clients.paused or PIPELINE_PAUSED is set; every row is left untouched (set_pause_flag excepted)")
        rows = self.conn.execute(
            "select id from actions where client_id=%s and status in ('approved','proposed') order by created_at, id",
            (self.client_id,)).fetchall()
        self.conn.commit()
        self.spend_brake()   # after the row list: a brake proposal made now is Sam's to decide, not this run's to report as skipped
        for row in rows:
            self.process(row["id"])

    # ---------- one action ----------

    def process(self, action_id: UUID) -> None:
        conn = self.conn
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))                     # §6 step 1
        a = conn.execute("select * from actions where id=%s and status in ('approved','proposed') for update skip locked",
                         (action_id,)).fetchone()
        if a is None:
            conn.rollback()
            return
        auto = False
        try:
            t = a["action_type"]
            if t not in self.types:
                if t in ADMIN_TYPES:
                    raise Skip("waits for Sam (approve and apply with --role sam_admin)", "skipped_role")
                if t in EXECUTOR_TYPES:
                    raise Skip("applied by the executor role, not sam_admin", "skipped_role")
                raise Skip("not handled in phase 0", "skipped_role")
            if a["status"] == "proposed":
                if t in ADMIN_TYPES:
                    raise Skip("proposed; Sam-only type is never automatic", "skipped_trust")
                ok, why = self.at_execute_trust(t)
                if not ok:
                    raise Skip(f"proposed; {why}", "skipped_trust")
                auto = True
            if t != "set_pause_flag" and self.paused():                                            # §6 step 2
                raise Skip("paused", "skipped_paused")
            target = self.load_target(a)
            self.validate(a, target)
            if t in BUDGET_TYPES:                                                                  # §6 step 3
                conn.execute("savepoint budgets")
                self.apply_budgets(a, target)
                cap_ok = conn.execute("select check_daily_cap(%s) as ok", (self.client_id,)).fetchone()["ok"]
                conn.execute("rollback to savepoint budgets")
                if not cap_ok:
                    raise Fail("daily_cap")
                if self.spend_tripped:
                    raise Skip("hourly spend above daily_cap; set_pause_flag proposed", "skipped_brake")
            if auto:                                                                               # §6 step 4
                limited = self.rate_limited(a)
                if limited:
                    raise Skip(f"rate limit: {limited}", "skipped_rate_limit")
            if auto:                                                                               # §6 step 5
                cur = conn.execute(
                    "update actions set status='applying', executor_run_id=%s, attempts=attempts+1, decided_by='executor',"
                    " decided_at=now(), decision_channel='auto', approved_payload=proposal"
                    " where id=%s and status in ('approved','proposed')", (self.run.id, a["id"]))
            else:
                cur = conn.execute(
                    "update actions set status='applying', executor_run_id=%s, attempts=attempts+1"
                    " where id=%s and status in ('approved','proposed')", (self.run.id, a["id"]))
            if cur.rowcount != 1:
                conn.rollback()
                return
            conn.commit()   # `applying` is durable before any external call
        except Skip as skip:
            conn.rollback()
            self.run.count(skip.counter)
            self._log(a, f"left {a['status']}: {skip.reason}")
            return
        except Fail as fail:
            conn.rollback()
            self.mark_failed(a, fail.last_error, expect=("approved", "proposed"))
            return

        try:                                                                                       # §6 steps 6–7
            obj = self.perform(a, target)
            self.mirror(a, target, obj)
            conn.execute("update actions set status='applied', applied_at=now(), last_error=null where id=%s", (a["id"],))
            conn.commit()
            self.run.count("applied_auto" if auto else "applied")
            self._log(a, "applied" + (" (auto)" if auto else ""))
        except Exception as exc:  # noqa: BLE001 — any failure is recorded on the row, never swallowed
            conn.rollback()
            error = f"{type(exc).__name__}: {exc}"
            try:   # the warehouse should still mirror whatever Meta did before the error
                obj = self.read_back(a, target)
                self.mirror(a, target, obj)
                conn.commit()
            except Exception:  # noqa: BLE001
                conn.rollback()
            self.mark_failed(a, error, expect=("applying",))

    def mark_failed(self, a: dict[str, Any], error: str, *, expect: tuple[str, ...]) -> None:
        """Guarded by the states the row can legitimately be in: a decision that landed after our lock was
        released (Sam rejecting it, say) is never overwritten."""
        cur = self.conn.execute("update actions set status='failed', last_error=%s, executor_run_id=%s where id=%s and status = any(%s)",
                                (error[:2000], self.run.id, a["id"], list(expect)))
        self.conn.commit()
        if cur.rowcount != 1:
            self._log(a, f"changed state meanwhile; not marked failed ({error})")
            return
        self.run.count("failed")
        self._log(a, f"failed: {error}")
        self.failure_brake(a["action_type"])

    # ---------- checks ----------

    def paused(self) -> bool:
        row = self.conn.execute("select paused from clients where id=%s", (self.client_id,)).fetchone()
        return bool(row and row["paused"]) or env_flag("PIPELINE_PAUSED")

    def at_execute_trust(self, action_type: str) -> tuple[bool, str]:
        """FR-46: execute trust = config level 'execute' AND streak ≥ threshold in `trust_streaks` (human
        channels only, unchanged payload, reset on rejection) AND no executor failure of this type since its
        last applied `promote_trust` (demotion is computed; the executor cannot write clients.config)."""
        row = self.conn.execute("select streak, threshold, level from trust_streaks where client_id=%s and action_type=%s",
                                (self.client_id, action_type)).fetchone()
        if row is None or row["level"] != "execute":
            return False, "trust=propose"
        if row["threshold"] is None or row["streak"] < row["threshold"]:
            return False, f"trust=execute but streak {row['streak']}/{row['threshold']}"
        demoted = self.conn.execute(
            "select exists (select 1 from actions f left join runs r on r.id = f.executor_run_id"
            "  where f.client_id=%s and f.action_type=%s and f.status='failed'"
            "    and coalesce(r.started_at, f.created_at) > coalesce((select max(p.applied_at) from actions p"
            "      where p.client_id=%s and p.action_type='promote_trust' and p.target_id=%s and p.status='applied'),"
            "      '-infinity'::timestamptz)) as demoted", (self.client_id, action_type, self.client_id, action_type)).fetchone()["demoted"]
        if demoted:
            return False, "demoted: an executor failure since the last promote_trust"
        return True, "trust=execute"

    def rate_limited(self, a: dict[str, Any]) -> str | None:
        """§6 step 4 for autonomous rows. A missing limit is a refusal, never a permissive default."""
        t = a["action_type"]
        if t == "kill":
            max_kills, share = self.limits.get("max_kills_per_day"), self.limits.get("max_share_of_live_ads_killed_per_day")
            if max_kills is None or share is None:
                return "rate_limits.max_kills_per_day / max_share_of_live_ads_killed_per_day missing in config"
            today = self.conn.execute(
                "select count(*) as n from actions where client_id=%s and action_type='kill' and status='applied'"
                " and applied_at::date = current_date", (self.client_id,)).fetchone()["n"]
            if today + 1 > int(max_kills):
                return f"max_kills_per_day={max_kills} ({today} applied today)"
            live = self.conn.execute("select count(*) as n from ad_entities where client_id=%s and status='ACTIVE'",
                                     (self.client_id,)).fetchone()["n"]
            if today + 1 > Decimal(str(share)) * (live + today):
                return f"max_share_of_live_ads_killed_per_day={share} ({today} killed today, {live} live)"
        if t == "scale":
            hours = self.limits.get("scale_cooldown_hours")
            if hours is None:
                return "rate_limits.scale_cooldown_hours missing in config"
            recent = self.conn.execute(
                "select exists (select 1 from actions where client_id=%s and action_type='scale' and status='applied'"
                " and target_id=%s and applied_at > now() - make_interval(hours => %s)) as hit",
                (self.client_id, a["target_id"], int(hours))).fetchone()["hit"]
            if recent:
                return f"one scale per ad per {hours}h"
        return None

    def load_target(self, a: dict[str, Any]) -> dict[str, Any]:
        tt, tid = a["target_type"], a["target_id"]
        if tt == "ad_entity":
            row = self.conn.execute("select * from ad_entities where id=%s and client_id=%s", (as_uuid(tid), self.client_id)).fetchone()
        elif tt == "campaign":
            row = self.conn.execute("select * from campaigns where id=%s and client_id=%s", (as_uuid(tid), self.client_id)).fetchone()
        elif tt == "client":
            row = self.conn.execute("select * from clients where id=%s", (as_uuid(tid),)).fetchone()
            if row is not None and row["id"] != self.client_id:
                row = None
        elif tt == "trust":
            row = {"action_type": tid}
        else:
            raise Fail(f"target_type {tt!r} is not handled by {a['action_type']}")
        if row is None:
            raise Fail(f"target {tt} {tid} not found for this client")
        return row

    def validate(self, a: dict[str, Any], target: dict[str, Any]) -> None:
        t, p = a["action_type"], a["proposal"] or {}
        if t in ("pause", "kill", "activate"):
            if a["target_type"] not in ("ad_entity", "campaign"):
                raise Fail(f"{t} targets an ad_entity or a campaign, not {a['target_type']}")
            if a["target_type"] == "campaign" and not target.get("external_id"):
                raise Fail("campaign has no external_id yet")
            if t == "activate" and a["target_type"] == "ad_entity" and target.get("review_status") == "DISAPPROVED":
                raise Fail("disapproved")                                                          # FR-37
        elif t == "scale":
            if a["target_type"] != "ad_entity":
                raise Fail("scale targets an ad_entity")
            new = self.scale_budget(a)
            old = target.get("adset_daily_budget")
            if old is not None and old > 0 and abs(new - Decimal(old)) > Decimal(old) * MAX_BUDGET_STEP:
                raise Fail(f"budget_step: {old} → {new} exceeds 20%")
        elif t == "set_pause_flag":
            if a["target_type"] != "client" or not isinstance(p.get("paused"), bool):
                raise Fail("set_pause_flag targets the client with proposal.paused true|false")
        elif t == "promote_trust":
            if a["target_type"] != "trust" or p.get("level") not in ("propose", "execute"):
                raise Fail("promote_trust targets trust/<action_type> with proposal.level propose|execute")
            if a["target_id"] == "kill" and p["level"] == "execute":                                  # FR-46
                floor = Decimal(str(((self.cfg.get("trust") or {}).get("kill") or {}).get("backtest_min_accuracy", "0.8")))
                try:
                    accuracy = Decimal(str(p["backtest_accuracy"]))
                except (KeyError, ArithmeticError, TypeError):
                    raise Fail(f"kill promotion needs proposal.backtest_accuracy >= {floor}") from None
                if accuracy < floor:
                    raise Fail(f"backtest_accuracy {accuracy} is below {floor}")
        elif t == "build_campaign":
            raise Fail("build_campaign lands in T9")

    @staticmethod
    def scale_budget(a: dict[str, Any]) -> Decimal:
        try:
            new = Decimal(str((a["proposal"] or {})["adset_daily_budget"]))
        except (KeyError, ArithmeticError, TypeError):
            raise Fail("proposal.adset_daily_budget missing or not a number") from None
        if new <= 0:
            raise Fail("proposal.adset_daily_budget must be positive")
        return new

    def apply_budgets(self, a: dict[str, Any], target: dict[str, Any]) -> None:
        """The proposal's budget effect on the warehouse, used inside a savepoint for `check_daily_cap()`."""
        t = a["action_type"]
        if t == "activate" and a["target_type"] == "ad_entity":
            self.conn.execute("update ad_entities set status='ACTIVE' where id=%s", (target["id"],))
        elif t == "activate":
            self.conn.execute("update campaigns set status='ACTIVE' where id=%s", (target["id"],))
        elif t == "scale":
            self.conn.execute("update ad_entities set adset_daily_budget=%s where client_id=%s and adset_id=%s",
                              (self.scale_budget(a), self.client_id, target["adset_id"]))

    # ---------- the side effect, its read-back, and the mirror ----------

    def meta_ref(self, a: dict[str, Any], target: dict[str, Any]) -> tuple[str, str]:
        if a["action_type"] == "scale":
            return "adset", target["adset_id"]
        if a["target_type"] == "campaign":
            return "campaign", target["external_id"]
        return "ad", target["ad_id"]

    def perform(self, a: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        t = a["action_type"]
        if t in DESIRED_STATUS:
            kind, oid = self.meta_ref(a, target)
            self.meta.update(kind, oid, status=DESIRED_STATUS[t])
        elif t == "scale":
            self.meta.update("adset", target["adset_id"], daily_budget=float(self.scale_budget(a)))
        elif t == "set_pause_flag":
            self.conn.execute("update clients set paused=%s where id=%s", (a["proposal"]["paused"], self.client_id))
        elif t == "promote_trust":
            cfg = json.loads(json.dumps(self.cfg))
            cfg.setdefault("trust", {}).setdefault(a["target_id"], {})["level"] = a["proposal"]["level"]
            self.conn.execute("update clients set config=%s where id=%s", (Jsonb(cfg), self.client_id))
            self.cfg = cfg
        elif t == "quote_release":
            pass   # the applied row is the release; the gate reads it
        else:
            raise Fail(f"{t} has no executor path")
        obj = self.read_back(a, target)
        ok, detail = self.matches(a, target, obj)
        if not ok:
            raise MetaApiError(f"read-back mismatch: {detail}")
        return obj

    def read_back(self, a: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        t = a["action_type"]
        if t in ("set_pause_flag", "promote_trust"):
            return self.conn.execute("select paused, config from clients where id=%s", (self.client_id,)).fetchone()
        if t == "quote_release":
            return {}
        kind, oid = self.meta_ref(a, target)
        return self.meta.get(kind, oid)

    def matches(self, a: dict[str, Any], target: dict[str, Any], obj: dict[str, Any]) -> tuple[bool, str]:
        t = a["action_type"]
        if t in DESIRED_STATUS:
            kind, oid = self.meta_ref(a, target)
            return obj.get("status") == DESIRED_STATUS[t], f"{kind} {oid} is {obj.get('status')}, expected {DESIRED_STATUS[t]}"
        if t == "scale":
            want = self.scale_budget(a)
            got = obj.get("daily_budget")
            return got is not None and abs(Decimal(str(got)) - want) < Decimal("0.005"), f"adset {target['adset_id']} budget is {got}, expected {want}"
        if t == "set_pause_flag":
            return obj["paused"] == a["proposal"]["paused"], f"clients.paused is {obj['paused']}"
        if t == "promote_trust":
            level = ((obj["config"] or {}).get("trust") or {}).get(a["target_id"], {}).get("level")
            return level == a["proposal"]["level"], f"trust.{a['target_id']}.level is {level}"
        return True, "no external state"

    def mirror(self, a: dict[str, Any], target: dict[str, Any], obj: dict[str, Any]) -> None:
        """Write what Meta returned (never what we asked for) to the warehouse. Executor column grants only."""
        t = a["action_type"]
        if t == "scale":
            budget = obj.get("daily_budget")
            if budget is not None:
                self.conn.execute("update ad_entities set adset_daily_budget=%s where client_id=%s and adset_id=%s",
                                  (Decimal(str(budget)), self.client_id, target["adset_id"]))
        elif t in DESIRED_STATUS and a["target_type"] == "ad_entity":
            status = obj.get("status") if obj.get("status") in AD_STATUSES else None
            review = obj.get("review_status") if obj.get("review_status") in REVIEW_STATUSES else None
            self.conn.execute(
                "update ad_entities set status=coalesce(%s, status), review_status=coalesce(%s, review_status),"
                " review_feedback=coalesce(%s, review_feedback),"
                " launched_at=case when %s='ACTIVE' then coalesce(launched_at, now()) else launched_at end where id=%s",
                (status, review, Jsonb(obj["ad_review_feedback"]) if isinstance(obj.get("ad_review_feedback"), dict) else None,
                 status, target["id"]))
        elif t in DESIRED_STATUS:
            status = obj.get("status") if obj.get("status") in CAMPAIGN_STATUSES else None
            budget = obj.get("daily_budget")
            self.conn.execute("update campaigns set status=coalesce(%s, status), daily_budget=coalesce(%s, daily_budget) where id=%s",
                              (status, None if budget is None else Decimal(str(budget)), target["id"]))

    # ---------- brakes (FR-47) ----------

    def failure_brake(self, action_type: str) -> None:
        """Three consecutive failures of one action type propose `set_pause_flag` (idempotent per failing row)."""
        last = self.conn.execute(
            "select f.id, f.status, f.last_error from actions f left join runs r on r.id = f.executor_run_id"
            " where f.client_id=%s and f.action_type=%s and f.status in ('applied','failed') and f.executor_run_id is not null"
            " order by r.started_at desc, f.created_at desc limit 3", (self.client_id, action_type)).fetchall()
        if len(last) < 3 or any(r["status"] != "failed" for r in last):
            self.conn.commit()
            return
        self.propose_pause(
            key=f"brake:consecutive_failures:{action_type}:{last[0]['id']}",
            rule="three_consecutive_failures",
            reason=f"{action_type} failed 3 times in a row",
            evidence={"action_type": action_type, "action_ids": [str(r["id"]) for r in last],
                      "errors": [r["last_error"] for r in last]})

    def spend_brake(self) -> None:
        """Hourly account spend above `daily_cap` (latest `account_spend_hourly` row today) proposes `set_pause_flag`
        and holds budget-affecting rows for this run."""
        row = self.conn.execute(
            "select spend_today, observed_at from account_spend_hourly where client_id=%s and observed_at::date = current_date"
            " order by observed_at desc limit 1", (self.client_id,)).fetchone()
        cap = self.client.get("daily_cap")
        if row is None or cap is None or row["spend_today"] <= cap:
            self.conn.commit()
            return
        self.spend_tripped = True
        self.propose_pause(
            key=f"brake:hourly_spend:{self.client_id}:{date.today().isoformat()}",
            rule="hourly_spend_over_cap",
            reason=f"account spend today {row['spend_today']} exceeds daily_cap {cap}",
            evidence={"spend_today": str(row["spend_today"]), "daily_cap": str(cap), "observed_at": row["observed_at"].isoformat()})

    def propose_pause(self, *, key: str, rule: str, reason: str, evidence: dict[str, Any]) -> None:
        """One open (proposed/approved) set_pause_flag per rule and action type at a time; keys make re-runs idempotent."""
        exists = self.conn.execute(
            "select 1 from actions where proposal_key=%s or (client_id=%s and action_type='set_pause_flag' and rule=%s"
            " and status in ('proposed','approved') and coalesce(evidence->>'action_type','') = %s)",
            (key, self.client_id, rule, evidence.get("action_type", ""))).fetchone()
        if exists:
            self.conn.commit()
            return
        insert(self.conn, "actions", client_id=self.client_id, action_type="set_pause_flag", target_type="client",
               target_id=str(self.client_id), rule=rule, proposal={"paused": True, "reason": reason},
               proposal_key=key, evidence=evidence)
        self.conn.commit()
        self.run.count("brake_proposed")
        print(f"brake: proposed set_pause_flag ({rule}: {reason})")

    # ---------- output ----------

    @staticmethod
    def _log(a: dict[str, Any], outcome: str) -> None:
        print(f"{a['action_type']} {a['target_type']} {a['target_id']} [{str(a['id'])[:8]}]: {outcome}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Apply approved (and execute-trust) actions. SKILL.md §6.")
    p.add_argument("--client", default="upclicklabs")
    p.add_argument("--reconcile", action="store_true", help="settle stale `applying` rows against Meta first; never re-send")
    p.add_argument("--role", choices=("executor", "sam_admin"), default="executor",
                   help="sam_admin applies set_pause_flag / promote_trust / quote_release only and never calls Meta")
    p.add_argument("--stale-minutes", type=int, default=STALE_MINUTES)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    with connect(args.role, job="apply_actions") as conn:
        client = client_by_slug(conn, args.client)
        if client is None:
            print(f"apply_actions: no client with slug {args.client!r}", file=sys.stderr)
            return 1
        try:
            with run(conn, WORKER, client["id"]) as r:
                print(format_where_are_we(where_are_we(conn, args.client)))
                check_config(client)
                meta = get_meta() if args.role == "executor" else None
                conn.execute("select pg_advisory_lock(hashtext(%s))", (LOCK_KEY,))
                conn.commit()
                try:
                    ex = Executor(conn, client, args.role, r, meta, args.stale_minutes)
                    if args.reconcile:
                        ex.reconcile()
                    ex.apply_all()
                finally:
                    conn.rollback()
                    conn.execute("select pg_advisory_unlock(hashtext(%s))", (LOCK_KEY,))
                    conn.commit()
        except (Blocked, ConfigError) as exc:
            print(f"apply_actions: {exc}", file=sys.stderr)
            return 2
        print(f"runs {r.id}: ok {json.dumps(r.counts, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
