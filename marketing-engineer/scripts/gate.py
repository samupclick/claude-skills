#!/usr/bin/env python3
"""`gate` / `verdicts` (T6): the creative gate. SKILL.md §3, §4 rules 4, 6, 7, §5.2; PRD FR-12, FR-26, FR-27, FR-29.

    python3 scripts/gate.py [--client upclicklabs] [--experiment batch-001] [--rescore]
    python3 scripts/gate.py --verdicts "approve 1,3,4; reject 2: hook is generic; reject 5: looks like stock"
    python3 scripts/gate.py --verdicts default          # Sam quiet 20 minutes: nothing ships

`gate` scores every `draft` creative of the latest batch (or the named experiment):
  1. opens a `runs` row (worker `gate`), prints "where are we", refuses when paused or when an action is `applying`;
  2. reads the creative's words: `primary_text`, `headline`, `description`, its hook, and every word the producer
     rendered (the `1080x1080.html` beside the asset, through the storage adapter), plus its brief and phrases;
  3. runs the eight hard checks (`references/creative-rubric.md`): `policy`, `brand`, `likeness`, `testimonial`,
     `coherence`, `components`, `landing`, `verbatim`. Text checks go through the model adapter (task `gate_checks`),
     image checks through it with the images attached (`gate_vision`); `components`, `landing`, `verbatim` and the
     rule-based part of `brand` are computed here. Any `fail` blocks (FR-26; FR-12 is `verbatim` on an `internal`
     phrase without an applied `quote_release`);
  4. scores the shadow rubric (`gate_rubric`, seven dimensions, the agent's own verdict) and writes ONE `gate_scores`
     row per creative: `scored_by='agent'`, `mode='shadow'` (never `blocking` here, FR-27), `attempt = creatives.version`,
     `hard_checks`, `policy_flags`, `hard_blocks`, `passed`, `scores`, `avg_score`, `verdict`, and on a failure the
     FR-29 feedback object (`route` = `planner` for `coherence`, else `producer`), then sets `creatives.status='gated'`;
  5. a creative at `version > MAX_ATTEMPTS` is never scored: attempt 4 is impossible (FR-29), it is archived and logged;
  6. prints the §5.2 table (number, Storage URL, source ad URL, hard-check results, shadow scores) and stops for Sam.
`--verdicts` writes Sam's chat verdicts: one `gate_scores` row per named creative with `scored_by='sam'`,
`decision_channel='chat'`, `verdict`, the reason in `feedback`; `approve` needs the hard checks passed (facts block)
and moves the creative to `approved`; `reject` archives it. `default` writes nothing: nothing ships, said so.
Worker role only; no side effect anywhere (SKILL.md §4 rule 1). Coherence feedback is recorded for the planner, not
re-run automatically.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.env import ME_DIR, load_env, require  # noqa: E402
from adapters.model import Model, get_model  # noqa: E402
from adapters.storage import get_storage  # noqa: E402
from warehouse import client as wh  # noqa: E402
from warehouse.client import Jsonb  # noqa: E402

WORKER = "gate"
TASK_CHECKS, TASK_VISION, TASK_RUBRIC = "gate_checks", "gate_vision", "gate_rubric"
PROMPTS = ME_DIR / "references" / "prompts" / "gate.md"
RUBRIC_REF = ME_DIR / "references" / "creative-rubric.md"
HARD_CHECKS = ("policy", "brand", "likeness", "testimonial", "coherence", "components", "landing", "verbatim")   # FR-26
PLANNER_CHECKS = ("coherence",)                                                                              # routes to the planner
RUBRIC_DIMENSIONS = ("hook_strength", "clarity_3s", "icp_specificity", "voc_language", "single_cta", "mobile_legibility", "layout_fidelity")
AGENT_MODE = "shadow"                                     # FR-27: the agent never writes mode='blocking' in phase 0
MAX_ATTEMPTS = 3                                          # FR-29: creatives.version is the attempt; 4 is impossible
REQUIRED_COMPONENTS = ("family", "variant", "hook", "angle", "template", "renderer", "image_model", "cta", "landing_page", "offer")
QUOTE_FAMILIES = ("testimonial_card", "press_quote")      # FR-23
VERBATIM_MIN_WORDS = 8                                    # a run of this many words of a phrase counts as verbatim use
RUBRIC_APPROVE_MIN, RUBRIC_APPROVE_MEAN = 3, 3.5
REQUIRED_CONFIG = (("targets", "ctr_floor"), ("targets", "kill_impressions"), ("daily_cap",), ("currency",), ("brand", "hard_blocks"))

PRICE_RE = re.compile(r"(?:[€$£]\s?\d[\d.,]*|\b\d[\d.,]*\s?(?:€|\$|£|eur|usd|gbp|per month|/mo)\b)", re.I)
INCOME_RE = re.compile(r"\b(?:income|revenue|profit|guaranteed?|roi|\d+\s?x\s+(?:return|leads|sales))\b", re.I)
_WORD_RE = re.compile(r"[^a-z0-9]+")


class GateRefused(RuntimeError):
    """`gate` or `--verdicts` refused; the message says why. The runs row closes `failed` with it."""


class PipelinePaused(GateRefused):
    pass


class ConfigMissing(GateRefused):
    pass


class VerdictError(GateRefused):
    """A verdict names a creative that does not exist, was not gated, or failed its hard checks."""


class BudgetExceeded(GateRefused):
    pass


# ---------- pure rules (unit-tested) ----------

def normalise(text: str) -> str:
    """Same rule as `scripts/pull_voc.py`: lower case, letters / digits / spaces only, single spaces."""
    return " ".join(_WORD_RE.sub(" ", (text or "").lower()).split())


def words_from_html(page_html: str) -> str:
    """Every rendered word of a template page: styles, scripts and tags dropped, entities unescaped."""
    text = re.sub(r"<(style|script)\b.*?</\1\s*>", " ", page_html, flags=re.S | re.I)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html_lib.unescape(text).split())


def verbatim_hits(words: str, phrases: list[dict[str, Any]], *, min_words: int = VERBATIM_MIN_WORDS) -> list[dict[str, Any]]:
    """Phrases used verbatim in `words`: the whole `phrase_normalised`, or any run of `min_words` consecutive words
    of it. Returns the matching phrase rows with the span that matched."""
    hay = " " + normalise(words) + " "
    hits = []
    for p in phrases:
        norm = normalise(p.get("phrase_normalised") or p.get("phrase") or "")
        toks = norm.split()
        if not toks:
            continue
        spans = [norm] if len(toks) <= min_words else [" ".join(toks[i:i + min_words]) for i in range(len(toks) - min_words + 1)]
        span = next((s for s in spans if f" {s} " in hay), None)
        if span:
            hits.append({**p, "span": span})
    return hits


def brand_rule_hits(words: str, hard_blocks: list[str]) -> list[str]:
    """The rule-based half of the `brand` check: pricing and income claims are found by pattern; client names need the
    model (`brand_flags`). Only rules named in `clients.config.brand.hard_blocks` fire."""
    rules = " ".join(hard_blocks).lower()
    hits = []
    if "pricing" in rules or "price" in rules:
        hits += [f"pricing: {m.group(0).strip()!r}" for m in PRICE_RE.finditer(words)]
    if "income" in rules:
        hits += [f"income claim: {m.group(0).strip()!r}" for m in INCOME_RE.finditer(words)]
    return hits


def components_check(components: list[dict[str, Any]], *, voc_phrase_ids: list[Any]) -> list[str]:
    """FR-21 / SKILL.md §4 rule 4 as a gate check: every required type exactly once with a non-empty ref, `voc_phrase`
    rows equal to the brief's phrases. Returns the problems (empty = pass)."""
    types = [c["component_type"] for c in components]
    problems = [f"{t} missing" for t in REQUIRED_COMPONENTS if types.count(t) != 1]
    problems += [f"{c['component_type']} empty" for c in components if not str(c.get("component_ref") or "").strip()]
    voc = sorted(str(c["component_ref"]) for c in components if c["component_type"] == "voc_phrase")
    if voc != sorted(str(v) for v in voc_phrase_ids):
        problems.append(f"voc_phrase rows {voc} differ from the brief's {[str(v) for v in voc_phrase_ids]}")
    return problems


