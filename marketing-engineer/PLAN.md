# Marketing Engineer Pipeline — Build Plan (v1.1, schedule only)

**Status:** v1.1, 2026-09-02. Rewritten after the crucible. This file is the **schedule**. The design lives in `ARCHITECTURE.md`; the data model in `warehouse/schema.sql` and `warehouse/0002_roles.sql`; the reasoning in `DECISIONS.md`; the review and the six items awaiting Sam's veto in `CRUCIBLE.md`. Anything here that disagrees with those files is wrong here.

---

## 1. Goal for the weekend

Close one honest loop for upClickLabs: **ad live → metrics in the warehouse → one learning row**, with every row carrying the attribution keys that make later batches compound. Sub-sample numbers are expected and fine. Scope is the cut line in `CRUCIBLE.md` §3, repeated here as the deliverable list.

**Definition of done (Sunday night)**

1. `0001` + `0002` applied on Supabase EU; upClickLabs seeded; Postgres MCP connected as `mcp_ro`.
2. ≥24 `patterns` rows with `family`, `variant`, `recipe.format_layer`, `source_image_url` in Storage, `status` per the 30-day rule.
3. ≥15 `voc_phrases` rows, anonymised, with `source_ref`, `source_weight`, `visibility`.
4. One `experiments` row with `capacity`; 12 proposed `briefs`; one `selections` row; 3 chosen briefs with `source_pattern_id` and `changed_ingredients`.
5. 6 `creatives` (3 recipes × 2 executions, HTML + Playwright, one image model, 1080×1080) with full `creative_components`.
6. `gate_scores` for all 6: agent shadow scores + Sam's chat verdicts; fact checks recorded in `hard_checks`.
7. Quiz page live on `go.upclicklabs.com` with consent step, Turnstile, pixel + CAPI (`event_id` dedup), `utm_content` capture; test events green; one test submission → `leads` + `lead_contacts` row.
8. One `new_recipes` campaign, 3 ad sets at €10/day, 6 ads, created **by the executor** from a proposed `build_campaign`; `QuizStart` optimisation; one proposed `activate` approved in chat and applied under `check_daily_cap()`.
9. `ad_metrics_daily` has rows; `mart_kill_scale_candidates` returns `hold` (not `config_missing`); one `learnings` row `status='proposed'`, `created_by='sam'`.
10. `apply_actions.py` with advisory lock + pause check + cap invariant; one 08:00 routine (fresh session, SessionStart hook) that pulls insights and emails the five-part check-in through the Gmail connector.
11. `SKILL.md` for `marketing-engineer` with triggers, env vars, run-mode → script map, the "where are we" query, the executor procedure, and the Friday checklist.

---

## 2. Friday evening (Sam, ~4h) — the checklist in `CRUCIBLE.md` §4

Do it in this order; ★ items block Saturday.

1. ★ Meta: app, system user on **Advertiser** role, assets assigned, token stored for the executor only, ad account with spend history, **account spending limit set by hand**.
2. ★ Meta events: domain verified, `QuizStart`/`QuizComplete`/`Schedule` created, CAPI token, `test_event_code`, Data Processing Terms accepted.
3. ◆ Submit Ads Management Standard Access review (multi-week; needed for any client account).
4. ★ `go.upclicklabs.com` on Vercel: CNAME, SSL, hello page. Cal.com account + booking link.
5. ★ Supabase EU project: pgvector, `creatives` bucket, pooler connection string, apply `0001` + `0002`, MCP as `mcp_ro`.
6. ★ scrapecreators key + one real Ad Library call saved; confirm fields and cost.
7. ★ Gemini image key + one test generation.
8. ★ Write `references/families.md` (15 names) and the 5-brand DTC list. 30 minutes, no code.
9. ★ `config/clients/upclicklabs.json`: offer, ICP, 3 quiz questions, terminal metric, floors per lever, `daily_cap`, currency, trust thresholds.
10. ★ Copy 5–10 vault notes into `config/clients/upclicklabs/voc-seed/`, anonymising as you go.
11. DPAs: Supabase, Anthropic, Google, scrapecreators, Vercel. SessionStart hook for Chromium/Python/secrets.

---

## 3. Saturday — produce

Two tracks. Sam's inputs are time-boxed; a slot that passes without them uses the default and moves on.

