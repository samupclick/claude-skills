# Marketing Engineer Pipeline — High-Level Architecture

**Status:** v1.1, consolidated from `DECISIONS.md` (components 0–9) and amended by `CRUCIBLE.md` on 2026-09-02. This is the document a build agent implements from. `warehouse/schema.sql` + `0002_roles.sql` are the data source of truth, `PLAN.md` the schedule, `DECISIONS.md` the reasoning, `CRUCIBLE.md` the amendments; the six veto items V1–V6 were resolved by Sam on 2026-09-02 (V1–V5 accepted, V6 cap raised to ~$500/month).

---

## 1. What it is

An always-on, event-driven creative engine that acquires clients for upClickLabs first and is then pointed at those clients. It replicates proven ads onto our offer, ships them to Meta and organic channels, measures them against a per-campaign value model, and writes structured learnings into a warehouse that compounds across clients. Humans supervise at first; the machine earns autonomy per action type.

**Non-negotiables**

1. Facts always block (policy, brand, likeness, coherence, tracking). Taste starts with Sam and is learned.
2. No side effect without the executor. Workers propose; one executor applies under the trust rule. **Enforced in Postgres** (roles + `actions_guard` trigger), not in prose; the Meta write token exists only in the executor process.
3. Every creative is decomposed into components. No attribution key, no ship.
4. Read learnings before planning; write learnings after measuring. Zero learnings at sample size is a warning.
5. Nothing lives only in a file. Warehouse is the system of record; git holds code, prompts, schema, and rendered memos.
6. The runtime is ours. Models are workers.
7. **Batch size is derived from impressions, not ambition.** Capacity = `floor(daily_budget × 7 × 1000 / (cpm × kill_impressions))`; a batch never exceeds it.
8. **Money signals must be verified.** Scale and conversion-stage kills use warehouse-verified bookings, never Meta-reported leads.
9. **Ingested text is untrusted.** Every row carries a `trust_tier`; models receive it as delimited data and return schema-validated JSON.

---

## 2. System diagram

```
                     ┌──────────────────────────────────────────────────────────────┐
   EXTERNAL          │                    OUR PLATFORM  (go.upclicklabs.com)         │
                     │                                                              │
 Meta Ad Library ──┐ │  ┌────────────── ORCHESTRATOR (reactor) ──────────────────┐  │
 TikTok / IG  ─────┼─┼─▶│  events ─▶ coalesce ─▶ dispatch ─▶ workers ─▶ proposed │  │
 X feed (Grok) ────┘ │  │                                        actions         │  │
                     │  │                                           │            │  │
 Obsidian vault ─────┼─▶│  ┌──────────── WORKERS ────────────┐      ▼            │  │
 Reddit/G2/Clutch ───┼─▶│  │ 1 creative-intel   (Grok)       │  ┌─────────┐      │  │
                     │  │  │ 2 customer-language (Claude)    │  │EXECUTOR │──────┼──┼──▶ Meta Marketing API
 Meta Insights ──────┼─▶│  │ 3 angle-planner    (Claude)     │  │ trust   │      │  │    Typefully (organic)
 Quiz / leads ───────┼─▶│  │ 4 creative-producer(Claude+img) │  │ rule +  │──────┼──┼──▶ Instantly (nurture)
 Instantly replies ──┼─▶│  │ 5 creative-gate    (Claude+Sam) │  │ brakes  │      │  │    Email (reviews, check-in)
                     │  │  │ 6 launcher                      │  └────┬────┘      │  │
                     │  │  │ 7 performance-loop              │       │           │  │
                     │  │  └─────────────┬───────────────────┘       │           │  │
                     │  └────────────────┼───────────────────────────┼───────────┘  │
                     │                   ▼                           ▼              │
                     │  ┌──────────────── GROWTH WAREHOUSE (Supabase) ───────────┐  │
                     │  │ raw_ingest · events · clients · offers · icps           │  │
                     │  │ voc_phrases · patterns(recipes) · families · hooks      │  │
                     │  │ experiments · briefs · selections · creatives           │  │
                     │  │ creative_components · gate_scores · review_tokens       │  │
                     │  │ campaigns · ad_entities · ad_metrics_daily              │  │
                     │  │ posts · post_metrics_daily · leads · benchmarks         │  │
                     │  │ actions · trust_levels · pause_flags · learnings        │  │
                     │  │ marts: component/hook leaderboards, benchmarks, funnel  │  │
                     │  └────────────────────────────────────────────────────────┘  │
                     │                                                              │
                     │  APP SURFACES: quiz funnels · review page · client dashboard │
                     └──────────────────────────────────────────────────────────────┘
                                              ▲
                                     Sam: email check-in (daily), review emails,
                                          Monday memo, pause flag
```

---

