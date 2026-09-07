# 07: Quiz funnel (T7)

**What to build:** A prospect can open the quiz page, consent, pass Turnstile, answer the 3 configured questions, and land in `leads` + `lead_contacts` through the `app` role, with server-side CAPI `QuizStart`/`QuizComplete` deduplicated by `event_id`; a signed calendar webhook sets `booked_verified_at` and fires `Schedule`.

**Blocked by:** T1 (01)

**Blocks:** T9 (09)

**Status:** ready-for-agent

**Done:** yes — 2de3aa1

**Stop point:** none

**FR ids:** FR-32, FR-33, FR-34, FR-35, DR-4

## Deliverable

Static quiz page: consent step before any pixel, Turnstile, 3 questions from `offers.quiz_config`, `utm_content`/`fbclid` capture; Supabase Edge Function `/quiz` (role `app`, RPC insert into `leads` + `lead_contacts`, server-side CAPI `QuizStart`/`QuizComplete` with `event_id` dedup, no event without consent); Edge Function `/cal-webhook` (signature-verified) setting `booked_verified_at` and firing `Schedule`; `scripts/test_events.py`

## Acceptance

- [x] FR-32 to FR-35; Events Manager test tool green with dedup; forged webhook rejected and logged; a submission without consent writes no CAPI event
- [x] FR-35: hard qualification is a config flag, default off; answers set `qualification_score` from `quiz_config.qualification`
- [x] DR-4: PII lands only in `lead_contacts`; `fbclid` is stored hashed; the `app` role inserts through the RPC only

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

Separate repo `go-upclicklabs` (Vercel) per the kickoff; in dev mode `FUNNEL_HOST=http://localhost:8788` with a local static server and local Edge Function emulation, `CAPI_BACKEND=fake` (`.dev/capi.jsonl` stands in for the Events Manager test tool; "green with dedup" = each `event_id` appears once), `TURNSTILE_BACKEND=pass`, `CAL_WEBHOOK_SECRET=dev-secret`. Quiz decision 4 (Sam, 2026-09-04): the funnel code lives in this repo under `marketing-engineer/funnel/` during phase 0 (static page, `/quiz` and `/cal-webhook` function code, local runner on port 8788); moving it to the `go-upclicklabs` repo and deploying to Vercel is T13's step 6. The RPC function and the `app` grants it needs are a numbered migration (`0004_quiz_rpc.sql`).

## Comments

- 2026-09-07 (implementer): shipped in commit 2de3aa1. `funnel/` (static page, `app.py` routes, `server.py` runner on 8788, README with T13 porting notes), `warehouse/0004_quiz_rpc.sql` (`quiz_start`, `quiz_complete`, `lead_booked`, `quiz_config` as SECURITY DEFINER, execute for `app`, 0002's direct inserts on `leads`/`lead_contacts` revoked from `app` so "RPC only" is enforced by Postgres), `scripts/test_events.py`, `tests/test_funnel.py` (16 tests incl. a headless Chromium walk of the page via the globally installed node playwright; skipped where node playwright is absent). Full suite: 75 passed on the real local cluster. `scripts/test_events.py` on the seeded dev database: green (three events once each for the consenting prospect, zero for the declining one, forged and unsigned webhooks 401 + `cal_webhook_rejected` log lines, webhook retry a no-op).
- 2026-09-07 (implementer): while proving DR-4 the test found that 0002's `revoke select (quiz_answers, consent, fbclid_hash) on leads from mcp_ro` never took effect: Postgres ignores a column revoke while the table-level `select` stands, so `mcp_ro` could read consent and answers. Fixed by `warehouse/0005_mcp_ro_leads_columns.sql` (table grant replaced by a column list without the three; no other role changes). Listed in `schema-notes.md`; `dev_db.sh` and the test fixture picked it up without edits.
- 2026-09-07 (implementer): flow and ids. `/quiz/start` creates the `leads` row in stage `new` once the consent screen is passed (starters exist as rows, so `mart_funnel`'s quiz-start / quiz-complete rates work); `/quiz` moves it to `completed`, writes answers + score to `leads` and name/email/phone to `lead_contacts`; the signed Cal.com webhook moves it to `booked` and sets `booked_verified_at`. `event_id` is `<lead_id>:QuizStart|QuizComplete|Schedule`, shared by the pixel and the server; the RPCs return whether the transition happened so a retry never re-sends. The booking link carries `?metadata[lead_id]=<uuid>`; Cal.com returns it in `payload.metadata`, which is how the webhook finds the lead (no email matching, so `app` never reads `lead_contacts`).
- 2026-09-07 (implementer): consent semantics. `consent.tracking=false` still stores the lead (the call needs the contact) but fires no CAPI event, ever, for that lead; the page loads no pixel before Start and none at all without tracking consent or a pixel id. Turnstile's script is the one third-party request before Start when `TURNSTILE_SITE_KEY` is set (unset in dev); it is a security control, not tracking.
- 2026-09-07 (implementer): DRAFT config effects to note for Sam. `offer.calendar_url` is a PLACEHOLDER (not a URL), so the result screen shows no booking button until it is replaced; the qualification table scores q1 and q3 only (q2 is unscored); `qualification_mode` is absent, so hard mode is off (FR-35). `META_PIXEL_ID`, `TURNSTILE_SITE_KEY`, `META_CAPI_TOKEN`, `META_TEST_EVENT_CODE` are unset in dev; `CAPI_BACKEND=live` and `TURNSTILE_BACKEND=live` are T13. The `app` role's `WAREHOUSE_URL_APP` is the funnel's only warehouse identity.
- 2026-09-07 (implementer): for T9 (launcher): ad URLs are `FUNNEL_HOST/quiz?utm_source=facebook&utm_medium=paid&utm_campaign=<campaign>&utm_content=<creative_id>`; `quiz_start` resolves `creative_id` and the ACTIVE `ad_entity_id` from `utm_content` when it names one of the client's creatives (test `test_utm_content_resolves_creative_and_ad_entity`). T9 is unblocked from T7's side (still needs T6 and T8).
