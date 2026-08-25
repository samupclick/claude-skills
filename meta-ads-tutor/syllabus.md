# Meta Ads Operator Syllabus — Low-Ticket Digital Products

A complete curriculum for running Meta Ads for low-ticket digital products ($27–$57 front-end)
sold through a direct-to-sales-page funnel with order bumps and 1-click upsells, at $250k–$1M/month
spend, measured on 1-Day / 7-Day / 30-Day ROAS.

Built around the operating model: Ad → Sales Page → Checkout (2 order bumps) → 2–3 1-click upsells.
Stack: Meta Ads Manager, Hyros (attribution), HighLevel (checkout/upsells), Claude Code + GitHub +
Cloudflare (sales pages), Atria (creative research). Markets: US, CA, UK, AU, DE.

Each module lists its lessons, the topics to teach, and the **grill focus** — what the learner must
be able to do from memory, under pressure, before advancing.

---

## Module 1 — The Money Math (Unit Economics of Low-Ticket Funnels)

Everything else in the course is a servant of this module. No decision in Ads Manager makes sense
until the learner can do this math cold.

### Lesson 1.1 — The AOV stack and break-even ROAS
- Why a $27–$57 sticker price cannot survive paid traffic on its own: realistic US CPMs, CPCs, and
  sales-page CVRs, and the raw CPA they imply.
- The AOV stack: order bumps (impulse add-ons at checkout, typical 20–40% take rates) and 1-click
  upsells (post-purchase, no card re-entry, typical 5–15% take rates each). Computing funnel AOV
  from take rates.
- Contribution margin for digital products: payment processing, refunds/chargebacks, affiliate
  costs if any; why margin is ~85–90%, not 100%.
- Break-even ROAS = 1 / contribution margin. Max CPA = AOV × margin. Target ROAS for a desired
  net margin.
- **Grill focus:** compute AOV from a take-rate table; compute break-even ROAS and max CPA from
  margin inputs; explain why AOV, not price, is the number that decides scalability.

### Lesson 1.2 — The three ROAS windows and cash velocity
- Why this business runs three ROAS clocks: 1-Day (steering + cash velocity), 7-Day (honest
  profitability after email/cart-recovery tail), 30-Day (backend revenue: buyer-list promos,
  cross-sells, ascension).
- The delayed-revenue multiplier: M7 and M30 (cohort revenue at day N ÷ day-1 revenue) and the
  decision rule: acceptable day-1 ROAS = break-even ROAS ÷ M30 — bounded by cash float.
- Day-1 self-liquidation doctrine: why scaling to $1M/month is financed by same-day revenue, and
  what capital float running below day-1 break-even actually costs.
- Refund lag: why 30-day ROAS must be net of refunds, and how refund timing distorts weekly reads.
- **Grill focus:** given cohort data, compute M30 and the lowest acceptable day-1 ROAS; articulate
  the cash-flow constraint; name which decisions each window drives.

### Lesson 1.3 — MER, attributed ROAS, and the profit ledger
- MER (blended ROAS) = total revenue ÷ total ad spend: the CFO metric that cannot lie.
- Attributed ROAS (platform or Hyros): the operator metric for per-campaign decisions.
- Why they diverge, how to reconcile them, and which one wins an argument.
- A simple daily P&L per funnel: spend, front-end revenue, bump/upsell revenue, refunds, fees,
  contribution profit.
- **Grill focus:** reconcile a scenario where Ads Manager, Hyros, and Stripe all disagree; state
  which yardstick to set targets on and why.

---

## Module 2 — How Meta's Delivery Machine Works

### Lesson 2.1 — The auction and what CPM really is
- Total value = advertiser bid × estimated action rate + user value (ad quality/relevance).
  Why the highest payer doesn't always win.
- CPM as an output, not an input: auction pressure, audience quality, creative engagement, seasonality
  (Q4/BFCM), and market (US vs DE) all move it.
- eCPM decomposition: CPM → CPC (via CTR) → CPA (via CVR). Where a media buyer can and cannot
  intervene.
