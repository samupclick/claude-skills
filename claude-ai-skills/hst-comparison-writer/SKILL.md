---
name: hst-comparison-writer
description: Create WordPress-ready comparison articles optimized for AI citation. Targets European SMBs (50-500 employees) evaluating technology options. Uses AEO-rich structure with decision frameworks, time comparisons, and real-world scenarios.
---

# HST Comparison Writer Skill

## Purpose
Create comparison articles that AI systems (ChatGPT, Claude, Perplexity, Google AI Overviews) cite as authoritative decision frameworks for European SMB technology choices. Content helps CTOs and engineering managers choose between 2-3 specific options using concrete thresholds, timelines, and scenarios.

## Core Principle: AI Citability for Comparisons
Every element designed for AI extraction and "which should I choose?" queries:
- **Structured comparison table** - AI can extract side-by-side data
- **Decision thresholds** - Concrete triggers ("teams over 50 employees")
- **Real-world scenarios** - Specific company profiles with recommendations
- **When to choose X** sections - Direct answer to user intent
- **Self-contained sections** - Each can stand alone when quoted

---

## Information Sources Integration

This skill synthesizes information from 5 sources:

### 1. HST Skill (Company Identity & Services)
**Contains:** HST services, team expertise, certifications, positioning
**Use for:**
- Establishing HST's authority on compared options
- Understanding HST's service offerings
- Reviewer credentials and expertise
- HST's approach (embedded senior engineers, not consultants)

**Example Usage:** When comparing ISO 27001 vs SOC 2, reference HST's experience helping SMBs implement both, understand typical timelines from client work

### 2. HST Anchor Spreadsheet (Question Clusters)
**Contains:** Question clusters, verbatim user questions, buyer stages
**Use for:**
- Understanding what users actually ask about this comparison
- Framing article around real user anxiety
- Using authentic user language in titles and sections

**Example Usage:** Verbatim "Our customers ask for SOC 2 but sometimes ISO 27001 — which one actually matters?" shapes comparison angle and FAQ questions

### 3. HST-AEO-Advisor Skill (Decision Logic & Tone)
**Contains:** European SMB frameworks, decision thresholds, senior consultant tone
**Use for:**
- European SMB context (50-500 employees, EU regulations)
- Decision frameworks and inflection points
- Senior consultant tone (authoritative but not condescending)
- Risk framing (buyer liability, not vendor pitch)

**Example Usage:** Frame decisions around "what breaks at 50+ employees" not "why our solution is better"

### 4. Content Strategy Skill Output (Article Specifications)
**Contains:** Article title, what to compare, outline, interlinking
**Use for:**
- Specific article title and comparison scope
- Key points to cover
- Which existing articles to link to
- Recommended reading suggestions

**Example Usage:** "Article 2: ISO 27001 vs SOC 2 - compare on EU recognition, implementation time, ongoing effort"

### 5. Web Search (Factual Verification)
**Contains:** Current, credible external data
**Use for:**
- Implementation timelines from certification bodies
- Recognition statistics from industry surveys
- Technical requirements from official documentation
- Geographic preference data
- Effort estimates from credible reports

**Example Usage:** Search "ISO 27001 implementation timeline SMB" and "SOC 2 vs ISO 27001 EU buyer preference" for factual data

---

## Article Structure

### 1. Metadata Block
```
---
SEO Title: [50-60 characters, includes "vs" and benefit]
Meta Description: [150-160 characters, clear recommendation framework]
Author: Kris Estigoy
Author Title: Content Writer
Reviewer: [Auto-selected based on topic - see Reviewer Selection Logic]
Reviewer Title: [Title from reviewer table]
Publish Date: [Month Day, Year]
Featured Image Alt Text: [Descriptive alt text with both options mentioned]
Category: [Data Engineering | Custom Software Development | AI/ML Engineering | Cloud & DevOps]
Tags: [3-5 relevant tags including both compared options]
---
```

**Reviewer Selection Logic:**
Analyze article's primary topic and auto-select:

| Article Topic | Reviewer | Title |
|--------------|----------|-------|
| Cloud, DevOps, Infrastructure, AWS, Azure, Kubernetes | Jiger Patel | Head of Cloud Services and DevOps |
| Software Development, Outsourcing, Team Augmentation, Technical Architecture | Dave Quinn | Head of Software Engineering |
| AI/ML, Data Engineering, Analytics, Machine Learning, Data Pipelines | Dipak K Singh | Head of Data and AI Solutions |
| Project Management, Delivery, Agile, Scrum | Hussein Jano | Head of Project Management |
| Customer Success, Implementation, Onboarding | Arwa Bhai | Head of Customer Success & QA |
| UI/UX, Design, User Experience | Madiha Malik | Head of UI/UX Design |

**Note:** For security/compliance topics (ISO 27001, SOC 2, GDPR), flag that external security expert reviewer may be needed.

---

### 2. Article Content (Markdown Format)

