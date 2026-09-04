# 00: Dev harness (T0)

**What to build:** A fresh session can run `scripts/dev_db.sh`, get a local Postgres with `0001` + `0002` applied and the five roles usable, load `.env`, and every external service the later tickets call (storage, Meta, CAPI, inspo, image, model, email, Turnstile) resolves to a working fake/local/fixture adapter chosen by its env var. Later tickets import adapters only, never a vendor SDK.

**Blocked by:** None (can start immediately)

**Blocks:** T1 (01)

**Status:** ready-for-agent

**Done:** no

**Stop point:** none

**FR ids:** FR-49, DR-1, NFR-1, NFR-4

## Deliverable

`scripts/dev_db.sh` (local Postgres, apply 0001 + 0002, create the five roles with dev passwords), the adapter interfaces and their fake/local/fixture implementations for storage, Meta, CAPI, inspo, image, model, email, Turnstile, plus `.env.example` loading and `fixtures/ad_library/` with an assumed-shape sample.

## Acceptance

- [ ] `scripts/dev_db.sh` is idempotent: from a stopped Postgres 16 cluster it starts the cluster, installs the `vector` extension (apt package `postgresql-16-pgvector` is available, not installed), creates database `gw`, applies `warehouse/schema.sql` then `warehouse/0002_roles.sql` with zero errors, and gives the five roles LOGIN with dev passwords matching `.env.example`; a second run changes nothing
- [ ] `scripts/dev_db.sh --verify` connects as each of the five roles and prints the role name and `select count(*) from families`
- [ ] `scripts/dev_db.sh --seed` inserts `families` from `references/families.md` and the `clients` (with `config` = the JSON file), `offers`, `icps` rows for `upclicklabs` from `config/clients/upclicklabs.json` using `WAREHOUSE_URL_ADMIN` (worker_rw has no insert on `clients`/`offers`/`icps`); re-running adds zero rows; placeholder values are copied as-is, never replaced with invented ones
- [ ] Each adapter (storage, meta, capi, inspo, image, model, email, turnstile) has one interface module, one dev implementation, and a factory that reads the env var named in `references/dev-mode.md`; an unknown value raises naming the variable; a unit test per adapter exercises the dev implementation (fake Meta: create → name lookup → read-back, synthesised insights, `META_FAKE_FAIL=<step>`; CAPI: `event_id` recorded to `.dev/capi.jsonl`; storage: `put(bytes, key) -> url` / `get(url)` round-trip under `.dev/storage/`; image: deterministic bytes per prompt hash; model: `fixture` replays `fixtures/model/*.json`; email: `.eml` in `.dev/outbox/`; turnstile: `pass`)
- [ ] `.env` loading: a helper loads `.env` from the `marketing-engineer/` directory, refuses to start a job when a variable that job needs is unset (names the variable), and never echoes a value; `.env` and `.dev/` are git-ignored
- [ ] `fixtures/ad_library/` holds at least one assumed-shape sample per DTC seed brand (5 brands, ≥5 ads each, with `start_date`, `is_active`, snapshot image fields) clearly marked as an assumed shape in a README
- [ ] `grep` for `facebook_business`, `google.generativeai`, `supabase`, `anthropic` imports outside the adapter package returns nothing (FR-49)

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

- Blocked by: None (can start immediately)
- Blocks: T1 (01)

## Notes for the implementer (dev mode)

Roles in `0002_roles.sql` are `nologin`; dev mode alters them to LOGIN with the passwords in `.env.example` (extend `.env.example` with the passwords if it lacks them; keep the connection strings as documented). Fake Meta must synthesise insights from a seed so T10 gets rows. Fixture-mode model adapter is for CI; `MODEL_BACKEND=claude` is the default per `.env.example`. Nothing here writes a `runs` row except `--seed`, which should (worker `seed`). `dev_db.sh` applies every numbered migration present in `warehouse/` in order (`schema.sql` is 0001), so later migrations are picked up without editing the script. Config numbers per quiz decision 1: `daily_cap` 45, `campaign.adset_daily_budget` 15 (DRAFT, changed at publish time).

## Comments
