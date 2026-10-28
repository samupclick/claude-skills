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

- 2026-10-28 (integrator, phase 0 completion build on `claude/sleepy-brahmagupta-jng3kp`): everything this ticket's swap
  needs from code now exists; the swap itself still waits on Sam's credentials and accounts (Friday checklist,
  `SKILL.md` §11), so the status stays `needs-info`. Added by this build (merges `175592e`, `2a2cdfd`, `75f4a38`,
  `e675cbb`, `26ea37c`, `0aac34d`, then the integration commit; details in `CHANGELOG.md` § "Phase 0 completion"):
  - every live backend: `storage/supabase`, `meta/live` (write token in the executor only, `META_READ_TOKEN` for
    workers), `capi/live`, `turnstile/live`, `inspo/scrapecreators`, `voc/reddit`, `image/gemini`,
    `email/gmail_connector`. All contract-tested with `httpx.MockTransport` against ASSUMED-SHAPE fixtures; **none is
    live-verified**, and each swap step now ends by recording a real response over its fixture;
  - step 1 is `scripts/apply_migrations.py` (`--dry-run`, `--baseline`, `--storage-writer`, `--verify`), not a hand
    apply; migrations are `0001` to `0008` (`0008_loop_review_sync.sql`, the FR-37 review-sync grant);
  - step 6 deploys the funnel **from this repo** to Vercel (`api/funnel.py`, `vercel.json`, `funnel/README.md` §
    "Deploy on Vercel"), not to a separate `go-upclicklabs` repo; `scripts/test_events.py --live` checks it. The
    acceptance line naming the `go-upclicklabs` repo is superseded by that (Sam, 2026-10-28: keep the funnel here);
  - step 7 is `EMAIL_BACKEND=gmail_connector` (check-in and Monday memo queued, sent by the routine session's Gmail
    connector, `--send-pending` / `--mark-sent`), and the routines register from `scripts/routines.py register --print`;
  - one `META_API_VERSION` default (v26.0) for the Marketing API and CAPI (`adapters/graph.py`).
  The rewritten checklist is `references/dev-mode.md` § "Go-live swap checklist"; `.env.example` names every variable
  and the only process that may hold it. Open questions for Sam from the builders are in the build report (bucket
  privacy for inspo copies, Data API exposure, read token, custom conversions, Gemini model, Reddit app, function
  region, staging database for Preview, re-send path).
