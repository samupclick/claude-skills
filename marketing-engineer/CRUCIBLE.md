# Crucible Report — Marketing Engineer Pipeline v1.0 → v1.1

**Date:** 2026-09-02
**Method:** three independent adversarial reviewers, each with one lens, reading `ARCHITECTURE.md`, `DECISIONS.md`, `PLAN.md`, `WAREHOUSE.md`, and `warehouse/schema.sql`: (E) economics, statistics, attribution; (S) safety, money, security, platform, compliance; (F) feasibility, complexity, dependencies. 40 findings raised, consolidated to 24 amendments below. Every amendment is applied in `ARCHITECTURE.md` v1.1, `warehouse/schema.sql` (migration 0001) and `warehouse/0002_roles.sql`, and `PLAN.md` v1.1, unless marked **veto**.

**Verdicts as delivered**

- E: "The weekend build will produce a working pipeline and no valid signal." Batch one as specified reaches sample size on almost nothing; Meta never leaves learning; the first conversion-stage kills would be wrong ~70% of the time.
- S: "Not as designed." The single-executor rule lived in prose and a shared service-role key; the money loop keyed on forgeable signals with a scale-everything default; approvals that earn autonomy could be cast by mail scanners.
- F: "The loop does not close by Sunday night." ~80 hours of scope against 36; the quiz app unbuilt on the critical path; the schema could not store the executor's first action.

---

## 1. Decisions the crucible reversed — **resolved by Sam, 2026-09-02**

Sam reviewed all six: V1–V5 **accepted as written**; V6 **overridden**: the machine budget cap is raised to ~$500/month, so Grok watchers return to week 2 and Instantly is enabled as soon as there are leads to nurture (no volume gate). The table below is the record.

| # | Was | Now | Why (one line) |
|---|-----|-----|----------------|
| V1 | 6 recipes × 2 executions = 12 creatives per batch at $30/day | Batch size is **derived from capacity**: `floor(daily_budget × 7 × 1000 / (cpm × kill_impressions))` ≈ **4 creatives/week at $30/day and €25 CPM**. Batch one = **3 recipes × 2 = 6 creatives**, Sam picks 3 of 12 proposals. Raise the daily budget to ~€90 to keep 6 recipes. | Impressions, not production, are the constraint. 12–48 creatives on $30/day reach 2,000 impressions on nothing before batch two lands. (E1, E10) |
| V2 | Ad sets optimise for `Schedule` (booked call) from day one | Testing ad sets optimise for **`QuizStart`**; `Schedule` stays the **terminal metric measured in the warehouse**. Promote the Meta event to `QuizComplete` at ~30/week per ad set, `Schedule` only in the scaling campaign. | Meta needs ~50 events per ad set per week to leave learning; the funnel yields ~3 bookings a week account-wide. Switching later resets learning, so start where the volume is. (E2, S12) |
| V3 | Both renderers and two image models side by side inside batch one | **Renderer and image model are between-batch factors**: batch one = HTML templates + one image model; batch two = image-to-image on the same recipes. In-batch comparisons only via Meta's A/B tool, never two ads in one ad set. | Meta starves one ad within 48h; in-ad-set pairs measure Meta's choice, not the renderer. Halving per-creative impressions makes V1 worse. (E9, F6) |
| V4 | Email review with one-click links this weekend | **Weekend: verdicts in chat**, written to `gate_scores` by the session. **Week 2: email** with links that open a confirmation page and POST, one token per item, 72h expiry, spend-affecting approvals behind a magic-link session, never in Slack. Daily check-in via the Gmail connector. | Mail scanners GET every link; single-use GET tokens get spent before Sam clicks and the scanner's click counts as Sam's verdict. (S5, F7) |
| V5 | Testimonial card as a weekend template, generated people allowed | **Testimonial/quote families are hard-blocked** unless the quote maps to a real client with a `quote_release` and no depicted person. Weekend templates: job-photo-bubble and screenshot-ad. | A generated person plus our copy is a fabricated endorsement under Meta policy and the EU Unfair Commercial Practices Directive. (S11) |
| V6 | Machine budget cap 250 USD/month | **Sam's decision: cap raised to ~$500/month.** Grok watchers in **week 2** (as C1/C9 originally decided) with a hard $/day source budget; Instantly enabled once there are leads to nurture. Weekend stack still ≈ $100. | Realistic total is $350–600/month including model usage. (E8) |

---

## 2. Amendments applied (no decision reversed)

