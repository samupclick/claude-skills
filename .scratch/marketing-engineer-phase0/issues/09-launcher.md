# 09: Launcher (T9)

**What to build:** Running `launch` writes one proposed `build_campaign` action for the approved creatives; after Sam approves and runs `apply actions`, the executor creates one paused `new_recipes` campaign with 3 ad sets and 6 ads in the (fake) Meta account and the warehouse carries their external ids; a later proposed `activate` turns them on under the cap invariant.

**Blocked by:** T6 (06), T7 (07), T8 (08)

**Blocks:** T10 (10)

**Status:** ready-for-agent

**Done:** no

**Stop point:** C — T9 proposes `build_campaign`, and later `activate`: print the proposal summary (campaign, ad sets, budgets, cap check result); wait for `approve n`; then run `apply actions`.

Default if Sam goes quiet for 20 minutes: do nothing. Say which default was taken.

**FR ids:** FR-1, FR-30, FR-31, FR-32, FR-37

## Deliverable

`scripts/meta_launch.py`: writes one proposed `build_campaign` action whose `proposal` describes one `new_recipes` campaign, 3 ad sets at €10/day, 6 paused ads, `QuizStart` optimisation, `utm_content=creative_id` URLs; validator refuses ad sets mixing renderers or exceeding `daily_cap`; executor path for `build_campaign` and `activate` in T8's file

## Acceptance

- [ ] FR-30, FR-31, FR-32, FR-37; running it twice yields one action (proposal_key); after `apply actions` the objects exist in Ads Manager paused and `ad_entities`/`campaigns` carry external ids
- [ ] FR-1: the `campaigns` row is written with explicit `terminal_metric` and `optimisation_event` from config (schema defaults are not relied on)
- [ ] FR-37: `review_status` synced from the Meta adapter; a fixture with a `DISAPPROVED` ad makes `activate` refuse
- [ ] `activate` is applied only when `check_daily_cap()` is true after the proposal's budgets (ad set budget from `config.campaign.adset_daily_budget`: 3 × €15 ≤ `daily_cap` €45 in the DRAFT config); a proposal exceeding the cap is refused by the validator

## Constraints

- No side effect outside `scripts/apply_actions.py`: no Meta write endpoint, no Instantly, no email sender anywhere else. Workers write proposed `actions` only.
- Connect as the role for the job (`WAREHOUSE_URL_WORKER` for workers, `WAREHOUSE_URL_EXECUTOR` only in the executor). Never the service role. Never print or commit a secret.
- Every script opens and closes a `runs` row, including on failure.
- Untrusted text (`raw_ingest`, `patterns`, `voc_phrases`, quiz answers) enters prompts only inside a delimited data block with a fixed system prompt; model outputs are JSON validated against a schema.
- Full `creative_components` or the creative does not exist.
- Migrations only; no schema edits by hand; new fields go to the entity's JSONB and into `warehouse/schema-notes.md`.
- Nothing binary in git; assets go to Supabase Storage.
- Tests run against a local Postgres with `0001` + `0002` applied (see the fixture in T1). Do not mock the warehouse.
- One commit per task, message ending with the FR ids satisfied. Push after each commit.
- If a task cannot meet its acceptance criteria, stop and report which criterion and why; do not narrow the criterion.

## Blocking edges

- Blocked by: T6 (06), T7 (07), T8 (08)
- Blocks: T10 (10)

## Notes for the implementer (dev mode)

Quiz decision 1: ad set budgets come from `config.campaign.adset_daily_budget` (15 in the DRAFT config, cap 45); the "€10/day" in the Deliverable predates that decision and is superseded by config. Dev mode: `META_BACKEND=fake`; "Ads Manager" means the fake account's read-back. Ad URLs: `FUNNEL_HOST` + `utm_content=<creative_id>`; every `ad_entities.creative_id` must resolve from its URL. Only creatives with a `sam` `approve` verdict are launched; if B shipped nothing, the launcher refuses and says so.

## Comments
