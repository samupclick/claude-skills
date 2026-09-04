# 06: Gate (T6)

**What to build:** Running `gate` scores every draft creative: hard checks into `gate_scores.hard_checks`, a shadow rubric row by the agent, and prints the numbered creative table for Sam; `--verdicts` writes Sam's chat verdicts as `gate_scores` rows.

**Blocked by:** T5 (05)

**Blocks:** T9 (09)

**Status:** ready-for-agent

**Done:** no

**Stop point:** B — T6 done: print the numbered creative table with Storage URLs and hard-check results; wait for `verdicts: approve …; reject …: reason`.

Default if Sam goes quiet for 20 minutes: ship nothing. Say which default was taken.

**FR ids:** FR-12 (hard check), FR-26, FR-27, FR-29

## Deliverable

`scripts/gate.py`: hard checks (policy prompt, brand hard blocks, likeness, testimonial block, coherence → planner, components, landing URL match, verbatim phrase without release) into `gate_scores.hard_checks`; rubric in `mode='shadow'`; `--verdicts "approve 1,3; reject 2: reason"` writes `scored_by='sam'`, `decision_channel='chat'`; prints the §5.2 table

## Acceptance

- [ ] FR-26, FR-27, FR-29; one fixture per hard check that fails it; no `agent` row ever has `mode='blocking'`
- [ ] FR-29: a hard-check failure records the feedback object and attempt number; attempt 4 is impossible (the fourth attempt is refused and logged)
- [ ] FR-12: an `internal` phrase used verbatim without an applied `quote_release` action fails the `verbatim` hard check

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

- Blocked by: T5 (05)
- Blocks: T9 (09)

## Notes for the implementer (dev mode)

Policy and rubric prompts run through the model adapter with the creative text inside the delimited data block; outputs are schema-validated JSON. The §5.2 table shows the Storage URL, the source ad URL (our copy), hard-check results, and shadow rubric scores. Coherence failures route feedback to the planner (recorded, not re-run automatically).

## Comments
