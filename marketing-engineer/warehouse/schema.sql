-- Growth Warehouse — migration 0001 (Postgres 15+, Supabase, EU region)
-- Incorporates every "fold into 0001" block from DECISIONS.md components 1–9
-- and the crucible amendments (CRUCIBLE.md). Deferred to later migrations:
-- events (wk3 reactor), review_tokens (wk2 email review), competitors (wk2),
-- benchmarks table (config floors until then), embeddings refresh, RLS policies
-- beyond the scaffold (0002_roles.sql).
--
-- Conventions: uuid pks; client_id on every entity row; created_at everywhere;
-- metrics append-only (restatements are new rows keyed by fetched_on);
-- enums as check constraints; PII isolated in lead_contacts; views run as
-- security_invoker so RLS applies through them.

create extension if not exists "pgcrypto";
create extension if not exists vector;

-- ---------- RAW ----------
create table raw_ingest (
  id           uuid primary key default gen_random_uuid(),
  source       text not null,
  client_id    uuid,
  external_id  text,
  dedup_key    text unique,                 -- source + external_id + content hash
  trust_tier   text not null default 'public' check (trust_tier in ('owned','client','public','inbound')),
  fetched_at   timestamptz not null default now(),
  purge_after  timestamptz,                 -- PII sources: fetched_at + 90 days
  payload      jsonb not null
);
create index on raw_ingest (source, fetched_at desc);
create index on raw_ingest (client_id, source);

-- ---------- CORE ENTITIES ----------
create table clients (
  id           uuid primary key default gen_random_uuid(),
  name         text not null,
  slug         text not null unique,
  site         text,
  industry     text,
  currency     text not null default 'EUR',
  daily_cap    numeric(12,2),               -- hard invariant: sum of active budgets <= daily_cap
  paused       boolean not null default false,
  -- config: targets{ctr_floor,kill_impressions,cpl_target?}, floors{lever:value},
  -- trust{action_type:{threshold,unit}}, worker_budgets{worker:{tokens,calls}},
  -- families_ref, quiz, brand, image_model, renderer
  config       jsonb not null default '{}',
  created_at   timestamptz not null default now()
);

create table offers (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references clients(id),
  name          text not null,
  promise       text,
  price_anchor  text,
  proof_points  text[] default '{}',
  landing_url   text,
  funnel_host   text,
  calendar_url  text,
  terminal_metric text not null default 'booked_call',
  quiz_config   jsonb default '{}',
  offer_layer   jsonb default '{}',         -- offer_mechanic, proof_type, cta_mechanic (fixed per offer, see C3 amendment)
  created_at    timestamptz not null default now()
);

create table icps (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references clients(id),
  label         text not null,
  role          text,
  company_type  text,
  industry      text,
  geo           text[] default '{}',
  size_band     text,
  pains         text[] default '{}',
  outcomes      text[] default '{}',
  created_at    timestamptz not null default now()
);

-- ---------- LANGUAGE ----------
create table voc_phrases (
  id                uuid primary key default gen_random_uuid(),
  client_id         uuid references clients(id),
  icp_id            uuid references icps(id),
  phrase            text not null,           -- already anonymised at extraction
  phrase_normalised text not null,
  category          text not null check (category in ('pain','outcome','objection','identity','trigger')),
  source            text,                    -- vault | quiz | reddit | quora | g2 | clutch | linkedin | x
  source_ref        text,                    -- pointer (note path, hashed URL), never the text
  source_weight     int not null default 1,  -- vault 3, quiz 2, public 1
  trust_tier        text not null default 'public' check (trust_tier in ('owned','client','public','inbound')),
  visibility        text not null default 'public' check (visibility in ('internal','public')),
  frequency         int not null default 1,
  embedding         vector(1536),
  created_at        timestamptz not null default now(),
  unique (source_ref, phrase_normalised)
);

-- ---------- INTEL ----------
create table families (
  name        text primary key,
  kind        text not null check (kind in ('format','hook_type','angle')),
  status      text not null default 'active' check (status in ('active','retired','proposed')),
  promoted_from_variant text,
  created_at  timestamptz not null default now()
);