## 3. The loop, end to end

| Step | Worker | Trigger (event) | Reads | Writes | Human touch |
|------|--------|-----------------|-------|--------|-------------|
| Intel | creative-intel | scrapecreators pull (weekend); Grok watcher findings (wk 2) | seed brand lists, families | `raw_ingest`, `patterns` (full recipe, `family`+`variant`, `source_list`, `status`), `intel_runs` | approve variant→family promotions (Monday) |
| Language | customer-language | vault change, quiz submit, watcher finding | vault notes, public sources | `voc_phrases` (verbatim, tagged, weighted, anonymised, `visibility`) | `quote_release` for internal phrases |
| Plan | angle-planner | `capacity_freed` (in-flight below sample < capacity − batch), ablation triggered | `learnings`, leaderboards (LCB-ranked, ≥3 creatives), config floors, VOC, patterns | `experiments` (with `capacity`), 4× `briefs` (replicas w/ `changed_ingredients`), `selections` | **picks N of 4N** (N = capacity/2) until promoted |
| Produce | creative-producer | briefs selected | briefs, brand kit, templates | `creatives` ×2 per recipe (one renderer per batch), `creative_components`, assets in Storage | none |
| Gate | creative-gate | creatives ready | policy, brand, source ad | `gate_scores` (agent shadow + Sam verdict) | **approve/reject in chat** (weekend) → email with POST-confirmed links (week 2) until promoted |
| Ship | launcher | creatives approved | campaigns, offer, quiz config | proposed `build_campaign` → executor creates `campaigns`, `ad_entities` (paused); proposed `activate` | activate (trust rule, cap invariant) |
| Measure | performance-loop | insights arrival, sample_size_reached | `ad_metrics_latest`, verified bookings, config floors, value model | `ad_metrics_daily` (append, restatements by `fetched_on`), `account_spend_hourly`, `campaigns.active_lever`, proposed kill/scale `actions`, `learnings` (statistically gated) | approve kill/scale until promoted |
| Close | launcher (nurture) | lead stage events | leads | proposed `push_to_instantly`, `leads.stage` from replies | approve until promoted |
| Learn | performance-loop | Monday | everything | Monday memo, promotions proposed, next batch requested | reads memo, picks recipes |

---

## 4. Component summaries

### 0. Value model
Per campaign: a **terminal metric** fixed at launch (booked call, measured in the warehouse) and a **lever chain** per platform. For static ads on Meta: **cost per link click → quiz-start rate → quiz-complete rate → booking rate → cost per booked call**. CPM is context reported alongside, not a lever. Hook rate is rung zero only for video families. The loop works the first lever below benchmark at sample size. Terminal metric changes need a human. **Meta's optimisation event is a separate setting** (`campaigns.optimisation_event`, `QuizStart` for testing ad sets) and is promoted as volume allows; it never redefines the terminal metric.

### 1. Creative intelligence
Three sub-workers: format library (weekend, scrapecreators), competitor watch and trend mining (week 2, Grok). Seed: best DTC testers; category peers as fallback after a family fails in-niche (3 creatives under floor). Two-level taxonomy: fixed **families** (attribution key) + free **variants** (exploration); variants promoted at the Monday memo. **Proven** = ≥30 days running or ≥3 concurrent variants. Every run logs counts; empty is valid; two consecutive source failures block the batch.

### 2. Customer language
Sources: Obsidian vault (weight 3) → quiz answers (2) → Reddit/Quora, G2/Clutch, LinkedIn/X replies (1). Unit: verbatim phrase, tagged pain/outcome/objection/identity/trigger. Anonymised at extraction; pointer to source only; vault phrases `internal` and quotable only with a `quote_release`. Event-driven per source; deduplicated by source pointer.

### 3. Angle planner
**Replicate then ablate.** Unit is the *recipe*, split into a **format layer** (family, visual structure, copy structure, copy length, hook type) carried exactly from DTC sources, and an **offer layer** (offer mechanic, proof type, CTA mechanic) fixed per offer from `offers.offer_layer` or category peers. Translation may change only offer, product nouns, VOC phrases, imagery subject, and records `changed_ingredients`. Attribution and ablation operate on the format layer. Ablation triggers when a replica is below the CTR floor at sample size **and** the recipe is proven **and** ≤3 ingredients changed; one ablation at a time, two creatives. Source strength is ordinal, for ranking only; there is no implied source benchmark. Coherence check routes back to the planner. Planner proposes 4× capacity, Sam picks (batch one: 3 of 12); selections train the ranker; deterministic ranker (source strength × family diversity) until four batches of selections exist. Spend: 100% new recipes until the first ablation exists, then 70/30. A new batch is requested when capacity frees, not on a calendar.

