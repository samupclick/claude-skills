# 06: Gate (T6)

**What to build:** Running `gate` scores every draft creative: hard checks into `gate_scores.hard_checks`, a shadow rubric row by the agent, and prints the numbered creative table for Sam; `--verdicts` writes Sam's chat verdicts as `gate_scores` rows.

**Blocked by:** T5 (05)

**Blocks:** T9 (09)

**Status:** ready-for-human (stop point B: the §5.2 table for `batch-001` is printed on the dev database, waiting for `verdicts: …`; code complete, all acceptance criteria pass)

**Done:** yes — 8e55c50

**Stop point:** B — T6 done: print the numbered creative table with Storage URLs and hard-check results; wait for `verdicts: approve …; reject …: reason`.

Default if Sam goes quiet for 20 minutes: ship nothing. Say which default was taken.

**FR ids:** FR-12 (hard check), FR-26, FR-27, FR-29

## Deliverable

`scripts/gate.py`: hard checks (policy prompt, brand hard blocks, likeness, testimonial block, coherence → planner, components, landing URL match, verbatim phrase without release) into `gate_scores.hard_checks`; rubric in `mode='shadow'`; `--verdicts "approve 1,3; reject 2: reason"` writes `scored_by='sam'`, `decision_channel='chat'`; prints the §5.2 table

## Acceptance

- [x] FR-26, FR-27, FR-29; one fixture per hard check that fails it; no `agent` row ever has `mode='blocking'`
- [x] FR-29: a hard-check failure records the feedback object and attempt number; attempt 4 is impossible (the fourth attempt is refused and logged)
- [x] FR-12: an `internal` phrase used verbatim without an applied `quote_release` action fails the `verbatim` hard check

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

- Blocked by: T5 (05)
- Blocks: T9 (09)

## Notes for the implementer (dev mode)

Policy and rubric prompts run through the model adapter with the creative text inside the delimited data block; outputs are schema-validated JSON. The §5.2 table shows the Storage URL, the source ad URL (our copy), hard-check results, and shadow rubric scores. Coherence failures route feedback to the planner (recorded, not re-run automatically).

## Comments

