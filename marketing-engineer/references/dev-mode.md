# Dev mode — building before the Friday checklist is done

Every external dependency sits behind an adapter selected by an environment variable. Phase 0 is built and tested entirely in dev mode; going live is one variable change per service plus the real credentials. The code paths, schema, and tests are identical in both modes.

| Service | Env var | Dev value | Live value | What the fake does |
|---------|---------|-----------|------------|--------------------|
| Warehouse | `WAREHOUSE_URL_WORKER` / `_EXECUTOR` / `_SAM_ADMIN` / `_APP` / `_MCP_RO` (`_ADMIN` is the dev superuser; at go-live Supabase's `postgres` string in Sam's shell for `scripts/apply_migrations.py`) | local Postgres (`postgresql://…@localhost:5432/gw` per role) | Supabase EU session-pooler strings (port 5432, `sslmode=require`) | Nothing to fake; same schema (`0001` to `0008`) applied locally by `scripts/dev_db.sh`, remotely by `scripts/apply_migrations.py` |
| Object storage | `STORAGE_BACKEND` | `local` (writes under `.dev/storage/`, returns `file://` URLs) | `supabase` (built: public bucket URLs `<SUPABASE_URL>/storage/v1/object/public/<bucket>/<key>`; writes as a dedicated Supabase Auth user under an RLS policy, never the service role) | Same interface: `put(bytes, key) -> url`, `get(url)` |
| Meta Marketing API | `META_BACKEND` | `fake` | `live` (built: Graph API `META_API_VERSION`, default v26.0; write mode on `META_ACCESS_TOKEN` in `scripts/apply_actions.py` only, read mode on `META_READ_TOKEN` for workers) | In-memory account: creates campaigns/ad sets/ads with ids, name lookup, `effective_status`, `ad_review_feedback`, insights that synthesise impressions/clicks from a seed, throttle header simulation, failure injection via `META_FAKE_FAIL=<step>` |
| Meta CAPI | `CAPI_BACKEND` | `fake` (logs events to `.dev/capi.jsonl`) | `live` (built; on Vercel the funnel function refuses any other value) | Records `event_id` for dedup tests |
| Ad Library | `INSPO_BACKEND` | `fixture` (reads `fixtures/ad_library/*.json`) | `apify` (Sam's choice, 2026-10-31: Apify's own actor `apify/facebook-ads-scraper` runs on the brand's page from `clients.config.inspo.pages`, capped in ads and dollars; shape seen in real runs on 2026-10-31, `fixtures/apify/README.md`) or `scrapecreators` (built: search companies → pageId → company ads by cursor) | Fixture shape is an **assumption** until one real call per endpoint is saved to `fixtures/scrapecreators/`; the shape functions at the top of `adapters/inspo/scrapecreators.py` normalise both backends |
| Public VOC threads (Reddit) | `VOC_BACKEND` | `fixture` (reads `fixtures/voc/*.json`, matched to `voc.public_sources` by URL) | `reddit` (built: app-only OAuth with `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`, else anonymous `.json`) | Fixture threads are **synthetic**; the shape is ours (`url`, `title`, `comments[{id,text,score}]`, no authors) and the live backend normalises Reddit's JSON into it |
| Image generation | `IMAGE_BACKEND` | `placeholder` (Pillow: solid colour + a small hash label) | `gemini` (built: `IMAGE_MODEL`, default `gemini-nano-banana-2.1`, recorded as `creatives.image_model`) | Deterministic bytes per prompt hash so renders are reproducible; the label is the adapter's dev marker, so the FR-24 vision check runs on the `image_text_check` fixture ("no text") in dev mode |
| Vision decomposition, copy, gate, planner reasoning | `MODEL_BACKEND` | `claude` (real; cheap) or `fixture` for CI | `claude` | Fixture mode replays recorded JSON outputs from `fixtures/model/` |
| Email (check-in, Monday memo) | `EMAIL_BACKEND` | `file` (writes `.dev/outbox/*.eml`) | `gmail_connector` (`gmail` is an alias): queues the message under `EMAIL_QUEUE_DIR`; the routine session sends it through its Gmail connector | Golden-file tests read the outbox |
| Calendar webhook | `CAL_WEBHOOK_SECRET` | `dev-secret` | real secret | Signature check identical; tests sign with the dev secret |
| Quiz page host | `FUNNEL_HOST` | `http://localhost:8788` | `https://go.upclicklabs.com`: the Vercel project deployed from this repo (`api/funnel.py`, `vercel.json`, Root Directory `marketing-engineer`; `funnel/README.md` § "Deploy on Vercel") | Local static server + the same WSGI app (`funnel/server.py`) |
| Turnstile | `TURNSTILE_BACKEND` | `pass` | `live` (built: Cloudflare siteverify with `TURNSTILE_SECRET_KEY`) | Always passes; rate limits still enforced |

Every live backend above is built and contract-tested with `httpx.MockTransport` against fixtures marked
**ASSUMED SHAPE** (`fixtures/supabase`, `meta`, `capi`, `turnstile`, `scrapecreators`, `reddit`, `gemini`,
`gmail_connector`), taken from the vendors' docs or the connector's tool schema on 2026-10-28. None has been called
with a real credential: each go-live step below replaces its fixture with a recorded response.

## Running locally (T0 dev harness)

```
pip install -r requirements.txt          # the SessionStart hook does this in remote sessions
scripts/dev_db.sh                        # start Postgres 16, pgvector, db gw, migrations, roles LOGIN; writes .env from .env.example
scripts/dev_db.sh --verify               # the five roles connect as themselves (scripts/apply_migrations.py --verify;
                                         # local or remote URLs; starts the local cluster only when all five are localhost)
scripts/dev_db.sh --seed                 # families + upclicklabs client/offer/icp from the DRAFT files, as-is
python3 -m pytest                        # tests run against the local warehouse, never a mock
```

macOS (Sam's Mac, no sudo): `brew install python@3.13 postgresql@16`, then at the **repo root** (a venv inside
`marketing-engineer/` trips the tests that scan its source tree)
`/opt/homebrew/opt/python@3.13/bin/python3.13 -m venv .venv && . .venv/bin/activate`,
`pip install -r marketing-engineer/requirements.txt` and `python3 -m playwright install chromium` (leave `CHROMIUM_PATH`
unset). `scripts/dev_db.sh` then takes its macOS path: it builds pgvector into the `postgresql@16` keg from Homebrew's
source tarball (the bottle targets 17/18 only), starts the cluster with `pg_ctl` (no launchd service), creates the
`postgres` superuser role, moves Homebrew's `trust` TCP lines in `pg_hba.conf` to `scram-sha-256` so a wrong role
password fails as on Debian and Supabase, and turns on TLS with a self-signed certificate (Debian's snakeoil
equivalent) so `sslmode=require` URLs connect.

Live credentials on the Mac come from the login keychain, never `.env`: `source scripts/env_from_keychain.sh [VAR ...]`
exports the named variables (all mapped ones by default) and prints names only. The Meta write token loads only with
`--with-meta-write`, in a subshell around `scripts/apply_actions.py`. The script's header has the mapping and the
`security add-generic-password -s marketing-engineer -a <VAR> -w` line for adding a missing credential.

`.env` is git-ignored and holds the dev passwords inside the `WAREHOUSE_URL_*` strings. Dev backends keep
their state under `DEV_ROOT` (default `.dev/`, git-ignored): `storage/`, `meta/account.json`,
`capi.jsonl`, `outbox/*.eml`. Workers get a backend with `from adapters.meta import get_meta` (likewise
`storage`, `capi`, `inspo`, `voc`, `image`, `model`, `email`, `turnstile`); an unknown env value raises naming the
variable. `adapters.env.require(job, *names)` refuses to start a job whose
variables are unset and never prints a value. Fake Meta knobs: `META_FAKE_SEED`, `META_FAKE_FAIL=<step>[:after]`
(`:after` performs the step, persists it, then fails, for orphan tests), `META_FAKE_THROTTLE_AFTER=<n>`.
The model adapter takes untrusted text through `untrusted=` only and wraps it in a delimited data block; `images=`
attaches PNG/JPEG bytes for vision tasks (the fixture backend ignores them). Fixture ad library knob:
`INSPO_FIXTURE_FAIL=<brand-slug>[,…]` makes those sources fail on every attempt (FR-8 tests).

`pull inspo` in dev mode: `python3 scripts/pull_inspo.py` (add `MODEL_BACKEND=fixture` when there is no
`ANTHROPIC_API_KEY`; `fixtures/model/decompose_ad.json` is a synthetic decomposition aligned to the fixture ads).
Images land under `.dev/storage/inspo/<brand>/<ad_id>/`. `--today YYYY-MM-DD` fixes the FR-6 reference date;
`--acknowledge <source>` is Sam's `acknowledge <source>` (SKILL.md §7).

`plan batch` in dev mode: `python3 scripts/plan_batch.py` (again `MODEL_BACKEND=fixture` without a key;
`fixtures/model/translate_brief.json` holds twelve synthetic translations) after `pull inspo` and `pull voc`; it
prints the §5.1 table (a `template` column; `NONE` means `produce` refuses that family) and stops. `--select "2, 5, 9"`
records Sam's picks, `--select default` the ranker's top three whose family has a weekend template. Plain `plan batch`
first re-translates every brief the producer marked after a coherence failure (FR-29 planner route);
`--retranslate` does only that (`fixtures/model/retranslate_brief.json`).
`--daily-budget` and `--cpm` override the capacity inputs for the FR-15 check; `--today` fixes the 7-day CPM window.

`produce` in dev mode: `python3 scripts/render_creatives.py` (`MODEL_BACKEND=fixture` without a key; `fixtures/model/write_copy.json`
holds three synthetic copy outputs, `image_text_check.json` the vision check) after `my picks`; it renders two creatives per
chosen brief through `assets/creative-templates/<family>.html` (`job-photo-bubble`, `screenshot-ad`; a pick in another family
is refused naming the family) with Playwright and writes them under `.dev/storage/creatives/<client>/<batch>/<creative id>/`.
Playwright needs a Chromium: its own download, or the container's `/opt/pw-browsers/chromium` (used when the download is
absent), or `CHROMIUM_PATH=<binary>`. Every `produce` also retries the recipes' gate-failed creatives (FR-29): a
producer-routed failure gets its next version through task `revise_copy` (`fixtures/model/revise_copy.json`) with the
failed checks' names as the constraint, a coherence failure waits for `plan batch --retranslate`, a failure at version 3
is dropped. `--rerender` archives a brief's creatives and writes the next version; `--reupload` is go-live step 2.

