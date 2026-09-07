# Quiz funnel (T7)

The prospect-facing half of the pipeline: a static quiz page, the `/quiz` and `/cal-webhook` function
code, and a local runner. Built in dev mode under this directory (quiz decision 4, Sam 2026-09-04);
T13 step 6 moves it to the `go-upclicklabs` repo on Vercel and flips `CAPI_BACKEND`, `TURNSTILE_BACKEND`,
`FUNNEL_HOST` to their live values. Requirements: PRD FR-32 to FR-35, DR-4.

| File | Role |
|------|------|
| `static/index.html`, `quiz.js`, `quiz.css` | The page: consent → 3 questions (from `offers.quiz_config`) → contact → calendar link |
| `app.py` | Function code, framework-free (`handle(Request, Deps) -> Response`); routes below |
| `quiz.py` | Pure logic: body schemas, answer whitelist, scoring, event ids, hashing, webhook signature |
| `server.py` | Local runner on `FUNNEL_HOST` (`http://localhost:8788`): static files + the routes, role `app` |
| `../warehouse/0004_quiz_rpc.sql` | `quiz_start`, `quiz_complete`, `lead_booked`, `quiz_config` — the only way `app` touches `leads` |
| `../scripts/test_events.py` | Events Manager test tool stand-in: three events once each, none without consent, forged webhook rejected |

## Routes

| Route | Does | Warehouse | CAPI |
|-------|------|-----------|------|
| `GET /quiz/config?client=` | questions, notice version, pixel / Turnstile keys | `quiz_config()` | — |
| `POST /quiz/start` | consent passed; captures `utm_*` and hashed `fbclid` | `quiz_start()` → `leads` (stage `new`) | `QuizStart` if `consent.tracking` |
| `POST /quiz` | answers (whitelisted against the config) + contact | `quiz_complete()` → `leads` + `lead_contacts` | `QuizComplete`, once per lead |
| `POST /cal-webhook` | Cal.com `BOOKING_CREATED`, HMAC-SHA256 of the raw body in `X-Cal-Signature-256` | `lead_booked()` → `booked_verified_at`, stage `booked` | `Schedule`, once per lead |

Every POST is Turnstile-checked and rate-limited per IP (`RATE_LIMIT_PER_MINUTE`, default 20; enforced
in `TURNSTILE_BACKEND=pass` too). Disposable email domains are rejected. Bodies over 16 KB are refused.

## Invariants

- **Consent first.** The page loads no pixel and sends nothing before "Start". The server fires CAPI only
  when `consent.tracking` is true, and re-checks it from the lead row on complete and on booking.
- **One `event_id` per (lead, event)**: `<lead_id>:QuizStart|QuizComplete|Schedule`. The pixel (when
  consented) and the server share it, so Meta deduplicates; the RPCs return whether the transition
  happened so a retry never re-sends.
- **PII only in `lead_contacts`.** `leads` carries answers (option strings only), score, consent, and
  `fbclid_hash` (sha256; the raw click id is used in-flight as CAPI `fbc` and never stored). Logs carry lead ids, never emails.
- **`booked_verified_at` only from the verified webhook.** A missing or wrong signature is a 401 and a
  `cal_webhook_rejected` log line; nothing is written.
- **Attribution**: `utm_content = creative_id` (FR-32) resolves `leads.creative_id` and the matching
  `ad_entity_id` inside `quiz_start`. The booking link carries `?metadata[lead_id]=<uuid>` so Cal.com
  returns it in `payload.metadata`.
- **Qualification** (FR-35): `qualification_score` = sum of `quiz_config.qualification[q][answer]`.
  Soft by default: every completer gets the calendar. `quiz_config.qualification_mode = "hard"` with
  `qualification_threshold` withholds the calendar below the threshold (config flag, default off).

## Run it

```
scripts/dev_db.sh && scripts/dev_db.sh --seed     # once
python3 funnel/server.py                          # http://localhost:8788/quiz?utm_content=<creative_id>&fbclid=…
python3 scripts/test_events.py                    # starts a runner itself if nothing answers on FUNNEL_HOST
```

## Porting notes for T13

`app.py` has no framework dependency: each route is a function of a `Request` (method, path, query,
headers, body, ip) returning a `Response` (status, JSON). On Vercel, wrap `handle()` in the Python
runtime's handler, or port route-by-route to a Supabase Edge Function keeping the RPC calls, the
event-id scheme, and the consent checks identical. Secrets stay with the functions: `META_CAPI_TOKEN`,
`META_TEST_EVENT_CODE`, `CAL_WEBHOOK_SECRET`, `WAREHOUSE_URL_APP` (SKILL.md §1).
