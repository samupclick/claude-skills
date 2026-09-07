"""Growth Warehouse client for every worker script (T1).

- `connect(role, job=...)`: a psycopg connection as the role for the job, from `WAREHOUSE_URL_<ROLE>` in
  the environment (`.env` is loaded first; a missing variable is reported by name, never by value).
- `insert(conn, table, **values)` and `insert_<table>(conn, **values)` for every table in schema.sql:
  columns are checked against the live catalog, JSONB values are wrapped, every parameter is cast to its
  column type, and the full inserted row comes back as a dict (`returning *`).
- `run(conn, worker, client_id)`: the `runs` row every invocation must open and close (SKILL.md §0, §7).
- `where_are_we(conn, slug)` (SKILL.md §2) and the two read-before-planning queries (SKILL.md §4.2), verbatim.

Rules this file enforces by construction: no vendor SDK, no Meta write, no email; only inserts and the
column updates 0002/0003 grant to the role in use. The executor is the only script that may pass
role="executor" (NFR-1); tests grep for it.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters.env import ME_DIR, load_env, require  # noqa: E402

__all__ = [
    "ROLES", "TABLES", "UnknownRole", "UnknownTable", "UnknownColumn", "Jsonb", "Run",
    "connect", "migration_files", "insert", "run", "client_by_slug",
    "where_are_we", "format_where_are_we", "learnings_before_planning", "leaderboard_before_planning",
    "blocked_sources",
]

Connection = psycopg.Connection[dict[str, Any]]

# role name → env var. `admin` is the superuser string dev_db.sh uses locally; `sam_admin` is the role
# Sam's shell uses (SKILL.md §1). Workers use `worker`; only scripts/apply_actions.py uses `executor`.
ROLES: dict[str, str] = {
    "worker": "WAREHOUSE_URL_WORKER",
    "executor": "WAREHOUSE_URL_EXECUTOR",
    "admin": "WAREHOUSE_URL_ADMIN",
    "sam_admin": "WAREHOUSE_URL_SAM_ADMIN",
    "app": "WAREHOUSE_URL_APP",
    "mcp_ro": "WAREHOUSE_URL_MCP_RO",
}

# Every base table in warehouse/schema.sql, in file order. A test asserts this equals the live catalog.
TABLES: tuple[str, ...] = (
    "raw_ingest", "clients", "offers", "icps", "voc_phrases", "families", "patterns", "hooks",
    "experiments", "briefs", "selections", "creatives", "creative_components", "gate_scores",
    "campaigns", "ad_entities", "ad_metrics_daily", "account_spend_hourly", "posts", "post_metrics_daily",
    "leads", "lead_contacts", "erasure_requests", "actions", "runs", "learnings",
)


class UnknownRole(ValueError):
    """`connect()` was asked for a role that has no WAREHOUSE_URL_* variable (there is no service role)."""


class UnknownTable(ValueError):
    """`insert()` was asked for a table that is not in schema.sql."""


class UnknownColumn(ValueError):
    """`insert()` was given a column the table does not have, or one Postgres generates itself."""


# ---------- connections ----------

def connect(role: str = "worker", *, job: str | None = None, autocommit: bool = False) -> Connection:
    """Open a connection as `role` from its env var. Rows come back as dicts. Caller owns commit/rollback."""
    load_env()
    if role not in ROLES:
        raise UnknownRole(f"role {role!r} is not one of {sorted(ROLES)}; workers use 'worker'")
    var = ROLES[role]
    url = require(job or role, var)[var]
    return psycopg.connect(url, row_factory=dict_row, autocommit=autocommit)


def migration_files() -> list[Path]:
    """Every migration in warehouse/, in apply order: schema.sql (0001) then NNNN_<slug>.sql by prefix.
    Same rule as scripts/dev_db.sh; the test fixture and the go-live swap (T13) apply this list."""
    wh = ME_DIR / "warehouse"
    numbered = sorted((p for p in wh.glob("[0-9][0-9][0-9][0-9]_*.sql")), key=lambda p: p.name[:4])
    return [wh / "schema.sql", *numbered]


# ---------- inserts ----------

_COLUMNS: dict[str, dict[str, tuple[str, bool]]] = {}   # table → column → (sql type, generated)

_COLUMNS_SQL = """
select a.attname as name, format_type(a.atttypid, a.atttypmod) as type, a.attgenerated <> '' as generated
from pg_attribute a
join pg_class c on c.oid = a.attrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relname = %s and a.attnum > 0 and not a.attisdropped
order by a.attnum
"""


def columns(conn: Connection, table: str) -> dict[str, tuple[str, bool]]:
    """Column → (type, generated) from the live catalog, cached per process (the schema only changes by migration)."""
    if table not in TABLES:
        raise UnknownTable(f"{table!r} is not a table in warehouse/schema.sql")
    if table not in _COLUMNS:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(_COLUMNS_SQL, (table,)).fetchall()
        _COLUMNS[table] = {r["name"]: (r["type"], r["generated"]) for r in rows}
    return _COLUMNS[table]


def _adapt(value: Any, sql_type: str) -> Any:
    if sql_type == "jsonb" and isinstance(value, (dict, list)):
        return Jsonb(value)
    return value


def insert(conn: Connection, table: str, **values: Any) -> dict[str, Any]:
    """Insert one row and return it in full. Unknown or generated columns raise before touching the database.
    Dicts and lists bound for jsonb columns are wrapped; every parameter is cast to its column type, so
    uuid[] and numeric columns accept plain Python lists and Decimals. Does not commit."""
    cols = columns(conn, table)
    bad = [c for c in values if c not in cols or cols[c][1]]
    if bad:
        raise UnknownColumn(f"{table}.{bad[0]} is not an insertable column" + (" (generated)" if bad[0] in cols else ""))
    if not values:
        query = sql.SQL("insert into {} default values returning *").format(sql.Identifier(table))
        params: list[Any] = []
    else:
        names = list(values)
        query = sql.SQL("insert into {} ({}) values ({}) returning *").format(
            sql.Identifier(table),
            sql.SQL(", ").join(sql.Identifier(c) for c in names),
            sql.SQL(", ").join(sql.SQL("%s::") + sql.SQL(cols[c][0]) for c in names),
        )
        params = [_adapt(values[c], cols[c][0]) for c in names]
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(query, params).fetchone()


def insert_raw_ingest(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "raw_ingest", **v)
def insert_clients(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "clients", **v)
def insert_offers(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "offers", **v)
def insert_icps(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "icps", **v)
def insert_voc_phrases(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "voc_phrases", **v)
def insert_families(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "families", **v)
def insert_patterns(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "patterns", **v)
def insert_hooks(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "hooks", **v)
def insert_experiments(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "experiments", **v)
def insert_briefs(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "briefs", **v)
def insert_selections(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "selections", **v)
def insert_creatives(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "creatives", **v)
def insert_creative_components(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "creative_components", **v)
def insert_gate_scores(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "gate_scores", **v)
def insert_campaigns(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "campaigns", **v)
def insert_ad_entities(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "ad_entities", **v)
def insert_ad_metrics_daily(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "ad_metrics_daily", **v)
def insert_account_spend_hourly(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "account_spend_hourly", **v)
def insert_posts(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "posts", **v)
def insert_post_metrics_daily(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "post_metrics_daily", **v)
def insert_leads(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "leads", **v)
def insert_lead_contacts(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "lead_contacts", **v)
def insert_erasure_requests(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "erasure_requests", **v)
def insert_actions(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "actions", **v)
def insert_runs(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "runs", **v)
def insert_learnings(conn: Connection, **v: Any) -> dict[str, Any]: return insert(conn, "learnings", **v)


# ---------- runs ----------

@dataclass
class Run:
    """The open `runs` row. Accumulate `counts` with `count()`; set `tokens_used` / `api_calls` as you go."""
    id: UUID
    worker: str
    client_id: UUID | None
    counts: dict[str, int] = field(default_factory=dict)
    tokens_used: int | None = None
    api_calls: int | None = None

    def count(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n


@contextmanager
def run(conn: Connection, worker: str, client_id: UUID | str | None = None) -> Iterator[Run]:
    """Open a `runs` row (committed at once, so a crash leaves it `running`, SKILL.md §7) and close it:
    `status='ok'` with counts and the body's work committed on normal exit; on an exception the body's
    uncommitted work is rolled back, the row gets `status='failed'` and `error`, and the exception
    propagates. `finished_at` is set either way."""
    row = insert(conn, "runs", worker=worker, client_id=client_id)
    conn.commit()
    r = Run(id=row["id"], worker=worker, client_id=row["client_id"])
    try:
        yield r
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"[:2000]
        try:
            conn.rollback()
            conn.execute(
                "update runs set status='failed', finished_at=now(), error=%s, counts=%s, tokens_used=%s, api_calls=%s where id=%s",
                (error, Jsonb(r.counts), r.tokens_used, r.api_calls, r.id),
            )
            conn.commit()
        except Exception as close_exc:  # the connection is gone: the row stays `running` (SKILL.md §7) and the cause propagates
            exc.add_note(f"runs row {r.id} could not be closed ({type(close_exc).__name__}); it stays 'running'")
        raise
    conn.execute(
        "update runs set status='ok', finished_at=now(), counts=%s, tokens_used=%s, api_calls=%s where id=%s",
        (Jsonb(r.counts), r.tokens_used, r.api_calls, r.id),
    )
    conn.commit()


# ---------- reads ----------

def client_by_slug(conn: Connection, slug: str) -> dict[str, Any] | None:
    return conn.execute("select * from clients where slug = %s", (slug,)).fetchone()


# SKILL.md §2, verbatim ($1 → %s). A test checks the text against SKILL.md.
WHERE_ARE_WE_SQL = """
select c.slug, c.paused, c.daily_cap, c.currency,
  (select count(*) from patterns where status='proven')                                 as proven_patterns,
  (select count(*) from voc_phrases where client_id=c.id)                                as voc_phrases,
  (select name from experiments where client_id=c.id order by created_at desc limit 1)  as latest_batch,
  (select capacity from experiments where client_id=c.id order by created_at desc limit 1) as capacity,
  (select jsonb_object_agg(status, n) from (select status, count(*) n from creatives where client_id=c.id group by 1) s) as creatives_by_status,
  (select count(*) from actions where client_id=c.id and status='proposed')             as actions_waiting,
  (select count(*) from actions where client_id=c.id and status='applying')             as actions_stuck,
  (select count(*) from ad_entities where client_id=c.id and status='ACTIVE')           as ads_active,
  (select count(*) from mart_kill_scale_candidates k where k.client_id=c.id and recommendation<>'hold') as kill_scale_candidates,
  (select count(*) from learnings where client_id=c.id and status='proposed')           as learnings_proposed,
  (select max(started_at) from runs where client_id=c.id and status='failed')           as last_failure
