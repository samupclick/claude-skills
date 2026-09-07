# 08: Executor (T8)

**What to build:** Running `apply actions` transitions approved (or execute-trust) actions exactly per `SKILL.md` §6 against the Meta adapter, and `decide.py` records Sam's chat approvals; every side effect in the codebase goes through this one file.

**Blocked by:** T1 (01)

**Blocks:** T9 (09)

**Status:** ready-for-human (review the shipped commit; code complete, all acceptance criteria pass)

**Done:** yes — 4e481e7

**Stop point:** none

**FR ids:** FR-44, FR-45, FR-46, FR-47

## Deliverable

`scripts/apply_actions.py` exactly per `SKILL.md` §6: advisory lock, pause re-check, `check_daily_cap()`, rate limits from config, `applying` before any external call, name lookup before every Meta create, external ids written immediately, `applied` only after read-back, `--reconcile` mode; `scripts/decide.py` writing approvals with `decision_channel='chat'`; Meta calls only in this file

## Acceptance

- [x] FR-44 to FR-47; two concurrent executors apply each action once (test with a fake Meta client); a crash after create leaves no orphan on re-run; grep for Meta write endpoints outside this file returns nothing
- [x] FR-44: the `0002` guard tests (worker transition, worker non-proposed insert, executor promote of `promote_trust`/`quote_release`/`set_pause_flag`) all raise
- [x] FR-46: trust is read from `trust_streaks`; an `auto` decision never increments a streak; a promoted type is rate-limited per `config.rate_limits` and demoted on any executor failure
- [x] FR-47: `clients.paused` and `PIPELINE_PAUSED` leave rows untouched; three consecutive failures of one action type propose `set_pause_flag`; each brake trigger has a fixture
- [x] `--reconcile`: an `applying` row older than 15 minutes is set to `applied` or `failed` by comparing against the fake Meta account by name/id, never re-sent

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

- 2026-09-07 (implementer): shipped in commit 4e481e7. `scripts/apply_actions.py` (SKILL.md §6 steps 1–8: session advisory lock per run plus `pg_advisory_xact_lock` and `for update skip locked` per action; pause re-check inside the transaction; `check_daily_cap()` evaluated with the proposal's budgets applied in a savepoint; rate limits from `clients.config.rate_limits` for autonomous rows; `applying` committed before the Meta call; read-back before `applied`; warehouse mirrored from Meta's answer on both paths; `--reconcile`), `scripts/decide.py` (§5.3 chat decisions, `decision_channel='chat'`, `approved_payload = proposal`, stable action numbers), `warehouse/0004_executor_runs.sql`, `tests/test_apply_actions.py` (18) + `tests/test_decide.py` (7). Full suite: 84 passed against the real local cluster. Review fixes folded in: stable numbering in decide.py, guarded failed-mark, kill promotion needs `backtest_accuracy`.
- 2026-09-07 (implementer): **grant gap, migration added.** `0002` grants `update` on `runs` to `worker_rw` only, so the executor could open its runs row and never close it. `0006_executor_runs.sql` grants the same six columns to `executor` (column grants only, same shape as 0003). Listed in `schema-notes.md`; `dev_db.sh` and the test fixture pick it up by number. Sam to confirm, as with 0003.
- 2026-09-07 (implementer): **role split.** `set_pause_flag`, `promote_trust`, `quote_release` cannot be approved or applied by the executor role (0002 trigger blocks `approved`/`applied`; no update grant on `clients`). Sam approves them with `decide.py --as sam_admin` and applies with `apply_actions.py --role sam_admin`, which never instantiates the Meta adapter. The role name maps to `WAREHOUSE_URL_SAM_ADMIN` (T0's naming); SKILL.md §1/§5.3 still say `WAREHOUSE_URL_ADMIN`, which T0 uses for the local superuser — T12 should reconcile the wording.
- 2026-09-07 (implementer): **demotion is computed** (executor cannot write `clients.config`): a type runs autonomously only when `config.trust.<type>.level='execute'`, `trust_streaks.streak >= threshold`, and no `failed` action of that type exists since the last applied `promote_trust` for it. Any executor failure (Meta error, `daily_cap`, bad target) therefore demotes at once; Sam re-arms with `promote_trust`. Promoting `kill` to `execute` requires `proposal.backtest_accuracy >= trust.kill.backtest_min_accuracy` (FR-46); the executor does not compute the back-test itself.
- 2026-09-07 (implementer): semantics chosen: `kill` → Meta `ARCHIVED` (final, reporting kept), `pause` → `PAUSED`; `scale` refuses steps over 20% (FR-31) and writes the new budget to every `ad_entities` row of that ad set; `activate` refuses `review_status='DISAPPROVED'` (FR-37) and syncs `review_status`/`review_feedback` from the read-back. A `failed` row is retried by re-approving it (`decide.py approve <n|id>`); `proposal_key` uniqueness means workers cannot re-propose it.
- 2026-09-07 (implementer): brakes in T8: `clients.paused`, `PIPELINE_PAUSED`, three consecutive failures of one type, hourly spend above `daily_cap` (latest `account_spend_hourly` today; also holds budget-affecting rows for that run). Error-rate spike and lead velocity are noted on T11. Known trap for T9: `check_daily_cap()` sums `adset_daily_budget` per ad row, so two ads per ad set double-count (comment on 09).
- 2026-09-07 (implementer): `runs` proof on the dev database (no actions waiting): `41ed63f6-d5fc-429a-91f4-69a05e5809cc | executor | 2026-09-07 06:22:39.77 → 06:22:39.79 | ok | {}`. Unblocked now: T2, T3, T7 (already open); T9 waits on T6 and T7.

