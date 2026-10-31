# Project Claude Code configuration

- `settings.json` enables the `mattpocock-skills@claude-plugins-official` plugin for every session on this repo and carries a SessionStart hook that installs it when a fresh remote container lacks it.
- Skill commands are namespaced: `/mattpocock-skills:to-tickets`, `/mattpocock-skills:implement`, `/mattpocock-skills:tdd`, `/mattpocock-skills:code-review`, and the rest.
- Tracker, triage labels, and domain-doc conventions for those skills live in `docs/agents/`.
- `marketing-engineer/` and `to-prd/` are this repo's own skills. `claude-ai-skills/` holds skills uploaded to claude.ai; Claude Code does not load them.