def landing_check(components: list[dict[str, Any]], *, landing_page: str, cta_mechanic: str, offer_id: Any) -> list[str]:
    by = {c["component_type"]: c["component_ref"] for c in components}
    problems = []
    if by.get("landing_page") != landing_page:
        problems.append(f"landing_page {by.get('landing_page')!r} is not the offer's page {landing_page!r}")
    if by.get("cta") != cta_mechanic:
        problems.append(f"cta {by.get('cta')!r} is not the offer's mechanic {cta_mechanic!r}")
    if by.get("offer") != str(offer_id):
        problems.append(f"offer {by.get('offer')!r} is not this brief's offer")
    return problems


def rubric_verdict(scores: dict[str, int]) -> str:
    vals = [int(scores[d]) for d in RUBRIC_DIMENSIONS]
    return "approve" if min(vals) >= RUBRIC_APPROVE_MIN and statistics.mean(vals) >= RUBRIC_APPROVE_MEAN else "reject"


def attempt_allowed(version: int) -> bool:
    """FR-29: attempts 1..MAX_ATTEMPTS may be gated; a fourth is impossible."""
    return 1 <= int(version) <= MAX_ATTEMPTS


def feedback_object(*, creative_id: Any, brief_id: Any, attempt: int, failures: dict[str, list[str]]) -> dict[str, Any]:
    """The FR-29 feedback object (content-supervisor §5.1, trimmed to what a producer or planner re-run needs)."""
    route = "planner" if any(c in failures for c in PLANNER_CHECKS) else "producer"
    guidance = {
        "policy": "rewrite the flagged words; no personal attributes, no results claims, no shouting",
        "brand": "remove the price / income / client-name words; the brand hard blocks are absolute",
        "likeness": "regenerate the image; no identifiable real person, no logos",
        "testimonial": "drop the quote or attribution, or obtain a quote_release; no depicted person in a quote family",
        "coherence": "the recipe does not carry this offer: choose another pattern or re-translate the nouns",
        "components": "write every FR-21 component; the creative cannot ship without them",
        "landing": "point the landing_page / cta / offer components at the offer's page and mechanic",
        "verbatim": "paraphrase the customer phrase; verbatim use needs an applied quote_release (internal) or is never allowed (public / inbound)",
    }
    return {
        "feedback_type": "revision_request", "source": "creative_gate", "route": route,
        "creative_id": str(creative_id), "brief_id": str(brief_id) if brief_id else None,
        "attempt": {"current": attempt, "max": MAX_ATTEMPTS, "next_possible": attempt < MAX_ATTEMPTS},
        "failures": [{"criterion": c, "severity": "blocking", "issues": issues, "fix_guidance": guidance[c]} for c, issues in failures.items()],
        "preserve": {"elements": ["format_layer", "cta", "landing_page", "offer_layer"], "note": "the format layer is carried verbatim; only offer, product nouns, VOC phrases, imagery subject may change"},
        "constraints": {"format_layer_change": "none", "renderer_change": "none"},
    }


