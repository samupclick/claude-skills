# Project skills

Everything under `.claude/skills/` is exposed as a `/<name>` slash command in every Claude Code session on this repo (CLI, desktop, and cloud), per https://code.claude.com/docs/en/skills.

## Vendored: Matt Pocock's skills (v1.2.3, MIT)

The 25 skills the official `mattpocock-skills` plugin ships, copied from https://github.com/mattpocock/skills so they work in cloud sessions without a per-user plugin install. Licence: `skills/LICENSE-mattpocock-skills`.

Do **not** also install the plugin (`/plugin install mattpocock-skills`) or every skill appears twice. To update, re-copy from the upstream repo's `.claude-plugin/plugin.json` list, or run `npx skills@latest add mattpocock/skills` and choose these.

First use in this repo: run `/setup-matt-pocock-skills` once. It configures the issue tracker the planning skills write to. Cloud sessions have no `gh` CLI, so choose **local markdown** (`.scratch/`) unless you run locally.

Note: there is no `orchestrate`, `crucible`, or `to-prd` skill upstream. `to-prd` was renamed `to-spec`. The build flow is `/to-tickets` (spec → tracer-bullet tickets) then `/implement` (per ticket, uses `/tdd` and `/code-review`), with `/wayfinder` for work too big for one session and `/grill-with-docs` for design.

## Ours (symlinks to the top-level folders)

- `marketing-engineer` → orchestrator for the Marketing Engineer Pipeline (`marketing-engineer/SKILL.md`)
- `to-prd` → our PRD generator, kept under the name we use; upstream's equivalent is `/to-spec`

The top-level folders remain the upload format for claude.ai skills.
