# Marketing Engineer Pipeline — Decision Log

Produced by the grill-me process, one component at a time. A build agent should be able to implement each component from its block alone. Newest blocks at the bottom.

---

## Component 0: System boundary

**Decided**

- **No single global metric.** Each campaign carries a *value model*: a terminal metric fixed at launch (what the account actually values, e.g. qualified lead, booked call, revenue, followers) plus a platform-specific *lever chain* of leading indicators. Meta chain: hook rate → link CTR → CPM → CVR → cost per qualified lead. The loop diagnoses the weakest link in the chain and works that lever before moving downstream. The active lever may change weekly; the terminal metric may not change without a human.
- **upClickLabs is tenant one.** The pipeline's first job is to acquire clients for upClickLabs. The first client is closed *by* the pipeline, and that client's own journey through the funnel is the proof used to sell them. Implications: the funnel mart and lead attribution must be presentable to prospects; onboarding a client means cloning the value model and config while keeping global learnings; client-scoped rows and global learnings exist in the warehouse from day one even with one tenant.
- **Graduated autonomy, per action type.** Target end state: the system launches, kills, and scales on its own. Start supervised, like onboarding a new employee. Each action type (launch, kill, scale, publish organic, push lead to nurture) has its own trust level. An action is promoted from *propose* to *execute* after it has been approved unchanged N times. N lives in client config; approval counts come from the `actions` table (`approved_by`, `applied`).
- **Stack.** Claude Code + skills remain the orchestrator, producer, and gate. Grok (xAI API with X search) powers the creative-intel worker and, in week 3, the buying-trigger agent; it is a worker behind a warehouse-write boundary, not the orchestrator. Supabase is the warehouse and asset store. Instantly is the nurture layer: quiz leads are pushed into sequences by API, replies and bookings flow back to `leads.stage`. Meta Marketing API for paid. Typefully for organic scheduling. Playwright HTML templates for statics; Canva later for brand templates. Notion stays the job board, Slack the alert channel. Rule: no new tool without a warehouse write.
- **Machine budget cap:** 250 USD/month for the first quarter, excluding ad spend and model usage on existing plans. Vendor prices to verify: xAI API, scrapecreators tier, Typefully.
- **Owner:** Sam owns the pipeline. Cadence is a **daily check-in** delivered by email (Slack carries only the count and a link); Sam approves or rejects proposed actions from it, and those decisions feed the trust counters. Monday learnings memo remains the weekly accountability artefact.

**Rejected**

- Single north-star metric across platforms (default proposal). Rejected because platforms and campaign stages value different levers; replaced by the value model + lever chain.
- Grok as the orchestrator. Rejected because the orchestration, gates, and warehouse client are already Claude-native; Grok's edge is live X data, which is an intel concern.
- "Drafts only" autonomy ceiling. Rejected in favour of graduated autonomy with a supervised start.

**Open**

- Exact promotion thresholds N per action type (Sam, before Sunday U4; default 10 unchanged approvals for kill, 20 for scale and launch).
- Which calendar tool backs the quiz funnel CTA (Sam, Friday).
- Verified monthly prices for xAI API, scrapecreators, Typefully (Sam or first build session, Friday).

---

## Component 1: Creative intelligence

**Decided**