create table patterns (
  id               uuid primary key default gen_random_uuid(),
  client_id        uuid references clients(id),        -- null = external / market
  origin           text not null check (origin in ('external','internal')),
  source_list      text not null check (source_list in ('dtc','category','own')),
  family           text not null references families(name),
  variant          text,
  hook_type        text,
  angle            text,
  status           text not null default 'candidate' check (status in ('candidate','proven','retired')),
  source_strength  int not null default 0,             -- ordinal, for ranking only, never a benchmark
  source_brand     text,
  source_url       text,
  source_image_url text,                                -- OUR Storage copy; CDN URLs expire
  start_date       date,
  days_running     int,
  concurrent_variants int,
  recipe           jsonb not null default '{}',         -- {format_layer:{...}, offer_layer:{...}}
  evidence         jsonb default '{}',                  -- internal: creative ids + metrics
  trust_tier       text not null default 'public' check (trust_tier in ('owned','client','public','inbound')),
  embedding        vector(1536),
  created_at       timestamptz not null default now()
);

create table hooks (
  id           uuid primary key default gen_random_uuid(),
  client_id    uuid references clients(id),
  text         text not null,
  hook_type    text,
  pattern_id   uuid references patterns(id),
  trust_tier   text not null default 'owned' check (trust_tier in ('owned','client','public','inbound')),
  embedding    vector(1536),
  created_at   timestamptz not null default now()
);

-- ---------- PLANNING ----------
create table experiments (
  id             uuid primary key default gen_random_uuid(),
  client_id      uuid not null references clients(id),
  offer_id       uuid references offers(id),
  name           text not null,
  kind           text not null default 'new_recipes' check (kind in ('new_recipes','ablation','renderer_pair')),
  variable       text,
  primary_metric text not null default 'link_ctr',
  budget_share   numeric(4,3) default 1.0,
  capacity       int,                        -- creatives that can reach sample size this week (derived)
  started_at     timestamptz,
  ended_at       timestamptz,
  result         jsonb default '{}',
  created_at     timestamptz not null default now()
);

create table briefs (
  id                  uuid primary key default gen_random_uuid(),
  client_id           uuid not null references clients(id),
  experiment_id       uuid references experiments(id),
  offer_id            uuid references offers(id),
  icp_id              uuid references icps(id),
  kind                text not null default 'replica' check (kind in ('replica','ablation')),
  source_pattern_id   uuid references patterns(id),
  ablation_of_creative_id uuid,
  changed_ingredients text[] default '{}',   -- must be subset of {offer, product_nouns, voc_phrases, imagery_subject}
  family              text references families(name),
  angle               text not null,
  hook_id             uuid references hooks(id),
  voc_phrase_ids      uuid[] default '{}',
  visual_spec         text,
  cta                 text,
  spec                jsonb default '{}',
  created_at          timestamptz not null default now()
);

create table selections (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references clients(id),
  experiment_id uuid references experiments(id),
  proposed      uuid[] not null,
  chosen        uuid[] not null,
  rejected      uuid[] not null,
  reason        text,
  selected_by   text not null,
  created_at    timestamptz not null default now()
);

-- ---------- PRODUCTION ----------
create table creatives (
  id                   uuid primary key default gen_random_uuid(),
  client_id            uuid not null references clients(id),
  brief_id             uuid references briefs(id),
  experiment_id        uuid references experiments(id),
  status               text not null default 'draft' check (status in ('draft','gated','approved','live','paused','killed','archived')),
  primary_text         text,
  headline             text,
  description          text,
  renderer             text check (renderer in ('html_template','image_to_image')),
  template             text,
  image_model          text,
  image_prompt         text,
  source_reference_url text,                -- Storage copy
  fidelity_score       numeric(4,3),
  asset_urls           text[] default '{}',
  sizes                text[] default '{}',
  version              int not null default 1,
  created_at           timestamptz not null default now()
);
alter table briefs add constraint briefs_ablation_fk foreign key (ablation_of_creative_id) references creatives(id);

create table creative_components (
  creative_id    uuid not null references creatives(id) on delete cascade,
  component_type text not null check (component_type in
    ('family','variant','hook','hook_type','angle','template','renderer','image_model',
     'voc_phrase','cta','landing_page','offer','proof_type','copy_length')),
  component_ref  text not null,
  primary key (creative_id, component_type, component_ref)
);
create index on creative_components (component_type, component_ref);

