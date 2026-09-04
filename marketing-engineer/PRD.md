# PRD — Marketing Engineer Pipeline

**Version:** 1.0 · **Date:** 2026-09-02 · **Owner:** Sam (upClickLabs) · **Status:** Ready for build, pending six veto items (§12)
**Derived from:** `ARCHITECTURE.md` v1.1, `DECISIONS.md`, `CRUCIBLE.md`, `warehouse/schema.sql`, `warehouse/0002_roles.sql`, `PLAN.md` v1.1

---

## 1. Summary

An always-on, event-driven creative engine that replicates proven ads onto upClickLabs' offer, ships them to Meta, measures them against a per-campaign value model, and writes statistically gated learnings into a warehouse that compounds across clients. It acquires clients for upClickLabs first and is then pointed at those clients, using their own journey through the funnel as proof. Humans supervise at first; the machine earns autonomy per action type.

## 2. Problem

Creative testing is manual, unattributed, and forgetful. Each campaign starts from zero, winners cannot say *why* they won, and knowledge leaves with the person who ran it. At the same time, agencies are being replaced by "marketing engineers" who build agents that find customers, test ads, and get smarter weekly. upClickLabs needs that machine for itself before it can sell it.

## 3. Users

| Persona | Does | Must never have to |
|---------|------|--------------------|
| **Sam (operator)** | Picks recipes, gives verdicts, approves spend actions, reads the daily check-in and Monday memo, sets pause flags and account spending limits | Log into Ads Manager for routine work; read a raw table; give a verdict that takes more than seconds; approve the same thing twice |
| **Prospect (lead)** | Clicks an ad, answers a 3-question quiz, books a call | Be tracked before consent; be emailed without marketing consent; see their words quoted in an ad |
| **Client (tenant, week 2+)** | Sees funnel, creatives, and leads in the app; requests exports | Touch the database; see another client's rows or un-suppressed benchmarks |
| **Build agent** | Implements from this PRD, the schema, and `SKILL.md` | Call a Meta write endpoint outside the executor; hold vendor write keys in a worker |

## 4. Goals / Non-goals

**Goals**
- Close one honest loop for upClickLabs this weekend: ad live → metrics in warehouse → one learning row (§6 phase 0).
- Every shipped creative decomposed into components so performance attributes to ingredients, not ads.
- Every side effect routed through one executor enforced in Postgres, with graduated autonomy per action type.
- Cross-client learnings and benchmarks as the compounding asset.

**Non-goals (v1)**
- Video creative. Organic publishing metrics. Instantly nurture before ≥10 leads/week. Grok watchers before week 3. Client database access, ever. A single north-star metric across platforms. Per-client databases.

## 5. Success metrics

| Metric | Baseline | Target | Measured |
|--------|----------|--------|----------|
| Loop closed (ad live, metrics rows, ≥1 learning row) | no | yes | Sunday night |
| Creatives with full `creative_components` | 0 | 100% of shipped | every batch |
| Creatives reaching sample size (2,000 impressions) | 0 | ≥8 cumulative | week 4 |
| Learnings proposed / supported | 0 / 0 | ≥3 / ≥1 | week 4 |
| Cost per link click vs config floor | unmeasured | ≤ floor | week 4 |
| Verified bookings (calendar-API confirmed) | 0 | ≥5 cumulative | week 4 |
| Side effects outside the executor | n/a | 0 (trigger-enforced) | continuous |
| Approvals cast by non-human channels counted toward trust | n/a | 0 | continuous |
| Clients on the pipeline | 0 | 1 | week 4 |

## 6. Scope by phase

| Phase | Ships | Definition of done |
|-------|-------|--------------------|
| **0 — Weekend** | Warehouse (`0001` + `0002`), format library (24 patterns), VOC seed (15 phrases), planner (12 → Sam picks 3), producer (6 creatives, HTML + Playwright, one image model, 1080×1080), gate (fact checks + chat verdicts + shadow rubric), quiz page on `go.upclicklabs.com` with consent + CAPI, one `new_recipes` campaign (3 ad sets, `QuizStart`), executor with cap invariant, insights pull, check-in email via Gmail connector, one 08:00 routine, `SKILL.md` | `PLAN.md` §1 items 1–11 all true |
| **1 — Week 2** | Email review with POST-confirmed tokens; batch two on image-to-image renderer; first ablation/scaling campaign if a winner exists; embeddings refresh; `competitors`; client-scoped RLS (`0003`); first client onboarded; auto-pause on kill rule | A second tenant runs the same loop from a `clients` row |
| **2 — Week 3** | Reactor service in the app with `events`, coalescing, worker budgets; Grok competitor watch + trend mining; buying-trigger agent; Instantly nurture at ≥10 leads/week; hard qualification if data supports; organic via X API | An intel event triggers a batch without a scheduled wake |
| **3 — Week 4** | AEO pipeline tables in the warehouse; client dashboard; rubric regression v1; export tooling; video scripts | Articles and ads share ICPs, VOC, and learnings |

