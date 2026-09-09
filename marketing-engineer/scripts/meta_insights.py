#!/usr/bin/env python3
"""`pull insights` (T10): the performance loop. SKILL.md §3, §4 rules 2 and 10, §7; PRD FR-2, FR-3, FR-38 to FR-41.

    python3 scripts/meta_insights.py [--client upclicklabs] [--today YYYY-MM-DD] [--days 7]
    python3 scripts/meta_insights.py --learning "text"        # stop point D: Sam's first learnings row by hand

One invocation, as `worker_rw`, reads only through the Meta adapter and writes entities and proposed actions:

  1. ad-level daily insights for every ad of the client, `since = today - days` to `today`, appended to
     `ad_metrics_daily` keyed by (ad, day, fetched_on = today): a day fetched again on a later date is a second row
     and `ad_metrics_latest` shows the newest (FR-38); the same (ad, day, fetched_on) is never written twice;
  2. account-level spend today into `account_spend_hourly` (one row per run; the routine runs hourly) for the
     executor's observational brake (FR-47);
  3. the active lever per campaign (FR-2, FR-3): the static chain cost per link click → quiz-start rate →
     quiz-complete rate → booking rate → cost per booked call (hook rate first only for video families), walked
     top-down from campaign-level `ad_metrics_latest` plus warehouse-verified leads, stopping at the first lever
     below its benchmark at sample size; the benchmark resolves own history → `mart_benchmarks` (≥3 clients) →
     config floor, and the reason names the source. Written to `campaigns.active_lever*` (0003 grant);
  4. kill / scale from `mart_kill_scale_candidates` (FR-39): `config_missing` is a hard stop; every `kill` /
     `scale` row becomes ONE proposed action with the view row as `evidence` (a scale proposes +20%, FR-31);
     an open action for the same ad and type is never duplicated;
  5. `cpl_target` derivation (FR-40): computed from the funnel after 100 link clicks and reported; writing it to
     `clients.config` is Sam's (`sam_admin`), so the number lands in `runs.counts` and on stdout;
  6. learnings (FR-41): per component value, arm A = the client's creatives carrying it, arm B = the rest;
     a `learnings` row is written only with ≥50 link clicks per arm, effect ≥0.3pp absolute or ≥30% relative,
     and Beta-Binomial posterior P(direction) ≥ 0.9; below the gates nothing is written and the reason is
     recorded. The "zero learnings" warning fires only when a creative reached sample size and no learning was
     written or refused with a reason.

Every run opens and closes a `runs` row (worker `loop`); refusals close it `failed` with the reason and exit 2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.env import load_env  # noqa: E402
from adapters.meta import MetaAds, get_meta  # noqa: E402
from warehouse import client as wh  # noqa: E402
from warehouse.client import Jsonb  # noqa: E402

WORKER = "loop"
STATIC_CHAIN = ("cost_per_link_click", "quiz_start_rate", "quiz_complete_rate", "booking_rate", "cost_per_booked_call")   # FR-2
VIDEO_RUNG_ZERO = "hook_rate"
COST_LEVERS = ("cost_per_link_click", "cost_per_booked_call")     # below benchmark means above the number
SCALE_STEP = Decimal("0.20")                                      # FR-31: budget moves in ≤20% steps
MIN_CLICKS_PER_ARM = 50                                           # FR-41
MIN_EFFECT_ABS = 0.003                                            # 0.3pp
MIN_EFFECT_REL = 0.30
MIN_POSTERIOR = 0.90
POSTERIOR_SAMPLES = 20_000
CPL_MIN_CLICKS = 100                                              # FR-40
DEFAULT_SAMPLE_CLICKS = 100                                       # DECISIONS C7: conversion-stage sample (clicks)
LEARNING_COMPONENTS = ("family", "variant", "hook_type", "angle", "template", "renderer", "image_model", "cta", "copy_length", "proof_type")
REQUIRED_CONFIG = (("targets", "ctr_floor"), ("targets", "kill_impressions"), ("floors",))
TRUTHY = ("1", "true", "yes", "on")


class LoopRefused(RuntimeError):
    """`pull insights` refused; the message says why. The runs row closes `failed` with it."""


# ---------- pure rules (unit-tested) ----------

def lever_chain(video: bool) -> tuple[str, ...]:
    """FR-2: the static chain; hook rate is rung zero only for video families."""
    return (VIDEO_RUNG_ZERO, *STATIC_CHAIN) if video else STATIC_CHAIN


def lever_values(m: dict[str, Any]) -> dict[str, float | None]:
    """The five (six) numbers from campaign-level totals: Meta impressions / clicks / spend, warehouse leads."""
    imp, lc, spend = float(m.get("impressions") or 0), float(m.get("link_clicks") or 0), float(m.get("spend") or 0)
    leads, completed, booked = float(m.get("leads") or 0), float(m.get("completed") or 0), float(m.get("booked_verified") or 0)
    v3 = m.get("video_3s")
    return {
        "hook_rate": (float(v3) / imp) if (v3 is not None and imp > 0) else None,
        "cost_per_link_click": (spend / lc) if lc > 0 else None,
        "quiz_start_rate": (leads / lc) if lc > 0 else None,
        "quiz_complete_rate": (completed / leads) if leads > 0 else None,
        "booking_rate": (booked / completed) if completed > 0 else None,
        "cost_per_booked_call": (spend / booked) if booked > 0 else None,
        "cpm": (spend / imp * 1000) if imp > 0 else None,
    }


def at_sample_size(lever: str, m: dict[str, Any], *, kill_impressions: int, sample_clicks: int) -> tuple[bool, str]:
    """CTR-stage levers need `kill_impressions` impressions (DECISIONS C7); conversion-stage levers need `sample_clicks`
    link clicks, evaluated at campaign level."""
    if lever in ("hook_rate", "cost_per_link_click"):
        n = int(m.get("impressions") or 0)
        return n >= kill_impressions, f"{n}/{kill_impressions} impressions"
    n = int(m.get("link_clicks") or 0)
    return n >= sample_clicks, f"{n}/{sample_clicks} link clicks"


def resolve_benchmark(lever: str, *, own: dict[str, float] | None, cross: dict[str, float] | None,
                      floors: dict[str, Any], cpl_target: Any) -> tuple[float | None, str]:
    """FR-3: own history → `mart_benchmarks` (≥3 clients) → config floor. Returns (value, source). Phase 0 carries no
    own history and the cross-client mart is empty, so the floor answers and the reason names it."""
    if own and own.get(lever) is not None:
        return float(own[lever]), "own history"
    if cross and cross.get(lever) is not None:
        return float(cross[lever]), "mart_benchmarks"
    if lever == "cost_per_booked_call":
        return (None, "config targets.cpl_target unset (FR-40: advisory until derived)") if cpl_target is None else (float(cpl_target), "config targets.cpl_target")
    value = (floors or {}).get(lever)
    return (None, f"config floors.{lever} unset") if value is None else (float(value), f"config floor floors.{lever}")


def below_benchmark(lever: str, value: float, benchmark: float) -> bool:
    return value > benchmark if lever in COST_LEVERS else value < benchmark


def select_lever(m: dict[str, Any], *, video: bool, floors: dict[str, Any], cpl_target: Any, kill_impressions: int,
                 sample_clicks: int, own: dict[str, float] | None = None, cross: dict[str, float] | None = None) -> tuple[str, str]:
    """FR-3: walk the chain top-down; the first lever below its benchmark at sample size is active. A lever not yet at
    sample size stops the walk (downstream levers have even less data) and stays active while it waits. Every
    lever at or above its benchmark is passed. Returns (lever, reason)."""
    values = lever_values(m)
    passed: list[str] = []
    for lever in lever_chain(video):
        ok, sample = at_sample_size(lever, m, kill_impressions=kill_impressions, sample_clicks=sample_clicks)
        benchmark, source = resolve_benchmark(lever, own=own, cross=cross, floors=floors, cpl_target=cpl_target)
        value = values.get(lever)
        prefix = f"passed {', '.join(passed)}; " if passed else ""
        if not ok:
            return lever, f"{prefix}{lever} waiting for sample size ({sample}); benchmark {fmt(benchmark)} from {source}"
        if benchmark is None:
            return lever, f"{prefix}{lever} = {fmt(value)} cannot be judged: {source}"
        if value is None:
            return lever, f"{prefix}{lever} undefined (no events yet) at {sample}; benchmark {fmt(benchmark)} from {source}"
        if below_benchmark(lever, value, benchmark):
            side = "above" if lever in COST_LEVERS else "below"
            return lever, f"{prefix}{lever} = {fmt(value)} {side} benchmark {fmt(benchmark)} from {source} at {sample}"
        passed.append(f"{lever} = {fmt(value)} vs {fmt(benchmark)} ({source})")
    last = lever_chain(video)[-1]
    return last, f"every lever at or above benchmark: {'; '.join(passed)}; working the terminal lever {last}"


def fmt(v: float | None) -> str:
    """Rates to four decimals, money and counts to two, trailing zeros dropped."""
    if v is None:
        return "-"
    return (f"{v:.2f}" if abs(v) >= 1 else f"{v:.4f}").rstrip("0").rstrip(".") or "0"


def derive_cpl_target(*, link_clicks: int, spend: Any, booked_verified: int, floor: Any = None,
                      min_clicks: int = CPL_MIN_CLICKS) -> tuple[Decimal | None, str]:
    """FR-40: after `min_clicks` link clicks, cpl_target = spend / verified bookings, never below `floor`. Before that
    (or with no verified booking yet) nothing is derived and the reason says so; conversion-stage rules stay advisory."""
    if link_clicks < min_clicks:
        return None, f"advisory: {link_clicks}/{min_clicks} link clicks"
    if booked_verified <= 0:
        return None, f"advisory: {link_clicks} link clicks but no verified booking yet"
    derived = (Decimal(str(spend)) / Decimal(booked_verified)).quantize(Decimal("0.01"))
    if floor is not None and derived < Decimal(str(floor)):
        return Decimal(str(floor)), f"derived {derived} below floor {floor}; floor applies"
    return derived, f"spend {Decimal(str(spend))} / {booked_verified} verified bookings over {link_clicks} link clicks"


def posterior_beats(a_clicks: int, a_imp: int, b_clicks: int, b_imp: int, *, samples: int = POSTERIOR_SAMPLES, seed: int = 0) -> float:
    """P(ctr_a > ctr_b) under Beta(1,1) priors on clicks/impressions (CRUCIBLE A8). Seeded, so the same inputs give the
    same number; two decimals of precision are all the gate needs."""
    rng = random.Random(f"{seed}:{a_clicks}:{a_imp}:{b_clicks}:{b_imp}")
    wins = 0
    for _ in range(samples):
        if rng.betavariate(a_clicks + 1, max(a_imp - a_clicks, 0) + 1) > rng.betavariate(b_clicks + 1, max(b_imp - b_clicks, 0) + 1):
            wins += 1
    return wins / samples


def learning_gate(arm: dict[str, int], rest: dict[str, int]) -> tuple[dict[str, Any] | None, str]:
    """FR-41 / A8 on link CTR. Returns (learning fields, reason). Below any gate: (None, why)."""
    for name, d in (("arm", arm), ("rest", rest)):
        if int(d.get("link_clicks") or 0) < MIN_CLICKS_PER_ARM:
            return None, f"{name} has {int(d.get('link_clicks') or 0)} link clicks, below {MIN_CLICKS_PER_ARM} per arm"
    a_imp, a_clicks, b_imp, b_clicks = int(arm["impressions"]), int(arm["link_clicks"]), int(rest["impressions"]), int(rest["link_clicks"])
    if a_imp <= 0 or b_imp <= 0:
        return None, "an arm has no impressions"
    ctr_a, ctr_b = a_clicks / a_imp, b_clicks / b_imp
    effect = ctr_a - ctr_b
    rel = abs(effect) / ctr_b if ctr_b > 0 else float("inf")
    if abs(effect) < MIN_EFFECT_ABS and rel < MIN_EFFECT_REL:
        return None, f"effect {effect * 100:+.2f}pp ({rel:.0%} relative) below 0.3pp and 30%"
    direction = "beat" if effect > 0 else "miss"
    p = posterior_beats(a_clicks, a_imp, b_clicks, b_imp)
    posterior = p if direction == "beat" else 1 - p
    if posterior < MIN_POSTERIOR:
        return None, f"posterior P({direction}) {posterior:.2f} below {MIN_POSTERIOR}"
    return {"direction": direction, "effect_size": round(effect, 5), "posterior": round(posterior, 3), "sample": a_imp,
            "ctr_a": ctr_a, "ctr_b": ctr_b, "relative": None if rel == float("inf") else round(rel, 4)}, "passed"


def scale_budget(current: Any) -> Decimal:
    """FR-31: one step of at most 20%, rounded to cents."""
    return (Decimal(str(current)) * (1 + SCALE_STEP)).quantize(Decimal("0.01"))


def kill_rule(row: dict[str, Any]) -> str:
    """Which branch of the view produced a `kill`: CTR-stage (`ctr_floor`) or conversion-stage (`cpl_expected_bookings`)."""
    imp, ctr = int(row.get("impressions") or 0), row.get("link_ctr")
    if row.get("kill_impressions") is not None and imp >= int(row["kill_impressions"]) and ctr is not None and row.get("ctr_floor") is not None \
            and Decimal(str(ctr)) < Decimal(str(row["ctr_floor"])):
        return "ctr_floor"
    return "cpl_expected_bookings"


def jsonable(v: Any) -> Any:
    """Evidence values as JSON: integral numerics (the view's sums and counts) as ints, other decimals as strings."""
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else str(v)
    return v


def evidence_hash(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


# ---------- config and reads ----------

def check_config(config: dict[str, Any], client: dict[str, Any]) -> None:
    missing = [k for k in ("daily_cap", "currency") if client.get(k) is None]
    for path in REQUIRED_CONFIG:
        node: Any = config
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            missing.append(".".join(path))
    if missing:
        raise LoopRefused(f"clients.config for {client['slug']!r} is missing {', '.join(missing)}; refusing to run")


def paused(client: dict[str, Any]) -> bool:
    return bool(client.get("paused")) or (os.environ.get("PIPELINE_PAUSED") or "").strip().lower() in TRUTHY


ADS_SQL = """
select a.id, a.ad_id, a.campaign_id, a.creative_id, a.adset_id, a.adset_daily_budget, a.status
  from ad_entities a
 where a.client_id = %s and a.platform = 'meta' and a.ad_id not like 'pending:%%'
 order by a.created_at, a.id;
"""

CAMPAIGN_TOTALS_SQL = """
select c.id as campaign_id,
       coalesce(sum(m.impressions), 0) as impressions, coalesce(sum(m.link_clicks), 0) as link_clicks,
       coalesce(sum(m.spend), 0) as spend, sum(m.video_3s) as video_3s,
       (select count(*) from leads l join ad_entities x on x.id = l.ad_entity_id
         where x.campaign_id = c.id and l.stage <> 'erased' and coalesce(l.abuse_score, 0) < 0.5) as leads,
       (select count(*) from leads l join ad_entities x on x.id = l.ad_entity_id
         where x.campaign_id = c.id and coalesce(l.abuse_score, 0) < 0.5
           and l.stage in ('completed','booked','showed','qualified','proposal','closed_won','closed_lost')) as completed,
       (select count(*) from leads l join ad_entities x on x.id = l.ad_entity_id
         where x.campaign_id = c.id and coalesce(l.abuse_score, 0) < 0.5 and l.booked_verified_at is not null) as booked_verified,
       exists (select 1 from ad_entities x join creatives cr on cr.id = x.creative_id
                 join creative_components cc on cc.creative_id = cr.id and cc.component_type = 'family'
                 join families f on f.name = cc.component_ref
                where x.campaign_id = c.id and f.kind = 'video') as video
  from campaigns c
  left join ad_entities a on a.campaign_id = c.id
  left join ad_metrics_latest m on m.ad_entity_id = a.id
 where c.client_id = %s and c.platform = 'meta' and c.external_id is not null
 group by c.id
 order by c.created_at, c.id;
"""

CROSS_BENCHMARK_SQL = """
select median_cost_per_link_click from mart_benchmarks b
  join icps i on i.industry = b.industry
 where i.client_id = %s
 order by b.creatives desc limit 1;
"""

CANDIDATES_SQL = "select * from mart_kill_scale_candidates where client_id = %s order by ad_id;"

OPEN_ACTION_SQL = """
select 1 from actions where client_id = %s and action_type = %s and target_type = 'ad_entity' and target_id = %s
   and status in ('proposed', 'approved', 'applying') limit 1;
"""

FUNNEL_TOTALS_SQL = """
select coalesce(sum(m.link_clicks), 0) as link_clicks, coalesce(sum(m.spend), 0) as spend,
       (select count(*) from leads l where l.client_id = %s and l.booked_verified_at is not null and coalesce(l.abuse_score, 0) < 0.5) as booked_verified
  from ad_entities a join ad_metrics_latest m on m.ad_entity_id = a.id
 where a.client_id = %s;
"""

ARMS_SQL = """
select cc.component_type, cc.component_ref, c.id as creative_id,
       coalesce(sum(m.impressions), 0) as impressions, coalesce(sum(m.link_clicks), 0) as link_clicks
  from creatives c
  join creative_components cc on cc.creative_id = c.id and cc.component_type = any(%s)
  left join ad_entities a on a.creative_id = c.id
  left join ad_metrics_latest m on m.ad_entity_id = a.id
 where c.client_id = %s
 group by cc.component_type, cc.component_ref, c.id
 order by cc.component_type, cc.component_ref, c.id;
"""

SAMPLE_REACHED_SQL = """
select count(*) as n from (
  select c.id from creatives c join ad_entities a on a.creative_id = c.id join ad_metrics_latest m on m.ad_entity_id = a.id
   where c.client_id = %s group by c.id having sum(m.impressions) >= %s) s;
"""


# ---------- the pull ----------

def action_value(actions: list[dict[str, Any]] | None, name: str) -> int:
    for a in actions or []:
        if a.get("action_type") == name:
            return int(a.get("value") or 0)
    return 0


def pull_metrics(conn: wh.Connection, r: wh.Run, meta: MetaAds, *, client_id: Any, since: date, until: date, fetched_on: date) -> list[dict[str, Any]]:
    """FR-38: ad-level daily rows for every ad of the client, appended with `fetched_on`. Returns the rows read."""
    ads = conn.execute(ADS_SQL, (client_id,)).fetchall()
    by_ad_id = {a["ad_id"]: a for a in ads}
    r.counts.update(ads=len(ads), since=since.isoformat(), until=until.isoformat(), fetched_on=fetched_on.isoformat())
    if not ads:
        r.counts.update(metrics_rows_inserted=0, metrics_rows_seen=0)
        return []
    rows = meta.insights(level="ad", since=since, until=until, ids=list(by_ad_id))
    r.api_calls = (r.api_calls or 0) + 1
    inserted = seen = 0
    for row in rows:
        ad = by_ad_id.get(row.get("ad_id"))
        if ad is None:
            continue
        cur = conn.execute(
            "insert into ad_metrics_daily (ad_entity_id, day, fetched_on, impressions, reach, clicks, link_clicks, spend,"
            " quiz_starts, quiz_completes, schedules, video_3s, frequency)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict (ad_entity_id, day, fetched_on) do nothing",
            (ad["id"], date.fromisoformat(row["date_start"]), fetched_on, int(row.get("impressions") or 0), int(row.get("reach") or 0),
             int(row.get("clicks") or 0), int(row.get("link_clicks") or 0), Decimal(str(row.get("spend") or 0)),
             action_value(row.get("actions"), "QuizStart"), action_value(row.get("actions"), "QuizComplete"),
             action_value(row.get("actions"), "Schedule"), row.get("video_3s"), row.get("frequency")))
        if cur.rowcount == 1:
            inserted += 1
        else:
            seen += 1
    r.counts.update(metrics_rows_inserted=inserted, metrics_rows_seen=seen)
    conn.commit()
    return rows


def pull_spend(conn: wh.Connection, r: wh.Run, meta: MetaAds, *, client_id: Any, today: date) -> Decimal:
    spend = Decimal(str(meta.account_spend_today(on=today)))
    r.api_calls = (r.api_calls or 0) + 1
    wh.insert_account_spend_hourly(conn, client_id=client_id, observed_at=datetime.now(timezone.utc), spend_today=spend)
    conn.commit()
    r.counts["spend_today"] = str(spend)
    return spend


def update_levers(conn: wh.Connection, r: wh.Run, *, client_id: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
    """FR-2, FR-3 per campaign with a Meta object; `active_lever_since` moves only when the lever changes."""
    targets, floors = config["targets"], config.get("floors") or {}
    kill = int(targets["kill_impressions"])
    sample_clicks = int(targets.get("sample_clicks") or DEFAULT_SAMPLE_CLICKS)
    cross_row = conn.execute(CROSS_BENCHMARK_SQL, (client_id,)).fetchone()
    cross = {"cost_per_link_click": float(cross_row["median_cost_per_link_click"])} if cross_row and cross_row.get("median_cost_per_link_click") is not None else None
    out = []
    r.counts.setdefault("campaigns_levered", 0)
    r.counts.setdefault("lever_changes", 0)
    for m in conn.execute(CAMPAIGN_TOTALS_SQL, (client_id,)).fetchall():
        lever, reason = select_lever(m, video=bool(m["video"]), floors=floors, cpl_target=targets.get("cpl_target"), kill_impressions=kill,
                                     sample_clicks=sample_clicks, own=None, cross=cross)
        values = lever_values(m)
        reason = f"{reason}; cpm {fmt(values['cpm'])} (context)"
        prev = conn.execute("select active_lever, active_lever_reason from campaigns where id = %s", (m["campaign_id"],)).fetchone()
        changed = prev["active_lever"] != lever
        conn.execute("update campaigns set active_lever = %s, active_lever_reason = %s,"
                     " active_lever_since = case when %s then now() else coalesce(active_lever_since, now()) end where id = %s",
                     (lever, reason[:2000], changed, m["campaign_id"]))
        r.count("campaigns_levered")
        if changed:
            r.count("lever_changes")
        out.append({"campaign_id": m["campaign_id"], "lever": lever, "reason": reason, "changed": changed, "values": values})
        print(f"lever: campaign {str(m['campaign_id'])[:8]} → {lever}{' (changed)' if changed else ''}: {reason}")
    conn.commit()
    return out


def propose_kill_scale(conn: wh.Connection, r: wh.Run, *, client: dict[str, Any], config: dict[str, Any], window: dict[str, str]) -> list[dict[str, Any]]:
    """FR-39: every non-hold row of the view becomes one proposed action with the row as evidence."""
    rows = conn.execute(CANDIDATES_SQL, (client["id"],)).fetchall()
    counts = {k: sum(1 for x in rows if x["recommendation"] == k) for k in ("config_missing", "kill", "scale", "hold")}
    r.counts["candidates"] = counts
    print(format_candidates(rows))
    if counts["config_missing"]:
        raise LoopRefused("mart_kill_scale_candidates says config_missing: set targets.ctr_floor and targets.kill_impressions; no decision is taken (FR-39, SKILL.md §7)")
    sample_clicks = int(config["targets"].get("sample_clicks") or DEFAULT_SAMPLE_CLICKS)
    out = []
    for row in rows:
        rec = row["recommendation"]
        if rec not in ("kill", "scale"):
            continue
        if conn.execute(OPEN_ACTION_SQL, (client["id"], rec, str(row["ad_entity_id"]))).fetchone():
            r.count(f"{rec}_open")
            continue
        rule = kill_rule(row) if rec == "kill" else "cpl_scale"
        evidence = {k: jsonable(v) for k, v in row.items() if k not in ("client_id",)}
        evidence.update(window=window, rule=rule, advisory=(rule != "ctr_floor" and int(row.get("link_clicks") or 0) < sample_clicks))
        for k in ("ad_entity_id", "creative_id"):
            evidence[k] = str(evidence[k]) if evidence.get(k) is not None else None
        proposal: dict[str, Any] = {}
        if rec == "scale":
            current = conn.execute("select adset_daily_budget from ad_entities where id = %s", (row["ad_entity_id"],)).fetchone()["adset_daily_budget"]
            if current is None:
                r.count("scale_skipped_no_budget")
                print(f"scale skipped for ad {row['ad_id']}: ad set budget unknown")
                continue
            proposal = {"adset_daily_budget": str(scale_budget(current)), "from": str(current)}
        key = f"{rec}:{row['ad_entity_id']}:{rule}:{evidence_hash(window['until'], row['impressions'], row['link_clicks'], row['spend'], row['booked_verified'])}"
        if conn.execute("select 1 from actions where proposal_key = %s", (key,)).fetchone():
            r.count(f"{rec}_seen")
            continue
        a = wh.insert_actions(conn, client_id=client["id"], action_type=rec, target_type="ad_entity", target_id=str(row["ad_entity_id"]),
                              rule=rule, proposal=proposal, proposal_key=key, evidence=evidence,
                              trust_level_at_proposal=((config.get("trust") or {}).get(rec) or {}).get("level") or "propose")
        conn.commit()
        r.count(f"{rec}_proposed")
        out.append(a)
        print(f"proposed {rec} for ad {row['ad_id']} [{str(a['id'])[:8]}] rule={rule}"
              + (f" budget {proposal['from']} → {proposal['adset_daily_budget']}" if proposal else "")
              + (" (advisory: below conversion sample)" if evidence["advisory"] else ""))
    return out


def format_candidates(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "kill/scale view: no ACTIVE ad with metrics"
    head = ("ad", "status", "impr", "clicks", "spend", "ctr", "booked", "recommendation")
    lines = ["kill/scale view (mart_kill_scale_candidates):", "  " + "  ".join(h.ljust(w) for h, w in zip(head, (16, 7, 7, 7, 8, 7, 6, 14)))]
    for x in rows:
        ctr = "-" if x["link_ctr"] is None else f"{float(x['link_ctr']):.4f}"
        lines.append("  " + "  ".join(str(v).ljust(w) for v, w in zip((x["ad_id"], x["status"], x["impressions"], x["link_clicks"], x["spend"], ctr,
                                                                             x["booked_verified"], x["recommendation"]), (16, 7, 7, 7, 8, 7, 6, 14))))
    return "\n".join(lines)


def report_cpl_target(conn: wh.Connection, r: wh.Run, *, client_id: Any, config: dict[str, Any]) -> None:
    t = conn.execute(FUNNEL_TOTALS_SQL, (client_id, client_id)).fetchone()
    derived, why = derive_cpl_target(link_clicks=int(t["link_clicks"]), spend=t["spend"], booked_verified=int(t["booked_verified"]),
                                     floor=config["targets"].get("cpl_target_floor"))
    r.counts["cpl_target_derived"] = None if derived is None else str(derived)
    r.counts["cpl_target_reason"] = why
    current = config["targets"].get("cpl_target")
    if derived is None:
        print(f"cpl_target: not derived ({why}); config targets.cpl_target is {current}")
    else:
        print(f"cpl_target: derived {derived} ({why}); config targets.cpl_target is {current}: Sam writes it as sam_admin (FR-40)")


def write_learnings(conn: wh.Connection, r: wh.Run, *, client_id: Any, config: dict[str, Any], window: dict[str, str]) -> list[dict[str, Any]]:
    """FR-41: one arm per component value against the rest of the client's creatives, on link CTR."""
    kill = int(config["targets"]["kill_impressions"])
    reached = int(conn.execute(SAMPLE_REACHED_SQL, (client_id, kill)).fetchone()["n"])
    r.counts["sample_reached"] = reached
    rows = conn.execute(ARMS_SQL, (list(LEARNING_COMPONENTS), client_id)).fetchall()
    per_creative: dict[Any, dict[str, int]] = {}
    groups: dict[tuple[str, str], set[Any]] = {}
    for row in rows:
        per_creative[row["creative_id"]] = {"impressions": int(row["impressions"]), "link_clicks": int(row["link_clicks"])}
        groups.setdefault((row["component_type"], row["component_ref"]), set()).add(row["creative_id"])
    written: list[dict[str, Any]] = []
    reasons: list[str] = []
    r.counts.setdefault("learnings_written", 0)
    r.counts.setdefault("learnings_updated", 0)
    for (ctype, cref), members in sorted(groups.items()):
        rest_ids = set(per_creative) - members
        if not rest_ids:
            continue
        arm = {k: sum(per_creative[c][k] for c in members) for k in ("impressions", "link_clicks")}
        rest = {k: sum(per_creative[c][k] for c in rest_ids) for k in ("impressions", "link_clicks")}
        if arm["impressions"] == 0 and rest["impressions"] == 0:
            continue
        fields, why = learning_gate(arm, rest)
        if fields is None:
            reasons.append(f"{ctype}={cref}: {why}")
            continue
        hypothesis = (f"{ctype}={cref} {'beats' if fields['direction'] == 'beat' else 'misses'} the other creatives on link CTR "
                      f"({fields['ctr_a']:.2%} vs {fields['ctr_b']:.2%}, {len(members)} vs {len(rest_ids)} creatives)")
        evidence = {"metric": "link_ctr", "arm": {**arm, "creatives": sorted(str(c) for c in members)},
                    "rest": {**rest, "creatives": sorted(str(c) for c in rest_ids)}, "relative_effect": fields["relative"],
                    "gates": {"min_clicks_per_arm": MIN_CLICKS_PER_ARM, "min_effect_abs": MIN_EFFECT_ABS, "min_effect_rel": MIN_EFFECT_REL,
                              "min_posterior": MIN_POSTERIOR}, "window": window, "sample_reached": True}
        existing = conn.execute(
            "select id from learnings where client_id = %s and component_type = %s and component_ref = %s and direction = %s"
            " and created_by = 'agent' and status in ('proposed', 'supported') order by created_at desc limit 1",
            (client_id, ctype, cref, fields["direction"])).fetchone()
        if existing:
            conn.execute("update learnings set posterior = %s, effect_size = %s, sample = %s, evidence = %s, updated_at = now() where id = %s",
                         (fields["posterior"], fields["effect_size"], fields["sample"], Jsonb(evidence), existing["id"]))
            r.count("learnings_updated")
            print(f"learning updated: {hypothesis} (posterior {fields['posterior']})")
            continue
        row = wh.insert_learnings(conn, client_id=client_id, scope="client", hypothesis=hypothesis, component_type=ctype, component_ref=cref,
                                  direction=fields["direction"], effect_size=fields["effect_size"], sample=fields["sample"],
                                  posterior=fields["posterior"], evidence=evidence, status="proposed", created_by="agent")
        r.count("learnings_written")
        written.append(row)
        print(f"learning proposed: {hypothesis} (effect {fields['effect_size'] * 100:+.2f}pp, posterior {fields['posterior']})")
    conn.commit()
    r.counts["learnings_refused"] = reasons
    warnings = r.counts.setdefault("warnings", [])
    if reached and not written and not r.counts["learnings_updated"] and not reasons:
        warnings.append(f"zero learnings: {reached} creative(s) at sample size ({kill} impressions), no learning written and no gate reason recorded")
    elif reached and not written and not r.counts["learnings_updated"]:
        print(f"learnings: {reached} creative(s) at sample size; nothing passed the FR-41 gates ({len(reasons)} reason(s) recorded)")
    for w in warnings:
        print(f"WARNING {w}")
    return written


def sam_learning(conn: wh.Connection, r: wh.Run, *, client_id: Any, text: str) -> dict[str, Any]:
    """Stop point D: Sam's first learnings row by hand (FR-41): `created_by='sam'`, `status='proposed'`,
    `evidence.sample_reached=false`. Nothing is inferred from the text."""
    text = text.strip()
    if not text:
        raise LoopRefused("--learning needs the hypothesis text")
    row = wh.insert_learnings(conn, client_id=client_id, scope="client", hypothesis=text, status="proposed", created_by="sam",
                              evidence={"sample_reached": False, "channel": "chat"})
    conn.commit()
    r.count("learnings_written_by_sam")
    print(f"learning (sam, proposed, sample_reached=false) [{str(row['id'])[:8]}]: {text}")
    return row


# ---------- main ----------

def pull(conn: wh.Connection, r: wh.Run, meta: MetaAds, *, client: dict[str, Any], config: dict[str, Any], today: date, days: int) -> dict[str, Any]:
    since, until = today - timedelta(days=days), today
    window = {"since": since.isoformat(), "until": until.isoformat(), "fetched_on": today.isoformat()}
    pull_metrics(conn, r, meta, client_id=client["id"], since=since, until=until, fetched_on=today)
    pull_spend(conn, r, meta, client_id=client["id"], today=today)
    levers = update_levers(conn, r, client_id=client["id"], config=config)
    proposals = propose_kill_scale(conn, r, client=client, config=config, window=window)
    report_cpl_target(conn, r, client_id=client["id"], config=config)
    learnings = write_learnings(conn, r, client_id=client["id"], config=config, window=window)
    return {"levers": levers, "proposals": proposals, "learnings": learnings}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Pull insights, select levers, propose kill/scale, write gated learnings. SKILL.md §3 `pull insights`.")
    p.add_argument("--client", default="upclicklabs")
    p.add_argument("--today", type=date.fromisoformat, default=None, help="the fetch date and window end (default: today)")
    p.add_argument("--days", type=int, default=7, help="window length in days before --today")
    p.add_argument("--learning", default=None, help="stop point D: write Sam's proposed learning by hand (sample_reached=false); no pull")
    args = p.parse_args(argv)
    load_env()
    today = args.today or date.today()
    with wh.connect("worker", job="pull_insights") as conn:
        client = wh.client_by_slug(conn, args.client)
        if client is None:
            print(f"pull_insights: no client with slug {args.client!r}", file=sys.stderr)
            return 1
        try:
            with wh.run(conn, WORKER, client["id"]) as r:
                state = wh.where_are_we(conn, args.client)
                print(wh.format_where_are_we(state))
                if state["actions_stuck"]:
                    raise LoopRefused(f"{state['actions_stuck']} action(s) in 'applying'; only apply_actions.py --reconcile may run")
                config = client.get("config") or {}
                check_config(config, client)
                if args.learning is not None:
                    sam_learning(conn, r, client_id=client["id"], text=args.learning)
                else:
                    if paused(client):
                        raise LoopRefused("pipeline paused (clients.paused or PIPELINE_PAUSED); `pull insights` may not run")
                    pull(conn, r, get_meta(), client=client, config=config, today=today, days=max(0, args.days))
        except LoopRefused as exc:
            print(f"pull_insights: {exc}", file=sys.stderr)
            return 2
        print(f"runs {r.id}: ok {json.dumps(r.counts, sort_keys=True, default=str)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