CLAUSE = re.compile(r"^\s*(approve|reject)\s+([^:]+?)\s*(?::\s*(.*?))?\s*$", re.IGNORECASE | re.DOTALL)


def parse_verdicts(text: str) -> list[tuple[str, int, str | None]]:
    """`verdicts: approve 1,3,4; reject 2: hook is generic; reject 5: looks like stock` -> [(verdict, number, reason)]."""
    body = re.sub(r"^\s*verdicts\s*:\s*", "", text.strip(), flags=re.I)
    out: list[tuple[str, int, str | None]] = []
    seen: set[int] = set()
    for clause in filter(None, (c.strip() for c in body.split(";"))):
        m = CLAUSE.match(clause)
        if not m:
            raise VerdictError(f"cannot parse {clause!r}; expected `approve 1,3` or `reject 2: reason`")
        for ref in [r for r in re.split(r"[,\s]+", m.group(2)) if r]:
            if not ref.isdigit():
                raise VerdictError(f"{ref!r} is not a creative number")
            n = int(ref)
            if n in seen:
                raise VerdictError(f"creative {n} named twice")
            seen.add(n)
            out.append((m.group(1).lower(), n, (m.group(3) or "").strip() or None))
    if not out:
        raise VerdictError("no verdicts given")
    return out


def checks_schema() -> dict[str, Any]:
    strings = {"type": "array", "items": {"type": "string"}}
    return {"type": "object",
            "properties": {"policy_flags": strings, "brand_flags": strings, "fabricated_testimonial": {"type": "boolean"},
                           "coherent": {"type": "boolean"}, "contradiction": {"type": "string"}, "notes": {"type": "string"}},
            "required": ["policy_flags", "brand_flags", "fabricated_testimonial", "coherent", "contradiction"], "additionalProperties": False}


def vision_schema() -> dict[str, Any]:
    return {"type": "object",
            "properties": {"real_person_likeness": {"type": "boolean"}, "depicts_person": {"type": "boolean"},
                           "logos_or_wordmarks": {"type": "boolean"}, "notes": {"type": "string"}},
            "required": ["real_person_likeness", "depicts_person", "logos_or_wordmarks"], "additionalProperties": False}


def rubric_schema() -> dict[str, Any]:
    props: dict[str, Any] = {d: {"type": "integer", "minimum": 1, "maximum": 5} for d in RUBRIC_DIMENSIONS}
    props.update(verdict={"type": "string", "enum": ["approve", "reject"]}, reason={"type": "string"})
    return {"type": "object", "properties": props, "required": [*RUBRIC_DIMENSIONS, "verdict", "reason"], "additionalProperties": False}


def load_prompts(path: Path = PROMPTS) -> dict[str, str]:
    text = path.read_text()
    sections = re.split(r"^## ([\w ]+?)\s*$", text, flags=re.M)
    found = {sections[i].strip().lower(): sections[i + 1].strip() for i in range(1, len(sections) - 1, 2)}
    for key in ("checks system", "checks instructions", "vision system", "vision instructions", "rubric system", "rubric instructions"):
        if key not in found:
            raise RuntimeError(f"{path} needs a '## {key.title()}' section")
    return found


