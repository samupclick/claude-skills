# Marketing Engineer Pipeline — Weekend Build Plan

**Owner:** upClickLabs
**Status:** Planning (v0.1, 2026-09-02)
**Goal for the weekend:** one live, closed loop running for upClickLabs itself — inspiration in, creatives out, ads live on Meta, performance read back, learnings stored — so the same loop can be pointed at a client the following week.

---

## 1. What we are building

An always-on creative engine. Not a one-shot campaign builder. Every cycle it:

```
RESEARCH ──▶ PLAN ──▶ PRODUCE ──▶ GATE ──▶ SHIP ──▶ MEASURE ──▶ LEARN ──┐
   ▲                                                                    │
   └────────────────────────────────────────────────────────────────────┘
```

Two optimisation targets, both measurable:

| Target | Channel | Primary metric | Secondary |
|--------|---------|----------------|-----------|
| CTR / cost per lead | Paid (Meta first) | Link CTR, CPL on the deep-funnel event | Hook rate, thumb-stop, CPM |
| Virality / reach | Organic (X, LinkedIn, IG) | Engagement rate, shares/reposts per impression | Follows, profile clicks, DMs |

The engine runs for two kinds of accounts: **us** (upClickLabs, dogfood first) and **clients** (same pipeline, different config). Everything is per-client config driven, exactly like `content-supervisor`.

### 1.1 Principles (borrowed from the inspiration, adapted to us)

1. **Broad targeting, deep-funnel event.** No interest stacks. Optimise for the booked call / qualified lead, never clicks or LPVs.
2. **Formats over polish.** Steal proven DTC creative formats (job photo + text bubble, ugly ads, testimonial cards, screenshot ads). No video editing required for v1.
3. **Volume with a kill switch.** 12–24 creatives per batch. Anything under the CTR floor after the impression threshold is paused automatically. Winners feed the next batch.
4. **Capture, don't close.** Landing page is a quiz funnel to a calendar booking. Close via follow-up.
5. **Humans approve, agents execute.** Two gates (Creative Gate, Launch Gate). Nothing spends money without a human tap. Same posture as the existing pipeline.
6. **Every cycle writes back.** Winning angles, hooks, and formats go into the pattern library with their numbers. The engine gets smarter each week or it is not an engine.

### 1.2 What this is NOT (this weekend)

- Not the buying-trigger / outbound agent. Week 2+.
- Not the SEO gap agent. We already have the AEO content pipeline; we will connect them later.
- Not video creative. Statics and copy only for v1.
- Not multi-platform paid. Meta only. Organic goes to X + LinkedIn.

---

## 2. Architecture

The pipeline is one orchestrator skill plus six worker skills, matching the repo's existing supervisor → skills → gates pattern.

```
marketing-engineer (orchestrator)
│
├── 1. creative-intel        Swipe file: pull winning ads/posts, tag format + hook + angle
├── 2. customer-language     Voice-of-customer memo: exact phrases, ranked by frequency
├── 3. angle-planner         Offer × ICP × VOC × patterns → test matrix + creative briefs
├── 4. creative-producer     Copy variants + rendered static creatives + organic posts
├── 5. creative-gate         Rubric scoring, Meta policy check, brand hard blocks
├── 6. launcher              Meta campaign build (paused) + organic scheduling + tracking test
└── 7. performance-loop      Pull insights, apply kill/scale rules, write learnings back
```

### 2.1 Worker skills in detail

**1. creative-intel**
- Inputs: client config (`competitors[]`, `inspiration_brands[]`), scrapecreators API key.
- Pulls: Meta Ad Library (via scrapecreators), TikTok/IG top posts for inspiration brands, X posts with high engagement in the niche.
- Output: normalised swipe entries in `patterns/` with fields `format`, `hook_type`, `angle`, `visual_structure`, `copy_structure`, `source_url`, `observed_signals` (days running, engagement).
- Rule: an ad running 30+ days in Ad Library is a proven format. Tag it `proven`.

**2. customer-language**
- Inputs: review sites, Reddit/Quora threads, call transcripts (if provided), support tickets (if provided).
- Reuses the research table already in `content-supervisor` §1.2 (Reddit/Quora fetch + verbatim preservation).
- Output: `voc-memo.md` — problem phrases, desired-outcome phrases, objection phrases, each with frequency count and 2–3 verbatim quotes.

