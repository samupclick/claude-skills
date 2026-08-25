# NZ Directory + Newsletter — Business Blueprints & AI-Native Build Plan

**Prepared:** 25 August 2026 · Builds on run 1 (`nz-retirement-directory-feasibility.md`) and run 2 (`nz-directory-newsletter-best-fit.md`)
**Scope:** the two winning sectors turned into concrete businesses, plus one shared AI-native build plan: tech stack, timeline, and the problems to avoid.

---

## 0. How to run this (the sequencing decision)

**Do not build two full products at once.** The single biggest failure mode for a solo founder is splitting focus across two directories. The recommended structure:

- **Primary build — Business A (property management / landlords):** the full AI-native directory + newsletter. Best standalone economics, biggest payer pool, durable audience, perfect fit for programmatic/AEO skills.
- **Side asset — Business B (aging-sector trade weekly):** launch as a **newsletter only** — no directory at first. The 2026–27 reform window (RV Amendment Bill at select committee, the Aug 2026 aged-care reform report) is the audience-building moment and it's happening *now*; an AI-assisted weekly costs ~3–4 hrs/week to run. The supplier directory and the run-1 consumer directory get built **only after** founding sponsors commit (kill criteria below).

Both businesses share one platform, one data-plant architecture, and one operating rhythm — that's the AI-native leverage.

---

## 1. Business A — the PM data layer (primary build)

*Working names (domain/trademark unchecked): PM Index · RentSense · The Landlord Brief (newsletter).*

### What it is

The neutral authority on **"which property manager, at what fee, and are they any good"** — a question ~410,000 rental-property owners face and nobody answers with data.

**Product surface:**
1. **Directory:** every PM company in NZ (est. 1,500–2,500 entities after dedup), seeded from Companies Office + own collection. Profile: suburbs served, portfolio size, **full fee schedule** (management %, letting, inspection, admin, maintenance margin), compliance posture, reviews, response record.
2. **Fee database — the moat.** Mystery-shopped + crowdsourced ("share your PM fee" flow for landlords, anonymised into benchmarks). Published as regional fee benchmarks. Nobody has this; every landlord wants it; every journalist will cite it.
3. **Programmatic data pages:** suburb/district rent & bond pages from Tenancy Services' monthly open data (back to 1993) — "Median rent in Papanui", "Bond stats: Tauranga". Hundreds of pages of citable, auto-refreshing, schema-marked stats.
4. **Tools:** "what should property management cost" calculator · rent-appraisal estimator · healthy-homes compliance checklist · **switch-PM kit** (letter templates, notice periods) — the switch kit is the lead-capture moment.
5. **Newsletter — The Landlord Brief (weekly):** law changes, a Tenancy Tribunal decisions digest (decisions are published — an AI-summarisation goldmine no one mines), bond-data moves, one deep explainer. This is the retention asset that turns one-off searchers into an owned audience.

**Audience:** NZ's ~250–300k landlord entities — both the ~42% using PMs (switch candidates) and self-managers (future customers + tool users).

### Revenue lines (sequenced — do not start selling before month 4)

