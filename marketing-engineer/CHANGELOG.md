# Changelog — Marketing Engineer Pipeline

Phase 0 (the weekend build, `PLAN.md` §1) built in dev mode per `references/dev-mode.md`: every external
service behind an adapter, fake backends and fixtures part of the build, tests against a local Postgres with
every migration applied. One commit per ticket; the tracker is `.scratch/marketing-engineer-phase0/issues/`.
The design documents did not change during the build; where the build found them disagreeing, the schema won
and the deviation is recorded in the ticket's comments and below.

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

Migrations: `schema.sql` (0001), `0002_roles.sql`, then `0003` to `0007` as above. Supabase gets them by hand at
go-live (`references/dev-mode.md` swap step 1); `scripts/dev_db.sh` applies them locally.

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
- **The `me-monday` routine and `onboard client`** have no script in phase 0; `SKILL.md` §3 says so and the
  orchestrator stops (T11, T12).
- **Picks 1, 3, 6 were recorded by the agent** on the dev database (`--by agent`) because the ranker's default would
  have chosen a `stat_card` recipe with no template (T5). Real picks are Sam's at go-live.
- **Stop points** A (picks), B (verdicts), C (launch), D (Sam's learning) were each reached on a dev database and are
  exercised end to end in the tests; the dev database does not carry over between build containers, so a fresh
  session rebuilds the state with the command sequence in the T5 comment (`dev_db.sh --seed` → `pull_inspo.py` →
  `pull_voc.py` → `plan_batch.py` → `--select` → `render_creatives.py` → `gate.py`, all `MODEL_BACKEND=fixture`).

### Still DRAFT or synthetic at the end of phase 0

Nothing below blocks the tests; all of it blocks going live. The full list with replacements is
`references/dev-mode.md` § "Placeholders"; the Friday checklist is `SKILL.md` §11.

| What | State | Owner |
|------|-------|-------|
| `config/clients/upclicklabs.json` | **DRAFT**: offer (`promise`, `proof_points`, `calendar_url` are PLACEHOLDER), ICP, quiz questions (PLACEHOLDER text; q2 unscored, hard mode off), `voc.vault_path` (PLACEHOLDER), floors, `cpm_estimate`, trust thresholds, rate limits, worker budgets, brakes (`0.3 / 1 / 3 / 3 / 7 / 1`), `voc.public_sources` (three placeholder URLs) | Sam |
| `references/families.md` | **DRAFT**: 15 families, 7 hook types, 5 angles, DTC seed list. `contrarian` and `identity` are both a hook type and an angle; `families.name` is unique, so `scripts/seed.py` skips the two angle rows and closes its run `failed` naming them until Sam renames the angles (e.g. `contrarian_led`, `identity_led`). Side effect seen in the T12 dry run: on a dev database seeded more than three times, those failed `seed` runs trip the check-in's worker error-rate brake and the morning check-in proposes `set_pause_flag` | Sam (open since T0) |
| `config/clients/upclicklabs/voc-seed/*.md` | **SYNTHETIC** notes with invented names, for the anonymisation tests | Sam copies 5 to 10 real vault notes |
| `fixtures/ad_library/*.json` | **ASSUMED SHAPE** until one real scrapecreators call is saved as `real-001.json`; the adapter normalises whatever the real shape is | Sam (Friday item 6) |
| `fixtures/voc/*.json` | **SYNTHETIC** threads matching the placeholder URLs | replaced by `VOC_BACKEND=reddit` |
| `fixtures/model/*.json` | **HAND-WRITTEN** model outputs (the build containers had no `ANTHROPIC_API_KEY`); `MODEL_BACKEND=claude` is wired in every worker but unexercised | re-record once the offer is real |
| `fixtures/checkin/golden-body.txt` | golden body of the five-part email as the dev database produces it | regenerate on a deliberate change |
| Live adapters | `storage/supabase`, `meta/live`, `capi/live`, `inspo/scrapecreators`, `voc/reddit`, `image/gemini`, `email/gmail`, `turnstile/live` raise "not built, T13" by name | T13 |
| `funnel/` | runs locally on 8788; `/quiz` and `/cal-webhook` are function code, not yet deployed; `META_PIXEL_ID`, `TURNSTILE_SITE_KEY` unset | T13 moves it to `go-upclicklabs` on Vercel |
| Routines | defined in `config/routines.json`, dry-run locally; not registered as Claude Code Routines | T13 step 7 |

### Known gaps carried into T13 / phase 1

- `ad_entities.review_status` is synced by `activate` only; the insights pull should sync it on every ad it reads and
  count disapprovals against `disapproval_pause_threshold` (FR-37 second half; T9 note for T10, not done in T10).
- The gate's FR-29 feedback object is written but no worker reads it; a re-render is Sam's `produce --rerender`.
- `EMAIL_BACKEND=gmail` stays `not_built` until T13 decides whether the routine session sends the composed `.eml`
  through the Gmail connector or the adapter gets an API client.
- FR-43 Monday memo, `onboard client`, client-scoped RLS, ablation and scaling campaigns, the phase-1 cut list in
  `PLAN.md` §5.
