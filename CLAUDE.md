# claude-skills

Skills and design documents for upClickLabs. The active build is the Marketing Engineer Pipeline under `marketing-engineer/` (source of truth order: `warehouse/schema.sql` + `warehouse/0002_roles.sql` → `PRD.md` → `ARCHITECTURE.md` → `CRUCIBLE.md` → `DECISIONS.md`; `PLAN.md` is the schedule only). Phase 0 is built in dev mode per `marketing-engineer/references/dev-mode.md`.

## Agent skills

### Issue tracker

Local markdown files under `.scratch/<feature>/issues/NN-<slug>.md`, committed to the working branch. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root, created lazily. See `docs/agents/domain.md`.