- **Grill focus:** explain why a better ad gets cheaper delivery; decompose a CPA change into
  CPM / CTR / CVR movements.

### Lesson 2.2 — Pixel, CAPI, and optimization events
- Pixel vs Conversions API; deduplication (event ID), Event Match Quality and what raises it.
- The event funnel: PageView → ViewContent → InitiateCheckout → Purchase. Why this account
  optimizes on Purchase and when (rarely) you'd step down an event.
- Value optimization vs conversion optimization; passing purchase values (including bumps) correctly
  from HighLevel.
- iOS-era reality: modeled conversions, aggregated data, delayed reporting.
- **Grill focus:** diagnose an event-setup problem from symptoms (e.g., purchases in Stripe that
  Meta never saw); defend Purchase optimization vs cheaper events at this AOV.

### Lesson 2.3 — Learning phase, liquidity, and the Advantage+ era
- Learning phase mechanics: ~50 conversions/ad set/week guideline, what actually resets learning,
  "learning limited," and why churning edits burns money.
- Liquidity principle: fewer, bigger ad sets outperform fragmentation; how consolidation feeds the
  algorithm.
- Advantage+ Sales / Advantage+ audience: what Meta's automation now controls, where manual levers
  remain, and how the modern broad-first era changes structure.
- **Grill focus:** list which edits reset learning; argue consolidation vs segmentation for a
  $10k/day account.

### Lesson 2.4 — Attribution windows in Ads Manager
- 7-day click / 1-day view defaults; what view-through actually counts; comparing windows.
- Why in-platform ROAS inflates vs click-based third-party numbers; when 1-day-click reporting is
  the honest steering view for an impulse-purchase funnel.
- **Grill focus:** choose and defend a reporting window for daily decisions in this business.

---

## Module 3 — Tracking & Attribution in Practice (Hyros)

### Lesson 3.1 — Why third-party attribution exists
- Click IDs, UTM discipline, first-party tracking scripts, server-side postbacks; what Hyros
  captures that Meta can't (cross-device, long lags, upsell revenue chains, email-assisted sales).
- Wiring the funnel: UTMs on ads → sales page script → HighLevel checkout/upsell events → Hyros.
- **Grill focus:** trace a purchase's data path end-to-end; name the failure points that create
  "missing" revenue.

### Lesson 3.2 — Reading Hyros without fooling yourself
- Last-click vs scientific/assisted modes; reattribution windows; how Hyros treats upsell revenue
  and refunds.
- Triangulating truth: Hyros vs Ads Manager vs Stripe/HighLevel vs MER — the reconciliation
  hierarchy and acceptable divergence bands.
- Feeding data back: value-based reporting to guide budget decisions per ad, not just per campaign.
- **Grill focus:** given three conflicting numbers, produce the reconciliation and the action.

### Lesson 3.3 — Incrementality basics
- When attribution lies: retargeting take-credit, branded search cannibalization equivalents,
  view-through myths.
- Cheap incrementality checks at this scale: holdout gut-checks, geo splits, spend on/off tests,
  new-customer rate.
- **Grill focus:** design a simple test to prove a campaign type is incremental.

---

## Module 4 — Campaign Structures & Buying Strategies

### Lesson 4.1 — Account architecture
- The two-lane account: testing lane (structured creative testing) and scaling lane (consolidated
  winners). What lives in each and how creatives graduate.
- ABO vs CBO vs Advantage+ Sales: what each controls, when each wins at this spend level.
- Naming conventions and hygiene that make Hyros and reporting usable.
- **Grill focus:** sketch a full account structure for a $300k/month, 3-funnel account and justify
  every campaign's existence.

### Lesson 4.2 — Bid strategies
- Highest volume (lowest cost) as default; cost caps: how they actually bid, spend throttling as a
  signal, cap-setting math off max CPA; bid caps and min-ROAS: what they're for, why most operators
  misuse them.
- Cost-cap testing and cost-cap scaling patterns; when to loosen vs tighten.
- **Grill focus:** set caps for a funnel from its unit economics; explain what a cost-cap campaign
  spending 20% of budget is telling you and what to do.

