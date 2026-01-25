---
name: hst-content-strategy
description: Dynamic content planning engine that analyzes the HST anchor spreadsheet, existing articles, and external intelligence to suggest strategic listicle and comparison articles across all 4 anchors and 3 buyer journey stages.
---

# HST Content Strategy Skill

## Purpose
Analyze the HST anchor spreadsheet and existing content to generate strategic content plans across all 4 expertise anchors (ISO 27001/SOC 2, Outsourcing Risk, Cloud/DevOps Maturity, AI/ML Production). Suggest listicle and comparison article titles mapped to buyer journey stages (Awareness, Consideration, Decision) with interlinking strategies.

## Core Principle
The **HST Anchor and Question Clusters spreadsheet is the source of truth**. All content suggestions must map directly to question clusters in the spreadsheet. Never invent question clusters outside the spreadsheet.

---

## Skill Capabilities

### 1. Multi-Anchor Content Planning
- Analyze all 4 anchors simultaneously or focus on specific anchor(s)
- Prioritize by buyer stage (typically Decision → Consideration → Awareness)
- Suggest optimal publishing sequence across anchors
- Identify cross-anchor interlinking opportunities

### 2. Buyer Journey Stage Mapping
- **Awareness Stage:** Educational content answering "What is this?" and "Why does this matter?"
- **Consideration Stage:** How-to content answering "How do I approach this?" and "What are my options?"
- **Decision Stage:** Urgency-driven content answering "Should I do this now?" and "What happens if I don't?"

**Important:** Question clusters in the spreadsheet already have assigned stages. Use those assignments as the foundation, but can suggest content for the same cluster at different stages when it makes strategic sense.

### 3. Article Format Selection
For each question cluster + stage combination, suggest both:

**Listicle Articles:**
- Pattern: "[Number] [Signs/Ways/Reasons/Triggers] [Action/Outcome]"
- Best for: Scannable insights, urgent signals, multiple approaches
- Examples: "7 Signs Missing ISO 27001 Is Blocking Deals", "5 Ways to Reduce Outsourcing Risk"

**Comparison Articles:**
- Pattern: "[Option A] vs [Option B]: [Question/Decision]" or "[Option A] or [Option B] for [Audience]?"
- Best for: Evaluating alternatives, choosing between approaches, understanding differences
- Examples: "ISO 27001 vs SOC 2: Which EU Buyers Require", "In-House vs Outsourced Development: Which Reduces Risk?"

### 4. Title Generation Rules
All titles must follow these principles:
- **Senior consultant tone** - Professional, not clickbait
- **European SMB context** - Include "SMB", "EU", or relevant scale indicators when appropriate
- **Concrete specifics** - Use numbers in listicles ("7 Signs" not "Several Signs")
- **Decision-focused** - Frame around outcomes, not features ("Blocking Deals" not "Important for Sales")
- **Plain language** - No buzzwords or jargon in titles

**Good Title Examples:**
- "5 Signs Your Ad-Hoc Cloud Setup Is Breaking Down" (Decision, Listicle)
- "Staff Augmentation vs Development Agency: Which Reduces Delivery Risk?" (Decision, Comparison)
- "8 Reasons Enterprise Buyers Ask About ISO 27001" (Awareness, Listicle)
- "AWS Certification vs Your Own ISO 27001: What Buyers Actually Check" (Consideration, Comparison)

**Bad Title Examples:**
- "Amazing Cloud Strategies You Won't Believe!" (clickbait)
- "Things About Compliance" (vague, no number)
- "Leveraging Best-in-Class DevOps" (buzzwords)
- "ISO 27001 Information" (no angle or benefit)

### 5. Interlinking Strategy
When suggesting articles, include interlinking guidance:

**Funnel Flow:**
- Awareness articles link down to → Consideration articles
- Consideration articles link down to → Decision articles
- Decision articles link back up to → Awareness/Consideration for context

**Cross-Anchor Linking:**
- ISO 27001 articles mention cloud security → link to Cloud/DevOps anchor
- Outsourcing articles mention compliance → link to ISO 27001 anchor
- AI/ML articles mention infrastructure → link to Cloud/DevOps anchor

**Recommended Reading Boxes:**
- For each new article, suggest 1-2 existing articles for "Recommended Reading" boxes
- Only suggest articles that currently exist (search Google Drive first)
- Match by topic relevance and expertise area

