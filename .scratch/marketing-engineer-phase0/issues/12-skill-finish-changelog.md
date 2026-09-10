# 12: Skill finish + changelog (T12)

**What to build:** A fresh session invoking the `marketing-engineer` skill can answer "where are we" and find every phase-0 script, worker prompt, and JSONB key documented.

**Blocked by:** T0–T11 (00–11), all

**Blocks:** T13 (13)

**Status:** ready-for-human (review the shipped commit; code complete, all acceptance criteria pass; T13 now waits on Sam only)

**Done:** yes — 8462d1d

**Stop point:** none

**FR ids:** FR-48, DR-3, NFR-6 (DoD `PLAN.md` §1 item 11)

## Deliverable

`SKILL.md` §3 table matches the scripts that exist; `references/prompts/<worker>.md` for each worker prompt used; `warehouse/schema-notes.md` listing any JSONB keys introduced; `CHANGELOG.md`

## Acceptance

- [x] DoD `PLAN.md` §1 item 11; a fresh session invoking "where are we" works end to end
- [x] `SKILL.md` §3 rows for scripts that do not exist in phase 0 (`monday_memo.py`, `onboard.py`) say so explicitly rather than pointing at missing files
- [x] Every fixed system prompt used by a worker is in `references/prompts/<worker>.md` and the code loads it from there
- [x] `warehouse/schema-notes.md` lists every JSONB key phase 0 introduced (`clients.config`, `patterns.recipe`, `actions.proposal`/`evidence`, `gate_scores.hard_checks`/`feedback`, `learnings.evidence`, `runs.counts`)

## Constraints

- No side effect outside `scripts/apply_actions.py`: no Meta write endpoint, no Instantly, no email sender anywhere else. Workers write proposed `actions` only.
- Connect as the role for the job (`WAREHOUSE_URL_WORKER` for workers, `WAREHOUSE_URL_EXECUTOR` only in the executor). Never the service role. Never print or commit a secret.
- Every script opens and closes a `runs` row, including on failure.
- Untrusted text (`raw_ingest`, `patterns`, `voc_phrases`, quiz answers) enters prompts only inside a delimited data block with a fixed system prompt; model outputs are JSON validated against a schema.
- Full `creative_components` or the creative does not exist.
- Migrations only; no schema edits by hand; new fields go to the entity's JSONB and into `warehouse/schema-notes.md`.
- Nothing binary in git; assets go to Supabase Storage.
- Tests run against a local Postgres with `0001` + `0002` applied (see the fixture in T1). Do not mock the warehouse.
- One commit per task, message ending with the FR ids satisfied. Push after each commit.
- If a task cannot meet its acceptance criteria, stop and report which criterion and why; do not narrow the criterion.

## Blocking edges

- Blocked by: T0–T11 (00–11), all
- Blocks: T13 (13)

## Notes for the implementer (dev mode)

No new behaviour here; documentation and the end-to-end dry run only. Note in `CHANGELOG.md` which placeholders (config, families, VOC seed, fixture shape) remain DRAFT.

## Comments
- 2026-09-10 (implementer): started at Sam's "start t12" on a fresh container; the branch was 10 commits behind (T5, T6, T9, T10, T11 landed), pulled first. `playwright` was missing from the container (the SessionStart hook's plugin step had failed, so its `pip install` step never ran); `pip install -r requirements.txt` fixed it and the baseline suite passed before any change.
- 2026-09-10 (implementer): what changed. (1) `SKILL.md`: §0 step 3 and the §3 first row name `warehouse/client.py status [slug]`; §1 splits `WAREHOUSE_URL_SAM_ADMIN` (Sam's `decide.py --as sam_admin` / `apply_actions.py --role sam_admin`) from `WAREHOUSE_URL_ADMIN` (dev-only superuser for `dev_db.sh` / `seed.py`) and lists `_APP`, `_MCP_RO`, `ANTHROPIC_API_KEY`, `CHECKIN_TO`, `FUNNEL_HOST`, the nine `*_BACKEND` selectors (T8's wording note); §3 adds the `acknowledge`, `approve/reject` and flag details, the `launch` row says the second run proposes the cascade `activate` (T9's note), and the `monday memo` / `onboard client` rows say **not built in phase 0** with the script name that does not exist; §5.3 names the sam_admin commands; §9 is the tree as it exists (the old `references/meta-launch-playbook.md`, `warehouse/queries/*.sql`, `monday_memo.py`, `onboard.py` are gone from it; migrations 0003–0007, `launch.py`, `adapters/`, `funnel/`, `fixtures/`, `tests/`, `routines.json`, `routines.py`, `seed.py`, `dev_db.sh`, `CHANGELOG.md`, the hook's real path are in); new §11 is the Friday checklist (DoD item 11 asks for it in `SKILL.md`) plus the go-live swap pointer. §8's table is untouched (`tests/test_routines.py` pins it to `config/routines.json`). (2) The intel worker was the one worker with its system prompt as a literal in code: `references/prompts/intel.md` now holds it and `scripts/pull_inspo.py` reads it with the same `load_prompts()` shape as the other four (`DECOMPOSE_SYSTEM` / `DECOMPOSE_INSTRUCTIONS` are bound from the file at import, so `tests/test_pull_inspo.py` is unchanged). (3) `warehouse/schema-notes.md` gains `offers.offer_layer`, `actions.approved_payload`, `ad_entities.review_feedback`, and a paragraph naming the JSONB columns no phase-0 worker writes (`patterns.evidence`, `experiments.result`, `erasure_requests.fanout`); every other column and every `Run.count()` key was already there. (4) `CHANGELOG.md`: one row per ticket with its commit, the build decisions Sam may overrule, the DRAFT / synthetic table, the gaps carried into T13 / phase 1. (5) `references/dev-mode.md`: the `me-monday` sentence no longer says T12 builds the memo; the warehouse row names all six URLs. (6) `tests/test_skill.py` (5 tests) pins all of it: §3 scripts exist or the row says not built, §9 names only files that exist, each worker's `load_prompts()` reads its file and no script carries a literal `system=`, every `jsonb` column in `schema.sql` and every `.count("…")` key is in schema-notes, and `warehouse/client.py status` runs as a subprocess against the test database (exit 0, all §2 columns; unknown slug exits 1).
- 2026-09-10 (implementer): end-to-end on this container's dev database `gw` (fresh: 0 patterns, 0 phrases, so "where are we" is the honest empty state). `python3 warehouse/client.py status upclicklabs` prints the §2 table, exit 0. `MODEL_BACKEND=fixture python3 scripts/routines.py dry-run me-morning`: status ok, pull insights ok (0 ads), apply actions --reconcile ok, check-in ok (`.eml` in the outbox, 1 waiting, 7 warnings), three `runs` rows; `dry-run me-monday`: status ok, `monday memo` reported "not built", exit 1 as designed. Observation for Sam: the families.md name conflict (open since T0) makes every `dev_db.sh --seed` close a failed `seed` run, and after a few seeds the check-in's worker error-rate brake proposes `set_pause_flag` ("worker seed failed 6 of 6 runs in the last 1h"); renaming the two angles clears both.
- 2026-09-10 (implementer): not done here, on purpose: `monday_memo.py` and `onboard.py` (outside the phase-0 DoD, `PLAN.md` §1; `SKILL.md` §3 says so), the live adapters (T13), and the FR-37 review-status sync on every insights pull (T9's note for T10, listed under "Known gaps" in the changelog). T13 is now blocked on Sam's Friday checklist only.
