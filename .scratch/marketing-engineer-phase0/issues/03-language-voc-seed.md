# 03: Language: VOC seed (T3)

**What to build:** Running `pull voc` turns the synthetic vault notes and the configured public thread URLs into anonymised `voc_phrases` rows with source pointers, weights, visibility, and trust tier, deduplicated on `(source_ref, phrase_normalised)`.

**Blocked by:** T1 (01)

**Blocks:** T4 (04)

**Status:** ready-for-agent

**Done:** no

**Stop point:** none

**FR ids:** FR-10, FR-11, FR-12, FR-13

## Deliverable

`scripts/pull_voc.py`: `voc-seed/` notes + 2–3 Reddit thread URLs from config → anonymise (names, companies, figures) → `voc_phrases` with `source_ref`, `source_weight`, `visibility`, `trust_tier`, dedup on `(source_ref, phrase_normalised)`

## Acceptance

- [ ] FR-10 to FR-13; ≥ 15 rows; seeded fake name in a fixture fails the validator; no write path to the vault
- [ ] Vault-derived phrases are `visibility='internal'`, `source_weight=3`, `trust_tier='owned'`; public-thread phrases are `visibility='public'`, `source_weight=1`, `trust_tier='public'`
- [ ] Re-running against the same inputs adds zero rows (unique constraint exercised, not bypassed)

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
