#!/usr/bin/env python3
"""`plan batch` / `my picks` (T4): the angle planner. SKILL.md §3, §4.2, §5.1; PRD FR-7 (guard), FR-8
(consumer), FR-14 to FR-20.

    python3 scripts/plan_batch.py [--client upclicklabs] [--daily-budget 45] [--cpm 25] [--today YYYY-MM-DD]
    python3 scripts/plan_batch.py --select "2, 5, 9"                # Sam's picks (§5.1), optional `n: reason`
    python3 scripts/plan_batch.py --select default                  # Sam quiet 20 minutes: the ranker's top N

`plan batch`:
  1. opens a `runs` row (worker `planner`), prints "where are we", refuses when paused, when any action is
     `applying`, or when an inspo source failed twice without acknowledgement (FR-8, named);
  2. reads before planning (FR-14): learnings, `mart_component_leaderboard` (creatives >= 3, by
     `link_ctr_lcb`), the config floors, `voc_phrases`, `patterns`; every query is listed in `runs.counts.queries`;
  3. capacity = floor(daily_budget * 7 * 1000 / (cpm * kill_impressions)) (FR-15; `daily_budget` is
     `clients.daily_cap`, cpm is the last 7 days' observed CPM when there is one, else `config.cpm_estimate`);
     a batch (recipes * executions_per_recipe) larger than capacity is refused with the number said;
  4. a batch is requested only when in-flight creatives below sample size + batch_size <= capacity (FR-16,
     CRUCIBLE A9), never on a calendar; otherwise the run closes `ok` with `batch_requested = 0`;
  5. ranks the external patterns deterministically: source strength x family diversity (FR-20, A21), skipping
     families retired for the client's ICP (FR-7 guard), and proposes recipes * proposals_multiplier briefs
     (FR-17), each a translation through the model adapter that may change only offer, product nouns, VOC
     phrases, imagery subject (FR-18): the format layer is copied verbatim, the offer layer from `offers.offer_layer`;
  6. writes `experiments` (with `capacity`), one `hooks` row and one `briefs` row per proposal, and prints the
     §5.1 numbered table; then waits for `my picks`.
`--select` records the `selections` row (proposed, chosen, rejected, reason, selected_by) and marks the chosen
briefs in `briefs.spec` (0003 grant). No ablation brief is created in phase 0; `ablation_allowed()` is the FR-19
guard only. Worker role only (`WAREHOUSE_URL_WORKER`); no side effect anywhere (SKILL.md §4 rule 1).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.env import ME_DIR, load_env, require  # noqa: E402
from adapters.model import Model, get_model  # noqa: E402
from warehouse import client as wh  # noqa: E402
from warehouse.client import Jsonb  # noqa: E402

WORKER = "planner"
TASK = "translate_brief"
PROMPTS = ME_DIR / "references" / "prompts" / "planner.md"
ALLOWED_INGREDIENTS = ("offer", "product_nouns", "voc_phrases", "imagery_subject")   # FR-18, SKILL.md §4 rule 5
FORMAT_LAYER_KEYS = ("family", "visual_structure", "copy_structure", "copy_length", "hook_type")
ABLATION_MAX_CHANGED = 3                                                              # FR-19, CRUCIBLE A7
RANKER_LEARNS_AFTER_SELECTIONS = 4                                                    # FR-20, A21
MAX_VOC_IN_PROMPT = 24
REQUIRED_CONFIG = (("targets", "ctr_floor"), ("targets", "kill_impressions"), ("daily_cap",), ("currency",),
                   ("cpm_estimate",), ("batch", "recipes"), ("batch", "executions_per_recipe"),
                   ("batch", "proposals_multiplier"))


class PlannerRefused(RuntimeError):
    """`plan batch` or `--select` refused; the message says why. The runs row closes `failed` with it."""


class PipelinePaused(PlannerRefused):
    pass


class ConfigMissing(PlannerRefused):
    pass


class SourceBlocked(PlannerRefused):
    """FR-8: an inspo source failed twice in a row and Sam has not acknowledged it."""


class CapacityExceeded(PlannerRefused):
    """FR-15: the configured batch is larger than capacity."""


class BriefInvalid(ValueError):
    """The planner's validator refused a brief (FR-18 translation discipline, FR-7 retired family, ...)."""


class BudgetExceeded(PlannerRefused):
    """`clients.config.worker_budgets.planner.tokens` spent before the proposals were complete."""


