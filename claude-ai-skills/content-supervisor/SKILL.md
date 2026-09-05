---
name: content-supervisor
description: |
  Universal content workflow supervisor. Configures per-client through skill import, research, or interview. Orchestrates content creation pipeline with two-gate validation (Content Gate, Publish Gate). Handles single articles, parallel batches, and interlinked content. Communicates with skills through structured feedback for revision loops. Triggers on any content workflow request.
---

# Content Supervisor Skill

## Purpose

Single entry point for content production workflows. The supervisor:
- Configures itself for any client (via skill import, research, or interview)
- Guides users through workflow decisions
- Orchestrates skills (Content Strategy → Writer → Entity Schema → HTML)
- Validates quality at two gates (Content Gate, Publish Gate)
- Communicates feedback to skills for revision
- Presents unified review packages for human approval

---

## Table of Contents

1. [Onboarding](#1-onboarding)
2. [Workflow Guidance](#2-workflow-guidance)
3. [Orchestration](#3-orchestration)
4. [Validation Gates](#4-validation-gates)
5. [Skill Communication](#5-skill-communication)
6. [Review & Approval](#6-review--approval)
7. [State Management](#7-state-management)
8. [Configuration Schema](#8-configuration-schema)
9. [Feedback Schema](#9-feedback-schema)

---

## 1. Onboarding

When invoked in a new project with no existing configuration, the supervisor offers four paths:

```
Supervisor: I'll set up this project for a new client. How would you like to configure?

1. Load existing skill file(s)
   → Best when: You have .skill files with client data defined
   → Time: ~30 seconds

2. Research from website and public sources
   → Best when: Client has existing website/content to analyze
   → Time: ~3-5 minutes

3. Start from a template
   → Best when: Common client type (B2B SaaS, Fintech, Healthcare, etc.)
   → Time: ~2 minutes

4. Walk me through setup questions
   → Best when: Unique client, minimal online presence
   → Time: ~10-15 minutes
```

---

### 1.1 Path: Skill Import

**Flow:**
1. User uploads .skill file(s)
2. Supervisor parses SKILL.md content
3. Extracts configuration fields
4. Presents draft config for confirmation
5. User confirms or edits
6. Saves and activates

**Skill Parsing Logic:**

| Skill Section Pattern | Maps To |
|----------------------|---------|
| "Who [Client] Is" | client.name, client.description |
| "What [Client] Does" | client.services, content.pillars |
| "[Year] Goals" | client.objectives, audience.target |
| "Target Client Profile" | audience.size, audience.industries |
| "Certifications" | client.credentials |
| "Industries Served" | audience.industries |
| "Core Services" | content.pillars |
| "Decision Rules" | content.decision_logic[] |
| "What Good Looks Like" | quality.benchmarks |
| "Tone of Voice" | tone.style, tone.avoid, tone.characteristics |
| "Output Expectations" | quality.requirements |
| Contains "never mention pricing" | rules.hard_blocks[] |
| Contains "Reddit" / "Quora" section | content.community_mode |

**Multiple Skills:**

Skills layer on top of each other:
- Layer 1: Base client skill (identity, tone, audience)
- Layer 2: Strategy skill (pillars, buyer journey)
- Layer 3: Writer skills (article templates)
- Layer 4: User overrides (manual edits during confirmation)

Merge strategy:
- Identity fields: Later layers override
- Lists (pillars, rules): Accumulate and dedupe
- Quality thresholds: Later layers override

**Connecting Assets:**

After skill import, prompt for:
- Anchor spreadsheet (upload CSV or link Google Sheet)
- Entity library (upload or create empty)
- Existing content (sitemap URL or skip)
- Site template (sample URL or skip)

---

### 1.2 Path: Research-Driven

**Flow:**
1. User provides seed: company name, website URL, optional notes
2. Supervisor researches (see Research Capabilities below)
3. Builds draft configuration from findings
4. Presents each section with source citations
5. User confirms or adjusts
6. Saves and activates

**Research Capabilities:**

| Source | Extracts | Method |
|--------|----------|--------|
| Homepage | Value proposition, positioning | `web_fetch` → parse hero, headings |
| About page | Company description, story | `web_fetch` → parse content |
| Team page | People entities (name, title) | `web_fetch` → structured extraction |
| Product pages | Product entities, terminology | `web_fetch` → parse each product |
| Blog | Topics, tone patterns, structure | `web_fetch` → analyze multiple posts |
| Footer | Geography, compliance mentions | `web_fetch` → parse footer |
| Sitemap | Full content inventory | `web_fetch` sitemap.xml |
| Wikipedia | Industry context, terminology | `web_search` → `web_fetch` |
| Reddit | Real questions, pain points, language | `web_search` site:reddit.com → `web_fetch` threads |
| Quora | Questions in user language | `web_search` site:quora.com → `web_fetch` |
| Competitors | Positioning to differentiate | `web_search` → `web_fetch` competitor blogs |

**Draft Config Presentation:**

Present each section with:
- Extracted values
- Source (where it came from)
- Confidence level
- [Confirm] [Edit] options

**Anchor Spreadsheet Generation:**

If no spreadsheet exists, offer to create from Reddit/Quora questions:
- Group by detected pillars
- Assign buyer stages (Decision, Consideration, Awareness)
- Preserve verbatim question language
- Export as Google Sheet or CSV

---

### 1.3 Path: Template-Based

**Available Templates:**

| Template | Target Audience | Default Pillars |
|----------|-----------------|-----------------|
| B2B SaaS | CTOs, Engineering leads | Product, Integration, Security, Scale |
| Fintech | CFOs, Compliance | Compliance, Risk, Automation, Integration |
| Healthcare Tech | CIOs, Clinical leads | Compliance (HIPAA), Integration, Security, Workflow |
| Professional Services | Partners, Directors | Expertise areas, Methodology, Client outcomes |
| E-commerce | COOs, Marketing | Conversion, Operations, Platform, Growth |

**Flow:**
1. User selects template
2. Supervisor loads template defaults
3. Asks 4-5 customization questions (name, URL, specific focus)
4. Optionally runs quick research on provided URL
5. Merges customizations with template
6. Saves and activates

---

### 1.4 Path: Interview

**Flow:**
1. Client Identity (name, description, industry, target size, geography)
2. Content Purpose (goals, audience, decisions they make)
3. Content Pillars (3-5 topic areas)
4. Tone and Voice (style, characteristics, avoid words)
5. Business Rules (hard blocks, required elements)
6. Quality Thresholds (gate strictness, fact verification, retry limits)
7. Assets (spreadsheet, entity library, content index, template)
8. Confirmation

**Fallback:**
Research path falls back to interview when:
- Website is minimal or under construction
- Industry too niche for Reddit/Quora presence
- Competitor analysis blocked

---

### 1.5 Returning Sessions

When supervisor is invoked in a project with existing configuration:

```
Supervisor: Welcome back. Configured for [Client Name].

Status:
• [X] articles published
• [Y] in draft
• Anchor spreadsheet last updated [date]

What would you like to do?
1. Create new content
2. Review pending drafts
3. Check content gaps
4. Update configuration
```

---

## 2. Workflow Guidance

After configuration, the supervisor guides content creation through intake questions.

### 2.1 Intake Decision Tree

```
Q1: What's the scope?
├── "One article" ──────────────────▶ Single article flow
├── "A few related articles (2-4)" ─▶ Small batch flow
├── "Full content push (5+)" ───────▶ Large batch flow
└── "What should I write next?" ────▶ Gap analysis flow

Q2: How much direction?
├── "I have a specific topic" ──────▶ Ask Q3
├── "Suggest based on gaps" ────────▶ Invoke Content Strategy (analysis mode)
└── "Continue the current plan" ────▶ Load existing roadmap

Q3: (If specific topic) What area?
├── Present pillars from config
├── User selects pillar
└── Present question clusters from anchor spreadsheet

Q4: How much control?
├── "Approve each step" ────────────▶ Pause after every skill
├── "Just show final review" ───────▶ Run pipeline, pause at end
└── "Full auto, flag issues only" ──▶ Run silently, interrupt on failure
```

### 2.2 Control Levels

**Level 1: Step-by-Step**
- Pause after Content Strategy (show spec, allow edit)
- Pause after Writer (show draft, allow edit or request revision)
- Pause after Entity Schema (show entities, allow review)
- Pause after HTML (show preview, allow edit)
- Pause for final approval

**Level 2: Final Review Only**
- Run entire pipeline
- Show progress indicator
- Present unified review package at end

**Level 3: Full Auto**
- Run entire pipeline silently
- Only interrupt if gate fails after max retries
- Present summary when complete

---

## 3. Orchestration

### 3.1 Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CONTENT PIPELINE                                │
└─────────────────────────────────────────────────────────────────────────────┘

                           CREATION PHASE
                                 │
              ┌──────────────────┴──────────────────┐
              ▼                                     │
     ┌─────────────────┐                           │
     │ Content Strategy │                           │
     │ Skill            │                           │
     └────────┬────────┘                           │
              │                                     │
              ▼                                     │
     ┌─────────────────┐                           │
     │ Writer Skill    │                           │
     │ (Listicle or    │◀──────────────────────────┤
     │  Comparison)    │      (revision loop)      │
     └────────┬────────┘                           │
              │                                     │
              ▼                                     │
     ┌─────────────────┐                           │
     │  CONTENT GATE   │───── REVISE ─────────────▶│
     └────────┬────────┘                           │
              │                                     │
            PASS                                   │
              │                                     │
              ▼                                     │
                           PROCESSING PHASE        │
              │                                     │
              ▼                                     │
     ┌─────────────────┐                           │
     │ Entity Schema   │                           │
     │ Validator       │                           │
     └────────┬────────┘                           │
              │                                     │
              ▼                                     │
     ┌─────────────────┐                           │
     │ HTML Converter  │                           │
     └────────┬────────┘                           │
              │                                     │
              ▼                                     │
     ┌─────────────────┐                           │
     │  PUBLISH GATE   │───── REVISE ─────────────▶│
     └────────┬────────┘                           │
              │                                     │
            PASS                                   
              │                                     
              ▼                                     
                           REVIEW PHASE            
              │                                     
              ▼                                     
     ┌─────────────────┐                           
     │ Review Package  │                           
     │ → Human Review  │                           
     └────────┬────────┘                           
              │                                     
        ┌─────┴─────┐                              
        ▼           ▼                              
    APPROVE      REVISE                            
        │           │                              
        ▼           └────────────────────────────▶│
    PUBLISH                                        
```

### 3.2 Prompt Generation

The supervisor constructs prompts for each skill invocation:

**Initial Invocation:**
```
[Skill instructions from skill file]
[Client configuration]
[Task specification]
[Context from previous steps if any]
```

**Revision Invocation:**
```
[Skill instructions from skill file]
[Client configuration]
[Original task specification]
[Current draft]
[Structured feedback object]
[Revision constraints]
```

**Template: Initial Writer Prompt**

```markdown
# Task: Write Article

## Client Configuration
{injected from client_config}

## Article Specification
- Title: {title}
- Format: {listicle|comparison}
- Question cluster: {verbatim from spreadsheet}
- Buyer stage: {Decision|Consideration|Awareness}
- Pillar: {pillar_name}
- Outline: {from Content Strategy}
- Interlinking: {suggested links}

## Quality Targets
- Fact density: {target} specific numbers per section
- Decision logic: {target}+ "if X then Y" patterns
- Source attribution: Name sources for statistics
- Context markers: Include {required_terms}

## Hard Rules
{list from client_config.rules.hard_blocks}

## Output
Complete markdown article following {format} structure.
```

**Template: Revision Prompt**

```markdown
# Revision Request

You are revising a {format} article. Attempt {current} of {max}.

## Client Configuration
{injected from client_config}

## Original Task
{original article specification}

## Current Draft
{full article markdown}

## Validation Feedback

Score: {score}/{threshold} — {PASS|FAIL}

### What Needs to Change

{for each failure}
**{criterion}** (score: {score}, target: {target})

Locations:
{for each location}
- {section}, {paragraph}: "{excerpt}"
  Issue: {issue}
  Fix: {fix_guidance}
{end for}
{end for}

### What NOT to Change
{list of sections/elements that scored well}

### Constraints
- {constraint_1}
- {constraint_2}

## Output
Complete revised article in markdown.
```

### 3.3 Batch Processing

**Parallel Execution:**
```
Content Strategy outputs batch spec
              │
    ┌─────────┼─────────┬─────────┐
    ▼         ▼         ▼         ▼
 Writer 1  Writer 2  Writer 3  Writer 4   (parallel)
    │         │         │         │
    ▼         ▼         ▼         ▼
 Gate 1    Gate 2    Gate 3    Gate 4     (parallel)
    │         │         │         │
    └─────────┴────┬────┴─────────┘
                   │
              (individual pass/revise per article)
                   │
                   ▼
           Batch Reconciliation
                   │
                   ▼
         Unified Review Package
```

**Batch Reconciliation:**

After individual articles pass gates, reconciliation handles cross-article concerns:

| Check | Action |
|-------|--------|
| Cross-links resolve | Verify Article A's link to Article B points to passing article |
| No broken dependencies | If A links to B and B failed, flag A |
| Interlinking completeness | All suggested links from Content Strategy present? |
| Entity consistency | Same entity uses same canonical name across articles |

**Timing:**
- Single article: ~15 seconds (blocking)
- Batch of 4: ~20 seconds (parallel)

---

## 4. Validation Gates

### 4.1 Content Gate

Runs after Writer skill, before processing phase.

**Phase 1: Hard Blocks (sync, <1s)**

Fail immediately if any triggered.

| Check | Detection | On Fail |
|-------|-----------|---------|
| No cost information | Regex: `€|£|\$|per month|pricing|cost|fee|budget` | REJECT |
| Required sections present | Parse markdown for expected H2s | REJECT |
| Metadata complete | Check frontmatter fields | REJECT |
| Quick Answer exists | Section present, 40-60 words | REJECT |
| Key Takeaways count | Exactly 3 bullets | REJECT |
| Format requirements | Listicle: number in title; Comparison: "vs" + table | REJECT |
| Client hard blocks | Check all `client_config.rules.hard_blocks` | REJECT |

**Phase 2: Quality Scoring (parallel, 2-3s)**

All signals scored simultaneously.

| Signal | Measurement | Weight |
|--------|-------------|--------|
| Fact density | Count of specific numbers per section | 20% |
| Decision logic | Count of conditional patterns ("if X", "when Y") | 20% |
| Context markers | Presence of required terms from config | 15% |
| Source attribution | Count of "According to", named sources | 15% |
| Tone compliance | Absence of avoid-words, presence of preferred style | 15% |
| Spec alignment | Interlinking present, buyer stage appropriate | 15% |

**Thresholds (configurable in client_config):**
- 80-100: PASS
- {threshold}-79: PASS WITH FLAGS (proceed, human sees warnings)
- Below {threshold}: REVISE

**Phase 3: Fact Verification (async, non-blocking)**

- Select 2-3 quantified claims
- Web search for corroboration
- Results appended to review package when complete
- Does NOT block pipeline

**Content Gate Output:**

```json
{
  "gate": "content",
  "result": "PASS|PASS_WITH_FLAGS|REVISE|REJECT",
  "score": 74,
  "threshold": 70,
  
  "hard_blocks": {
    "passed": true,
    "checks": 7,
    "failures": []
  },
  
  "quality_signals": {
    "fact_density": {"score": 85, "target": 80},
    "decision_logic": {"score": 90, "target": 70},
    "context_markers": {"score": 80, "target": 70},
    "source_attribution": {"score": 45, "target": 60, "failing": true},
    "tone_compliance": {"score": 70, "target": 70},
    "spec_alignment": {"score": 75, "target": 70}
  },
  
  "fact_verification": {
    "status": "IN_PROGRESS|COMPLETE",
    "claims_checked": 3,
    "results": []
  },
  
  "failures": [...],
  "flags": [...],
  "proceed": true
}
```

---

### 4.2 Publish Gate

Runs after Entity Schema Validator and HTML Converter.

**Technical Validation (sync, <2s):**

| Check | Detection | On Fail |
|-------|-----------|---------|
| Valid HTML | Parse without errors | REJECT |
| Valid JSON-LD | Schema parses, has @context and @graph | REJECT |
| Schema embedded | `<script type="application/ld+json">` present | REJECT |
| Article schema complete | Has headline, author, datePublished | REJECT |
| No markdown remnants | No `##`, `**`, triple backticks in HTML | REJECT |
| Template applied | Expected wrapper elements present | REJECT |

**Soft Validation (warnings, don't block):**

| Check | Detection | Action |
|-------|-----------|--------|
| Internal links valid | URL patterns correct | WARN |
| Images referenced | Paths valid | WARN |
| Entity confidence | Average ≥ threshold | WARN if low |
| Pending entities | ≤ threshold % of total | WARN if high |

**Publish Gate Output:**

```json
{
  "gate": "publish",
  "result": "PASS|REVISE|REJECT",
  
  "technical": {
    "passed": true,
    "checks": 6,
    "failures": []
  },
  
  "entities": {
    "total": 5,
    "active": 4,
    "pending": 1,
    "confidence_avg": 82
  },
  
  "warnings": [
    "1 image path unresolved"
  ],
  
  "content_gate_summary": {
    "score": 74,
    "flags_carried_forward": [...]
  },
  
  "fact_verification": {
    "status": "COMPLETE",
    "results": [...]
  },
  
  "proceed_to_review": true
}
```

---

## 5. Skill Communication

### 5.1 Feedback Object Schema

When validation fails, the supervisor constructs a structured feedback object:

```json
{
  "feedback_type": "revision_request",
  "source": "content_gate|publish_gate",
  "timestamp": "ISO8601",
  
  "original_task": {
    "article_id": "string",
    "format": "listicle|comparison",
    "question_cluster": "string"
  },
  
  "attempt": {
    "current": 1,
    "max": 2,
    "history": [
      {
        "attempt": 1,
        "score": 52,
        "primary_failure": "source_attribution",
        "feedback_given": "summary"
      }
    ]
  },
  
  "validation_result": {
    "overall_score": 58,
    "threshold": 70,
    "passed": false
  },
  
  "failures": [
    {
      "criterion": "source_attribution",
      "score": 45,
      "target": 60,
      "severity": "blocking|warning",
      
      "locations": [
        {
          "section": "Section 2",
          "paragraph": 1,
          "text": "excerpt of problematic text",
          "issue": "description of what's wrong"
        }
      ],
      
      "fix_guidance": "specific instruction on how to fix",
      
      "examples": [
        {
          "before": "problematic text",
          "after": "corrected text"
        }
      ]
    }
  ],
  
  "preserve": {
    "sections": ["Section 1", "Section 3"],
    "elements": ["Quick Answer", "FAQ"],
    "note": "These scored well. Do not modify."
  },
  
  "constraints": {
    "word_count_change": "minimal",
    "structure_change": "none",
    "tone_change": "none"
  }
}
```

### 5.2 Feedback Templates

**Quality Score Low:**
```markdown
## Revision Required: Quality Below Threshold

**Score:** {score}/100 (threshold: {threshold})

### Failing Signals

**{signal_name}** (score: {score}, target: {target})

Locations:
- {section}, {paragraph}: "{excerpt}"
  Issue: {issue}

Fix guidance: {guidance}

### Preserve
{list of good sections}

### Constraints
{constraints}
```

**Hard Block Violation:**
```markdown
## Revision Required: Hard Block Violation

**Rule:** {rule_name}

Found: "{violating_text}"
Location: {section}

Fix: {specific_instruction}
```

**Unverified Fact:**
```markdown
## Revision Required: Unverified Claim

**Claim:** "{claim}"
**Location:** {section}

Verification result: {result}

Options:
1. Find and cite a credible source
2. Rephrase: "{suggested_rephrase}"
3. Remove if not essential
```

### 5.3 Revision Loop

```
Writer produces draft v{n}
         │
         ▼
Content Gate validates
         │
    ┌────┴────┐
    │         │
  PASS      FAIL
    │         │
    ▼         ▼
Continue   attempt < max?
                │
           ┌────┴────┐
           │         │
         YES        NO
           │         │
           ▼         ▼
    Construct     ESCALATE
    feedback      to human
    object
           │
           ▼
    Construct
    revision prompt
    (skill instructions +
     config + draft +
     feedback)
           │
           ▼
    Writer produces
    draft v{n+1}
           │
           ▼
    Loop back to
    Content Gate
```

### 5.4 Cross-Skill Routing

Feedback routes to the appropriate skill based on failure type:

| Failure Type | Route To | Example |
|--------------|----------|---------|
| Content quality | Writer skill | Source attribution low |
| Structure missing | Writer skill | FAQ section missing |
| Entity inconsistency | Writer skill | Use canonical entity name |
| Schema invalid | Entity Schema Validator | JSON-LD parse error |
| HTML malformed | HTML Converter | Template not applied |
| Entity conflict | Human | Conflicting sources for entity |

---

## 6. Review & Approval

### 6.1 Review Package

When content passes both gates, generate a review package:

```markdown
# Review Package: {article_title}

## Summary
- **Quality Score:** {score}/100
- **Technical Status:** {passed|warnings}
- **Entity Status:** {active}/{total}, {pending} pending
- **Fact Verification:** {complete|pending}

## Flags for Review

### {Priority Level}: {Flag Title}
{Description}
**Location:** {section}
**Suggested action:** {action}

## Content Preview
[Link or embedded preview]

## Artifacts
- Markdown: {path}
- Schema: {path}
- HTML: {path}

## Actions
- [ ] APPROVE — Publish as-is
- [ ] APPROVE WITH EDITS — Minor changes, then publish
- [ ] RETURN FOR REVISION — Send back with feedback
- [ ] REJECT — Archive, do not publish
```

### 6.2 Batch Review Package

For multiple articles:

```markdown
# Batch Review: {batch_name}

## Summary
- **Articles:** {total}
- **Passed:** {passed_count}
- **Pending revision:** {revising_count}
- **Cross-links:** {resolved}/{total}

## Per-Article Status

| Article | Score | Status | Flags |
|---------|-------|--------|-------|
| {title} | {score} | {status} | {flag_count} |

## Batch-Level Flags
{cross-link issues, entity inconsistencies}

## Actions
- [ ] APPROVE ALL — Publish entire batch
- [ ] REVIEW INDIVIDUALLY — See each article
- [ ] HOLD BATCH — Wait for revisions to complete
```

### 6.3 Human Decision Routing

| Human Decision | System Action |
|----------------|---------------|
| APPROVE | Mark ready for publish, move to outputs |
| APPROVE WITH EDITS | Accept manual edits, bypass re-validation |
| RETURN FOR REVISION | Create feedback from human notes, re-enter pipeline |
| REJECT | Archive with rejection reason |

---

## 7. State Management

### 7.1 Workflow State Schema

```json
{
  "session_id": "workflow-{timestamp}",
  "client_id": "string",
  "mode": "single|small_batch|large_batch|gap_analysis",
  "control_level": "step_by_step|final_review|full_auto",
  
  "intake": {
    "scope": "string",
    "direction": "string",
    "pillar": "string",
    "question_clusters": ["string"],
    "completed_at": "ISO8601"
  },
  
  "plan": {
    "articles": [
      {
        "id": "string",
        "title": "string",
        "format": "listicle|comparison",
        "status": "pending|writing|validating|processing|review|approved|rejected",
        "current_stage": "string"
      }
    ],
    "interlinking": {
      "{article_id} → {article_id}": "{section}"
    }
  },
  
  "gates": {
    "{article_id}": {
      "content_gate": {
        "status": "pending|passed|failed",
        "score": 0,
        "attempt": 1,
        "result": {}
      },
      "publish_gate": {
        "status": "pending|passed|failed",
        "result": {}
      }
    }
  },
  
  "async_tasks": {
    "fact_verification_{article_id}": {
      "status": "pending|in_progress|complete",
      "results": []
    }
  },
  
  "revision_history": [
    {
      "article_id": "string",
      "attempt": 1,
      "score": 52,
      "feedback": {},
      "timestamp": "ISO8601"
    }
  ],
  
  "outputs": {
    "{article_id}": {
      "markdown": "path",
      "schema": "path",
      "html": "path"
    }
  }
}
```

### 7.2 State Persistence

State persists across conversation turns within a session. Enables:
- Resume after interruption
- Track revision history
- Reference previous attempts in feedback
- Batch progress monitoring

---

## 8. Configuration Schema

### 8.1 Client Configuration

```json
{
  "config_version": "1.0",
  "created_at": "ISO8601",
  "last_updated": "ISO8601",
  "onboarding_path": "skill_import|research|template|interview",
  
  "client": {
    "name": "string",
    "description": "string",
    "industry": "string",
    "credentials": ["string"],
    "target_customer_size": "smb|mid_market|enterprise|consumer",
    "target_customer_range": "string",
    "geography": ["string"]
  },
  
  "content": {
    "purpose": ["aeo", "lead_gen", "thought_leadership", "product_education"],
    "audience": {
      "titles": ["string"],
      "decisions": "string",
      "problems": "string"
    },
    "pillars": [
      {
        "id": "pillar-{n}",
        "name": "string",
        "description": "string"
      }
    ],
    "decision_logic": [
      {
        "category": "string",
        "rules": ["if X then Y statements"]
      }
    ],
    "community_mode": {
      "enabled": true,
      "guidelines": "string"
    }
  },
  
  "tone": {
    "style": "senior_consultant|friendly_expert|corporate|technical|conversational",
    "characteristics": {
      "decision_focused": true,
      "data_heavy": true,
      "example_rich": true,
      "direct": true
    },
    "avoid_words": ["string"],
    "required_context": ["string"]
  },
  
  "rules": {
    "hard_blocks": [
      {
        "id": "string",
        "description": "string",
        "detection": "regex|presence|absence",
        "pattern": "string"
      }
    ],
    "required_elements": [
      {
        "id": "string",
        "description": "string",
        "detection": "presence",
        "terms": ["string"]
      }
    ]
  },
  
  "quality": {
    "content_gate_threshold": 70,
    "publish_gate_threshold": 70,
    "fact_verification": "required|optional|skip",
    "max_revision_attempts": 2,
    "quality_signals": {
      "fact_density": {"weight": 20, "target": 2},
      "decision_logic": {"weight": 20, "target": 5},
      "context_markers": {"weight": 15, "terms": ["string"]},
      "source_attribution": {"weight": 15, "target": 3},
      "tone_compliance": {"weight": 15},
      "spec_alignment": {"weight": 15}
    }
  },
  
  "assets": {
    "anchor_spreadsheet": {
      "type": "google_sheet|csv|none",
      "url": "string",
      "local_path": "string"
    },
    "entity_library": {
      "type": "google_sheet|json|none",
      "url": "string",
      "status": "active|to_be_created"
    },
    "existing_content": {
      "type": "sitemap|folder|none",
      "url": "string"
    },
    "template": {
      "type": "wordpress|webflow|custom|none",
      "sample_url": "string"
    }
  },
  
  "publishing": {
    "platform": "wordpress|webflow|custom|manual",
    "workflow": "direct|draft_then_review"
  }
}
```

---

## 9. Feedback Schema

### 9.1 Complete Feedback Object

```json
{
  "feedback_type": "revision_request|escalation|approval",
  "source": "content_gate|publish_gate|human|batch_reconciliation",
  "timestamp": "ISO8601",
  
  "original_task": {
    "article_id": "string",
    "title": "string",
    "format": "listicle|comparison",
    "question_cluster": "string",
    "pillar": "string",
    "buyer_stage": "Decision|Consideration|Awareness"
  },
  
  "attempt": {
    "current": 1,
    "max": 2,
    "history": [
      {
        "attempt": 1,
        "score": 0,
        "primary_failure": "string",
        "feedback_summary": "string",
        "timestamp": "ISO8601"
      }
    ]
  },
  
  "validation_result": {
    "gate": "content|publish",
    "overall_score": 0,
    "threshold": 70,
    "passed": false,
    "signals": {
      "{signal_name}": {
        "score": 0,
        "target": 0,
        "passed": false
      }
    }
  },
  
  "failures": [
    {
      "criterion": "string",
      "score": 0,
      "target": 0,
      "severity": "critical|blocking|warning",
      
      "locations": [
        {
          "section": "string",
          "paragraph": 0,
          "line": 0,
          "text": "excerpt",
          "issue": "description"
        }
      ],
      
      "fix_guidance": "string",
      
      "examples": [
        {
          "before": "string",
          "after": "string"
        }
      ]
    }
  ],
  
  "preserve": {
    "sections": ["string"],
    "elements": ["string"],
    "note": "string"
  },
  
  "constraints": {
    "word_count_change": "none|minimal|allowed",
    "structure_change": "none|minimal|allowed",
    "tone_change": "none|minimal|allowed",
    "focus_only_on": ["string"]
  },
  
  "human_notes": "string",
  
  "action": "REVISE|ESCALATE|APPROVE|REJECT",
  "route_to": "writer|entity_schema|html_converter|human"
}
```

---

## Skill Activation

When invoked, the supervisor:

1. **Checks for configuration**
   - If none: Start onboarding flow
   - If exists: Load and present status

2. **Guides workflow intake**
   - Scope, direction, control level
   - Generate plan

3. **Orchestrates pipeline**
   - Construct prompts with config
   - Invoke skills in sequence (or parallel for batch)
   - Maintain state

4. **Validates at gates**
   - Run Content Gate after Writer
   - Run Publish Gate after processing
   - Generate feedback on failure

5. **Manages revision loop**
   - Construct revision prompts with feedback
   - Re-invoke skills
   - Track attempts
   - Escalate when max reached

6. **Presents review package**
   - Aggregate results
   - Include flags and recommendations
   - Await human decision

7. **Routes human decisions**
   - Approve: Finalize outputs
   - Revise: Re-enter pipeline with human feedback
   - Reject: Archive

---

## Important Notes

### What This Skill Does
- Configures per-client (via multiple paths)
- Orchestrates the full content pipeline
- Validates quality at defined gates
- Communicates structured feedback to skills
- Manages state and revision history
- Presents unified review packages

### What This Skill Does NOT Do
- Duplicate quality logic from writer skills
- Make subjective content judgments
- Modify content directly (returns feedback instead)
- Replace human review for final approval
- Persist state across separate sessions (state is per-session)

### Efficiency Design
- Hard blocks checked first (fail fast)
- Quality signals scored in parallel
- Fact verification runs async (non-blocking)
- Batch articles processed in parallel
- Reconciliation runs once after all articles pass individual gates
