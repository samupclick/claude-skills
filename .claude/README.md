# Project Claude Code configuration

## Matt Pocock's skills (plugin, project scope)

`settings.json` enables the official `mattpocock-skills@claude-plugins-official` plugin for every session on this repo (CLI, desktop, cloud). Commands are namespaced by the plugin name:

- `/mattpocock-skills:grill-me`, `/mattpocock-skills:grill-with-docs` — design interrogation
- `/mattpocock-skills:to-spec` (was `to-prd`), `/mattpocock-skills:to-tickets`, `/mattpocock-skills:implement` — spec → tickets → build
- `/mattpocock-skills:wayfinder`, `/mattpocock-skills:tdd`, `/mattpocock-skills:code-review`, `/mattpocock-skills:triage`, and the rest

Model-invoked ones (tdd, diagnosing-bugs, research, …) also trigger automatically when the task fits.

First use in this repo: run `/mattpocock-skills:setup-matt-pocock-skills` once. Cloud sessions have no `gh` CLI, so choose the **local markdown** tracker (`.scratch/`) unless you run locally.

There is no `orchestrate` or `crucible` skill upstream. The build flow is `to-tickets` then `implement` per ticket.

## Our skills (`skills/`, symlinks to the top-level folders)

- `/marketing-engineer` — orchestrator for the Marketing Engineer Pipeline
- `/to-prd` — our PRD generator

The top-level folders remain the upload format for claude.ai skills.
