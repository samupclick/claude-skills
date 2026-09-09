"""The `build_campaign` / cascade `activate` proposal shapes and their validator (T9). Shared by the launcher
(`scripts/meta_launch.py`, which writes the proposal) and the executor (`scripts/apply_actions.py`, which
re-validates it before `applying`). Pure functions: no connection, no adapter, nothing to mock.

`build_campaign` proposal (`actions.proposal`, target `campaign` = the `campaigns` row the launcher wrote):

    {"campaign": {"name", "kind": "new_recipes", "objective", "currency", "terminal_metric", "optimisation_event",
                  "experiment_id", "offer_id"},
     "ad_sets": [{"name", "brief_id", "recipe_pattern_id", "family", "renderer", "daily_budget", "optimisation_event",
                  "targeting": {"geo": [...], "age_min", "age_max"},
                  "ads": [{"name", "creative_name", "creative_id", "link_url", "image_url", "title", "body"}]}],
     "cap_check": {"daily_cap", "active_budget", "proposed_budget", "ok"}}

Cascade `activate` proposal (target `campaign`): {"cascade": true, "ad_entity_ids": [...]} — the executor turns the
campaign, every ad set of those ads, and the ads themselves ACTIVE in one action (FR-37 refuses when any is
DISAPPROVED; the cap is re-checked with every ad set budget applied).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

# FR-21 / SKILL.md §4 rule 4: full components or no ship (`voc_phrase` is optional: "if any").
REQUIRED_COMPONENTS = ("family", "variant", "hook", "angle", "template", "renderer", "image_model", "cta", "landing_page", "offer")
RENDERERS = ("html_template", "image_to_image")
UTM_SOURCE, UTM_MEDIUM = "facebook", "paid"


# What already spends: each ACTIVE ad set once (the same rule as check_daily_cap() after 0007) plus ACTIVE
# scaling campaigns. Two parameters, both the client id.
ACTIVE_BUDGET_SQL = """
select coalesce((select sum(s.budget) from (select max(adset_daily_budget) as budget from ad_entities
                   where client_id = %s and status = 'ACTIVE' group by platform, adset_id) s), 0)
     + coalesce((select sum(daily_budget) from campaigns where client_id = %s and kind = 'scaling' and status = 'ACTIVE'), 0) as active;
"""


class ProposalInvalid(ValueError):
    """The validator refused the proposal; the message says which rule (FR-22, FR-31, FR-32, FR-21, cap)."""


def money(value: Any, what: str) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ProposalInvalid(f"{what} is not a number: {value!r}") from None
    if d <= 0:
        raise ProposalInvalid(f"{what} must be positive, got {d}")
    return d


def ad_url(landing_page: str, *, campaign_name: str, creative_id: str) -> str:
    """FR-32: the ad's URL is the creative's `landing_page` component (the page the gate checked: `offers.landing_url`,
    else `<funnel_host>/quiz`) plus the utm block, `utm_content` = the creative id (quiz_start() resolves creative and
    ad from it). A base that already carries a query keeps it."""
    base = landing_page.strip()
    if not base:
        raise ProposalInvalid("landing_page is empty")
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}utm_source={UTM_SOURCE}&utm_medium={UTM_MEDIUM}&utm_campaign={quote(campaign_name, safe='')}&utm_content={creative_id}"


def utm_content(url: str) -> str | None:
    try:
        return (parse_qs(urlsplit(url).query).get("utm_content") or [None])[0]
    except (ValueError, AttributeError):
        return None


def proposed_budget(proposal: dict[str, Any]) -> Decimal:
    """Sum of the proposal's ad set budgets (each ad set once, whatever its ad count)."""
    return sum((money(s.get("daily_budget"), f"ad set {s.get('name')!r} daily_budget") for s in proposal.get("ad_sets") or []), Decimal(0))


