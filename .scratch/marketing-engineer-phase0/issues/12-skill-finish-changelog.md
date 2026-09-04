# 12: Skill finish + changelog (T12)

**What to build:** A fresh session invoking the `marketing-engineer` skill can answer "where are we" and find every phase-0 script, worker prompt, and JSONB key documented.

**Blocked by:** T0–T11 (00–11), all

**Blocks:** T13 (13)

**Status:** ready-for-agent

**Done:** no

**Stop point:** none

**FR ids:** FR-48, DR-3, NFR-6 (DoD `PLAN.md` §1 item 11)

## Deliverable

`SKILL.md` §3 table matches the scripts that exist; `references/prompts/<worker>.md` for each worker prompt used; `warehouse/schema-notes.md` listing any JSONB keys introduced; `CHANGELOG.md`

## Acceptance

- [ ] DoD `PLAN.md` §1 item 11; a fresh session invoking "where are we" works end to end
- [ ] `SKILL.md` §3 rows for scripts that do not exist in phase 0 (`monday_memo.py`, `onboard.py`) say so explicitly rather than pointing at missing files
- [ ] Every fixed system prompt used by a worker is in `references/prompts/<worker>.md` and the code loads it from there
- [ ] `warehouse/schema-notes.md` lists every JSONB key phase 0 introduced (`clients.config`, `patterns.recipe`, `actions.proposal`/`evidence`, `gate_scores.hard_checks`/`feedback`, `learnings.evidence`, `runs.counts`)

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

- Blocked by: T0–T11 (00–11), all
- Blocks: T13 (13)

## Notes for the implementer (dev mode)

No new behaviour here; documentation and the end-to-end dry run only. Note in `CHANGELOG.md` which placeholders (config, families, VOC seed, fixture shape) remain DRAFT.

## Comments
