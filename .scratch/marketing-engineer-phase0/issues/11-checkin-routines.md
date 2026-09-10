# 11: Check-in + routines (T11)

**What to build:** Running `check-in` sends the five-part email through the email adapter, `pause.py` proposes `set_pause_flag`, the three routines from `SKILL.md` §8 are defined and dry-run, and a SessionStart hook prepares a fresh remote session (Chromium, Python deps, secrets).

**Blocked by:** T10 (10)

**Blocks:** T12 (12)

**Status:** ready-for-human (review the shipped commit; code complete, all acceptance criteria pass in dev mode)

**Done:** yes — e87c285

**Stop point:** none

**FR ids:** FR-42, FR-47, FR-48

## Deliverable

`scripts/checkin.py`: five parts in order, email via the Gmail connector, golden-file test; `scripts/pause.py`; routine definitions from `SKILL.md` §8 registered; SessionStart hook (use the `session-start-hook` skill) installing Chromium, Python deps, secrets

## Acceptance

- [x] FR-42, FR-47, FR-48; a check-in email is received (`.dev/outbox/*.eml` in dev mode; `tests/test_checkin.py`, `tests/test_routines.py`); the 08:00 routine fires once in dry-run (`scripts/routines.py dry-run me-morning` on the dev database: status ok, pull insights ok, apply actions --reconcile ok, check-in ok, exit 0, runs summary printed)
- [x] FR-42: exactly five parts in order (actions waiting with reasons, actions taken, active lever per campaign, new learnings, warnings); the body escapes all content and carries no URL from rows below `owned` (`clean()` removes every URL from row text, the HTML part is the escaped text; golden `fixtures/checkin/golden-body.txt`)
- [x] A `runs` row left in `running` by a crashed script appears in the warnings part (older than `--stale-minutes`, default 15, own run excluded)
- [x] FR-48: routine definitions checked into `SKILL.md` §8 match what is registered (`config/routines.json` is the twin; `scripts/routines.py check` and a test fail on drift; registration itself is T13 step 7 per quiz decision 7); the hook installs Chromium, Python deps, and reads secrets without printing them (`.claude/hooks/session-start.sh`, names only; `tests/test_session_hook.py` runs it with a fake secret and asserts it never appears)

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
- 2026-09-07 (T8 implementer): of the FR-47 brake triggers, T8 covers `clients.paused`, `PIPELINE_PAUSED`, three consecutive failures of one action type, and hourly account spend above `daily_cap` (each proposes `set_pause_flag`, idempotent, one open proposal per rule). The worker error-rate spike (threshold still an open decision in DECISIONS.md C9: default >30% of a worker's runs failing over 1 hour) and lead velocity >3× the 7-day median are not in the executor; they read `runs` and `leads` and belong with the check-in / loop. Their fixtures are still owed for FR-47's AC. The morning routine's `apply actions --reconcile` runs reconcile first and then the normal pass; a row in `applying` younger than 15 minutes blocks the normal pass (SKILL.md §7) and the run closes `failed` with the reason, which the check-in should report.
- 2026-09-10 (T11 implementer): started at Sam's "start t11" while T10 was still open in another session; T5, T6, T9, T10 landed on the branch before this commit and it was rebased onto them (230 tests pass after the rebase). The check-in reads tables, not T10's script: part 3 shows `campaigns.active_lever*` as T10 writes them ("lever not set (no `pull insights` yet)" until it runs); part 5 quotes the latest loop run's `runs.counts.warnings` and `learnings_refused` (T10's shapes, both lists) and only judges the FR-41 zero-learnings case from `mart_creative_performance` itself when no loop ran in the window. The dry-run runs `scripts/meta_insights.py` for real; `me-monday` reports `monday_memo.py` as not built and continues.
- 2026-09-10 (T11 implementer): FR-47 brakes owed by T8's comment are in `scripts/checkin.py`: worker error-rate (`config.brakes.error_rate_threshold` 0.3 over `error_rate_window_hours` 1 with at least `error_rate_min_runs` 3, DECISIONS.md C9's open default) and lead velocity (`lead_velocity_multiplier` 3 × the median daily leads of the previous `lead_velocity_window_days` 7, baseline floored at `lead_velocity_min_baseline` 1 so a brand-new account still has a working brake). All six keys are DRAFT in `config/clients/upclicklabs.json`; a missing key is a warning in part 5, not a default. Each brake has a fixture in `tests/test_checkin.py`; proposals are idempotent (one open row per rule / worker) and show in part 1 marked "approve as sam_admin". An `applying` row suspends the brakes and is itself a warning; the email still goes out (SKILL.md §0 step 4 lists check-in among the modes that run under pause, and a stuck row must reach Sam).
- 2026-09-10 (T11 implementer): `warehouse.client.blocked_sources()` gained an optional `client_id` filter (the planner keeps the default); the check-in scopes its FR-8 warning to the client so the golden body is deterministic in a shared test database.
- 2026-09-10 (T11 implementer): recipient is `CHECKIN_TO` (env / `.env`; `--to` overrides), so no address is committed. An existing `.env` created before this ticket lacks it: the first dev-mode run failed cleanly naming the variable and the next check-in reported that failed run in part 5. `EMAIL_BACKEND=gmail` stays `not_built` until T13 step 7 (the Gmail connector is a session tool, not a Python client; T13 decides whether the routine session sends through the connector from the composed `.eml` or the adapter gets a Gmail API client).
- 2026-09-10 (T11 implementer): SessionStart hook replaces the two inline commands in `.claude/settings.json` (`matcher: startup|resume`, synchronous, 600 s timeout). Remote sessions only for deps / Chromium / dev DB; the plugin install runs everywhere. Validated in this container: exit 0, Chromium found under `/opt/pw-browsers`, `dev_db.sh` idempotent, a fake `META_ACCESS_TOKEN` never printed. Post-rebase counts: `tests/test_checkin.py` 12, `tests/test_pause.py` 2, `tests/test_routines.py` 5, `tests/test_session_hook.py` 3 (the full-hook test is skipped outside `CLAUDE_CODE_REMOTE=true`); full suite 230 passed on the local cluster.
- 2026-09-10 (T11 implementer) for T12: `SKILL.md` §3 rows for `check-in` and `pause` now name the scripts and flags; §8 points at `config/routines.json`, `scripts/routines.py`, and the hook. `monday_memo.py` is still not built (`me-monday` dry-run reports it). `decide.what_changes` now accepts `proposal.ad_sets` as a count as well as a list (a `build_campaign` row with a count crashed `decide.py list` and the check-in). For T13: `references/dev-mode.md` step 7 now includes setting `CHECKIN_TO` and registering the three routines from `scripts/routines.py list` with `create_trigger` (fresh session per fire, cron as `cron_utc`).