`gate` in dev mode: `python3 scripts/gate.py` (`MODEL_BACKEND=fixture`; `fixtures/model/gate_checks.json`, `gate_vision.json`,
`gate_rubric.json` are clean / shadow answers) after `produce`; it writes one agent `gate_scores` row per draft creative
(hard checks + shadow rubric), prints the §5.2 table and stops for `verdicts: approve 1,3; reject 2: reason`
(`--verdicts "…"`; `--verdicts default` ships nothing). `components`, `landing`, `verbatim` and the rule-based part of
`brand` are computed from the warehouse and the rendered HTML, so they fail for real in dev mode; the model-judged
checks (policy, likeness, coherence, fabricated testimonial) only fail with a recorded or hand-written fixture.
`--rescore` scores gated creatives again (same attempt).

`launch` in dev mode: `python3 scripts/meta_launch.py` after `verdicts: approve …` (T6). It proposes one
`build_campaign` per experiment with approved, unlaunched creatives and prints the stop-point C summary (campaign,
ad sets, budgets, ads, cap check); `python3 scripts/decide.py "approve n"` then `python3 scripts/apply_actions.py`
creates the objects paused in the fake account (`.dev/meta/account.json`, "Ads Manager" in dev mode). A second
`launch` then proposes the cascade `activate` for the built campaign; approve and apply again and the ads deliver
(the fake synthesises insights from the next day on). `META_FAKE_FAIL=create_ad:after` is the crash-mid-build
fixture; `FakeMeta.update("ad", id, review_status="DISAPPROVED", ad_review_feedback={...})` plays Meta's review
turning an ad down (FR-37): the next `activate` syncs it to `ad_entities.review_status` and refuses.