| # | Line | Pricing | When |
|---|---|---|---|
| 1 | Verified/featured PM profiles | $99–$249/mo ($1,200–$3,000/yr), 2–3 tiers | Month 4+ |
| 2 | Qualified switch leads | $100–$200/lead (below a PM's ~$2–3k/yr landlord value) | Month 6+ |
| 3 | Newsletter sponsorship | $500–$1,500/send as list passes 3–5k (proptech, landlord insurance, tenant screening) | Month 6+ |
| 4 | Annual "State of NZ Property Management" report | Free (PR/link asset); sponsored edition later | Month 10 |
| 5 | Affiliate (landlord insurance, self-manager software) | Modest, additive | Opportunistic |

**P&L sketch (estimates, GST-excl):**

| | Year 1 | Year 2 | Year 3 |
|---|---|---|---|
| Featured profiles | $15k (15 × ~$1k avg part-year) | $75k (50 paying) | $150k (85–100 paying) |
| Leads + sponsorship | $10k | $50k | $110k |
| Other | $2k | $10k | $25k |
| **Revenue** | **~$27k** | **~$135k** | **~$285k** |
| Cash costs (infra, LLM, email, legal, data) | $8–12k | $15–20k | $25–35k |
| **Margin (pre-founder-time)** | ~$15k | ~$115k | ~$250k |

**KPIs:** fee datapoints in DB (target 300 by month 6, 1,000 by month 12) · newsletter subs (1,000 / 3,000 / 6,000 at months 6/12/24) · indexed pages + AI-citation share · paying PMs · leads delivered.

---

## 2. Business B — the aging-sector operation (newsletter-first side asset)

*Working names: The Village Wire · Aged Care Weekly NZ.*

### What it is

The independent Friday email NZ's aged-care and retirement-village sector doesn't have (INsite dead, AgedPlus bi-monthly print, The Weekly Source is Australian): the week's news curated with judgment, people moves, operator results, a regulation tracker (RV Amendment Bill, aged-care reform implementation, funding review), and a jobs block. Audience: ~2,000–5,000 executives, owners, suppliers, investors, policymakers — a career-long, zero-churn readership.

**Phases, each gated:**
1. **Phase 1 (now): the weekly.** 20–30 issues through the reform cycle. Free. Built with the shared AI pipeline (~3–4 hrs/week of founder time).
2. **Phase 2 (month 4–6, only if gate passes): monetize.** Founding sponsorships (5–10 × $10–20k/yr: care software like VCare/eCase, catering, laundry, construction, recruiters — all verified active sector advertisers), supplier directory ($1k/yr listings, villages.com.au-priced), jobs board ($150–$300/listing into the email).
3. **Phase 3 (year 2, optional): the consumer side.** The run-1 pricing-transparency directory (villages + ARC + home-care section) — now with operator relationships already built via the B2B side. Disclosed church/state split between editorial and listings sales.

**Gate at month 6 (kill criteria):** ≥1,000 subscribers with >45% open rate AND ≥2 sponsors committed (or $20k+ pipeline). Miss both → archive gracefully; the research and audience knowledge still feed the agency.

**P&L sketch if it passes:** Y1 $20–40k (2–3 founding sponsors, part-year) → Y2 $90–150k (5–7 sponsors + listings + jobs) → Y3 $150–250k (add report/event/consumer side). Costs are shared with Business A's platform; incremental cash cost <$3k/yr.

---

## 3. The AI-native build (one architecture, both businesses)

### Principles

1. **A data plant, not a blog.** The core asset is a structured Postgres database of entities and facts (providers, fees, locations, reviews, news events, sources). Every page, table, JSON-LD block, and newsletter section is a *projection* of the database. Nothing is hand-maintained twice.
2. **Agents draft, humans publish.** Every LLM output lands in a review queue. Nothing reaches the public site or the send button without a human pass. This is both the quality bar and the legal/E-E-A-T defence.
3. **AEO-first, not bolted on.** Schema, citation-ready stat blocks, machine-readable endpoints and llms.txt ship in week 1 — this is the existing agency skillset (`aeo-entity-master`, `entity-schema-validator` in this repo) applied to owned assets.
4. **Boring tools, custom pipelines.** The differentiation is the data and editorial judgment — never a custom CMS.

### The stack (opinionated, solo-friendly, ~$150–$400/mo all-in)

| Layer | Choice | Why |
|---|---|---|
| Site | **Astro** on **Cloudflare Pages** | Content-first, fastest to ship programmatic pages, near-zero hosting cost, excellent Core Web Vitals out of the box |
| Database | **Supabase (Postgres)** | Entities, fees, reviews, news items; auth + row-level security for claimed profiles; generous free tier |
| Search/filter | Postgres full-text first; **Typesense** when filters get heavy | Don't buy search infra before you have traffic |
| Pipelines | **Claude API + tool use** (Python workers) on **GitHub Actions cron**; graduate to Anthropic **Managed Agents scheduled deployments** if you want the loop + sandbox hosted for you | Deterministic scheduling, versioned in git, no servers to babysit |
| Pipeline models | **Claude Opus 5** (`claude-opus-5`, $5/$25 per MTok) for drafting, judgment and extraction quality; **Claude Haiku 4.5** ($1/$5) for high-volume classification/triage; **Batch API for every nightly job — 50% off** | Right tier per stage; batch pricing makes nightly sweeps ~$30–150/mo total |
| Scraping/ingest | **Playwright** workers + official CSVs/APIs; PDFs (disclosure statements, Tribunal decisions) parsed by Claude directly | PDFs are the moat — LLMs read what competitors won't manually transcribe |
| Newsletter | **beehiiv** (free to 2,500 subs, growth loops, built-in sponsorship tooling); custom domain + DMARC/SPF/DKIM from day 1; weekly list export to your own DB | Fastest path; the export habit removes lock-in |
| Payments | **Stripe** (subscriptions + invoicing) + **Xero** (NZ GST) | Standard |
| Reviews | Own table + moderation queue: AI pre-screen (defamation/authenticity flags) → human approve; email-verified reviewers; provider right-of-reply | Legal posture built into the product |
| Analytics | **Plausible** + Google Search Console + a monthly scripted **AI-citation audit** (20–30 prompts across ChatGPT/Perplexity/Gemini/AI Overviews, logged to the DB) | You optimise what you measure — including the AEO channel |

### The agent pipelines (each: trigger → model → human gate)

| Pipeline | Cadence | What it does | Gate |
|---|---|---|---|
| **Register watch** | Nightly (batch) | Diff Companies Office / official CSVs against the entity DB; propose adds/edits/closures | Auto-apply trivial; queue the rest |
| **Fee extractor** | On new doc | Parse PDFs (PM fee schedules; RV disclosure statements) into normalized fee rows with source + date | Human approves each row |
| **News desk** | Daily scan, weekly assembly | Monitor RSS/Beehive/HUD/Tenancy Services/NZX/Google News queries; cluster, dedupe, draft newsletter items *with citations* | Founder edits every issue — the voice is human |
| **Tribunal digest** (A) | Weekly (batch) | Summarise new Tenancy Tribunal decisions; extract themes for the Brief | Editorial pass |
| **Review screener** | On submission | Flag defamation risk, authenticity signals, PII | Human approves every review |
| **QA sweep** | Weekly (batch) | Dead links, stale facts (>N days unverified), schema validation, internal consistency | Fix queue |
| **Citation audit** | Monthly | Run the prompt panel, log which sites AI assistants cite | Informs content roadmap |

**What NOT to automate:** outbound sales and sponsor relationships (humans buy from humans), review authenticity judgment, final editorial voice, and anything that sends email to a list.

### The AEO layer (the unfair advantage)

- JSON-LD per entity (Organization/LocalBusiness/Service + FAQPage/Dataset where earned) generated from the DB — run through the repo's own `entity-schema-validator`.
- Every stat published with a visible date + source line (citation-ready for AI answers).
- Machine-readable endpoints: per-region CSV/JSON of fee benchmarks and rent stats; `llms.txt`; stable entity URLs.
- Named human author + methodology pages (E-E-A-T armour — the anonymous compareretirementvillages.co.nz counter-example).

---

## 4. Timeline

### Weeks 0–2 — validation gates (kill before you build)
- **A:** mystery-shop 20 Auckland PM fee schedules · 5–10 PM pricing calls (signal, not closing) · NZ keyword pull · confirm regulatory status with HUD/Tenancy Services (run-2 flagged conflicting signals) · backlink audit of top5.nz & propertymanagementguide.co.nz.
- **B:** draft issue #0 · LinkedIn-size the executive audience · request AgedPlus media kit · list 15 target founding sponsors.
- **Kill criteria:** A dies if PMs uniformly refuse to discuss placement at any price; B dies later (month-6 gate) — issue #0 costs almost nothing.

### Weeks 3–8 — the data plant + first sends
- Wk 3–4: Supabase schema (entities/fees/sources/reviews/news) · seed A's entity DB · bond-data ingestion · Astro site scaffold with schema layer.
- Wk 5–6: ship 3 programmatic page types (city PM directory pages, suburb rent/bond pages, fee-guide skeleton) · beehiiv + domain auth (start warming) · **The Landlord Brief #1**.
- Wk 5 (parallel, timeboxed 4 hrs/wk): **Village Wire #1** — the reform cycle won't wait.
- Wk 7–8: fee database v1 live (first ~100 mystery-shopped datapoints) · switch-PM kit + calculator (lead capture on) · review system with moderation queue.

### Months 3–6 — audience before revenue
- Distribution push: landlord Facebook groups, r/PersonalFinanceNZ, property-accountant/adviser partnerships, PR the fee database ("NZ's first property-management fee index") to interest.co.nz/OneRoof/Stuff.
- Targets: 1,000+ Brief subs, 300+ fee datapoints, reviews trickling, first AI-citation appearances.
- Month 4: open monetization — claimed/verified profiles, first 10–15 featured PMs at founder pricing.
- Month 6: **Business B gate** (≥1,000 subs, >45% opens, ≥2 sponsors) → fund the supplier directory + jobs board, or archive.

### Months 7–12 — monetize + moat
- Leads product live (tracked, capped, disclosed) · sponsorship slots in the Brief · annual report #1 · 3,000+ subs · 1,000+ fee datapoints · target $3–8k MRR exiting month 12.

### The weekly operating rhythm (steady state, ~12–15 founder-hours/wk)
| Day | Block | Hours |
|---|---|---|
| Mon | Pipeline review queues (register diffs, fee rows, reviews) | 1.5 |
| Tue | Content/data: one deep piece or new programmatic page type | 3 |
| Thu | Edit + send The Landlord Brief; Village Wire edit | 3–4 |
| Fri | Sales/partnerships (calls, sponsor pipeline) | 2 |
| Monthly | Citation audit review, KPI review, report chapter | 3 |

---

## 5. Problems to avoid (the field guide)

1. **Focus split.** Two full builds solo = both die. B stays newsletter-only until its gate passes. One primary product.
2. **Selling before traffic (directory cold-start).** Pitching PMs listings in week 2 with zero audience burns the market's small pool of goodwill. Sequence: data → audience → then revenue. Validation calls are for *pricing signal only* — say so on the call.
3. **The AI-slop trap.** Pure programmatic LLM content is exactly what Google's scaled-content-abuse policy targets and what AI engines learn to distrust. Every public page needs a human-reviewed layer, a named author, and a methodology page. AI for structure and data; humans for judgment and voice. (compareretirementvillages.co.nz's anonymity is the cautionary tale *and* your differentiation.)
4. **NZ email law — Unsolicited Electronic Messages Act 2007.** Commercial email needs consent (express or clearly inferable), accurate sender ID, and unsubscribe. **Never scrape emails into a launch blast** — build the list through content, referrals, and one-to-one outreach. Fines are real; sender reputation damage is worse.
5. **Reviews & defamation — NZ has no Section 230.** Hosts can be liable for user reviews once on notice (Murray v Wishart is the leading NZ authority on host liability; the Harmful Digital Communications Act adds a complaints channel). Mitigations that must ship *with* the review feature, not after: pre-publication moderation, evidence-encouraged review policy, provider right-of-reply, fast notice-and-takedown process, and media-liability insurance once revenue starts.
6. **Privacy Act 2020.** Sole-trader PMs and named managers are individuals — profiles about them are personal information. You need accuracy processes, a correction channel, and a privacy statement. Handle "remove me" requests with a policy, not improvisation.
7. **Fair Trading Act.** "Best PM in Auckland" rankings need a defensible, published methodology; paid placement must be clearly labelled and must never contaminate rankings (the Commerce Commission has acted on undisclosed endorsements; A Place for Mom's steering scandal is the category's ghost story). Sponsorship buys visibility, never verdicts.
8. **The Google Places data trap.** Places API terms prohibit storing/republishing Places data as your directory content. Seed from official registers, Companies Office, and your own collection — use Maps only as a live embed/link layer.
9. **Open-data licences.** Tenancy Services / Stats NZ / MoE data is generally CC-BY — attribute it. Check the Companies Office register terms before bulk republication of documents (link to filings rather than mirroring where unclear).
10. **Deliverability debt.** Custom sending domain, SPF/DKIM/DMARC, double opt-in, gradual warm-up from send #1. A weekly that lands in spam is a zero. Export your list weekly — beehiiv/Substack are rented land.
11. **Cadence debt.** Weekly means weekly. The pipeline makes drafting cheap, but the human edit is the bottleneck — protect the Thursday block, batch evergreen sections, and hold two banked back-pocket issues. Never miss two consecutive weeks.
12. **Over-engineering.** No custom CMS, no Kubernetes, no bespoke review platform, no mobile app. The moat is data + trust, not infrastructure. Every hour on infra is an hour off the fee database.
13. **Church/state (Business B).** Selling listings to operators you cover editorially needs a disclosed policy from day 1 — a one-paragraph statement in every issue footer beats a crisis later.
14. **Unmeasured pipelines.** LLM pipelines drift. Keep a small eval set per pipeline (the repo's `skill-creator` eval tooling applies), review a sample weekly, and cache aggressively. Budget guardrail: alert if LLM spend exceeds ~$400/mo — at this scale that signals a runaway loop, not growth.
15. **US-anchored pricing.** NZ operators pay NZ prices: $1–3k/yr listings, $10–20k/yr founding sponsorships, $100–200 leads. Price the market you're in; raise later with proof.

---

## 6. Cost & break-even summary

| | Monthly (steady state) |
|---|---|
| Hosting (Cloudflare, Supabase) | $0–50 |
| beehiiv | $0–100 (scales with list) |
| LLM (Opus 5 + Haiku 4.5, nightly jobs on Batch API) | $50–300 |
| Tools/misc (Plausible, domains, Stripe fees) | $30–60 |
| One-offs Y1: legal review (review policy, T&Cs, privacy statement) ~$3–5k; media-liability insurance from first revenue ~$1.5–3k/yr | — |
| **Total run rate** | **~$150–$500/mo** |

Break-even (cash) at roughly **10–15 featured PM profiles** or **one Village Wire founding sponsor**. Everything past that funds the moat.

---

*Working names are placeholders — check domains, the Companies Register and IPONZ before committing. Figures marked as estimates are modelled from run-1/run-2 verified benchmarks; the validation gates in §4 exist to replace them with real numbers before serious money or time is committed.*
