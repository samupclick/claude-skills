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