### 4. Creative producer
Two renderers, both built, compared **between batches**: batch one = HTML family templates via Playwright with one image model; batch two = image-to-image from the source ad with a fidelity check on the same recipes. In-batch renderer comparisons only through Meta's A/B tool, never two ads inside one ad set. Imagery generated by best-in-class models only (config value); no stock; generated people ok, real likeness blocked; **testimonial/quote families blocked** unless the quote is a real client's with a `quote_release` and no depicted person. **Text is always ours**, overlaid in HTML. Source images are copied to Storage at ingest (CDN URLs expire). Copy per direct-response rules and translation discipline. Organic posts share recipes and hooks (publishing deferred). Full `creative_components` (family, variant, hook, angle, template, renderer, image_model, voc_phrase, cta, landing_page, offer) or no ship.

### 5. Creative gate
Facts block automatically: Meta policy, brand hard blocks, real-person likeness, fabricated testimonial, translation coherence, missing components, landing mismatch, verbatim `public`/`inbound`/`internal` phrase without release. Taste is Sam's verdict: **in chat this weekend**, by **email from week 2** (inline creatives; links open a confirmation page that POSTs; one token per item, 72h expiry; spend-affecting approvals behind a magic-link session; never in Slack; reply parsing requires DMARC + `In-Reply-To` and lands as untrusted feedback). The model rubric scores in shadow mode and is promoted to blocking when it agrees with Sam at the configured rate over only human-channel decisions. Taste is corrected by the market in the Monday memo; rubric dimensions regressed on CTR quarterly.

### 6. Launcher
Meta per offer: a **new-recipes** campaign with one ad set per recipe (own budget, ≤3 ad sets at $30/day); the **ablation** and **scaling** (CBO) campaigns are created when the first ablation or proven winner exists. Broad targeting. Testing ad sets optimise for **`QuizStart`**; `QuizComplete` when an ad set exceeds ~30/week; `Schedule` only in the scaling campaign. Budget moves in ≤20% steps; `object_story_id` reused when moving to scaling; origin ad paused in the same action. `review_status` synced from Meta; a disapproval blocks `activate`; N disapprovals in 7 days pauses the client. The launcher **proposes** `build_campaign`; the executor creates the objects. **Quiz funnel on our platform** (`go.upclicklabs.com`, separate repo), first-party pixel + server-side CAPI with `event_id` dedup, consent step before any pixel fires, Turnstile + rate limits, `utm_content = creative_id`, soft qualification with a score in month one. `Schedule` fires only on a booking verified through the calendar tool's API (`leads.booked_verified_at`). Nurture via Instantly on lead-stage events once leads exist (nurture / reminder / rebook), marketing consent required; starters never emailed. Organic publishing deferred.

### 7. Performance loop
Benchmarks per lever resolved: own history → cross-client mart (≥3 clients) → config floor. Chain walked top-down; first lever below benchmark becomes the active lever. Kill/scale under the trust rule with evidence snapshots: CTR-stage kill per ad at sample size; conversion-stage kill only when expected bookings ≥5 and observed < expected/3; scale only on ≥5 verified bookings at or under `cpl_target`, which is derived from the funnel after 100 clicks. Missing config is `config_missing`, never a default. Learnings need statistics: ≥50 clicks per arm, effect ≥0.3pp or ≥30% relative, posterior ≥0.9; tiers proposed → supported (replication or ablation) → global (3 clients); below the gates = zero weight. Leaderboards rank by lower confidence bound and hide levels under 3 creatives. **Daily check-in** by email via the Gmail connector: actions waiting, actions taken, active levers, new learnings, warnings. Monday memo: promotions, taste-vs-market, next batch.

### 8. Growth warehouse
Supabase Postgres (EU region) + pgvector + Storage. Clients see the app, never the DB; exports on request; benchmarks are ours by contract and suppressed under 3 clients. PII isolated in `lead_contacts` with column grants; consent on every lead; retention and erasure fan-out (`erasure_requests`); DPAs with every processor; Meta Data Processing Terms accepted. Every ingested row carries `trust_tier`. Views are `security_invoker`. Schema growth: raw → JSONB (documented) → column (migration) once read twice. Migrations only.

### 9. Orchestrator
Our runtime. From week 3 a reactor consumes `events`, coalesces, dispatches to workers with daily budgets. **Grok is the watcher (week 2); Claude plans, writes, gates; image models draw.** Single executor applies proposed actions under per-action-type trust levels computed from `trust_streaks` (human decisions only, unchanged payload, reset on rejection; `activate` counted per batch; `kill` also needs ≥80% back-test accuracy); promotions are Sam-only actions enforced by trigger; autonomous actions are rate-limited and demoted on any executor failure. Concurrency: advisory lock per executor run, `for update skip locked`, `applying` written before any external call, `applied` only after reading the object back from Meta, stuck `applying` reconciled never re-sent. Brakes: (1) the cap invariant `check_daily_cap()` before every create/activate/scale; (2) `clients.paused` + global env flag, re-checked inside the applying transaction; (3) hourly account-level spend pull; (4) auto-pause on 3 failures / error spike / lead velocity >3× median; (5) one ad account per client, system user on Advertiser role, account spending limit set by Sam's admin, prepaid card. Weekend stand-in: two fixed Claude Code wakes per day (08:00, 20:00), fresh session, SessionStart hook, no session webhooks (Edge Functions write to the warehouse). App service in week 3.

