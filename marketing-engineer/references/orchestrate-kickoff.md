# Kickoff — Marketing Engineer Pipeline, phase 0 build

Three messages drive the build with Matt Pocock's skills, which are enabled for this repo through `.claude/settings.json`. There is no `orchestrate` skill in that set; the flow is **`to-tickets`** (spec → tracer-bullet tickets with blocking edges) then **`implement`** (one ticket per fresh context, test-first, reviewed, committed).

Prerequisite: **none in dev mode.** Phase 0 is built against local Postgres and fake backends per `references/dev-mode.md`; the Friday checklist in `CRUCIBLE.md` §4 is needed only for the go-live swap. Start a new session on `samupclick/claude-skills` from `main`.

- **Message 1** creates the tickets. Send once.
- **Message 2** implements one ticket. Send once per ticket, in dependency order, in a fresh session or after `/clear`.
- **Message 3** is what you reply at the four stop points.

---

## Message 1 — set up the tracker and create the tickets

```
If `docs/agents/issue-tracker.md` does not exist, run /mattpocock-skills:setup-matt-pocock-skills first.
Choose the LOCAL MARKDOWN tracker under `.scratch/` (this session has no `gh` CLI), feature name
`marketing-engineer-phase0`, and accept the defaults for everything else.

Then run /mattpocock-skills:to-tickets on the spec at marketing-engineer/PRD.md, phase 0 only
(PRD §6 row "0 — Weekend", FR-1 to FR-49, DR-1 to DR-6, NFR-1 to NFR-7), with the following as
the DRAFT BREAKDOWN for your step 3. Do not re-derive the slices; present these twelve as the
proposed tickets with their blocking edges and quiz me on granularity and edges as the skill
requires. Each ticket body must carry, verbatim: its Deliverable, its Acceptance, the Constraints
block below, its blocking edges, and its stop-point marker if it has one. Do not publish until I
approve the breakdown.

Read first, yourself, before drafting: marketing-engineer/PRD.md, marketing-engineer/SKILL.md,
marketing-engineer/warehouse/schema.sql, marketing-engineer/warehouse/0002_roles.sql,
marketing-engineer/CRUCIBLE.md §3–4, marketing-engineer/PLAN.md §1–4. Precedence when documents
disagree: schema → PRD → ARCHITECTURE → CRUCIBLE → DECISIONS. PLAN.md is the schedule only.

Goal of phase 0: close one honest loop for the `upclicklabs` client — ad live → metrics rows in the
warehouse → one learning row — per PLAN.md §1 items 1–11. Sub-sample numbers are expected.

DEV MODE: we are building before the Friday checklist is done. Read marketing-engineer/references/dev-mode.md.
Every external service sits behind an adapter chosen by an env var; the fake backends and fixtures are
part of the build, not a shortcut. Add a ticket T0 "Dev harness" that blocks T1: `scripts/dev_db.sh`
(local Postgres, apply 0001 + 0002, create the five roles with dev passwords), the adapter interfaces
and their fake/local/fixture implementations for storage, Meta, CAPI, inspo, image, model, email,
Turnstile, plus `.env.example` loading and `fixtures/ad_library/` with an assumed-shape sample. Every
later ticket uses the adapters and never imports a vendor SDK directly. The placeholder files
(config/clients/upclicklabs.json, references/families.md, the voc-seed notes) are DRAFTS marked as
such; build against them as they are and do not invent real-looking values. "Ad live" in dev mode
means live in the fake Meta account with synthesised insights; the go-live swap in dev-mode.md §
"Go-live swap checklist" is a separate, later ticket T13 that stays blocked until Sam clears it.

### Draft breakdown (tracer-bullet tickets)

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

Parallelism: T0 first; T1 after T0; T2, T3, T7, T8 are unblocked once T1 lands. T5 carries stop point A, T6 stop point B,
T9 stop point C, T10 stop point D.

### Constraints (copy into every ticket body verbatim)

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

### Stop points (mark the ticket; the implementer must stop and wait for my reply)

- A — T4 done: print the numbered proposal table; wait for `my picks: n, n, n`.
- B — T6 done: print the numbered creative table with Storage URLs and hard-check results; wait for
  `verdicts: approve …; reject …: reason`.
- C — T9 proposes `build_campaign`, and later `activate`: print the proposal summary (campaign,
  ad sets, budgets, cap check result); wait for `approve n`; then run `apply actions`.
- D — T10's first insights pull: show the `where are we` table and the kill/scale view output;
  ask me for the first `learnings` row text (`created_by='sam'`, `evidence.sample_reached=false`).

When the tickets are published, reply with the ticket list in dependency order, each with its
path under `.scratch/`, and tell me which ones are unblocked right now.
```

---

## Message 2 — implement one ticket (repeat per ticket, fresh context each time)

Replace `<TICKET>` with the ticket's path under `.scratch/marketing-engineer-phase0/`.

```
/mattpocock-skills:implement <TICKET>

Before writing code: confirm every ticket this one is blocked by is closed (its file says done and
its commit is on the branch); if not, stop and tell me which. Load `.env` (dev mode per
marketing-engineer/references/dev-mode.md; start the local Postgres with `scripts/dev_db.sh` if it
is not running). Print the "where are we" query from marketing-engineer/SKILL.md §2 against the warehouse.

Work test-first with /mattpocock-skills:tdd at the seams the ticket names. Tests run against a
local Postgres with warehouse/schema.sql and warehouse/0002_roles.sql applied; do not mock the
warehouse. Follow the Constraints block in the ticket verbatim. Every script opens and closes a
`runs` row; prove it with a real invocation and paste the row.

Finish with /mattpocock-skills:code-review against the merge-base of this ticket's work, scoped to:
acceptance criteria actually tested, no Meta write outside scripts/apply_actions.py, correct DB role,
`runs` row present, untrusted text handled as data, no secrets, no binaries. Fix what it finds, then
commit once on the current branch with a message ending in the FR ids satisfied, and push. Mark the
ticket done in `.scratch/`.

If the ticket carries a stop point, stop there, print exactly what the stop point asks for, and tell
me the reply format you expect. Do not continue past it.

If an acceptance criterion cannot be met, stop and report which one and why. Never narrow it.

Report in under 20 lines: what shipped, commit hash, acceptance criteria with pass/fail, the `runs`
row, and which tickets are now unblocked.
```

---

## Message 3 — my replies at the stop points

| Stop | I send |
|------|--------|
| A | `my picks: 2, 5, 9` (optionally `: reason` after a number) |
| B | `verdicts: approve 1,3; reject 2: hook is generic; reject 5: looks like stock` |
| C | `approve 1` then, when asked, `apply actions` |
| D | the learning text, e.g. `learning: screenshot family replicated cleanly onto the audit offer; no signal yet` |

Default if I go quiet for 20 minutes: A takes the ranker's top three; B ships nothing; C does nothing; D writes no row. The implementer must say which default it took.

---

## After phase 0

`marketing-engineer/PRD.md` §6 rows 1–3 are the next specs. Run Message 1 again per phase with the relevant FR ids, and let `to-tickets` derive the slices itself; the draft breakdown above is phase 0 only.
