#!/usr/bin/env python3
"""`launch` (T9): the launcher. SKILL.md §3, §5.3; PRD FR-1, FR-30, FR-31, FR-32, FR-37 (proposal side).

    python3 scripts/meta_launch.py [--client upclicklabs]

Never calls Meta (FR-30). One invocation, as `worker_rw`, does two things and stops for Sam (stop point C):

  1. Creatives whose latest `sam` gate verdict is `approve`, that have no `ad_entities` row and sit in no
     pending `build_campaign` proposal, become ONE proposed `build_campaign` action per experiment: one
     `new_recipes` campaign, one ad set per recipe (= chosen brief) at `config.campaign.adset_daily_budget`,
     both executions as paused ads inside it, `QuizStart` optimisation, broad targeting (geo + age from
     config), ad URLs = the creative's `landing_page` component + `utm_content=<creative_id>` (FR-32). The `campaigns` row is written
     here with explicit `terminal_metric` (from the offer) and `optimisation_event` (from config), never the
     schema defaults (FR-1); the executor fills `external_id` when Sam applies it. The validator
     (`warehouse/launch.py`) refuses ad sets mixing renderers (FR-22), more ad sets than
     `campaign.adsets_max`, a budget over `daily_cap` with what already spends (FR-31), a URL without
     `utm_content = creative_id`, and a creative without full components (FR-21). `proposal_key` is a hash of
     the creative set, so running twice yields one action (the second run reprints it).
  2. A built campaign (external id present, every ad PAUSED and never launched, its build applied) gets ONE
     proposed cascade `activate` (campaign + ad sets + ads in one action) when no ad is DISAPPROVED (FR-37) and
     the cap holds with every ad set budget applied; otherwise the refusal names the ads or the numbers.

Nothing approved: refuse and say so (gate B shipped nothing). Every run opens and closes a `runs` row
(worker `launcher`); refusals close it `failed` with the reason and exit 2.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import OrderedDict
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.env import load_env  # noqa: E402
from warehouse import client as wh  # noqa: E402
from warehouse.launch import ACTIVE_BUDGET_SQL, ProposalInvalid, ad_url, cap_check, validate_build_campaign  # noqa: E402

WORKER = "launcher"
OBJECTIVE = "OUTCOME_LEADS"
REQUIRED_CONFIG = (("targets", "ctr_floor"), ("targets", "kill_impressions"),
                   ("campaign", "optimisation_event"), ("campaign", "adset_daily_budget"), ("campaign", "adsets_max"),
                   ("campaign", "geo"), ("campaign", "age"))
TRUTHY = ("1", "true", "yes", "on")


class LaunchRefused(RuntimeError):
    """`launch` refused; the message says why. The runs row closes `failed` with it."""


# ---------- reads ----------

# The latest `sam` verdict per creative decides (SKILL.md §5.2); an agent row never ships anything on its own.
APPROVED_SQL = """
with latest_sam as (
  select distinct on (g.creative_id) g.creative_id, g.id as gate_score_id, g.verdict
    from gate_scores g join creatives c on c.id = g.creative_id
   where c.client_id = %s and g.scored_by = 'sam'
   order by g.creative_id, g.attempt desc, g.created_at desc
)
select c.*, ls.gate_score_id, b.source_pattern_id, b.family as brief_family, b.spec as brief_spec,
       b.created_at as brief_created_at, e.name as experiment_name, e.created_at as experiment_created_at
  from creatives c
  join latest_sam ls on ls.creative_id = c.id and ls.verdict = 'approve'
  left join briefs b on b.id = c.brief_id
  left join experiments e on e.id = c.experiment_id
 where c.client_id = %s and c.status not in ('killed', 'archived')
   and not exists (select 1 from ad_entities a where a.creative_id = c.id)
 order by e.created_at nulls last, b.created_at nulls last, c.created_at, c.id;