`pull insights` in dev mode: `python3 scripts/meta_insights.py [--today YYYY-MM-DD] [--days 7]` after `activate` was
applied. The fake account synthesises one insights row per (ad, day) from `META_FAKE_SEED` for days the ad, its ad set
and its campaign were all ACTIVE, so the first pull after activation carries today only and numbers stay well below
sample size (the view says `hold`, no agent learning is written). `--today` sets `fetched_on` and the window end: a
second pull under another seed on a later `--today` is the FR-38 restatement (two rows, one latest). Stop point D:
`python3 scripts/meta_insights.py --learning "<Sam's hypothesis>"` writes the hand-written proposed learning.

`check-in` in dev mode: `python3 scripts/checkin.py` (recipient `CHECKIN_TO` from `.env`, default `sam@example.invalid`;
`--to` overrides) writes the five-part email to `.dev/outbox/*.eml` through `EMAIL_BACKEND=file`; `--dry-run` prints it
instead; `--since 24h|ISO` and `--now ISO` fix the window. The golden body is `fixtures/checkin/golden-body.txt`
(`CHECKIN_GOLDEN_WRITE=1 python3 -m pytest tests/test_checkin.py -k golden` regenerates it after a deliberate change).
With `EMAIL_BACKEND=gmail_connector` (the go-live value) the check-in is queued once per client and UTC day as
`checkin-<slug>-<day>` under `EMAIL_QUEUE_DIR` (default `DEV_ROOT/pending-send`); `python3 scripts/checkin.py
--send-pending` prints the exact `send_message` arguments for the session's Gmail connector, the session calls the tool,
and `python3 scripts/checkin.py --mark-sent <key> --message-id <id>` records the delivery and removes the file. The
Monday memo is queued and delivered the same way under `memo-<slug>-<day>`.