| # | Amendment | Source | Applied in |
|---|-----------|--------|------------|
| A1 | **Executor enforced in Postgres.** Roles `worker_rw`, `executor`, `sam_admin`, `app`, `mcp_ro`; trigger `actions_guard` (workers may only insert `proposed`; only `sam_admin` may approve `promote_trust`, `quote_release`, `set_pause_flag`); Meta write token lives only in the executor process; the launcher proposes `build_campaign`, it does not call Meta. | S2, S13 | `0002_roles.sql`, ARCH §5, §9 |
| A2 | **Actions are a state machine** with `proposal_key` unique (idempotency), `proposal`/`approved_payload` (so "unchanged" is computable), `status` proposed→approved→applying→applied/failed/superseded, `decision_channel`, `attempts`, `last_error`, `executor_run_id`. | S3, S9 | schema `actions` |
| A3 | **Trust streaks are a view**, never a stored counter; count only human decisions (`chat`, `token_post`, `app`) with `approved_payload = proposal`, reset on rejection; `activate` counts per batch; `kill` promotion also requires back-test accuracy ≥80%; autonomous actions rate-limited (max kills/day, ≤50% of live ads, one scale per ad per 72h) and demoted on any executor failure. | S3, E12 | schema `trust_streaks`, ARCH §5 |
| A4 | **Kill/scale view fixed**: missing config → `config_missing`, never a permissive default; CTR-stage rules per ad; conversion-stage kill only when expected bookings ≥5 (spend ≥ 5 × target) and observed < expected/3; scale only on **warehouse-verified bookings**; `ad_entities.status` is an enum. `cpl_target` derived from the funnel after 100 clicks, config floor until then. | S1, E3 | schema view, ARCH §7 |
| A5 | **Lever chain for statics**: cost per link click → quiz-start rate → quiz-complete rate → booking rate → cost per booked call. CPM is context, not a lever. Hook rate only when `family.kind = video`. | E7 | ARCH §4.0, §4.7 |
| A6 | **Recipe split**: `recipe.format_layer` (family, visual structure, copy structure, copy length, hook type) carried exactly from DTC sources; `recipe.offer_layer` (offer mechanic, proof type, CTA mechanic) drawn from `offers.offer_layer` or category peers, fixed per offer for Q1. Attribution and ablation operate on the format layer. | E6 | schema `patterns.recipe`, `offers.offer_layer`, ARCH §4.3 |
| A7 | **No "implied source benchmark."** `patterns.source_strength` is ordinal, for ranking only. Benchmark resolution: own history → cross-client → config floor. Ablation trigger: replica below floor at sample size **and** recipe proven **and** ≤3 changed ingredients; one ablation at a time, 2 creatives. | E5 | schema, ARCH §4.3, §4.7 |
| A8 | **Learnings need statistics**: ≥50 clicks per arm, effect ≥0.3pp absolute or ≥30% relative, posterior P(direction) ≥0.9 (Beta-Binomial on clicks/impressions); leaderboard ranks by **lower confidence bound** and only levels with ≥3 creatives; below the gates = zero weight, not reduced weight. "Zero learnings" warning fires only when a creative reached sample size. | E4 | schema `learnings.posterior`, `mart_component_leaderboard.link_ctr_lcb`, ARCH §4.7 |
| A9 | **Batch cadence is a threshold event**: request a batch when in-flight creatives below sample size < capacity − batch_size. Capacity recomputed from the last 7 days' actual CPM. | E10 | schema `experiments.capacity`, ARCH §3 |
| A10 | **Campaign structure**: ablation and scaling campaigns are created when the first ablation or winner exists, not at batch one; 100% of budget to new recipes until then across ≤3 ad sets; `currency` on client and campaign; `scale` typed per target (ad set vs CBO campaign); moving to scaling pauses the origin ad in the same action. | E11, S7 | schema `campaigns`, ARCH §4.6 |
| A11 | **Brakes rebuilt**: (1) configuration invariant `sum(active ad set budgets) + scaling budgets ≤ clients.daily_cap` checked by the executor **before** create/activate/scale (`check_daily_cap()`); (2) hourly account-level spend pull into `account_spend_hourly` for the observational brake; (3) one ad account per client, system user on Advertiser role only, Sam's admin sets the account spending limit by hand, prepaid/limited card behind it; (4) lead-velocity brake (>3× 7-day median). | S7, S8, S4 | schema, `0002` function, ARCH §5 |
| A12 | **Forgeable signals closed**: Turnstile + rate limits + disposable-email rejection on the quiz; every inbound webhook verified (HMAC or re-fetch by ID); `leads.booked_verified_at` set only from the calendar tool's authenticated API; CAPI `Schedule` fires only on verified booking with `event_id` dedup; scale evidence uses verified bookings only; `leads.abuse_score`. | S4 | schema `leads`, ARCH §4.6 |
| A13 | **GDPR baseline**: `leads.consent` captured before pixel/CAPI/Instantly; Supabase **EU region**; DPAs listed as a Friday item (Supabase, Instantly, xAI, Anthropic, image vendors, scrapecreators, hosting) and Meta's Data Processing Terms accepted; `voc_phrases` stores anonymised phrases and pointers only, **no verbatim quotes column**; PII isolated in `lead_contacts` with column grants; `raw_ingest.purge_after` (90 days for PII sources), `leads.purge_after` (24 months post-activity); `erasure_requests` with fan-out to Storage, Instantly, Meta audiences, backups; `mart_benchmarks` suppressed under 3 clients; verbatim use of any `public`/`inbound` phrase in a creative is a gate hard check. | S6 | schema, ARCH §8 |
| A14 | **Concurrency**: `pg_advisory_xact_lock` per executor and reactor run; `select … for update skip locked` on actions; transition to `applying` inside the transaction before any external call, `applied` only after reading the entity back from Meta; stuck `applying` reconciled against Meta, never re-sent; pause flag re-checked in the same transaction; no session-bound webhooks, Edge Functions write to the warehouse and the next wake picks it up. | S9, F8 | ARCH §9 |
| A15 | **Trust boundary on ingested text**: `trust_tier` (`owned`/`client`/`public`/`inbound`) on `raw_ingest`, `voc_phrases`, `patterns`, `hooks`, `gate_scores.feedback`; workers receive untrusted text only inside delimited data blocks with a fixed system prompt and must return schema-validated JSON; emails escape everything and carry no URLs from rows below `owned`; reply parsing (week 2) requires DMARC pass + `In-Reply-To` match and lands in quarantined feedback labelled untrusted. | S10 | schema, ARCH §8 |
| A16 | **Meta lifecycle**: `ad_entities.review_status` synced from `effective_status`/`ad_review_feedback`; disapproval blocks `activate` and N disapprovals in 7 days pauses the client; budget changes in ≤20% steps; reuse `object_story_id` when moving to scaling; insights via async jobs with backoff; Ads Management **Standard Access review submitted Friday** (needed for any client account); use an ad account with spend history. | S12, S11, F5 | schema, ARCH §4.6, PLAN Friday |
| A17 | **Metrics restatements**: `ad_metrics_daily` keyed by `(ad, day, fetched_on)`; `ad_metrics_latest` view; append-only holds and back-tests are honest. | S14 | schema |
| A18 | **Views run as `security_invoker`** so RLS applies through marts; RLS enabled on every PII-bearing table; baseline policies in `0002`. | S14 | schema, `0002` |
| A19 | **Source images persisted** to Storage at fetch time (`patterns.source_image_url`); scrapecreators field names and cost verified with one real call on Friday; `days_running` derived from `start_date`. | F12 | schema, PLAN Friday |
| A20 | **Deferred without losing compounding**: `events` + coalescing + per-worker budgets (week 3 reactor; routines poll tables until then), `review_tokens` (week 2), `competitors` (week 2), `benchmarks` table (config floors until then), `trust_levels`/`pause_flags` tables (live in `clients.config` / `clients.paused`), `intel_runs`+`worker_runs` → one `runs` table, embeddings refresh, Typefully/organic (no metrics API; needs X API later), Instantly nurture. **Must exist from batch one**: full `creative_components`, `briefs.source_pattern_id/changed_ingredients/kind`, `patterns.recipe`, `selections`, `gate_scores.scored_by/verdict/mode`, `actions.evidence`, `raw_ingest`, `ad_entities ↔ creative_id` with `utm_content=creative_id`, append-only metrics, `experiments`. | F13 | schema, ARCH §7 |
| A21 | **Cold start bootstrap**: config floors per lever; static-ad chain per A5; `references/families.md` and the DTC seed list hand-written by Sam on Friday; 5–10 vault notes copied into the build env as a one-time seed (no watcher); deterministic ranker = source strength × family diversity until `selections` has 4 batches. | F11 | PLAN Friday, ARCH §4.3 |
| A22 | **Sam is not a serial dependency**: families and DTC list written before code; picks and verdicts time-boxed to 20 minutes in chat; anything that says "Sam approves" carries a clock. | F10 | PLAN §3 |
| A23 | **Reactor stand-in rules**: two fixed wakes per day (08:00, 20:00), fresh-session mode, SessionStart hook for Chromium/Python/secrets, advisory lock at the top of the executor, name-based lookup before every Meta create with the external id written immediately after. Workable for one week, not three. | F8 | ARCH §9, PLAN §3 |
| A24 | **Document hygiene**: `PLAN.md` rewritten as schedule-only against the cut line; `WAREHOUSE.md` banner pointing to the schema as source of truth; `DECISIONS.md` C0 fixed (check-in by email, Slack carries the count); the pipeline is **one skill** (`marketing-engineer/SKILL.md`, worker prompts under `references/prompts/`), the `go.` app is a **separate repo**. | F9, F14 | this commit |