create table gate_scores (
  id               uuid primary key default gen_random_uuid(),
  creative_id      uuid not null references creatives(id) on delete cascade,
  attempt          int not null default 1,
  scored_by        text not null check (scored_by in ('agent','sam','human')),
  mode             text not null default 'shadow' check (mode in ('shadow','blocking')),
  verdict          text check (verdict in ('approve','reject')),
  decision_channel text check (decision_channel in ('chat','token_post','app','auto')),
  scores           jsonb not null default '{}',
  avg_score        numeric(3,2),
  hard_checks      jsonb not null default '{}',   -- {policy:pass, likeness:pass, coherence:fail, components:pass, landing:pass, testimonial:pass}
  policy_flags     text[] default '{}',
  hard_blocks      text[] default '{}',
  passed           boolean,
  feedback         jsonb default '{}',
  feedback_trust   text not null default 'owned' check (feedback_trust in ('owned','inbound')),
  created_at       timestamptz not null default now()
);

-- ---------- PAID ----------
create table campaigns (
  id                 uuid primary key default gen_random_uuid(),
  client_id          uuid not null references clients(id),
  offer_id           uuid references offers(id),
  platform           text not null default 'meta',
  kind               text not null check (kind in ('new_recipes','ablation','scaling')),
  external_id        text,
  currency           text not null default 'EUR',
  daily_budget       numeric(12,2),
  spend_cap          numeric(12,2),
  terminal_metric    text not null default 'booked_call',
  optimisation_event text not null default 'QuizStart',   -- Meta's event; NOT the terminal metric
  active_lever       text,
  active_lever_reason text,
  active_lever_since timestamptz,
  status             text not null default 'PAUSED' check (status in ('PAUSED','ACTIVE','ARCHIVED')),
  created_at         timestamptz not null default now(),
  unique (platform, external_id)
);

create table ad_entities (
  id                 uuid primary key default gen_random_uuid(),
  client_id          uuid not null references clients(id),
  campaign_id        uuid references campaigns(id),
  creative_id        uuid references creatives(id),
  recipe_pattern_id  uuid references patterns(id),
  platform           text not null default 'meta',
  adset_id           text,
  adset_daily_budget numeric(12,2),
  ad_id              text not null,
  object_story_id    text,
  optimisation_event text,
  status             text not null default 'PAUSED' check (status in ('PAUSED','ACTIVE','ARCHIVED','DELETED')),
  review_status      text default 'PENDING' check (review_status in ('PENDING','APPROVED','DISAPPROVED','WITH_ISSUES')),
  review_feedback    jsonb default '{}',
  launched_at        timestamptz,
  created_at         timestamptz not null default now(),
  unique (platform, ad_id)
);

-- Append-only, restatements allowed: one row per (ad, day, fetch date).
create table ad_metrics_daily (
  ad_entity_id  uuid not null references ad_entities(id),
  day           date not null,
  fetched_on    date not null default current_date,
  impressions   bigint default 0,
  reach         bigint default 0,
  clicks        bigint default 0,
  link_clicks   bigint default 0,
  spend         numeric(12,2) default 0,
  quiz_starts   int default 0,
  quiz_completes int default 0,
  schedules     int default 0,               -- Meta-reported; verification lives in leads
  video_3s      bigint,
  frequency     numeric(6,3),
  cpm           numeric(10,4) generated always as (case when impressions > 0 then spend / impressions * 1000 else null end) stored,
  link_ctr      numeric(8,5) generated always as (case when impressions > 0 then link_clicks::numeric / impressions else null end) stored,
  fetched_at    timestamptz not null default now(),
  primary key (ad_entity_id, day, fetched_on)
);

create view ad_metrics_latest with (security_invoker = true) as
select distinct on (ad_entity_id, day) *
from ad_metrics_daily
order by ad_entity_id, day, fetched_on desc;

-- Account-level hourly spend for the brake, separate from the daily per-ad pull.
create table account_spend_hourly (
  client_id   uuid not null references clients(id),
  observed_at timestamptz not null,
  spend_today numeric(12,2) not null,
  primary key (client_id, observed_at)
);

-- ---------- ORGANIC (schema now, populated when publishing is in scope) ----------
create table posts (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references clients(id),
  creative_id   uuid references creatives(id),
  channel       text not null check (channel in ('x','linkedin','ig','tiktok','youtube')),
  external_id   text,
  text          text,
  hook_id       uuid references hooks(id),
  posted_at     timestamptz,
  created_at    timestamptz not null default now(),
  unique (channel, external_id)
);

