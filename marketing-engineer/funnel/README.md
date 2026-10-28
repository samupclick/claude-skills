# Quiz funnel (T7)

The prospect-facing half of the pipeline: a static quiz page, the `/quiz` and `/cal-webhook` function
code, a local runner, and the Vercel packaging that serves both at `go.upclicklabs.com`. It stays in this
repo (Sam, 2026-10-28): Vercel deploys it with `marketing-engineer/` as the project root. Going live flips
`CAPI_BACKEND`, `TURNSTILE_BACKEND`, `FUNNEL_HOST` to their live values in the Vercel project, not in code.
Requirements: PRD FR-32 to FR-35, DR-4.

| File | Role |
|------|------|
| `static/index.html`, `quiz.js`, `quiz.css` | The page: consent → 3 questions (from `offers.quiz_config`) → contact → calendar link |
| `app.py` | Function code, framework-free (`handle(Request, Deps) -> Response`); routes below |
| `quiz.py` | Pure logic: body schemas, answer whitelist, scoring, event ids, hashing, webhook signature |
| `wsgi.py` | WSGI adapter over `handle()` for Vercel: role and environment guards, visitor IP, body limit |
| `server.py` | Local runner on `FUNNEL_HOST` (`http://localhost:8788`): static files + the routes, role `app` |
| `../api/funnel.py` | The Vercel function: the WSGI `app` the Python runtime loads |
| `../api/requirements.txt`, `../api/.python-version` | The function's own dependencies (four packages, pinned) and Python 3.13 |
| `../vercel.json` | Routes the four function paths to `api/funnel.py`, serves `funnel/static/` as the site |
| `../.vercelignore` | Uploads only the function's imports and the page: never `.env`, fixtures, tests, scripts |
| `../warehouse/0004_quiz_rpc.sql` | `quiz_start`, `quiz_complete`, `lead_booked`, `quiz_config` — the only way `app` touches `leads` |
| `../scripts/test_events.py` | Events Manager test tool: three events once each, none without consent, forged webhook rejected; `--live` sends them to Meta's Test events tab |

## Routes

