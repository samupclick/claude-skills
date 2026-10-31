---
name: agency-sop
description: |
  AEO Content Pipeline Agency SOP and workflow manager. Use when starting new client projects,
  managing job status, preventing workflow overlap, or needing guidance through pipeline stages.
  Triggers on: "new project", "new client", "update job status", "what's the next step",
  "claim this job", "hand off", "check my pipeline", "workflow help", "SOP", or any project
  management task for the AEO agency. Integrates with Notion for job tracking.
---

# Agency SOP - AEO Content Pipeline

Guide projects through the content pipeline while preventing overlap and maintaining visibility.

## Quick Start

When user starts a new project:
1. Confirm client name and project scope
2. Create job in Notion with status "Lead" or "Discovery"
3. Assign ownership to claiming partner
4. Walk through stage-specific checklist

When user asks "what's next":
1. Check current job status in Notion
2. Provide exit criteria for current stage
3. Guide through next steps

## Pipeline Stages

| Stage | Entry | Exit |
|-------|-------|------|
| Lead | Inbound interest | Discovery call scheduled |
| Discovery | Call scheduled | Needs documented, quote decision made |
| Quoted | Proposal sent | Client response received |
| Approved | Contract signed | Kick-off complete, work assigned |
| Research | Assignment confirmed | Strategy documented and approved |
| Drafting | Strategy approved | First draft complete |
| Review | Draft submitted | Feedback received |
| Revisions | Feedback documented | Revised version approved |
| Publishing | Final approval | Content live and verified |
| Complete | Client acknowledgment | Invoice sent (if applicable) |

## Anti-Overlap Rules

Before taking any action on a job:
1. Check Notion for current owner
2. If unclaimed: assign ownership first
3. If claimed by partner: confirm handoff before proceeding
4. Update status BEFORE moving to next task

## Claiming Protocol

```
1. User: "I want to work on [job]"
2. Claude: Check Notion for current owner
3. If unclaimed → Assign user as owner, confirm
4. If owned by partner → "This job is owned by [Partner]. Should I request a handoff?"
5. Update status to reflect active work
```

## Handoff Protocol

When transferring ownership:
1. Update job notes with current progress and any blockers
2. Change Owner field to new owner
3. Suggest Slack notification: "Handing off [Job] to [Partner] - [brief context]"
4. New owner must acknowledge before status changes

## Stage Checklists

### Lead → Discovery
- [ ] Log in Notion within 24 hours
- [ ] Include: source, initial needs, contact details
- [ ] Schedule discovery call within 3 business days
- [ ] Use scheduling template: "Discovery call for [Client] - AEO Assessment"
- [ ] Include in invite: 30-min duration, video link, brief agenda

### Discovery → Quoted
- [ ] Document client needs
- [ ] Assess fit for AEO services
- [ ] Prepare proposal with scope and pricing

### Research → Drafting
- [ ] Complete keyword research
- [ ] Competitor analysis documented
- [ ] Entity mapping complete
- [ ] Strategy approved (or noted as skipped)

### Review → Complete
- [ ] Track revision rounds (max 2 in scope)
- [ ] Publish content with schema markup
- [ ] Verify live deployment
- [ ] Send invoice if applicable

### Publishing Checklist
- [ ] Upload to client CMS
- [ ] Run Rich Results Test (schema validation)
- [ ] Verify live URL accessible
- [ ] Test all internal links work
- [ ] Notify client of publication
- [ ] Add entry to Content Library

## Revision Feedback Loop (SOP Learning)

When a job enters Revisions, trigger the feedback loop to improve future jobs:

### During Revisions
1. Categorise feedback: Client preference, Quality gap, or Process miss?
2. Log the feedback type in job notes
3. If this is the 2nd+ occurrence of the same issue, flag for SOP update

### Feedback Categories

| Category | Action |
|----------|--------|
| Client Preference | Add to client profile in Notion (not SOP) |
| Quality Gap | Propose new checklist item for relevant stage |
| Process Miss | Propose stage gate or approval requirement |

### When Pattern Detected (2+ occurrences)
1. Draft SOP update proposal
2. Add to weekly review agenda
3. If approved: update SOP doc AND this skill
4. Goal: First drafts should increasingly pass Review without revisions

### Prompts to Use
- "Log revision feedback" → Categorise and record
- "Check for patterns" → Review recent revisions for recurring issues
- "Propose SOP update" → Draft improvement based on feedback