---

## 7. Functional requirements

### 7.0 Value model

- **FR-1** Each `campaigns` row MUST carry `terminal_metric` (default `booked_call`) and `optimisation_event` (Meta's event, default `QuizStart`) as separate fields. *Rationale:* Meta needs volume; we need bookings. **AC:** inserting a campaign without either fails; `terminal_metric` changes require `sam_admin`.
- **FR-2** The static-ad lever chain MUST be, in order: cost per link click → quiz-start rate → quiz-complete rate → booking rate → cost per booked call. CPM is reported as context. Hook rate applies only when `families.kind = 'video'`. **AC:** `campaigns.active_lever` ∈ that set for static campaigns.
- **FR-3** The loop MUST select the active lever by walking the chain top-down and stopping at the first lever below its benchmark at sample size, writing `active_lever_reason`. Benchmark resolution: own history → `mart_benchmarks` (≥3 clients) → config floor. **AC:** with only config floors, the reason string names the floor source.

### 7.1 Creative intelligence

- **FR-4** The intel worker MUST write every fetched payload to `raw_ingest` with `dedup_key` before normalising. **AC:** re-running a pull adds zero duplicate `raw_ingest` rows.
- **FR-5** Each `patterns` row MUST carry `family` (FK to `families`), `variant` (free text), `source_list`, `status` (`candidate` | `proven` | `retired`), `source_strength` (ordinal), `recipe.format_layer`, and `source_image_url` pointing at our Storage copy. **AC:** a pattern with a CDN `source_url` and no Storage copy is rejected by the worker's validator.
- **FR-6** `status='proven'` MUST require `start_date ≤ today − 30 days` or `concurrent_variants ≥ 3` from the same brand. **AC:** unit test on both branches.
- **FR-7** Seed order MUST be DTC testers first; category peers are consulted only after a family is retired for the ICP (3 creatives under floor at sample size), which writes a `learnings` row with scope `icp` and proposes `retire_family`. **AC:** the fourth creative of a retired family cannot be briefed.
- **FR-8** Every run MUST write a `runs` row with counts; zero new patterns is `status='ok'`; a failed source is retried once then written as a warning; two consecutive failures on one source MUST block the next batch until Sam acknowledges. **AC:** simulate two failures → planner refuses with the source named.
- **FR-9** (Phase 2) Grok watchers MUST run under a daily source/$ budget from client config and write raw events when the budget is exhausted without reasoning. **AC:** budget exhaustion shows in `runs.counts`.

### 7.2 Customer language

- **FR-10** Sources and weights: vault notes 3, quiz answers 2, public 1, stored in `voc_phrases.source_weight`. The vault is read-only to the worker. **AC:** no write path to the vault exists in code.
- **FR-11** Phrases MUST be anonymised at extraction (names, companies, identifying figures removed); the row stores `source_ref` (path or hashed URL) and never the source text; there is no quotes column. **AC:** schema has no `quotes`; a phrase containing a seeded fake name fails the validator.
- **FR-12** Vault-derived phrases MUST be `visibility='internal'` and MAY appear verbatim in a creative only after a `quote_release` action approved by `sam_admin`. **AC:** gate hard check fails on an internal phrase without an applied `quote_release`.
- **FR-13** Deduplication MUST be by `(source_ref, phrase_normalised)`. **AC:** unique constraint present.

### 7.3 Angle planner

- **FR-14** The planner MUST read `learnings`, `mart_component_leaderboard` (filtering `creatives ≥ 3`, ranking by `link_ctr_lcb`), config floors, `voc_phrases`, and `patterns` before proposing. **AC:** the planner's run log lists the queries executed.
- **FR-15** Capacity MUST be computed as `floor(daily_budget × 7 × 1000 / (cpm_estimate × kill_impressions))` and stored on `experiments.capacity`; a batch MUST NOT exceed it. **AC:** at €30/day and €25 CPM, capacity = 4; a 6-creative batch is refused unless `daily_budget ≥ 45`.
- **FR-16** A new batch MUST be requested only when in-flight creatives below sample size < capacity − batch_size (threshold event), never on a calendar. **AC:** with 4 in-flight sub-sample creatives and capacity 4, no batch is requested.
- **FR-17** The planner MUST propose 4× the batch's recipe count and record a `selections` row (proposed, chosen, rejected, reason, selected_by). Selection stays with Sam until the trust rule promotes it. **AC:** batch one has 12 proposed, 3 chosen.
- **FR-18** Translation MUST change only offer, product nouns, VOC phrases, imagery subject; `briefs.changed_ingredients` MUST be a subset of that set; the format layer is copied verbatim; the offer layer comes from `offers.offer_layer`. **AC:** a brief with `changed_ingredients` containing `copy_length` is rejected.
- **FR-19** An ablation brief MUST be created only when a replica is below the CTR floor at sample size, its source pattern is `proven`, and `changed_ingredients` has ≤3 entries; one ablation at a time; two creatives. **AC:** unit test on all three conditions.
- **FR-20** Until four `selections` rows exist, the ranker MUST be deterministic: source strength × family diversity. **AC:** same inputs → same order.

### 7.4 Creative producer

- **FR-21** Every creative MUST have `creative_components` rows for family, variant, hook, angle, template, renderer, image_model, voc_phrase (if any), cta, landing_page, offer. **AC:** gate hard check `components` fails otherwise.
- **FR-22** Phase 0 renderer is `html_template` via Playwright with one image model; `image_to_image` runs in phase 1 on the same recipes. In-batch renderer comparisons MAY use Meta's A/B tool only; two renderers MUST NOT share one ad set. **AC:** launcher validator rejects an ad set whose ads differ in `renderer`.
- **FR-23** Imagery MUST be generated (no stock); generated people are allowed; real-person likeness is a hard block; testimonial/quote families are hard-blocked unless the quote is a real client's with an applied `quote_release` and no depicted person. **AC:** gate `hard_checks.testimonial` present on every creative.
- **FR-24** All text MUST be overlaid in HTML by us; models generate text-free images. **AC:** image prompts contain the no-text instruction; a vision check flags rendered text in generated images.
- **FR-25** Assets MUST be stored in Supabase Storage and referenced from `creatives.asset_urls`; phase 0 size 1080×1080 only. **AC:** no binary in git.

### 7.5 Creative gate

- **FR-26** Fact checks MUST run on every creative and any failure blocks: Meta policy, brand hard blocks, likeness, testimonial, translation coherence (routes to planner), components, landing URL match, verbatim `public`/`inbound`/`internal` phrase without release. Results in `gate_scores.hard_checks`. **AC:** each check has a fixture that fails it.
- **FR-27** The rubric MUST score in `mode='shadow'` until promoted; Sam's verdict is written with `scored_by='sam'`, `decision_channel` ∈ {`chat`, `token_post`, `app`}. **AC:** no `agent` row has `mode='blocking'` in phase 0.
- **FR-28** (Phase 1) Email review: links MUST open a confirmation page that POSTs; one token per item; 72h expiry; spend-affecting approvals MUST require a magic-link session; approve URLs MUST NOT be posted to Slack; reply parsing MUST require DMARC pass and a matching `In-Reply-To` and MUST land as `feedback_trust='inbound'`. **AC:** a GET on a token changes nothing.
- **FR-29** Retry loop: fact-check fail → producer (or planner for coherence) with the feedback object; max 3 attempts; then dropped and logged. **AC:** attempt 4 is impossible.

### 7.6 Launcher, landing, tracking, nurture

- **FR-30** The launcher MUST NOT call Meta. It writes a `build_campaign` proposal; the executor creates campaign, ad sets, ads (paused) and writes external ids immediately after each create, with a name-based lookup before every create. **AC:** grep for Meta write endpoints outside the executor returns nothing; a crash mid-build leaves no orphan on re-run.
- **FR-31** Structure: one `new_recipes` campaign, one ad set per recipe, ≤3 ad sets at €30/day; `ablation` and `scaling` campaigns created on first need; broad targeting (geo + age); budget changes ≤20% steps; moving to scaling reuses `object_story_id` and pauses the origin ad in the same action. **AC:** launcher validator enforces ad-set count vs `daily_cap`.
- **FR-32** Ad URLs MUST carry `utm_content = creative_id`. **AC:** every `ad_entities` row's creative resolves from its URL.
- **FR-33** The quiz page MUST live on `go.upclicklabs.com`, show a consent step before any pixel or CAPI call, use Turnstile and per-IP rate limits, capture `utm`/`fbclid` (hashed), write `leads` + `lead_contacts` through an RPC as role `app`, and fire server-side CAPI with `event_id` dedup for `QuizStart`, `QuizComplete`. **AC:** Events Manager test tool green for all three events with dedup; a submission without consent writes no CAPI event.
- **FR-34** `Schedule` MUST fire only when `leads.booked_verified_at` is set from the calendar tool's authenticated API or a signature-verified webhook. **AC:** a forged webhook without signature is rejected and logged.
- **FR-35** Qualification is soft in month one: every completer may book; answers set `qualification_score`. Hard mode is a config switch enabled only after the warehouse shows which answers predict `closed_won`. **AC:** config flag default off.
- **FR-36** (Phase 2) Nurture via Instantly on lead-stage events only with `consent.marketing = true`, sequences nurture / reminder / rebook; starters never emailed; `push_to_instantly` is an action under the trust rule. **AC:** a lead without marketing consent never gets an `instantly_lead_id`.
- **FR-37** `ad_entities.review_status` MUST be synced from Meta; `DISAPPROVED` blocks `activate`; N disapprovals in 7 days (config) proposes `set_pause_flag`. **AC:** fixture with a disapproved ad → activate refused.

### 7.7 Performance loop

- **FR-38** Insights MUST be pulled ad-level daily into `ad_metrics_daily` keyed by `(ad, day, fetched_on)`; readers use `ad_metrics_latest`. Account-level spend MUST be pulled hourly into `account_spend_hourly`. **AC:** a restated day yields two rows and one latest.
- **FR-39** Kill/scale MUST be read from `mart_kill_scale_candidates`: `config_missing` when targets are unset; CTR-stage kill at sample size; conversion-stage kill only when spend ≥ 5 × `cpl_target` and verified bookings < expected/3; scale only on ≥5 verified bookings at ≤ `cpl_target`. Every recommendation becomes a proposed action with `evidence`. **AC:** the view's fixture set (config missing, hold, kill, scale) passes.
- **FR-40** `cpl_target` MUST be derived from the funnel after 100 link clicks and written to config with a floor; until then conversion-stage rules are advisory. **AC:** derivation function unit-tested.
- **FR-41** A `learnings` row MUST be written only when ≥50 clicks per arm, effect ≥0.3pp absolute or ≥30% relative, and `posterior ≥ 0.9`; tiers `proposed` → `supported` (replication or ablation) → `global` (≥3 clients). Rows below the gates are not written. Sam MAY write a `proposed` learning by hand with `evidence.sample_reached=false`. **AC:** a batch with no creative at sample size writes no agent learning and raises the "zero learnings" warning only if a creative reached sample size.
- **FR-42** The daily check-in MUST contain exactly five parts in order: actions waiting (with reasons), actions taken, active lever per campaign, new learnings, warnings; delivered by email through the Gmail connector; Slack carries only the count. **AC:** golden-file test on the email body.
- **FR-43** The Monday memo MUST contain: learnings promoted/refuted, taste-vs-market report, variant→family promotion proposals, JSON keys due for column promotion, and the next batch's proposals. **AC:** template sections present.

### 7.8 Orchestrator and executor

- **FR-44** Workers MUST only insert `actions` with `status='proposed'`; the executor alone transitions them; `promote_trust`, `quote_release`, `set_pause_flag` MAY be approved only by `sam_admin`. **AC:** `0002` guard tests (worker transition, worker non-proposed insert, executor promote) all raise.
- **FR-45** Before any side effect the executor MUST: take `pg_advisory_xact_lock`, re-check `clients.paused` and the global flag, evaluate `check_daily_cap()` for budget-affecting actions, move the action to `applying` with `executor_run_id`, perform the external call, read the object back, then mark `applied`. Stuck `applying` older than N minutes MUST be reconciled against Meta, never re-sent. **AC:** two concurrent executors apply each action once.
- **FR-46** Trust MUST be computed from `trust_streaks` (human channels only, `approved_payload = proposal`, reset on rejection); `activate` counts per batch; `kill` promotion additionally requires back-test accuracy ≥80%; promoted types are rate-limited (config: max kills/day, ≤50% of live ads/day, one scale per ad per 72h) and demoted on any executor failure. **AC:** an auto decision never increments a streak (verified).
- **FR-47** Brakes: `clients.paused` and a global env flag; auto-propose `set_pause_flag` on 3 consecutive failures of one action, on worker error rate spike (config), on lead velocity >3× 7-day median, and on hourly spend > cap; the Meta account spending limit is set by Sam's admin, not by the system user. **AC:** each trigger has a fixture.
- **FR-48** Phase 0 reactor stand-in: two fixed wakes (08:00, 20:00), fresh-session mode, SessionStart hook for Chromium/Python/secrets, no session-bound webhooks; Edge Functions write to the warehouse. Phase 2 replaces it with the app service and `events`. **AC:** routine definitions checked into `SKILL.md`.
- **FR-49** Model per task: Claude for planning, copy, gate; Grok (phase 2) for watchers only; image models per config. **AC:** worker code has no hard-coded vendor for a task that config governs.

## 8. Data requirements

- **DR-1** `warehouse/schema.sql` (0001) and `warehouse/0002_roles.sql` are the source of truth; they apply cleanly on Postgres 16 and Supabase; changes are numbered migrations only.
- **DR-2** Must exist and be populated from batch one: `raw_ingest`, `patterns.recipe`, `families`, `voc_phrases`, `experiments.capacity`, `briefs.source_pattern_id/changed_ingredients/kind`, `selections`, `creatives`, full `creative_components`, `gate_scores.scored_by/verdict/mode/decision_channel`, `campaigns`, `ad_entities` ↔ `creative_id`, append-only `ad_metrics_daily`, `leads.consent`, `actions` with `proposal_key`/`evidence`, `runs`, `learnings`.
- **DR-3** Schema growth rule: raw → JSONB key documented in `warehouse/schema-notes.md` → column via migration once read by a second worker or a mart.
- **DR-4** PII lives only in `lead_contacts` (column grants) and `leads.quiz_answers/consent/fbclid_hash` (revoked from `mcp_ro`); `raw_ingest.purge_after` 90 days for PII sources; `leads.purge_after` 24 months post-activity; `erasure_requests` fan-out to Storage, Instantly, Meta audiences, backups.
- **DR-5** Every ingested text row carries `trust_tier`; marts are `security_invoker`; `mart_benchmarks` suppresses groups under 3 clients.
- **DR-6** Deferred tables with reserved names: `events`, `review_tokens`, `competitors`, `benchmarks`, `trust_levels`, `pause_flags` (the last two live in `clients.config`/`clients.paused` until needed).

## 9. Non-functional requirements

- **NFR-1 Security:** vendor write keys (Meta, Instantly, Typefully) exist only in the executor process; workers connect as `worker_rw`; Claude sessions and the Postgres MCP as `mcp_ro`; quiz app as `app`; secrets in the host secret store or Supabase Vault; rotate the Meta token on any suspected injection.
- **NFR-2 Prompt-injection boundary:** untrusted text (`public`, `inbound`, `client` tiers) is passed to models only inside delimited data blocks with a fixed system prompt; outputs are schema-validated JSON; emails escape all content and carry no URLs from rows below `owned`.
- **NFR-3 Privacy:** Supabase EU region; consent before pixel/CAPI/marketing; DPAs with Supabase, Anthropic, Google (image), scrapecreators, Vercel before phase 0; Instantly and xAI before they enter; Meta Data Processing Terms accepted; verbatim customer words never in an ad without release.
- **NFR-4 Reliability:** every worker invocation writes a `runs` row; idempotent re-runs from `raw_ingest`; actions idempotent via `proposal_key`; Meta creates preceded by name lookup; insights via async jobs with backoff on throttle headers.
- **NFR-5 Cost:** machine budget staged (phase 0 ≈ $100/month; cap decision in §12); per-worker daily token/API budgets from phase 2; two model wakes per day in phase 0.
- **NFR-6 Observability:** `runs`, `actions`, `account_spend_hourly`, and the daily check-in are sufficient to answer "what did the system do since yesterday and why" without reading logs.
- **NFR-7 Meta account hygiene:** one ad account per client; system user on Advertiser role; account spending limit set by hand; ad account with spend history for phase 0; Standard Access review submitted before phase 1.

## 10. Dependencies

| Dependency | Needed by | Owner | Notes |
|------------|-----------|-------|-------|
| Meta app, system user (Advertiser), assets, token; domain verified; events + CAPI token; spending limit | Phase 0 Friday | Sam | UI-only steps documented in `references/meta-launch-playbook.md` as performed |
| Ads Management Standard Access review | Phase 1 | Sam | multi-week; submit Friday |
| Supabase project (EU), pgvector, Storage, pooler string | Phase 0 Friday | Sam | apply `0001` + `0002` |
| `go.upclicklabs.com` on Vercel; Cal.com | Phase 0 Friday | Sam | separate repo for the app |
| scrapecreators key + verified field names/cost | Phase 0 Friday | Sam | one real call saved |
| Gemini image API key | Phase 0 Friday | Sam | other models later via config |
| `references/families.md`, DTC seed list, client config, vault seed | Phase 0 Friday | Sam | 30 minutes, before code |
| Gmail connector (check-in sender) | Phase 0 | existing | transactional sender in phase 1 |
| Instantly, xAI, X API, Typefully | Phases 2–3 | Sam | not before the gates in §6 |

## 11. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Meta account restriction on first launch | medium | high | spend-history account, Advertiser role, ≤6 ads, policy fact check, review submitted |
| Sub-sample numbers mistaken for results | high | medium | FR-41 gates, LCB ranking, `sample_reached=false` on the first learning |
| Executor bug spends money | low | high | FR-44–47, cap invariant, spending limit, prepaid card |
| Injection through ingested text | medium | high | NFR-1, NFR-2, trust tiers |
| Weekend scope slips | medium | medium | cut line is the scope; every deferred item has a slot |
| Sam is a serial dependency | medium | medium | Friday pre-writes; 10–20 minute chat slots with defaults |
| GDPR complaint or erasure request | low | high | DR-4, NFR-3 |

## 12. Open questions

**Awaiting Sam's veto (defaults stand until vetoed):**
- V1 Batch size from capacity (3 recipes at €30/day) vs raising budget to ~€90/day.
- V2 `QuizStart` optimisation for testing ad sets.
- V3 Renderer and image model as between-batch factors.
- V4 Chat verdicts in phase 0; email review in phase 1.
- V5 Testimonial families blocked.
- V6 Machine budget cap: ~$500/month or slower cadence.

**Other (owner, deadline):** calendar tool confirmation (Sam, Fri); vault note convention and seed (Sam, Fri); image-model shortlist beyond Gemini (Sam, phase 1); ablation margin and conversion-stage sample sizes (tune after batch 2); Monday memo timing (Sam, U4); export format (phase 1); `events` partitioning (phase 2); error-spike definition (phase 1); app hosting for the reactor (phase 2).

## 13. Appendix — requirement to source map

| IDs | Source |
|-----|--------|
| FR-1–3 | DECISIONS C0, C7; CRUCIBLE A5, V2 |
| FR-4–9 | DECISIONS C1; CRUCIBLE A19, A20 |
| FR-10–13 | DECISIONS C2; CRUCIBLE A13, A15 |
| FR-14–20 | DECISIONS C3; CRUCIBLE V1, A6–A9, A21 |
| FR-21–25 | DECISIONS C4; CRUCIBLE V3, V5, A19 |
| FR-26–29 | DECISIONS C5; CRUCIBLE V4, A15 |
| FR-30–37 | DECISIONS C6; CRUCIBLE V2, A10–A13, A16 |
| FR-38–43 | DECISIONS C7; CRUCIBLE A4, A8, A17 |
| FR-44–49 | DECISIONS C9; CRUCIBLE A1–A3, A11, A14, A23 |
| DR-1–6 | `warehouse/schema.sql`, `0002_roles.sql`; DECISIONS C8; CRUCIBLE A18, A20 |
| NFR-1–7 | CRUCIBLE A1, A11, A13, A15, A16, V6 |
