# AEO Agency SOP - Full Reference

**Version:** 1.1.0
**Last Updated:** 2026-01-25
**Status:** Final

This is the complete Standard Operating Procedure for the AEO Content Pipeline Agency.

---

## Table of Contents

1. [Purpose & Scope](#1-purpose--scope)
2. [Platform Stack](#2-platform-stack)
3. [Role Framework](#3-role-framework)
4. [Pipeline Stages](#4-pipeline-stages---detailed)
5. [Skill Orchestration](#5-skill-orchestration)
6. [Standardised Checkpoints](#6-standardised-checkpoints)
7. [Checkpoint Handling Rules](#7-checkpoint-handling-rules)
8. [Content Library](#8-content-library)
9. [Ownership & Claiming Rules](#9-ownership--claiming-rules)
10. [Communication Protocol](#10-communication-protocol)
11. [Notion Setup](#11-notion-setup)
12. [Quick Reference Card](#12-quick-reference-card)
13. [Review & Update Process](#13-review--update-process)

---

## 1. Purpose & Scope

### 1.1 Why This SOP Exists

This SOP establishes clear workflows for our AEO (Answer Engine Optimization) content pipeline agency. As a two-person team in early stages, we need lightweight but effective processes to prevent overlap, maintain visibility, and communicate efficiently.

### 1.2 What This Document Covers

- How jobs flow through our pipeline from lead to completion
- How we claim and hand off work without stepping on each other
- Where and how we communicate about active work
- Which tools we use and how they connect
- How skill orchestration automates quality validation
- How to update this SOP as we learn

### 1.3 Core Principles

| Principle | What It Means |
|-----------|---------------|
| Visibility First | If it's not in Notion, it doesn't exist. Update status before moving on. |
| Claim Before Start | Always claim ownership before beginning work. No assumptions. |
| Communicate Blockers | The moment you're stuck, flag it. Don't wait. |
| Iterate the Process | This SOP is a living document. If something doesn't work, we change it. |
| Automate Quality | Use skill orchestration to catch issues before human review. |

### 1.4 North Star

**Anything that can be automated, is automated.** Each job refines the process, making future jobs more efficient.

---

## 2. Platform Stack

| Tool | Purpose | Why We Chose It |
|------|---------|-----------------|
| Notion | Job tracker, client database, Content Library, SOP storage | Flexible, Claude-integrated, free for 2 users |
| Slack | Quick communication, urgent updates | Real-time chat, integrates with Notion |
| Claude + Skills | AI-guided workflow, automated quality validation | Automates repetitive work, enforces SOP |
| Google Drive | Document storage, client deliverables | Familiar, easy sharing, version history |

### 2.1 How Tools Connect

The Claude skill (`agency-sop`) embedded with this SOP can read from and write to Notion, allowing it to:

- Create new jobs with correct fields when you start a project
- Update job status as you complete stages
- Flag overdue items or status inconsistencies
- Guide you through each stage with the right checklists
- Prevent duplicate work by checking ownership before actions
- Query Content Library for internal linking opportunities
- Orchestrate production skills with automated quality validation

### 2.2 Skills Ecosystem

| Skill | Purpose |
|-------|---------|
| `agency-sop` | Workflow orchestrator, SOP guidance |
| `hst-comparison-writer` | Writes comparison articles |
| `hst-listicle-writer` | Writes listicle articles |
| `hst-aeo-advisor` | Validates content against checkpoints |
| `aeo-entity-master` | Generates schema markup |

---

## 3. Role Framework

### 3.1 Flexible Roles (Current State)

Since we're still discovering our natural division of labour, roles are currently flexible. Either partner can claim any task. Over time, patterns will emerge and we can formalise roles.

### 3.2 Task Categories

| Category | Tasks Included |
|----------|----------------|
| Business Development | Lead generation, initial outreach, discovery calls, proposals |
| Client Management | Client communication, expectation setting, feedback collection |
| Research & Strategy | Keyword research, competitor analysis, content planning |
| Content Production | Writing, editing, schema markup, publishing |
| Operations | Invoicing, tool management, process improvement |

### 3.3 Ownership Model

- Owner is responsible for moving the job through its current stage
- Owner is the point of contact for that job
- Owner must update status before handing off
- Ownership can transfer at any stage (with explicit handoff)

---

## 4. Pipeline Stages - Detailed

### Pipeline Overview

```
LEAD → DISCOVERY → QUOTED → APPROVED → RESEARCH → DRAFTING → REVIEW → REVISIONS → PUBLISHING → COMPLETE
  1        2          3         4          5          6         7          8           9          10
```

### Stage 1: Lead

| Attribute | Detail |
|-----------|--------|
| Description | New inquiry, not yet qualified |
| Entry Criteria | Inbound interest or outreach response |
| Exit Criteria | Discovery call scheduled |

**Actions:**
- Log in Notion within 24 hours
- Include: source, initial needs, contact details
- Schedule discovery call within 3 business days

**Discovery Call Scheduling:**
- **Template**: "Discovery call for [Client] - AEO Assessment"
- **Duration**: 30 minutes
- **Include in invite**: Video link, brief agenda
- **Agenda**: Intro (5 min), Needs Assessment (15 min), Next Steps (10 min)

### Stage 2: Discovery

| Attribute | Detail |
|-----------|--------|
| Description | Understanding needs, assessing fit |
| Entry Criteria | Call scheduled |
| Exit Criteria | Needs documented, decision to quote or decline |

**Actions:**
- Conduct discovery call
- Document client needs and pain points
- Assess fit for AEO services
- Capture client preferences for future reference

### Stage 3: Quoted

| Attribute | Detail |
|-----------|--------|
| Description | Proposal sent, awaiting response |
| Entry Criteria | Proposal delivered |
| Exit Criteria | Client accepts, rejects, or negotiates |

**Actions:**
- Prepare proposal with scope and pricing
- Send proposal with clear next steps
- Set follow-up reminder (1 week if no response)

### Stage 4: Approved

| Attribute | Detail |
|-----------|--------|
| Description | Client signed, ready to begin |
| Entry Criteria | Contract/agreement in place |
| Exit Criteria | Kick-off complete, work assigned |

**Actions:**
- Confirm contract signed
- Collect any required assets/access
- Assign owner for production stages
- Create client record if new client

### Stage 5: Research

| Attribute | Detail |
|-----------|--------|
| Description | Keyword/competitor/entity research |
| Entry Criteria | Assignment confirmed |
| Exit Criteria | Research documented, strategy approved |
| Skill | Manual + AEO Advisor validation |
| Checkpoints | R01-R06 |

**Actions:**
- Complete keyword research with search volume
- Competitor analysis with gap identification
- Entity mapping for schema
- Document anchor questions (≥3)
- Human review: approve strategy before drafting

### Stage 6: Drafting

| Attribute | Detail |
|-----------|--------|
| Description | Content being written |
| Entry Criteria | Strategy approved |
| Exit Criteria | First draft complete, passes validation |
| Skill | `hst-comparison-writer` or `hst-listicle-writer` + AEO Advisor |
| Checkpoints | D01-D08 |

**Actions:**
- Route to appropriate writing skill based on content type
- Skill creates draft following template
- AEO Advisor validates against checkpoints
- Retry loop if validation fails (max 3 attempts)
- Human review: approve content before client review

### Stage 7: Review

| Attribute | Detail |
|-----------|--------|
| Description | Client review of draft |
| Entry Criteria | Draft submitted to client |
| Exit Criteria | Feedback received |

**Actions:**
- Share draft with client (Google Doc or CMS preview)
- Set feedback deadline (typically 3-5 business days)
- Log feedback in job notes

### Stage 8: Revisions

| Attribute | Detail |
|-----------|--------|
| Description | Incorporating client feedback |
| Entry Criteria | Feedback documented |
| Exit Criteria | Revised version approved by client |

**Actions:**
- Categorise feedback (client preference, quality gap, or process miss)
- Apply revisions
- Track revision rounds (typically max 2 in scope)
- If pattern detected (2+ similar issues), flag for SOP update

**Feedback Loop (SOP Learning):**

| Category | Example | Action |
|----------|---------|--------|
| Client Preference | Client prefers shorter intros | Add to client profile in Notion |
| Quality Gap | Missing schema on 3 jobs | Propose new checkpoint |
| Process Miss | Strategy not approved before drafting | Propose stage gate |

### Stage 9: Publishing

| Attribute | Detail |
|-----------|--------|
| Description | Deploying content and schema |
| Entry Criteria | Final approval from client |
| Exit Criteria | Content live and verified |
| Skill | `aeo-entity-master` + AEO Advisor |
| Checkpoints | S01-S06 |

**Publishing Checklist:**
- [ ] Upload to client CMS
- [ ] Run Rich Results Test (schema validation)
- [ ] Verify live URL accessible
- [ ] Test all internal links work
- [ ] Notify client of publication
- [ ] Add entry to Content Library

### Stage 10: Complete

| Attribute | Detail |
|-----------|--------|
| Description | Delivered and closed |
| Entry Criteria | Client acknowledgment |
| Exit Criteria | Invoice sent, Content Library updated |

**Actions:**
- Create Content Library entry
- Send invoice (if applicable)
- Update job status to Complete
- Log any learnings in job notes
- Consider follow-up for additional work

---

## 5. Skill Orchestration

Production stages (Research, Drafting, Schema) use specialized skills with automated quality validation via the AEO Advisor.

### 5.1 Orchestration Flow

```
                    ┌─────────────────────────────────────────────┐
                    │                                             │
                    ▼                                             │
┌──────────────────────────────┐                                  │
│     PRODUCTION SKILL         │                                  │
│  (creates output)            │                                  │
│  • Research (manual)         │                                  │
│  • hst-comparison-writer     │                                  │
│  • hst-listicle-writer       │                                  │
│  • aeo-entity-master         │                                  │
└──────────────┬───────────────┘                                  │
               │                                                  │
               ▼                                                  │
┌──────────────────────────────┐                                  │
│       AEO ADVISOR            │                                  │
│  (validates checkpoints)     │                                  │
│  hst-aeo-advisor             │                                  │
└──────────────┬───────────────┘                                  │
               │                                                  │
        ┌──────┴──────┐                                           │
        │             │                                           │
        ▼             ▼                                           │
      PASS          FAIL                                          │
        │             │                                           │
        │        ┌────┴────┐                                      │
        │        │         │                                      │
        │    Retry < 3?    │                                      │
        │        │         │                                      │
        │       Yes        No                                     │
        │        │         │                                      │
        │        │         ▼                                      │
        │        │   ┌───────────┐                                │
        │        │   │ ESCALATE  │                                │
        │        │   │ to Human  │                                │
        │        │   │ (failure  │                                │
        │        │   │  report)  │                                │
        │        │   └─────┬─────┘                                │
        │        │         │                                      │
        │        └─────────┼──────────────────────────────────────┘
        │                  │         (retry with feedback)
        ▼                  ▼
┌──────────────────────────────┐
│       HUMAN REVIEW           │
│  Partner reviews output      │
│  • Approve → Next Stage      │
│  • Reject → Back to Skill    │
└──────────────────────────────┘
```

### 5.2 Skill Routing

| Content Type | Writing Skill | Schema Skill |
|--------------|---------------|--------------|
| Comparison | `hst-comparison-writer` | `aeo-entity-master` |
| Listicle | `hst-listicle-writer` | `aeo-entity-master` |

### 5.3 AEO Advisor Role

The AEO Advisor (`hst-aeo-advisor`) acts as an automated quality gate:

1. **Trigger**: Runs after each production stage output
2. **Validate**: Checks output against standardised checkpoints
3. **Return**: Pass/fail with specific actions for failures
4. **Loop**: Retries with production skill until pass (max 3)
5. **Escalate**: If max retries exceeded, escalates to human with failure report

### 5.4 Human Review Checkpoints

Human reviews occur at these gates:

| Gate | When | What to Review |
|------|------|----------------|
| Strategy Approval | After Research passes | Keyword target, entities, approach |
| Content Approval | After Drafting passes | Quality, accuracy, AEO elements |
| Schema Approval | After Schema passes | Markup validity, completeness |
| Escalation | Max retries exceeded | Failure report, decide next steps |

---

## 6. Standardised Checkpoints

All checkpoints are binary pass/fail with specific remediation actions.

### 6.1 Research Stage Checkpoints (R01-R06)

| ID | Checkpoint | Pass Criteria |
|----|------------|---------------|
| R01 | Keyword target | Primary keyword specified with search volume |
| R02 | Anchor questions | ≥3 questions content will answer |
| R03 | Competitor analysis | ≥2 competitors with gaps noted |
| R04 | Entity list | Entities to reference defined with schema types |
| R05 | Content type | Format declared (Comparison/Listicle) |
| R06 | Client alignment | Research addresses client objectives |

### 6.2 Drafting Stage Checkpoints (D01-D08)

| ID | Checkpoint | Pass Criteria |
|----|------------|---------------|
| D01 | Keyword placement | Primary keyword in H1 AND first 100 words |
| D02 | Anchor questions | All questions from Research addressed |
| D03 | Entity references | All entities from Research referenced in content |
| D04 | Structure | Follows template for content type |
| D05 | Word count | Within target ±15% |
| D06 | AEO formatting | Contains FAQ, HowTo, or definition callouts |
| D07 | Internal links | Opportunities marked (from Content Library) |
| D08 | Complete | No placeholder text remaining |

### 6.3 Schema Stage Checkpoints (S01-S06)

| ID | Checkpoint | Pass Criteria |
|----|------------|---------------|
| S01 | Article schema | Valid Article/BlogPosting with required fields |
| S02 | Entity markup | All Research entities have schema |
| S03 | FAQ schema | FAQ content has FAQPage schema |
| S04 | HowTo schema | Instructional content has HowTo schema |
| S05 | Syntax valid | No JSON-LD errors |
| S06 | Speakable | Key passages marked for voice search |

### 6.4 Checkpoint Output Format

Advisors return structured feedback:

```
STAGE: Drafting
ATTEMPT: 2 of 3

CHECKPOINTS:
  D01_keyword_placement: PASS
  D02_anchor_questions: FAIL
    required: [Q1, Q2, Q3, Q4]
    found: [Q1, Q3, Q4]
    missing: [Q2]
    action: "Add section addressing Q2"
  D03_entity_references: PASS
  D04_structure: PASS
  D05_word_count: PASS (2,340 words, target 2,000-2,500)
  D06_aeo_formatting: PASS
  D07_internal_links: N/A
    reason: "First article for client - no Content Library entries"
  D08_complete: PASS

RESULT: FAIL (1 checkpoint failed)
ACTION: Retry with fixes for D02_anchor_questions
```

---

## 7. Checkpoint Handling Rules

### 7.1 N/A Checkpoint Handling

Some checkpoints don't apply to all content types.

**Rules:**
- Advisor marks checkpoint as `N/A` with explicit reason
- N/A checkpoints don't count toward pass/fail
- Must have specific reason (not just "doesn't apply")

**Content Type Defaults:**

| Checkpoint | Comparison | Listicle | When N/A Applies |
|------------|------------|----------|------------------|
| S03 FAQ schema | Required | Optional | No FAQ section in content |
| S04 HowTo schema | Optional | Optional | No step-by-step instructions |
| D06 AEO formatting | Required | Required | Never N/A - always needs some AEO element |
| D07 Internal links | Conditional | Conditional | No Content Library entries for client |

**N/A Output Format:**
```
S04_howto_schema: N/A
  reason: "Content is comparison article, no step-by-step instructions"
  override_available: false
```

### 7.2 Conditional Checkpoints

Some checkpoints only apply when certain conditions are met.

| Checkpoint | Condition | When It Applies |
|------------|-----------|-----------------|
| S03 FAQ schema | FAQ section exists | Content contains FAQ heading or Q&A format |
| S04 HowTo schema | Instructions exist | Content contains numbered steps or "how to" |
| D07 Internal links | Content Library has entries | Client has published content to link to |

**Evaluation Flow:**
1. Advisor checks if condition trigger is present
2. If trigger present → evaluate checkpoint normally
3. If trigger absent → mark as N/A with reason
4. Proceed with remaining checkpoints

### 7.3 Checkpoint Override Protocol

In rare cases, a checkpoint may need to be bypassed. This requires explicit human approval.

**When Override is Allowed:**
- Client explicitly requests deviation from standard
- Technical limitation prevents compliance
- Time constraint with client acknowledgment

**Override Process:**
1. Advisor flags checkpoint as `OVERRIDE_REQUESTED`
2. Human reviews with context
3. If approved: log override with reason, approver, and date
4. If denied: continue normal retry loop

**Override Request Format:**
```
CHECKPOINT OVERRIDE REQUEST

Checkpoint: D05_word_count
Reason: Client requested 800-word article; target was 1500
Requested by: [Partner name]
Client acknowledgment: Yes

HUMAN DECISION REQUIRED:
[ ] APPROVE - Log override and proceed
[ ] DENY - Revise to meet checkpoint
```

**Override Logging (in job notes):**
```
OVERRIDE LOG:
- Checkpoint: D05_word_count
- Reason: Client-requested shorter format
- Approved by: [Name]
- Date: [Date]
- Client informed: Yes
```

### 7.4 Adding New Checkpoints

As the SOP evolves, new checkpoints may be needed.

**When to Add:**
- Same revision feedback appears on 2+ jobs (pattern detected)
- New content type requires different validation
- Client feedback reveals consistent quality gap

**Process:**
1. **Propose**: Document with ID, name, pass criteria, applicable content types
2. **Review**: Discuss in weekly review
3. **Test**: Apply to next 2 jobs manually before automating
4. **Implement**: Add to both SKILL.md and full-sop.md
5. **Log**: Record in CHANGELOG with rationale

**Naming Convention:**
- Research: R01-R99
- Drafting: D01-D99
- Schema: S01-S99
- Publishing: P01-P99 (if needed)

**Example Proposal:**
```
NEW CHECKPOINT PROPOSAL

ID: D09
Name: CTA placement
Pass Criteria: Call-to-action present in final section
Applies to: All content types
Rationale: Last 3 jobs required revision to add CTA
Pattern jobs: [Job A], [Job B], [Job C]
```

---

## 8. Content Library

The Content Library tracks all published content per client in Notion.

### 8.1 Purpose

- Enable internal linking by referencing existing client content
- Track production history per client
- Link completed jobs to their published outputs
- Support D07 checkpoint validation

### 8.2 Database Fields

| Field | Type | Description |
|-------|------|-------------|
| Title | Title | Article headline |
| Client | Relation | Links to Clients database |
| URL | URL | Live published URL |
| Primary Keyword | Text | Main target keyword |
| Entities | Multi-select | Key entities covered |
| Content Type | Select | Comparison, Listicle, etc. |
| Published Date | Date | When content went live |
| Related Job | Relation | Links to Job Tracker |

### 8.3 Workflow Integration

1. Job reaches Complete status
2. Prompt to add entry to Content Library
3. Fill in all fields including live URL
4. Link back to originating job
5. Future jobs for same client query library for D07 checkpoint

### 8.4 Using Content Library for Internal Linking

When drafting new content:
1. Query Content Library for client's existing content
2. Identify relevant articles for internal linking
3. Mark link opportunities in draft
4. D07 checkpoint validates links were considered

---

## 9. Ownership & Claiming Rules

### 9.1 The Claiming Process

1. Check Notion to see if someone else is already working on it
2. If unclaimed: assign yourself as Owner in Notion
3. If already claimed: contact the current owner before taking action
4. Update status to reflect you're actively working

### 9.2 Anti-Overlap Rules

| Rule | Why It Matters |
|------|----------------|
| One owner per job | Prevents confusion about who's responsible |
| Claim before starting | Avoids duplicate work |
| Update before leaving | Keeps status accurate for partner |
| Explicit handoffs only | No assumptions about who picks up next |

### 9.3 Handoff Protocol

1. Update the job's notes in Notion with current status and any blockers
2. Change the Owner field to the new owner
3. Notify the new owner via Slack with a brief context summary
4. New owner acknowledges in Slack before status changes

**Slack Template:**
```
#active-jobs: Handing off [Job Name] to [Partner]
- Current stage: [Stage]
- What's done: [Summary]
- What's next: [Next steps]
- Blockers: [Any blockers]
```

### 9.4 What Happens If Both Start Working

If you discover overlap has occurred:
1. Stop immediately and compare what each person has done
2. Decide which version to use (or merge if practical)
3. Log the overlap in the job notes as a process learning
4. Discuss in weekly review how to prevent recurrence

---

## 10. Communication Protocol

### 10.1 Channel Structure (Slack)

| Channel | Use For |
|---------|---------|
| #general | Non-work chat, general updates |
| #active-jobs | Updates on current work, handoffs, quick questions |
| #blockers | Flagging issues that need the other person's input |
| DMs | Sensitive client matters, personal coordination |

### 10.2 When to Update

Post in #active-jobs when:
- You claim a new job
- You complete a stage and move to the next
- You hand off to your partner
- You're stepping away mid-task (provide context)
- A client responds with important information

### 10.3 Flagging Blockers

Post in #blockers with:
- Job name/link
- What you're blocked on
- What you need from your partner
- Urgency level (can wait vs. need today)

### 10.4 Response Expectations

| Message Type | Expected Response Time |
|--------------|------------------------|
| #blockers urgent | Within 2 hours during work hours |
| #blockers can wait | Within 24 hours |
| #active-jobs | Acknowledge within same day (react or reply) |

### 10.5 Slack Templates

**Claiming a job:**
```
#active-jobs: Picking up [Job Name] for [Client]. Moving to [Stage].
```

**Stage completion:**
```
#active-jobs: [Job Name] moved to [Stage]. [Brief context if needed]
```

**Blocker:**
```
#blockers: [Job Name]
Blocked on: [Issue]
Need: [What you need]
Urgency: [Can wait / Need today]
```

---

## 11. Notion Setup

### 11.1 Databases Required

1. **Clients** - Client information and preferences
2. **Job Tracker** - Main pipeline with all stages
3. **Content Library** - Published content for internal linking

### 11.2 Clients Database Fields

| Field | Type | Required |
|-------|------|----------|
| Company Name | Title | Yes |
| Primary Contact | Text | Yes |
| Email | Email | Yes |
| Industry | Select | No |
| Size | Select | No |
| Location | Text | No |
| Preferences | Text | No |
| Notes | Text | No |

### 11.3 Job Tracker Database Fields

| Field | Type | Required |
|-------|------|----------|
| Job Name | Title | Yes |
| Client | Relation → Clients | Yes |
| Status | Select | Yes |
| Owner | Person | Yes |
| Content Type | Select | Yes |
| Priority | Select | No |
| Due Date | Date | No |
| Notes | Text | No |
| Created | Created time | Auto |
| Last Updated | Last edited time | Auto |

**Status Options:**
Lead, Discovery, Quoted, Approved, Research, Drafting, Review, Revisions, Publishing, Complete

**Content Type Options:**
Comparison, Listicle

### 11.4 Content Library Database Fields

| Field | Type | Required |
|-------|------|----------|
| Title | Title | Yes |
| Client | Relation → Clients | Yes |
| URL | URL | Yes |
| Primary Keyword | Text | Yes |
| Entities | Multi-select | No |
| Content Type | Select | Yes |
| Published Date | Date | Yes |
| Related Job | Relation → Job Tracker | Yes |

### 11.5 Recommended Views

**Job Tracker Views:**
- **Pipeline Board**: Kanban by Status
- **My Jobs**: Filtered by Owner = Me
- **Overdue**: Filtered by Due Date < Today
- **By Client**: Grouped by Client

**Content Library Views:**
- **By Client**: Grouped by Client
- **Recent**: Sorted by Published Date descending
- **By Type**: Grouped by Content Type

---

## 12. Quick Reference Card

### Pipeline (Simplified)

```
LEAD → DISCOVERY → QUOTED → APPROVED → RESEARCH → DRAFTING → REVIEW → REVISIONS → PUBLISHING → COMPLETE
  1        2          3         4          5          6         7          8           9          10
                                         ────────── Production (Skill + Advisor) ──────────
```

### Before Starting Any Work

1. Check Notion: Is this job claimed?
2. If not: Assign yourself as Owner
3. Update Status to reflect current stage
4. Begin work

### Before Stopping Work

1. Update Notes with current progress
2. Update Status if you completed a stage
3. Post in #active-jobs if handing off or pausing

### If You're Stuck

1. Post in #blockers with: Job link, what you need, urgency
2. Don't wait - flag early

### Production Stage Quick Reference

| Stage | Skill | Checkpoints | Human Gate |
|-------|-------|-------------|------------|
| Research | Manual | R01-R06 | Strategy approval |
| Drafting | Writer skill | D01-D08 | Content approval |
| Schema | Entity master | S01-S06 | Schema approval |

### Checkpoint States

- **PASS** - Criteria met, proceed
- **FAIL** - Needs fix, retry (max 3)
- **N/A** - Doesn't apply (with reason)

### Weekly Rhythm

- **Monday**: Review all active jobs, set priorities for the week
- **Friday**: Check for stale jobs (nothing updated in 3+ days)
- **Monthly**: Review this SOP - what's working, what isn't?

---

## 13. Review & Update Process

### 13.1 Scheduled Reviews

| Frequency | Focus |
|-----------|-------|
| Weekly (Friday) | Process friction, blockers that recurred, workload balance |
| Monthly | SOP accuracy, stage definitions, tool effectiveness |
| Quarterly | Role evolution, major process changes, scaling needs |

### 13.2 How to Propose Changes

1. Identify the issue or improvement opportunity
2. Draft the proposed change
3. Discuss with partner in weekly review
4. If agreed, update this document AND the Claude skill
5. Note the change in the CHANGELOG

### 13.3 Feedback Loop Integration

When revision patterns are detected:
1. Log the pattern (2+ occurrences of same feedback type)
2. Propose SOP update (new checkpoint, checklist item, or stage gate)
3. Test manually on next 2 jobs
4. Implement if successful
5. Update both documentation and skill

### 13.4 Version Control

All changes are logged in `/sop/CHANGELOG.md` with:
- Version number (semantic versioning)
- Date
- What changed (Added, Changed, Removed, Fixed)
- Rationale
- Contributor

---

## Appendix A: Visual References

- **Pipeline Overview**: `/assets/pipeline-overview-v1.1.svg`
- **Skill Orchestration Flow**: `/assets/skill-orchestration-v1.1.svg`

## Appendix B: Related Documents

- **Claude Skill**: `/skills/aeo-agency-workflow/SKILL.md`
- **Notion Setup Guide**: `/notion/setup-guide.md`
- **Templates**: `/templates/`
  - `client-brief.md`
  - `content-strategy.md`
  - `handoff-note.md`
- **Changelog**: `/sop/CHANGELOG.md`

---

*AEO Agency SOP v1.1.0 - Last updated 2026-01-25*
