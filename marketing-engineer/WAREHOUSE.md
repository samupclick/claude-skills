# Growth Warehouse — the compounding asset

**Status:** Design v0.1 (2026-09-02). **Superseded in detail by `warehouse/schema.sql` (migration 0001) and `warehouse/0002_roles.sql`**, which carry every decision from `DECISIONS.md` and every amendment from `CRUCIBLE.md`. Read this file for the *why*; read the SQL for the *what*. Known drift: §1 and §3.2 predate the two-level taxonomy, the recipe split, the actions state machine, roles, PII isolation, and the deferral of `events` to week 3.
**One line:** every input the agents consume and every output they produce is written to one queryable store, decomposed into components, stamped with time and client, and joined to outcomes. Skills stay generic; the knowledge lives here.

---

## 1. Why a warehouse and not a folder of markdown

Files in `patterns/` and `state/` capture what happened. They do not let an agent ask, in one call, "for B2B service ICPs, which hook type has the best link CTR across every batch we have ever run, and which VOC phrases were in those hooks?" That question is the whole business. Answering it requires:

1. **Decomposition.** A creative is not a row, it is a bundle of components (hook type, angle, format, template, VOC phrases, CTA, landing page). Performance must be attributable to components, or nothing generalises past the ad that got lucky.
2. **Joins to outcomes.** CTR is a proxy. The asset is ad → lead → booked → qualified → closed → revenue, attributed back to the component mix that produced it.
3. **Cross-client priors.** Client five should start from what clients one to four taught us. That is the agency moat and it only exists if data from every client lands in the same schema.
4. **Append-only history.** Metrics are snapshotted daily, never overwritten, so "what did we believe on day 3 vs day 30" is answerable and kill/scale rules can be back-tested.
5. **Retrieval.** Hooks, copy, VOC phrases, and swipe patterns are embedded so planners retrieve semantically ("our best hooks near this angle"), not by tag match alone.

---

## 2. Storage decision

**Recommendation: Postgres on Supabase, with pgvector, plus Supabase Storage for rendered creatives.**

| Option | Verdict | Why |
|--------|---------|-----|
| **Supabase Postgres + pgvector** | **Pick this** | SQL for agents and humans, JSONB for raw payloads, vectors in the same store, row-level security per client if clients ever get read access, free tier is enough for a year, Postgres MCP exists so Claude can query it directly, and a dashboard can sit on the views later. |
| DuckDB + parquet in the repo | Fallback | Zero infra and great for analysis, but no concurrent writers from routines, no vectors without extensions, and binary files in git compound badly. Use it for offline analysis exports, not as the system of record. |
| BigQuery / Snowflake | No | Cost and ceremony for a dataset that will be under 10 GB for a long time. |
| Notion | No (as warehouse) | Notion stays the human job board via `agency-sop`. It is not queryable at component level and cannot hold metrics history. |
| Markdown in git | Derived only | Memos, briefs, skills, and the schema itself are versioned in git. Data is not. |

Secrets stay in env (`WAREHOUSE_URL`), never in config or git.

---

## 3. Data model

Three layers. Plain names, not medallion jargon, but the idea is the same.

```
RAW        verbatim payloads, one row per fetch, JSONB, never edited
   │
ENTITIES   the things we reason about: clients, offers, ICPs, creatives, components, ads, posts, leads, learnings
   │
MARTS      SQL views the agents and dashboard read: leaderboards, benchmarks, phrase frequency, experiment results
```

### 3.1 Raw

One table, `raw_ingest`: `source` (meta_insights, meta_ad_library, scrapecreators_tiktok, x_posts, reddit, g2, gong, typeform…), `client_id` (nullable for market-wide pulls), `fetched_at`, `external_id`, `payload` JSONB. Every script writes here first, then normalises. If a normaliser has a bug we re-run it from raw.

### 3.2 Entities (v1, this weekend)

| Table | What it holds | Compounds how |
|-------|---------------|---------------|
| `clients` | one row per account, including upClickLabs | every other row carries `client_id` |
| `offers` | promise, price anchor, proof points, landing page | outcomes attribute to an offer, not just a client |
| `icps` | role, company type, industry, geo, size band | the key for cross-client benchmarks |
| `voc_phrases` | verbatim phrase, category (pain / outcome / objection), source, frequency, embedding | the language bank; usage in winning creatives raises its weight |
| `patterns` | external swipe entries and our own proven formats: format, hook type, angle, visual + copy structure, source, days_running, `proven`, embedding | the format library; every batch adds internal patterns with numbers |
| `hooks` | the hook line text, hook type, embedding, origin (external pattern or ours) | a reusable hook bank with performance attached |
| `briefs` | one per cell of a test matrix: angle, format, hook, VOC phrases, visual spec, CTA | the plan of record for each creative |
| `creatives` | the produced unit: copy fields, template, asset URLs, `brief_id`, batch, status | the thing that gets shipped |
| `creative_components` | (creative_id, component_type, component_ref) rows: hook, angle, format, template, voc_phrase, cta, landing_page | **the attribution key.** performance joins through here |
| `gate_scores` | rubric dimension scores, policy flags, pass/fail, attempt number | tells us which rubric dimensions predict performance, so the rubric itself improves |
| `ad_entities` | Meta campaign / ad set / ad ids mapped to `creative_id` | the join from platform to our model |
| `ad_metrics_daily` | one row per ad per day: impressions, reach, clicks, link clicks, spend, leads, schedules, ctr, cpm, cpl, frequency | append-only performance history |
| `posts` | organic post: channel, text, creative_id if reused, external id, posted_at | organic side of the same components |
| `post_metrics_daily` | impressions, engagements, reposts, replies, profile clicks per post per day | virality signal history |
| `leads` | lead with UTM / fbclid attribution to `ad_id` or `post_id`, quiz answers, stage (new / booked / qualified / closed), value | closes the loop to revenue |
| `actions` | kill / scale / relaunch with rule that fired, evidence snapshot, who approved | auditable automation; lets us back-test rules |
| `learnings` | hypothesis text, scope (client / icp / global), evidence (experiment refs, effect size, sample), confidence, status (proposed / supported / refuted), embedding | **the memory the planner reads first.** agents write it, humans can edit it |
| `experiments` | batch-level: what was varied, start/end, primary metric, result summary | groups creatives into tests so effect sizes are computed properly |

