# 08: Executor (T8)

**What to build:** Running `apply actions` transitions approved (or execute-trust) actions exactly per `SKILL.md` §6 against the Meta adapter, and `decide.py` records Sam's chat approvals; every side effect in the codebase goes through this one file.

**Blocked by:** T1 (01)

**Blocks:** T9 (09)

**Status:** ready-for-agent

**Done:** no

**Stop point:** none

**FR ids:** FR-44, FR-45, FR-46, FR-47

## Deliverable

`scripts/apply_actions.py` exactly per `SKILL.md` §6: advisory lock, pause re-check, `check_daily_cap()`, rate limits from config, `applying` before any external call, name lookup before every Meta create, external ids written immediately, `applied` only after read-back, `--reconcile` mode; `scripts/decide.py` writing approvals with `decision_channel='chat'`; Meta calls only in this file

## Acceptance

- [ ] FR-44 to FR-47; two concurrent executors apply each action once (test with a fake Meta client); a crash after create leaves no orphan on re-run; grep for Meta write endpoints outside this file returns nothing
- [ ] FR-44: the `0002` guard tests (worker transition, worker non-proposed insert, executor promote of `promote_trust`/`quote_release`/`set_pause_flag`) all raise
- [ ] FR-46: trust is read from `trust_streaks`; an `auto` decision never increments a streak; a promoted type is rate-limited per `config.rate_limits` and demoted on any executor failure
- [ ] FR-47: `clients.paused` and `PIPELINE_PAUSED` leave rows untouched; three consecutive failures of one action type propose `set_pause_flag`; each brake trigger has a fixture
- [ ] `--reconcile`: an `applying` row older than 15 minutes is set to `applied` or `failed` by comparing against the fake Meta account by name/id, never re-sent

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
- Blocks: T9 (09)

## Notes for the implementer (dev mode)

Runs with `WAREHOUSE_URL_EXECUTOR` only; `decide.py` writes approvals as the executor role with `decided_by='sam'`, `decision_channel='chat'`, `approved_payload = proposal`. Action types handled here: `pause`, `kill`, `activate`, `scale`, `set_pause_flag` (admin only) plus the generic state machine; `build_campaign` is added by T9 in this same file. Fake Meta `META_FAKE_FAIL=<step>` drives the crash test.

## Comments
