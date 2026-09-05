# Agency SOP Skill

**Version:** 1.1.0
**Last Updated:** 2026-01-25

A Claude skill for managing your AEO (Answer Engine Optimization) content pipeline agency. This skill acts as your "third partner" — guiding you through projects, orchestrating production skills, validating quality, and keeping your Notion workspace in sync.

---

## Quick Start

1. Copy the `agency-sop` folder to your Claude skills directory
2. Connect Notion to Claude (for job tracking and Content Library)
3. Say "new project" or "check my pipeline" to get started

---

## What's Included

```
agency-sop-skill/
├── README.md                    # This file
├── SKILL.md                     # The main skill file (copy to your skills folder)
├── references/
│   └── full-sop.md              # Complete SOP documentation (800+ lines)
├── assets/
│   ├── pipeline-overview.svg    # Visual workflow diagram
│   └── skill-orchestration.svg  # Skill + Advisor flow diagram
├── templates/
│   ├── client-brief.md          # New client intake template
│   ├── content-strategy.md      # Research output format
│   └── handoff-note.md          # Job handoff template
├── notion/
│   └── setup-guide.md           # Step-by-step Notion configuration
└── CHANGELOG.md                 # Version history
```

---

## Features

### Pipeline Management
- 10-stage pipeline: Lead → Discovery → Quoted → Approved → Research → Drafting → Review → Revisions → Publishing → Complete
- Ownership tracking to prevent workflow overlap
- Stage checklists and exit criteria

### Skill Orchestration
- Automated quality validation via AEO Advisor
- Retry loop (max 3 attempts) before human escalation
- Human review gates at key checkpoints

### Standardised Checkpoints
- **Research (R01-R06):** Keyword target, anchor questions, competitor analysis, entity list, content type, client alignment
- **Drafting (D01-D08):** Keyword placement, anchor questions, entity references, structure, word count, AEO formatting, internal links, completeness
- **Schema (S01-S06):** Article schema, entity markup, FAQ schema, HowTo schema, syntax validation, speakable markup

### Checkpoint Handling
- **N/A handling:** For checkpoints that don't apply to certain content types
- **Override protocol:** For client-requested deviations (with logging)
- **Conditional checkpoints:** Only evaluated when triggers are present
- **Adding new checkpoints:** Process for evolving the SOP based on patterns

### Content Library Integration
- Tracks all published content per client
- Enables internal linking via D07 checkpoint
- Links completed jobs to their outputs

---

## Trigger Phrases

The skill activates on:
- "new project" / "new client"
- "update job status"
- "what's the next step"
- "claim this job" / "hand off"
- "check my pipeline"
- "workflow help" / "SOP"

---

## Skills Ecosystem

This skill works with your existing AEO skills:

| Skill | Purpose |
|-------|---------|
| `agency-sop` | Workflow orchestrator (this skill) |
| `hst-comparison-writer` | Writes comparison articles |
| `hst-listicle-writer` | Writes listicle articles |
| `hst-aeo-advisor` | Validates content against checkpoints |
| `aeo-entity-master` | Generates schema markup |

---

## Notion Setup

The skill integrates with three Notion databases:

1. **Clients** — Client information and preferences
2. **Job Tracker** — Main pipeline with all stages
3. **Content Library** — Published content for internal linking

See `notion/setup-guide.md` for detailed setup instructions.

---

## Installation

### Option 1: Full Installation
Copy the entire `agency-sop` folder to your Claude skills directory:
```
~/.claude/skills/agency-sop/
```

### Option 2: Minimal Installation
Copy just `SKILL.md` to your skills folder. The skill will work without the reference files, but you'll lose access to the full documentation.

---

## Usage Examples

**Starting a new project:**
```
User: "New project for Acme Corp"
Claude: [Creates job in Notion, walks through Lead stage checklist]
```

**Checking pipeline status:**
```
User: "What's the status of my active jobs?"
Claude: [Queries Notion, shows pipeline overview]
```

**Moving through stages:**
```
User: "Research is done for the Acme comparison article"
Claude: [Validates R01-R06 checkpoints, moves to Drafting if pass]
```

---

## Version History

See `CHANGELOG.md` for full version history.

### v1.1.0 (Current)
- Added skill orchestration with AEO Advisor validation
- Added standardised checkpoints (R01-R06, D01-D08, S01-S06)
- Added N/A handling, override protocol, conditional checkpoints
- Added Content Library integration
- Added visual workflow diagrams

### v1.0.0
- Initial release with 10-stage pipeline
- Ownership and claiming rules
- Communication protocol
- Notion integration

---

## Support

This skill was designed for a two-person AEO content agency. If you need to adapt it for your team size or workflow, the `references/full-sop.md` document contains all the details you'll need.

**North Star:** Anything that can be automated, is automated.

---

*Built with Claude*