# ---------- pure rules (unit-tested) ----------

def capacity(daily_budget: float, cpm: float, kill_impressions: int) -> int:
    """FR-15: creatives that can reach sample size in a week. At 30/day, CPM 25, 2000 impressions -> 4."""
    if daily_budget <= 0 or cpm <= 0 or kill_impressions <= 0:
        raise ConfigMissing(f"capacity needs positive daily_budget ({daily_budget}), cpm ({cpm}), kill_impressions ({kill_impressions})")
    return math.floor(daily_budget * 7 * 1000 / (cpm * kill_impressions))


def min_daily_budget(batch_size: int, cpm: float, kill_impressions: int) -> float:
    """The smallest daily budget at which `capacity()` reaches `batch_size` (what the refusal tells Sam)."""
    return math.ceil(batch_size * cpm * kill_impressions / 7000 * 100) / 100


def batch_requested(in_flight_below_sample: int, cap: int, batch_size: int) -> bool:
    """FR-16 / CRUCIBLE A9, the threshold event: a batch is wanted only when it still fits next to the creatives
    that have not reached sample size. With 4 in flight and capacity 4 nothing fits, whatever the batch size.
    Read as `in_flight + batch_size <= capacity`: FR-16's strict `<` would make batch one (6 creatives at
    capacity 6, spec.md decision 1) impossible, which FR-15's own AC rules out."""
    return in_flight_below_sample + batch_size <= cap


def rank_patterns(patterns: list[dict[str, Any]], n: int, retired: set[str] = frozenset()) -> list[dict[str, Any]]:
    """FR-20 / A21: deterministic ranker, source strength x family diversity, until four `selections` exist.
    Greedy: each step takes the pattern with the highest (source_strength + 1) / (1 + already picked in its family);
    the +1 keeps diversity separating zero-strength candidates. Ties break on proven first, then brand, then
    source ad id, so the same inputs always give the same order. Patterns of a retired family never rank (FR-7)."""
    pool = [p for p in patterns if p["family"] not in retired and p.get("status") in ("proven", "candidate") and complete_format_layer(p)]
    picked: list[dict[str, Any]] = []
    per_family: dict[str, int] = {}

    def key(p: dict[str, Any]) -> tuple:
        score = (int(p.get("source_strength") or 0) + 1) / (1 + per_family.get(p["family"], 0))
        return (-score, 0 if p.get("status") == "proven" else 1, p.get("source_brand") or "", _ad_id(p), str(p["id"]))

    while pool and len(picked) < n:
        best = min(pool, key=key)
        pool.remove(best)
        picked.append(best)
        per_family[best["family"]] = per_family.get(best["family"], 0) + 1
    return picked


def complete_format_layer(p: dict[str, Any]) -> bool:
    """A pattern can be replicated only when its format layer carries all five keys (FR-5, FR-18); the intel
    worker writes them, but a row without them is skipped and counted, never briefed."""
    layer = (p.get("recipe") or {}).get("format_layer") or {}
    return all(layer.get(k) for k in FORMAT_LAYER_KEYS) and layer.get("family") == p.get("family")


def _ad_id(p: dict[str, Any]) -> str:
    return str(((p.get("recipe") or {}).get("source") or {}).get("ad_id") or "")


def ablation_allowed(*, below_floor_at_sample: bool, source_status: str, changed_ingredients: list[str],
                     ablation_in_flight: bool) -> tuple[bool, str]:
    """FR-19 / CRUCIBLE A7: an ablation brief needs all three conditions and no other ablation running.
    Phase 0 never creates one; this is the guard the loop (T10) will call. Returns (allowed, reason)."""
    if not below_floor_at_sample:
        return False, "replica is not below the CTR floor at sample size"
    if source_status != "proven":
        return False, f"source pattern is {source_status!r}, not proven"
    if len(changed_ingredients) > ABLATION_MAX_CHANGED:
        return False, f"{len(changed_ingredients)} changed ingredients, more than {ABLATION_MAX_CHANGED}"
    if ablation_in_flight:
        return False, "an ablation is already in flight; one at a time"
    return True, "below floor at sample size, source proven, <= 3 changed ingredients, none in flight"


