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
- **Owner:** Sam owns the pipeline. Cadence is a **daily check-in**: the daily routine reports to Slack, Sam approves or rejects proposed actions there, and those decisions feed the trust counters. Monday learnings memo remains the weekly accountability artefact.

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