### Lesson 4.3 — Audiences in the broad era
- Why broad wins at scale for mass-market low-ticket offers; what interests and lookalikes are
  still for (cold-start, new geos, niche angles).
- Advantage+ audience mechanics (suggestions, not constraints); exclusions that still matter
  (buyers within N days) and why over-exclusion hurts.
- Retargeting for a same-day-conversion funnel: small, honest, capped.
- **Grill focus:** defend broad vs a stakeholder demanding interest stacks; size a retargeting
  budget honestly.

### Lesson 4.4 — Geo and placement strategy
- One campaign per tier vs blended geos: CPM/AOV differences across US/CA/UK/AU/DE, currency and
  language implications, when DE needs its own localized funnel and creatives.
- Advantage+ placements vs manual: when feeds/reels-only is defensible; placement-driven creative
  ratios (9:16, 1:1, 4:5).
- **Grill focus:** decide grouped vs split geos for a given budget and explain the tradeoff.

---

## Module 5 — Creative Strategy (The Real Targeting)

### Lesson 5.1 — Angles, hooks, and the creative hierarchy
- Creative is the targeting: how different angles reach different sub-audiences inside broad.
- Hierarchy: concept/angle → hook → format → variation. Why testing new concepts beats testing
  10 crops of one ad.
- Angle sources: pain, desire, curiosity, novelty, identity, proof, us-vs-them, cost-of-inaction.
- **Grill focus:** generate 5 genuinely distinct angles for a given product on the spot; classify
  a batch of ads into concepts vs variations.

### Lesson 5.2 — Research and customer language
- Mining reviews, communities, competitor ads (Meta Ad Library), and Atria for hooks and angles;
  swipe-file discipline.
- Voice-of-customer extraction: turning real phrases into hooks; awareness levels (Schwartz) and
  matching message to awareness.
- **Grill focus:** given raw customer quotes, produce hooks and name the awareness level each
  targets.

### Lesson 5.3 — Formats that print for low-ticket digital
- Statics: ugly ads, screenshot ads, meme ads, benefit-stack ads, founder-note ads — why "native"
  beats polished at this price point.
- Video: UGC talking-head, faceless b-roll + captions, VSL-lite; AI-generated image/video ads and
  where they're credible vs uncanny.
- Anatomy of each: hook (first 1–3s / first line), agitation, demo/proof, CTA; text overlay and
  caption norms.
- **Grill focus:** critique a described ad and fix its weakest element; match format to angle and
  awareness level.

### Lesson 5.4 — Briefs and ad copy
- Writing a creative brief a strategist/editor can execute without you: angle, awareness, hook
  options, structure beats, proof assets, spec list, reference ads.
- Primary text formulas for DR (PAS, star-story-solution, straight benefit stack), headline norms,
  compliance traps for info products (income/health claims, personal attributes).
- **Grill focus:** write a complete brief from a one-line angle; rewrite non-compliant copy without
  killing its punch.

---

## Module 6 — The Creative Testing System

### Lesson 6.1 — Testing architecture
- Dedicated testing campaign design: ABO with fixed budgets vs cost-cap testing; one-concept-per-ad-set
  vs batch testing; Dynamic/Flexible formats and post-ID preservation.
- Throughput math: tests per week needed at $250k–$1M/month; budget per test (spend-to-signal:
  ~1–2× max CPA per ad before verdict).
- **Grill focus:** design the weekly testing calendar and budget for a given spend level; compute
  how much a verdict costs.

### Lesson 6.2 — Win/kill criteria
- Leading indicators (hook rate ≥ ~30%, hold rate, CTR ≥ ~1–2%, CPC, CPM) vs deciding metrics
  (CPA vs max CPA, day-1 ROAS vs target): what each can and cannot tell you.
- Kill rules by spend checkpoint; statistical honesty at low volume — why you judge on cost per
  result, not tiny CVR differences.
