# Marketing Engineer Pipeline — High-Level Architecture

**Status:** v1.0, consolidated from `DECISIONS.md` (components 0–9) on 2026-09-02. This is the document a build agent implements from. `PLAN.md` holds the schedule, `WAREHOUSE.md` the data design, `DECISIONS.md` the reasoning and rejected options.

---

## 1. What it is

An always-on, event-driven creative engine that acquires clients for upClickLabs first and is then pointed at those clients. It replicates proven ads onto our offer, ships them to Meta and organic channels, measures them against a per-campaign value model, and writes structured learnings into a warehouse that compounds across clients. Humans supervise at first; the machine earns autonomy per action type.

**Non-negotiables**

1. Facts always block (policy, brand, likeness, coherence, tracking). Taste starts with Sam and is learned.
2. No side effect without the executor. Workers propose; one executor applies under the trust rule.
3. Every creative is decomposed into components. No attribution key, no ship.
4. Read learnings before planning; write learnings after measuring. Zero learnings at sample size is a warning.
5. Nothing lives only in a file. Warehouse is the system of record; git holds code, prompts, schema, and rendered memos.
6. The runtime is ours. Models are workers.

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
| Plan | angle-planner | batch requested, ablation triggered | `learnings`, leaderboards, benchmarks, VOC, patterns | `experiments`, ~24 `briefs` (replicas w/ `changed_ingredients`), `selections` | **picks 6 of 24** until promoted |
| Produce | creative-producer | briefs selected | briefs, brand kit, templates | `creatives` ×2 per recipe ×2 renderers, `creative_components`, assets in Storage | none |
| Gate | creative-gate | creatives ready | policy, brand, source ad | `gate_scores` (agent shadow + Sam verdict), `review_tokens` | **approve/reject by email** until promoted |
| Ship | launcher | creatives approved | campaigns, offer, quiz config | `campaigns`, `ad_entities` (paused), `posts`, proposed `activate` | activate (trust rule) |
| Measure | performance-loop | insights arrival, sample_size_reached | metrics, benchmarks, value model | `ad_metrics_daily`, `benchmarks`, `campaigns.active_lever`, proposed kill/scale `actions`, `learnings` | approve kill/scale until promoted |
| Close | launcher (nurture) | lead stage events | leads | proposed `push_to_instantly`, `leads.stage` from replies | approve until promoted |
| Learn | performance-loop | Monday | everything | Monday memo, promotions proposed, next batch requested | reads memo, picks recipes |

---

## 4. Component summaries

### 0. Value model
Per campaign: a **terminal metric** fixed at launch (e.g. booked call) and a **lever chain** per platform (Meta: hook rate → link CTR → CPM → CVR → cost per booked call). The loop works the first lever below benchmark at sample size. Terminal metric changes need a human.

### 1. Creative intelligence
Three sub-workers: format library (weekend, scrapecreators), competitor watch and trend mining (week 2, Grok). Seed: best DTC testers; category peers as fallback after a family fails in-niche (3 creatives under floor). Two-level taxonomy: fixed **families** (attribution key) + free **variants** (exploration); variants promoted at the Monday memo. **Proven** = ≥30 days running or ≥3 concurrent variants. Every run logs counts; empty is valid; two consecutive source failures block the batch.

### 2. Customer language
Sources: Obsidian vault (weight 3) → quiz answers (2) → Reddit/Quora, G2/Clutch, LinkedIn/X replies (1). Unit: verbatim phrase, tagged pain/outcome/objection/identity/trigger. Anonymised at extraction; pointer to source only; vault phrases `internal` and quotable only with a `quote_release`. Event-driven per source; deduplicated by source pointer.

### 3. Angle planner
**Replicate then ablate.** Unit is the *recipe* (full decomposition of a proven ad). A batch replicates recipes onto our offer; translation may change only offer, product nouns, VOC phrases, imagery subject, and records `changed_ingredients`. Underperformance vs source → ablation batch restoring ingredients one at a time. Coherence check routes back to the planner. Planner proposes ~24, Sam picks 6 (×2 executions = 12 creatives); selections train the ranker. Spend 70% new recipes / 30% ablations.

### 4. Creative producer
Two renderers, both built, both tested on batch one: HTML family templates via Playwright, and image-to-image from the source ad with a fidelity check. Imagery generated by best-in-class models only (config value; two models side by side in batch one); no stock; generated people ok, real likeness blocked. **Text is always ours**, overlaid in HTML. Copy per direct-response rules and translation discipline. Organic posts share recipes and hooks. Full `creative_components` or no ship.

### 5. Creative gate
Facts block automatically. Taste is Sam's verdict by **email** (inline creatives, one-click signed approve/reject, reasons by reply); the model rubric scores in shadow mode and is promoted to blocking when it agrees with Sam at the configured rate. Taste is corrected by the market in the Monday memo; rubric dimensions regressed on CTR quarterly.

### 6. Launcher
Meta per offer: **new-recipes** and **ablation** campaigns with one ad set per recipe (own budget), plus a **scaling** campaign (CBO) for proven winners. Broad targeting. Optimise for **booked call** from day one; quiz events tracked; `QuizComplete` fallback documented. **Quiz funnel on our platform** (`go.upclicklabs.com`), first-party pixel + CAPI, `utm_content = creative_id`, soft qualification with a score in month one. Nurture via Instantly on lead-stage events (nurture / reminder / rebook); starters never emailed. Organic via Typefully.

