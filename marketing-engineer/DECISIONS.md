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
