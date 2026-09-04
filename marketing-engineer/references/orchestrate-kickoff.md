# Kickoff prompt for `/orchestrate` — Marketing Engineer Pipeline, phase 0

Paste everything below the line into a fresh Claude Code session on branch `claude/marketing-engineer-pipeline-8d7hfs` of `samupclick/claude-skills`, after the Friday checklist in `marketing-engineer/CRUCIBLE.md` §4 is done.

---

Use the orchestrate skill.

## What we are building

Phase 0 of the Marketing Engineer Pipeline, specified in `marketing-engineer/PRD.md` v1.0 (functional requirements FR-1 to FR-49, data requirements DR-1 to DR-6, non-functional requirements NFR-1 to NFR-7). The architecture is `marketing-engineer/ARCHITECTURE.md` v1.1. The data model is already written and validated: `marketing-engineer/warehouse/schema.sql` (migration 0001) and `warehouse/0002_roles.sql`. The orchestrator skill that will run the finished pipeline is `marketing-engineer/SKILL.md`; every script you build must match its run-mode table (§3) and its executor procedure (§6). If documents disagree, the precedence is: schema → PRD → ARCHITECTURE → CRUCIBLE → DECISIONS. `PLAN.md` is the schedule only.

Goal of this session: close one honest loop for the `upclicklabs` client — ad live → metrics rows in the warehouse → one learning row — per `PLAN.md` §1 items 1–11. Sub-sample numbers are expected.

## Before dispatching any task

1. Read `PRD.md`, `SKILL.md`, `warehouse/schema.sql`, `warehouse/0002_roles.sql`, `CRUCIBLE.md` §3–4, and `PLAN.md` §1–4 yourself. Subagents get the excerpts you hand them, not the whole history.
2. Verify the Friday prerequisites and stop if any starred item is missing: env vars `WAREHOUSE_URL_WORKER`, `WAREHOUSE_URL_EXECUTOR`, `SUPABASE_URL`, `SUPABASE_STORAGE_BUCKET`, `SCRAPECREATORS_API_KEY`, `GEMINI_API_KEY` present (do not print values); `select count(*) from families` ≥ 15; `select count(*) from clients where slug='upclicklabs'` = 1 with `daily_cap`, `currency`, `config.targets.ctr_floor`, `config.targets.kill_impressions` set; `config/clients/upclicklabs.json` exists with `batch.recipes = 3`, `optimisation_event = "QuizStart"`; `config/clients/upclicklabs/voc-seed/` has ≥ 5 notes; `references/families.md` exists with the DTC seed list.
3. Confirm the six resolved veto items in `PRD.md` §12 are reflected in config (V1 three recipes, V2 QuizStart, V3 one renderer, V4 chat verdicts, V5 testimonial block, V6 Grok not in this phase).

## Task graph

Dispatch in dependency order. Each task is one subagent with a fresh context. Each task ends with: tests passing, a `runs` row written by a real invocation against the warehouse, and one commit on this branch with a message that names the FR ids satisfied. No task may start before its dependencies are committed.