def validate_build_campaign(proposal: dict[str, Any], *, daily_cap: Any, active_budget: Any, adsets_max: int,
                            components_by_creative: dict[str, set[str]] | None = None) -> Decimal:
    """Refuse a `build_campaign` proposal that breaks FR-1 (explicit value model), FR-21 (components), FR-22 (one
    renderer per ad set), FR-31 (ad set count, cap), FR-32 (`utm_content = creative_id`). Returns the proposed
    budget. `active_budget` is what already spends (ACTIVE ad sets + ACTIVE scaling campaigns); `daily_cap`
    from `clients.daily_cap`. `components_by_creative` (creative id -> component types present) enables the
    FR-21 check; the executor passes it too, so a creative stripped after the proposal still cannot ship."""
    if not isinstance(proposal, dict):
        raise ProposalInvalid("proposal is not an object")
    camp = proposal.get("campaign")
    if not isinstance(camp, dict) or not camp.get("name"):
        raise ProposalInvalid("proposal.campaign.name missing")
    if camp.get("kind") not in ("new_recipes", "ablation", "scaling"):
        raise ProposalInvalid(f"proposal.campaign.kind {camp.get('kind')!r} is not new_recipes|ablation|scaling")
    for key in ("terminal_metric", "optimisation_event", "currency", "objective"):
        if not camp.get(key):
            raise ProposalInvalid(f"proposal.campaign.{key} missing (FR-1: the value model is explicit, never a default)")
    ad_sets = proposal.get("ad_sets")
    if not isinstance(ad_sets, list) or not ad_sets:
        raise ProposalInvalid("proposal.ad_sets is empty")
    if len(ad_sets) > int(adsets_max):
        raise ProposalInvalid(f"{len(ad_sets)} ad sets exceed campaign.adsets_max {adsets_max} (FR-31)")
    names: set[str] = {camp["name"]}
    seen_creatives: set[str] = set()
    for i, s in enumerate(ad_sets, start=1):
        if not isinstance(s, dict) or not s.get("name"):
            raise ProposalInvalid(f"ad set {i} has no name")
        if s["name"] in names:
            raise ProposalInvalid(f"object name {s['name']!r} is used twice")
        names.add(s["name"])
        money(s.get("daily_budget"), f"ad set {s['name']!r} daily_budget")
        if s.get("optimisation_event") != camp["optimisation_event"]:
            raise ProposalInvalid(f"ad set {s['name']!r} optimises for {s.get('optimisation_event')!r}, campaign says {camp['optimisation_event']!r}")
        targeting = s.get("targeting") or {}
        if not targeting.get("geo") or targeting.get("age_min") is None or targeting.get("age_max") is None:
            raise ProposalInvalid(f"ad set {s['name']!r} targeting needs geo, age_min, age_max (FR-31: broad, geo + age)")
        ads = s.get("ads")
        if not isinstance(ads, list) or not ads:
            raise ProposalInvalid(f"ad set {s['name']!r} has no ads")
        ad_renderers = sorted({ad.get("renderer") for ad in ads if isinstance(ad, dict) and ad.get("renderer")})
        if len(ad_renderers) > 1:
            raise ProposalInvalid(f"ad set {s['name']!r} mixes renderers {ad_renderers}; two renderers never share an ad set (FR-22)")
        if s.get("renderer") not in RENDERERS:
            raise ProposalInvalid(f"ad set {s['name']!r} renderer {s.get('renderer')!r} is not one of {list(RENDERERS)}")
        for ad in ads:
            if not isinstance(ad, dict) or not ad.get("name") or not ad.get("creative_name"):
                raise ProposalInvalid(f"an ad in {s['name']!r} has no name / creative_name")
            for key in ("name", "creative_name"):
                if ad[key] in names:
                    raise ProposalInvalid(f"object name {ad[key]!r} is used twice")
                names.add(ad[key])
            cid = str(ad.get("creative_id") or "")
            if not cid:
                raise ProposalInvalid(f"ad {ad['name']!r} has no creative_id")
            if cid in seen_creatives:
                raise ProposalInvalid(f"creative {cid} appears in two ads")
            seen_creatives.add(cid)
            if ad.get("renderer", s["renderer"]) != s["renderer"]:
                raise ProposalInvalid(f"ad set {s['name']!r} mixes renderers ({s['renderer']} and {ad.get('renderer')}); two renderers never share an ad set (FR-22)")
            if utm_content(ad.get("link_url") or "") != cid:
                raise ProposalInvalid(f"ad {ad['name']!r} link_url must carry utm_content={cid} (FR-32)")
            if not ad.get("image_url") or not ad.get("title") or not ad.get("body"):
                raise ProposalInvalid(f"ad {ad['name']!r} needs image_url, title, body")
            if components_by_creative is not None:
                missing = [c for c in REQUIRED_COMPONENTS if c not in components_by_creative.get(cid, set())]
                if missing:
                    raise ProposalInvalid(f"creative {cid} lacks creative_components {missing}; full components or no ship (FR-21)")
    proposed = proposed_budget(proposal)
    cap = Decimal(str(daily_cap)) if daily_cap is not None else None
    if cap is None:
        raise ProposalInvalid("clients.daily_cap is unset; refusing to build (FR-31)")
    active = Decimal(str(active_budget or 0))
    if active + proposed > cap:
        raise ProposalInvalid(f"daily_cap: active {active} + proposed {proposed} = {active + proposed} exceeds daily_cap {cap} (FR-31)")
    return proposed


def cap_check(*, daily_cap: Any, active_budget: Any, proposed: Any) -> dict[str, Any]:
    """The `cap_check` block the proposal carries and the stop-point summary prints."""
    cap = Decimal(str(daily_cap)) if daily_cap is not None else None
    active, prop = Decimal(str(active_budget or 0)), Decimal(str(proposed))
    return {"daily_cap": None if cap is None else str(cap), "active_budget": str(active), "proposed_budget": str(prop),
            "ok": cap is not None and active + prop <= cap}


def is_cascade(action: dict[str, Any]) -> bool:
    p = action.get("proposal") or {}
    return action.get("action_type") == "activate" and action.get("target_type") == "campaign" and p.get("cascade") is True


def validate_cascade(proposal: dict[str, Any]) -> list[str]:
    ids = proposal.get("ad_entity_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids):
        raise ProposalInvalid("cascade activate needs proposal.ad_entity_ids (non-empty list of ad_entities ids)")
    if len(set(ids)) != len(ids):
        raise ProposalInvalid("proposal.ad_entity_ids has duplicates")
    return ids
