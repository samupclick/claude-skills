# 13: Go-live swap (T13)

**What to build:** After Sam clears the Friday checklist (`CRUCIBLE.md` §4), the eight steps of the go-live swap checklist in `references/dev-mode.md` are executed, one env var per service, with no code change; then `launch` → stop point C → `apply actions` against the real account.

**Blocked by:** T12 (12) and Sam's clearance of the Friday checklist

**Blocks:** —

**Status:** needs-info

**Done:** no

**Stop point:** C — T9 proposes `build_campaign`, and later `activate`: print the proposal summary (campaign, ad sets, budgets, cap check result); wait for `approve n`; then run `apply actions`.

Default if Sam goes quiet for 20 minutes: do nothing. Say which default was taken.

**FR ids:** NFR-3, NFR-7, DR-1 (on Supabase)

## Deliverable

Execution of `references/dev-mode.md` § "Go-live swap checklist" steps 1–8: `0001` + `0002` on Supabase EU and `dev_db.sh --verify` against it; `STORAGE_BACKEND=supabase` with `render_creatives.py --reupload`; placeholder files replaced and `pull_voc.py` / `plan_batch.py` re-run; one real scrapecreators call saved to `fixtures/ad_library/real-001.json` and `INSPO_BACKEND=scrapecreators`; `IMAGE_BACKEND=gemini`; `META_BACKEND=live`, `CAPI_BACKEND=live`, `FUNNEL_HOST=https://go.upclicklabs.com`, quiz app deployed, `test_events.py` green; `EMAIL_BACKEND=gmail` with one check-in sent; then `launch`.

## Acceptance

- [ ] Steps 1–7 change no code; any code change found is filed back to the ticket owning that adapter (a bug in the adapter boundary)
- [ ] `scripts/dev_db.sh --verify` passes against Supabase as each role; `select count(*) from families` ≥ 15
- [ ] `test_events.py` green in the Events Manager test tool for `QuizStart`, `QuizComplete`, `Schedule` with dedup
- [ ] Objects created in the real Ads Manager are paused until the `activate` approval at stop point C; `check_daily_cap()` true after activation
- [ ] The funnel is deployed from `marketing-engineer/funnel/` to the `go-upclicklabs` repo on Vercel (quiz decision 4) and the three routines from `SKILL.md` §8 are registered (quiz decision 7)

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

- Blocked by: T12 (12) and Sam's clearance of the Friday checklist
- Blocks: —

## Notes for the implementer (dev mode)

STAYS BLOCKED until Sam clears it. Requires real credentials in the executor's env only; never in a worker, never in git. Status is `needs-info` (waiting on Sam), not `ready-for-agent`.

## Comments
