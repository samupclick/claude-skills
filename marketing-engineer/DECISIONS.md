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