**3. angle-planner**
- Inputs: offer, ICP, VOC memo, pattern library.
- Output: a test matrix. Default: 3 angles × 4 formats = 12 creatives. Each cell is a creative brief with hook, body direction, visual spec, CTA, and the VOC phrases it must use.
- Angle types to rotate: pain-led, outcome-led, proof-led, contrarian, identity ("for [role] who…").

**4. creative-producer**
- Copy: primary text (3 lengths), headline (5), hook lines (10) per brief. Direct-response rules baked into the prompt (one idea per ad, specificity, first-line hook, CTA matches landing page).
- Statics: HTML/CSS templates rendered to PNG with Playwright (already installed in this environment). Deterministic, brand-kit driven, no design tool in the loop. Sizes: 1080×1080, 1080×1350, 1080×1920.
  - Template A: job photo + text bubble overlay (the organic-looking format from the inspiration).
  - Template B: testimonial / result card.
  - Template C: "screenshot" ad (fake-native text message / notes app / tweet style).
- Optional: Nano Banana or Canva MCP for image generation when no photo assets exist. Decision point, see §6.
- Organic: same angles rewritten as X posts/threads and LinkedIn posts. Hook bank shared with paid.

**5. creative-gate** (mirrors Content Gate)
- Rubric, scored 1–5 each: hook strength, clarity in 3 seconds, ICP specificity, VOC language present, single CTA, visual legibility on mobile.
- Hard checks: Meta ad policy (no before/after body claims, no "you" + personal attribute, no income claims), brand hard blocks from config, landing page match.
- Threshold from config (`quality.creative_gate_min`, default 3.5 avg, no score under 2). Fails go back to producer with the same feedback object schema as `content-supervisor` §5.1. Max 3 retries then human.

**6. launcher** (Launch Gate sits here)
- Meta: create campaign → ad set → ads via Marketing API using a system user token from env. Structure: 1 campaign per offer, broad targeting (age + geo only), optimisation event = deepest funnel event available (Lead or Schedule), CBO on, all ads created **paused**. Human reviews the launch package and flips to active.
- Landing page: quiz funnel → calendar booking, generated from a template. 3–5 self-qualifying questions, micro-commitment progress bar, pixel + CAPI events on each step.
- Tracking: fire test events for `PageView`, `Lead`, `Schedule` and verify in Events Manager test tool before launch. This is a Launch Gate hard check.
- Organic: post/schedule to X and LinkedIn (API or Typefully/Buffer — decision point).

**7. performance-loop**
- Daily pull of ad-level insights: impressions, link CTR, CPM, CPL, hook rate (3s video views / impressions where applicable), frequency.
- Kill rule (default): impressions ≥ 2,000 AND link CTR < 1.0% → pause. CPL > 2× target after 3× target spend → pause.
- Scale rule (default): CPL ≤ target after ≥ 5 leads → +20% budget, flag as winner.
- Organic pull: impressions, engagement rate, reposts per post.
- Write-back: winners and losers appended to `patterns/` with their numbers; a weekly `learnings-memo.md` is produced and the next batch brief is seeded from it.

### 2.2 Repo layout

```
marketing-engineer/
├── PLAN.md                          # this file
├── SKILL.md                         # orchestrator (triggers, cadence, gates, state)
├── README.md
├── CHANGELOG.md
├── config/
│   ├── schema.md                    # client config schema (extends content-supervisor's)
│   └── clients/
│       ├── example-client.json
│       └── upclicklabs.json
├── references/
│   ├── creative-rubric.md           # Creative Gate scoring + Meta policy checklist
│   ├── meta-launch-playbook.md      # BM setup, system user, what is UI-only vs API, event testing
│   ├── kill-scale-rules.md
│   ├── hook-library.md              # hook types with examples
│   └── direct-response-copy.md      # copy rules the producer must follow
├── templates/
│   ├── creative-brief.md
│   ├── voc-memo.md
│   ├── launch-package.md            # what the human sees at Launch Gate
│   └── learnings-memo.md
├── assets/creative-templates/
│   ├── job-photo-bubble.html
│   ├── testimonial-card.html
│   └── screenshot-ad.html
├── scripts/
│   ├── pull_inspo.py                # scrapecreators → patterns/
│   ├── render_creatives.py          # HTML templates → PNG via Playwright
│   ├── meta_launch.py               # campaign/adset/ads (paused) via Marketing API
│   ├── meta_insights.py             # daily pull + kill/scale evaluation
│   └── test_events.py               # pixel/CAPI test event firing
├── patterns/                        # swipe file + learnings (one YAML/MD per pattern)
└── state/                           # per-client iteration state (gitignored for clients)
```