- **Three sub-workers, one component, one set of tables.** (a) *Format library*: which creative formats are proven; Meta Ad Library via scrapecreators; weekly. (b) *Competitor watch*: what changed in competitors' messaging; their ads, X and LinkedIn posts, site; daily; needs a `competitors` table and a diff. (c) *Trend and hook mining*: what is getting engagement in the ICP's feed now; Grok with X search; daily. **Weekend builds (a) only.** (b) and (c) land in week 2 on Grok.
- **Seed source: best direct-to-consumer testers first.** DTC brands known for creative testing seed the library. Category peers are the fallback once a format has failed in our niche. Every `patterns` row records `source_list` (`dtc` | `category`) so the planner can distinguish "DTC-derived, untested here" from "category-proven".
- **Niche-fail rule:** a family is retired for an ICP after 3 creatives from it fall under the CTR floor at sample size. The loop then pulls the next candidate from the category list. Retirement is a `learnings` row with scope `icp`.
- **Two-level taxonomy.** `family` is a fixed, human-controlled list (~15 to start, plus `unclassified`) and is the attribution key; all performance rolls up at family. `variant` is free text the intel worker invents; variants compete inside a family. The Monday routine proposes promoting a variant to a family when it reaches sample size across ≥3 creatives; Sam approves. Same two-level structure for `hook_type` and `angle`. Rationale: the binding constraint is impressions per creative, not production cost; free tags split the same impressions across more buckets. Exploration breadth scales with spend automatically.
- **Proven threshold:** an external pattern is `proven` when the ad has run ≥30 days in the Ad Library, or the same brand runs ≥3 concurrent variants of one family. Everything else is a `candidate`, visible to the planner at lower weight.
- **Empty and failure handling:** every run writes an `intel_runs` record with per-source counts. Zero new patterns is a valid result; the planner proceeds on the existing library. A failed source is retried once, then reported as a warning in the daily Slack check-in. Two consecutive failures on the same source block the Monday batch until Sam acknowledges.

**Rejected**

- Category peers as the primary seed (default). Rejected in favour of DTC-first with category fallback.
- Fully free-form tagging ("Darwinian" at the tag level). Rejected because it fragments sample size; replaced by fixed families + free variants, which keeps the exploration.
- Fully fixed taxonomy. Rejected because it needs a human to notice every new format.

**Schema changes (fold into 0001 before first apply)**

- `patterns`: add `family text not null`, `variant text`, `source_list text check in ('dtc','category','own')`, `status text check in ('candidate','proven','retired')`; keep `format` as an alias of `family` or drop it.
- New `families(name pk, kind check in ('format','hook_type','angle'), status, promoted_from_variant, created_at)`.
- New `intel_runs(id, source, started_at, finished_at, status, counts jsonb, error text)`.
- New `competitors(id, client_id, name, domain, meta_page_id, x_handle, linkedin_url)` — table now, populated in week 2.
- `learnings`: retirement rows use `component_type='family'`.

**Open**

- The initial DTC brand list (10) and category peer list (10) — Sam, Friday evening; the intel worker can propose candidates but Sam picks the seed.
- Initial family list (~15) — draft in `references/families.md` on Saturday S2, Sam approves before S3.

---

## Cross-cutting: event-driven orchestration

**Decided (raised during component 2, applies to every component)**

- **The pipeline is event-driven, not scheduled.** Watchers emit events; the orchestrator is a reactor that decides what to do next. No human-paced schedule for the machine. The daily Slack check-in is Sam's window into the system, not its clock.
- **Event sources (initial):** intel watcher findings (Grok competitor watch and trend mining, week 2; scrapecreators pulls this weekend), Obsidian vault note changes, quiz funnel submissions / lead stage changes, Meta insights arrivals, threshold crossings (an ad reaching sample size, a kill or scale rule firing), human approvals in Slack.
- **Event storage:** an `events` table in the warehouse (`source`, `type`, `entity_ref`, `payload`, `occurred_at`, `processed_at`, `coalesced_into`). Supabase realtime or a polling reactor consumes it; implementation chosen at build time.
- **Guardrail 1, debounce and budget:** events are coalesced per source over a window (default 15 minutes); each watcher has a daily token and API-call budget. On budget exhaustion the watcher keeps writing raw events and stops reasoning until the next window. Budgets live in client config.
- **Guardrail 2, spend decisions keep their own clock:** intel, vault, and lead events may trigger new briefs at any time. Kill and scale decisions wait for sample size (default 2,000 impressions per creative) because Meta insights are daily-grained and sub-sample CTR is noise.
- **Graduated autonomy still applies:** an event may trigger a *proposal* at any trust level; *execution* follows the per-action trust level from component 0.

**Rejected**

- Fixed cadences per worker (weekly public sources, daily vault, on-arrival quiz). Rejected as human-paced; replaced by events with the two guardrails above.

---

## Component 2: Customer language

**Decided**