### 6. Google Drive Integration
Before suggesting content plans:
1. Search Google Drive for existing HST articles
2. Identify which question clusters already have content
3. Note which stages and formats are covered
4. Suggest articles to fill gaps (uncovered clusters, missing stages, incomplete formats)
5. Provide interlinking opportunities for existing articles

### 7. Flexible Output Modes
Support different planning scopes:

**Full Roadmap Mode:**
- User: "Plan all Decision stage content across all anchors"
- Output: Complete list of listicle + comparison articles for every Decision-stage question cluster across Anchors 1-4

**Targeted Mode:**
- User: "Suggest 5 articles for Anchor 2 Consideration stage"
- Output: 5 highest-priority articles (mix of listicles and comparisons) for outsourcing consideration

**Single Article Mode:**
- User: "What should I write next?"
- Output: 1-2 article suggestions based on current gaps and strategic priority

**Gap Analysis Mode:**
- User: "What's missing from our content?"
- Output: Analysis of covered vs uncovered question clusters, stage coverage, format balance

### 8. External Intelligence Integration
Accept and incorporate external research:

**Passionfruit Reports:**
- Analyze AEO reports for trending queries
- Identify new topics not in current spreadsheet
- Suggest new article ideas to strengthen AEO performance
- Flag which existing articles might need refreshing

**Other Sources:**
- Reddit/Quora trend analysis
- Competitor content gaps
- Search console data
- AI citation reports

When suggesting articles based on external intelligence:
- Clearly mark as "New topic - not in current spreadsheet"
- Suggest which anchor it belongs under
- Recommend question cluster addition to spreadsheet
- Explain strategic rationale

---

## Output Format

```markdown
# Content Plan: [Scope Description]

## Summary
- Total articles suggested: [X]
- Coverage: [Anchor 1: X articles, Anchor 2: Y articles, etc.]
- Stages: [Decision: X, Consideration: Y, Awareness: Z]
- Formats: [Listicles: X, Comparisons: Y]

## Existing Content Analysis
[If Google Drive search performed]
- Articles found: [X]
- Covered question clusters: [List]
- Missing clusters: [List]
- Stage gaps: [Which stages need more coverage]
- Format balance: [Listicle vs Comparison ratio]

---

## Priority 1: [Stage] Articles

### Anchor 1 - ISO 27001/SOC 2 Certification

**Article 1: [Listicle Title]**
- Format: Listicle
- Question Cluster: "[Verbatim from spreadsheet]"
- Buyer Stage: [Decision/Consideration/Awareness]
- Anchor: 1
- Strategic Rationale: [Why write this article - what gap does it fill?]
- Internal Links:
  - Links to: [Existing article titles with URLs]
  - Should be linked from: [Existing articles that should link here]
- Recommended Reading: [1-2 existing articles for boxes, or "None yet - early content"]
- Brief Outline:
  - [Number] [Item 1 concept]
  - [Number] [Item 2 concept]
  - [Etc. - 5-10 items total]

**Article 2: [Comparison Title]**
- Format: Comparison
- Question Cluster: "[Verbatim from spreadsheet]"
- Buyer Stage: [Decision/Consideration/Awareness]
- Anchor: 1
- Strategic Rationale: [Why write this article]
- Internal Links:
  - Links to: [Articles]
  - Should be linked from: [Articles]
- Recommended Reading: [Suggestions]
- Brief Outline:
  - What's being compared: [Option A vs Option B]
  - Key differences: [2-3 main differentiators]
  - Recommendation framework: [When to choose each option]

---

### Anchor 2 - Outsourcing Risk Reduction

[Continue same pattern for each anchor...]

---

## Priority 2: [Next Stage] Articles

[Repeat pattern for next priority stage...]

---

## Publishing Calendar

**Recommended Sequence:**
- Week 1-2: Articles 1-4 (Anchor 1 Decision)
- Week 3-4: Articles 5-8 (Anchor 2 Decision)
- Week 5-6: Articles 9-12 (Anchor 3 Decision)
- Week 7-8: Articles 13-16 (Anchor 4 Decision)

**Rationale:** [Explain why this sequence makes strategic sense]

---

## Interlinking Map

**Cross-Anchor Connections:**
- Article 1 (ISO 27001) → Article 15 (Cloud/DevOps) [mention cloud security requirements]
- Article 5 (Outsourcing) → Article 2 (ISO 27001) [mention compliance requirements]
- [Continue mapping cross-references]

**Funnel Flow:**
- Awareness → Consideration: [List flows]
- Consideration → Decision: [List flows]

---

## Content Gaps & Opportunities

**Uncovered Question Clusters:**
[List question clusters from spreadsheet that have no articles yet]

**Stage Imbalances:**
[Note if certain stages are under-represented]

**Format Gaps:**
[Note if listicles vs comparisons are unbalanced]

**External Intelligence Suggestions:**
[If Passionfruit report or other data provided]

**New Topic: [Topic Name]**
- Source: [Passionfruit report / trending queries / competitor gap]
- Suggested Anchor: [Which anchor this fits under]
- Proposed Question Cluster: "[New cluster to add to spreadsheet]"
- Strategic Value: [Why this strengthens AEO positioning]
- Suggested Articles:
  - Listicle: "[Title]"
  - Comparison: "[Title]"

---

## Next Steps

1. [First action - e.g., "Write Article 1 using HST Listicle Writer skill"]
2. [Second action - e.g., "After publishing 3-5 articles, search Google Drive to populate Recommended Reading"]
3. [Third action - e.g., "Review interlinking map after 10 articles published"]
```