def validate_brief(values: dict[str, Any], *, retired: set[str], format_layer: dict[str, Any],
                   voc_count: int) -> dict[str, Any]:
    """FR-18 + FR-7: the brief changes only the allowed ingredients, copies the format layer verbatim, and is
    not in a family retired for the client's ICP. Anything else is refused before it touches the database."""
    changed = list(values.get("changed_ingredients") or [])
    bad = [c for c in changed if c not in ALLOWED_INGREDIENTS]
    if bad:
        raise BriefInvalid(f"changed_ingredients {bad} not in {list(ALLOWED_INGREDIENTS)} (FR-18)")
    if len(set(changed)) != len(changed):
        raise BriefInvalid("changed_ingredients has duplicates")
    if values.get("kind", "replica") == "replica" and values.get("source_pattern_id") and "offer" not in changed:
        raise BriefInvalid("a replica of an external pattern changes the offer; changed_ingredients must list 'offer'")
    fam = values.get("family")
    if fam in retired:
        raise BriefInvalid(f"family {fam!r} is retired for this client's ICP; it cannot be briefed (FR-7)")
    spec = values.get("spec") or {}
    if spec.get("format_layer") != format_layer or set(format_layer) != set(FORMAT_LAYER_KEYS):
        raise BriefInvalid("spec.format_layer is not the source pattern's format layer copied verbatim (FR-18)")
    if fam != format_layer["family"]:
        raise BriefInvalid("briefs.family disagrees with the format layer's family")
    if not (values.get("angle") or "").strip():
        raise BriefInvalid("angle is empty")
    ids = list(values.get("voc_phrase_ids") or [])
    if bool(ids) != ("voc_phrases" in changed):
        raise BriefInvalid("voc_phrase_ids and changed_ingredients disagree about 'voc_phrases'")
    idx = list(spec.get("voc_phrase_indexes") or [])
    if any(i < 0 or i >= voc_count for i in idx):
        raise BriefInvalid(f"voc_phrase_indexes {idx} out of range for {voc_count} phrases")
    if not (spec.get("hook_line") or "").strip():
        raise BriefInvalid("hook_line is empty")
    return values


def translate_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "hook_line": {"type": "string", "minLength": 1},
            "product_nouns": {"type": "array", "items": {"type": "string"}},
            "imagery_subject": {"type": "string"},
            "visual_spec": {"type": "string"},
            "voc_phrase_indexes": {"type": "array", "items": {"type": "integer", "minimum": 0}, "maxItems": 2},
            "changed_ingredients": {"type": "array", "items": {"type": "string", "enum": list(ALLOWED_INGREDIENTS)},
                                    "uniqueItems": True},
            "coherence_note": {"type": "string"},
        },
        "required": ["hook_line", "product_nouns", "imagery_subject", "visual_spec", "voc_phrase_indexes", "changed_ingredients"],
        "additionalProperties": False,
    }


def untrusted_pattern_text(pattern: dict[str, Any], voc: list[dict[str, Any]]) -> str:
    """The source recipe and the customer phrases, as data. URLs and the vendor row stay out of the prompt."""
    recipe = pattern.get("recipe") or {}
    src = recipe.get("source") or {}
    payload = {
        "source_recipe": {
            "family": pattern["family"], "variant": pattern.get("variant"), "hook_type": pattern.get("hook_type"),
            "angle": pattern.get("angle"), "source_brand": pattern.get("source_brand"),
            "format_layer": recipe.get("format_layer"), "hook_text": (recipe.get("decomposition") or {}).get("hook_text"),
            "source_text": src.get("text"),
        },
        "customer_phrases": [{"n": i, "category": v["category"], "visibility": v["visibility"], "phrase": v["phrase"]}
                             for i, v in enumerate(voc)],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1, default=str)


def offer_instructions(offer: dict[str, Any], icp: dict[str, Any] | None, config: dict[str, Any]) -> str:
    """The trusted half of the user turn: Sam's offer and ICP from config (DRAFT values are copied as they are)."""
    lines = [
        "", "Offer (ours):", f"- name: {offer.get('name')}", f"- promise: {offer.get('promise')}",
        f"- price anchor: {offer.get('price_anchor')}", f"- proof points: {', '.join(offer.get('proof_points') or []) or '-'}",
        f"- offer layer (fixed): {json.dumps(offer.get('offer_layer') or {}, sort_keys=True)}",
        f"- brand hard blocks: {', '.join(((config.get('brand') or {}).get('hard_blocks')) or []) or '-'}",
    ]
    if icp:
        lines += ["Audience (ICP):", f"- {icp.get('label')}", f"- role: {icp.get('role')}; company: {icp.get('company_type')}; "
                  f"size: {icp.get('size_band')}; geo: {', '.join(icp.get('geo') or [])}",
                  f"- pains: {'; '.join(icp.get('pains') or []) or '-'}", f"- outcomes: {'; '.join(icp.get('outcomes') or []) or '-'}"]
    return "\n".join(lines)