- **Sources, in priority order:** (1) the Obsidian vault (call transcripts, customer notes) — our own voice of customer, thin today but highest weight; (2) public: Reddit and Quora threads about SEO agencies, AI visibility, and lead gen; G2 and Clutch reviews of competing agencies and tools, negative reviews especially; LinkedIn and X replies under AI-search posts; (3) quiz funnel answers and discovery call notes as the pipeline produces them, making it self-feeding.
- **Vault access:** the worker reads the vault as a markdown folder; no integration. A convention decides which notes count (default: a `voc` tag or a `customers/` folder — Sam to confirm). The worker never writes into the vault.
- **Unit of extraction:** verbatim phrases, tagged `pain | outcome | objection | identity | trigger`, each with quote, source, and frequency. The human-readable memo is a ranked view over `voc_phrases`. No separate summary artefact.
- **Weighting:** a phrase from our own calls outweighs the same phrase from public sources (`source_weight` on the row; default vault 3, quiz 2, public 1).
- **Privacy:** names, companies, and identifying figures are stripped at extraction. Rows hold a pointer to the source note (`source_ref`), never the note text. Vault-derived phrases are `visibility='internal'`: they may shape angles and briefs but cannot be quoted verbatim in a creative without Sam's tap (recorded as an `actions` row of type `quote_release`).
- **Trigger:** event-driven per the cross-cutting decision. A vault change event, a quiz submission event, or a watcher finding event triggers extraction for that source only. Each row is deduplicated by `source_ref` + normalised phrase, so nothing is counted twice.

**Rejected**

- Pain/objection summaries as a second artefact. Rejected: doubles review load; phrases drop straight into hooks.
- Fixed weekly/daily/on-arrival cadence. Rejected in favour of events.

**Schema changes (fold into 0001)**

- `voc_phrases`: add `source_ref text`, `source_weight int default 1`, `visibility text check in ('internal','public') default 'public'`, unique on `(source_ref, phrase_normalised)`.
- New `events` table as above.
- `actions.action`: add `quote_release`.

**Open**

- Vault convention for which notes count (Sam, Friday).
- Vault sync path into the build environment (local folder vs. Obsidian Sync vs. git) — decide Saturday S2.

---

## Component 3: Angle planner

**Decided**

