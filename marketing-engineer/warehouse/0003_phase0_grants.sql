-- 0003: phase-0 column grants for worker_rw (quiz decision 2, Sam 2026-09-04; see
-- .scratch/marketing-engineer-phase0/spec.md). Apply after 0002. Column grants only:
-- no new tables, no new columns, no change to the executor / sam_admin boundary.
--
-- Why: 0002 lets workers insert these rows but not move them. The producer and gate
-- move creatives through draft → gated → approved and re-render assets; the planner
-- marks chosen briefs in briefs.spec after Sam's picks; the loop records the lever it
-- selected on the campaign. Actions stay executor-only (FR-44); the trigger in 0002
-- still blocks any worker transition there.

grant update (status, asset_urls, sizes, version) on creatives to worker_rw;
grant update (spec) on briefs to worker_rw;
grant update (active_lever, active_lever_reason, active_lever_since) on campaigns to worker_rw;
