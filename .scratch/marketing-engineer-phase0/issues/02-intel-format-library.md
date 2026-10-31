# 02: Intel: format library (T2)

**What to build:** Running `pull inspo` fills `raw_ingest` and `patterns` for the 5 DTC seed brands from the inspo adapter (fixture in dev mode), with every source image copied to storage and every pattern decomposed into a family, variant, format layer, source strength, and status by the 30-day / 3-variant rule.

**Blocked by:** T1 (01)

**Blocks:** T4 (04)

**Status:** ready-for-human (review the shipped commit; code complete, all acceptance criteria pass)

**Done:** yes — 1a4069a

**Stop point:** none

**FR ids:** FR-4, FR-5, FR-6, FR-8

## Deliverable

`scripts/pull_inspo.py`: scrapecreators Ad Library → `raw_ingest` (dedup_key) → download every snapshot image to Storage → vision decomposition (Claude) into `patterns` with `family` from `families`, `variant`, `recipe.format_layer`, `source_strength`, `status` by the 30-day / 3-variant rule → `runs` counts

## Acceptance

- [x] FR-4, FR-5, FR-6, FR-8; ≥ 24 rows for the 5 seed brands; re-run adds zero duplicates; a pattern with a CDN URL and no Storage copy is rejected
- [x] FR-6 unit test on both branches (`start_date ≤ today − 30 days`; `concurrent_variants ≥ 3` from the same brand)
- [x] FR-8: zero new patterns is `status='ok'`; a failed source is retried once then written as a warning; two consecutive failures on one source are recorded so the planner can refuse with the source named

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

- 2026-09-07 (implementer): shipped in commit 1a4069a. `scripts/pull_inspo.py` (`pull inspo`; `--today`, `--brands`, `--client`, `--acknowledge <source>`), `warehouse.client.blocked_sources()` (the FR-8 read for T4), model adapter `images=` for vision (Claude sends image blocks; fixture ignores), `INSPO_FIXTURE_FAIL` on the fixture ad library, `fixtures/model/decompose_ad.json`, `tests/test_pull_inspo.py` (13 tests). Full suite: 72 passed against the real local cluster. Proof on the dev database with `MODEL_BACKEND=fixture`: first run `ads 30, raw_ingest new 30, images 45, patterns new 30 (proven 25, candidate 5)`; second run `raw_ingest new 0 seen 30, patterns new 0 seen 30`, status ok; `where are we` now shows `proven_patterns 25`.
- 2026-09-07 (implementer): FR-8 conventions for T4. Per-source outcomes live in `runs.counts.sources_ok` / `sources_failed` (worker `intel`); `blocked_sources(conn)` returns the sources whose last two outcomes are both failures and no `acknowledged` entry came after; the planner refuses `plan batch` naming them. `scripts/pull_inspo.py --acknowledge <source>` writes the acknowledgement run (SKILL.md §7 `acknowledge <source>`). A failed source (after one retry) is a warning: the run stays `status='ok'` and the other sources are pulled; PRD FR-8 wins over SKILL.md §7's `status='failed'` wording (precedence in spec.md).
- 2026-09-07 (implementer): FR-6 details. `concurrent_variants` counts the brand's active ads in the same family (known + new in this run); inactive ads get 0 for that branch. `source_strength` = (age branch) + (concurrency branch) + (is_active), 0..3, ordinal only (CRUCIBLE A7). `days_running` runs to `end_date` for ended ads, else to `today`. Re-runs promote a known candidate that now meets the rule (0002 grants worker_rw update on `patterns.status`); nothing is ever demoted. Patterns dedup on `recipe.source.ad_id`; a changed vendor row adds a new `raw_ingest` row (content hash) but no second pattern.
- 2026-09-07 (implementer): no `ANTHROPIC_API_KEY` in the build container, so `MODEL_BACKEND=claude` is wired (image blocks + `output_config` JSON schema) but unexercised; `decompose_ad.json` is SYNTHETIC, not recorded (its `_shape` says so and how it lines up with the six fixture ads per brand). Because the seed skips `contrarian` and `identity` (families.md name conflict, T0 comment), the decomposition schema's hook-type enum currently has five values; once Sam renames the two angles and re-seeds, the enum grows on its own (it is built from the live `families` table each run). T4 is unblocked on the T2 side (T3 still open).