### 7. Performance loop
Benchmarks per lever resolved: own history → cross-client mart → source recipe → config floor. Chain walked top-down; first lever below benchmark becomes the active lever. Kill/scale rules under the trust rule with evidence snapshots. Learnings in three tiers: proposed (any benchmark hit/miss at sample size) → supported (replication or ablation) → global (3 clients). **Daily check-in**: actions waiting, actions taken, active levers, new learnings, warnings. Monday memo: promotions, taste-vs-market, next batch.

### 8. Growth warehouse
Supabase Postgres + pgvector + Storage. Clients see the app, never the DB; exports on request; benchmarks are ours by contract. Schema growth: raw → JSONB (documented) → column (migration) once read twice. Migrations only.

### 9. Orchestrator
Our runtime. Reactor consumes `events`, coalesces, dispatches to workers with daily budgets. **Grok is the watcher; Claude plans, writes, gates; image models draw.** Single executor applies proposed actions under per-action-type trust levels; promotions are Sam-only actions. Brakes: pause flags (global/client), auto-pause on spend +20% / 3 failures / error spike, and a Business Manager spend ceiling. Weekend stand-in: Claude Code routines + webhooks; app service in week 3.

---

## 5. Trust ladder (graduated autonomy)

| Action type | Starts as | Promoted after (default) | Who promotes |
|-------------|-----------|--------------------------|--------------|
| recipe selection (planner picks the 6) | Sam picks | planner top-6 matches Sam's picks ≥80% over 4 batches | Sam |
| taste gate (rubric blocks) | Sam verdicts | agent verdict agrees with Sam ≥85% over 40 creatives | Sam |
| activate campaign / ad | propose | 20 unchanged approvals | Sam |
| kill | propose | 10 unchanged approvals | Sam |
| scale / move to scaling campaign | propose | 20 unchanged approvals | Sam |
| publish organic post | propose | 20 unchanged approvals | Sam |
| push lead to Instantly | propose | 20 unchanged approvals | Sam |
| quote_release (internal VOC verbatim) | Sam only | never auto | — |
| trust promotion | Sam only | never auto | — |

Counters come from `actions` (`approved_by`, `applied`, unchanged vs edited). Any rejection resets the streak for that type.

---

## 6. Event catalogue (v1)

`intel_finding`, `pattern_added`, `vault_note_changed`, `voc_extracted`, `batch_requested`, `briefs_proposed`, `selection_made`, `creatives_rendered`, `review_ready`, `verdict_received`, `creatives_approved`, `campaign_built`, `action_proposed`, `action_applied`, `quiz_start`, `quiz_step`, `quiz_complete`, `lead_booked`, `lead_no_show`, `lead_stage_changed`, `insights_arrived`, `sample_size_reached`, `lever_changed`, `learning_proposed`, `checkin_sent`, `pause_set`, `worker_failed`.

Coalescing window 15 minutes per source. Each worker has a daily token and API-call budget in client config.

---

## 7. What ships this weekend vs later

| Weekend | Week 2 | Week 3 | Week 4 |
|---------|--------|--------|--------|
| Warehouse (migration 0001 incl. all component schema changes), client lib, seed | Grok competitor watch + trend mining | Reactor service in the app | AEO pipeline tables share the warehouse |
| Format library from scrapecreators, DTC seed list, families v1 | Embeddings refresh, CRM/Instantly stage sync | Buying-trigger agent (Grok) | Client dashboard on the app |
| VOC from vault + public sources | Auto-pause on kill rule enabled | Image-to-image path for families without templates | Video scripts |
| Planner: 24 recipes → Sam picks 6 | First client onboarded (cloned config) | Hard qualification if data supports | Rubric regression v1 |
| Producer: 3 templates + 1 generation path, 2 image models | | | |
| Gate: fact checks + email review with one-click verdicts | | | |
| Launcher: 3-campaign structure (paused), quiz on `go.` subdomain, CAPI tested | | | |
| Loop: insights pull, lever selection, proposed kill/scale, first learning | | | |
| Orchestrator stand-in: routines + webhooks, executor, pause flag | | | |
| Daily check-in email | | | |

Definition of done for the weekend is unchanged in spirit from `PLAN.md` §3: one live loop for upClickLabs with batch one fully in the warehouse, but with the decisions above applied (both renderers, email review, three-campaign structure, quiz on our platform, executor + pause flag).

---

## 8. Open items (from DECISIONS.md)

Friday (Sam): Meta access; Supabase project; DTC and category seed lists; vault note convention; image model access; app hosting + `go.` DNS; calendar tool; vendor prices; promotion thresholds.
Saturday: families v1 (S2); recipe benchmark inference (S2); vault sync path (S2); fidelity check threshold (S3); email sender (S4); quiz questions v1 (S3).
Post-weekend: ablation margin, conversion-stage sample sizes, Monday memo timing, export format, events partitioning, error-spike definition, reactor hosting.