| # | Task | Depends on | Deliverable | Acceptance (from PRD) |
|---|------|-----------|-------------|------------------------|
| T1 | Warehouse client | — | `warehouse/client.py`: psycopg connection per role from env, insert helpers for every table in `schema.sql`, the "where are we" query from `SKILL.md` §2, the two read-before-planning queries from `SKILL.md` §4.2, a `runs` context manager | Unit tests with a local Postgres fixture applying `0001` + `0002`; every helper round-trips; a worker role cannot update `actions` (FR-44) |
| T2 | Intel: format library | T1 | `scripts/pull_inspo.py`: scrapecreators Ad Library → `raw_ingest` (dedup_key) → download every snapshot image to Storage → vision decomposition (Claude) into `patterns` with `family` from `families`, `variant`, `recipe.format_layer`, `source_strength`, `status` by the 30-day / 3-variant rule → `runs` counts | FR-4, FR-5, FR-6, FR-8; ≥ 24 rows for the 5 seed brands; re-run adds zero duplicates; a pattern with a CDN URL and no Storage copy is rejected |
| T3 | Language: VOC seed | T1 | `scripts/pull_voc.py`: `voc-seed/` notes + 2–3 Reddit thread URLs from config → anonymise (names, companies, figures) → `voc_phrases` with `source_ref`, `source_weight`, `visibility`, `trust_tier`, dedup on `(source_ref, phrase_normalised)` | FR-10 to FR-13; ≥ 15 rows; seeded fake name in a fixture fails the validator; no write path to the vault |
| T4 | Planner | T1, T2, T3 | `scripts/plan_batch.py`: capacity formula → `experiments.capacity`; deterministic ranker (source strength × family diversity); translation with `changed_ingredients ⊆ {offer, product_nouns, voc_phrases, imagery_subject}`; 4× proposals as `briefs`; `--select "2,5,9"` writes `selections` and marks chosen; prints the numbered table in `SKILL.md` §5.1 format | FR-14 to FR-20; at €30/day and €25 CPM capacity = 4 and a 6-creative batch is refused; a brief changing `copy_length` is rejected; same inputs → same order |
| T5 | Producer | T4 | `scripts/render_creatives.py`: copy per `references/direct-response-copy.md` (write that reference if missing, ≤ 60 lines); two HTML templates in `assets/creative-templates/` (`job-photo-bubble.html`, `screenshot-ad.html`); Gemini image generation with a no-text instruction; Playwright render 1080×1080 → Storage; `creatives` + full `creative_components` (family, variant, hook, angle, template, renderer, image_model, voc_phrase, cta, landing_page, offer) | FR-21 to FR-25; 6 creatives for 3 chosen briefs; a creative missing any component is refused by the script's validator; nothing binary committed |
| T6 | Gate | T5 | `scripts/gate.py`: hard checks (policy prompt, brand hard blocks, likeness, testimonial block, coherence → planner, components, landing URL match, verbatim phrase without release) into `gate_scores.hard_checks`; rubric in `mode='shadow'`; `--verdicts "approve 1,3; reject 2: reason"` writes `scored_by='sam'`, `decision_channel='chat'`; prints the §5.2 table | FR-26, FR-27, FR-29; one fixture per hard check that fails it; no `agent` row ever has `mode='blocking'` |
| T7 | Quiz funnel (separate repo `go-upclicklabs`, Vercel) | T1 | Static quiz page: consent step before any pixel, Turnstile, 3 questions from `offers.quiz_config`, `utm_content`/`fbclid` capture; Supabase Edge Function `/quiz` (role `app`, RPC insert into `leads` + `lead_contacts`, server-side CAPI `QuizStart`/`QuizComplete` with `event_id` dedup, no event without consent); Edge Function `/cal-webhook` (signature-verified) setting `booked_verified_at` and firing `Schedule`; `scripts/test_events.py` | FR-32 to FR-35; Events Manager test tool green with dedup; forged webhook rejected and logged; a submission without consent writes no CAPI event |
| T8 | Executor | T1 | `scripts/apply_actions.py` exactly per `SKILL.md` §6: advisory lock, pause re-check, `check_daily_cap()`, rate limits from config, `applying` before any external call, name lookup before every Meta create, external ids written immediately, `applied` only after read-back, `--reconcile` mode; `scripts/decide.py` writing approvals with `decision_channel='chat'`; Meta calls only in this file | FR-44 to FR-47; two concurrent executors apply each action once (test with a fake Meta client); a crash after create leaves no orphan on re-run; grep for Meta write endpoints outside this file returns nothing |
| T9 | Launcher | T6, T7, T8 | `scripts/meta_launch.py`: writes one proposed `build_campaign` action whose `proposal` describes one `new_recipes` campaign, 3 ad sets at €10/day, 6 paused ads, `QuizStart` optimisation, `utm_content=creative_id` URLs; validator refuses ad sets mixing renderers or exceeding `daily_cap`; executor path for `build_campaign` and `activate` in T8's file | FR-30, FR-31, FR-32, FR-37; running it twice yields one action (proposal_key); after `apply actions` the objects exist in Ads Manager paused and `ad_entities`/`campaigns` carry external ids |
| T10 | Loop | T9 | `scripts/meta_insights.py`: ad-level daily → `ad_metrics_daily` (append, `fetched_on`), account-level hourly → `account_spend_hourly`, lever selection from config floors → `campaigns.active_lever` + reason, kill/scale from `mart_kill_scale_candidates` → proposed actions with `evidence`, learnings only through the FR-41 gates, `cpl_target` derivation stub | FR-38 to FR-41; restated day yields two rows and one latest; `config_missing` is a hard stop; no agent learning without a creative at sample size |
| T11 | Check-in + routines | T10 | `scripts/checkin.py`: five parts in order, email via the Gmail connector, golden-file test; `scripts/pause.py`; routine definitions from `SKILL.md` §8 registered; SessionStart hook (use the `session-start-hook` skill) installing Chromium, Python deps, secrets | FR-42, FR-47, FR-48; a check-in email is received; the 08:00 routine fires once in dry-run |
| T12 | Skill finish + changelog | all | `SKILL.md` §3 table matches the scripts that exist; `references/prompts/<worker>.md` for each worker prompt used; `warehouse/schema-notes.md` listing any JSONB keys introduced; `CHANGELOG.md` | DoD `PLAN.md` §1 item 11; a fresh session invoking "where are we" works end to end |

Parallelism allowed: T2 ∥ T3 ∥ T7 ∥ T8 after T1. T5 needs my picks (stop point A). T9 needs my verdicts (stop point B) and my `activate` approval (stop point C).

## Constraints every subagent inherits (put these in every task prompt verbatim)

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

## Stop points (do not proceed past these without my reply)

- **A — after T4:** print the numbered proposal table and wait for `my picks: n, n, n`.
- **B — after T6:** print the numbered creative table with Storage URLs and hard-check results and wait for `verdicts: approve …; reject …: reason`.
- **C — after T9 proposes `build_campaign` and, later, `activate`:** print the proposal summary (campaign, ad sets, budgets, cap check result) and wait for `approve n`. Then run `apply actions`.
- **D — after T10's first insights pull:** show me the `where are we` table and the kill/scale view output, and ask me for the first `learnings` row text (`created_by='sam'`, `evidence.sample_reached=false`).

## Reviewer pass

After each task's commit, run a reviewer subagent with only the task's diff, the PRD rows it claims, and the constraints list. The reviewer checks: acceptance criteria actually tested, no Meta write outside the executor, role used correctly, `runs` row present, untrusted-text handling, no secrets, no binaries. A failed review sends the task back once; a second failure stops the orchestration and reports to me.

## Reporting

At each stop point and at the end, give me: tasks done with commit hashes, tasks blocked and the criterion that blocked them, the `where are we` table, and what I need to do next. Keep it under 30 lines.
