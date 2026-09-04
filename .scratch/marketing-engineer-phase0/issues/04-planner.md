# 04: Planner (T4)

**What to build:** Running `plan batch` computes capacity, writes an `experiments` row, ranks patterns deterministically, proposes 4× the recipe count as translated `briefs`, prints the numbered proposal table for Sam, and `--select` records the `selections` row for the chosen briefs.

**Blocked by:** T1 (01), T2 (02), T3 (03)

**Blocks:** T5 (05)

**Status:** ready-for-agent

**Done:** no

**Stop point:** A — T4 done: print the numbered proposal table; wait for `my picks: n, n, n`.

Default if Sam goes quiet for 20 minutes: take the ranker's top three. Say which default was taken.

**FR ids:** FR-7 (guard only), FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, FR-20

## Deliverable

`scripts/plan_batch.py`: capacity formula → `experiments.capacity`; deterministic ranker (source strength × family diversity); translation with `changed_ingredients ⊆ {offer, product_nouns, voc_phrases, imagery_subject}`; 4× proposals as `briefs`; `--select "2,5,9"` writes `selections` and marks chosen; prints the numbered table in `SKILL.md` §5.1 format

## Acceptance

- [ ] FR-14 to FR-20; at €30/day and €25 CPM capacity = 4 and a 6-creative batch is refused; a brief changing `copy_length` is rejected; same inputs → same order
- [ ] FR-14: the run log (`runs.counts` or stdout) lists the queries executed, including the two read-before-planning queries from `SKILL.md` §4.2
- [ ] FR-16: with 4 in-flight sub-sample creatives and capacity 4, no batch is requested
- [ ] FR-17: batch one has 12 proposed, 3 chosen, one `selections` row with `selected_by='sam'` (or the default noted)
- [ ] FR-19: unit test on all three ablation conditions (no ablation brief is created in phase 0; the guard is tested)
- [ ] FR-8 consumer: two consecutive recorded failures on one inspo source make `plan batch` refuse with the source named
- [ ] FR-7 guard: a brief whose family is `retired` for the client's ICP is refused (the retire flow itself is cut from phase 0; only the refusal is built and tested)

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

- Blocked by: T1 (01), T2 (02), T3 (03)
- Blocks: T5 (05)

## Notes for the implementer (dev mode)

Batch config: 3 recipes × 2 executions, proposals multiplier 4 (`config.batch`). Quiz decision 1 (Sam, 2026-09-04): the DRAFT config carries `daily_cap` 45 and `campaign.adset_daily_budget` 15, so the live batch computes capacity = floor(45 × 7 × 1000 / (25 × 2000)) = 6 and the 6-creative batch fits. The FR-15 acceptance test still runs the formula at €30/day and €25 CPM with explicit inputs (capacity 4, 6 creatives refused unless `daily_budget ≥ 45`). Capacity uses the client's `daily_cap` as `daily_budget`. `--select` writes `selections` and marks chosen briefs via `briefs.spec` (`0003` grant from T1).

## Comments
