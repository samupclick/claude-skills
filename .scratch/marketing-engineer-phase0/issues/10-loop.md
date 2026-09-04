# 10: Loop (T10)

**What to build:** Running `pull insights` appends ad-level daily metrics and account-level hourly spend from the Meta adapter, selects the active lever per campaign with a reason, turns kill/scale view rows into proposed actions with evidence, and writes agent learnings only through the FR-41 gates.

**Blocked by:** T9 (09)

**Blocks:** T11 (11)

**Status:** ready-for-agent

**Done:** no

**Stop point:** D — T10's first insights pull: show the `where are we` table and the kill/scale view output; ask me for the first `learnings` row text (`created_by='sam'`, `evidence.sample_reached=false`).

Default if Sam goes quiet for 20 minutes: write no row. Say which default was taken.

**FR ids:** FR-2, FR-3, FR-38, FR-39, FR-40, FR-41

## Deliverable

`scripts/meta_insights.py`: ad-level daily → `ad_metrics_daily` (append, `fetched_on`), account-level hourly → `account_spend_hourly`, lever selection from config floors → `campaigns.active_lever` + reason, kill/scale from `mart_kill_scale_candidates` → proposed actions with `evidence`, learnings only through the FR-41 gates, `cpl_target` derivation stub

## Acceptance

- [ ] FR-38 to FR-41; restated day yields two rows and one latest; `config_missing` is a hard stop; no agent learning without a creative at sample size
- [ ] FR-2, FR-3: `active_lever` is in the static chain; with only config floors the `active_lever_reason` names the floor source
- [ ] FR-39: the view's fixture set (config missing, hold, kill, scale) passes; every non-hold recommendation becomes a proposed action with `evidence`
- [ ] FR-40: `cpl_target` derivation function unit-tested; conversion-stage rules advisory until 100 link clicks
- [ ] FR-41: the "zero learnings" warning is raised only when a creative reached sample size

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
