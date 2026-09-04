-- 0002: roles and grants. Enforces the single-executor rule in Postgres, not prose.
-- Apply after 0001. On Supabase run as postgres. Adjust passwords via Vault.
--
-- worker_rw : every worker (intel, voc, planner, producer, gate, loop, Claude Code sessions).
--             May insert entities and PROPOSE actions. May not decide, apply, or touch trust/pause/config.
-- executor  : the only role that transitions actions and holds vendor write keys (Meta, Instantly, Typefully).
-- sam_admin : the only role that writes clients.config (trust levels, pause) and quote_release / promote_trust decisions.
-- app       : quiz + review page (anon key via RLS); insert leads/lead_contacts only through RPC.
-- mcp_ro    : Postgres MCP for Claude's ad-hoc queries; no PII columns.

do $$ begin
  create role worker_rw nologin;  exception when duplicate_object then null; end $$;
do $$ begin
  create role executor nologin;   exception when duplicate_object then null; end $$;
do $$ begin
  create role sam_admin nologin;  exception when duplicate_object then null; end $$;
do $$ begin
  create role app nologin;        exception when duplicate_object then null; end $$;
do $$ begin
  create role mcp_ro nologin;     exception when duplicate_object then null; end $$;

grant usage on schema public to worker_rw, executor, sam_admin, app, mcp_ro;

-- worker_rw
grant select on all tables in schema public to worker_rw;
revoke select on lead_contacts from worker_rw;
grant insert on raw_ingest, voc_phrases, families, patterns, hooks, experiments, briefs, selections,
                 creatives, creative_components, gate_scores, campaigns, ad_entities, ad_metrics_daily,
                 account_spend_hourly, posts, post_metrics_daily, runs, learnings to worker_rw;
grant update (status, finished_at, counts, tokens_used, api_calls, error) on runs to worker_rw;
grant update (status, updated_at, posterior, effect_size, sample, evidence) on learnings to worker_rw;
grant update (status, evidence) on patterns to worker_rw;
grant insert on actions to worker_rw;   -- status must be 'proposed': enforced by trigger below

-- executor
grant select on all tables in schema public to executor;
grant update (status, decided_by, decided_at, decision_channel, approved_payload, reject_reason,
              attempts, last_error, executor_run_id, applied_at) on actions to executor;
grant update (status, review_status, review_feedback, launched_at, adset_daily_budget, object_story_id) on ad_entities to executor;
grant update (status, external_id, daily_budget, spend_cap, active_lever, active_lever_reason, active_lever_since) on campaigns to executor;
grant update (stage, stage_changed_at, nurture_sequence, instantly_lead_id, booked_verified_at) on leads to executor;
grant insert on runs, account_spend_hourly, actions to executor;

-- sam_admin
grant all on all tables in schema public to sam_admin;

-- app (through RPC functions only; direct table grants minimal)
grant insert on leads, lead_contacts to app;
grant select (id, client_id, offer_id) on leads to app;

-- mcp_ro
grant select on all tables in schema public to mcp_ro;
revoke select on lead_contacts from mcp_ro;
revoke select (quiz_answers, consent, fbclid_hash) on leads from mcp_ro;

-- Workers may only create actions in 'proposed'; only executor may move them; only sam_admin may
-- decide promote_trust / quote_release / set_pause_flag.
create or replace function actions_guard() returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    if new.status <> 'proposed' and current_user not in ('executor','sam_admin') then
      raise exception 'workers may only propose actions';
    end if;
    return new;
  end if;
  if tg_op = 'UPDATE' then
    if current_user = 'worker_rw' then
      raise exception 'workers may not transition actions';
    end if;
    if new.action_type in ('promote_trust','quote_release','set_pause_flag')
       and new.status in ('approved','applied') and current_user <> 'sam_admin' then
      raise exception 'only sam_admin may approve %', new.action_type;
    end if;
    return new;
  end if;
  return new;
end $$;
drop trigger if exists actions_guard_trg on actions;
create trigger actions_guard_trg before insert or update on actions for each row execute function actions_guard();

-- Budget invariant: sum of active ad set budgets + scaling campaign budgets <= clients.daily_cap.
create or replace function check_daily_cap(p_client uuid) returns boolean language sql stable as $$
  select coalesce((select daily_cap from clients where id = p_client), 0) >=
         coalesce((select sum(adset_daily_budget) from ad_entities where client_id = p_client and status = 'ACTIVE'), 0)
       + coalesce((select sum(daily_budget) from campaigns where client_id = p_client and kind = 'scaling' and status = 'ACTIVE'), 0);
$$;

-- Baseline RLS policies. RLS is a safety net now; client-scoped policies for the
-- app role land in 0003 with the first external tenant.
do $$ declare t text; begin
  foreach t in array array['clients','leads','lead_contacts','raw_ingest','voc_phrases','gate_scores'] loop
    execute format('drop policy if exists internal_read on %I', t);
    execute format('create policy internal_read on %I for select to worker_rw, executor, sam_admin, mcp_ro using (true)', t);
    execute format('drop policy if exists internal_write on %I', t);
    execute format('create policy internal_write on %I for all to worker_rw, executor, sam_admin using (true) with check (true)', t);
  end loop;
end $$;
-- app: insert leads and contacts only (through RPC), never read them back.
drop policy if exists app_insert on leads;
create policy app_insert on leads for insert to app with check (true);
drop policy if exists app_insert on lead_contacts;
create policy app_insert on lead_contacts for insert to app with check (true);