### 2.3 Client config (delta over `content-supervisor` schema)

```json
{
  "client": { "name": "", "site": "" },
  "offer": { "name": "", "promise": "", "price_anchor": "", "proof_points": [] },
  "icp": { "role": "", "company_type": "", "pains": [], "desired_outcomes": [] },
  "brand": { "colors": {}, "font": "", "photo_assets_dir": "", "hard_blocks": [] },
  "channels": {
    "meta": { "ad_account_id": "", "pixel_id": "", "page_id": "", "conversion_event": "Schedule", "daily_budget": 30, "geo": [], "age": [25, 65] },
    "organic": { "x": true, "linkedin": true, "ig": false }
  },
  "targets": { "cpl": 25, "ctr_floor": 0.01, "kill_impressions": 2000 },
  "cadence": { "batch_size": 12, "new_batch": "weekly", "insights_pull": "daily" },
  "quality": { "creative_gate_min": 3.5, "max_retries": 3 }
}
```

Secrets (system user token, scrapecreators key) live in env only, never in config or git.

### 2.4 State

`state/{client}/iteration-{n}.json`: batch id, briefs, creative ids → Meta ad ids, gate scores, launch timestamp, daily metrics snapshots, kill/scale actions taken, learnings extracted. Same persistence approach as `content-supervisor` §7.

---

## 3. Weekend schedule

Assumes two people, roughly 8 working hours each per day. Blocks are ordered so that if Sunday afternoon slips, the loop is still closed.

### Friday evening — access and decisions (1.5–2h, the thing that usually blocks everyone)

- [ ] Meta Business Manager: confirm ad account, create/confirm pixel, create a **system user** with ads_management + business_management, generate a non-expiring token, store in env. Note which steps are UI-only (system user creation, asset assignment) so the playbook is accurate.
- [ ] Assign page, pixel, ad account to the system user.
- [ ] scrapecreators account + API key in env.
- [ ] Decide upClickLabs offer + ICP for the dogfood campaign (see §6).
- [ ] Gather 10–20 real photos (team, screens, work in progress) for Template A.
- [ ] Book a calendar link for the landing page CTA.

### Saturday — produce creatives end to end

| Block | Time | Deliverable | Done when |
|-------|------|-------------|-----------|
| S1 | 09:00–12:00 | `SKILL.md` skeleton, config schema, `upclicklabs.json`, state schema, `patterns/` format | Orchestrator can load a client config and print the current iteration state |
| S2 | 12:00–14:00 | `pull_inspo.py` + 20 tagged pattern entries; VOC memo for the upClickLabs ICP | `patterns/` has ≥20 entries with format + hook + angle tags; `voc-memo.md` has ≥15 ranked phrases |
| S3 | 14:00–17:00 | Angle planner + creative producer: brief template, copy prompts, Templates A and B rendering via Playwright | 12 creatives (PNG + copy) rendered for upClickLabs from a 3×4 matrix |
| S4 | 17:00–19:00 | Creative Gate rubric + Meta policy checklist + review package | All 12 scored; failures loop once; a human-readable review package is produced |

Parallel split: one person on S1 → S3 (producer), the other on S2 → S4 (intel + gate). Merge at S3.

### Sunday — ship, measure, automate

| Block | Time | Deliverable | Done when |
|-------|------|-------------|-----------|
| U1 | 09:00–12:00 | `meta_launch.py` (campaign → ad set → ads, paused), landing page quiz funnel from template, `test_events.py` | Campaign visible in Ads Manager, paused, 12 ads attached; test events show green in Events Manager |
| U2 | 12:00–14:00 | `meta_insights.py` + kill/scale evaluation + learnings write-back | Script pulls yesterday's metrics, prints kill/scale recommendations, appends winners to `patterns/` |
| U3 | 14:00–16:00 | Organic branch: 6 X posts + 3 LinkedIn posts from the same angles, scheduled | Posts queued for the week |
| U4 | 16:00–18:00 | Routines: daily 08:00 insights + kill/scale check, Monday 09:00 learnings memo + next batch brief; `README`, `CHANGELOG`, Notion board column for "Creative batches" | Routines exist and have fired once in dry-run; **upClickLabs campaign flipped to active at $30/day** |