def untrusted_creative_text(creative: dict[str, Any], brief: dict[str, Any], rendered_words: str, voc: list[dict[str, Any]]) -> str:
    """The creative and its brief as data (SKILL.md §4 rule 7). No URLs."""
    spec = brief.get("spec") or {}
    payload = {
        "creative": {"primary_text": creative.get("primary_text"), "headline": creative.get("headline"),
                     "description": creative.get("description"), "hook_line": creative.get("hook_text"),
                     "rendered_words": rendered_words, "template": creative.get("template"), "family": brief.get("family")},
        "brief": {"format_layer": spec.get("format_layer"), "visual_spec": brief.get("visual_spec"), "product_nouns": spec.get("product_nouns"),
                  "imagery_subject": spec.get("imagery_subject"), "changed_ingredients": brief.get("changed_ingredients"),
                  "angle": brief.get("angle"), "source_variant": (spec.get("source") or {}).get("variant")},
        "customer_phrases": [{"n": i, "category": v["category"], "visibility": v["visibility"], "phrase": v["phrase"]} for i, v in enumerate(voc)],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1, default=str)


def trusted_context(offer: dict[str, Any], icp: dict[str, Any] | None, config: dict[str, Any], landing_page: str) -> str:
    brand = config.get("brand") or {}
    lines = ["", "Offer (ours):", f"- name: {offer.get('name')}", f"- promise: {offer.get('promise')}",
             f"- price anchor: {offer.get('price_anchor')}", f"- proof points (the only figures allowed): {', '.join(offer.get('proof_points') or []) or '-'}",
             f"- offer layer (fixed): {json.dumps(offer.get('offer_layer') or {}, sort_keys=True)}",
             f"- landing page: the quiz at {landing_page}, then a 15-minute call",
             f"- brand hard blocks: {', '.join(brand.get('hard_blocks') or []) or '-'}"]
    if icp:
        lines += ["Audience (ICP):", f"- {icp.get('label')}", f"- role: {icp.get('role')}; company: {icp.get('company_type')}; "
                  f"size: {icp.get('size_band')}; geo: {', '.join(icp.get('geo') or [])}",
                  f"- pains: {'; '.join(icp.get('pains') or []) or '-'}", f"- outcomes: {'; '.join(icp.get('outcomes') or []) or '-'}"]
    return "\n".join(lines)


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


def landing_page_for(offer: dict[str, Any]) -> str:
    """Same rule as the producer: `offers.landing_url`, else the quiz on the funnel host."""
    if offer.get("landing_url"):
        return str(offer["landing_url"])
    if offer.get("funnel_host"):
        return f"{str(offer['funnel_host']).rstrip('/')}/quiz"
    raise ConfigMissing("offer has neither landing_url nor funnel_host")


EXPERIMENT_SQL = """
select e.* from experiments e where e.client_id = %s and (%s::text is null or e.name = %s)
   and exists (select 1 from creatives c where c.experiment_id = e.id) order by e.created_at desc limit 1;
"""
CREATIVES_SQL = """
select c.*, b.spec as brief_spec, b.family as brief_family, b.voc_phrase_ids, b.offer_id as brief_offer_id, b.angle as brief_angle,
       b.visual_spec, b.changed_ingredients, b.hook_id as brief_hook_id,
       (select h.text from creative_components cc join hooks h on h.id::text = cc.component_ref
         where cc.creative_id = c.id and cc.component_type = 'hook' limit 1) as hook_text,
       (select cc.component_ref = b.hook_id::text from creative_components cc
         where cc.creative_id = c.id and cc.component_type = 'hook' limit 1) as first_execution
  from creatives c left join briefs b on b.id = c.brief_id
 where c.client_id = %s and c.experiment_id = %s and c.status = any(%s::text[])
 order by (b.spec->>'proposal_number')::int nulls last, c.version, first_execution desc nulls last, c.created_at, c.id;
"""
COMPONENTS_SQL = "select component_type, component_ref from creative_components where creative_id = %s order by component_type, component_ref;"
VOC_SQL = "select id, phrase, phrase_normalised, category, visibility, trust_tier from voc_phrases where id = any(%s::uuid[]) order by id;"
RESTRICTED_VOC_SQL = """
select id, phrase, phrase_normalised, category, visibility, trust_tier from voc_phrases
 where (client_id = %s or client_id is null) and (visibility = 'internal' or trust_tier in ('public', 'inbound')) order by id;
"""
QUOTE_RELEASE_SQL = """
select target_id, proposal from actions where client_id = %s and action_type = 'quote_release' and status = 'applied';
"""
LATEST_AGENT_ROW_SQL = """
select * from gate_scores where creative_id = %s and scored_by = 'agent' order by attempt desc, created_at desc limit 1;
"""