"""

PENDING_CREATIVES_SQL = """
select a.id as action_id, a.status, ad->>'creative_id' as creative_id
  from actions a, jsonb_array_elements(coalesce(a.proposal->'ad_sets', '[]'::jsonb)) s,
       jsonb_array_elements(coalesce(s->'ads', '[]'::jsonb)) ad
 where a.client_id = %s and a.action_type = 'build_campaign' and a.status in ('proposed','approved','applying','applied','failed');
"""

BUILT_AWAITING_ACTIVATION_SQL = """
select c.* from campaigns c
 where c.client_id = %s and c.external_id is not null and c.status = 'PAUSED'
   and exists (select 1 from ad_entities a where a.campaign_id = c.id)
   and not exists (select 1 from ad_entities a where a.campaign_id = c.id and (a.status <> 'PAUSED' or a.launched_at is not null))
   and exists (select 1 from actions x where x.target_type = 'campaign' and x.target_id = c.id::text
                 and x.action_type = 'build_campaign' and x.status = 'applied')
   and not exists (select 1 from actions x where x.target_type = 'campaign' and x.target_id = c.id::text
                     and x.action_type in ('build_campaign', 'activate') and x.status in ('proposed','approved','applying'))
 order by c.created_at, c.id;
"""

NUMBER_SQL = "select n from (select id, row_number() over (order by created_at, id) as n from actions where client_id = %s) x where id = %s"


def check_config(config: dict[str, Any], client: dict[str, Any]) -> None:
    """SKILL.md §0 step 1 (`daily_cap` and `currency` are columns of the clients row) plus the campaign shape."""
    missing = [k for k in ("daily_cap", "currency") if client.get(k) is None]
    for path in REQUIRED_CONFIG:
        node: Any = config
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            missing.append(".".join(path))
    if missing:
        raise LaunchRefused(f"clients.config for {client['slug']!r} is missing {', '.join(missing)}; refusing to run")
    age = config["campaign"]["age"]
    if not (isinstance(age, list) and len(age) == 2):
        raise LaunchRefused("config.campaign.age must be [min, max]")


def paused(client: dict[str, Any]) -> bool:
    return bool(client.get("paused")) or (os.environ.get("PIPELINE_PAUSED") or "").strip().lower() in TRUTHY


def action_number(conn: wh.Connection, client_id: Any, action_id: Any) -> int:
    row = conn.execute(NUMBER_SQL, (client_id, action_id)).fetchone()
    return int(row["n"]) if row else 0


def trust_level(config: dict[str, Any], action_type: str) -> str:
    level = ((config.get("trust") or {}).get(action_type) or {}).get("level")
    return level if level in ("propose", "execute") else "propose"


def creative_hash(ids: list[Any]) -> str:
    return hashlib.sha256("\n".join(sorted(str(i) for i in ids)).encode()).hexdigest()[:16]


# ---------- build_campaign ----------

def landing_page_for(creative_id: Any, refs: dict[str, dict[str, str]], offer: dict[str, Any]) -> str:
    """The URL the ad sends people to: the creative's `landing_page` component (what the gate's `landing` check saw),
    else the producer's own rule (`offers.landing_url`, else `<funnel_host>/quiz`)."""
    ref = (refs.get(str(creative_id)) or {}).get("landing_page")
    if ref:
        return ref
    if offer.get("landing_url"):
        return offer["landing_url"]
    host = (offer.get("funnel_host") or os.environ.get("FUNNEL_HOST") or "").rstrip("/")
    if not host:
        raise LaunchRefused("no landing_page component, offers.landing_url, offers.funnel_host or FUNNEL_HOST; ad URLs need a page (FR-32)")
    return f"{host}/quiz"


