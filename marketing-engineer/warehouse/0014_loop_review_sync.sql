-- 0014: FR-37 second half. Column grants only: no new tables, no new columns.
--
-- Why: `pull insights` (scripts/meta_insights.py, worker `loop`, role worker_rw) syncs
-- ad_entities.review_status / review_feedback from Meta's effective_status and ad_review_feedback for
-- every ad it reads, so disapprovals are counted against clients.config.disapproval_pause_threshold.
-- 0002 gave those two columns to the executor only. Status, budgets and launch dates stay the
-- executor's. A worker writing APPROVED here unblocks nothing at Meta: the cascade activate re-reads
-- review from Meta before anything flips, and Meta does not deliver a disapproved ad.
--
-- Numbered 0014 so it cannot collide with the numbers handed to the parallel phase-0 builders;
-- the integrator may renumber it to the next free number when merging.

grant update (review_status, review_feedback) on ad_entities to worker_rw;