from clients c where c.slug = %s;
"""

# SKILL.md §4 rule 2, verbatim: run both before `plan batch`.
LEARNINGS_BEFORE_PLANNING_SQL = """
select hypothesis, status, effect_size, posterior from learnings
where (client_id=%s or scope='global') and status in ('proposed','supported','global') order by status desc, posterior desc nulls last;
"""
LEADERBOARD_BEFORE_PLANNING_SQL = """
select component_type, component_ref, creatives, link_ctr, link_ctr_lcb from mart_component_leaderboard
where client_id=%s and creatives>=3 order by link_ctr_lcb desc;
"""


def where_are_we(conn: Connection, slug: str = "upclicklabs") -> dict[str, Any] | None:
    """The §2 row for one client, or None when the slug does not exist."""
    return conn.execute(WHERE_ARE_WE_SQL, (slug,)).fetchone()


def format_where_are_we(row: dict[str, Any]) -> str:
    """The §2 row as the short two-column table the skill prints, plus the `actions_stuck` stop line."""
    width = max(len(k) for k in row)
    lines = [f"{k.ljust(width)}  {_cell(v)}" for k, v in row.items()]
    if row.get("actions_stuck"):
        lines.append(f"actions_stuck = {row['actions_stuck']}: stop; only the executor's reconcile mode may touch `applying` rows.")
    return "\n".join(lines)


def _cell(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, dict):
        return ", ".join(f"{k}={n}" for k, n in sorted(v.items())) or "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


# FR-8 / SKILL.md §7: a source whose last two intel outcomes are both failures blocks `plan batch` until Sam
# acknowledges it. Outcomes are the `runs.counts` lists the intel worker writes (`sources_ok`, `sources_failed`)
# plus `acknowledged` (written by `scripts/pull_inspo.py --acknowledge <source>`), newest first per source.
BLOCKED_SOURCES_SQL = """
with outcomes as (
  select r.started_at, s.source, 'failed' as outcome
    from runs r, jsonb_array_elements_text(coalesce(r.counts->'sources_failed', '[]'::jsonb)) s(source)
   where r.worker = 'intel'
  union all
  select r.started_at, s.source, 'ok'
    from runs r, jsonb_array_elements_text(coalesce(r.counts->'sources_ok', '[]'::jsonb)) s(source)
   where r.worker = 'intel'
  union all
  select r.started_at, s.source, 'acknowledged'
    from runs r, jsonb_array_elements_text(coalesce(r.counts->'acknowledged', '[]'::jsonb)) s(source)
   where r.worker = 'intel'
), ranked as (
  select source, outcome, row_number() over (partition by source order by started_at desc) as rn from outcomes
)
select source from ranked where rn <= 2
group by source having count(*) = 2 and bool_and(outcome = 'failed')
order by source;
"""


def blocked_sources(conn: Connection) -> list[str]:
    """Sources (brand names) with two consecutive intel failures and no acknowledgement since (FR-8).
    The planner refuses `plan batch` naming these."""
    return [row["source"] for row in conn.execute(BLOCKED_SOURCES_SQL).fetchall()]


def learnings_before_planning(conn: Connection, client_id: UUID | str) -> list[dict[str, Any]]:
    return conn.execute(LEARNINGS_BEFORE_PLANNING_SQL, (client_id,)).fetchall()


def leaderboard_before_planning(conn: Connection, client_id: UUID | str) -> list[dict[str, Any]]:
    return conn.execute(LEADERBOARD_BEFORE_PLANNING_SQL, (client_id,)).fetchall()


def main(argv: list[str]) -> int:
    """`python3 warehouse/client.py status [slug]`: print the §2 table as worker_rw. Reads only (SKILL.md §3)."""
    if not argv or argv[0] != "status":
        print("usage: warehouse/client.py status [client-slug]", file=sys.stderr)
        return 2
    slug = argv[1] if len(argv) > 1 else "upclicklabs"
    with connect("worker", job="status") as conn:
        row = where_are_we(conn, slug)
    if row is None:
        print(f"status: no client with slug {slug!r}", file=sys.stderr)
        return 1
    print(format_where_are_we(row))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