`monday memo` in dev mode: `python3 scripts/monday_memo.py [--dry-run] [--since 7d|ISO] [--now ISO]` composes the
five-section memo and sends it through the email adapter to `CHECKIN_TO`; the golden body is
`fixtures/monday/golden-body.txt` (`MEMO_GOLDEN_WRITE=1 python3 -m pytest tests/test_monday_memo.py -k golden`
regenerates it).
`pause the pipeline`: `python3 scripts/pause.py pause --reason "…"` proposes `set_pause_flag`; approve with
`scripts/decide.py --as sam_admin "approve N"` and apply with `scripts/apply_actions.py --role sam_admin`
(`WAREHOUSE_URL_SAM_ADMIN` is in `.env` in dev mode); `resume` and `status` likewise. Routines: `python3 scripts/routines.py
dry-run me-morning` runs the 08:00 prompt's steps as scripts against the dev warehouse (`me-monday` runs status, the memo
and the send step; `me-executor` runs `apply_actions.py --reconcile` alone, and every other routine runs with the
executor-only variables blanked); `python3 scripts/routines.py register --print` prints the `create_trigger` arguments per routine
(UTC cron, fresh session, connectors `["Gmail"]` only for the routines that send email, the `environment_id` of the
routine's environment to fill in) and registers nothing. The
SessionStart hook (`.claude/hooks/session-start.sh`) does `pip install`, checks Chromium, creates `.env`, reports every
live-backend variable and live selector by name only (`session-start.sh --report-env` prints that report alone), runs
`scripts/dev_db.sh` then `scripts/dev_db.sh --verify` in remote sessions, and seeds the DRAFT client only in a dev-only
container.

## Placeholders that need Sam's replacement before go-live

| File | Status | Replace with |
|------|--------|--------------|
| `config/clients/upclicklabs.json` | **DRAFT** — offer, ICP, quiz questions, floors are my guesses | Sam's real values (30 minutes) |
| `references/families.md` | Name conflict resolved (Sam renamed the angles to `contrarian_led` / `identity_led`, 2026-10-28; the seed closes `ok`); the header still reads DRAFT and the DTC seed list PLACEHOLDER | Sam confirms the seed brands |
| `config/clients/upclicklabs/voc-seed/*.md` | **SYNTHETIC** — invented notes with fake names, for testing anonymisation | 5–10 real vault notes copied from `/Users/Sam/Documents/ucl-brain` |
| `fixtures/ad_library/*.json`, `fixtures/scrapecreators/*.json` | **ASSUMED SHAPE** | one real scrapecreators response per endpoint |
| `fixtures/supabase`, `meta`, `capi`, `turnstile`, `reddit`, `gemini`, `gmail_connector` | **ASSUMED SHAPE** from vendor docs / the connector's tool schema (2026-10-28) | the first recorded response of each, at its go-live step |
| `fixtures/model/*.json` | **HAND-WRITTEN** (incl. `revise_copy.json`, `retranslate_brief.json`) | re-recorded with `MODEL_BACKEND=claude` once the offer is real |
| `fixtures/voc/*.json` | **SYNTHETIC** — invented threads matching the placeholder URLs | nothing; set real thread URLs in `voc.public_sources` and `VOC_BACKEND=reddit` |

## Go-live swap checklist (do after the Friday checklist)

1. Warehouse: enable `vector` in Supabase Dashboard → Database → Extensions (schema `extensions`); put the `postgres`
   session-pooler string (port 5432, `sslmode=require`) in `WAREHOUSE_URL_ADMIN` in Sam's shell; run
   `scripts/apply_migrations.py --dry-run`, then `scripts/apply_migrations.py` (every numbered migration once, `0001`
   to `0008`, the five roles' LOGIN and SCRAM passwords from their `WAREHOUSE_URL_*` strings, the Data API roles
   revoked). If `0001`–`0007` were applied by hand, run `--baseline 0007` once first. Create the storage-writer user in
   Dashboard → Authentication (sign-ups off), then `scripts/apply_migrations.py --storage-writer <email>`. Set the five
   role strings to their session-pooler URLs; `scripts/dev_db.sh --verify` against them prints no FAIL.
2. `STORAGE_BACKEND=supabase` with `SUPABASE_URL` and `SUPABASE_STORAGE_BUCKET` for every process that reads assets
   (gate and executor included) and `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_STORAGE_EMAIL`, `SUPABASE_STORAGE_PASSWORD`
   for the writers only (intel, producer); re-run `render_creatives.py --reupload` so `asset_urls` point at Storage.
3. Replace the placeholder files above; register a Reddit app and set `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` and
   `REDDIT_USER_AGENT` for the language worker, `VOC_BACKEND=reddit`; re-run `pull_voc.py` and `plan_batch.py`.
4. Save one real scrapecreators response per endpoint to `fixtures/scrapecreators/` (search companies, company ads);
   fix the shape functions at the top of `adapters/inspo/scrapecreators.py` if the shape differs;
   `INSPO_BACKEND=scrapecreators`; re-run `pull_inspo.py` (until then the dev-era `file://` source URLs count as
   missing images in the gate).
5. `IMAGE_BACKEND=gemini` with `GEMINI_API_KEY` (and `IMAGE_MODEL` if not the default); save one test generation to
   `fixtures/gemini/` with the base64 replaced by `<PNG_BASE64>`; re-render.
6. Meta and the funnel: `META_BACKEND=live`; create two claude.ai environments (SKILL.md §8): `marketing-engineer`
   for the workers and the Gmail connector, and `marketing-engineer-executor` holding `META_ACCESS_TOKEN`,
   `META_PAGE_ID` and `WAREHOUSE_URL_EXECUTOR` (plus the executor's non-secret Meta and Storage variables) and nothing
   else; the workers' environment never holds those three (`scripts/routines.py dry-run` blanks them and the workers
   still run). `META_READ_TOKEN` for the workers; `META_AD_ACCOUNT_ID`, `META_PIXEL_ID` and `META_CUSTOM_CONVERSIONS`
   (`QuizStart=<id>,QuizComplete=<id>`, created as custom conversions in Events Manager) where `.env.example` says.
   Record one real ad read, one async insights page and one throttle response over `fixtures/meta/`. Deploy the quiz
   funnel from this repo to Vercel per `funnel/README.md` § "Deploy on Vercel" (`CAPI_BACKEND=live`,
   `TURNSTILE_BACKEND=live`, `META_CAPI_TOKEN`, `TURNSTILE_SECRET_KEY`, `WAREHOUSE_URL_APP`; `META_TEST_EVENT_CODE` on
   Preview only), CNAME `go` → Vercel, `FUNNEL_HOST=https://go.upclicklabs.com`; `scripts/test_events.py --live` green
   against the Preview (`VERCEL_AUTOMATION_BYPASS_SECRET` in Sam's shell).
7. `EMAIL_BACKEND=gmail_connector` with `CHECKIN_TO` set to Sam's plain address; connect the Gmail connector on the
   claude.ai account that owns the routines; send one check-in (`scripts/checkin.py`, `--send-pending`, the connector
   call, `--mark-sent <key> --message-id <id>`) and save the result over `fixtures/gmail_connector/send_message.json`;
   register the four routines with Sam's approval from `scripts/routines.py register --print`, each with the
   `environment_id` of the environment its row names (`me-executor` in `marketing-engineer-executor`, the rest in
   `marketing-engineer`).
8. Only then: `launch` → stop point C → `apply actions`.

Nothing in steps 1–7 changes code. If it does, that is a bug in the adapter boundary and goes back to the ticket that owns it.
