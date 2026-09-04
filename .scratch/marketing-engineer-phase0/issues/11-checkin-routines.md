# 11: Check-in + routines (T11)

**What to build:** Running `check-in` sends the five-part email through the email adapter, `pause.py` proposes `set_pause_flag`, the three routines from `SKILL.md` §8 are defined and dry-run, and a SessionStart hook prepares a fresh remote session (Chromium, Python deps, secrets).

**Blocked by:** T10 (10)

**Blocks:** T12 (12)

**Status:** ready-for-agent

**Done:** no

**Stop point:** none

**FR ids:** FR-42, FR-47, FR-48

## Deliverable

`scripts/checkin.py`: five parts in order, email via the Gmail connector, golden-file test; `scripts/pause.py`; routine definitions from `SKILL.md` §8 registered; SessionStart hook (use the `session-start-hook` skill) installing Chromium, Python deps, secrets

## Acceptance

- [ ] FR-42, FR-47, FR-48; a check-in email is received; the 08:00 routine fires once in dry-run
- [ ] FR-42: exactly five parts in order (actions waiting with reasons, actions taken, active lever per campaign, new learnings, warnings); the body escapes all content and carries no URL from rows below `owned`
- [ ] A `runs` row left in `running` by a crashed script appears in the warnings part
- [ ] FR-48: routine definitions checked into `SKILL.md` §8 match what is registered; the hook installs Chromium, Python deps, and reads secrets without printing them

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

- Blocked by: T10 (10)
- Blocks: T12 (12)

## Notes for the implementer (dev mode)

Dev mode: `EMAIL_BACKEND=file` writes `.dev/outbox/*.eml`; "received" means the `.eml` exists and matches the golden file. Quiz decision 7 (Sam, 2026-09-04): "registered" here means the three routine definitions exist in the repo (`SKILL.md` §8 plus a machine-readable file) and one dry-run of the 08:00 prompt is executed locally; real registration as Claude Code Routines is T13's step 7. `pause.py` writes a proposed `set_pause_flag` as a worker; approval needs `WAREHOUSE_URL_ADMIN`.

## Comments
