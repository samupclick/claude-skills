# 10: Loop (T10)

**What to build:** Running `pull insights` appends ad-level daily metrics and account-level hourly spend from the Meta adapter, selects the active lever per campaign with a reason, turns kill/scale view rows into proposed actions with evidence, and writes agent learnings only through the FR-41 gates.

**Blocked by:** T9 (09)

**Blocks:** T11 (11)

**Status:** ready-for-human (review the shipped commit; code complete, all acceptance criteria pass; stop point D on the dev database printed with an empty account, waiting for Sam's learning text)

**Done:** yes — 10ae6de

**Stop point:** D — T10's first insights pull: show the `where are we` table and the kill/scale view output; ask me for the first `learnings` row text (`created_by='sam'`, `evidence.sample_reached=false`).

Default if Sam goes quiet for 20 minutes: write no row. Say which default was taken.

**FR ids:** FR-2, FR-3, FR-38, FR-39, FR-40, FR-41

## Deliverable

`scripts/meta_insights.py`: ad-level daily → `ad_metrics_daily` (append, `fetched_on`), account-level hourly → `account_spend_hourly`, lever selection from config floors → `campaigns.active_lever` + reason, kill/scale from `mart_kill_scale_candidates` → proposed actions with `evidence`, learnings only through the FR-41 gates, `cpl_target` derivation stub

## Acceptance

- [x] FR-38 to FR-41; restated day yields two rows and one latest; `config_missing` is a hard stop; no agent learning without a creative at sample size
- [x] FR-2, FR-3: `active_lever` is in the static chain; with only config floors the `active_lever_reason` names the floor source
- [x] FR-39: the view's fixture set (config missing, hold, kill, scale) passes; every non-hold recommendation becomes a proposed action with `evidence`
- [x] FR-40: `cpl_target` derivation function unit-tested; conversion-stage rules advisory until 100 link clicks
- [x] FR-41: the "zero learnings" warning is raised only when a creative reached sample size

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

- Blocked by: T9 (09)
- Blocks: T11 (11)

## Notes for the implementer (dev mode)

Dev mode: the fake Meta account synthesises insights from a seed; sub-sample numbers are expected, so the view returns `hold` and no agent learning is written. Writing `campaigns.active_lever*` as a worker uses the `0003` grant from T1. Stop point D's learning row is written with `created_by='sam'`, `status='proposed'`, `evidence.sample_reached=false`.

## Comments
- 2026-09-09 (implementer): shipped in commit 10ae6de. `scripts/meta_insights.py` (worker `loop`, `worker_rw`, reads through the Meta adapter only, no create/update), `tests/test_meta_insights.py` (11). Full suite: 211 passed on the local cluster. No migration: every write uses a 0002/0003 grant (`ad_metrics_daily`, `account_spend_hourly`, `actions`, `learnings` inserts; `campaigns.active_lever*` and `learnings (posterior, effect_size, sample, evidence, updated_at)` updates).
- 2026-09-09 (implementer): shapes. FR-38: one `insert … on conflict (ad_entity_id, day, fetched_on) do nothing` per (ad, day) with `fetched_on = --today` (default today) over `--days` (default 7); the same fetch date never doubles a row, a later fetch date restates (test: two rows, `ad_metrics_latest` shows the newest). `quiz_starts` / `quiz_completes` / `schedules` come from Meta's `actions` and stay Meta-reported context; decisions use warehouse leads. One `account_spend_hourly` row per run from `account_spend_today()`. FR-2/FR-3: campaign totals from `ad_metrics_latest` + `leads` (starts = leads, completes = stage ≥ completed, bookings = `booked_verified_at`); CTR-stage sample = `targets.kill_impressions` impressions, conversion-stage sample = `targets.sample_clicks` link clicks (100 when unset, DECISIONS C7); a lever not yet at sample size stays active with `waiting for sample size` (downstream levers have less data); `hook_rate` is rung zero only when a creative of the campaign carries a `family` component whose `families.kind = 'video'` (none in phase 0). Benchmarks: own history is not implemented in phase 0 (nothing proven yet; the resolver accepts it), `mart_benchmarks` gives `cost_per_link_click` once ≥3 clients exist, else the config floor and the reason names `config floor floors.<lever>`; `cost_per_booked_call` uses `targets.cpl_target` and is `cannot be judged` while it is unset (FR-40 advisory). FR-39: `config_missing` from the view is a hard stop, though SKILL.md §0 refuses first when `targets.ctr_floor` / `kill_impressions` are unset (the test shows the view row and the refusal); rules `ctr_floor`, `cpl_expected_bookings`, `cpl_scale`; `scale` proposes one 20% step from the ad set's current budget; an open action of the same type for the same ad is never re-proposed; `evidence.advisory = true` marks a conversion-stage rule below the click sample. FR-40: `derive_cpl_target()` unit-tested; the derived number is printed and stored in `runs.counts.cpl_target_derived`, never written to `clients.config` (Sam, `sam_admin`; `targets.cpl_target_floor` optional). FR-41: arms are one component value vs the client's other creatives on link CTR (`family`, `variant`, `hook_type`, `angle`, `template`, `renderer`, `image_model`, `cta`, `copy_length`, `proof_type`); posterior by seeded Beta(1,1) sampling (20k draws, no scipy); a second run updates the existing proposed row instead of duplicating; gate reasons go to `runs.counts.learnings_refused`; the zero-learnings warning fires only with a creative at sample size and neither a row written nor a reason recorded.
- 2026-09-09 (implementer): **stop point D on the dev database: printed, waiting for Sam.** `python3 scripts/meta_insights.py` on `gw` (no ads yet on this container) closed `runs 4bc99f01-ce8d-40c6-987f-8e4c4ae60feb | loop | ok` with the `where are we` table and `kill/scale view: no ACTIVE ad with metrics`. Sam's reply is the hypothesis text: `python3 scripts/meta_insights.py --learning "…"` writes it with `created_by='sam'`, `status='proposed'`, `evidence.sample_reached=false`. Default if Sam is quiet 20 minutes: no row (nothing was written; the default was taken here because no reply exists).
- 2026-09-09 (implementer): notes for later tickets. T11: the check-in's "active lever per campaign" reads `campaigns.active_lever`, `active_lever_reason`, `active_lever_since` (moved = `active_lever_since` after the last check-in); "warnings" reads `runs.counts.warnings` of the latest `loop` run plus the `learnings_refused` count; "new learnings" reads `learnings` proposed since the last check-in. Not in T10 (FR-37 second half, noted on T9): syncing `ad_entities.review_status` during the pull is impossible under 0002 (the worker has no update on `ad_entities`); the disapproval-count brake needs either an executor-side sync in `--reconcile` or a column grant in a later migration, Sam to decide. The lead-velocity brake (A11) is T11's with the error-rate spike.