def released(releases: list[dict[str, Any]], *, creative_id: Any, brief_id: Any, phrase_id: Any = None) -> bool:
    """An applied `quote_release` names the creative, its brief, or the phrase (`target_id`, or `proposal.creative_id`,
    `.brief_id`, `.voc_phrase_id`). Applied only as `sam_admin` (0002 trigger), so an applied row is Sam's decision."""
    ids = {str(creative_id), str(brief_id)} | ({str(phrase_id)} if phrase_id else set())
    for a in releases:
        p = a.get("proposal") or {}
        if str(a.get("target_id")) in ids or any(str(p.get(k)) in ids for k in ("creative_id", "brief_id", "voc_phrase_id")):
            return True
    return False


# ---------- the gate ----------

def read_rendered_words(storage: Any, creative: dict[str, Any], r: wh.Run) -> str:
    """The words the producer rendered: `1080x1080.html` beside the asset (T5 convention). Missing = DB words only."""
    urls = list(creative.get("asset_urls") or [])
    if not urls:
        return ""
    html_url = re.sub(r"\.png$", ".html", urls[0])
    try:
        return words_from_html(storage.get(html_url).decode("utf-8", "replace"))
    except Exception as exc:  # the asset exists but its HTML does not (pre-T6 render): gate on the DB words, say so
        r.count("html_missing")
        print(f"gate: WARNING rendered HTML missing for creative {creative['id']} ({type(exc).__name__}); gating on the database words only", file=sys.stderr)
        return ""