def load_prompts(path: Path = PROMPTS) -> tuple[str, str]:
    text = path.read_text()
    sections = re.split(r"^## (\w+)\s*$", text, flags=re.M)
    found = {sections[i].lower(): sections[i + 1].strip() for i in range(1, len(sections) - 1, 2)}
    if "system" not in found or "instructions" not in found:
        raise RuntimeError(f"{path} needs '## System' and '## Instructions' sections")
    return found["system"], found["instructions"]


def parse_picks(text: str) -> dict[int, str | None]:
    """`my picks: 2, 5, 9` with optional `n: reason` per pick (SKILL.md §5.1). `;` separates picks when a
    reason contains commas. Returns number -> reason, in the order given."""
    body = re.sub(r"^\s*my picks\s*:\s*", "", text.strip(), flags=re.I)
    parts = [p for p in re.split(r";" if ";" in body else r",", body) if p.strip()]
    picks: dict[int, str | None] = {}
    for part in parts:
        m = re.fullmatch(r"\s*(\d+)\s*(?::\s*(.*?))?\s*", part, flags=re.S)
        if not m:
            raise PlannerRefused(f"cannot read pick {part.strip()!r}; expected `n` or `n: reason`")
        n = int(m.group(1))
        if n in picks:
            raise PlannerRefused(f"pick {n} given twice")
        picks[n] = (m.group(2) or "").strip() or None
    if not picks:
        raise PlannerRefused("no picks given")
    return picks


# ---------- config and state ----------

def check_config(config: dict[str, Any]) -> None:
    for path in REQUIRED_CONFIG:
        node: Any = config
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            raise ConfigMissing(f"config is missing {'.'.join(path)}")


def paused(client: dict[str, Any]) -> bool:
    return bool(client.get("paused")) or os.environ.get("PIPELINE_PAUSED", "").strip().lower() in ("1", "true", "yes")


def batch_size(config: dict[str, Any]) -> int:
    return int(config["batch"]["recipes"]) * int(config["batch"]["executions_per_recipe"])


def proposals_wanted(config: dict[str, Any]) -> int:
    return int(config["batch"]["recipes"]) * int(config["batch"]["proposals_multiplier"])


class Reads:
    """Every read the planner does before proposing, logged for FR-14 (`runs.counts.queries`)."""

    def __init__(self, conn: wh.Connection, r: wh.Run):
        self.conn, self.r = conn, r
        self.r.counts.setdefault("queries", [])

    def q(self, label: str, sql_text: str, params: tuple = ()) -> list[dict[str, Any]]:
        self.r.counts["queries"].append(f"{label}: {' '.join(sql_text.split())}")
        return self.conn.execute(sql_text, params).fetchall()


RETIRED_FOR_ICP_SQL = """
select name as family from families where status = 'retired'
union
select a.target_id as family from actions a
 where a.client_id = %s and a.action_type = 'retire_family' and a.status = 'applied' and a.target_type = 'family'
   and (a.proposal->>'icp_id' is null or a.proposal->>'icp_id' = %s)
order by 1;
"""

IN_FLIGHT_SQL = """
select count(*) as n from creatives c
 left join mart_creative_performance p on p.creative_id = c.id
 where c.client_id = %s and c.status = 'live' and coalesce(p.impressions, 0) < %s;
"""

OBSERVED_CPM_SQL = """
select sum(m.spend) as spend, sum(m.impressions) as impressions
  from ad_metrics_latest m join ad_entities a on a.id = m.ad_entity_id
 where a.client_id = %s and m.day >= %s;
"""

PATTERNS_SQL = """
select p.* from patterns p join families f on f.name = p.family
 where p.origin = 'external' and p.status in ('proven', 'candidate') and f.kind = 'format'
 order by p.source_brand, p.recipe->'source'->>'ad_id', p.id;
"""

VOC_SQL = """
select id, phrase, category, visibility, source_weight, trust_tier from voc_phrases
 where client_id = %s order by source_weight desc, frequency desc, created_at, id limit %s;
"""

OPEN_EXPERIMENT_SQL = """
select e.* from experiments e
 where e.client_id = %s and e.kind = 'new_recipes'
   and not exists (select 1 from selections s where s.experiment_id = e.id)
 order by e.created_at desc limit 1;
"""