| Block | Track A (producer) | Track B (intel + gate) | Done when |
|-------|--------------------|------------------------|-----------|
| S1 09:00–12:00 | `warehouse/client.py` (insert helpers, six planner queries), seed, `SKILL.md` skeleton | `pull_inspo.py`: scrapecreators → `raw_ingest` → images to Storage → vision decomposition → `patterns` | `select * from mart_component_leaderboard` runs; 24 patterns tagged with families |
| S2 12:00–14:00 | `render_creatives.py`: two templates (job-photo-bubble, screenshot-ad) → Playwright → Storage | `pull_voc.py`: vault seed + 2–3 Reddit threads → `voc_phrases` (anonymised, weighted) | Two sample PNGs in Storage; 15 phrases |
| S3 14:00–17:00 | Planner: ranker + translation (format layer carried, `changed_ingredients` recorded) → 12 briefs. **Sam picks 3 (20 min, 16:00)** → `selections`. Copy + images for 6 creatives, full components | Gate: fact checks (policy prompt, components, coherence, landing URL, testimonial block) + shadow rubric → `gate_scores` | 6 creatives rendered and gated |
| S4 17:00–19:00 | **Sam's verdicts in chat (20 min)** → `gate_scores` with `scored_by='sam'`, `decision_channel='chat'` | Quiz page: 3 questions, consent, Turnstile, pixel, Edge Function `/quiz` (CAPI + `leads` insert), calendar embed. Test events green | Approved creatives; quiz resolving with green test events |

## 4. Sunday — ship, measure, stand-in

| Block | Track A | Track B | Done when |
|-------|---------|---------|-----------|
| U1 09:00–12:00 | `meta_launch.py` writes a `build_campaign` proposal; `apply_actions.py` (advisory lock, pause, `check_daily_cap()`, name-based lookup before every create, external ids written immediately, `applying`→`applied`) creates campaign + 3 ad sets + 6 ads paused, `QuizStart` optimisation, `utm_content=creative_id` | `test_events.py`; one real quiz submission end to end; Cal.com webhook → `booked_verified_at` (verify signature) | Objects in Ads Manager, paused; `ad_entities` rows; a verified test lead |
| U2 12:00–14:00 | **Sam approves `activate` in chat (10 min)** → executor applies → live at €30/day | `meta_insights.py`: ad-level daily → `ad_metrics_daily`; account-level hourly → `account_spend_hourly`; lever selection from config floors | Ads active; first metrics rows; view returns `hold` |
| U3 14:00–16:00 | Check-in composer: five parts from `actions`, `campaigns.active_lever`, `learnings`, `runs` → Gmail connector | 08:00 routine (fresh session, SessionStart hook) wired and dry-run; `clients.paused` honoured | Check-in email received; routine fired once |
| U4 16:00–18:00 | Sam writes the first `learnings` row (`proposed`, `sample_reached=false`); `SKILL.md` completed; `CHANGELOG.md` | Meta review status sync into `ad_entities.review_status`; disapproval blocks activate | DoD list above all green |

---

## 5. Cut entirely this weekend

Organic/Typefully, Instantly, image-to-image, second image model, extra sizes, testimonial template, ablation and scaling campaigns, email review, `events`/coalescing/worker budgets, `benchmarks` table, vault watcher, hook-rate lever, Slack, embeddings, review page, client dashboard, Grok. Each has a slot in the schema or a week in `ARCHITECTURE.md` §7.

## 6. Risks that survived the crucible

| Risk | Handling |
|------|----------|
| Meta ad review or account restriction on Sunday | Ad account with spend history; Advertiser-role system user; policy fact check; ≤6 ads; Standard Access review submitted Friday |
| `go.` not resolving by Saturday evening | Friday item 4; a hello page is the acceptance test |
| Sam becomes the bottleneck | All Sam inputs are Friday or 10–20 minute chat slots with a default |
| Sub-sample numbers read as results | Learnings gates; leaderboard by lower confidence bound; the first learning is explicitly `sample_reached=false` |
| Secrets in a session that reads untrusted text | Vendor write keys only in the executor process; workers use `worker_rw`; MCP as `mcp_ro` |
| Routines double-apply | Advisory lock; `proposal_key` unique; `applying` before external calls |

## 7. First-month metrics (revised)

| Metric | Week 1 | Week 4 |
|--------|--------|--------|
| Creatives reaching sample size | 0–2 | ≥8 cumulative |
| Creatives with full component attribution | 6 | ≥24 |
| Learnings: proposed / supported | 1 (human) / 0 | ≥3 / ≥1 |
| Cost per link click vs floor | measured | ≤ floor |
| Verified bookings | measured | ≥5 cumulative |
| Trust promotions | 0 | 0–1 (kill, if back-test passes) |
| Clients on the pipeline | 0 (us) | 1 |
