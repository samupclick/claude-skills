# 01: Warehouse client (T1)

**What to build:** Any worker script can open a role-scoped connection from env, insert into every table in `schema.sql` through typed helpers, run the "where are we" query and the two read-before-planning queries, and wrap its work in a `runs` row that closes on success and on failure.

**Blocked by:** T0 (00)

**Blocks:** T2 (02), T3 (03), T4 (04), T7 (07), T8 (08)

**Status:** ready-for-agent

**Done:** no

**Stop point:** none

**FR ids:** FR-44, DR-1, DR-2, NFR-1, NFR-4

## Deliverable

`warehouse/client.py`: psycopg connection per role from env, insert helpers for every table in `schema.sql`, the "where are we" query from `SKILL.md` §2, the two read-before-planning queries from `SKILL.md` §4.2, a `runs` context manager. Plus (quiz decision 2): migration `warehouse/0003_phase0_grants.sql` granting worker_rw update on `creatives (status, asset_urls, sizes, version)`, `briefs (spec)`, `campaigns (active_lever, active_lever_reason, active_lever_since)`, applied after `0002` by the test fixture and by `scripts/dev_db.sh`.

## Acceptance

- [ ] Unit tests with a local Postgres fixture applying `0001` + `0002`; every helper round-trips; a worker role cannot update `actions` (FR-44)
- [ ] The `runs` context manager writes `status='ok'` with `counts` on normal exit and `status='failed'` with `error` when the body raises, in both cases with `finished_at` set
- [ ] The "where are we" query prints the §2 table for `upclicklabs` on a freshly seeded database
- [ ] `0003_phase0_grants.sql` applies cleanly after `0002`; as worker_rw, updating `creatives.status` and `campaigns.active_lever` succeeds while updating `actions` still raises; the migration is listed in `warehouse/schema-notes.md`

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

- Blocked by: T0 (00)
- Blocks: T2 (02), T3 (03), T4 (04), T7 (07), T8 (08)

## Notes for the implementer (dev mode)

The Postgres test fixture defined here (create a throwaway database, apply `0001` + `0002`, seed, drop) is reused by every later ticket. Sam approved (2026-09-04) closing the `0002` grant gaps with `warehouse/0003_phase0_grants.sql`; keep it to column grants, no new tables or columns. `dev_db.sh` (T0) applies every numbered migration in `warehouse/`, so `0003` is picked up without editing the script.

## Comments