def retired_for_icp(reads: Reads, client_id: Any, icp_id: Any) -> set[str]:
    """FR-7: a family is retired for the ICP when `families.status='retired'` or an applied `retire_family` action
    for this client names it (scoped to the ICP when its proposal carries `icp_id`). The retire flow itself is
    cut from phase 0; only this read and the refusal exist."""
    return {row["family"] for row in reads.q("retired_families_for_icp", RETIRED_FOR_ICP_SQL, (client_id, str(icp_id) if icp_id else None))}


def open_experiment(conn: wh.Connection, client_id: Any) -> dict[str, Any] | None:
    return conn.execute(OPEN_EXPERIMENT_SQL, (client_id,)).fetchone()


def proposal_briefs(conn: wh.Connection, experiment_id: Any) -> list[dict[str, Any]]:
    rows = conn.execute("select b.*, h.text as hook_text from briefs b left join hooks h on h.id = b.hook_id "
                        "where b.experiment_id = %s", (experiment_id,)).fetchall()
    return sorted(rows, key=lambda b: int((b["spec"] or {}).get("proposal_number") or 0))


# ---------- the plan ----------

def plan(conn: wh.Connection, r: wh.Run, *, client: dict[str, Any], config: dict[str, Any], model: Model,
         today: date, daily_budget: float | None = None, cpm_override: float | None = None) -> dict[str, Any] | None:
    """Returns the new experiment row, or None when no batch is requested (FR-16). Raises PlannerRefused otherwise."""
    reads = Reads(conn, r)
    client_id = client["id"]
    for key in ("proposals", "briefs_written", "briefs_refused", "patterns_considered", "patterns_skipped_retired", "batch_requested"):
        r.counts.setdefault(key, 0)

    blocked = wh.blocked_sources(conn)
    r.counts["queries"].append("blocked_sources: " + " ".join(wh.BLOCKED_SOURCES_SQL.split()))
    if blocked:
        raise SourceBlocked(f"inspo source(s) failed twice in a row: {', '.join(blocked)}; run "
                            f"`scripts/pull_inspo.py --acknowledge <source>` before `plan batch` (FR-8)")

    # FR-14: read before planning (SKILL.md §4 rule 2, both queries verbatim), floors, VOC, patterns.
    learnings = reads.q("learnings_before_planning", wh.LEARNINGS_BEFORE_PLANNING_SQL, (client_id,))
    leaderboard = reads.q("leaderboard_before_planning", wh.LEADERBOARD_BEFORE_PLANNING_SQL, (client_id,))
    floors = {"targets": config["targets"], "floors": config.get("floors") or {}}
    r.counts["queries"].append("config_floors: clients.config.targets, clients.config.floors")
    offer = reads.q("offer", "select * from offers where client_id = %s order by created_at limit 1", (client_id,))
    icp_rows = reads.q("icp", "select * from icps where client_id = %s order by created_at limit 1", (client_id,))
    if not offer:
        raise ConfigMissing("no offers row for this client; run scripts/dev_db.sh --seed")
    offer, icp = offer[0], (icp_rows[0] if icp_rows else None)
    voc = reads.q("voc_phrases", VOC_SQL, (client_id, MAX_VOC_IN_PROMPT))
    patterns = reads.q("patterns", PATTERNS_SQL)
    retired = retired_for_icp(reads, client_id, icp["id"] if icp else None)
    r.counts.update(learnings_read=len(learnings), leaderboard_rows=len(leaderboard), voc_read=len(voc),
                    patterns_considered=len(patterns), retired_families=sorted(retired))

    # An open proposal already waits for picks: print it again rather than proposing twice.
    existing = open_experiment(conn, client_id)
    if existing:
        briefs = proposal_briefs(conn, existing["id"])
        print(f"plan_batch: proposal {existing['name']} is still waiting for `my picks` ({len(briefs)} proposed); reprinting")
        print(format_proposals(existing, briefs, config))
        r.counts.update(reprinted=1, capacity=existing["capacity"], batch_requested=1)
        return existing

    # FR-15 capacity; CRUCIBLE A9: observed CPM from the last 7 days when there is one.
    kill = int(config["targets"]["kill_impressions"])
    budget = float(daily_budget if daily_budget is not None else client["daily_cap"])
    cpm_row = reads.q("observed_cpm_7d", OBSERVED_CPM_SQL, (client_id, today - timedelta(days=7)))[0]
    if cpm_override is not None:
        cpm, cpm_source = float(cpm_override), "override"
    elif cpm_row["impressions"] and int(cpm_row["impressions"]) > 0:
        cpm, cpm_source = float(cpm_row["spend"]) / int(cpm_row["impressions"]) * 1000, "observed_7d"
    else:
        cpm, cpm_source = float(config["cpm_estimate"]), "config"
    cap = capacity(budget, cpm, kill)
    size = batch_size(config)
    r.counts.update(capacity=cap, batch_size=size, daily_budget=budget, cpm=round(cpm, 4), cpm_source=cpm_source,
                    kill_impressions=kill)
    print(f"plan_batch: capacity {cap} = floor({budget:g} x 7 x 1000 / ({cpm:g} x {kill})) [cpm from {cpm_source}]; "
          f"batch {size} = {config['batch']['recipes']} recipes x {config['batch']['executions_per_recipe']}")
    if size > cap:
        raise CapacityExceeded(f"batch of {size} creatives exceeds capacity {cap}; refused. Needs daily_budget >= "
                               f"{min_daily_budget(size, cpm, kill):g} {client['currency']} at CPM {cpm:g}, or a smaller config.batch (FR-15)")

    # FR-16: threshold event, never a calendar.
    in_flight = int(reads.q("in_flight_below_sample", IN_FLIGHT_SQL, (client_id, kill))[0]["n"])
    r.counts["in_flight_below_sample"] = in_flight
    if not batch_requested(in_flight, cap, size):
        print(f"plan_batch: no batch requested: {in_flight} creative(s) in flight below {kill} impressions + batch {size} "
              f"> capacity {cap} (FR-16); run again when capacity frees")
        return None
    r.counts["batch_requested"] = 1

    # FR-20 ranking, FR-17 4x proposals, FR-18 translation.
    wanted = proposals_wanted(config)
    ranked = rank_patterns(patterns, wanted, retired)
    r.counts["patterns_skipped_retired"] = sum(1 for p in patterns if p["family"] in retired)
    r.counts["patterns_skipped_incomplete"] = sum(1 for p in patterns if p["family"] not in retired and not complete_format_layer(p))
    if len(ranked) < int(config["batch"]["recipes"]):
        raise PlannerRefused(f"only {len(ranked)} rankable pattern(s) for {config['batch']['recipes']} recipes; run `pull inspo` first")
    if len(ranked) < wanted:
        print(f"plan_batch: WARNING only {len(ranked)} rankable patterns for {wanted} proposals (FR-17 wants "
              f"{config['batch']['proposals_multiplier']}x); run `pull inspo` with more sources", file=sys.stderr)
        r.counts["proposals_short"] = wanted - len(ranked)
    n_batch = conn.execute("select count(*) as n from experiments where client_id = %s", (client_id,)).fetchone()["n"]
    exp = wh.insert_experiments(conn, client_id=client_id, offer_id=offer["id"], name=f"batch-{int(n_batch) + 1:03d}",
                                kind="new_recipes", variable="recipe", primary_metric="link_ctr", budget_share=1.0,
                                capacity=cap)
    system, instructions = load_prompts()
    instructions = instructions + "\n" + offer_instructions(offer, icp, config)
    schema = translate_schema()
    budget_tokens = int((((config.get("worker_budgets") or {}).get("planner") or {}).get("tokens")) or 0)
    tokens = 0
    briefs: list[dict[str, Any]] = []
    for number, p in enumerate(ranked, start=1):
        if budget_tokens and tokens > budget_tokens:
            raise BudgetExceeded(f"planner token budget {budget_tokens} spent after {number - 1} of {wanted} proposals")
        result = model.generate_json(task=TASK, system=system, instructions=instructions,
                                     untrusted=untrusted_pattern_text(p, voc), schema=schema)
        tokens += result.tokens_used
        r.api_calls = (r.api_calls or 0) + 1
        out = result.output
        format_layer = dict((p["recipe"] or {}).get("format_layer") or {})
        voc_ids = [voc[i]["id"] for i in out["voc_phrase_indexes"] if 0 <= i < len(voc)]
        values = dict(
            client_id=client_id, experiment_id=exp["id"], offer_id=offer["id"], icp_id=icp["id"] if icp else None,
            kind="replica", source_pattern_id=p["id"], changed_ingredients=list(out["changed_ingredients"]),
            family=p["family"], angle=p.get("angle") or "", voc_phrase_ids=voc_ids, visual_spec=out["visual_spec"],
            cta=(offer.get("offer_layer") or {}).get("cta_mechanic"),
            spec={
                "proposal_number": number, "rank": number, "format_layer": format_layer,
                "offer_layer": offer.get("offer_layer") or {}, "hook_line": out["hook_line"],
                "product_nouns": out["product_nouns"], "imagery_subject": out["imagery_subject"],
                "voc_phrase_indexes": out["voc_phrase_indexes"], "coherence_note": out.get("coherence_note"),
                "translation_backend": result.backend, "chosen": None,
                "source": {"brand": p.get("source_brand"), "ad_id": _ad_id(p), "source_url": p.get("source_url"),
                           "source_image_url": p.get("source_image_url"), "source_strength": p.get("source_strength"),
                           "status": p.get("status"), "variant": p.get("variant"), "hook_type": p.get("hook_type")},
            },
        )
        try:
            validate_brief(values, retired=retired, format_layer=format_layer, voc_count=len(voc))
        except BriefInvalid as exc:
            r.count("briefs_refused")
            raise PlannerRefused(f"proposal {number} ({p.get('source_brand')} / {p['family']}) refused: {exc}") from exc
        hook = wh.insert_hooks(conn, client_id=client_id, text=out["hook_line"], hook_type=p.get("hook_type"),
                               pattern_id=p["id"], trust_tier="owned")
        values["hook_id"] = hook["id"]
        brief = wh.insert_briefs(conn, **values)
        brief["hook_text"] = hook["text"]
        briefs.append(brief)
        r.count("briefs_written")
    r.counts["proposals"] = len(briefs)
    r.tokens_used = tokens
    print(format_proposals(exp, briefs, config))
    return exp