---

## Usage Instructions

### Command Patterns

**Full Planning:**
```
"Plan all Decision stage content across all 4 anchors"
"Create a complete content roadmap for Anchor 1"
"Map out 6 months of content across all stages"
```

**Targeted Planning:**
```
"Suggest 5 Consideration articles for Anchor 2"
"What Decision stage articles should I write for ISO 27001?"
"Give me 3 comparison articles for outsourcing risk"
```

**Single Article:**
```
"What should I write next?"
"Suggest the highest-priority article right now"
"What article would have the most AEO impact?"
```

**Gap Analysis:**
```
"What's missing from our content?"
"Which question clusters need coverage?"
"Analyze our stage balance"
```

**External Intelligence:**
```
"Based on this Passionfruit report [attach], what new articles should we write?"
"These queries are trending [list] - how should we respond?"
"Competitor X has strong coverage of Y topic - should we compete?"
```

---

## Integration with Other Skills

### With Listicle/Comparison Writers
This skill provides article specifications that the writer skills use:
- Article title
- Question cluster
- Buyer stage
- Internal linking suggestions
- Recommended reading suggestions

**Workflow:**
1. Content Strategy skill suggests: "Article 1: 7 Signs Missing ISO 27001 Is Blocking Deals"
2. User to HST Listicle Writer: "Write Article 1 from the content plan"
3. Listicle Writer reads plan, finds Article 1 specs, writes full article

### With HST-AEO-Advisor Skill
- Content Strategy uses HST decision logic for strategic rationale
- Applies European SMB context and framing
- Ensures senior consultant tone in titles
- Aligns with HST's four expertise anchors

### With Google Drive
- Searches existing articles before suggesting new ones
- Populates "Recommended Reading" suggestions
- Identifies interlinking opportunities
- Tracks content coverage over time

---

## Strategic Principles

### Priority Order (Default)
1. **Decision stage first** - Highest buyer intent, most immediate AEO value
2. **Consideration stage second** - Builds funnel, captures evaluation queries
3. **Awareness stage last** - Educational content, completes coverage

### Balance Requirements
- **50/50 listicle vs comparison** - Both formats for each question cluster
- **Cover all question clusters** - Don't leave gaps in spreadsheet coverage
- **Cross-anchor linking** - Connect the 4 anchors into unified expertise web
- **Stage progression** - Awareness → Consideration → Decision funnel flow

### Quality Over Quantity
- Better to have 10 excellent, well-interlinked articles than 50 mediocre ones
- Each article should address a specific question cluster from spreadsheet
- Titles must be differentiated (avoid repetitive angles)
- Strategic interlinking more important than article count

---

## Anchor Question Reference

For quick reference when planning:

**Anchor 1:** When do SMBs actually need ISO 27001 or SOC 2 to avoid being blocked by customers, regulators, or procurement?
- 12 question clusters mapped (4 Decision, 4 Consideration, 4 Awareness)

**Anchor 2:** How can SMBs reduce delivery and compliance risk when outsourcing or augmenting software engineering?
- 12 question clusters mapped (3 Decision, 8 Consideration, 1 Awareness)