### 3.3 Marts (views, v1)

| View | Answers |
|------|---------|
| `mart_creative_performance` | per creative, latest and cumulative metrics joined to all its components |
| `mart_component_leaderboard` | per client and per ICP: CTR, CPL, lead rate by hook type, angle, format, template, VOC phrase, with sample sizes |
| `mart_hook_leaderboard` | hook lines ranked by link CTR with n, filterable by ICP |
| `mart_voc_frequency` | phrase frequency by source, and lift when used in a creative vs not |
| `mart_benchmarks` | cross-client medians by industry × format × objective. **This is the asset clients cannot build themselves.** |
| `mart_kill_scale_candidates` | ads meeting kill or scale thresholds today, with the evidence, for the daily routine |
| `mart_funnel` | ad → lead → booked → qualified → closed per creative, offer, and client |

---

## 4. How the agents use it

```
planner   READS  learnings, mart_component_leaderboard, mart_benchmarks, voc_phrases, patterns, hooks
producer  WRITES briefs, creatives, creative_components, hooks
gate      WRITES gate_scores
launcher  WRITES ad_entities, posts
insights  WRITES raw_ingest → ad_metrics_daily, post_metrics_daily, leads
loop      READS  mart_kill_scale_candidates, mart_funnel   WRITES actions, learnings, patterns (internal, proven)
```

Two access paths:

1. **Scripts** use a thin Python client (`warehouse/client.py`, psycopg + one helper per table). All pipeline scripts go through it. No script writes files as the system of record.
2. **Claude directly** uses the Postgres MCP for ad-hoc analysis and for the planner's retrieval queries. The orchestrator skill documents the canonical queries so they are reproducible.

Rule for every skill: **read learnings before planning, write learnings after measuring.** A cycle that does not write a learning row is a bug.

---

## 5. Compounding mechanics, made explicit

| Mechanic | Implementation |
|----------|----------------|
| Component attribution | `creative_components` is mandatory at creation; the gate fails a creative that has no hook, angle, and format rows |
| Outcome join | landing page carries `utm_content = creative_id`; quiz submits write to `leads` with the attribution; CRM stage updates flow back via a weekly sync |
| Cross-client priors | `mart_benchmarks` keyed on `icps.industry` and `patterns.format`; the planner's first query on a new client is the benchmark for its ICP |
| Learning lifecycle | proposed by the loop → supported / refuted when n crosses a threshold → global when it holds across 3+ clients |
| Rubric calibration | quarterly: regress gate dimension scores on link CTR; drop or reweight dimensions with no predictive value |
| Rule back-testing | `actions` stores the evidence snapshot; replay kill/scale rules against `ad_metrics_daily` history before changing thresholds |
| Semantic retrieval | embeddings on `hooks`, `voc_phrases`, `patterns`, `learnings`; refresh on insert |
| Beyond ads | week 3–4: `content_pieces`, `content_metrics_daily`, and `ai_citation_checks` from the AEO pipeline land in the same store, so articles and ads share ICPs, VOC, and learnings |

---

## 6. Governance

- `client_id` on every row. Row-level security policies from day one, even though only we read it now.
- Leads hold PII. Restricted role for anything that reads `leads.email` or `leads.phone`; marts expose counts and stages only.
- Retention: raw payloads 12 months, entities and metrics forever, since they are the asset.
- Backups: Supabase daily plus a weekly `pg_dump` to object storage.
- Schema versioned in `warehouse/migrations/`. No manual edits in the Supabase UI.
- Clients own their raw data. Benchmarks are aggregated and anonymised across clients; that aggregate is ours. Put this in client contracts.

---

## 7. Weekend scope (v1)

Build on Saturday morning before any producer code, because every later script writes to it.

- [ ] Supabase project, `pgvector` enabled, `WAREHOUSE_URL` in env
- [ ] `warehouse/migrations/0001_init.sql` applied (see `warehouse/schema.sql`)
- [ ] `warehouse/client.py` with insert helpers and the six planner queries
- [ ] Seed: `clients` (upClickLabs), one `offers` row, one `icps` row
- [ ] Postgres MCP connected so Claude can query it
- [ ] Every Saturday and Sunday script writes to the warehouse, not to files
- [ ] Sunday evening: `mart_component_leaderboard` returns rows for batch 1 and the loop writes at least one `learnings` row

Deferred: embeddings refresh job (week 2), CRM sync (week 2), AEO tables (week 3–4), dashboard (week 4).
