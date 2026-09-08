# 04: Planner (T4)

**What to build:** Running `plan batch` computes capacity, writes an `experiments` row, ranks patterns deterministically, proposes 4× the recipe count as translated `briefs`, prints the numbered proposal table for Sam, and `--select` records the `selections` row for the chosen briefs.

**Blocked by:** T1 (01), T2 (02), T3 (03)

**Blocks:** T5 (05)

**Status:** ready-for-human (stop point A: proposal `batch-001` printed on the dev database, waiting for `my picks: n, n, n`; code complete, all acceptance criteria pass)

**Done:** yes — 1ae2838

**Stop point:** A — T4 done: print the numbered proposal table; wait for `my picks: n, n, n`.

Default if Sam goes quiet for 20 minutes: take the ranker's top three. Say which default was taken.

**FR ids:** FR-7 (guard only), FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, FR-20

## Deliverable

`scripts/plan_batch.py`: capacity formula → `experiments.capacity`; deterministic ranker (source strength × family diversity); translation with `changed_ingredients ⊆ {offer, product_nouns, voc_phrases, imagery_subject}`; 4× proposals as `briefs`; `--select "2,5,9"` writes `selections` and marks chosen; prints the numbered table in `SKILL.md` §5.1 format

## Acceptance

- [x] FR-14 to FR-20; at €30/day and €25 CPM capacity = 4 and a 6-creative batch is refused; a brief changing `copy_length` is rejected; same inputs → same order
- [x] FR-14: the run log (`runs.counts` or stdout) lists the queries executed, including the two read-before-planning queries from `SKILL.md` §4.2
- [x] FR-16: with 4 in-flight sub-sample creatives and capacity 4, no batch is requested
- [x] FR-17: batch one has 12 proposed, 3 chosen, one `selections` row with `selected_by='sam'` (or the default noted)
- [x] FR-19: unit test on all three ablation conditions (no ablation brief is created in phase 0; the guard is tested)
- [x] FR-8 consumer: two consecutive recorded failures on one inspo source make `plan batch` refuse with the source named
- [x] FR-7 guard: a brief whose family is `retired` for the client's ICP is refused (the retire flow itself is cut from phase 0; only the refusal is built and tested)

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