## Skill Orchestration

Production stages use specialized skills with automated quality validation.

### Flow Model

```
Production Skill → AEO Advisor (validate) → Pass?
                                              │
                        ┌─────────────────────┴─────────────────────┐
                        ▼                                           ▼
                      PASS                                        FAIL
                        │                                           │
                        ▼                                    Retry < 3?
                  Human Review                                 │     │
                                                             Yes    No
                                                              │     │
                                            ┌─────────────────┘     ▼
                                            │                  Human Review
                                            ▼                  (failure report)
                              Skill revises with checkpoint feedback
                                            │
                                            └──→ Back to AEO Advisor
```

### Skill Routing

| Content Type | Writing Skill | Schema Skill |
|--------------|---------------|--------------|
| Comparison | `hst-comparison-writer` | `aeo-entity-master` |
| Listicle | `hst-listicle-writer` | `aeo-entity-master` |

### AEO Advisor Role

Runs after each production stage, before human review:
- Validates output against standardised checkpoints
- Returns pass/fail with specific actions for failures
- Loops with production skill until pass (max 3 retries)
- If max retries exceeded: escalate to human with failure report

## Standardised Checkpoints

### Research Stage (R01-R06)

| ID | Checkpoint | Pass Criteria |
|----|------------|---------------|
| R01 | Keyword target | Primary keyword specified with search volume |
| R02 | Anchor questions | ≥3 anchor questions content will answer |
| R03 | Competitor analysis | ≥2 competitors with content gaps noted |
| R04 | Entity list | Entities to reference defined |
| R05 | Content type | Format declared (Comparison/Listicle/etc) |
| R06 | Client alignment | Research addresses client objectives |

### Drafting Stage (D01-D08)

| ID | Checkpoint | Pass Criteria |
|----|------------|---------------|
| D01 | Keyword placement | Primary keyword in H1 AND first 100 words |
| D02 | Anchor questions | All questions from Research addressed |
| D03 | Entity references | All entities from Research referenced |
| D04 | Structure | Follows template for content type |
| D05 | Word count | Within target ±15% |
| D06 | AEO formatting | Contains FAQ, HowTo, or definition callouts |
| D07 | Internal links | Opportunities marked (from Content Library or placeholder) |
| D08 | Complete | No [TBD] or placeholder text |

### Schema Stage (S01-S06)

| ID | Checkpoint | Pass Criteria |
|----|------------|---------------|
| S01 | Article schema | Valid Article/BlogPosting with required fields |
| S02 | Entity markup | All Research entities have schema |
| S03 | FAQ schema | FAQ content has FAQPage schema |
| S04 | HowTo schema | Step-by-step content has HowTo schema |
| S05 | Syntax valid | No JSON-LD errors |
| S06 | Speakable | Key passages marked for voice search |

### Checkpoint Output Format

```
STAGE: Drafting
ATTEMPT: 1 of 3

CHECKPOINTS:
  D01_keyword_placement: PASS
  D02_anchor_questions: FAIL
    required: [list from Research]
    found: [what's in draft]
    missing: [gaps]
    action: "Add sections addressing: [missing items]"
  D03_entity_references: PASS
  D06_aeo_formatting: N/A (no FAQ or HowTo content in scope)
  ...

RESULT: FAIL
ACTION: Retry with fixes for D02
```

## N/A Checkpoint Handling

Some checkpoints don't apply to all content types. Handle as follows:

### When a Checkpoint is N/A
- Advisor marks checkpoint as `N/A` with reason
- N/A checkpoints don't count toward pass/fail
- Must have explicit reason (not just "doesn't apply")

### Content Type Defaults

| Checkpoint | Comparison | Listicle | When N/A Applies |
|------------|------------|----------|------------------|
| S03 FAQ schema | Required | Optional | No FAQ section in content |
| S04 HowTo schema | Optional | Optional | No step-by-step instructions |
| D06 AEO formatting | Required | Required | Never N/A - always needs some AEO element |

### N/A Output Format
```
S04_howto_schema: N/A
  reason: "Content is comparison article, no step-by-step instructions"
  override_available: false
```

## Checkpoint Override Protocol

In rare cases, a checkpoint may need to be bypassed. This requires explicit human approval.

### When Override is Allowed
- Client explicitly requests deviation from standard
- Technical limitation prevents compliance
- Time constraint with client acknowledgment

