# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`. Chosen because build sessions run remotely without the `gh` CLI; the files are committed to the working branch so a fresh session can read them.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md` (for `marketing-engineer-phase0` it is a pointer to `marketing-engineer/PRD.md` §6 phase 0 plus the kickoff's draft breakdown)
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, never a single combined tickets file. Numbers match the ticket ids used in the kickoff (`T0` → `00-…`, `T13` → `13-…`) so chat references and file names agree.
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings). Implementation state is recorded as a `Done:` line (`no` | `yes — <commit hash>`) so a later ticket can check its blockers without reading git.
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## When a skill says "mark the ticket done"

Set `Done: yes — <commit hash>` and tick the acceptance checkboxes that passed. A ticket is closed when its `Done:` line names a commit that is on the branch.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` (the Notes / Decisions-so-far / Fog body).
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.