def format_proposals(exp: dict[str, Any], briefs: list[dict[str, Any]], config: dict[str, Any]) -> str:
    """SKILL.md §5.1: number, family/variant, hook line, angle, source brand, source strength, changed ingredients."""
    rows = [("#", "family / variant", "hook line", "angle", "source", "str", "changed")]
    for b in briefs:
        s = b["spec"] or {}
        src = s.get("source") or {}
        rows.append((str(s.get("proposal_number")), f"{b['family']} / {src.get('variant') or '-'}",
                     (b.get("hook_text") or s.get("hook_line") or "")[:70], b["angle"], src.get("brand") or "-",
                     str(src.get("source_strength", "-")), ", ".join(b.get("changed_ingredients") or [])))
    widths = [min(max(len(r[i]) for r in rows), 72) for i in range(len(rows[0]))]
    lines = [f"\n{exp['name']} (capacity {exp['capacity']}): {len(briefs)} proposals"]
    for i, row in enumerate(rows):
        lines.append("  ".join(c.ljust(w) for c, w in zip(row, widths)).rstrip())
        if i == 0:
            lines.append("  ".join("-" * w for w in widths))
    n = int(config["batch"]["recipes"])
    lines.append(f"\nReply `my picks: n, n, n` with exactly {n} numbers (optional `n: reason`). "
                 f"Default after 20 minutes: the ranker's top {n} (`--select default`).")
    return "\n".join(lines)