create table post_metrics_daily (
  post_id       uuid not null references posts(id),
  day           date not null,
  fetched_on    date not null default current_date,
  impressions   bigint default 0,
  engagements   bigint default 0,
  reposts       int default 0,
  replies       int default 0,
  saves         int default 0,
  profile_clicks int default 0,
  link_clicks   int default 0,
  follows       int default 0,
  engagement_rate numeric(8,5) generated always as (case when impressions > 0 then engagements::numeric / impressions else null end) stored,
  primary key (post_id, day, fetched_on)
);

-- ---------- LEADS (PII isolated) ----------
create table leads (
  id                  uuid primary key default gen_random_uuid(),
  client_id           uuid not null references clients(id),
  offer_id            uuid references offers(id),
  ad_entity_id        uuid references ad_entities(id),
  post_id             uuid references posts(id),
  creative_id         uuid references creatives(id),
  source              text,
  utm                 jsonb default '{}',
  fbclid_hash         text,
  quiz_version        text,
  quiz_answers        jsonb default '{}',
  qualification_score numeric(5,2),
  consent             jsonb not null default '{}',   -- {tracking:bool, marketing:bool, verbatim_use:bool, notice_version, at}
  stage               text not null default 'new' check (stage in ('new','completed','booked','showed','qualified','proposal','closed_won','closed_lost','erased')),
  booked_verified_at  timestamptz,                  -- set only from the calendar tool's authenticated API
  stage_changed_at    timestamptz,
  nurture_sequence    text,
  instantly_lead_id   text,
  value               numeric(12,2),
  abuse_score         numeric(4,3) default 0,
  purge_after         timestamptz,
  created_at          timestamptz not null default now()
);
create index on leads (client_id, stage);
create index on leads (creative_id);

create table lead_contacts (
  lead_id     uuid primary key references leads(id) on delete cascade,
  email       text,
  phone       text,
  name        text,
  created_at  timestamptz not null default now()
);

create table erasure_requests (
  id           uuid primary key default gen_random_uuid(),
  client_id    uuid references clients(id),
  lead_id      uuid references leads(id),
  email_hash   text,
  requested_at timestamptz not null default now(),
  fanout       jsonb not null default '{}',   -- {warehouse:done_at, storage:..., instantly:..., meta_audience:..., backups:...}
  completed_at timestamptz
);

-- ---------- ACTIONS (the only path to a side effect) ----------
create table actions (
  id                uuid primary key default gen_random_uuid(),
  client_id         uuid not null references clients(id),
  action_type       text not null check (action_type in
    ('build_campaign','activate','pause','kill','scale','relaunch','publish_post','push_to_instantly',
     'send_email','quote_release','promote_trust','set_pause_flag','retire_family','promote_variant')),
  target_type       text not null,            -- ad_entity | campaign | creative | lead | post | client | family | trust
  target_id         text not null,
  rule              text,
  proposal          jsonb not null default '{}',
  proposal_key      text not null unique,     -- hash(action_type, target, rule, evidence window)
  evidence          jsonb not null default '{}',
  trust_level_at_proposal text not null default 'propose' check (trust_level_at_proposal in ('propose','execute')),
  status            text not null default 'proposed' check (status in ('proposed','approved','rejected','applying','applied','failed','superseded')),
  decided_by        text,
  decided_at        timestamptz,
  decision_channel  text check (decision_channel in ('chat','token_post','app','auto')),
  approved_payload  jsonb,
  reject_reason     text,
  attempts          int not null default 0,
  last_error        text,
  executor_run_id   uuid,
  applied_at        timestamptz,
  created_at        timestamptz not null default now()
);
create index on actions (client_id, status);
create index on actions (action_type, status);

-- Every worker / executor invocation.
create table runs (
  id           uuid primary key default gen_random_uuid(),
  worker       text not null,                -- intel | voc | planner | producer | gate | launcher | loop | executor | checkin
  client_id    uuid references clients(id),
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  status       text not null default 'running' check (status in ('running','ok','failed')),
  counts       jsonb default '{}',
  tokens_used  bigint,
  api_calls    int,
  error        text
);
create index on runs (worker, started_at desc);

