# Warehouse schema notes

Migrations are the only way the schema changes (PRD DR-1, SKILL.md §4 rule 9). New fields go into
the owning entity's JSONB column and are listed here, never added as ad-hoc columns.

## Migrations (apply in order; `scripts/dev_db.sh` applies every numbered file once)

| File | Purpose |
|------|---------|
| `schema.sql` (0001) | Tables, views, marts, RLS scaffold |
| `0002_roles.sql` | Roles `worker_rw`, `executor`, `sam_admin`, `app`, `mcp_ro`; grants; `actions_guard` trigger; `check_daily_cap()`; baseline RLS policies |
| `0003_phase0_grants.sql` | Column grants only, for phase 0 workers: `worker_rw` may update `creatives (status, asset_urls, sizes, version)`, `briefs (spec)`, `campaigns (active_lever, active_lever_reason, active_lever_since)` |

## JSONB keys in use

| Column | Key | Written by | Meaning |
|--------|-----|-----------|---------|
| `clients.config` | whole file | `scripts/seed.py` | `config/clients/<slug>.json` copied as-is (`_status` marks it DRAFT) |
| `runs.counts` | `families`, `clients`, `offers`, `icps` | `scripts/seed.py` | rows inserted by the seed |
| `runs.counts` | `<any>` | `warehouse.client.run()` | per-worker counters accumulated with `Run.count()`; each worker documents its keys in its ticket |
| `runs.counts` | `sources_ok`, `sources_failed`, `warnings` (lists) | `scripts/pull_inspo.py` | per-source outcome of one intel run (FR-8); `warnings` holds the retried-then-failed messages. Two consecutive `sources_failed` entries for one source block `plan batch` (`warehouse.client.blocked_sources`) |
| `runs.counts` | `acknowledged` (list) | `scripts/pull_inspo.py --acknowledge <source>` | Sam's acknowledgement (SKILL.md §7); clears the FR-8 block for that source |
| `runs.counts` | `ads_fetched`, `raw_ingest_new`, `raw_ingest_seen`, `images_stored`, `patterns_new`, `patterns_seen`, `patterns_promoted`, `patterns_proven`, `patterns_candidate`, `ads_skipped` | `scripts/pull_inspo.py` | intel run counters |
| `raw_ingest.payload` | `backend`, `brand`, `ad` | `scripts/pull_inspo.py` (`source='ad_library'`) | the normalised ad from the inspo adapter, `ad.raw` being the vendor row; `dedup_key = ad_library:<ad_id>:<sha256(raw)[:16]>` |
| `patterns.recipe` | `format_layer` {`family`, `visual_structure`, `copy_structure`, `copy_length`, `hook_type`} | `scripts/pull_inspo.py` | the format layer carried verbatim into replicas (ARCH §4); `family` equals `patterns.family` |
| `patterns.recipe` | `offer_layer` {} | `scripts/pull_inspo.py` (empty), planner (T4) | fixed per offer from `offers.offer_layer` |
| `patterns.recipe` | `decomposition` {`variant`, `angle`, `hook_text`, `confidence`, `backend`} | `scripts/pull_inspo.py` | the model output behind the row; `backend` is `claude` or `fixture` |
| `patterns.recipe` | `proven_by` [`days_running` \| `concurrent_variants`] | `scripts/pull_inspo.py` | which FR-6 branches held when the row was written (empty for candidates) |
| `patterns.recipe` | `source` {`backend`, `ad_id`, `brand`, `page_name`, `raw_ingest_id`, `dedup_key`, `display_format`, `is_active`, `end_date`, `images` [{`cdn_url`, `storage_url`}], `text` {`title`, `body`, `cta`}} | `scripts/pull_inspo.py` | provenance; `ad_id` is the re-run dedup key for patterns; every `storage_url` is our copy of the CDN image (FR-5); `text` is untrusted (SKILL.md §4 rule 7) |
