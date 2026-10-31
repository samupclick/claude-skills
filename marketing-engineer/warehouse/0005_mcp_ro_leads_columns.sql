-- 0005: make 0002's PII revoke for mcp_ro effective (DR-4). Found by T7's DR-4 test.
--
-- 0002 grants `select on all tables` to mcp_ro and then revokes select on three leads columns. In
-- Postgres a column-level revoke is a no-op while a table-level privilege stands ("If a table-level
-- privilege is held, revoking the same privilege for individual columns will have no effect"), so
-- mcp_ro could still read leads.quiz_answers / consent / fbclid_hash. Replace the table-level grant
-- with a column list that leaves those three out. No new tables or columns; no other role changes.

revoke select on leads from mcp_ro;
grant select (id, client_id, offer_id, ad_entity_id, post_id, creative_id, source, utm, quiz_version,
              qualification_score, stage, booked_verified_at, stage_changed_at, nurture_sequence,
              instantly_lead_id, value, abuse_score, purge_after, created_at) on leads to mcp_ro;