### Override Process
1. Advisor flags checkpoint as `OVERRIDE_REQUESTED`
2. Human reviews with context
3. If approved: log override with reason, approver, and date
4. If denied: continue normal retry loop

### Override Output Format
```
CHECKPOINT OVERRIDE REQUEST

Checkpoint: D05_word_count
Reason: Client requested 800-word article; target was 1500
Requested by: [Partner name]
Client acknowledgment: Yes/No

HUMAN DECISION REQUIRED:
[ ] APPROVE - Log override and proceed
[ ] DENY - Revise to meet checkpoint
```

### Override Logging
All overrides are logged in job notes:
```
OVERRIDE LOG:
- Checkpoint: D05_word_count
- Reason: Client-requested shorter format
- Approved by: [Name]
- Date: [Date]
- Client informed: Yes
```

## Conditional Checkpoints

Some checkpoints only apply when certain conditions are met.

### Condition Triggers

| Checkpoint | Condition | When It Applies |
|------------|-----------|-----------------|
| S03 FAQ schema | FAQ section exists | Content contains FAQ heading or Q&A format |
| S04 HowTo schema | Instructions exist | Content contains numbered steps or "how to" |
| D07 Internal links | Content Library has entries | Client has published content to link to |

### Evaluation Flow
1. Advisor checks if condition trigger is present
2. If trigger present: evaluate checkpoint normally
3. If trigger absent: mark as N/A with reason
4. Proceed with remaining checkpoints

## Adding New Checkpoints

As the SOP evolves, new checkpoints may be needed. Follow this process:

### When to Add a Checkpoint
- Same revision feedback appears on 2+ jobs (pattern detected)
- New content type requires different validation
- Client feedback reveals consistent quality gap

### Process for Adding
1. **Propose**: Document the new checkpoint with:
   - ID (following naming convention: R07, D09, S07, etc.)
   - Checkpoint name
   - Pass criteria
   - Which content types it applies to
2. **Review**: Discuss in weekly review
3. **Test**: Apply to next 2 jobs manually before automating
4. **Implement**: Add to both SKILL.md and full-sop.md
5. **Log**: Record in CHANGELOG with rationale

### Checkpoint Naming Convention
- Research: R01-R99
- Drafting: D01-D99
- Schema: S01-S99
- Publishing: P01-P99 (if needed)

### Example Proposal
```
NEW CHECKPOINT PROPOSAL

ID: D09
Name: CTA placement
Pass Criteria: Call-to-action present in final section
Applies to: All content types
Rationale: Last 3 jobs required revision to add CTA
Pattern jobs: [Job A], [Job B], [Job C]
```

## Notion Integration

When Notion MCP is connected, Claude can:
- Create new jobs with correct fields
- Update job status and ownership
- Check for stale jobs (no update in 3+ days)
- Query current pipeline state
- Query Content Library for internal linking

### Job Tracker Fields
- Job Name (title)
- Client (relation → Clients)
- Status (select: Lead, Discovery, Quoted, Approved, Research, Drafting, Review, Revisions, Publishing, Complete)
- Owner (person)
- Priority (select: High, Medium, Low)
- Due Date (date)
- Notes (text)
- Content Type (select: Comparison, Listicle)

### Content Library Fields
Single database with per-client views:
- Title (title)
- Client (relation → Clients)
- URL (url)
- Primary Keyword (text)
- Entities (multi-select)
- Content Type (select)
- Published Date (date)
- Related Job (relation → Job Tracker)

When a job reaches Complete:
1. Prompt to add entry to Content Library
2. Link back to originating job
3. Future jobs for same client can reference for internal linking

## Communication Guidance

Suggest Slack posts for:
- Claiming a job: "#active-jobs: Picking up [Job] for [Client]"
- Stage completion: "#active-jobs: [Job] moved to [Stage]"
- Handoffs: "#active-jobs: Handing [Job] to [Partner] - [context]"
- Blockers: "#blockers: [Job] - [what's needed] - [urgency]"

## Weekly Rhythm Reminders

- **Monday**: Review all active jobs, set week's priorities
- **Friday**: Check for stale jobs, flag anything stuck
- **Monthly**: Review SOP effectiveness, propose updates

## Reference Documents

For complete SOP details including all policies and detailed guidance:
- See `references/full-sop.md` for the complete searchable SOP
- See `AEO_Agency_SOP_v1.docx` for the printable Word document version