---

## 3. Weekend cut line (from F, adopted)

The minimum that closes ad live → metrics in warehouse → one learning row:

1. **Warehouse**: `0001` + `0002` as now in `warehouse/`, seed upClickLabs.
2. **Intel**: scrapecreators Ad Library for 5 DTC brands → `raw_ingest` → images to Storage → vision decomposition into `patterns` with `family` from `references/families.md`; `proven` where `start_date` ≥ 30 days ago. Target 24 rows.
3. **VOC**: one-time seed from 5–10 vault notes + 2–3 Reddit threads. No watcher.
4. **Planner**: 12 ranked recipes → Sam picks 3 in chat → `selections`, 3 `briefs` with `source_pattern_id` and `changed_ingredients`.
5. **Producer**: HTML + Playwright, two templates (job-photo-bubble, screenshot-ad), one image model (Gemini image), 1080×1080 only, 2 executions per recipe = 6 creatives, full `creative_components`.
6. **Gate**: automated fact checks (policy, components, coherence, landing URL, testimonial block) + Sam's verdicts in chat → `gate_scores`; rubric in shadow.
7. **Landing**: one static quiz page on `go.upclicklabs.com` (Vercel), 3 questions, consent step, Turnstile, pixel + Edge Function CAPI with `event_id` dedup, `utm_content`/`fbclid` capture, `leads` + `lead_contacts` insert, calendar embed; `Schedule` fired only on verified booking. Test events green.
8. **Launcher**: one `new_recipes` campaign, 3 ad sets at €10/day, 6 ads paused, `QuizStart` optimisation. Activation = one proposed `activate`, Sam approves in chat, executor applies under the cap invariant.
9. **Loop**: `meta_insights.py` ad-level daily → `ad_metrics_daily`; `mart_kill_scale_candidates` (all `hold`); one `learnings` row `status='proposed'`, `created_by='sam'`, `evidence.sample_reached=false`.
10. **Orchestrator stand-in**: `apply_actions.py` (advisory lock, pause check, cap invariant, Meta call, write external id, mark applied) + one 08:00 routine (fresh session, SessionStart hook) that pulls insights and sends the five-part check-in through the Gmail connector.

