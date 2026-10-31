# 03: Language: VOC seed (T3)

**What to build:** Running `pull voc` turns the synthetic vault notes and the configured public thread URLs into anonymised `voc_phrases` rows with source pointers, weights, visibility, and trust tier, deduplicated on `(source_ref, phrase_normalised)`.

**Blocked by:** T1 (01)

**Blocks:** T4 (04)

**Status:** ready-for-human (review the shipped commit; code complete, all acceptance criteria pass)

**Done:** yes — f408777

**Stop point:** none

**FR ids:** FR-10, FR-11, FR-12, FR-13

## Deliverable

`scripts/pull_voc.py`: `voc-seed/` notes + 2–3 Reddit thread URLs from config → anonymise (names, companies, figures) → `voc_phrases` with `source_ref`, `source_weight`, `visibility`, `trust_tier`, dedup on `(source_ref, phrase_normalised)`

## Acceptance

- [x] FR-10 to FR-13; ≥ 15 rows; seeded fake name in a fixture fails the validator; no write path to the vault
- [x] Vault-derived phrases are `visibility='internal'`, `source_weight=3`, `trust_tier='owned'`; public-thread phrases are `visibility='public'`, `source_weight=1`, `trust_tier='public'`
- [x] Re-running against the same inputs adds zero rows (unique constraint exercised, not bypassed)

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

The `voc.public_sources` entries in the client config are PLACEHOLDER URLs; in dev mode the public source reads a local fixture thread (`fixtures/voc/`), never the network. The synthetic notes carry fake names (e.g. the Nordic Consulting note) on purpose for the anonymiser test. `voc_phrases` has no `quotes` column; store `source_ref` only.

## Comments

- 2026-09-07 (implementer): shipped in commit f408777. `scripts/pull_voc.py`, `adapters/voc/` (`VOC_BACKEND=fixture|reddit`), `fixtures/voc/` (SYNTHETIC threads), `fixtures/model/voc_extract.json`, `references/prompts/language.md`, `tests/test_pull_voc.py` + `tests/test_voc_adapter.py` (18 tests). Full suite: 77 passed against the real local cluster.
- 2026-09-07 (implementer): proof on the dev database `gw` with `MODEL_BACKEND=fixture`: first run `f29de51a…` status `ok`, counts `sources_vault 3, sources_public 3, raw_ingest_inserted 6, phrases_extracted 27, phrases_inserted 27, phrases_duplicates 0, phrases_rejected_identifiers 0`, `api_calls 6`; second run `7bc54032…` status `ok`, `phrases_inserted 0, phrases_duplicates 27, raw_ingest_duplicates 6` (the `unique (source_ref, phrase_normalised)` constraint fires per row through a savepoint; nothing is pre-filtered). 14 vault rows (`internal`, 3, `owned`) and 13 public rows (`public`, 1, `public`, source `reddit`).
- 2026-09-07 (implementer): FR-11 validator is two layers: the model anonymises at extraction and lists `identifiers_removed`; `validate_phrase()` then rejects any phrase that still contains a proper-noun run, headcount, money amount, email, handle, or phone found in the source, or anything on the model's list. The seeded fake names (`Henrik Lindqvist`, `Nordic Consulting AB`, `Priya Raman`, `BrightPath Software Ltd`) and figures (`40k`, `48 staff`, `120 staff`) are all found by rule; a model fixture that leaks one never reaches `voc_phrases` and is counted in `phrases_rejected_identifiers`. Single capitalised words (a city) rely on the model's list.
- 2026-09-07 (implementer): FR-10: the worker reads `voc.seed_dir` only and never opens `voc.vault_path`; a static test greps the script and adapter for any write call, and the end-to-end test hashes the seed folder before and after a run. FR-12: rows carry `visibility='internal'`; the gate hard check that enforces `quote_release` is T6's.
- 2026-09-07 (implementer): decisions taken, for Sam to overrule: (1) `voc.public_sources` in the DRAFT config now holds three distinct PLACEHOLDER URLs (`…/1`, `…/2`, `…/3`) so the "2–3 thread URLs" deliverable is exercised; the fixture threads match those strings, so replacing them at go-live makes the fixture backend refuse with a message naming T13. The worker reads the config file, not `clients.config` (the seed does not update an existing row). (2) Vault notes go into `raw_ingest` as `{path, sha256, bytes}` only, never the note text; public threads are stored as fetched (no author field exists in the adapter shape) with `purge_after` = fetched + 90 days. (3) Every run re-extracts every source so the constraint is exercised; with `MODEL_BACKEND=claude` that is one small call per source (6 today). (4) `fixtures/model/voc_extract.json` is hand-written from the synthetic notes because the build container has no `ANTHROPIC_API_KEY`; re-record it once the seed notes are real. (5) A paused pipeline closes the `runs` row as `failed` with error `pipeline paused …` and exits 2, following SKILL.md §0 order (row opened at step 2, pause checked at step 4).
- 2026-09-07 (implementer): T4 is unblocked on the T3 side (still needs T2).