- 2026-09-08 (implementer): shipped in commit 8e55c50. `scripts/gate.py` (`gate`; `--experiment`, `--rescore`; `--verdicts "…"` / `--verdicts default`, `--by`), `references/creative-rubric.md` (dimensions, rubric rule, the eight hard checks and where each routes), `references/prompts/gate.md` (`gate_checks`, `gate_vision`, `gate_rubric`), `fixtures/model/gate_*.json` (SYNTHETIC, clean answers; the rubric alternates approve / reject), `tests/test_gate.py` (21 tests: 9 unit, one parametrised over the eight checks, verdicts, attempt 4, refusals), JSONB keys + creative status flow in `warehouse/schema-notes.md`, dev-mode note. Two T5 amendments in the same commit because the gate needs them: the producer keeps the filled template as `1080x1080.html` beside the PNG (the gate reads every rendered word through the storage adapter; without it the overlay words were unchecked) and `--rerender` refuses a fourth version (FR-29 on the producer side). Full suite: 185 passed against the real local cluster.
- 2026-09-08 (implementer): **stop point B reached on the dev database `gw`**: run `49b91bb1…` ok, `batch-001` 6 creatives `gated`, 6 agent rows (`mode='shadow'`, attempt 1), `api_calls 18` (3 per creative). Table: #1–#4 (briefs #1, #3) PASS; **#5 (brief #6, execution 1) FAIL: verbatim** (the planner fixture's hook line "I want a prospect to say the AI told me to call you" is an `internal` vault phrase word for word, no `quote_release`; FR-12 working as specified, feedback routed to the producer); #6 PASS. Shadow rubric alternates approve (avg 3.86) / reject (avg 3.29) from the fixture and says nothing about the creatives. **Waiting for Sam:** `verdicts: approve 1,3,4; reject 2: reason` → `python3 scripts/gate.py --verdicts "…"`; `#5` cannot be approved (facts block) until a `quote_release` for brief #6 is applied as `sam_admin` (`scripts/decide.py --as sam_admin`) and `gate --rescore` runs, or the producer re-renders it. Default if quiet 20 minutes: `--verdicts default`, nothing ships, nothing written. Not taken. `python3 scripts/gate.py` reprints the table.
- 2026-09-08 (implementer): FR-26 proof: each of the eight checks has a test that fails it on creative #1 alone (`test_each_hard_check_has_a_fixture_that_fails_it[policy|brand|likeness|testimonial|coherence|components|landing|verbatim]`): policy / likeness / coherence / testimonial through a temporary model fixture, brand through "€999 per month" in the copy (rule-based scan, only rules named in `config.brand.hard_blocks` fire; client names need the model's `brand_flags`), components by deleting the `angle` row, landing by pointing `landing_page` elsewhere, verbatim by quoting an internal phrase. `hard_checks` carries all eight keys on every row; `hard_blocks` the failed names; `policy_flags` the model's labels. `likeness` also fails on logos / wordmarks in the picture; `testimonial` on a quote family without release, a depicted person in a quote family, or a fabricated quote in the copy.
- 2026-09-08 (implementer): FR-27 proof: the agent row is written with `mode=AGENT_MODE` (`'shadow'`, a constant; a test greps the insert) and `decision_channel='auto'`; the query `scored_by='agent' and mode='blocking'` returns 0 after every run; the agent's `verdict` is recomputed from the scores by the rubric rule (no dimension < 3, mean ≥ 3.5) so a model that contradicts its own scores is corrected and the reason says so. Sam's rows: `scored_by='sam'`, `decision_channel='chat'`, `mode='blocking'` (the decision that ships), `verdict`, reason in `feedback.reason`, the agent row's `hard_checks` / `passed` copied for the record. `approve` → `creatives.status='approved'`; `reject` → `archived`; approving a failed creative refuses the whole reply before writing anything; unknown numbers likewise.
- 2026-09-08 (implementer): FR-29 proof: `gate_scores.attempt = creatives.version` (the producer's `--rerender` archives and bumps it); a draft at version 4 is never scored: archived, `dropped_max_attempts` counted, `attempt 4 is impossible (FR-29)` on stderr; the producer refuses `--rerender` past version 3 with the same words. The feedback object (`route`, `attempt {current, max, next_possible}`, `failures[] {criterion, severity, issues, fix_guidance}`, `preserve`, `constraints`) is the content-supervisor §5.1 shape trimmed to what a re-run needs; `coherence` routes to the planner (recorded, not re-run, per the ticket note), everything else to the producer. Neither worker reads the feedback yet: the re-render is Sam's call in phase 0 (`produce --rerender`).
- 2026-09-08 (implementer): FR-12 / verbatim rule: phrases with `visibility='internal'` or `trust_tier in ('public','inbound')` are scanned against the creative's words (`primary_text`, `headline`, `description`, hook, every rendered word from the HTML); a hit is the whole `phrase_normalised` or any run of 8 consecutive words of it (`VERBATIM_MIN_WORDS`; the anonymised vault phrases are sentences, so a whole-phrase match alone would let the hook above through). An `internal` hit passes when an applied `quote_release` names the creative, its brief, or the phrase (`target_id` or `proposal.creative_id` / `brief_id` / `voc_phrase_id`, documented in schema-notes); `public` / `inbound` hits never pass (CRUCIBLE A13). Tested both ways (release inserted as `sam_admin`, `--rescore` → pass).
- 2026-09-08 (implementer): numbering: the §5.2 number is the creative's rank among the batch's `gated` creatives (brief proposal number, version, first execution first, created_at), recomputed identically by `gate` and `--verdicts`; after some verdicts the remaining ones are renumbered from 1 and the reprinted table says so, so read the table before replying. Decisions worth a glance: (1) the gate keeps the creative `gated` when a hard check fails (the agent row says `passed=false`), rather than a status of its own; (2) `--rescore` writes a new agent row at the same attempt (a re-check, not a retry); (3) the rendered words come from `1080x1080.html`; a pre-T6 render without it is gated on the database words with `html_missing` counted and a WARNING. (4) `gate_vision` gets the render and the generated image, `gate_rubric` the render and our copy of the source ad; the fixture backend ignores them, the Claude backend attaches them (unexercised: no key in the container).