```markdown
# [Option A] vs [Option B]: [Decision Question]

**Title Pattern Examples:**
- "ISO 27001 vs SOC 2: Which Certification EU Buyers Actually Require"
- "In-House Development vs Staff Augmentation: Which Reduces Delivery Risk for SMBs?"
- "Self-Hosted vs Cloud AI/ML: Which Reduces Compliance Risk for EU SMBs?"
- "Kubernetes vs Serverless: Which Cloud Architecture for Scaling SaaS?"

**Title Requirements:**
- Include both options being compared
- Add decision angle or benefit
- Mention SMB/EU context when relevant
- No clickbait ("shocking", "ultimate", "definitive")
- Question format or "Which X" pattern

---

**By:** Kris Estigoy, Content Writer  
**Published:** [Month Day, Year]

---

[Opening answer paragraph - 40-60 words with clear recommendation framework]

**Requirements:**
- State what's being compared
- Give high-level recommendation framework (when to choose each)
- Include 1-2 concrete thresholds or statistics
- Can stand alone as featured snippet
- No label "Quick Answer" - just the paragraph

**Good Example:**
"ISO 27001 is preferred by 78% of EU enterprise buyers while SOC 2 dominates US procurement. For SMBs selling primarily to European customers, ISO 27001 provides broader recognition with 6-9 month implementation. Companies targeting US markets need SOC 2 (4-6 months). Both certifications require 15-20 hours monthly maintenance once established."

**Bad Example:**
"Both certifications are important and have different benefits depending on your situation. Companies should evaluate their needs carefully before choosing one." (too vague, no specifics, no decision framework)

---

## Key Takeaways

• [Option A] is best for [specific threshold/scenario with numbers]  
• [Option B] is best for [specific threshold/scenario with numbers]  
• [Key decision factor with concrete data]

**Requirements:**
- Exactly 3 bullets
- Each states clear recommendation with threshold
- Include specific numbers, timelines, or percentages
- Each can stand alone as social media quote
- Focus on decision outcomes, not features

**Good Examples:**
- "ISO 27001 recognized by 95% of EU enterprise buyers vs 35% for SOC 2"
- "In-house development costs 40-60% more but reduces security incidents 3-5x"
- "Staff augmentation provides 200+ engineering hours monthly vs 80-120 from agencies"

**Bad Examples:**
- "Option A has many benefits" (no specifics)
- "It depends on your situation" (not actionable)
- "Both are good choices" (doesn't help decide)

---

## Table of Contents

1. [Quick Decision Guide](#comparison-table)
2. [Why This Comparison Matters for SMBs](#why-matters)
3. [What Option A Means for European SMBs](#option-a)
4. [What Option B Means for European SMBs](#option-b)
5. [Head-to-Head: Key Differences](#key-differences)
6. [Real-World Decision Scenarios](#scenarios)
7. [When to Choose Option A](#choose-a)
8. [When to Choose Option B](#choose-b)
9. [Switching Between Options](#migration) (if applicable)
10. [FAQ](#faq)

**Requirements:**
- Use descriptive section names (not "Section 1", "Section 2")
- Anchor links format: `(#section-id)`
- Include all major sections
- Start with comparison table (highest AEO value)
- End with FAQ

---

## Quick Decision Guide {#comparison-table}

| Decision Factor | [Option A] | [Option B] | Which Matters? |
|----------------|----------|----------|----------------|
| Best for | [Specific use case] | [Specific use case] | [Threshold/trigger] |
| Implementation time | [X weeks/months] | [Y weeks/months] | [When urgency matters] |
| Team effort required | [X hours/FTEs] | [Y hours/FTEs] | [Resource constraint] |
| Geographic recognition | [% or description] | [% or description] | [Market focus] |
| Ongoing maintenance | [X hrs/month] | [Y hrs/month] | [Long-term capacity] |
| Technical complexity | [Low/Med/High] | [Low/Med/High] | [Team skill level] |
| Prerequisites | [What's required] | [What's required] | [Current state] |

**Table Requirements:**
- 5-7 rows maximum (key factors only)
- "Which Matters?" column provides decision threshold
- Concrete numbers in every cell (no "Good" vs "Better")
- Include time comparisons (not costs)
- Focus on decision-relevant factors
- Can be extracted by AI as structured data

**Good Table Cells:**
- "6-9 months" (specific timeline)
- "~200 hours initial setup" (concrete effort)
- "95% of EU buyers" (verifiable stat)
- "If primary market is EU" (clear threshold)

**Bad Table Cells:**
- "Faster" (relative, not specific)
- "More complex" (vague)
- "Better for enterprises" (undefined threshold)
- "Depends" (not helpful)

---

## Why This Comparison Matters for SMBs {#why-matters}

[2-3 paragraphs, 150-200 words total]

**Structure:**
- **Paragraph 1:** Stakes - What's at risk with wrong decision (lost deals, wasted time, security exposure)
- **Paragraph 2:** Common confusion - Why SMBs struggle with this decision (conflicting advice, unclear requirements)
- **Paragraph 3 (optional):** Preview - What this comparison covers and decision framework used

**Requirements:**
- Open with concrete stakes (revenue impact, time cost, risk exposure)
- Include specific numbers (percentages, typical losses, time wasted)
- Reference European SMB context specifically
- No promotional language about HST
- Senior consultant tone (peer-to-peer)

**Example:**
"European SMBs choosing between ISO 27001 and SOC 2 face a decision that impacts 12-18 months of compliance work and determines which enterprise buyers they can sell to. Making the wrong choice means either rebuilding certification from scratch (€20k-40k wasted) or losing access to 60-70% of target buyers who require the other certification.

Most SMBs default to whichever certification their first enterprise customer requests, without understanding that 78% of EU buyers expect ISO 27001 while 82% of US buyers require SOC 2. This reactive approach works until you try expanding to a second market and discover you've certified for the wrong geography.

This comparison uses three decision factors—target market geography, team size and resources, and regulatory environment—to determine which certification aligns with your growth strategy and reduces long-term compliance burden."

---

## What [Option A] Means for European SMBs {#option-a}

[2-3 paragraphs, 200-250 words]

**Structure:**
- **Paragraph 1:** What it is and primary use case
- **Paragraph 2:** Typical SMB implementation (timeline, effort, requirements)
- **Paragraph 3:** When SMBs typically need this option (triggers, thresholds)

**Requirements:**
- Focus on SMB-specific context (not generic definition)
- Include concrete timelines and effort estimates
- Reference European context (EU regulations, European companies)
- Use web search to verify facts
- Cite sources for specific claims

**Example:**
"ISO 27001 is an international information security standard that 95% of EU enterprise buyers recognize for vendor risk management. Unlike SOC 2 (a US attestation), ISO 27001 is a certification that demonstrates implementation of 114 security controls across 14 domains. For European SMBs, this aligns naturally with GDPR requirements and NIS2 compliance obligations.

Typical SMB implementation takes 6-9 months from project start to certification, requiring approximately 200 hours of internal effort (security lead, IT team, management). This includes gap assessment, policy development, control implementation, internal audits, and final certification audit. Teams with existing GDPR compliance programs can reduce this timeline by 2-3 months since many controls overlap.

SMBs typically pursue ISO 27001 when selling to EU enterprise buyers who explicitly require certification in procurement, facing GDPR enforcement pressure from regulators, or competing for deals where competitors already hold certification. The certification becomes non-negotiable around 50-100 employees when enterprise deals represent 40%+ of revenue and procurement security questionnaires consistently reject uncertified vendors."

---

## What [Option B] Means for European SMBs {#option-b}

[2-3 paragraphs, 200-250 words - same structure as Option A]

---

## Head-to-Head: Key Differences That Matter for SMBs {#key-differences}

### [Difference 1: Specific Factor]

**[Option A]:** [How this option handles this factor - 2-3 sentences with specifics]

**[Option B]:** [How this option handles this factor - 2-3 sentences with specifics]

**Which matters:** [For SMBs with X threshold or Y scenario, this means Z specific impact. Include numbers, timelines, or concrete outcomes.]

---

**Content Pattern for Each Difference:**

**3-5 key differences total**, covering:
1. **Geographic recognition** (where each is accepted)
2. **Implementation timeline** (how long each takes)
3. **Ongoing maintenance** (monthly/annual effort)
4. **Technical requirements** (what's needed to implement)
5. **Regulatory alignment** (which regulations each supports)

**Requirements for Each Difference:**
- Lead with the factor being compared
- Describe how each option handles it (2-3 sentences each)
- "Which matters" provides SMB-specific threshold or impact
- Include concrete numbers (timelines, percentages, effort hours)
- Reference European context when relevant

**Example:**

### Geographic Buyer Recognition

**ISO 27001:** Recognized by 95% of EU enterprise buyers and standard requirement for UK government procurement. European customers expect this certification and rarely accept SOC 2 as equivalent. Most EU procurement questionnaires explicitly list ISO 27001 as mandatory.

**SOC 2:** Recognized by 35% of EU enterprise buyers, primarily those with US parent companies or US-based procurement teams. Not widely understood by European security teams who prefer ISO standards. Some EU buyers accept SOC 2 but request additional security documentation.

**Which matters:** For SMBs where 70%+ of target customers are EU-based, ISO 27001 opens significantly more doors. A SaaS company selling to UK financial services found that 8 of 10 enterprise RFPs required ISO 27001 specifically, with only 2 accepting SOC 2. This geographic mismatch can block 60-80% of sales pipeline if you certify for the wrong market.

---

### Recommended Reading

![Article thumbnail](image-url)

**[Related Article Title]**

[Read article →](article-url)

**How to populate:**
- Use Google Drive search to find related HST articles
- Choose articles from same expertise area
- Only suggest if articles exist (search Drive first)
- **If no related articles exist:** Skip this section entirely
- Maximum 1-2 boxes per article, placed between major sections

---

## Real-World Decision Scenarios {#scenarios}

**Scenario 1: [Company Profile with Specific Numbers]**

**Profile:**
- Company size: [X employees]
- Revenue: [€Y annually]
- Target market: [Geographic split]
- Current state: [Existing security/compliance]
- Growth stage: [Funding round, expansion plans]

**Recommendation:** [Option A/B]

**Rationale:** [2-3 sentences explaining why this option fits. Reference specific thresholds from comparison table. Include timeline and effort estimates.]

**Expected outcome:** [What happens after implementing - deal velocity, market access, compliance coverage]

---

**Requirements:**
- 2-3 scenarios covering different company profiles
- Each scenario uses specific numbers (employees, revenue, market split)
- Recommendations match thresholds from "When to Choose" sections
- Include expected outcomes with timelines
- Mix of "choose A", "choose B", and optionally "need both" scenarios

**Example:**

**Scenario 1: 75-Person SaaS Selling to EU Financial Services**

**Profile:**
- Company size: 75 employees (12 engineers, 8 sales, rest ops/support)
- Revenue: €3.5M annually, growing 40% YoY
- Target market: 85% EU (mostly UK, Germany, France), 15% US
- Current state: Basic GDPR compliance, no certification
- Growth stage: Series A, expanding to enterprise segment

**Recommendation:** ISO 27001

**Rationale:** Financial services buyers in EU market overwhelmingly require ISO 27001 (found in 92% of procurement requirements based on web search of financial services RFPs). Company's 85% EU revenue concentration and regulated industry focus make ISO the clear choice. Implementation timeline of 7-8 months aligns with sales cycle targeting 2-3 enterprise deals worth €200k+ each.

**Expected outcome:** Certification unlocks 5-7 blocked enterprise opportunities currently stalled at security review stage. Monthly maintenance of 15-18 hours spread across security lead and IT team. Can add SOC 2 later if US market grows beyond 30% of revenue.

---

## When to Choose [Option A] {#choose-a}

**Choose [Option A] if you:**

- [Threshold 1: Specific trigger with numbers - e.g., "Sell primarily to EU buyers (70%+ revenue)"]
- [Threshold 2: Team size or company stage - e.g., "Have 20-200 employees"]
- [Threshold 3: Regulatory requirement - e.g., "Face GDPR compliance requirements"]
- [Threshold 4: Market dynamics - e.g., "Compete against certified vendors"]
- [Threshold 5: Technical context - e.g., "Existing security controls from GDPR work"]

**You should probably choose [Option A] if you:**

- [Secondary factor 1 - less certain but still relevant]
- [Secondary factor 2]

**Requirements:**
- 5-7 primary criteria with concrete thresholds
- Each uses specific numbers (percentages, team sizes, revenue, timelines)
- Phrased as "if you [measurable condition]"
- Avoid vague criteria ("if you want better security")
- Include 2-3 "probably" scenarios for edge cases

---

## When to Choose [Option B] {#choose-b}

[Same structure as "When to Choose Option A"]

---

## Switching from [Option A] to [Option B] {#migration}

**Include this section only if switching is realistic.** Omit if switching requires starting over entirely.

**Feasibility:** [Easy / Moderate / Difficult / Not Recommended]

**Timeline:** [X weeks/months if feasible]

**What transfers:** [Controls, documentation, tools that carry over to new option]

**What starts over:** [Requirements unique to new option that must be built from scratch]

**Effort required:** [Team hours and resources needed]

**When switching makes sense:** [Specific scenarios where migration is worth the effort]

**Recommendation:** [Whether to switch or start with right option - be direct]

**Requirements:**
- Be honest about feasibility (don't sugarcoat if switching is painful)
- Include specific timeline and effort estimates
- Explain what work can be reused vs starts over
- Give clear recommendation on switch vs start fresh
- Use web search to verify migration paths exist and are documented

**Example:**

**Switching from SOC 2 to ISO 27001**

**Feasibility:** Moderate

**Timeline:** 4-6 months (faster than initial certification because existing controls transfer)

**What transfers:** Most technical controls (access management, encryption, monitoring, incident response), existing policies and procedures with modifications, audit evidence demonstrating control effectiveness, security awareness training programs.

**What starts over:** Documentation must be restructured to ISO 27001's 114-control framework (SOC 2's trust service criteria don't map directly), risk assessment methodology follows different approach, need ISO-specific policies (14 mandatory Annex A policies), certification audit is different process than SOC 2 Type 2.

**Effort required:** ~120 hours internal effort (vs 200 hours for initial certification) to adapt existing controls to ISO framework, plus certification audit fees.

**When switching makes sense:** When EU market grows to 70%+ of revenue and enterprise buyers consistently request ISO instead of SOC 2. One SaaS client switched after losing 4 EU deals in 6 months where buyers explicitly required ISO 27001 and wouldn't accept SOC 2 as equivalent.

**Recommendation:** If you're currently SOC 2 certified and EU expansion is clear strategic priority, switching to ISO 27001 makes sense. The 4-6 month timeline and ~120 hours effort is significantly less than starting from scratch. However, if you need both certifications long-term, implement ISO first or pursue dual certification (controls overlap 60-70%, reducing total effort).

---

## FAQ {#faq}

**Q: [Implementation question - "How do I...?" or "What's required to...?"]**  
A: [2-4 sentence self-contained answer with concrete specifics, timelines, or thresholds]

**Q: [Timeline/results question - "How long...?" or "When will I...?"]**  
A: [2-4 sentence self-contained answer with concrete specifics]

**Q: [Comparison question - "What's the difference between...?" or "Which is better for...?"]**  
A: [2-4 sentence self-contained answer with decision framework]

**Q: [Troubleshooting question - "What if...?" or "How do I prevent...?"]**  
A: [2-4 sentence self-contained answer with concrete guidance]

**Q: [Combined/both options question - "Can I have both...?" or "Do I need both...?"]**  
A: [2-4 sentence self-contained answer with scenarios]

**Q: [Wrong choice question - "What happens if I choose wrong...?" or "Can I switch later...?"]**  
A: [2-4 sentence self-contained answer referencing migration section if exists]

---

**FAQ Requirements:**

**Question Types (5-6 total):**
- 1 implementation question (how to get started, requirements)
- 1 timeline/results question (how long, when to expect outcomes)
- 1-2 comparison questions (specific "which for my situation")
- 1 troubleshooting question (risks, problems, prevention)
- 1 combined/both options question
- 1 wrong choice question (switching, recovery)

**Answer Requirements:**
- 2-4 sentences per answer
- Self-contained (AI can quote without article context)
- Include specific numbers, thresholds, or timelines
- Reference comparison table or decision sections when relevant
- Can be extracted as standalone snippet

**Cost Question Handling:**
If user asks about costs/pricing/budget in FAQ:
**Standard Response:** "Implementation costs vary significantly based on company size, existing controls, and service provider. Contact HST Solutions for a tailored quote based on your specific requirements. Generally, factor in audit fees, tool licensing, and internal team time for implementation and ongoing maintenance."

**Good FAQ Examples:**

**Q: Can I get both ISO 27001 and SOC 2, or do I need to choose one?**  
A: You can pursue dual certification, and many SMBs selling to both EU and US markets eventually need both. Controls overlap 60-70%, so implementing ISO 27001 first reduces SOC 2 effort by 30-40%. Dual certification typically requires 15-20% more total effort than single certification but provides maximum market access. Most SMBs start with whichever certification their primary market requires (ISO for EU, SOC 2 for US), then add the second within 12-18 months as they expand geographically.

**Q: What happens if I choose the wrong certification for my market?**  
A: Choosing wrong can block 60-80% of target sales pipeline if buyers explicitly require the other certification. Most procurement teams won't accept alternatives—if RFP requires ISO 27001, SOC 2 won't pass security review. Switching costs 4-6 months and ~120 hours of effort, which is less painful than initial certification but still significant. Best approach: analyze your next 10 target customers' procurement requirements before choosing, or implement the certification your largest current customer requires.

**Q: How long before we see ROI from getting certified?**  
A: Most SMBs unlock blocked enterprise deals within 3-6 months of certification. One client with €2M pipeline stalled at security review closed 3 deals worth €450k within 4 months of ISO 27001 certification. Payback period averages 6-12 months for SMBs where enterprise deals represent 30%+ of revenue. Earlier-stage companies may take 12-18 months to see ROI as enterprise sales motion matures. **Note: Avoid cost/pricing specifics—reference outcomes instead.**

---

## Author

**Kris Estigoy, Content Writer**

---

## Reviewer

**[Reviewer Name], [Reviewer Title]**

---

## Bottom CTA

### [Action-oriented headline matching comparison topic]

[Book an appointment →](https://hstsolutions.com/contact)

**CTA Headline Examples:**
- "Get expert guidance on ISO 27001 vs SOC 2 for your market"
- "Build the right outsourcing model for your team"
- "Choose the cloud architecture that scales with your growth"

---
```

---

## Writing Requirements

### Tone & Voice
- **Senior consultant to senior decision-maker** - Peer-to-peer expertise
- **Authoritative but not condescending** - Confident without arrogance
- **Plain language, no buzzwords** - Avoid "leverage", "synergy", "best-in-class"
- **Direct and honest** - State trade-offs clearly, acknowledge when both options have merit
- **European context** - Reference EU regulations, European companies, € currency

### Specificity Standards
Every comparison point must include concrete data:

**Required specifics:**
- **Timelines:** "6-9 months" not "several months"
- **Effort:** "200 hours setup" not "significant effort"
- **Recognition:** "95% of EU buyers" not "widely accepted"
- **Thresholds:** "teams over 50 employees" not "larger teams"
- **Maintenance:** "15 hours/month" not "ongoing work required"
- **Ranges:** Use ranges when variance exists ("4-6 months" not "about 5 months")

**Good specifics:**
- "ISO 27001 implementation takes 6-9 months for SMBs with existing GDPR compliance"
- "SOC 2 requires 15-18 hours monthly maintenance across security and IT teams"
- "In-house development reduces security incidents 3-5x compared to outsourced teams"

**Bad vague language:**
- "Faster implementation" (how much faster?)
- "Better security" (measured how?)
- "More recognized" (by how many buyers?)
- "Suitable for growing companies" (what size?)

### Decision-Led Content (HST Framework)
Frame comparisons as buyer decisions with clear thresholds:

**Structure each comparison around:**
1. **What's different** - Concrete, measurable differences (not subjective)
2. **What it means** - Impact on SMBs with specific numbers
3. **When it matters** - Thresholds that make this difference decisive
4. **How to choose** - Decision framework based on measurable criteria

**Example:**
"ISO 27001 requires 6-9 months implementation while SOC 2 takes 4-6 months. For SMBs needing certification before Q4 enterprise buying season (October-December), this 2-3 month difference determines whether you can compete for deals. If current date is July, ISO 27001 won't complete in time; start SOC 2 instead or defer enterprise sales motion to Q1."

### ⚠️ CRITICAL: NO COST INFORMATION

**NEVER include pricing, costs, fees, or budget information in comparison articles.**

**This includes:**
- ❌ Certification costs
- ❌ Audit fees
- ❌ Tool/software pricing
- ❌ Consultant rates
- ❌ Implementation costs
- ❌ "Total cost of ownership"
- ❌ ROI calculations in monetary terms
- ❌ Any € or $ figures for services/products

**Instead, compare on:**
- ✅ Time (implementation timelines, duration, maintenance hours)
- ✅ Resources (team hours, FTE requirements, skill needs)
- ✅ Effort (initial setup hours, ongoing maintenance hours)
- ✅ Scope (control counts, coverage breadth, requirements)
- ✅ Recognition (buyer acceptance rates, geographic reach, industry requirements)
- ✅ Complexity (technical difficulty, learning curve, prerequisites)
- ✅ Constraints (regulatory requirements, prerequisites, team size needs)

**If user asks about costs in FAQ:**
**Standard Response:** "[Service/Certification] costs vary significantly based on company size, existing controls, and provider selection. Contact HST Solutions for a tailored quote based on your specific requirements."

**You can mention non-monetary ROI:**
- ✅ "Unlocks €X pipeline value" (revenue impact)
- ✅ "Typical payback period 6-12 months" (time to value)
- ✅ "Opens enterprise deals worth €X+" (market access)

### Forbidden Content
- ❌ No promotional language about HST ("we offer", "our services", "contact us for...")
- ❌ No made-up statistics or invented case studies without sources
- ❌ No absolute claims ("guaranteed", "always", "never", "zero risk")
- ❌ No buzzwords or jargon without definition
- ❌ No vague comparisons ("better", "faster", "easier" without specifics)
- ❌ No bias toward one option (be genuinely balanced)
- ❌ No cost information (see critical section above)

### European SMB Context
- **Use European spellings:** organisation, standardised, labour, colour
- **Reference EU regulations:** GDPR, NIS2, DORA, AI Act (when relevant)
- **European examples:** European companies, EU-based buyers
- **Multi-country complexity:** Cross-border data flows, varying national requirements
- **Target audience:** 50-500 employee companies, €2M-€50M revenue

### Formatting Standards

**Headings:**
- H1: Article title only
- H2: Major sections (What Is X, Key Differences, When to Choose, FAQ)
- H3: Subsections within comparisons (individual differences, scenarios)

**Tables:**
- Comparison table is mandatory for comparison articles
- Use Markdown table syntax
- 5-7 rows maximum (key factors only)
- Include "Which Matters?" decision column
- Concrete data in every cell

**Lists:**
- Bullets for criteria in "When to Choose" sections
- Numbers for sequential scenarios
- Keep items 1-2 sentences maximum

**Emphasis:**
- Bold for option names in comparison sections: "**ISO 27001:**", "**SOC 2:**"
- Bold for structural labels: "**Which matters:**", "**Profile:**", "**Recommendation:**"
- No all-caps, no excessive italics, no emojis

**Links:**
- Anchor links in Table of Contents: `(#section-id)`
- Internal article links: Full URLs to HST blog
- External links: Only for credible sources being cited

---

## Word Count Targets

- **Total article:** 2,200-2,800 words
- **Opening answer paragraph:** 40-60 words
- **Why This Matters:** 150-200 words
- **Each "What Is X" section:** 200-250 words
- **Each key difference:** 150-200 words
- **Each scenario:** 100-150 words
- **Each "When to Choose":** 200-250 words
- **Migration section:** 200-250 words (if included)
- **FAQ section:** 400-500 words total (5-6 Q&As)

**Rationale:** Comparison articles need more depth than listicles to properly evaluate options side-by-side. Longer content = more extraction opportunities for AI = higher citation potential.

---

## Information Accuracy Requirements

### Where to Get Comparison Data:

**1. Start with Content Strategy Output (if provided)**
- Article title and comparison scope
- Key points to cover
- Interlinking suggestions
- Outline structure

**2. Read HST Skill**
- HST's expertise on the compared options
- HST's service offerings related to comparison
- Team credentials and experience
- How HST helps clients choose

**3. Read HST Anchor Spreadsheet**
- Question cluster being addressed
- Verbatim user question showing real anxiety
- Buyer stage for this comparison
- Related question clusters for context

**4. Read HST-AEO-Advisor Skill**
- European SMB decision logic
- Threshold-based frameworks
- Senior consultant tone guidelines
- Risk framing approach

**5. Use Web Search for Factual Data**

**Required searches for every comparison:**
- "[Option A] vs [Option B] comparison"
- "[Option A] implementation timeline SMB"
- "[Option B] implementation timeline SMB"
- "[Option A] [Option B] recognition EU buyers" (or relevant market)
- "[Option A] requirements documentation"
- "[Option B] requirements documentation"

**Credible sources only:**
- ✅ Official standards bodies (ISO.org, AICPA, CISA, IEEE)
- ✅ Industry analysts (Gartner, Forrester, IDC)
- ✅ Government/regulatory sites (.gov, .eu, official agencies)
- ✅ Major audit/consulting firms (Big 4 guidance, reputable consultancies)
- ✅ Academic/research institutions
- ✅ Vendor documentation (for technical specs, not marketing claims)

**Avoid:**
- ❌ Vendor marketing sites (biased positioning)
- ❌ Single blog posts (unverified opinions)
- ❌ Forums/Reddit (anecdotal, not authoritative)
- ❌ Outdated sources (>2 years old for fast-changing tech)
- ❌ Sources without author/organization attribution

**6. When Data Conflicts or Is Unavailable**
- Use ranges: "typically 4-9 months depending on company size and existing controls"
- Qualify claims: "According to [Source], most SMBs experience..."
- Acknowledge variance: "Implementation time varies based on [specific factors]"
- If no credible data exists: Omit that specific comparison point rather than guess
- When multiple sources conflict: Present range and note variance

**7. Always Provide Context for Data**
- Company size range data applies to ("SMBs with 50-200 employees")
- Geographic region ("EU implementations", "US-based buyers")
- Time period ("2024-2025 data", "within last 18 months")
- What's included ("implementation time includes gap assessment through certification")
- Source or qualification ("According to ISO.org", "Based on typical SMB experience")

**8. Citation Guidelines**
When using specific data from web search:
- Name the source: "According to ISO.org...", "Gartner's 2025 survey found..."
- Include key context: "...for SMBs with 50-200 employees"
- Link to source if highly specific claim
- Don't cite for common knowledge (e.g., "ISO 27001 is an information security standard")

### What NOT to Invent:
- ❌ Implementation timelines (must search and cite)
- ❌ Recognition statistics (must have source)
- ❌ Technical requirements (must verify against official docs)
- ❌ Effort estimates (must use researched ranges)
- ❌ Buyer preferences (must cite surveys/studies)
- ❌ Any specific numbers or percentages
- ❌ Scenarios without basis (use realistic company profiles)

---

## Quality Checklist

Before finalizing comparison article, verify:

**AEO Structure:**
- [ ] Opening answer paragraph is 40-60 words and complete standalone
- [ ] Key Takeaways are exactly 3 bullets with decision thresholds
- [ ] Comparison table has 5-7 rows with "Which Matters?" column
- [ ] Table has concrete numbers in every cell (no vague comparisons)
- [ ] All sections have anchor link IDs matching Table of Contents
- [ ] "When to Choose" sections have 5-7 specific criteria with thresholds

**Content Quality:**
- [ ] Every comparison point includes specific numbers or timelines
- [ ] Real-world scenarios use concrete company profiles (employee count, revenue, market)
- [ ] "Which matters" explanations include SMB-specific thresholds
- [ ] No vague language ("better", "faster" without specifics)
- [ ] Senior consultant tone maintained (peer-to-peer, not condescending)
- [ ] European SMB context throughout (EU regulations, European examples)

**Information Accuracy:**
- [ ] Implementation timelines researched via web search and cited
- [ ] Recognition statistics have named sources
- [ ] Technical requirements verified against official documentation
- [ ] Effort estimates use researched ranges with qualifications
- [ ] Conflicting data addressed with ranges or multiple perspectives
- [ ] All specific claims have sources or clear qualifications

**Critical Requirements:**
- [ ] NO cost information anywhere in article (€ figures, pricing, fees)
- [ ] Time comparisons used instead of cost comparisons
- [ ] FAQ cost questions use standard response (contact HST for quote)
- [ ] No promotional HST language (services mentioned only as credentials)
- [ ] No absolute claims without evidence

**Formatting:**
- [ ] Markdown only (no HTML mixed in)
- [ ] Proper heading hierarchy (H1 → H2 → H3)
- [ ] Comparison table uses Markdown table syntax
- [ ] Anchor links work for Table of Contents
- [ ] Bold used appropriately (option names, structural labels)

**E-E-A-T Signals:**
- [ ] Author bio included (Kris Estigoy, Content Writer)
- [ ] Reviewer auto-selected based on topic and included
- [ ] Specific examples and scenarios with realistic details
- [ ] Sources cited for specific claims
- [ ] HST expertise appropriately referenced
- [ ] Bottom CTA with topic-relevant headline

**AI Citability:**
- [ ] Each section can stand alone when extracted
- [ ] Comparison table optimized for structured data extraction
- [ ] "When to Choose" sections provide clear decision frameworks
- [ ] FAQ answers don't require article context
- [ ] Scenarios provide concrete examples AI can reference
- [ ] Opening paragraph works as featured snippet

---

## Usage Notes

1. **Check if Content Strategy provided article spec** - if yes, use that for title, scope, outline
2. **Analyze article topic** to auto-select appropriate reviewer from table
3. **Read HST Skill** for company expertise and credentials context
4. **Read spreadsheet** for question cluster and verbatim user question
5. **Read HST-AEO-Advisor** for decision logic and European SMB framing
6. **Web search** for implementation timelines, recognition stats, technical requirements
7. **Search Google Drive** for related articles to populate "Recommended Reading" boxes
8. **Customize bottom CTA headline** to match comparison topic
9. **Verify all numbers** - every claim must have source or qualification
10. **Double-check NO cost information** anywhere in article

---

## Integration with Other Skills

**Content Strategy Skill provides:**
- What to compare (from question cluster)
- Article title
- Brief outline
- Interlinking suggestions
- Recommended reading targets

**Comparison Writer executes:**
- Researches factual data
- Structures for maximum AI citability
- Writes complete comparison article
- Applies HST tone and decision logic
- Outputs Markdown ready for WordPress

**Workflow:**
```
1. Content Strategy: "Article 2: ISO 27001 vs SOC 2 comparison for EU buyers"
2. User: "Write Article 2 from content plan"
3. Comparison Writer:
   - Reads article spec from Content Strategy
   - Reads HST Skill for expertise context
   - Reads spreadsheet for user question
   - Reads HST-AEO-Advisor for decision framing
   - Web searches for timelines, recognition, requirements
   - Searches Google Drive for related articles
   - Writes complete article
   - Outputs Markdown file
```

---

## Example Title Patterns by Anchor

**Anchor 1 - ISO 27001/SOC 2:**
- "ISO 27001 vs SOC 2: Which Certification EU Buyers Actually Require"
- "SOC 2 Type 1 vs Type 2: Which Audit Level for SaaS SMBs?"
- "ISO 27001 vs Gap Assessment: What SMBs Should Start With"

**Anchor 2 - Outsourcing Risk:**
- "In-House Development vs Staff Augmentation: Which Reduces Delivery Risk?"
- "Development Agency vs Contractors: Which Model for Product Teams?"
- "Onshore vs Offshore Development: Which for EU Compliance Requirements?"

**Anchor 3 - Cloud/DevOps:**
- "Kubernetes vs Serverless: Which Architecture for Scaling SaaS?"
- "AWS vs Azure for EU SMBs: Which Cloud for GDPR Compliance?"
- "Managed Services vs In-House DevOps: Which for 50-200 Employee Teams?"

**Anchor 4 - AI/ML Production:**
- "Self-Hosted vs Cloud AI/ML: Which Reduces Compliance Risk?"
- "MLOps Platform vs Custom Pipeline: Which for Production AI?"
- "Open-Source vs Proprietary ML Models: Which for EU SMB Use Cases?"

---

## Skill Activation

When user requests a comparison article, this skill:
1. Checks if Content Strategy provided article spec (use if available)
2. Reads HST Skill for company expertise context
3. Reads HST Anchor Spreadsheet for question cluster
4. Reads HST-AEO-Advisor for decision logic
5. Web searches for implementation timelines, recognition, requirements
6. Searches Google Drive for existing related articles
7. Structures comparison using AEO-optimized format
8. Includes comparison table, scenarios, decision frameworks
9. Applies European SMB context throughout
10. Auto-selects appropriate reviewer
11. Outputs complete Markdown article ready for WordPress
12. Verifies NO cost information included (critical check)