---

## 5. Trust ladder (graduated autonomy)

| Action type | Starts as | Promoted after (default) | Who promotes |
|-------------|-----------|--------------------------|--------------|
| recipe selection (planner picks) | Sam picks | planner top-N matches Sam's picks ≥80% over 4 batches | Sam |
| taste gate (rubric blocks) | Sam verdicts | agent verdict agrees with Sam ≥85% over 40 creatives, human-channel only | Sam |
| build_campaign | propose | 10 unchanged approvals (per batch) | Sam |
| activate campaign / ad | propose | 20 unchanged approvals, **counted per batch** | Sam |
| kill | propose | 10 unchanged approvals **and** back-test accuracy ≥80% | Sam |
| scale / move to scaling campaign | propose | 20 unchanged approvals | Sam |
| publish organic post | propose | 20 unchanged approvals | Sam |
| push lead to Instantly | propose | 20 unchanged approvals | Sam |
| quote_release (internal / public verbatim) | Sam only | never auto | — |
| set_pause_flag, promote_trust | Sam only | never auto (trigger-enforced) | — |

Streaks are the `trust_streaks` view over `actions`: only `decision_channel in (chat, token_post, app)`, only `approved_payload = proposal`, reset at the last rejection. Auto-applied actions never count. Even when promoted: max kills per day, never >50% of live ads in one day, one scale per ad per 72h; any executor failure demotes the type to `propose`.

---

## 6. Event catalogue (v1)

`intel_finding`, `pattern_added`, `vault_note_changed`, `voc_extracted`, `batch_requested`, `briefs_proposed`, `selection_made`, `creatives_rendered`, `review_ready`, `verdict_received`, `creatives_approved`, `campaign_built`, `action_proposed`, `action_applied`, `quiz_start`, `quiz_step`, `quiz_complete`, `lead_booked`, `lead_no_show`, `lead_stage_changed`, `insights_arrived`, `sample_size_reached`, `lever_changed`, `learning_proposed`, `checkin_sent`, `pause_set`, `worker_failed`.

Coalescing window 15 minutes per `(source, entity_ref)`; lifecycle types (`lead_*`, `verdict_received`, `pause_set`) are never coalesced; `quiz_step` is sampled at the app. Each worker has a daily token and API-call budget in client config. **The `events` table and reactor land in week 3**; until then routines poll the entity tables directly.

---

## 7. What ships this weekend vs later

The weekend scope is the **cut line in `CRUCIBLE.md` §3** (6 creatives, one renderer, one image model, one campaign, chat verdicts, config-floor benchmarks, routine stand-in). It closes ad live → metrics in warehouse → one learning row with honest sub-sample numbers.

| Week 2 | Week 3 | Week 4 |
|--------|--------|--------|
| Email review with POST-confirmed links; `review_tokens`; Grok competitor watch + trend mining with $/day budget | Reactor service in the app; `events` + coalescing + worker budgets | AEO pipeline tables share the warehouse |
| Batch two: image-to-image renderer on batch-one recipes | Grok competitor watch + trend mining with $/day source budget | Client dashboard on the app |
| First ablation / scaling campaign if a winner exists | Hard qualification if data supports | Rubric regression v1 |
| Embeddings refresh; `competitors` table | Instantly nurture once ≥10 leads/week | Video scripts |
| Client-scoped RLS (`0003`) and first client onboarded | Hard qualification if data supports | Export tooling |
| Auto-pause on kill rule; Standard Access review lands | | |

---

## 8. Open items (from DECISIONS.md)

**Veto items resolved (see `CRUCIBLE.md` §1):** V1–V5 accepted; V6 cap raised to ~$500/month, Grok in week 2.
**Friday:** the corrected checklist in `CRUCIBLE.md` §4 (Meta on Advertiser role + spending limit + Standard Access review; `go.` on Vercel; Supabase EU; scrapecreators test call; Gemini image key; `families.md` + DTC list; config; vault seed; DPAs; SessionStart hook).
**Post-weekend:** ablation margin, conversion-stage sample sizes, Monday memo timing, export format, `events` partitioning, error-spike definition, reactor hosting, X API for organic metrics.