Parallel split: one person U1 → U3, the other U2 → U4.

### Definition of done for the weekend

1. One Meta campaign live for upClickLabs, broad, optimised for `Schedule`, 12 statics, tracking verified.
2. Organic posts queued for the week from the same angles.
3. Daily routine that pulls insights and recommends kills/scales (auto-pause can stay human-confirmed for week 1).
4. Pattern library with ≥20 external patterns and the structure to accept our own results.
5. Skill documented well enough that "new client: X" starts the same loop from config.

---

## 4. Week 2–4 roadmap (after the loop is closed)

| Week | Add | Why |
|------|-----|-----|
| 2 | First client on the pipeline; auto-pause enabled; Template C; hook-rate tracking | Prove it is config-driven, not upClickLabs-shaped |
| 2 | Connect to `agency-sop`: creative batches as a job type with stage tracking in Notion | One board for content and creative |
| 3 | Buying-trigger agent (job posts, funding, competitor review spikes → enriched contact → outbound draft) | The outbound half of "marketing engineer" |
| 3 | Image generation (Nano Banana / Canva MCP) for clients without photo assets | Removes the asset dependency |
| 4 | Connect to the AEO pipeline: winning ad angles → article briefs for `hst-content-strategy`-style planners; winning articles → ad angles | Paid and organic learn from each other |
| 4 | Simple dashboard (CTR, CPL, winners by format/angle per client) | Client-facing reporting |
| 4+ | Video: script generator + template-driven UGC-style captions; TikTok/YouTube Shorts | Only once statics prove the angle |

---

## 5. Risks and how we handle them

| Risk | Mitigation |
|------|------------|
| Meta asset access / permissions (the #1 hang-up in the inspiration thread) | Friday evening, before any code. Document every UI-only step in `meta-launch-playbook.md`. |
| Ad policy rejections on "job photo + bubble" style | Policy checklist in Creative Gate; avoid personal-attribute language; keep claims proof-backed. |
| Marketing API app review / rate limits | System user token on our own BM does not need app review for our own ad accounts. Client accounts get added as partners to our BM. |
| scrapecreators cost or gaps | Cap pulls per run; Meta Ad Library web UI as manual fallback for week 1. |
| Too little data to kill/scale in 48h | Rules stay human-confirmed until ≥ 2,000 impressions per ad; week 1 is about the loop working, not the numbers. |
| Scope creep into video / more channels | §1.2 is the contract. Anything not there goes to §4. |

---

## 6. Decisions needed before Saturday

1. **upClickLabs offer and ICP for the dogfood campaign.** Recommended: the AEO content pipeline as a productised offer, targeting founders / marketing leads at B2B service firms (50–500 staff) in Europe, since the existing skills already speak to that ICP. CTA: 15-min "AI visibility audit" booking.
2. **Daily budget.** Recommended $30/day for week 1.
3. **Image source.** Recommended: real photos + HTML templates (Playwright render). Skip generative images until week 3.
4. **Organic posting tool.** Recommended: Typefully (X + LinkedIn, API, cheap) over building against two platform APIs this weekend.
5. **Meta API access method.** Recommended: direct Graph API calls from `meta_launch.py` with the system user token. Evaluate the Meta Ads MCP in week 2 once we know what we actually call.
6. **Who owns which Saturday track.** Producer track (S1→S3) vs intel + gate track (S2→S4).

---

## 7. Success metrics for the first month

| Metric | Week 1 | Week 4 |
|--------|--------|--------|
| Creatives produced per batch | 12 | 24 |
| Time from brief to launch package | < 1 day | < 2 hours |
| Link CTR on best ad | ≥ 1.0% | ≥ 1.5% |
| CPL vs target | measured | ≤ target |
| Organic posts per week | 9 | 15 |
| Clients on the pipeline | 0 (us) | 2 |
| Learnings written back per cycle | manual | automatic |
