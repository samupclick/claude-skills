-- Growth Warehouse v1 schema (Postgres 15+, Supabase)
-- Apply as warehouse/migrations/0001_init.sql
-- Conventions: uuid pks, client_id on every entity row, created_at everywhere,
-- metrics tables append-only (unique on entity + day), embeddings 1536-d.

create extension if not exists "pgcrypto";
create extension if not exists vector;

-- ---------- RAW ----------
create table raw_ingest (
  id           uuid primary key default gen_random_uuid(),
  source       text not null,            -- meta_insights | meta_ad_library | scrapecreators_tiktok | x_posts | reddit | g2 | gong | quiz
  client_id    uuid,                     -- null for market-wide pulls
  external_id  text,
  fetched_at   timestamptz not null default now(),
  payload      jsonb not null
);
create index on raw_ingest (source, fetched_at desc);
create index on raw_ingest (client_id, source);

-- ---------- ENTITIES ----------
create table clients (
  id           uuid primary key default gen_random_uuid(),
  name         text not null,
  slug         text not null unique,
  site         text,
  industry     text,
  config       jsonb not null default '{}',   -- mirrors config/clients/*.json
  created_at   timestamptz not null default now()
);

create table offers (
  id           uuid primary key default gen_random_uuid(),
  client_id    uuid not null references clients(id),
  name         text not null,
  promise      text,
  price_anchor text,
  proof_points text[] default '{}',
  landing_url  text,
  created_at   timestamptz not null default now()
);

create table icps (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references clients(id),
  label         text not null,
  role          text,
  company_type  text,
  industry      text,                    -- benchmark key
  geo           text[] default '{}',
  size_band     text,                    -- e.g. 50-500
  pains         text[] default '{}',
  outcomes      text[] default '{}',
  created_at    timestamptz not null default now()
);

create table voc_phrases (
  id           uuid primary key default gen_random_uuid(),
  client_id    uuid references clients(id),
  icp_id       uuid references icps(id),
  phrase       text not null,
  category     text not null check (category in ('pain','outcome','objection','identity','trigger')),
  source       text,                     -- reddit | g2 | gong | intercom | quiz
  source_url   text,
  frequency    int not null default 1,
  quotes       text[] default '{}',
  embedding    vector(1536),
  created_at   timestamptz not null default now()
);

create table patterns (
  id               uuid primary key default gen_random_uuid(),
  client_id        uuid references clients(id),   -- null = external / market
  origin           text not null check (origin in ('external','internal')),
  format           text not null,        -- job_photo_bubble | testimonial_card | screenshot | ugly_ad | carousel | thread ...
  hook_type        text,                 -- pain | outcome | proof | contrarian | identity | question | number
  angle            text,
  visual_structure text,
  copy_structure   text,
  source_brand     text,
  source_url       text,
  days_running     int,
  proven           boolean not null default false,
  evidence         jsonb default '{}',   -- for internal: creative ids + metrics summary
  embedding        vector(1536),
  created_at       timestamptz not null default now()
);

create table hooks (
  id           uuid primary key default gen_random_uuid(),
  client_id    uuid references clients(id),
  text         text not null,
  hook_type    text,
  pattern_id   uuid references patterns(id),
  embedding    vector(1536),
  created_at   timestamptz not null default now()
);

create table experiments (
  id             uuid primary key default gen_random_uuid(),
  client_id      uuid not null references clients(id),
  offer_id       uuid references offers(id),
  name           text not null,          -- e.g. batch-001
  variable       text,                   -- what is varied: angle | format | hook | offer
  primary_metric text not null default 'link_ctr',
  started_at     timestamptz,
  ended_at       timestamptz,
  result         jsonb default '{}',
  created_at     timestamptz not null default now()
);

create table briefs (
  id             uuid primary key default gen_random_uuid(),
  client_id      uuid not null references clients(id),
  experiment_id  uuid references experiments(id),
  offer_id       uuid references offers(id),
  icp_id         uuid references icps(id),
  angle          text not null,
  format         text not null,
  hook_id        uuid references hooks(id),
  voc_phrase_ids uuid[] default '{}',
  visual_spec    text,
  cta            text,
  spec           jsonb default '{}',
  created_at     timestamptz not null default now()
);

create table creatives (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references clients(id),
  brief_id      uuid references briefs(id),
  experiment_id uuid references experiments(id),
  status        text not null default 'draft' check (status in ('draft','gated','approved','live','paused','killed','archived')),
  primary_text  text,
  headline      text,
  description   text,
  template      text,
  asset_urls    text[] default '{}',
  sizes         text[] default '{}',
  version       int not null default 1,
  created_at    timestamptz not null default now()
);

-- Attribution key: what a creative is made of.
create table creative_components (
  creative_id    uuid not null references creatives(id) on delete cascade,
  component_type text not null check (component_type in ('hook','angle','format','template','voc_phrase','cta','landing_page','offer')),
  component_ref  text not null,          -- uuid or enum value as text
  primary key (creative_id, component_type, component_ref)
);
create index on creative_components (component_type, component_ref);

create table gate_scores (
  id            uuid primary key default gen_random_uuid(),
  creative_id   uuid not null references creatives(id) on delete cascade,
  attempt       int not null default 1,
  scores        jsonb not null,          -- {hook:4, clarity:5, icp_fit:3, voc:4, single_cta:5, legibility:4}
  avg_score     numeric(3,2) not null,
  policy_flags  text[] default '{}',
  hard_blocks   text[] default '{}',
  passed        boolean not null,
  feedback      jsonb default '{}',
  scored_by     text not null default 'agent',
  created_at    timestamptz not null default now()
);

create table ad_entities (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references clients(id),
  creative_id   uuid references creatives(id),
  platform      text not null default 'meta',
  campaign_id   text,
  adset_id      text,
  ad_id         text not null,
  objective     text,
  optimization_event text,
  status        text,
  launched_at   timestamptz,
  created_at    timestamptz not null default now(),
  unique (platform, ad_id)
);

create table ad_metrics_daily (
  ad_entity_id  uuid not null references ad_entities(id),
  day           date not null,
  impressions   bigint default 0,
  reach         bigint default 0,
  clicks        bigint default 0,
  link_clicks   bigint default 0,
  spend         numeric(12,2) default 0,
  leads         int default 0,
  schedules     int default 0,
  video_3s      bigint,
  frequency     numeric(6,3),
  link_ctr      numeric(8,5) generated always as (case when impressions > 0 then link_clicks::numeric / impressions else null end) stored,
  cpm           numeric(10,4) generated always as (case when impressions > 0 then spend / impressions * 1000 else null end) stored,
  cpl           numeric(10,4) generated always as (case when leads > 0 then spend / leads else null end) stored,
  fetched_at    timestamptz not null default now(),
  primary key (ad_entity_id, day)
);

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
  impressions   bigint default 0,
  engagements   bigint default 0,
  reposts       int default 0,
  replies       int default 0,
  saves         int default 0,
  profile_clicks int default 0,
  link_clicks   int default 0,
  follows       int default 0,
  engagement_rate numeric(8,5) generated always as (case when impressions > 0 then engagements::numeric / impressions else null end) stored,
  fetched_at    timestamptz not null default now(),
  primary key (post_id, day)
);

create table leads (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references clients(id),
  offer_id      uuid references offers(id),
  ad_entity_id  uuid references ad_entities(id),
  post_id       uuid references posts(id),
  creative_id   uuid references creatives(id),
  source        text,                    -- meta | x | linkedin | organic_search | referral
  utm           jsonb default '{}',
  fbclid        text,
  email         text,                    -- PII: restricted role only
  phone         text,                    -- PII: restricted role only
  quiz_answers  jsonb default '{}',
  stage         text not null default 'new' check (stage in ('new','booked','showed','qualified','proposal','closed_won','closed_lost')),
  value         numeric(12,2),
  stage_changed_at timestamptz,
  created_at    timestamptz not null default now()
);
create index on leads (client_id, stage);

create table actions (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid not null references clients(id),
  ad_entity_id  uuid references ad_entities(id),
  action        text not null check (action in ('kill','scale','relaunch','hold')),
  rule          text not null,           -- e.g. ctr_floor_2000imp
  evidence      jsonb not null,          -- metrics snapshot at decision time
  approved_by   text,                    -- human handle or 'auto'
  applied       boolean not null default false,
  applied_at    timestamptz,
  created_at    timestamptz not null default now()
);

create table learnings (
  id            uuid primary key default gen_random_uuid(),
  client_id     uuid references clients(id),   -- null = global
  icp_id        uuid references icps(id),
  scope         text not null check (scope in ('client','icp','global')),
  hypothesis    text not null,
  component_type text,
  component_ref text,
  evidence      jsonb not null default '{}',   -- {experiments:[...], n:..., effect:..., baseline:...}
  confidence    numeric(3,2),
  status        text not null default 'proposed' check (status in ('proposed','supported','refuted','retired')),
  embedding     vector(1536),
  created_by    text not null default 'agent',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- ---------- MARTS ----------
create view mart_creative_performance as
select c.id as creative_id, c.client_id, c.experiment_id, c.status, c.template,
       sum(m.impressions) as impressions, sum(m.link_clicks) as link_clicks, sum(m.spend) as spend,
       sum(m.leads) as leads, sum(m.schedules) as schedules,
       case when sum(m.impressions) > 0 then sum(m.link_clicks)::numeric / sum(m.impressions) end as link_ctr,
       case when sum(m.leads) > 0 then sum(m.spend) / sum(m.leads) end as cpl,
       min(m.day) as first_day, max(m.day) as last_day
from creatives c
join ad_entities a on a.creative_id = c.id
join ad_metrics_daily m on m.ad_entity_id = a.id
group by c.id;

create view mart_component_leaderboard as
select cc.component_type, cc.component_ref, p.client_id, i.industry,
       count(distinct p.creative_id) as creatives,
       sum(p.impressions) as impressions, sum(p.link_clicks) as link_clicks, sum(p.spend) as spend, sum(p.leads) as leads,
       case when sum(p.impressions) > 0 then sum(p.link_clicks)::numeric / sum(p.impressions) end as link_ctr,
       case when sum(p.leads) > 0 then sum(p.spend) / sum(p.leads) end as cpl
from creative_components cc
join mart_creative_performance p on p.creative_id = cc.creative_id
left join briefs b on b.id = (select brief_id from creatives where id = cc.creative_id)
left join icps i on i.id = b.icp_id
group by cc.component_type, cc.component_ref, p.client_id, i.industry;

create view mart_hook_leaderboard as
select h.id as hook_id, h.text, h.hook_type, l.client_id, l.industry, l.creatives, l.impressions, l.link_ctr, l.cpl
from hooks h
join mart_component_leaderboard l on l.component_type = 'hook' and l.component_ref = h.id::text;

create view mart_benchmarks as
select i.industry, cc.component_ref as format,
       count(distinct p.client_id) as clients, count(distinct p.creative_id) as creatives,
       percentile_cont(0.5) within group (order by p.link_ctr) as median_link_ctr,
       percentile_cont(0.5) within group (order by p.cpl) as median_cpl
from mart_creative_performance p
join creative_components cc on cc.creative_id = p.creative_id and cc.component_type = 'format'
join creatives c on c.id = p.creative_id
join briefs b on b.id = c.brief_id
join icps i on i.id = b.icp_id
where p.impressions >= 2000
group by i.industry, cc.component_ref;

create view mart_funnel as
select c.id as creative_id, c.client_id, c.experiment_id,
       count(l.id) filter (where l.stage <> 'closed_lost') as leads,
       count(l.id) filter (where l.stage in ('booked','showed','qualified','proposal','closed_won')) as booked,
       count(l.id) filter (where l.stage in ('qualified','proposal','closed_won')) as qualified,
       count(l.id) filter (where l.stage = 'closed_won') as closed_won,
       coalesce(sum(l.value) filter (where l.stage = 'closed_won'), 0) as revenue
from creatives c
left join leads l on l.creative_id = c.id
group by c.id;

-- Daily kill/scale candidates. Thresholds read from clients.config->'targets'.
create view mart_kill_scale_candidates as
with cum as (
  select a.id as ad_entity_id, a.client_id, a.ad_id, a.status,
         sum(m.impressions) as impressions, sum(m.link_clicks) as link_clicks,
         sum(m.spend) as spend, sum(m.leads) as leads,
         case when sum(m.impressions) > 0 then sum(m.link_clicks)::numeric / sum(m.impressions) end as link_ctr,
         case when sum(m.leads) > 0 then sum(m.spend) / sum(m.leads) end as cpl
  from ad_entities a join ad_metrics_daily m on m.ad_entity_id = a.id
  group by a.id
)
select cum.*, cl.config->'targets' as targets,
  case
    when cum.impressions >= coalesce((cl.config->'targets'->>'kill_impressions')::int, 2000)
     and cum.link_ctr < coalesce((cl.config->'targets'->>'ctr_floor')::numeric, 0.01) then 'kill'
    when cum.leads >= 5 and cum.cpl <= coalesce((cl.config->'targets'->>'cpl')::numeric, 1e9) then 'scale'
    when cum.spend >= 3 * coalesce((cl.config->'targets'->>'cpl')::numeric, 1e9)
     and cum.cpl > 2 * coalesce((cl.config->'targets'->>'cpl')::numeric, 1e9) then 'kill'
    else 'hold'
  end as recommendation
from cum join clients cl on cl.id = cum.client_id
where cum.status = 'ACTIVE';

-- ---------- RLS scaffold ----------
alter table clients enable row level security;
alter table leads enable row level security;
-- Policies are added in 0002 once service roles are defined. Service role bypasses RLS for pipeline scripts.