-- ---------- LEARNINGS ----------
create table learnings (
  id             uuid primary key default gen_random_uuid(),
  client_id      uuid references clients(id),
  icp_id         uuid references icps(id),
  scope          text not null check (scope in ('client','icp','global')),
  hypothesis     text not null,
  component_type text,
  component_ref  text,
  direction      text check (direction in ('beat','miss')),
  effect_size    numeric(8,5),
  sample         int,
  posterior      numeric(4,3),               -- P(direction) from Beta-Binomial on clicks/impressions
  evidence       jsonb not null default '{}',
  status         text not null default 'proposed' check (status in ('proposed','supported','global','refuted','retired')),
  embedding      vector(1536),
  created_by     text not null default 'agent',
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

-- ---------- MARTS (security_invoker so RLS applies) ----------
create view mart_creative_performance with (security_invoker = true) as
select c.id as creative_id, c.client_id, c.experiment_id, c.status, c.renderer, c.template, c.image_model,
       sum(m.impressions) as impressions, sum(m.link_clicks) as link_clicks, sum(m.spend) as spend,
       sum(m.quiz_starts) as quiz_starts, sum(m.quiz_completes) as quiz_completes, sum(m.schedules) as schedules_reported,
       case when sum(m.impressions) > 0 then sum(m.link_clicks)::numeric / sum(m.impressions) end as link_ctr,
       case when sum(m.link_clicks) > 0 then sum(m.spend) / sum(m.link_clicks) end as cost_per_link_click,
       min(m.day) as first_day, max(m.day) as last_day
from creatives c
join ad_entities a on a.creative_id = c.id
join ad_metrics_latest m on m.ad_entity_id = a.id
group by c.id;

create view mart_funnel with (security_invoker = true) as
select c.id as creative_id, c.client_id, c.experiment_id,
       count(l.id) filter (where l.stage not in ('erased')) as leads,
       count(l.id) filter (where l.stage in ('completed','booked','showed','qualified','proposal','closed_won','closed_lost')) as completed,
       count(l.id) filter (where l.booked_verified_at is not null) as booked_verified,
       count(l.id) filter (where l.stage in ('qualified','proposal','closed_won')) as qualified,
       count(l.id) filter (where l.stage = 'closed_won') as closed_won,
       coalesce(sum(l.value) filter (where l.stage = 'closed_won'), 0) as revenue
from creatives c
left join leads l on l.creative_id = c.id and coalesce(l.abuse_score,0) < 0.5
group by c.id;

create view mart_component_leaderboard with (security_invoker = true) as
select cc.component_type, cc.component_ref, p.client_id, i.industry,
       count(distinct p.creative_id) as creatives,
       sum(p.impressions) as impressions, sum(p.link_clicks) as link_clicks, sum(p.spend) as spend,
       sum(f.booked_verified) as booked_verified,
       case when sum(p.impressions) > 0 then sum(p.link_clicks)::numeric / sum(p.impressions) end as link_ctr,
       -- lower bound of a ~95% CI on CTR (Wilson), for ranking; rank by this, not the point estimate
       case when sum(p.impressions) > 0 then
         ((sum(p.link_clicks)::numeric + 1.92) / (sum(p.impressions) + 3.84))
         - 1.96 * sqrt((sum(p.link_clicks)::numeric * (sum(p.impressions) - sum(p.link_clicks)) / sum(p.impressions) + 0.96) / (sum(p.impressions) + 3.84)) / sqrt(sum(p.impressions) + 3.84)
       end as link_ctr_lcb,
       case when sum(f.booked_verified) > 0 then sum(p.spend) / sum(f.booked_verified) end as cost_per_booked
from creative_components cc
join mart_creative_performance p on p.creative_id = cc.creative_id
join mart_funnel f on f.creative_id = cc.creative_id
join creatives c on c.id = cc.creative_id
left join briefs b on b.id = c.brief_id
left join icps i on i.id = b.icp_id
group by cc.component_type, cc.component_ref, p.client_id, i.industry;

create view mart_hook_leaderboard with (security_invoker = true) as
select h.id as hook_id, h.text, h.hook_type, l.client_id, l.industry, l.creatives, l.impressions, l.link_ctr, l.link_ctr_lcb
from hooks h
join mart_component_leaderboard l on l.component_type = 'hook' and l.component_ref = h.id::text;

-- Cross-client benchmarks: suppressed under 3 clients (anonymisation).
create view mart_benchmarks with (security_invoker = true) as
select i.industry, cc.component_ref as family,
       count(distinct p.client_id) as clients, count(distinct p.creative_id) as creatives,
       percentile_cont(0.5) within group (order by p.link_ctr) as median_link_ctr,
       percentile_cont(0.5) within group (order by p.cost_per_link_click) as median_cost_per_link_click
from mart_creative_performance p
join creative_components cc on cc.creative_id = p.creative_id and cc.component_type = 'family'
join creatives c on c.id = p.creative_id
join briefs b on b.id = c.brief_id
join icps i on i.id = b.icp_id
where p.impressions >= 2000
group by i.industry, cc.component_ref
having count(distinct p.client_id) >= 3;

-- Kill/scale candidates. Missing config is an error state, never a permissive default.
-- CTR-stage rules per ad; conversion-stage rules gated on minimum expected counts
-- and on warehouse-verified bookings, never Meta-reported leads.
create view mart_kill_scale_candidates with (security_invoker = true) as
with cum as (
  select a.id as ad_entity_id, a.client_id, a.ad_id, a.status, a.creative_id,
         sum(m.impressions) as impressions, sum(m.link_clicks) as link_clicks, sum(m.spend) as spend,
         case when sum(m.impressions) > 0 then sum(m.link_clicks)::numeric / sum(m.impressions) end as link_ctr
  from ad_entities a join ad_metrics_latest m on m.ad_entity_id = a.id
  group by a.id
), booked as (
  select ad_entity_id, count(*) as booked_verified
  from leads where booked_verified_at is not null and coalesce(abuse_score,0) < 0.5
  group by ad_entity_id
), cfg as (
  select id as client_id,
         (config->'targets'->>'ctr_floor')::numeric        as ctr_floor,
         (config->'targets'->>'kill_impressions')::int     as kill_impressions,
         (config->'targets'->>'cpl_target')::numeric       as cpl_target
  from clients
)
select cum.*, coalesce(b.booked_verified,0) as booked_verified, cfg.ctr_floor, cfg.kill_impressions, cfg.cpl_target,
  case
    when cfg.ctr_floor is null or cfg.kill_impressions is null then 'config_missing'
    when cum.impressions >= cfg.kill_impressions and cum.link_ctr < cfg.ctr_floor then 'kill'
    when cfg.cpl_target is null then 'hold'
    -- conversion stage: expected bookings = spend / target; act only when expected >= 5
    when cum.spend >= 5 * cfg.cpl_target and coalesce(b.booked_verified,0) < (cum.spend / cfg.cpl_target) / 3 then 'kill'
    when coalesce(b.booked_verified,0) >= 5 and cum.spend / b.booked_verified <= cfg.cpl_target then 'scale'
    else 'hold'
  end as recommendation
from cum
join cfg on cfg.client_id = cum.client_id
left join booked b on b.ad_entity_id = cum.ad_entity_id
where cum.status = 'ACTIVE';

-- Trust streaks computed from actions, never stored. Counts only human, non-auto,
-- unchanged decisions since the last rejection. Thresholds live in clients.config.trust.
create view trust_streaks with (security_invoker = true) as
with decided as (
  select client_id, action_type, status, decided_at,
         (approved_payload is not null and approved_payload = proposal) as unchanged
  from actions
  where status in ('approved','rejected','applied','failed') and decision_channel in ('chat','token_post','app')
), last_reject as (
  select client_id, action_type, max(decided_at) as at from decided where status = 'rejected' group by 1,2
)
select d.client_id, d.action_type,
       count(*) filter (where d.status in ('approved','applied') and d.unchanged
                        and d.decided_at > coalesce(lr.at, '-infinity'::timestamptz)) as streak,
       (c.config->'trust'->d.action_type->>'threshold')::int as threshold,
       coalesce(c.config->'trust'->d.action_type->>'level','propose') as level
from decided d
join clients c on c.id = d.client_id
left join last_reject lr on lr.client_id = d.client_id and lr.action_type = d.action_type
group by d.client_id, d.action_type, c.config;

-- ---------- RLS scaffold ----------
alter table clients enable row level security;
alter table leads enable row level security;
alter table lead_contacts enable row level security;
alter table raw_ingest enable row level security;
alter table voc_phrases enable row level security;
alter table gate_scores enable row level security;
-- Roles and policies: 0002_roles.sql (worker_rw, executor, sam_admin, app, mcp_ro).