- Fatigue signals: frequency, first-time impression ratio, CPA drift; when a "dead" ad gets a
  second life (new market, new placement, new landing page).
- **Grill focus:** given a table of 8 test ads with spend/CPM/CTR/CPA, call kill/iterate/scale on
  each and defend it.

### Lesson 6.3 — Iteration and graduation
- Iteration tree off a winner: new hooks first, then openers, formats, lengths, offers/landers.
- Graduating winners to the scaling lane without resetting what works (post IDs, existing
  engagement); when to duplicate vs move budget.
- **Grill focus:** propose the next 6 iterations for a described winning ad, ordered by expected
  information gain.

---

## Module 7 — Daily Management & Budget Gatekeeping

### Lesson 7.1 — The daily operating routine
- The morning read (post-attribution-settle): spend pacing, day-1 ROAS by funnel, MER, outliers.
  Midday and evening checks. What belongs in a daily log.
- Intervention discipline: acting on 1 bad day vs 3-day trends; why panic edits at 9am on
  yesterday's incomplete data burn accounts.
- **Grill focus:** walk through the exact daily checklist and the thresholds that trigger action
  vs observation.

### Lesson 7.2 — The diagnostic tree
- CPA up — locate the leak: CPM (auction/seasonality/creative decay) → CTR (creative fatigue,
  angle saturation) → CVR (page, offer, traffic quality, tech breakage, price test side effects).
- Funnel-side failure checks first when CVR tanks account-wide: page uptime, checkout bugs,
  tracking outage — before touching campaigns.
- **Grill focus:** given a symptom set, isolate the failing layer and name the first three checks
  in order.

### Lesson 7.3 — Budget gatekeeping
- Being the gatekeeper: reallocation rules (cut X% after N days below target; scale winners
  20–30%/day vs doubling; floor/ceiling budgets per funnel).
- Portfolio thinking: spend split across proven winners / iterations / new concepts (~70/20/10);
  protecting testing budget when the account has a bad week.
- Writing decisions down: a decision log with hypothesis and review date, so optimization is
  falsifiable, not vibes.
- **Grill focus:** rebalance a described 5-campaign portfolio after a rough week, with numbers.

---

## Module 8 — Scaling to $1M/Month

### Lesson 8.1 — Vertical scaling mechanics
- Budget-raise cadence on winners (20–30% steps vs cost-cap "uncapped budget" scaling); why CPA
  rises with scale (auction depth) and planning margin for it.
- Learning-phase-safe scaling: duplicating into CBO, budget ramps, avoiding structure churn.
- **Grill focus:** take a winning ad set from $500/day to $5k/day on paper, step by step, with
  expected metric drift.

### Lesson 8.2 — Horizontal scaling
- New angles > new audiences: creative-led scale; new funnels/offers as the real unlock; new geos
  (DE localization: translated funnel, native creatives, VAT/pricing).
- Scheduling and dayparting myths at scale; account caps, spend limits, and working with Meta reps.
- **Grill focus:** given a plateaued account, propose the horizontal expansion sequence and the
  expected contribution of each move.

### Lesson 8.3 — Volatility and risk at scale
- Why $30k+/day accounts swing: auction volatility, attribution lag, creative cliff. Managing the
  CEO's expectations with bands, not point targets.
- Creative pipeline as the bottleneck: required net-new concepts/week at $1M/month; keeping a
  winner bench.
- Account safety: ad account redundancy, payment thresholds, policy compliance, avoiding bans
  (claims, before/afters, personal attributes); backup BM hygiene.
- **Grill focus:** present a volatility-management plan and a compliance pre-flight checklist from
  memory.

---

## Module 9 — Funnel CRO for Media Buyers

### Lesson 9.1 — Sales page anatomy and benchmarks
- The low-ticket sales page: hook/promise, mechanism, proof, offer stack, price anchor, guarantee,
  FAQ; congruence between ad angle and page (message match) as the top CVR lever.
- Benchmarks: sales-page CVR bands for cold traffic at $27–$57, checkout completion rates, load
  speed and mobile-first realities.
