-- 0007: launcher (T9). Apply after 0006. No new tables, no new columns; one function body and two grants.
--
-- (1) check_daily_cap() counts each ad set once. 0002 documented the invariant as "sum of active ad set
--     budgets + scaling campaign budgets <= clients.daily_cap" but summed `adset_daily_budget` over every
--     ACTIVE `ad_entities` row, so an ad set with two ads (the batch-one shape: 3 ad sets x 2 executions)
--     counted twice and activating the sixth ad of a 3 x EUR 15 campaign failed a EUR 45 cap. Ad sets have
--     no table; the budget is the same number on every ad row of the set (the executor's `scale` mirror
--     writes it to all of them), so the set's budget is `max()` over its rows grouped by (platform, adset_id).
--     Rows without an `adset_id` group together as one set. The scaling-campaign term is unchanged.
create or replace function check_daily_cap(p_client uuid) returns boolean language sql stable as $$
  select coalesce((select daily_cap from clients where id = p_client), 0) >=
         coalesce((select sum(s.budget) from (
                     select max(adset_daily_budget) as budget from ad_entities
                      where client_id = p_client and status = 'ACTIVE'
                      group by platform, adset_id) s), 0)
       + coalesce((select sum(daily_budget) from campaigns where client_id = p_client and kind = 'scaling' and status = 'ACTIVE'), 0);
$$;

-- (2) The executor records ads. SKILL.md §6 step 6 has the executor write every external id to
--     `campaigns` / `ad_entities` immediately after each Meta create; 0002 lets it update
--     `campaigns.external_id` but gave it no insert on `ad_entities` (`ad_id` is not null and unique, so a
--     row cannot exist before Meta has answered). Workers keep their 0002 insert; the executor writes only
--     what Meta returned (scripts/apply_actions.py `build_campaign`). The update grant from 0002 is unchanged.
grant insert on ad_entities to executor;

-- (3) The creative status flow (schema-notes.md, T5/T6) ends `approved` → `live` with the executor: the mirror sets
--     `creatives.status` from the ad's status Meta returned (ACTIVE → live; PAUSED → paused and ARCHIVED → killed
--     for a creative that went live). 0003 gave that column to worker_rw only. Column grant, nothing else.
grant update (status) on creatives to executor;