def gate(conn: wh.Connection, r: wh.Run, *, client: dict[str, Any], config: dict[str, Any], model: Model, storage: Any,
         experiment_name: str | None = None, rescore: bool = False) -> list[dict[str, Any]]:
    """Score every draft creative (gated ones too with `--rescore`) of the batch; returns the numbered rows printed."""
    client_id = client["id"]
    for key in ("creatives_scored", "passed", "failed", "dropped_max_attempts", "html_missing", "skipped_gated"):
        r.counts.setdefault(key, 0)
    r.counts.setdefault("hard_check_failures", {})
    exp = conn.execute(EXPERIMENT_SQL, (client_id, experiment_name, experiment_name)).fetchone()
    if exp is None:
        raise GateRefused("no batch with creatives" + (f" named {experiment_name}" if experiment_name else "") + "; run `produce` first")
    r.counts["experiment"] = exp["name"]
    statuses = ["draft", "gated"] if rescore else ["draft"]
    creatives = conn.execute(CREATIVES_SQL, (client_id, exp["id"], statuses)).fetchall()
    if not creatives:
        already = conn.execute("select count(*) as n from creatives where experiment_id = %s and status = 'gated'", (exp["id"],)).fetchone()["n"]
        if already:
            r.counts["skipped_gated"] = int(already)
            print(f"gate: {exp['name']}: {already} creative(s) already gated and waiting for verdicts; reprinting (use --rescore to score again)")
            return print_table(conn, exp, gated_rows(conn, client_id, exp["id"]), config)
        raise GateRefused(f"{exp['name']} has no draft creative to gate; run `produce` first")

    offer = conn.execute("select * from offers where client_id = %s order by created_at limit 1", (client_id,)).fetchone()
    if offer is None:
        raise ConfigMissing("no offers row for this client")
    icp = conn.execute("select * from icps where client_id = %s order by created_at limit 1", (client_id,)).fetchone()
    landing_page = landing_page_for(offer)
    cta_mechanic = str((offer.get("offer_layer") or {}).get("cta_mechanic") or "")
    hard_blocks = list((config.get("brand") or {}).get("hard_blocks") or [])
    releases = conn.execute(QUOTE_RELEASE_SQL, (client_id,)).fetchall()
    restricted = conn.execute(RESTRICTED_VOC_SQL, (client_id,)).fetchall()
    prompts = load_prompts()
    context = trusted_context(offer, icp, config, landing_page)
    rubric_ref = RUBRIC_REF.read_text()
    token_budget = int((((config.get("worker_budgets") or {}).get("gate") or {}).get("tokens")) or 0)

    for c in creatives:
        if not attempt_allowed(c["version"]):
            conn.execute("update creatives set status = 'archived' where id = %s", (c["id"],))
            r.count("dropped_max_attempts")
            print(f"gate: creative {c['id']} (brief #{(c.get('brief_spec') or {}).get('proposal_number')}) is at version {c['version']}: attempt "
                  f"{c['version']} is impossible, max {MAX_ATTEMPTS} (FR-29); archived and logged", file=sys.stderr)
            continue
        if token_budget and (r.tokens_used or 0) > token_budget:
            raise BudgetExceeded(f"gate token budget {token_budget} spent")
        components = conn.execute(COMPONENTS_SQL, (c["id"],)).fetchall()
        voc = conn.execute(VOC_SQL, (list(c.get("voc_phrase_ids") or []),)).fetchall() if c.get("voc_phrase_ids") else []
        rendered_words = read_rendered_words(storage, c, r)
        words = " ".join(filter(None, [c.get("primary_text"), c.get("headline"), c.get("description"), c.get("hook_text"), rendered_words]))
        brief = {"spec": c.get("brief_spec") or {}, "family": c.get("brief_family"), "visual_spec": c.get("visual_spec"),
                 "changed_ingredients": c.get("changed_ingredients"), "angle": c.get("brief_angle")}
        untrusted = untrusted_creative_text(c, brief, rendered_words, voc)

        # model checks: text, then images
        res = model.generate_json(task=TASK_CHECKS, system=prompts["checks system"], instructions=prompts["checks instructions"] + context,
                                  untrusted=untrusted, schema=checks_schema(), max_tokens=1500)
        checks = res.output
        images = _images(storage, c, r)
        vis = model.generate_json(task=TASK_VISION, system=prompts["vision system"], instructions=prompts["vision instructions"],
                                  untrusted="(rendered ad and generated image attached; no text data)", schema=vision_schema(),
                                  max_tokens=500, images=[images[k] for k in ("render", "image") if k in images] or None)
        vision = vis.output
        rub = model.generate_json(task=TASK_RUBRIC, system=prompts["rubric system"],
                                  instructions=prompts["rubric instructions"] + context + "\n\nRubric reference:\n" + rubric_ref,
                                  untrusted=untrusted, schema=rubric_schema(), max_tokens=800,
                                  images=[images[k] for k in ("render", "source") if k in images] or None)
        rubric = rub.output
        r.api_calls = (r.api_calls or 0) + 3
        r.tokens_used = (r.tokens_used or 0) + res.tokens_used + vis.tokens_used + rub.tokens_used

        # the eight hard checks
        family = c.get("brief_family") or next((x["component_ref"] for x in components if x["component_type"] == "family"), None)
        failures: dict[str, list[str]] = {}
        if checks["policy_flags"]:
            failures["policy"] = list(checks["policy_flags"])
        brand_hits = brand_rule_hits(words, hard_blocks) + list(checks["brand_flags"])
        if brand_hits:
            failures["brand"] = brand_hits
        if vision["real_person_likeness"] or vision["logos_or_wordmarks"]:
            failures["likeness"] = [k for k in ("real_person_likeness", "logos_or_wordmarks") if vision[k]]
        quote_family = family in QUOTE_FAMILIES
        testimonial_issues = []
        if quote_family and not released(releases, creative_id=c["id"], brief_id=c.get("brief_id")):
            testimonial_issues.append(f"family {family} without an applied quote_release")
        if quote_family and vision["depicts_person"]:
            testimonial_issues.append("a person is depicted in a quote family")
        if checks["fabricated_testimonial"]:
            testimonial_issues.append("the copy presents a quote or testimonial")
        if testimonial_issues:
            failures["testimonial"] = testimonial_issues
        if not checks["coherent"]:
            failures["coherence"] = [checks.get("contradiction") or "the recipe does not carry this offer"]
        comp_problems = components_check(components, voc_phrase_ids=list(c.get("voc_phrase_ids") or []))
        if comp_problems:
            failures["components"] = comp_problems
        land_problems = landing_check(components, landing_page=landing_page, cta_mechanic=cta_mechanic, offer_id=c.get("brief_offer_id") or offer["id"])
        if land_problems:
            failures["landing"] = land_problems
        verbatim = []
        for hit in verbatim_hits(words, restricted):
            if hit["visibility"] == "internal" and hit["trust_tier"] not in ("public", "inbound") \
                    and released(releases, creative_id=c["id"], brief_id=c.get("brief_id"), phrase_id=hit["id"]):
                continue
            verbatim.append(f"{hit['visibility']}/{hit['trust_tier']} phrase {str(hit['id'])[:8]} used verbatim: {hit['span']!r}")
        if verbatim:
            failures["verbatim"] = verbatim

        hard_checks = {name: ("fail" if name in failures else "pass") for name in HARD_CHECKS}
        passed = not failures
        for name in failures:
            r.counts["hard_check_failures"][name] = r.counts["hard_check_failures"].get(name, 0) + 1
        scores = {d: int(rubric[d]) for d in RUBRIC_DIMENSIONS}
        avg = round(statistics.mean(scores.values()), 2)
        verdict = rubric_verdict(scores)
        if verdict != rubric["verdict"]:
            rubric["reason"] = f"{rubric['reason']} (verdict recomputed from the scores by the rubric rule)"
        row = wh.insert_gate_scores(
            conn, creative_id=c["id"], attempt=int(c["version"]), scored_by="agent", mode=AGENT_MODE, verdict=verdict,
            decision_channel="auto", scores={**scores, "reason": rubric["reason"], "backend": rub.backend, "notes": checks.get("notes"),
                                             "vision_notes": vision.get("notes")},
            avg_score=avg, hard_checks=hard_checks, policy_flags=list(checks["policy_flags"]), hard_blocks=sorted(failures), passed=passed,
            feedback=feedback_object(creative_id=c["id"], brief_id=c.get("brief_id"), attempt=int(c["version"]), failures=failures) if failures else {},
            feedback_trust="owned",
        )
        conn.execute("update creatives set status = 'gated' where id = %s", (c["id"],))
        r.count("creatives_scored")
        r.count("passed" if passed else "failed")
    return print_table(conn, exp, gated_rows(conn, client_id, exp["id"]), config)