- **Grill focus:** audit a described page against the anatomy and rank the three highest-leverage
  fixes.

### Lesson 9.2 — Bumps, upsells, and offer economics
- Designing bumps (low-friction, complementary, $17–$37) and upsells (bigger promise, $47–$197);
  take-rate benchmarks and the AOV sensitivity table.
- Testing offer changes without wrecking attribution or comparability windows.
- **Grill focus:** compute the AOV impact of a proposed bump/upsell change and decide if the test
  is worth the traffic.

### Lesson 9.3 — CRO testing method
- Hypothesis → single-variable test → sample-size sanity (purchases, not sessions, as the unit);
  sequential vs A/B testing at this volume; when a test is done and when it's noise.
- The media buyer's role vs the funnel builder's: proposing tests from traffic data (heatmaps,
  scroll, drop-off between page → checkout → purchase).
- **Grill focus:** design a CRO test end-to-end for a given CVR problem, including the numbers
  that would call the winner.

---

## Module 10 — Reporting, SOPs, and Operating Cadence

### Lesson 10.1 — Reporting that leadership actually reads
- The weekly report: spend, MER, 1/7/30-day ROAS by funnel, top/bottom creatives, tests
  launched/verdicts, next week's plan. One page. Insights ("what we learned, what we'll do"), not
  data dumps.
- Building the report pipeline with AI: pulling Hyros/Meta exports, letting Claude draft the
  narrative, human judgment on the recommendation.
- **Grill focus:** given a messy week of numbers, produce the five-line executive summary a CEO
  would act on.

### Lesson 10.2 — SOPs and automation
- Writing SOPs that survive contact: trigger, owner, steps, thresholds, escalation. The core SOP
  set for a media buying team (daily checklist, testing, scaling, kill rules, launch QA, incident
  response for tracking outages).
- Automating the repetitive layer: rules in Ads Manager, alerting on threshold breaches, AI-drafted
  briefs and reports; what must never be automated (kill/scale judgment on ambiguous data).
- **Grill focus:** draft an SOP from scratch for a chosen process, complete with thresholds.

### Lesson 10.3 — Operating with the CEO
- Communication cadence: daily numbers drop, weekly deep-dive, instant escalation triggers
  (tracking down, account ban, MER below floor, spend anomaly).
- Owning the budget: making the case to raise/cut spend with unit economics, not opinions;
  forecasting next month's spend/revenue with honest bands.
- **Grill focus:** role-play the "ROAS dropped 30% this week" call: explain, own, and present the
  plan in under two minutes.

---

## Capstone — Full-Account Simulation Drills

Run after all modules pass. Each drill is a timed, multi-layer scenario grilled to completion:

1. **The Monday crash** — day-1 ROAS down 40% account-wide; find the cause from a data pack
   (it's a tracking outage, not the ads).
2. **The scaling month** — plan spend from $300k to $500k in 30 days: budgets, creative pipeline,
   hiring the second buyer, risk register.
3. **The creative drought** — winners fatiguing, tests all losing; rebuild the pipeline from
   research to briefs to calendar.
4. **The attribution war** — Hyros, Meta, and Stripe disagree wildly after an iOS update; produce
   the reconciliation memo and new reporting standard.
5. **BFCM** — plan and run a Black Friday offer on paper: CPM surge economics, offer change,
   budget hour-by-hour, rollback criteria.

---

## Responsibility map (job-ad → syllabus)

| Job responsibility | Modules |
|---|---|
| Launch and test new ad creatives and concepts | 5, 6 |
| Monitor and manage campaigns daily | 7 |
| Optimize budget / gatekeep spend | 1, 7, 8 |
| Proposals and briefs for new creatives | 5 |
| Propose changes to Media Buying SOPs | 10 |
| Reports with KPIs and insights for leadership | 1, 3, 10 |
| Use AI/automation for repetitive tasks | 10 |
| Design static ads / produce AI video ads | 5 |
| Communicate with the CEO | 10 |
| Scale $250–300k/mo → $1M/mo | 2, 4, 8 |
