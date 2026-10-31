-- 0004: quiz funnel RPC (T7). Apply after 0003, as the role that applied 0001–0003 (the local
-- superuser; `postgres` on Supabase — both bypass RLS, which the functions below rely on).
--
-- The `app` role (quiz page, calendar webhook) writes leads only through these three functions.
-- They are SECURITY DEFINER so `app` needs no table grants of its own: 0002's direct insert on
-- leads / lead_contacts is revoked here, so "app inserts through the RPC only" (PRD FR-33, DR-4) is
-- enforced by Postgres, not by prose. `app` keeps `select (id, client_id, offer_id) on leads` from 0002.
--
-- PII rule (DR-4): name / email / phone go to lead_contacts only; the raw fbclid never reaches the
-- warehouse — the caller passes its sha256 (`quiz_start.p_fbclid_hash`), and the function refuses a
-- value that is not a 64-char hex digest. `booked_verified_at` is set only by `lead_booked`, which the
-- signature-verified calendar webhook calls (FR-34); a second call for the same lead is a no-op.
--
-- No new tables, no new columns. JSONB keys written here are listed in warehouse/schema-notes.md.

-- quiz_start: the prospect passed the consent step and saw question 1. Creates the `leads` row in
-- stage 'new' with attribution; the caller fires CAPI QuizStart only when tracking consent is true.
create or replace function quiz_start(
  p_client_slug   text,
  p_consent       jsonb,               -- {tracking, marketing, verbatim_use: bool, notice_version: text}; `at` is set here
  p_utm           jsonb default '{}',  -- {source, medium, campaign, content, term} as captured from the URL
  p_fbclid_hash   text default null,   -- sha256 hex of the fbclid, or null
  p_quiz_version  text default null,
  p_source        text default null
) returns table (lead_id uuid, client_id uuid, offer_id uuid, creative_id uuid, ad_entity_id uuid)
language plpgsql security definer set search_path = public as $$
declare
  v_client   clients%rowtype;
  v_offer_id uuid;
  v_creative uuid;
  v_ad       uuid;
  v_content  text := p_utm->>'content';
  v_lead     uuid;
begin
  select * into v_client from clients c where c.slug = p_client_slug;
  if not found then
    raise exception 'quiz_start: no client with slug %', p_client_slug using errcode = 'no_data_found';
  end if;
  if p_consent is null or jsonb_typeof(p_consent) <> 'object' then
    raise exception 'quiz_start: consent must be a JSON object' using errcode = 'check_violation';
  end if;
  if p_fbclid_hash is not null and p_fbclid_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'quiz_start: fbclid must arrive hashed (sha256 hex)' using errcode = 'check_violation';
  end if;
  select o.id into v_offer_id from offers o where o.client_id = v_client.id order by o.created_at limit 1;

  -- utm_content = creative_id (FR-32): resolve when it names one of this client's creatives.
  if v_content ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' then
    select cr.id into v_creative from creatives cr where cr.id = v_content::uuid and cr.client_id = v_client.id;
    if v_creative is not null then
      select ae.id into v_ad from ad_entities ae
      where ae.creative_id = v_creative and ae.client_id = v_client.id
      order by (ae.status = 'ACTIVE') desc, ae.launched_at desc nulls last, ae.created_at desc limit 1;
    end if;
  end if;

  insert into leads (client_id, offer_id, ad_entity_id, creative_id, source, utm, fbclid_hash, quiz_version,
                     consent, stage, stage_changed_at, purge_after)
  values (v_client.id, v_offer_id, v_ad, v_creative, p_source, coalesce(p_utm, '{}'::jsonb), p_fbclid_hash, p_quiz_version,
          p_consent || jsonb_build_object('at', to_jsonb(now())), 'new', now(), now() + interval '24 months')
  returning id into v_lead;
  return query select v_lead, v_client.id, v_offer_id, v_creative, v_ad;
end $$;

-- quiz_complete: the last question was answered and the contact form submitted. Answers and the score
-- go to `leads`; name / email / phone go to `lead_contacts` only. Returns `transitioned` = true the
-- first time (stage new → completed) so the caller fires CAPI QuizComplete exactly once per lead.
create or replace function quiz_complete(
  p_lead_id             uuid,
  p_answers             jsonb,   -- {question_id: chosen option}, validated against offers.quiz_config by the caller
  p_qualification_score numeric,
  p_email               text,
  p_name                text default null,
  p_phone               text default null
) returns table (transitioned boolean, tracking_consent boolean, client_id uuid, creative_id uuid)
language plpgsql security definer set search_path = public as $$
declare
  v_lead leads%rowtype;