| Route | Does | Warehouse | CAPI |
|-------|------|-----------|------|
| `GET /quiz/config?client=` | questions, notice version, pixel / Turnstile keys, `capi_test_mode` | `quiz_config()` | — |
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
- **A CAPI failure never costs the lead.** The RPC has committed before the event is sent, so a refused or
  unreachable Conversions API is one `capi_failed` log line (event name, event id, Meta's code and fbtrace_id)
  and the route still answers 200 with the `event_id` for the pixel. The live adapter retries transient
  errors itself (safe: Meta keeps the first copy per event id); there is no replay queue in phase 0.
- **One Turnstile token per POST.** Tokens are single-use (siteverify answers `timeout-or-duplicate` on a
  second check), so `/quiz/start` and `/quiz` each have their own widget and a failed POST resets its widget.
- **PII only in `lead_contacts`.** `leads` carries answers (option strings only), score, consent, and
  `fbclid_hash` (sha256; the raw click id is used in-flight as CAPI `fbc` and never stored). Logs carry lead ids,
  never emails. The live CAPI adapter refuses to send a customer-information field that is not sha256 hex.
- **`booked_verified_at` only from the verified webhook.** A missing or wrong signature is a 401 and a
  `cal_webhook_rejected` log line; nothing is written.
- **Attribution**: `utm_content = creative_id` (FR-32) resolves `leads.creative_id` and the matching
  `ad_entity_id` inside `quiz_start`. The booking link carries `?metadata[lead_id]=<uuid>` so Cal.com
  returns it in `payload.metadata`.
- **Qualification** (FR-35): `qualification_score` = sum of `quiz_config.qualification[q][answer]`.
  Soft by default: every completer gets the calendar. `quiz_config.qualification_mode = "hard"` with
  `qualification_threshold` withholds the calendar below the threshold (config flag, default off).
- **Role `app` only.** The function reads `WAREHOUSE_URL_APP` and nothing else from the warehouse side; its
  first connection must log in as `app` (not a superuser, not BYPASSRLS) or it answers 503. It also refuses to
  serve while another job's credentials are in its environment (below).

## Run it

```
scripts/dev_db.sh && scripts/dev_db.sh --seed     # once
python3 funnel/server.py                          # http://localhost:8788/quiz?utm_content=<creative_id>&fbclid=…
python3 scripts/test_events.py                    # starts a runner itself if nothing answers on FUNNEL_HOST
```

`scripts/test_events.py --live` sends the same three events to Meta through `CAPI_BACKEND=live` and refuses to run
without `META_TEST_EVENT_CODE`. With nothing listening on `FUNNEL_HOST` it runs the funnel in-process on the live
backend (needs `META_PIXEL_ID`, `META_CAPI_TOKEN`) and requires Meta to acknowledge each event once; pointed at a
deployed preview (`--no-serve`) it first checks that preview's `capi_test_mode` and prints what Events Manager →
Test events must show. Without `--live` the script refuses `CAPI_BACKEND=live`.

## Deploy on Vercel (Sam)

Nothing here has been deployed or checked against a live Vercel, Meta or Cloudflare account; the packaging is
tested by invoking the function the way Vercel's Python runtime (vercel-runtime 0.24.1) does.

1. **Project.** Vercel → Add New → Project → import this GitHub repo. **Root Directory: `marketing-engineer`**
   (the function imports `adapters/` and `warehouse/`, and Vercel cannot read files outside the root). Framework
   Preset: Other; leave Build Command and Output Directory empty (`vercel.json` sets `framework: null` and
   `outputDirectory: funnel/static`). The function installs `api/requirements.txt` on Python 3.13, not the
   top-level `requirements.txt`.
2. **Function region.** Settings → Functions → Region: the region of the Supabase EU project (each request makes
   several round trips to the warehouse).
3. **Environment variables** (Settings → Environment Variables; mark the secrets Sensitive):

   | Variable | Production | Preview | Notes |
   |----------|------------|---------|-------|
   | `WAREHOUSE_URL_APP` | Supabase pooler string for role `app` | same, or a staging database | the only warehouse variable the function may hold |
   | `CAPI_BACKEND` | `live` | `live` | the function refuses any other value on Vercel |
   | `TURNSTILE_BACKEND` | `live` | `live` | likewise |
   | `META_PIXEL_ID` | the pixel (dataset) id | same | also shown to the page for the browser pixel |
   | `META_CAPI_TOKEN` | Events Manager → Settings → Conversions API → access token | same | secret |
   | `META_TEST_EVENT_CODE` | **unset** | Events Manager → Test events code | set in Production it marks every real event as a test event (the function logs `capi_test_mode_in_production`) |
   | `META_API_VERSION` | optional (default `v26.0`, shared with the Marketing API adapter) | same | |
   | `TURNSTILE_SITE_KEY` | the widget's site key | `1x00000000000000000000AA` (Cloudflare's always-pass test key) | public |
   | `TURNSTILE_SECRET_KEY` | the widget's secret key | `1x0000000000000000000000000000000AA` (test secret) | secret in Production |
   | `TURNSTILE_EXPECTED_HOSTNAME` | `go.upclicklabs.com` | unset | optional; siteverify's `hostname` must match |
   | `CAL_WEBHOOK_SECRET` | the Cal.com webhook secret | a separate value | secret |
   | `FUNNEL_HOST` | `https://go.upclicklabs.com` | `https://go.upclicklabs.com` | becomes CAPI's `event_source_url`; keep it on the verified domain |
   | `RATE_LIMIT_PER_MINUTE` | `20` | `20` | per function instance, not global |

   Never add `WAREHOUSE_URL_WORKER`, `_EXECUTOR`, `_SAM_ADMIN`, `_ADMIN`, `_MCP_RO`, `META_ACCESS_TOKEN` or
   `META_READ_TOKEN` to this project: the function answers 503 while any of them is set (SKILL.md §1).
4. **Domain.** Settings → Domains → add `go.upclicklabs.com` to Production; at the DNS provider add a `CNAME`
   record `go` → the project-specific value Vercel shows; the certificate is issued once it resolves. Verify
   the domain in Meta Business Settings (Friday checklist item 2).
5. **Cal.com.** Webhook subscriber URL `https://go.upclicklabs.com/cal-webhook`, trigger Booking Created, secret =
   Production `CAL_WEBHOOK_SECRET`. Booking link in `offers.calendar_url`.
6. **Test on a preview.** Push a branch; Vercel builds a Preview. Preview URLs sit behind Deployment Protection, so
   create a secret under Settings → Deployment Protection → Protection Bypass for Automation. Then, from a shell
   with the dev warehouse for the `runs` row:
   ```
   FUNNEL_HOST=https://<preview-url> CAL_WEBHOOK_SECRET=<preview secret> META_TEST_EVENT_CODE=<code> \
   VERCEL_AUTOMATION_BYPASS_SECRET=<bypass secret> python3 scripts/test_events.py --live --no-serve
   ```
   and watch Events Manager → Test events: QuizStart, QuizComplete, Schedule once each from Server. The test
   leads land in the preview's warehouse.
7. **Go live.** Merge to the production branch; open `https://go.upclicklabs.com/quiz` and walk it once with
   tracking allowed; the events appear in Events Manager's Overview (not Test events). Function logs (one JSON
   line per event: `quiz_start`, `capi_sent`, `capi_failed`, `turnstile_rejected`, `function_misconfigured`, …)
   are under the project's Logs.
