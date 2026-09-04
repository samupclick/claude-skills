# 07: Quiz funnel (T7)

**What to build:** A prospect can open the quiz page, consent, pass Turnstile, answer the 3 configured questions, and land in `leads` + `lead_contacts` through the `app` role, with server-side CAPI `QuizStart`/`QuizComplete` deduplicated by `event_id`; a signed calendar webhook sets `booked_verified_at` and fires `Schedule`.

**Blocked by:** T1 (01)

**Blocks:** T9 (09)

**Status:** ready-for-agent

**Done:** no

**Stop point:** none

**FR ids:** FR-32, FR-33, FR-34, FR-35, DR-4

## Deliverable

Static quiz page: consent step before any pixel, Turnstile, 3 questions from `offers.quiz_config`, `utm_content`/`fbclid` capture; Supabase Edge Function `/quiz` (role `app`, RPC insert into `leads` + `lead_contacts`, server-side CAPI `QuizStart`/`QuizComplete` with `event_id` dedup, no event without consent); Edge Function `/cal-webhook` (signature-verified) setting `booked_verified_at` and firing `Schedule`; `scripts/test_events.py`

## Acceptance

- [ ] FR-32 to FR-35; Events Manager test tool green with dedup; forged webhook rejected and logged; a submission without consent writes no CAPI event
- [ ] FR-35: hard qualification is a config flag, default off; answers set `qualification_score` from `quiz_config.qualification`
- [ ] DR-4: PII lands only in `lead_contacts`; `fbclid` is stored hashed; the `app` role inserts through the RPC only

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