# ---------- --select ----------

def select(conn: wh.Connection, r: wh.Run, *, client: dict[str, Any], config: dict[str, Any], picks_text: str,
           selected_by: str = "sam") -> dict[str, Any]:
    """FR-17: record the `selections` row for the open proposal and mark the chosen briefs in `briefs.spec`."""
    client_id = client["id"]
    exp = open_experiment(conn, client_id)
    if exp is None:
        raise PlannerRefused("no proposal is waiting for picks; run `plan batch` first")
    briefs = proposal_briefs(conn, exp["id"])
    by_number = {int((b["spec"] or {}).get("proposal_number") or 0): b for b in briefs}
    n = int(config["batch"]["recipes"])
    if picks_text.strip().lower() == "default":
        picks = {k: None for k in sorted(by_number)[:n]}
        selected_by = "ranker_default"
        reason = f"Sam quiet for 20 minutes: default taken, the deterministic ranker's top {n} (SKILL.md §5.1)"
    else:
        picks = parse_picks(picks_text)
        unknown = [k for k in picks if k not in by_number]
        if unknown:
            raise PlannerRefused(f"pick(s) {unknown} are not in proposal {exp['name']} (1..{len(by_number)})")
        if len(picks) != n:
            raise PlannerRefused(f"exactly {n} picks are needed (capacity/2 = recipes); got {len(picks)}")
        reasons = [f"{k}: {v}" for k, v in picks.items() if v]
        reason = "; ".join(reasons) or None
    chosen = [by_number[k]["id"] for k in picks]
    proposed = [b["id"] for b in briefs]
    rejected = [b["id"] for b in briefs if b["id"] not in chosen]
    sel = wh.insert_selections(conn, client_id=client_id, experiment_id=exp["id"], proposed=proposed, chosen=chosen,
                               rejected=rejected, reason=reason, selected_by=selected_by)
    for b in briefs:
        number = int((b["spec"] or {}).get("proposal_number") or 0)
        mark = {"chosen": b["id"] in chosen, "selection_id": str(sel["id"]), "selected_by": selected_by,
                "pick_reason": picks.get(number)}
        conn.execute("update briefs set spec = spec || %s where id = %s", (Jsonb(mark), b["id"]))
    r.counts.update(proposed=len(proposed), chosen=len(chosen), rejected=len(rejected), experiment=exp["name"], selected_by=selected_by)
    note = f" ({reason})" if selected_by == "ranker_default" else ""
    print(f"plan_batch: {exp['name']}: {len(chosen)} chosen of {len(proposed)} proposed by {selected_by}{note}; rejected {len(rejected)}")
    for k in picks:
        b = by_number[k]
        print(f"  #{k} {b['family']} / {((b['spec'] or {}).get('source') or {}).get('variant') or '-'}: {b.get('hook_text') or ''}")
    print("Next: `produce` (scripts/render_creatives.py, T5).")
    return sel


