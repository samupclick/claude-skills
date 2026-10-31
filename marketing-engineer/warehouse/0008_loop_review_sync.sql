-- 0008: FR-37 second half. Column grants only: no new tables, no new columns.
--
-- Why: `pull insights` (scripts/meta_insights.py, worker `loop`, role worker_rw) syncs
-- ad_entities.review_status / review_feedback from Meta's effective_status and ad_review_feedback for
-- every ad it reads, so disapprovals are counted against clients.config.disapproval_pause_threshold.
-- 0002 gave those two columns to the executor only. Status, budgets and launch dates stay the
-- executor's. A worker writing APPROVED here unblocks nothing at Meta: the cascade activate re-reads
-- review from Meta before anything flips, and Meta does not deliver a disapproved ad.
--
-- Built as 0014 next to the parallel phase-0 completion builders; renumbered to 0008, the next free number, when
-- the branches were merged (2026-10-28). A dev database that recorded 0014 gets this grant again: it is idempotent.

grant update (review_status, review_feedback) on ad_entities to worker_rw;