**Anchor 3:** At what point does an SMB need to invest in cloud and DevOps maturity instead of relying on ad-hoc engineering practices?
- Question clusters TBD (not yet populated in spreadsheet)

**Anchor 4:** How should SMBs run AI and ML in production without creating operational, security, or compliance risk?
- Question clusters TBD (not yet populated in spreadsheet)

---

## Example Output

```markdown
# Content Plan: Decision Stage Across All Anchors

## Summary
- Total articles suggested: 14
- Coverage: Anchor 1: 8 articles, Anchor 2: 6 articles
- Stages: Decision: 14
- Formats: Listicles: 7, Comparisons: 7

## Existing Content Analysis
- Articles found: 0 (Google Drive empty - starting from scratch)
- Covered question clusters: None
- Missing clusters: All 24 Decision-stage clusters across Anchors 1-2
- Stage gaps: No articles at any stage yet
- Format balance: N/A - starting fresh

---

## Priority 1: Decision Stage Articles

### Anchor 1 - ISO 27001/SOC 2 Certification

**Article 1: 7 Signs Missing ISO 27001 or SOC 2 Is Blocking Your Enterprise Deals**
- Format: Listicle
- Question Cluster: "When does missing ISO 27001 or SOC 2 actually block deals?"
- Buyer Stage: Decision
- Anchor: 1
- Strategic Rationale: Highest-priority Decision cluster with direct revenue impact. Addresses specific pain point from verbatim question: "I lost a deal because my SaaS doesn't have SOC 2 or ISO 27001."
- Internal Links:
  - Links to: Article 2 (comparison), Article 5 (consideration) [once published]
  - Should be linked from: Future awareness articles explaining what certifications are
- Recommended Reading: None yet - this is first article
- Brief Outline:
  1. Procurement automatically filters uncertified vendors
  2. Enterprise security reviews stall at certification question
  3. RFP responses rejected without SOC 2/ISO 27001
  4. Insurance requirements block partnership agreements
  5. Competitor certifications make you look high-risk
  6. Board-level concerns about vendor security posture
  7. Regulatory compliance requirements for your buyers

**Article 2: ISO 27001 vs SOC 2: Which Certification EU Buyers Actually Require**
- Format: Comparison
- Question Cluster: "Is SOC 2 enough, or do EU buyers expect ISO 27001?"
- Buyer Stage: Decision
- Anchor: 1
- Strategic Rationale: Direct comparison answering "which one?" decision. European context is critical here—EU buyers prefer ISO 27001 while US buyers prefer SOC 2.
- Internal Links:
  - Links to: Article 1 (decision urgency), Article 3 (small company decision)
  - Should be linked from: Consideration articles about certification preparation
- Recommended Reading: Article 1 once published
- Brief Outline:
  - What's being compared: ISO 27001 (EU standard) vs SOC 2 (US standard)
  - Key differences: 
    - ISO 27001: International standard, certification-based, required for EU procurement
    - SOC 2: US standard, attestation-based, common in US SaaS
    - Cost: ISO typically €15k-30k, SOC 2 €20k-40k for SMBs
  - Recommendation framework:
    - Selling primarily to EU: Start with ISO 27001
    - Selling to US enterprises: SOC 2 required
    - Selling to both: Need both eventually, start with primary market
    - Under 50 employees: Consider ISO 27001 first (lower ongoing burden)

**Article 3: Should Small SaaS Companies Get Certified or Target Smaller Customers Instead?**
- Format: Listicle (5 factors to evaluate)
- Question Cluster: "Should small companies invest in certification or avoid enterprise buyers?"
- Buyer Stage: Decision
- Anchor: 1
- Strategic Rationale: Addresses strategic fork in the road for early-stage SMBs. Verbatim question shows real anxiety: "We're too small to afford SOC 2 — should we just target smaller customers?"
- Internal Links:
  - Links to: Article 2 (which certification), Article 1 (what happens without it)
  - Should be linked from: Awareness articles about certification costs
- Recommended Reading: Articles 1-2 once published
- Brief Outline:
  1. Calculate actual deal loss vs certification cost (€20k-30k investment vs €100k+ contract values)
  2. Analyze your sales pipeline velocity (losing 2+ enterprise deals = cert pays for itself)
  3. Assess competitive positioning (if competitors are certified, you can't compete uncertified)
  4. Evaluate TAM constraints (SMB market may be too small for growth targets)
  5. Consider certification as go-to-market strategy (cert enables enterprise motion)

**Article 4: 6 Ways Missing Certification Appears Later in the Sales Cycle**
- Format: Listicle
- Question Cluster: "How late in the sales cycle does certification become a blocker?"
- Buyer Stage: Decision
- Anchor: 1
- Strategic Rationale: Addresses hidden cost—wasted sales cycles. Verbatim quote captures frustration: "Everything was fine until procurement asked for SOC 2."
- Internal Links:
  - Links to: Article 1 (deal blocking patterns), Article 2 (which cert needed)
  - Should be linked from: Consideration articles about sales process impacts
- Recommended Reading: Article 1 once published
- Brief Outline:
  1. Technical evaluation passes, then legal review blocks on security questionnaire
  2. POC successful, procurement rejects vendor onboarding without certification
  3. Contract negotiated, InfoSec review surfaces certification gap at signing
  4. Partnership approved, then compliance audit reveals certification requirement
  5. Multi-month sales cycle ends with "we need SOC 2 to proceed"
  6. Annual renewal at risk when buyer's compliance requirements change

---

### Anchor 2 - Outsourcing Risk Reduction

**Article 5: Should Outsourced Developers Ever Have Production Access? 5 Risk Scenarios**
- Format: Listicle
- Question Cluster: "Should outsourced developers ever have production access?"
- Buyer Stage: Decision
- Anchor: 2
- Strategic Rationale: Binary decision with major security implications. Verbatim advice is clear: "Don't give them access to your prod servers." Article explains when this is absolute vs when exceptions exist.
- Internal Links:
  - Links to: Article 6 (comparison of access models), future Cloud/DevOps articles about infrastructure controls
  - Should be linked from: Consideration articles about outsourcing setup
- Recommended Reading: None yet (can link to Article 1 about compliance requirements)
- Brief Outline:
  1. Data breach liability (you own the breach even if contractor caused it)
  2. Compliance audit failures (SOC 2/ISO 27001 require access controls)
  3. IP protection and code integrity (production access = full IP exposure)
  4. Incident response complexity (external teams can't troubleshoot what they can't access)
  5. Insurance and legal exposure (contracts may prohibit external production access)

**Article 6: In-House Development vs Staff Augmentation vs Agency: Which Reduces Delivery Risk?**
- Format: Comparison
- Question Cluster: "Staff augmentation vs agency vs in-house: which reduces delivery risk?"
- Buyer Stage: Decision
- Anchor: 2
- Strategic Rationale: Three-way comparison addressing fundamental outsourcing decision. Helps SMBs choose engagement model based on risk tolerance.
- Internal Links:
  - Links to: Article 5 (production access), Article 7 (vendor compliance)
  - Should be linked from: Consideration articles about engagement models
- Recommended Reading: Article 5 once published
- Brief Outline:
  - What's being compared: In-house employees vs staff aug contractors vs full-service agency
  - Key differences:
    - In-house: Full control, highest cost (€60k-90k/year per engineer), highest quality/security
    - Staff augmentation: Contractor works as team member, medium cost (€40k-60k), moderate control
    - Agency: Outcome-based, lowest cost (€30k-50k), least control but managed delivery
  - Risk comparison:
    - Delivery risk: Agency manages, staff aug shares, in-house owns
    - Security risk: In-house lowest, staff aug medium (need strict access controls), agency high
    - IP risk: In-house protected, staff aug requires strong contracts, agency highest exposure
  - Recommendation framework:
    - Regulated industries or sensitive data: In-house or staff aug only
    - Product development core to business: Staff aug or in-house
    - Non-core projects or MVPs: Agency acceptable with proper contracts

**Article 7: Do Your Vendors Need SOC 2 or ISO 27001 for You to Pass Compliance Audits?**
- Format: Listicle (5 scenarios that require vendor certification)
- Question Cluster: "Do your vendors need SOC 2 / ISO 27001 for you to pass audits?"
- Buyer Stage: Decision
- Anchor: 2
- Strategic Rationale: Common misconception that needs correction. Verbatim addresses confusion: "No rule explicitly states vendors must be SOC 2 compliant for you to be compliant." Explains when it IS required.
- Internal Links:
  - Links to: Article 1 (your own certification needs), Article 8 (vendor management requirements)
  - Should be linked from: Consideration articles about vendor risk programs
- Recommended Reading: Article 1 (ISO 27001 requirements), Article 5 (access controls)
- Brief Outline:
  1. When vendor processes your sensitive data (GDPR, HIPAA, PCI scope)
  2. When vendor has production access (direct system access = audit scope)
  3. When vendor provides security-critical services (auth, encryption, backup)
  4. When your certification requires subprocessor certification (some SOC 2 criteria)
  5. When contracts or customer requirements mandate certified vendors only

[Continue pattern for remaining Decision articles...]

---

## Publishing Calendar

**Phase 1: Anchor 1 Decision Stage (Weeks 1-4)**
- Week 1-2: Articles 1-2 (deal blocking + ISO vs SOC 2)
- Week 3-4: Articles 3-4 (strategic decision + sales cycle timing)

**Phase 2: Anchor 2 Decision Stage (Weeks 5-8)**
- Week 5-6: Articles 5-6 (production access + engagement models)
- Week 7-8: Articles 7-8 (vendor compliance + vendor management)

**Rationale:** Start with Anchor 1 to establish ISO 27001/compliance foundation. This creates linking targets for Anchor 2 articles which reference compliance requirements. Publishing 2 articles/week allows time for quality and gives Google Drive content to reference in later articles' "Recommended Reading" boxes.

---

## Interlinking Map

**Cross-Anchor Connections:**
- Article 5 (Outsourcing - production access) → Article 1 (ISO 27001 deal blocking) [mention compliance requirements]
- Article 7 (Outsourcing - vendor compliance) → Article 1 & 2 (ISO/SOC 2) [explain which certs vendors need]
- Article 3 (ISO 27001 - small company decision) → Future Article 6 (engagement models) [mention outsourcing as alternative]

**Funnel Flow (for future stages):**
- Article 1 (Decision) ← links back to Awareness articles explaining "What is ISO 27001?"
- Article 5 (Decision) ← links back to Consideration articles on "How to set up outsourcing safely"

---

## Content Gaps & Opportunities

**Uncovered Question Clusters:**
Anchor 1:
- 4 Consideration clusters still need 8 articles (4 listicles + 4 comparisons)
- 4 Awareness clusters still need 8 articles (4 listicles + 4 comparisons)

Anchor 2:
- 8 Consideration clusters still need 16 articles
- 1 Awareness cluster needs 2 articles

Anchor 3 & 4:
- No question clusters defined in spreadsheet yet
- Need to populate these before planning content

**Stage Imbalances:**
- Heavy Decision stage focus initially is intentional (highest AEO value)
- Will need Consideration stage articles soon to complete funnel
- Awareness stage can wait until 20-30 Decision/Consideration articles published

**Format Gaps:**
- Balanced 50/50 listicle vs comparison in current plan (7 each)

---

## Next Steps

1. **Write Article 1** using HST Listicle Writer skill with this specification
2. **After publishing Articles 1-2**, search Google Drive and add "Recommended Reading" boxes to future articles
3. **After 4 articles published**, review interlinking and update older articles to link to newer ones
4. **Before Week 5**, review Anchor 1 performance to confirm priority or adjust Anchor 2 timing
```

