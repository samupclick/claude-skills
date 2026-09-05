# SOP Changelog

All notable changes to the AEO Agency SOP will be documented in this file.

Format: Each entry includes the date, version, author, and description of changes.

---

## [1.1.0] - 2026-01-25

### Added
- Skill Orchestration flow (Section 4.5) with production skill → AEO Advisor → human review model
- Standardised Checkpoints (Section 4.6): R01-R06, D01-D08, S01-S06
- Content Library integration (Section 4.12) for internal linking
- N/A Checkpoint Handling (Section 4.8) with content type defaults
- Checkpoint Override Protocol (Section 4.9) for client-requested deviations
- Conditional Checkpoints (Section 4.10) with condition triggers
- New Checkpoint Process (Section 4.11) for adding checkpoints via feedback loop
- Publishing Checklist with 6-item verification list
- Discovery scheduling template (Lead stage enhancement)
- Pipeline Overview infographic (pipeline-overview.svg)
- Skill Orchestration infographic (skill-orchestration.svg)

### Changed
- Updated pipeline visual to clarify Publishing stage and Schema flow
- Renumbered Content Library section from 4.7 to 4.12

### From Simulation Testing
- Gap 1: Added detailed Publishing checklist
- Gap 2: Added discovery call scheduling template
- Gap 3: Defined N/A checkpoint handling rules
- Gap 4: Created override protocol with logging
- Gap 5: Established conditional checkpoint triggers
- Gap 6: Documented process for adding new checkpoints

### Contributors
- Sam

---

## [1.0.0] - 2026-01-25

### Added
- Initial SOP document with 9 sections
- Pipeline stages: Lead → Discovery → Quoted → Approved → Research → Drafting → Review → Revisions → Publishing → Complete
- Ownership and claiming rules to prevent overlap
- Communication protocol with Slack channel structure
- Notion setup guide
- Quick reference card
- Revision Feedback Loop (Section 4.4) for continuous process improvement

### Contributors
- Sam

---

## How to Log Changes

When updating the SOP based on feedback loop learnings:

1. Add a new entry at the top (newest first)
2. Use semantic versioning:
   - **Major (X.0.0)**: Significant process changes, new stages, role restructuring
   - **Minor (0.X.0)**: New checklist items, template additions, clarifications
   - **Patch (0.0.X)**: Typo fixes, minor wording changes
3. Categorise changes as Added, Changed, Removed, or Fixed
4. Note the source (e.g., "From feedback loop: quality gap pattern")

### Example Entry

```markdown
## [1.1.0] - 2026-02-15

### Added
- Schema markup checklist item to Drafting stage (from feedback loop: quality gap on 3 jobs)

### Changed
- Clarified handoff protocol to require Slack acknowledgment before status change

### Contributors
- Partner Name
```