**Cut entirely this weekend**: organic/Typefully, Instantly, image-to-image, second image model, extra sizes, testimonial template, ablation + scaling campaigns, email review, `events`/coalescing/budgets, `benchmarks` resolution, vault watcher, hook-rate lever, Slack, embeddings, review page, client dashboard, Grok.

## 4. Corrected Friday checklist

★ = blocker if missing · ◆ = silently multi-day

- ★ **Meta**: Business-type app created and added to BM; system user with `ads_management` + `business_management` on **Advertiser** (not Admin); page, pixel, ad account assigned; non-expiring token stored for the executor only. Ad account has payment method and prior spend. Sam's admin sets the **account spending limit** by hand.
- ★ **Meta events**: root domain verified in Events Manager; `QuizStart`, `QuizComplete`, `Schedule` created; CAPI token generated; `test_event_code` noted; Meta Data Processing Terms accepted.
- ◆ **Meta**: submit Ads Management Standard Access review with the `go.` page as demo URL.
- ★ **`go.upclicklabs.com`**: Vercel project, CNAME, SSL green, hello page resolving. Calendar tool chosen (Cal.com: free, webhooks, API for verified bookings) and a booking link created.
- ★ **Supabase**: project in **EU region**, `create extension vector`, Storage bucket `creatives`, service key + **pooler (IPv4) connection string** in env, `0001` + `0002` applied, Postgres MCP connected as `mcp_ro`.
- ★ **scrapecreators**: account, key, one real Ad Library call saved to scratch; confirm `start_date`, `is_active`, snapshot image fields, cost per call.
- ★ **Image model**: Gemini image API key, one test generation.
- ★ **Sam writes** `references/families.md` (15 names, one line each) and the 5-brand DTC seed list. 30 minutes, before any code.
- ★ **Config**: offer, ICP, 3 quiz questions, terminal metric, floors per lever, `daily_cap`, currency, trust thresholds in `config/clients/upclicklabs.json`.
- ★ **Vault seed**: 5–10 notes copied into `config/clients/upclicklabs/voc-seed/` (anonymise as you copy).
- **DPAs**: list and accept for Supabase, Anthropic, Google (image), scrapecreators, Vercel. Instantly/xAI when they enter.
- **SessionStart hook** for Chromium/Python deps/secrets in the remote environment.
- Not Friday: xAI key (week 3), Typefully, Instantly, Resend, Slack.

## 5. Findings not adopted

- E: "raise the cap to $500 or accept monthly cadence" — Sam raised the cap (V6).
- F: testimonial-card as a weekend template — superseded by S11 (V5); screenshot-ad replaces it.
- S: per-client databases — not needed; roles + RLS + app scoping (already decided in C8).