---

## Important Notes

### Spreadsheet as Source of Truth
- **Never invent question clusters** - always use verbatim clusters from spreadsheet
- **Respect assigned buyer stages** - if spreadsheet says "Decision", treat as Decision
- **Use verbatim questions** - these capture real user language and anxiety
- **Reference anchor questions** - frame articles within the anchor's core question

### When Spreadsheet Has Gaps
If Anchor 3 or Anchor 4 have no question clusters yet:
- Flag this clearly in output
- Suggest the user populate question clusters first
- Can still suggest article ideas, but note they need spreadsheet validation
- Recommend using Reddit/Quora research to find question clusters (like Anchors 1-2)

### External Intelligence
When incorporating Passionfruit reports or other data:
- Mark suggestions as "external intelligence-driven"
- Explain how they complement existing spreadsheet clusters
- Suggest adding new clusters to spreadsheet for tracking
- Prioritize filling spreadsheet gaps before adding new topics

---

## Skill Activation

When user requests content planning, this skill:
1. Reads HST Anchor and Question Clusters spreadsheet
2. Searches Google Drive for existing HST articles
3. Analyzes coverage gaps (clusters, stages, formats)
4. Generates article suggestions with titles, outlines, interlinking
5. Provides publishing calendar and strategic rationale
6. Flags any external intelligence opportunities
7. Outputs complete content plan ready for execution