def build_proposal(*, slug: str, campaign_name: str, creatives: list[dict[str, Any]], offer: dict[str, Any],
                   config: dict[str, Any], currency: str, funnel_host: str,
                   experiment_id: Any, components: dict[str, set[str]], refs: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """One `new_recipes` campaign; one ad set per recipe (brief), in proposal order; the creatives of the brief as
    its ads, created paused. Names are deterministic so the executor's name lookup finds what a crashed run
    created (SKILL.md §6 step 6). Raises LaunchRefused for a creative that cannot be placed."""
    by_brief: "OrderedDict[Any, list[dict[str, Any]]]" = OrderedDict()
    for c in creatives:
        if c.get("brief_id") is None:
            raise LaunchRefused(f"creative {c['id']} has no brief; an ad set is one recipe (FR-31) and this creative belongs to none")
        by_brief.setdefault(c["brief_id"], []).append(c)
    camp_cfg = config["campaign"]
    budget = str(Decimal(str(camp_cfg["adset_daily_budget"])))
    event = camp_cfg["optimisation_event"]
    age_min, age_max = camp_cfg["age"]
    ad_sets = []
    for n, (brief_id, group) in enumerate(by_brief.items(), start=1):
        family = group[0].get("brief_family") or "recipe"
        adset_name = f"{campaign_name}-as{n}-{family}"
        ads = []
        for m, c in enumerate(group, start=1):
            for field, label in (("asset_urls", "asset_urls"), ("headline", "headline"), ("primary_text", "primary_text")):
                if not c.get(field):
                    raise LaunchRefused(f"creative {c['id']} has no {label}; it cannot become an ad (producer output incomplete)")
            if c.get("renderer") not in ("html_template", "image_to_image"):
                raise LaunchRefused(f"creative {c['id']} has renderer {c.get('renderer')!r}; expected html_template or image_to_image")
            ad_name = f"{adset_name}-ad{m}-{str(c['id'])[:8]}"
            ads.append({"name": ad_name, "creative_name": f"{ad_name}-creative", "creative_id": str(c["id"]),
                        "renderer": c["renderer"],
                        "link_url": ad_url(landing_page_for(c["id"], refs or {}, offer), campaign_name=campaign_name, creative_id=str(c["id"])),
                        "image_url": c["asset_urls"][0], "title": c["headline"], "body": c["primary_text"],
                        "gate_score_id": str(c["gate_score_id"])})
        renderers = sorted({a["renderer"] for a in ads})
        ad_sets.append({"name": adset_name, "brief_id": str(brief_id), "recipe_pattern_id": None if group[0].get("source_pattern_id") is None else str(group[0]["source_pattern_id"]),
                        "family": family, "renderer": renderers[0] if len(renderers) == 1 else "mixed",
                        "daily_budget": budget, "optimisation_event": event,
                        "targeting": {"geo": list(camp_cfg["geo"]), "age_min": int(age_min), "age_max": int(age_max)},
                        "ads": ads})
    return {
        "campaign": {"name": campaign_name, "kind": "new_recipes", "objective": OBJECTIVE, "currency": currency,
                     "terminal_metric": offer.get("terminal_metric") or "booked_call", "optimisation_event": event,
                     "experiment_id": None if experiment_id is None else str(experiment_id), "offer_id": str(offer["id"]),
                     "funnel_host": funnel_host},
        "ad_sets": ad_sets,
        "cap_check": {},
    }


def propose_builds(conn: wh.Connection, r: wh.Run, *, client: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Returns the build_campaign actions this run proposed or reprinted (one per experiment with approved,
    unlaunched creatives). Raises LaunchRefused when nothing is approved or a proposal fails validation."""
    client_id, slug = client["id"], client["slug"]
    rows = conn.execute(APPROVED_SQL, (client_id, client_id)).fetchall()
    pending = conn.execute(PENDING_CREATIVES_SQL, (client_id,)).fetchall()
    pending_ids = {p["creative_id"] for p in pending}
    r.counts.update(creatives_approved=len(rows), creatives_pending=sum(1 for c in rows if str(c["id"]) in pending_ids))
    fresh = [c for c in rows if str(c["id"]) not in pending_ids]
    open_builds = conn.execute(
        "select * from actions where client_id = %s and action_type = 'build_campaign' and status in ('proposed','approved','applying','failed')"
        " order by created_at, id", (client_id,)).fetchall()
    if not fresh:
        if open_builds:
            for a in open_builds:
                r.count("reprinted")
                print(format_build(a, action_number(conn, client_id, a["id"]), client))
            return open_builds
        raise LaunchRefused("no creative with a `sam` approve verdict is waiting to launch; the gate (B) shipped nothing, "
                            "so there is nothing to build (`verdicts: approve …` first)")

    offer = conn.execute("select * from offers where client_id = %s order by created_at limit 1", (client_id,)).fetchone()
    if offer is None:
        raise LaunchRefused("no offers row for this client; run scripts/dev_db.sh --seed")
    funnel_host = offer.get("funnel_host") or os.environ.get("FUNNEL_HOST") or ""
    ids = [c["id"] for c in fresh]
    comp_rows = conn.execute("select creative_id, component_type, component_ref from creative_components where creative_id = any(%s)"
                             " order by creative_id, component_type, component_ref", (ids,)).fetchall()
    components: dict[str, set[str]] = {}
    refs: dict[str, dict[str, str]] = {}
    for row in comp_rows:
        components.setdefault(str(row["creative_id"]), set()).add(row["component_type"])
        refs.setdefault(str(row["creative_id"]), {}).setdefault(row["component_type"], row["component_ref"])
    active = conn.execute(ACTIVE_BUDGET_SQL, (client_id, client_id)).fetchone()["active"]
    n_builds = conn.execute("select count(*) as n from actions where client_id = %s and action_type = 'build_campaign'", (client_id,)).fetchone()["n"]

    by_experiment: "OrderedDict[Any, list[dict[str, Any]]]" = OrderedDict()
    for c in fresh:
        by_experiment.setdefault(c["experiment_id"], []).append(c)
    out: list[dict[str, Any]] = []
    for exp_id, group in by_experiment.items():
        exp_name = group[0].get("experiment_name") or "unbatched"
        key = f"build_campaign:{client_id}:{exp_id}:{creative_hash([c['id'] for c in group])}"
        existing = conn.execute("select * from actions where proposal_key = %s", (key,)).fetchone()
        if existing is not None:
            r.count("reprinted")
            print(format_build(existing, action_number(conn, client_id, existing["id"]), client))
            out.append(existing)
            continue
        suffix = "" if int(n_builds) == 0 else f"-r{int(n_builds) + 1}"
        n_builds = int(n_builds) + 1
        campaign_name = f"{slug}-{exp_name}-new_recipes{suffix}"
        proposal = build_proposal(slug=slug, campaign_name=campaign_name, creatives=group, offer=offer, config=config,
                                  currency=client["currency"], funnel_host=funnel_host, experiment_id=exp_id, components=components, refs=refs)
        try:
            proposed = validate_build_campaign(proposal, daily_cap=client["daily_cap"], active_budget=active,
                                               adsets_max=int(config["campaign"]["adsets_max"]), components_by_creative=components)
        except ProposalInvalid as exc:
            r.count("proposals_refused")
            raise LaunchRefused(f"{exp_name}: {exc}") from exc
        proposal["cap_check"] = cap_check(daily_cap=client["daily_cap"], active_budget=active, proposed=proposed)
        campaign = wh.insert_campaigns(
            conn, client_id=client_id, offer_id=offer["id"], platform="meta", kind="new_recipes", currency=client["currency"],
            terminal_metric=proposal["campaign"]["terminal_metric"], optimisation_event=proposal["campaign"]["optimisation_event"],
            status="PAUSED")                                                                                   # FR-1: explicit
        evidence = {"experiment": exp_name, "experiment_id": None if exp_id is None else str(exp_id),
                    "creative_ids": [str(c["id"]) for c in group],
                    "gate_score_ids": {str(c["id"]): str(c["gate_score_id"]) for c in group},
                    "ad_sets": len(proposal["ad_sets"]), "ads": sum(len(s["ads"]) for s in proposal["ad_sets"]),
                    "cap_check": proposal["cap_check"]}
        action = wh.insert_actions(
            conn, client_id=client_id, action_type="build_campaign", target_type="campaign", target_id=str(campaign["id"]),
            rule="launch_approved_creatives", proposal=proposal, proposal_key=key, evidence=evidence,
            trust_level_at_proposal=trust_level(config, "build_campaign"))
        conn.commit()
        r.count("proposed")
        r.count("ad_sets", len(proposal["ad_sets"]))
        r.count("ads", evidence["ads"])
        print(format_build(action, action_number(conn, client_id, action["id"]), client))
        out.append(action)
    return out


def format_build(a: dict[str, Any], n: int, client: dict[str, Any]) -> str:
    """Stop point C: campaign, ad sets, budgets, ads, cap check result, and the reply Sam sends."""
    p, camp, cur = a["proposal"] or {}, (a["proposal"] or {}).get("campaign") or {}, client.get("currency") or ""
    lines = [f"\nbuild_campaign #{n} [{str(a['id'])[:8]}] {a['status']}: {camp.get('name')}"
             f"  kind={camp.get('kind')}  objective={camp.get('objective')}  optimisation_event={camp.get('optimisation_event')}"
             f"  terminal_metric={camp.get('terminal_metric')}  {camp.get('currency')}"]
    for i, s in enumerate(p.get("ad_sets") or [], start=1):
        t = s.get("targeting") or {}
        lines.append(f"  ad set {i}  {s.get('name')}  {cur} {s.get('daily_budget')}/day  {s.get('renderer')}"
                     f"  geo {','.join(t.get('geo') or [])}  age {t.get('age_min')}-{t.get('age_max')}  {len(s.get('ads') or [])} ad(s), paused")
        for ad in s.get("ads") or []:
            lines.append(f"      ad  {ad.get('name')}  creative {ad.get('creative_id')}  {ad.get('link_url')}")
    cc = p.get("cap_check") or {}
    lines.append(f"  cap check  active {cc.get('active_budget')} + proposed {cc.get('proposed_budget')} <= daily_cap {cc.get('daily_cap')}"
                 f" -> {'ok' if cc.get('ok') else 'EXCEEDED'}")
    if a["status"] == "proposed":
        lines.append(f"Reply `approve {n}` (scripts/decide.py) then run `apply actions`. Default after 20 minutes: nothing is applied.")
    elif a["status"] == "failed":
        lines.append(f"  last_error: {a.get('last_error')}  (re-approve with `approve {n}` to retry)")
    return "\n".join(lines)


# ---------- activate ----------

def propose_activations(conn: wh.Connection, r: wh.Run, *, client: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """One cascade `activate` per built, never-launched campaign whose ads are all reviewable and whose ad set
    budgets fit the cap next to what already spends. Refusals are printed and counted, never proposed."""
    client_id = client["id"]
    out: list[dict[str, Any]] = []
    for camp in conn.execute(BUILT_AWAITING_ACTIVATION_SQL, (client_id,)).fetchall():
        ads = conn.execute("select * from ad_entities where campaign_id = %s order by adset_id, created_at, id", (camp["id"],)).fetchall()
        disapproved = [a for a in ads if a.get("review_status") == "DISAPPROVED"]
        if disapproved:
            r.count("activate_refused_disapproved")
            print(f"activate refused for campaign {camp['external_id']}: {len(disapproved)} DISAPPROVED ad(s) "
                  f"{', '.join(a['ad_id'] for a in disapproved)} (FR-37); fix or archive them first")
            continue
        per_set: dict[Any, Decimal] = {}
        for a in ads:
            per_set[a["adset_id"]] = max(per_set.get(a["adset_id"], Decimal(0)), Decimal(str(a["adset_daily_budget"] or 0)))
        active = conn.execute(ACTIVE_BUDGET_SQL, (client_id, client_id)).fetchone()["active"]
        check = cap_check(daily_cap=client["daily_cap"], active_budget=active, proposed=sum(per_set.values(), Decimal(0)))
        if not check["ok"]:
            r.count("activate_refused_cap")
            print(f"activate refused for campaign {camp['external_id']}: active {check['active_budget']} + {check['proposed_budget']}"
                  f" exceeds daily_cap {check['daily_cap']} (FR-31)")
            continue
        ids = [str(a["id"]) for a in ads]
        key = f"activate:{camp['id']}:{creative_hash(ids)}"
        existing = conn.execute("select * from actions where proposal_key = %s", (key,)).fetchone()
        if existing is not None:
            r.count("reprinted")
            print(format_activate(existing, action_number(conn, client_id, existing["id"]), camp, ads))
            out.append(existing)
            continue
        evidence = {"campaign_external_id": camp["external_id"], "ad_sets": len(per_set), "ads": len(ads),
                    "review_status": {s: sum(1 for a in ads if a.get("review_status") == s) for s in sorted({a.get("review_status") for a in ads})},
                    "cap_check": check}
        action = wh.insert_actions(
            conn, client_id=client_id, action_type="activate", target_type="campaign", target_id=str(camp["id"]),
            rule="launch_activate_built_campaign", proposal={"cascade": True, "ad_entity_ids": ids}, proposal_key=key,
            evidence=evidence, trust_level_at_proposal=trust_level(config, "activate"))
        conn.commit()
        r.count("activate_proposed")
        print(format_activate(action, action_number(conn, client_id, action["id"]), camp, ads))
        out.append(action)
    return out


def format_activate(a: dict[str, Any], n: int, camp: dict[str, Any], ads: list[dict[str, Any]]) -> str:
    ev = a["evidence"] or {}
    cc = ev.get("cap_check") or {}
    sets = sorted({x["adset_id"] for x in ads})
    lines = [f"\nactivate #{n} [{str(a['id'])[:8]}] {a['status']}: campaign {camp['external_id']} -> ACTIVE with {len(sets)} ad set(s) and {len(ads)} ad(s)"]
    for s in sets:
        ids = [x["ad_id"] for x in ads if x["adset_id"] == s]
        budget = max((x["adset_daily_budget"] or 0) for x in ads if x["adset_id"] == s)
        lines.append(f"  ad set {s}  {budget}/day  ads {', '.join(ids)}")
    lines.append(f"  review_status {json.dumps(ev.get('review_status') or {}, sort_keys=True)}")
    lines.append(f"  cap check  active {cc.get('active_budget')} + {cc.get('proposed_budget')} <= daily_cap {cc.get('daily_cap')} -> {'ok' if cc.get('ok') else 'EXCEEDED'}")
    if a["status"] == "proposed":
        lines.append(f"Reply `approve {n}` (scripts/decide.py) then run `apply actions`; the ads start spending. Default after 20 minutes: nothing is applied.")
    return "\n".join(lines)


# ---------- main ----------

def launch(conn: wh.Connection, r: wh.Run, *, client: dict[str, Any], config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    activations = propose_activations(conn, r, client=client, config=config)
    try:
        builds = propose_builds(conn, r, client=client, config=config)
    except LaunchRefused:
        if activations:      # a campaign is waiting for activation: that is the stop point, not a failure
            r.count("build_skipped_nothing_new")
            builds = []
        else:
            raise
    return {"build_campaign": builds, "activate": activations}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Propose build_campaign / activate for approved creatives. SKILL.md §3 `launch`.")
    p.add_argument("--client", default="upclicklabs")
    args = p.parse_args(argv)
    load_env()
    with wh.connect("worker", job="launch") as conn:
        client = wh.client_by_slug(conn, args.client)
        if client is None:
            print(f"launch: no client with slug {args.client!r}", file=sys.stderr)
            return 1
        try:
            with wh.run(conn, WORKER, client["id"]) as r:
                state = wh.where_are_we(conn, args.client)
                print(wh.format_where_are_we(state))
                if state["actions_stuck"]:
                    raise LaunchRefused(f"{state['actions_stuck']} action(s) in 'applying'; only apply_actions.py --reconcile may run")
                config = client.get("config") or {}
                check_config(config, client)
                if paused(client):
                    raise LaunchRefused("pipeline paused (clients.paused or PIPELINE_PAUSED); `launch` may not run")
                launch(conn, r, client=client, config=config)
        except LaunchRefused as exc:
            print(f"launch: {exc}", file=sys.stderr)
            return 2
        print(f"runs {r.id}: ok {json.dumps(r.counts, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