# ---------- main ----------

def load_config(client: dict[str, Any]) -> dict[str, Any]:
    """`clients.config` is the seeded copy of config/clients/<slug>.json (schema-notes); the planner reads the row."""
    return dict(client.get("config") or {})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="plan batch: capacity -> experiments; ranked, translated 4x briefs; --select records Sam's picks")
    ap.add_argument("--client", default="upclicklabs")
    ap.add_argument("--select", metavar="PICKS", default=None, help='`"2, 5, 9"` (optional `n: reason`) or `default`')
    ap.add_argument("--by", default="sam", help="selected_by for --select (default sam)")
    ap.add_argument("--daily-budget", type=float, default=None, help="override clients.daily_cap for the capacity formula (FR-15 test)")
    ap.add_argument("--cpm", type=float, default=None, help="override the CPM (observed 7-day, else config.cpm_estimate)")
    ap.add_argument("--today", type=date.fromisoformat, default=None)
    args = ap.parse_args(argv)

    load_env()
    if args.select is None:
        require(WORKER, "WAREHOUSE_URL_WORKER", "MODEL_BACKEND")
    else:
        require(WORKER, "WAREHOUSE_URL_WORKER")
    r: wh.Run | None = None
    with wh.connect("worker", job=WORKER) as conn:
        client = wh.client_by_slug(conn, args.client)
        if client is None:
            print(f"plan_batch: no client with slug {args.client!r}; run scripts/dev_db.sh --seed", file=sys.stderr)
            return 1
        config = load_config(client)
        try:
            with wh.run(conn, WORKER, client["id"]) as r:
                status = wh.where_are_we(conn, args.client)
                print(wh.format_where_are_we(status))
                check_config(config)
                if paused(client):
                    raise PipelinePaused("pipeline paused (clients.paused or PIPELINE_PAUSED); plan batch refused")
                if status["actions_stuck"]:
                    raise PlannerRefused(f"{status['actions_stuck']} action(s) in `applying`; only the executor's reconcile mode may run (SKILL.md §2)")
                if args.select is not None:
                    select(conn, r, client=client, config=config, picks_text=args.select, selected_by=args.by)
                else:
                    plan(conn, r, client=client, config=config, model=get_model(), today=args.today or date.today(),
                         daily_budget=args.daily_budget, cpm_override=args.cpm)
        except PlannerRefused as exc:
            print(f"plan_batch: refused: {exc} (runs row {r.id} closed as failed)", file=sys.stderr)
            return 2
    assert r is not None
    print(f"\nplan_batch: run {r.id} ok; counts {json.dumps({k: v for k, v in r.counts.items() if k != 'queries'}, sort_keys=True, default=str)}; "
          f"queries {len(r.counts.get('queries', []))}; api_calls {r.api_calls}; tokens {r.tokens_used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
