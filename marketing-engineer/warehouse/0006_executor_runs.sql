-- 0006: executor closes its own runs row (T8). Apply after 0005. Column grants only: no new tables,
-- no new columns, no change to the executor / sam_admin boundary on actions.
--
-- Why: 0002 lets the executor insert into runs but grants update on runs to worker_rw only, so
-- scripts/apply_actions.py could open its runs row and never close it (SKILL.md §0 step 2 and §7
-- require every invocation to close the row, including on failure). Same six columns as worker_rw.

grant update (status, finished_at, counts, tokens_used, api_calls, error) on runs to executor;