- **Replicate then ablate, not one-variable-at-a-time and not a lottery.** The unit of planning is a *recipe*: the full decomposition of a proven ad — family, variant, hook type, angle, proof type, visual structure, copy structure, copy length, CTA mechanic, offer mechanic. The intel worker must capture the whole recipe; "format + hook" is not enough.
- **A batch is a set of recipes replicated onto our offer**, each as a bundle. Attribution is at recipe level first, then flows to ingredients via `creative_components`.
- **Ablation is the diagnostic.** When our replica underperforms its source by a clear margin at sample size (default: link CTR below 60% of the source's implied benchmark or below the client floor), the loop diffs our creative against the source recipe, lists the ingredients that changed in translation, and spins an ablation batch (3–4 creatives) restoring them one at a time. When the replica matches or beats the source, the recipe is marked `proven` for the ICP and its ingredients get leaderboard credit.
- **Disciplined translation.** When translating a DTC recipe to our offer the planner may change only: the offer, product nouns, VOC phrases, and imagery subject. Carried over exactly: structure, hook type, angle, copy length, visual layout, CTA mechanic. Every translation records `changed_ingredients[]` so the ablation diff is computed, not guessed.
- **Coherence check.** Every translated recipe passes a "translation coherence" hard check in the creative gate: does the structure still make sense with the swapped nouns (no "home grown smartphones"). A fail routes back to the *planner* with the contradiction named, not to the producer, because the fault is recipe choice.
- **Human selection with 4× over-generation.** The planner proposes ~24 ranked recipes (by source strength and family diversity); Sam selects 6, each executed twice → 12 creatives. Each pick is recorded as a `selections` event: proposed set, chosen set, rejected set, optional one-line reason. Selections are training data for the ranker. Under graduated autonomy, once the planner's top-6 matches Sam's picks at the configured rate, selection is promoted to the planner.
- **Spend split:** 70% of daily budget to the current new-recipe batch, 30% to ablations. Ablations run only when a replica has underperformed at sample size; otherwise the 30% goes to the next-ranked new recipes.
- **Planner reads before proposing:** `learnings` (client, ICP, global), `mart_component_leaderboard` for the ICP, `mart_benchmarks` for a cold ICP, `voc_phrases` weighted by source, proven and candidate `patterns`. Cold start on a new ICP is handled by replication: the priors come from the source recipes.

**Rejected**

- One primary variable per batch (default proposal). Rejected: too slow and ignores the free prior that proven ads provide. Kept only as the ablation mechanism.
- Free-form rewriting during translation. Rejected: makes the ablation diff meaningless.
- Planner picks the 6 from day one. Rejected until trust is earned.

**Schema changes (fold into 0001)**

- `patterns`: add recipe fields `proof_type`, `copy_length`, `cta_mechanic`, `offer_mechanic`, `recipe jsonb` (full decomposition), `benchmark jsonb` (implied performance signals from source).
- `briefs`: add `source_pattern_id`, `changed_ingredients text[]`, `kind check in ('replica','ablation')`, `ablation_of_creative_id`.
- New `selections(id, client_id, experiment_id, proposed uuid[], chosen uuid[], rejected uuid[], reason text, selected_by, created_at)`.
- `experiments`: add `budget_share numeric` and `kind check in ('new_recipes','ablation')`.
- `gate_scores.scores`: add dimension `translation_coherence` (hard check, pass/fail).

**Open**

- Underperformance margin for triggering an ablation (default 60% of source benchmark) — tune after batch 2.
- How the intel worker infers a source ad's implied benchmark from Ad Library signals (days running, variant count, engagement where visible) — design in Saturday S2.

---

## Component 4: Creative producer

**Decided**

- **Renderer is an experiment, not a decision.** Two paths are built: (a) HTML templates per family rendered with Playwright, (b) image-to-image generation with the source ad as reference plus a layout-fidelity check. Batch one runs the same six recipes through both where a template exists, so pairs differ only in renderer. `renderer` is a `creative_components` row, so `mart_component_leaderboard` answers which wins. The gate scores both on legibility and layout fidelity before spend.
- **Weekend scope:** three family templates (job photo + bubble, testimonial card, screenshot ad) plus the generation path wired to one model with the fidelity check, so both run on batch one.
- **Imagery is generated, best-in-class only.** No stock, no budget image tools. The image model is a config value because the leader changes monthly; batch one runs two top-tier models side by side inside the renderer experiment. Shortlist to verify Friday: Google Nano Banana line, OpenAI image model, Flux Pro; Ideogram only if text must be generated in-image.
- **People:** generated people allowed; real-person likeness is a gate hard block.
- **Text is ours, never the model's.** The model generates a text-free image; the producer overlays all copy in HTML using the family template and renders with Playwright. Copy and layout are exact; the image is the only moving part. In-image text only when the recipe structure demands it (fake screenshot), and then still composed by us.
- **Copy:** per brief the producer writes primary text (3 lengths), headline (5), hook lines (10), following `references/direct-response-copy.md` (one idea per ad, first-line hook, specificity, CTA matches landing page) and the translation rules from component 3 (only offer, product nouns, VOC phrases, imagery subject may change).
- **Organic:** same recipes rewritten as X posts/threads and LinkedIn posts, sharing the hook bank; stored in `posts` with `creative_id` and `hook_id`.
- **Outputs:** sizes 1080×1080, 1080×1350, 1080×1920 to Supabase Storage; `creatives.asset_urls` holds the URLs; every creative has full `creative_components` (hook, angle, family, variant, template, renderer, image_model, voc_phrase, cta, landing_page, offer) or the gate refuses it.

**Rejected**

- Own phone photos as the primary image source (default). Rejected: generated, best-in-class only.
- Stock imagery. Rejected outright.
- Model-painted text. Rejected: breaks copy-constant ablation.

**Schema changes (fold into 0001)**

- `creative_components.component_type`: add `renderer`, `image_model`, `variant`, `family` (replace `format`).
- `creatives`: add `image_prompt text`, `source_reference_url text`, `fidelity_score numeric`.
- `gate_scores.scores`: add `layout_fidelity` (numeric) and hard block `real_person_likeness`.

**Open**

- Image model shortlist verification and API access (Sam, Friday).
- Fidelity check implementation: vision-model comparison against the source ad, threshold to tune after batch one (Saturday S3).

---

## Component 5: Creative gate

**Decided**

- **Facts always block, automatically.** Hard checks run on every creative and any failure blocks: Meta ad policy, brand hard blocks from config, real-person likeness, translation coherence (routes to planner), missing `creative_components`, landing page mismatch, internal VOC phrase quoted without a `quote_release`.
- **Taste is Sam's, and the gate learns it.** Initially Sam is the taste gate. On every creative the model rubric (hook strength, 3-second clarity, ICP specificity, VOC language present, single CTA, mobile legibility, layout fidelity) scores in *shadow mode*, then Sam gives approve/reject with an optional one-line reason. Both are stored in `gate_scores` (`scored_by='agent'` and `scored_by='sam'`). The taste gate is promoted to blocking when agent verdicts agree with Sam's at the configured rate over a window (graduated autonomy, same rule as every action).
- **Taste is corrected by the market.** The Monday memo reports where Sam's rejections would have out-performed approvals (via ablation or later re-runs) and where rubric dimensions do or do not predict CTR. Quarterly: regress rubric dimensions on link CTR; drop or reweight the ones that predict nothing. Target is Sam's taste corrected by performance, not Sam's taste frozen.
- **Review channel: email first.** When a batch clears fact checks, a `review_ready` event sends an email with each creative inline at mobile size, its source ad, and its recipe. One-click signed approve/reject links per creative write directly to the warehouse and expire after use. Replying to the email with numbered lines is parsed into `gate_scores.feedback`. A review page backed by the warehouse exists for the full view. Slack carries only the count waiting and the link. Sender: transactional email service with Sam's Gmail as reply-to (Gmail connector is the fallback sender).
- **Retry loop:** a fact-check fail goes back to the producer (or planner for coherence) with the feedback object from `content-supervisor` §5.1; max 3 attempts, then it is dropped from the batch and logged.

**Rejected**

- Rubric blocking from day one (default). Rejected: rubric is unvalidated; Sam's taste is the initial filter.
- Review in Drive + Slack. Rejected: verdict friction kills the reason data.

**Schema changes (fold into 0001)**

- `gate_scores`: `scored_by` becomes a required enum (`agent`, `sam`, later other humans); add `verdict text check in ('approve','reject')`, `mode check in ('shadow','blocking')`.
- New `review_tokens(id, creative_id, verdict, token_hash, expires_at, used_at)` for one-click links.
- `events.type`: add `review_ready`, `verdict_received`.

**Open**

- Transactional email sender choice (Resend vs Supabase SMTP vs Gmail connector) — Saturday S4.
- Agreement rate and window for promoting the taste gate (default 85% over 40 creatives) — Sam, before Sunday U4.

---

## Component 6: Launcher (paid, landing, tracking, nurture)

**Decided**

- **Meta structure per offer:** two testing campaigns matching the 70/30 split — *new recipes* and *ablations* — each with **one ad set per recipe** on its own budget so every recipe reaches sample size, both executions as ads inside it. A third **scaling campaign** with campaign budget optimisation holds proven winners only, where Meta is allowed to pick. Broad targeting (geo + age only). All ads created paused; activation follows the trust rule.
- **Conversion event:** optimise for `Schedule` (booked call) from day one. `QuizStart`, `QuizStep`, `QuizComplete` fire as tracked events for funnel visibility. Documented fallback: switch to `QuizComplete` only if bookings stay under 5/week after two weeks.
- **The quiz is the landing page and it lives on our platform.** One small app of ours on a subdomain (`go.upclicklabs.com`), separate from the WordPress brochure site, hosts: quiz funnels per offer, the creative review page (component 5), and later client dashboards. Backed by Supabase. Client funnels run on the same app under client domains via CNAME at onboarding. Rationale: first-party pixel/CAPI match quality, server-side writes to the warehouse, trust, and a product surface clients see.
- **Quiz mechanics:** 3–5 questions, one per screen, progress bar; questions in client config; ad URL carries `utm_content = creative_id`; submission writes a `leads` row with creative attribution, `fbclid`, answers, and a qualification score; free-text answers emit VOC events for component 2. Server-side CAPI on every step. Event testing tool must show green before launch (Launch Gate hard check).
- **Qualification: soft for month one.** Every completer can book; answers set `leads.qualification_score`, visible before the call. Hard mode (disqualifying answers never reach the calendar, `qualified` stage automatic) is turned on once the warehouse shows which answers predict a closed deal.
- **Nurture via Instantly, by lead-stage events:** completed-not-booked within 1 hour → nurture sequence; booked → reminder sequence until the call; no-show → rebook sequence. Quiz starters who never complete are retargeted on Meta only, never emailed. "Push to Instantly" is an action under the trust rule (proposed first, auto once promoted). Replies and bookings flow back to `leads.stage`.
- **Organic:** posts scheduled via Typefully with the same recipe and hook links; publishing is an action under the trust rule.

**Rejected**

- Single campaign with budget optimisation for testing. Rejected: starves creatives before sample size, breaks attribution and the 70/30 split.
- Shallow optimisation events (clicks, LPV, QuizStart). Rejected per the deep-funnel rule.
- Third-party quiz/landing tools. Rejected: tracking quality, data path, trust, ownership.
- Emailing every quiz starter. Rejected: domain reputation.

**Schema changes (fold into 0001)**

- `leads`: add `qualification_score numeric`, `quiz_version text`, `nurture_sequence text`, `instantly_lead_id text`.
- `ad_entities`: add `campaign_kind check in ('new_recipes','ablation','scaling')`, `recipe_pattern_id`.
- `offers`: add `quiz_config jsonb`, `calendar_url`, `funnel_host text`.
- `events.type`: add `quiz_start`, `quiz_step`, `quiz_complete`, `lead_booked`, `lead_no_show`, `lead_stage_changed`.
- `actions.action`: add `push_to_instantly`, `activate`, `publish_post`.

**Open**

- Hosting for the app (Vercel vs Cloudflare Pages vs Supabase Edge) and the `go.` subdomain DNS — Sam, Friday.
- Calendar tool behind the booking step (from component 0) — Sam, Friday.
- Quiz questions v1 for the upClickLabs offer — draft Saturday S3, Sam approves Sunday U1.

---

## Component 7: Performance loop

**Decided**

- **Active lever selection.** Every lever in a platform's chain (Meta: hook rate → link CTR → CPM → conversion rate → cost per booked call) has a benchmark, resolved in this order: (1) our own proven history for the ICP, (2) `mart_benchmarks` cross-client, (3) the source recipe's implied signal, (4) a fixed floor from client config. The loop walks the chain top down and stops at the first lever below its benchmark at sample size. That lever becomes `campaigns.active_lever`, with the reason written to the warehouse. One active lever per campaign at a time. The terminal metric never changes without a human.
- **Sample size:** default 2,000 impressions per creative for CTR-stage levers; for conversion-stage levers, the sample is clicks (default 100) and bookings are evaluated at campaign level, not per creative, until volume allows.
- **Kill / scale rules** (from PLAN.md, now under the trust rule): kill when impressions ≥ sample and link CTR < floor, or CPL > 2× target after 3× target spend; scale (+20%, move to scaling campaign) when CPL ≤ target after ≥5 bookings. Every decision is an `actions` row with the evidence snapshot; rules are back-tested against `ad_metrics_daily` before thresholds change.
- **Learnings, three tiers.** *Proposed*: written whenever a recipe or ingredient beats or misses its benchmark at sample size, with effect size and sample. *Supported*: same direction holds across two more creatives, or one ablation confirms it. *Global*: holds across three clients. Proposed learnings are visible to the planner at reduced weight. A batch that reaches sample size and produces zero proposed learnings raises a warning in the check-in.
- **Daily check-in: one message, five parts, in order.** (1) Actions waiting for Sam's tap, one-line reason each, approve/reject links. (2) Actions the system executed on its own since yesterday. (3) Active lever per campaign and whether it moved. (4) New proposed learnings, one line each. (5) Warnings: failed source, budget cap, blocked batch. Anything else goes to the Monday memo. Delivered by email (same mechanism as reviews); Slack carries only the count and link.
- **Monday memo:** learnings promoted or refuted, taste-vs-market report (component 5), variant-to-family promotion proposals (component 1), next batch's proposed recipes for selection (component 3).
- **Write-back:** proven internal recipes go to `patterns` with `origin='internal'`; retired families to `learnings` with scope `icp`; every kill/scale to `actions`.

**Rejected**

- "Worst number today" as the lever picker. Rejected in favour of ordered benchmarks and top-down chain walk.
- Free-text learnings. Rejected; learnings are structured rows with evidence and tier.
- A check-in that reports everything. Rejected; five parts only.

**Schema changes (fold into 0001)**

- New `campaigns(id, client_id, offer_id, platform, kind, external_id, terminal_metric, active_lever, active_lever_reason, active_lever_since)`; `ad_entities.campaign_id` becomes a FK to it.
- New `benchmarks(id, client_id, icp_id, lever, value, source check in ('own','cross_client','recipe','floor'), sample, computed_at)`.
- `learnings.status`: `proposed | supported | global | refuted | retired`; add `effect_size numeric`, `sample int`, `direction check in ('beat','miss')`.
- `events.type`: add `sample_size_reached`, `lever_changed`, `checkin_sent`.

**Open**

- Conversion-stage sample sizes (100 clicks default) — tune after batch 2.
- Monday memo delivery time and whether it doubles as the recipe-selection email — Sam, Sunday U4.

---

## Component 8: Growth warehouse

Design in `WAREHOUSE.md` and `warehouse/schema.sql` stands; these decisions close what it left open. All "schema changes (fold into 0001)" blocks from components 1–7 are applied before the first migration runs.

**Decided**

- **Clients never touch the database.** They see their funnel, creatives, and leads through the app on our platform (`go.upclicklabs.com`). Raw rows and assets are exportable on request; we generate the export. Row-level security is on from day one as a safety net, not as the product surface. Pipeline scripts use the service role.
- **Benchmarks are ours.** Cross-client benchmarks are aggregated and anonymised and belong to upClickLabs; client contracts say so. Clients own their raw data.
- **Schema growth rule, three tiers.** (1) Raw payloads always land in `raw_ingest`; nothing is lost. (2) A field a worker needs today goes into the entity's JSONB column (`config`, `spec`, `evidence`, `recipe`, `payload`) with the key documented in `warehouse/schema-notes.md`. (3) When the same key is read by a second worker or a mart, it graduates to a real column via a numbered migration. Never a Supabase UI edit, never a markdown file as the system of record. The Monday memo lists JSON keys read twice and due for promotion.
- **Storage:** Supabase Postgres + pgvector; Supabase Storage for rendered creatives and generated images; `WAREHOUSE_URL` and service key in env only.
- **Access paths:** `warehouse/client.py` for scripts; Postgres MCP for Claude's ad-hoc and planner queries; canonical queries in `warehouse/queries/`.
- **Retention:** raw 12 months; entities, metrics, events, learnings forever. Daily Supabase backup plus weekly `pg_dump` to object storage.

**Rejected**

- Per-client databases. Rejected: no client DB access, so isolation is RLS + app scoping.
- Ad-hoc JSON as permanent home for fields. Rejected via the promotion rule.

**Open**

- Export format for client data requests (default: CSV per table + asset zip) — week 2.
- Whether `events` needs partitioning by month from day one (default no; revisit at 1M rows).

---

## Component 9: Orchestrator

**Decided**

- **The runtime is ours.** The reactor is an always-on service on our platform (week 3), consuming the `events` table and calling models per task through their APIs: **Grok as the watcher** (competitor watch, ICP feed and trend mining, buying triggers later), **Claude for planning, copy, and the gate** (the skills in this repo via the Agent SDK), **best-in-class image models** for pictures. This weekend, Claude Code routines and webhook-triggered sessions stand in for the reactor; the warehouse carries state between wakes, so nothing in the skills changes when the reactor moves.
- **Single executor enforces trust.** Workers never perform side effects. They write *proposed* `actions`. One executor inside the orchestrator reads proposed actions, checks the action type's trust level and approval counters, and either executes (marking `applied`) or routes the action into Sam's check-in. Every side effect — launch, activate, kill, scale, publish, push to Instantly, send email, quote release, taste promotion — goes through this path. **Promotions to a higher trust level are themselves actions only Sam can approve.**
- **Three brakes.** (1) A pause flag per client and one global, settable from the check-in email, Slack, or the app; the executor checks it before every side effect. (2) Automatic pause when daily spend exceeds the cap by 20%, when the same action fails 3 times, or when any worker's error rate spikes. (3) A spend ceiling on the Meta ad account set in Business Manager, the brake that works when our code does not.
- **Reactor loop:** read unprocessed events → coalesce per source over the window → dispatch to the worker for that event type with a per-worker daily budget → workers write entities and proposed actions → executor applies or routes → check-in composed from `actions`, `campaigns.active_lever`, `learnings`, and warnings.

**Rejected**

- Grok (or any vendor agent product) as the runtime. Rejected: the orchestrator holds the gates and trust logic and must live on our platform; model-per-task needs a neutral runtime. Grok is a first-class watcher, not the host.
- Per-worker trust checks. Rejected: one bug spends money; single executor instead.

**Schema changes (fold into 0001)**

- `actions`: add `trust_level_at_proposal`, `routed_to_human boolean`, `executor_run_id`.
- New `trust_levels(client_id, action_type, level check in ('propose','execute'), threshold int, approvals_unchanged int, promoted_at, promoted_by)`.
- New `pause_flags(scope check in ('global','client'), client_id, paused boolean, reason, set_by, set_at)`.
- New `worker_runs(id, worker, trigger_event_ids uuid[], started_at, finished_at, tokens_used, api_calls, status, error)`.

**Open**

- Reactor hosting when it moves into the app (same host as the app; decide with the app hosting choice) — Sam, Friday.
- Error-rate spike definition for auto-pause (default: >30% of a worker's runs failing over 1 hour) — tune week 2.


---

## Crucible amendments (2026-09-02)

Three adversarial reviews (economics, safety, feasibility) produced 40 findings, consolidated in `CRUCIBLE.md`. Twenty-four amendments are applied to `ARCHITECTURE.md` v1.1, `warehouse/schema.sql`, `warehouse/0002_roles.sql`, and `PLAN.md` v1.1. Six of them reverse choices made above and stand as v1.1 defaults **pending Sam's veto**:

| # | Component | Reversed | Now |
|---|-----------|----------|-----|
| V1 | C3, C6 | 6 recipes × 2 = 12 creatives at $30/day | capacity-derived batch (≈4 creatives/week at $30/day); batch one = 3 recipes × 2 = 6, Sam picks 3 of 12; or raise budget to ~€90/day |
| V2 | C6 | optimise ad sets for `Schedule` day one | testing ad sets optimise for `QuizStart`; `Schedule` is the warehouse-measured terminal metric; promote the Meta event with volume |
| V3 | C4 | both renderers + two image models inside batch one | renderer and image model are between-batch factors; in-batch only via Meta A/B tool |
| V4 | C5 | email review with one-click GET links this weekend | chat verdicts this weekend; email in week 2 with POST-confirmed tokens; spend approvals behind a session; never in Slack |
| V5 | C4 | testimonial-card template with generated people | testimonial/quote families hard-blocked without a real client's `quote_release` and no depicted person |
| V6 | C0 | 250 USD/month cap, Grok wk2, Instantly day one | staged stack; Grok wk3 with $/day budget; Instantly at ≥10 leads/week; Sam to raise cap to ~$500 or accept slower cadence |

The remaining amendments (A1–A24 in `CRUCIBLE.md` §2) add enforcement, statistics, compliance, and scope discipline without reversing a decision. Schema changes listed in the component blocks above are now folded into migration 0001; the "fold into 0001" notes are historical.