begin
  select * into v_lead from leads l where l.id = p_lead_id;
  if not found then
    raise exception 'quiz_complete: no lead %', p_lead_id using errcode = 'no_data_found';
  end if;
  if p_answers is null or jsonb_typeof(p_answers) <> 'object' then
    raise exception 'quiz_complete: answers must be a JSON object' using errcode = 'check_violation';
  end if;
  if p_email is null or p_email = '' then
    raise exception 'quiz_complete: email is required' using errcode = 'check_violation';
  end if;
  if v_lead.stage <> 'new' then
    return query select false, coalesce((v_lead.consent->>'tracking')::boolean, false), v_lead.client_id, v_lead.creative_id;
    return;
  end if;
  update leads set quiz_answers = p_answers, qualification_score = p_qualification_score,
                   stage = 'completed', stage_changed_at = now(), purge_after = now() + interval '24 months'
  where id = p_lead_id;
  insert into lead_contacts (lead_id, email, name, phone) values (p_lead_id, p_email, p_name, p_phone)
  on conflict (lead_id) do update set email = excluded.email, name = excluded.name, phone = excluded.phone;
  return query select true, coalesce((v_lead.consent->>'tracking')::boolean, false), v_lead.client_id, v_lead.creative_id;
end $$;

-- lead_booked: called by the calendar webhook after its signature check (FR-34). Sets
-- booked_verified_at once; a retry returns `updated` = false so CAPI Schedule fires once per lead.
create or replace function lead_booked(
  p_lead_id   uuid,
  p_booked_at timestamptz default now()
) returns table (updated boolean, tracking_consent boolean, client_id uuid, creative_id uuid)
language plpgsql security definer set search_path = public as $$
declare
  v_lead leads%rowtype;
begin
  select * into v_lead from leads l where l.id = p_lead_id;
  if not found then
    raise exception 'lead_booked: no lead %', p_lead_id using errcode = 'no_data_found';
  end if;
  if v_lead.booked_verified_at is not null then
    return query select false, coalesce((v_lead.consent->>'tracking')::boolean, false), v_lead.client_id, v_lead.creative_id;
    return;
  end if;
  update leads set booked_verified_at = coalesce(p_booked_at, now()), stage = 'booked', stage_changed_at = now()
  where id = p_lead_id;
  return query select true, coalesce((v_lead.consent->>'tracking')::boolean, false), v_lead.client_id, v_lead.creative_id;
end $$;

-- quiz_config: what the page needs to render (questions, notice version, calendar link) — no PII, no
-- targets. Returned as one JSON object so `app` needs no select on clients / offers.
create or replace function quiz_config(p_client_slug text) returns jsonb
language sql security definer stable set search_path = public as $$
  select jsonb_build_object(
    'client_slug', c.slug,
    'offer_id', o.id,
    'offer_name', o.name,
    'promise', o.promise,
    'calendar_url', o.calendar_url,
    'funnel_host', o.funnel_host,
    'quiz_config', coalesce(o.quiz_config, '{}'::jsonb)
  )
  from clients c
  left join lateral (select * from offers o where o.client_id = c.id order by o.created_at limit 1) o on true
  where c.slug = p_client_slug;
$$;

revoke all on function quiz_start(text, jsonb, jsonb, text, text, text) from public;
revoke all on function quiz_complete(uuid, jsonb, numeric, text, text, text) from public;
revoke all on function lead_booked(uuid, timestamptz) from public;
revoke all on function quiz_config(text) from public;
grant execute on function quiz_start(text, jsonb, jsonb, text, text, text) to app;
grant execute on function quiz_complete(uuid, jsonb, numeric, text, text, text) to app;
grant execute on function lead_booked(uuid, timestamptz) to app;
grant execute on function quiz_config(text) to app;

-- RPC only: the direct inserts 0002 granted to app are withdrawn now that the functions exist.
revoke insert on leads, lead_contacts from app;