def _images(storage: Any, c: dict[str, Any], r: wh.Run) -> dict[str, bytes]:
    """{render: the PNG, image: the generated image beside it, source: our copy of the source ad} as available; a
    missing one is skipped and counted."""
    out: dict[str, bytes] = {}
    urls = list(c.get("asset_urls") or [])
    for label, url in (("render", urls[0] if urls else None), ("image", re.sub(r"/1080x1080\.png$", "/image.png", urls[0]) if urls else None),
                       ("source", c.get("source_reference_url"))):
        if not url:
            continue
        try:
            out[label] = storage.get(url)
        except Exception:
            r.count(f"images_missing_{label}")
    return out


def gated_rows(conn: wh.Connection, client_id: Any, experiment_id: Any) -> list[dict[str, Any]]:
    """The creatives waiting for verdicts, numbered the same way in `gate` and `--verdicts` (SKILL.md §5.2)."""
    rows = conn.execute(CREATIVES_SQL, (client_id, experiment_id, ["gated"])).fetchall()
    for n, c in enumerate(rows, start=1):
        c["n"] = n
        c["gate"] = conn.execute(LATEST_AGENT_ROW_SQL, (c["id"],)).fetchone()
    return rows


def print_table(conn: wh.Connection, exp: dict[str, Any], rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    print(format_table(exp, rows))
    return rows


def format_table(exp: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    """SKILL.md §5.2: number, the Storage URL, the source ad URL (our copy), hard-check results, shadow rubric scores."""
    lines = [f"\n{exp['name']}: {len(rows)} creative(s) gated, waiting for verdicts"]
    for c in rows:
        g = c.get("gate") or {}
        hc = g.get("hard_checks") or {}
        failed = [k for k in HARD_CHECKS if hc.get(k) == "fail"]
        result = "PASS" if g.get("passed") else ("FAIL: " + ", ".join(failed) if failed else "not scored")
        scores = g.get("scores") or {}
        shadow = " ".join(f"{d.split('_')[0]}={scores.get(d, '-')}" for d in RUBRIC_DIMENSIONS)
        spec = c.get("brief_spec") or {}
        lines += [
            f"#{c['n']}  brief #{spec.get('proposal_number')}  {c.get('brief_family')} / {c.get('template')}  v{c['version']}  attempt {g.get('attempt', '-')}  hard checks: {result}",
            f"     hook: {(c.get('hook_text') or '')[:100]}",
            f"     storage: {(c.get('asset_urls') or ['-'])[0]}",
            f"     source ad (our copy): {c.get('source_reference_url') or '-'}",
            f"     shadow rubric: avg {g.get('avg_score', '-')} verdict {g.get('verdict', '-')}  [{shadow}]",
        ]
        if g.get("feedback"):
            fb = g["feedback"]
            lines.append(f"     feedback -> {fb.get('route')}: " + "; ".join(f"{f['criterion']}: {'; '.join(f['issues'])[:160]}" for f in fb.get("failures", [])))
    lines.append("\nReply `verdicts: approve 1,3,4; reject 2: hook is generic` (facts block: a creative with a failed hard check cannot be approved). "
                 "Default after 20 minutes: nothing ships (`--verdicts default`).")
    return "\n".join(lines)


# ---------- --verdicts ----------

def verdicts(conn: wh.Connection, r: wh.Run, *, client: dict[str, Any], text: str, experiment_name: str | None = None,
             by: str = "sam") -> list[dict[str, Any]]:
    """SKILL.md §5.2: Sam's chat verdicts as `gate_scores` rows (`scored_by='sam'`, `decision_channel='chat'`)."""
    client_id = client["id"]
    exp = conn.execute(EXPERIMENT_SQL, (client_id, experiment_name, experiment_name)).fetchone()
    if exp is None:
        raise GateRefused("no batch with creatives; run `produce` and `gate` first")
    rows = gated_rows(conn, client_id, exp["id"])
    r.counts.update(experiment=exp["name"], approved=0, rejected=0, default_taken=0)
    if not rows:
        raise GateRefused(f"{exp['name']} has no gated creative waiting for verdicts; run `gate` first")
    if text.strip().lower() == "default":
        r.counts["default_taken"] = 1
        print(f"gate: Sam quiet for 20 minutes: default taken, nothing ships (SKILL.md §5.2); {len(rows)} creative(s) stay gated, no verdict written")
        return []
    by_n = {c["n"]: c for c in rows}
    decisions = parse_verdicts(text)
    for verdict, n, reason in decisions:            # validate everything before writing anything
        c = by_n.get(n)
        if c is None:
            raise VerdictError(f"creative {n} is not in the gated table of {exp['name']} (1..{len(rows)})")
        if verdict == "approve" and not (c.get("gate") or {}).get("passed"):
            failed = [k for k in HARD_CHECKS if ((c.get("gate") or {}).get("hard_checks") or {}).get(k) == "fail"]
            raise VerdictError(f"creative {n} failed hard check(s) {failed}; facts block, it cannot be approved (SKILL.md §4 rule 6)")
    written = []
    for verdict, n, reason in decisions:
        c = by_n[n]
        row = wh.insert_gate_scores(conn, creative_id=c["id"], attempt=int(c["version"]), scored_by=by, mode="blocking", verdict=verdict,
                                    decision_channel="chat", feedback={"reason": reason} if reason else {}, feedback_trust="owned",
                                    passed=(c.get("gate") or {}).get("passed"), hard_checks=(c.get("gate") or {}).get("hard_checks") or {})
        conn.execute("update creatives set status = %s where id = %s", ("approved" if verdict == "approve" else "archived", c["id"]))
        r.count("approved" if verdict == "approve" else "rejected")
        written.append(row)
        print(f"gate: #{n} {verdict}{' (' + reason + ')' if reason else ''} -> creatives.status "
              f"{'approved' if verdict == 'approve' else 'archived'}")
    left = len(rows) - len(written)
    print(f"gate: {exp['name']}: {r.counts['approved']} approved, {r.counts['rejected']} rejected by {by}; {left} still gated without a verdict")
    if r.counts["approved"]:
        print("Next: `launch` (scripts/meta_launch.py, T9).")
    return written


# ---------- main ----------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="gate: hard checks + shadow rubric into gate_scores; --verdicts records Sam's chat verdicts")
    ap.add_argument("--client", default="upclicklabs")
    ap.add_argument("--experiment", default=None, help="batch name (default: the latest batch with creatives)")
    ap.add_argument("--rescore", action="store_true", help="score gated creatives again (same attempt, a new agent row)")
    ap.add_argument("--verdicts", metavar="TEXT", default=None, help='`"approve 1,3; reject 2: reason"` or `default`')
    ap.add_argument("--by", default="sam", help="scored_by for --verdicts (default sam)")
    args = ap.parse_args(argv)

    load_env()
    if args.verdicts is None:
        require(WORKER, "WAREHOUSE_URL_WORKER", "MODEL_BACKEND", "STORAGE_BACKEND")
    else:
        require(WORKER, "WAREHOUSE_URL_WORKER")
    r: wh.Run | None = None
    with wh.connect("worker", job=WORKER) as conn:
        client = wh.client_by_slug(conn, args.client)
        if client is None:
            print(f"gate: no client with slug {args.client!r}; run scripts/dev_db.sh --seed", file=sys.stderr)
            return 1
        config = dict(client.get("config") or {})
        try:
            with wh.run(conn, WORKER, client["id"]) as r:
                status = wh.where_are_we(conn, args.client)
                print(wh.format_where_are_we(status))
                check_config(config)
                if paused(client):
                    raise PipelinePaused("pipeline paused (clients.paused or PIPELINE_PAUSED); gate refused")
                if status["actions_stuck"]:
                    raise GateRefused(f"{status['actions_stuck']} action(s) in `applying`; only the executor's reconcile mode may run (SKILL.md §2)")
                if args.verdicts is not None:
                    verdicts(conn, r, client=client, text=args.verdicts, experiment_name=args.experiment, by=args.by)
                else:
                    gate(conn, r, client=client, config=config, model=get_model(), storage=get_storage(),
                         experiment_name=args.experiment, rescore=args.rescore)
        except GateRefused as exc:
            print(f"gate: refused: {exc} (runs row {r.id} closed as failed)", file=sys.stderr)
            return 2
    assert r is not None
    print(f"\ngate: run {r.id} ok; counts {json.dumps(r.counts, sort_keys=True, default=str)}; api_calls {r.api_calls}; tokens {r.tokens_used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
