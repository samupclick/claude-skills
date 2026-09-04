# 02: Intel: format library (T2)

**What to build:** Running `pull inspo` fills `raw_ingest` and `patterns` for the 5 DTC seed brands from the inspo adapter (fixture in dev mode), with every source image copied to storage and every pattern decomposed into a family, variant, format layer, source strength, and status by the 30-day / 3-variant rule.

**Blocked by:** T1 (01)

**Blocks:** T4 (04)

**Status:** ready-for-agent

**Done:** no

**Stop point:** none

**FR ids:** FR-4, FR-5, FR-6, FR-8

## Deliverable

`scripts/pull_inspo.py`: scrapecreators Ad Library → `raw_ingest` (dedup_key) → download every snapshot image to Storage → vision decomposition (Claude) into `patterns` with `family` from `families`, `variant`, `recipe.format_layer`, `source_strength`, `status` by the 30-day / 3-variant rule → `runs` counts

## Acceptance

- [ ] FR-4, FR-5, FR-6, FR-8; ≥ 24 rows for the 5 seed brands; re-run adds zero duplicates; a pattern with a CDN URL and no Storage copy is rejected
- [ ] FR-6 unit test on both branches (`start_date ≤ today − 30 days`; `concurrent_variants ≥ 3` from the same brand)
- [ ] FR-8: zero new patterns is `status='ok'`; a failed source is retried once then written as a warning; two consecutive failures on one source are recorded so the planner can refuse with the source named

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

- Blocked by: T1 (01)
- Blocks: T4 (04)

## Notes for the implementer (dev mode)

Dev mode: `INSPO_BACKEND=fixture`, `STORAGE_BACKEND=local`, `MODEL_BACKEND=claude` (or `fixture` in CI). Vision decomposition output is JSON validated against a schema; fixture payloads enter the prompt only inside the delimited data block. `families` must already be seeded (T0 `--seed`).

## Comments
