# Changelog — Marketing Engineer Pipeline

Phase 0 (the weekend build, `PLAN.md` §1) built in dev mode per `references/dev-mode.md`: every external
service behind an adapter, fake backends and fixtures part of the build, tests against a local Postgres with
every migration applied. One commit per ticket; the tracker is `.scratch/marketing-engineer-phase0/issues/`.
The design documents did not change during the build; where the build found them disagreeing, the schema won
and the deviation is recorded in the ticket's comments and below.

## Local hand-off on Sam's Mac — 2026-10-29 (branch `claude/sleepy-brahmagupta-jng3kp`)

Following `references/handoff-local.md`:

- **macOS dev harness** (`8edf135`): `scripts/dev_db.sh` takes a Homebrew `postgresql@16` path (pgvector built into
  the keg from Homebrew's source tarball, `postgres` superuser role, `scram-sha-256` on TCP, self-signed TLS); the
  venv lives at the repo root. The suite runs green on the Mac.
- **Keychain → environment** (`9bc9513`): `scripts/env_from_keychain.sh` maps each variable to a keychain
  service/account and prints names only; the Meta write token needs `--with-meta-write`. Anthropic and Gemini come
  from the live `aeo-pipeline-v3` items; every other credential is expected at `marketing-engineer/<VAR>`.
- **Model adapter for Opus 5 / 5.5**: thinking is always on and counts against `max_tokens`, so the callers' small
  limits (gate 1500 / 500 / 800, the image check 512, VOC 2048) would have truncated every real call. The caller's
  `max_tokens` is now the answer budget and the request adds headroom (`max(caller + 12000, 16000)`, at most 20000,
  non-streaming); `output_config.effort` comes from `MODEL_EFFORT` (default `high`; Opus 5.5 defaults to `medium`);
  default `MODEL_ID` is `claude-opus-5-5`; refusals opt into the server-side fallback (`fallbacks="default"`, beta
  `server-side-fallback-2026-07-01`) and the answer is read after the last `fallback` block. `ModelResult.model`
  records the model that served it. FR-49, NFR-4.
- **Preflight** (`2be5e74`): `scripts/preflight.py` proves each set credential with one read-only call and writes
  names and status only to `references/credentials-status.md`. On 2026-10-29 only Anthropic and Gemini were set,
  and both were ok.
- **Live-run blockers**: `references/live-run-blockers.md` lists Sam's remaining items, checked against the repo,
  preflight and DNS. `go.upclicklabs.com` does not resolve yet. The routines are printed, not registered; cloud or
  local `launchd` is Sam's call.
- **A second, creative-only client (Circadian, Step 6 gaps 1 and 2)**:
  - `scripts/seed.py --config <path>` seeds any client file. The default is still `upclicklabs.json`, and a failed run
    is attributed to the file's client, not to upClickLabs.
  - `clients.config.brand.banned_terms` is a list of words the gate's rule-based brand check rejects wherever they
    appear, ignoring case and treating spaces and hyphens alike, whole words only. The planner, producer and gate
    prompts list them.
  - An offer with its own `landing_url` (a shop's product page) is named as that page and its terminal metric in the
    producer and gate prompts, instead of "the quiz, then a 15-minute call". `landing_check` already passed a
    non-funnel URL. The upClickLabs prompts are unchanged.
  - `config/clients/circadian.json` is DRAFT: product facts only from Jacob's fact file of 2026-10-27; no `campaign`
    or `trust` block, so nothing can launch from it; inspo seeds, customer-language sources, templates and imagery
    wait on Sam.
  - Not touched, launch-side only: `meta_insights.py` still assumes booked calls and the quiz floors.
- **Sam's Step 6 answers, 2026-10-31**:
  - Product: the Buckwheat Pillow.
  - Template: `product_photo_caption`, the product in a real room with one line of copy under the photo. It is a new
    format row in `references/families.md` and `assets/creative-templates/product-photo-caption.html`, with one
    `caption` slot.
  - Imagery: Gemini with Jacob's reference photos as ground truth.
    - `generate()` takes `references` (PNG or JPEG, at most 6), sent first as inline image parts. The request shape
      `inline_data` / `mime_type` is ASSUMED.
    - `clients.config.image_references` names the photo sets. Each execution takes the next set, and the
      "Use [Image n] (file) ..." lines go before the image prompt, so the no-text instruction stays last and
      `creatives.image_prompt` records the files.
    - The photos stay in Sam's vault. There is no tag or logo reference, because images are text-free (FR-24).
  - Inspo: Hullo, Avocado, Coyuchi, Naturepedic and Turmerry, the fact file's main rivals.
- **Apify for the Ad Library pull (Sam, 2026-10-31; DECISIONS.md "Inspo vendor: Apify")**:
  - `adapters/inspo/apify.py` (`INSPO_BACKEND=apify`) runs Apify's own actor `apify/facebook-ads-scraper` on each
    brand's page from `clients.config.inspo.pages`, polls the run, reads its dataset and normalises it to the same ad
    dict.
  - Each run is capped in ads (`maxItems`) and in dollars (`maxTotalChargeUsd`, 1 USD); a run that does not end is
    aborted. The token travels only in the Bearer header, never to the CDN.
  - The CDN download and date parsing moved to `adapters/inspo/shared.py`; scrapecreators keeps its errors and
    messages.
  - `fetch_ads` takes an optional `page`, which the other backends ignore. `pull_inspo.py --per-brand N` caps the ads,
    and so the model calls, per brand (default 50).
  - `APIFY_TOKEN` is mapped to the keychain item `aeo-discovery-pipeline/apify`. Preflight checks it with
    `GET /v2/users/me`; on 2026-10-31 it was ok, plan STARTER.
  - The first real runs (2026-10-31, about $0.06) confirmed the per-ad shape and showed two more:
    - a page with no ads answers one summary item (`results: []`), which counts as zero ads;
    - an input the actor cannot read answers one error item (`no_items`), which fails the source.

    The fixtures record all three shapes with synthetic values.
  - Avocado's website links a page that is not its advertiser, so Circadian's `inspo.pages` are Ad Library URLs built
    from each advertiser's page id (active ads, US). Hullo has no Meta ads, active or past.
  - `scripts/seed.py --refresh-config` rewrites an existing client's `clients.config`, `currency` and `daily_cap` from
    its file. A plain re-seed leaves an existing client as it was, so the new pages never reached the database.

## Phase 0 completion — 2026-10-28 (branch `claude/sleepy-brahmagupta-jng3kp`)

Wave 0 (`476b985`): Sam renamed the clashing angles to `contrarian_led` / `identity_led`, so `scripts/seed.py`
inserts every family and closes `ok` (Friday item 8 done); `dev_db.sh` refreshes the apt index once when pgvector is
missing; `httpx` pinned for the live adapters. Then six builders worked in parallel on branches from `476b985`,
merged with `--no-ff` in the order below, and one integration commit aligned them.

| Builder | Commit (merge) | What landed |
|---------|----------------|-------------|
| supabase | `698fb82` (`175592e`) | `STORAGE_BACKEND=supabase` (`adapters/storage/supabase.py`): uploads with `x-upsert` into a public bucket and returns the public object URL; writes as a dedicated Supabase Auth user whose only grant is an RLS policy on `storage.objects` (insert / select / update in one bucket, no delete), never the service role. `scripts/apply_migrations.py`: every numbered migration once (`ops.schema_migrations` with sha256, `--dry-run`, `--baseline`), a superuser-only preflight, LOGIN + client-side SCRAM verifiers for the five roles, the Data API roles revoked on Supabase, `--storage-writer`, `--verify`. `scripts/dev_db.sh --verify` runs that verify against local or remote URLs. `fixtures/supabase/` |
| sources | `dd60079` (`2a2cdfd`) | `INSPO_BACKEND=scrapecreators` (search companies → pageId → company ads by cursor; CDN images https-only on ad CDN hosts, converted to PNG; vendor calls in `runs.counts.inspo_usage`), `VOC_BACKEND=reddit` (app-only OAuth, else anonymous `.json`; no author anywhere), `IMAGE_BACKEND=gemini` (`IMAGE_MODEL`, nearest aspect ratio, exact-size PNG, `ImageBlocked`). The producer counts a block as a failed attempt and records the backend's `model_id` as `image_model`. Shared bounded retry `adapters/backoff.py`. `fixtures/scrapecreators`, `reddit`, `gemini` |
| meta | `793348c` (`75f4a38`) | `META_BACKEND=live` (`adapters/meta/live.py`): write mode on `META_ACCESS_TOKEN` for `scripts/apply_actions.py` only, read mode on `META_READ_TOKEN` refusing every write; budgets in the account's minor units; images to `adimages` by `image_hash`; QuizStart / QuizComplete through `META_CUSTOM_CONVERSIONS`; async insights; throttle back-off by the usage headers, then `MetaThrottled`; a write that may have landed is never re-sent. `scripts/meta_insights.py` syncs `review_status` / `review_feedback` for every ad it reads and proposes `set_pause_flag` at `disapproval_pause_threshold` (FR-37 second half); migration `0008_loop_review_sync.sql` (built as 0014). `fixtures/meta/` |
| funnel | `fc0b59d` (`e675cbb`) | `CAPI_BACKEND=live` and `TURNSTILE_BACKEND=live`; the quiz funnel packaged for Vercel **from this repo** (`api/funnel.py` over `funnel/wsgi.py`, `api/requirements.txt`, Python 3.13, `vercel.json`, `.vercelignore` allowlist; role `app` only, other jobs' credentials refused, live backends required on Vercel); `scripts/test_events.py --live`; `funnel/README.md` § "Deploy on Vercel". Fixed a T7 bug: `quiz.js` reused one single-use Turnstile token for `/quiz/start` and `/quiz`, which would have refused every completion under `TURNSTILE_BACKEND=live`. `fixtures/capi`, `turnstile` |
| checkin | `85042b2` (`26ea37c`) | `EMAIL_BACKEND=gmail_connector` (alias `gmail`): the check-in is queued once per client and UTC day; `scripts/checkin.py --send-pending` prints the Gmail connector's `send_message` arguments, `--mark-sent <key> --message-id <id>` records the delivery; a check-in never marked sent is a warning in the next one. `me-morning` gains the send step; `scripts/routines.py register --print` prints the `create_trigger` arguments and registers nothing. SessionStart hook: name-only report of every live variable and selector, `dev_db.sh --verify`, seeds only a dev-only container. `fixtures/gmail_connector/` |
| gaps | `6b3ad06` (`0aac34d`) | `scripts/monday_memo.py` (FR-43, five sections, golden-file test, `me-monday` step); the FR-29 retry loop (`produce` consumes the gate's feedback: producer-routed failures get the next version through task `revise_copy`, coherence failures are re-translated by `plan batch` / `--retranslate`, attempt 4 impossible; the launcher keeps a re-translation in its recipe's ad set); `--select default` takes the ranker's top N with a weekend template |
| integration | this commit | Conflicts: `scripts/render_creatives.py` keeps gaps' `render_recipe` / `render_execution` split with sources' `ImageBlocked` drop and `model_id` (now `Batch.image_model`); `warehouse/schema-notes.md` keeps both sides' rows. `adapters/graph.py`: one Graph host and one `META_API_VERSION` default (v26.0) for the Marketing API and CAPI adapters (CAPI had v24.0). Supabase's transient retry goes through `adapters/backoff.py`. `0014` renumbered `0008`. The Monday memo is queued for the Gmail connector like the check-in (`memo-<slug>-<UTC day>`) and `me-monday` gains the send step (gaps sent it through `get_email()`, which under `gmail_connector` would have queued it with no step to deliver it). `adapters.env.not_built` removed (no adapter is unbuilt). `.env.example`, `SKILL.md` §1/§3/§5.1/§8/§9/§11, `references/dev-mode.md`, this file, the tracker |

Migrations are now `0001` to `0008`; `scripts/dev_db.sh` applies them locally, `scripts/apply_migrations.py` on
Supabase at go-live (swap step 1).

### Decisions taken in this build (Sam to overrule)

- **Storage bucket is public**: Meta fetches creative images by URL, the gate derives sibling objects from the stored
  asset URL, and `asset_urls` are permanent, which a signed URL's token and expiry would break. Keys are UUIDs and
  there is no list policy. Open: whether inspo copies of other brands' ads should go to a separate private bucket.
- **Storage writes as a dedicated Auth user** with an RLS policy, not S3 keys, the service key or a custom JWT. Only
  the intel and producer workers hold its password.
- **Data API locked out of the warehouse**: Supabase's default privileges give `anon` / `authenticated` ALL on what
  `postgres` creates in `public`, which would let a publishable-key holder approve actions; `apply_migrations.py`
  revokes them and `--verify` fails while they hold privileges.
- **Workers read Meta with their own `ads_read` token** (`META_READ_TOKEN`); they never fall back to the executor's
  write token (NFR-1). Creative images go to `adimages` and are referenced by `image_hash`.
- **QuizStart / QuizComplete are custom conversions** (`META_CUSTOM_CONVERSIONS`): the ad sets optimise them and the
  insights count them. Budgets use the ad account's currency as Meta reports it; a mismatch with `clients.currency`
  is not checked yet.
- **Disapprovals** count once, at the first loop run that lists an ad disapproved within 7 days; the first live run
  sees old disapprovals as new.
- **One `META_API_VERSION` default, v26.0**, for the Marketing API and CAPI (`adapters/graph.py`; integration).
- **A CAPI send failure is a `capi_failed` log line**; the quiz request still answers 200 and there is no replay.
- **Check-in and memo go out through the Gmail connector queue**, one message per client, kind and UTC day; a crashed
  claim blocks re-queueing that day (never two messages). `me-morning` stays `0 6 * * *` UTC (07:00 CET in winter).
- **FR-29 retry is automatic on every `produce`**, bounded by the three-attempt cap and the worker budgets.
- **`--select default` skips template-less families**; an explicit pick of one is recorded with a warning and
  `produce` refuses it as before. This replaces the agent-recorded picks of T5.
- **The memo reuses `CHECKIN_TO`**; variant → family promotions are text backed by creative ids, since the executor
  has no `promote_variant` handler.
- **Gemini default model `gemini-nano-banana-2.1`**; Reddit has both an OAuth and an anonymous path.
- **`0014_loop_review_sync.sql` renumbered `0008`** so the migrations stay contiguous (integration).

### Review fixes (same branch, after the integration commit)

- **Check-in and memo windows open at the last message sent or queued** (`checkin.window_anchor`): under
  `gmail_connector` a second run on the same day queues nothing (`duplicate`) and a `--dry-run` sends nothing, but both
  closed `ok` and became the next window's start, so what happened between the delivered message and them reached no
  email. They no longer move it.
- **`--send-pending` prints the body as data**: the `send_message` arguments sit inside an `untrusted_data` frame that
  text in the body cannot close (a tag's `<` is the JSON escape `<`), with the line that they are data; the
  routine prompts say the same. A queue file whose `to` is not exactly `CHECKIN_TO` is refused and left in the queue
  (`refused_recipient`).
- **The executor runs alone in its own routine and environment**: a session gives every step and the agent one
  environment, so `me-morning` running `apply actions --reconcile` meant the Meta write token sat beside the Gmail
  connector, Bash and the check-in's untrusted text. `me-executor` (`45 5 * * *` UTC, before the 08:00 check-in) runs
  `apply_actions.py --reconcile` alone in `marketing-engineer-executor` (`META_ACCESS_TOKEN`, `META_PAGE_ID`,
  `WAREHOUSE_URL_EXECUTOR`, no connector); `me-morning` no longer applies; `scripts/routines.py check` enforces it,
  `register --print` carries each routine's `environment_id`, and the dry-run of a worker routine blanks the
  executor-only variables. Sam to overrule: this is a third short daily wake beside FR-48's two (NFR-5 budgets two
  model wakes a day); the alternative is applying only from Sam's shell.
- **Meta pacing at ≥90% usage** waits `PACE_DEFAULT_WAIT` when the headers state 0 (Meta sends
  `estimated_time_to_regain_access: 0` until the caller is blocked), instead of not waiting at all.
- **`scripts/test_events.py` without `--live` refuses a funnel it did not start unless `/quiz/config` reports
  `capi_backend: fake`**: a deployment runs `CAPI_BACKEND=live` and would have sent the synthetic prospects to the
  production pixel with no test event code.

### Contract-tested, NOT live-verified

Every live backend runs against `httpx.MockTransport` (or the connector's tool schema) with fixtures marked ASSUMED
SHAPE. No credentialed vendor call was made in this build.

| Backend | Fixtures | Source of the shape | Record at go-live |
|---------|----------|---------------------|-------------------|
| `storage/supabase` + `scripts/apply_migrations.py` | `fixtures/supabase/` | storage3 / supabase-auth 2.33.0 on PyPI (supabase.com unreachable from the build) | an upload, a sign-in, an RLS refusal (400 or 403 is not pinned); the storage policy and bucket SQL on a real project |
| `meta/live` | `fixtures/meta/` | Meta's Marketing API docs, read 2026-10-28 | one GET ad (approved, disapproved), one async insights page with QuizStart / Schedule, one throttle response |
| `capi/live` | `fixtures/capi/` | Conversions API docs, read 2026-10-28 | the Test events tab showing the three events (`test_events.py --live`) |
| `turnstile/live` | `fixtures/turnstile/` | Cloudflare siteverify docs, read 2026-10-28 | one Production siteverify |
| `inspo/scrapecreators` | `fixtures/scrapecreators/`, `fixtures/ad_library/` | search summaries only (the docs were outside the build's network allowlist) | one real response per endpoint |
| `voc/reddit` | `fixtures/reddit/` | Reddit's archived API wiki + search summaries | one OAuth token and one thread |
| `image/gemini` | `fixtures/gemini/` | search summaries of Google's docs and release notes | one test generation (confirms the model id) |
| `email/gmail_connector` | `fixtures/gmail_connector/` | the session's `send_message` tool schema | the first real send's result |
| Vercel packaging | — | `@vercel/python` 29.0.0 / `vercel-runtime` 0.24.1, invoked as Vercel does | the first Preview deployment |

### Still DRAFT or synthetic

Nothing below blocks the tests; all of it blocks going live. The full list with replacements is
`references/dev-mode.md` § "Placeholders"; the Friday checklist is `SKILL.md` §11.

| What | State | Owner |
|------|-------|-------|
| `config/clients/upclicklabs.json` | **DRAFT**: offer (`promise`, `proof_points`, `calendar_url` are PLACEHOLDER), ICP, quiz questions (PLACEHOLDER text; q2 unscored, hard mode off), `voc.vault_path` (PLACEHOLDER), floors, `cpm_estimate`, trust thresholds, rate limits, worker budgets, brakes, `disapproval_pause_threshold`, `voc.public_sources` (three placeholder URLs) | Sam |
| `references/families.md` | name conflict **resolved** (angles `contrarian_led` / `identity_led`, Sam 2026-10-28; Friday item 8 done); the header still reads DRAFT and the DTC seed list PLACEHOLDER | Sam confirms the seed brands |
| `config/clients/upclicklabs/voc-seed/*.md` | **SYNTHETIC** notes with invented names, for the anonymisation tests | Sam copies 5 to 10 real vault notes |
| `fixtures/ad_library/*.json`, `fixtures/scrapecreators/*.json` | **ASSUMED SHAPE** until one real scrapecreators call per endpoint is saved | Sam (Friday item 6) |
| `fixtures/supabase`, `meta`, `capi`, `turnstile`, `reddit`, `gemini`, `gmail_connector` | **ASSUMED SHAPE** (table above) | recorded at each go-live step |
| `fixtures/voc/*.json` | **SYNTHETIC** threads matching the placeholder URLs | replaced by `VOC_BACKEND=reddit` |
| `fixtures/model/*.json` | **HAND-WRITTEN** model outputs, now including `revise_copy.json` and `retranslate_brief.json`; `MODEL_BACKEND=claude` is wired in every worker but unexercised | re-record once the offer is real |
| `fixtures/checkin/golden-body.txt`, `fixtures/monday/golden-body.txt` | golden bodies as the test scenarios produce them | regenerate on a deliberate change |
| `funnel/` + `api/` | built for Vercel from this repo, **not deployed**; function region unset (defaults to US East until set to the Supabase EU region) | Sam (Friday item 4, swap step 6) |
| Routines | defined in `config/routines.json`, dry-run locally, `register --print` ready; **not registered** | T13 step 7, with Sam's approval |

### Known gaps carried into T13 / phase 1

- T13 itself: every step of the go-live swap waits on Sam's credentials and accounts (`SKILL.md` §11).
- `onboard client`, client-scoped RLS, ablation and scaling campaigns, the phase-1 cut list in `PLAN.md` §5.
- No replay for a failed CAPI send (logged `capi_failed` only); the funnel's rate limiter is per function instance on
  Vercel.
- No `promote_variant` executor action: an approved promotion is a hand edit to `references/families.md`.
- No re-send path for a queued check-in or memo whose session died before sending (`--requeue` is an open question).
- Currency mismatch between the ad account and `clients.currency` is not refused.
- Test isolation: running `tests/test_render_creatives.py` before `tests/test_pull_inspo.py` in one process trips
  `hooks_pattern_id_fkey`; the default alphabetical order passes.

## Phase 0 — 2026-09-07 to 2026-09-10 (branch `claude/marketing-engineer-phase0-odmkd9`)

| Ticket | Commit | What landed |
|--------|--------|-------------|
| T0 dev harness | `0719153` | `scripts/dev_db.sh` (local Postgres 16, pgvector, every numbered migration applied once, roles LOGIN), `scripts/seed.py`, `adapters/env.py`, eight dev adapters (`storage/local`, `meta/fake`, `capi/fake`, `inspo/fixture`, `voc/fixture`, `image/placeholder`, `model/claude` + `fixture`, `email/file`, `turnstile`), `fixtures/ad_library/`, `.env.example` |
| T1 warehouse client | `39d988e` | `warehouse/client.py`: one connection per role from `WAREHOUSE_URL_*`, insert helpers for every table, the `runs` context manager (`run()` / `Run.count()`), the "where are we" query and CLI (`warehouse/client.py status`), the two read-before-planning queries; `0003_phase0_grants.sql` |
| T2 format library | `1a4069a` | `scripts/pull_inspo.py`: five DTC seed brands → `raw_ingest` (dedup key) → Storage copies of every snapshot image → vision decomposition into `patterns` with the 30-day / 3-variant rule, FR-8 source warnings and blocks, `--acknowledge` |
| T3 VOC seed | `f408777` | `scripts/pull_voc.py`: seed notes and fixture threads → anonymised `voc_phrases` with `source_ref`, `source_weight`, `visibility`, `trust_tier`; validator refuses surviving identifiers; `adapters/voc`, `fixtures/voc/` |
| T7 quiz funnel | `2de3aa1` | `funnel/`: static quiz page with consent step, `/quiz` and `/cal-webhook` function code, local server on 8788; `0004_quiz_rpc.sql` (role `app` writes leads through RPCs only), `0005_mcp_ro_leads_columns.sql` (DR-4 column grant fix); `scripts/test_events.py` |
| T8 executor | `4e481e7` | `scripts/apply_actions.py`: advisory lock, pause re-check, `check_daily_cap()`, trust from `trust_streaks` with computed demotion, rate limits, brakes, `--reconcile`, `--role sam_admin`; `scripts/decide.py` chat approvals; `0006_executor_runs.sql` |
| T4 planner | `1ae2838` | `scripts/plan_batch.py`: capacity into `experiments`, deterministic ranker (source strength × family diversity), translation through the model adapter with `changed_ingredients` restricted to the four FR-18 ingredients, the §5.1 picks table, `--select`; FR-7 retired-family and FR-8 blocked-source refusals |
| T5 producer | `55dce7d` | `scripts/render_creatives.py`: two creatives per chosen brief through `assets/creative-templates/job-photo-bubble.html` / `screenshot-ad.html` and Playwright at 1080×1080, copy per `references/direct-response-copy.md`, text-free images with a vision check, `creatives` + full `creative_components` or nothing, `--rerender`, `--reupload` |
| T6 gate | `8e55c50` | `scripts/gate.py`: eight hard checks into `gate_scores.hard_checks`, shadow rubric (`references/creative-rubric.md`), FR-29 feedback object, the §5.2 table, `--verdicts` for Sam's chat verdicts (facts block approval; default ships nothing) |
| T9 launcher | `fe5193c` | `scripts/meta_launch.py`: one proposed `build_campaign` per experiment from Sam's approve verdicts, then the cascade `activate`; `warehouse/launch.py` validator; executor paths for both; `0007_launch.sql` (cap counts each ad set once; executor inserts `ad_entities`, moves creatives to `live`) |
| T10 loop | `10ae6de` | `scripts/meta_insights.py`: `ad_metrics_daily` keyed by `fetched_on`, `account_spend_hourly`, the lever chain into `campaigns.active_lever` with a reason naming its benchmark source, kill / scale proposals with evidence from `mart_kill_scale_candidates` (`config_missing` is a hard stop), `cpl_target` derivation reported, agent learnings only through the FR-41 gates, `--learning` for Sam's hand-written row |
| T11 check-in + routines | `e87c285` | `scripts/checkin.py` (five-part email through the email adapter, golden-file test, FR-47 error-rate and lead-velocity brakes), `scripts/pause.py`, `config/routines.json` + `scripts/routines.py list|check|dry-run`, `.claude/hooks/session-start.sh` at the repository root |
| T12 skill finish | this commit | `SKILL.md` §1, §3, §5.3, §9 reconciled with what exists, §11 Friday checklist and go-live pointer; `references/prompts/intel.md` (the intel worker's prompts now load from the file like the other four workers); `warehouse/schema-notes.md` completed; this file; `tests/test_skill.py` |

Migrations: `schema.sql` (0001), `0002_roles.sql`, then `0003` to `0007` as above (`0008` came with the completion
build). `scripts/dev_db.sh` applies them locally; on Supabase `scripts/apply_migrations.py` does (2026-10-28).

### Decisions taken during the build (Sam to overrule)

- **`check_daily_cap()` counts each ad set once** (`0007`): the 0002 function summed every ACTIVE ad row, which
  double-counted the batch-one shape against its own comment (T8 finding, T9 migration).
- **Admin-only actions**: `set_pause_flag`, `promote_trust`, `quote_release` cannot be approved or applied by the
  executor role; Sam runs `decide.py --as sam_admin` and `apply_actions.py --role sam_admin` on
  `WAREHOUSE_URL_SAM_ADMIN` (T8). `SKILL.md` said `WAREHOUSE_URL_ADMIN`; that name is the dev-only superuser (T12 wording fix).
- **Trust demotion is computed**, never stored: a `failed` action of a type since its last applied `promote_trust`
  takes the type out of autonomous mode (T8).
- **Ad set budgets come from config** (`campaign.adset_daily_budget` 15, `daily_cap` 45; quiz decision 1, 2026-09-04),
  not the "€10/day" in the kickoff deliverable (T9).
- **The `me-monday` routine and `onboard client`** had no script in phase 0; `SKILL.md` §3 said so and the
  orchestrator stopped (T11, T12). The memo was built on 2026-10-28; `onboard client` still stops.
- **Picks 1, 3, 6 were recorded by the agent** on the dev database (`--by agent`) because the ranker's default would
  have chosen a `stat_card` recipe with no template (T5). Real picks are Sam's at go-live. Since 2026-10-28 the
  default itself skips template-less families and lands on 1, 3, 6.
- **Stop points** A (picks), B (verdicts), C (launch), D (Sam's learning) were each reached on a dev database and are
  exercised end to end in the tests; the dev database does not carry over between build containers, so a fresh
  session rebuilds the state with the command sequence in the T5 comment (`dev_db.sh --seed` → `pull_inspo.py` →
  `pull_voc.py` → `plan_batch.py` → `--select` → `render_creatives.py` → `gate.py`, all `MODEL_BACKEND=fixture`).

### Still DRAFT and known gaps

Superseded by the "Phase 0 completion — 2026-10-28" section above: the live adapters are built (contract-tested, not
live-verified), the families name conflict is resolved, and the FR-37 review sync, the FR-29 feedback reader, the
`EMAIL_BACKEND` decision (Gmail connector) and the FR-43 Monday memo are closed.