- 2026-09-08 (implementer): shipped in commit 1ae2838. `scripts/plan_batch.py` (`plan batch`; `--select "2, 5, 9"` / `--select default`; `--daily-budget`, `--cpm`, `--today`, `--client`), `references/prompts/planner.md` (system + instructions, read by the script), `fixtures/model/translate_brief.json` (SYNTHETIC, twelve translations), `tests/test_plan_batch.py` (16 tests), JSONB keys in `warehouse/schema-notes.md`, dev-mode note. Full suite: 147 passed against the real local cluster.
- 2026-09-08 (implementer): **stop point A reached on the dev database `gw`** (after `pull inspo` and `pull voc` with `MODEL_BACKEND=fixture`): run `d7f54222…` status `ok`, `capacity 6 = floor(45 x 7 x 1000 / (25 x 2000))`, batch 6, `experiments` row `batch-001` with `capacity 6`, 12 `briefs` + 12 `hooks`, `patterns_considered 30`, `voc_read 24`, `api_calls 12`, 11 queries logged. The §5.1 table is in this session's transcript; `python3 scripts/plan_batch.py` reprints it (an open proposal is never proposed twice). **Waiting for Sam:** `my picks: n, n, n` (exactly 3) → `python3 scripts/plan_batch.py --select "n, n, n"`. Default if quiet 20 minutes: `--select default` takes the ranker's top three (#1 screenshot_ad/AG1, #2 stat_card/AG1, #3 screenshot_ad/AG1) with `selected_by='ranker_default'` and says so in `selections.reason`. Not taken yet. Note the dev database lives in the build container; a fresh session re-runs `scripts/dev_db.sh --seed`, `pull_inspo.py --today 2026-09-07`, `pull_voc.py`, `plan_batch.py` (about a minute, no network) to get the same table back, same order (FR-20).
- 2026-09-08 (implementer): FR-15 proof (test): `--daily-budget 30 --cpm 25` → `capacity 4`, `batch of 6 creatives exceeds capacity 4; refused. Needs daily_budget >= 42.86 EUR at CPM 25`, runs row `failed` with `CapacityExceeded`, no `experiments` row; at 45 the batch fits (capacity 6). `daily_budget` is `clients.daily_cap` (ticket note). CPM is the last 7 days' observed CPM from `ad_metrics_latest` when the account has impressions (CRUCIBLE A9), else `config.cpm_estimate`; `runs.counts.cpm_source` says which.
- 2026-09-08 (implementer): FR-16 reading, **for Sam to confirm**: implemented as `in_flight_below_sample + batch_size <= capacity`. PRD FR-16's strict `<` (in-flight < capacity − batch_size) would make batch one impossible: 0 < 6 − 6 is false, yet FR-15's own AC says the 6-creative batch is accepted at daily_budget ≥ 45 (capacity 6) and spec.md decision 1 was taken for that. The FR-16 AC holds under `<=` too (4 in flight, capacity 4, any batch size → no batch), unit-tested for batch sizes 1–12 and end-to-end at 60/day (capacity 8: 4 in flight + 6 → no batch, run `ok` with `batch_requested 0`; two archived → batch requested). In-flight = `creatives.status='live'` with `mart_creative_performance.impressions < kill_impressions` (no metrics yet counts as 0).
- 2026-09-08 (implementer): FR-20 ranker: greedy, score `(source_strength + 1) / (1 + patterns already proposed from the same family)`, ties broken proven-first, then brand, then source ad id; the `+1` keeps diversity separating zero-strength candidates. Same inputs in any input order → same output (unit test); batch two from the same library ranks identically (end-to-end). Patterns without a complete five-key `format_layer` are skipped and counted (`patterns_skipped_incomplete`; T1's test row is one). When fewer than 4× recipes patterns are rankable the planner proposes what exists, warns, and counts `proposals_short`; fewer than `recipes` refuses.
- 2026-09-08 (implementer): FR-18: the format layer in `briefs.spec.format_layer` is compared key-for-key with the source `patterns.recipe.format_layer` (verbatim or the brief does not exist); `changed_ingredients` is enforced twice (JSON schema enum on the model output, then `validate_brief`); a replica of an external pattern must list `offer`; `voc_phrase_ids` and `'voc_phrases' in changed_ingredients` must agree. `briefs.angle` is carried from the source pattern (DECISIONS: angle is carried over exactly); `briefs.cta` stores `offers.offer_layer.cta_mechanic` (`book_15_min`), the producer writes the CTA copy (T5). One `hooks` row per brief (`text` = hook line, `pattern_id` = source, `trust_tier='owned'`).
- 2026-09-08 (implementer): FR-7 guard: a family counts as retired for the client's ICP when `families.status='retired'` or an applied `retire_family` action for the client names it in `target_id` (scoped to one ICP when `proposal.icp_id` is set, else every ICP). Such patterns never rank and `validate_brief` refuses them (tested both ways: 15 screenshot_ad + 5 us_vs_them skipped → 10 proposals). The retire flow itself (learnings row scope `icp`, proposing the action) is T10+.
- 2026-09-08 (implementer): FR-8: `plan batch` calls `warehouse.client.blocked_sources()` first and refuses with `SourceBlocked` naming the sources (test: Ridge failed twice → refused; `pull_inspo.py --acknowledge Ridge` → plans). FR-14: `runs.counts.queries` lists every read with its SQL (11 per run), the two SKILL.md §4.2 queries verbatim among them; `learnings_read` and `leaderboard_rows` are 0 on a fresh warehouse, as expected.
- 2026-09-08 (implementer): `--select` rules: exactly `config.batch.recipes` picks (= capacity/2 for batch one), numbers from the open proposal only, `n: reason` optional (`;` separates picks when a reason has commas), one `selections` row per proposal (a second pick is refused), `briefs.spec` gets `chosen`, `selection_id`, `selected_by`, `pick_reason` on every brief of the proposal (0003 grant). Refusals (paused, `applying` actions, blocked source, capacity, bad picks) close the runs row `failed` and exit 2; FR-16 not met closes `ok` with `batch_requested 0` and exits 0.
- 2026-09-08 (implementer): no `ANTHROPIC_API_KEY` in the build container, so `MODEL_BACKEND=claude` is wired (fixed system prompt, offer/ICP appended to the instructions, pattern text and VOC phrases only inside the data block) but unexercised; `translate_brief.json` is hand-written and its hook lines say FIXTURE. Record real outputs once the DRAFT offer is real. T5 (producer) is unblocked once Sam's picks are recorded.
