#!/usr/bin/env python3
"""Warehouse go-live tooling (go-live swap step 1; PRD DR-1 migrations only, NFR-1 role per job).

    scripts/apply_migrations.py [--dry-run] [--baseline NNNN] [--storage-writer EMAIL] [--admin-env VAR]
    scripts/apply_migrations.py --verify

Applies every numbered migration in warehouse/ (`warehouse.client.migration_files()`: schema.sql is 0001) to the
database named by `WAREHOUSE_URL_ADMIN` (on Supabase: the `postgres` pooler string, session mode), once each, one
transaction per file, recorded in `ops.schema_migrations` with the file's sha256. `--dry-run` lists what is pending
and changes nothing. A target that already has the warehouse tables but no bookkeeping (applied by hand) is refused
until `--baseline NNNN` records files up to that prefix as applied without running them. A preflight refuses SQL that
needs a superuser (Supabase's `postgres` is not one) before anything runs, and reports where extensions land.

Then LOGIN and the password from each `WAREHOUSE_URL_*` string for the five roles: the password is turned into a
SCRAM-SHA-256 verifier on this machine, so the plaintext never reaches the server or its logs; a role whose URL
already connects is left alone, so a second run changes nothing.

On a Supabase target (roles `anon` and `authenticated` exist) the Data API roles lose every privilege on the
warehouse, now and by default for later migrations: Supabase grants them ALL on what `postgres` creates in public,
and 0002's actions_guard only stops `worker_rw`. `--storage-writer EMAIL` creates the public bucket
(`SUPABASE_STORAGE_BUCKET`, default `creatives`) if absent and the RLS policy that lets that one Auth user insert,
read and overwrite objects there and nothing else (adapters/storage/supabase.py signs in as it).

`--verify` (what `scripts/dev_db.sh --verify` runs, local or remote) connects with each of the five role URLs, checks
it is that role and neither superuser nor BYPASSRLS, prints `verify: <role> families=<n>`, warns on a remote URL
without sslmode=require, and fails while the Data API roles can reach the warehouse. It reads only.

Opens and closes a `runs` row (worker `migrate`) as soon as the runs table exists. Prints names, never a secret.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.env import MissingEnvVar, load_env  # noqa: E402
from warehouse.client import insert, migration_files  # noqa: E402

WORKER = "migrate"
ROLE_VARS = {"WAREHOUSE_URL_WORKER": "worker_rw", "WAREHOUSE_URL_EXECUTOR": "executor", "WAREHOUSE_URL_SAM_ADMIN": "sam_admin",
             "WAREHOUSE_URL_APP": "app", "WAREHOUSE_URL_MCP_RO": "mcp_ro"}
DATA_API_ROLES = ("anon", "authenticated")
LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}
TLS_MODES = {"require", "verify-ca", "verify-full"}
CONNECT = {"connect_timeout": 15, "prepare_threshold": None}   # prepared statements break on Supabase's transaction pooler

SUPERUSER_ONLY = [
    (r"\balter\s+system\b", "ALTER SYSTEM needs a superuser"),
    (r"\bcreate\s+(?:or\s+replace\s+)?(?:trusted\s+)?(?:procedural\s+)?language\b", "CREATE LANGUAGE needs a superuser"),
    (r"\bcopy\b[^;]*\bprogram\b", "COPY ... PROGRAM needs a superuser"),
    (r"\b(?:create|alter)\s+(?:role|user)\b[^;]*\b(?:superuser|replication|bypassrls)\b", "only a superuser grants SUPERUSER / REPLICATION / BYPASSRLS"),
    (r"\bcreate\s+event\s+trigger\b", "event triggers need a superuser"),
    (r"\bpg_(?:read|write)_server_files\b|\bpg_execute_server_program\b", "server file access needs a superuser"),
    (r"\bsession_replication_role\b", "session_replication_role needs a superuser"),
    (r"\blanguage\s+'?c'?\s*(?:;|$|\bas\b)", "C-language functions need a superuser"),
]

BOOKKEEPING = """
create schema if not exists ops;
create table if not exists ops.schema_migrations (
  name        text primary key,
  checksum    text not null,
  baselined   boolean not null default false,
  applied_at  timestamptz not null default now(),
  applied_by  text not null default current_user
);
"""


class RoleUrlError(ValueError):
    """A WAREHOUSE_URL_* string does not name its role or has no password. Names the variable, never the value."""


class SetupError(RuntimeError):
    """The target cannot take a step as asked (refused before it changes anything)."""


# ---------- SQL checks ----------

def strip_comments(text: str) -> str:
    return re.sub(r"--[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))


def lint(text: str) -> list[str]:
    """Statements Supabase's `postgres` (CREATEROLE, database owner, no superuser) cannot run."""
    body = strip_comments(text)
    return [why for pattern, why in SUPERUSER_ONLY if re.search(pattern, body, flags=re.I | re.M)]


def preflight(conn: psycopg.Connection, pending: list[Path]) -> list[str]:
    """Notes to print; raises SetupError naming every blocker before any file runs."""
    blockers, notes = [], []
    version = conn.execute("select current_setting('server_version_num')::int").fetchone()[0]
    if version < 150000:
        blockers.append("the target runs Postgres < 15; schema.sql's views use security_invoker")
    superuser, createrole = conn.execute("select rolsuper, rolcreaterole from pg_roles where rolname = current_user").fetchone()
    for path in pending:
        text = strip_comments(path.read_text())
        blockers += [f"{path.name}: {why}" for why in lint(text)]
        if re.search(r"\bcreate\s+role\b", text, flags=re.I) and not (superuser or createrole):
            blockers.append(f"{path.name} creates roles and the connecting role lacks CREATEROLE")
        for ext in re.findall(r'\bcreate\s+extension\s+(?:if\s+not\s+exists\s+)?"?([\w-]+)"?', text, flags=re.I):
            row = conn.execute(
                "select n.nspname, coalesce((select bool_or(v.trusted) from pg_available_extension_versions v where v.name = a.name), false)"
                " from pg_available_extensions a left join pg_extension e on e.extname = a.name"
                " left join pg_namespace n on n.oid = e.extnamespace where a.name = %s", (ext,)).fetchone()
            if row is None:
                blockers.append(f"{path.name}: extension {ext} is not available on the target")
            elif row[0]:
                notes.append(f"extension {ext} is installed in schema {row[0]}")
            elif not row[1] and not superuser:
                notes.append(f"extension {ext} is not a trusted extension: Supabase's postgres creates it only from its allow-list"
                             " (enable it in Dashboard > Database > Extensions, schema extensions, before applying)")
            else:
                notes.append(f"extension {ext} will be created by {path.name} in the first schema on the search path")
    if blockers:
        raise SetupError("preflight refused: " + "; ".join(blockers))
    return notes


# ---------- the runs row ----------

class MigrateRun:
    """The `runs` row, opened as soon as the runs table exists (a fresh target gets it right after schema.sql)."""

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn
        self.id = None
        self.started_at: datetime = conn.execute("select clock_timestamp()").fetchone()[0]
        conn.commit()
        self.counts: dict[str, Any] = {"pending": 0, "applied": [], "baselined": [], "checksum_mismatch": [],
                                       "roles_updated": [], "data_api_revoked": 0, "storage_writer_policies": 0, "dry_run": 0}

    def open_if_possible(self) -> None:
        if self.id is None and self.conn.execute("select to_regclass('public.runs') is not null").fetchone()[0]:
            self.id = insert(self.conn, "runs", worker=WORKER, started_at=self.started_at)["id"]
        self.conn.commit()

    def close(self, status: str, error: str | None = None) -> None:
        self.conn.rollback()
        self.open_if_possible()
        if self.id is not None:
            self.conn.execute("update runs set status = %s, finished_at = now(), counts = %s, error = %s where id = %s",
                              (status, Jsonb(self.counts), error, self.id))
            self.conn.commit()


# ---------- migrations ----------

def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prefix(path: Path) -> str:
    return "0001" if path.name == "schema.sql" else path.name[:4]


def applied_migrations(conn: psycopg.Connection) -> dict[str, str]:
    if not conn.execute("select to_regclass('ops.schema_migrations') is not null").fetchone()[0]:
        return {}
    return dict(conn.execute("select name, checksum from ops.schema_migrations").fetchall())


def migrate(conn: psycopg.Connection, r: MigrateRun, files: list[Path], *, dry_run: bool, baseline: str | None) -> None:
    applied = applied_migrations(conn)
    if not applied and conn.execute("select to_regclass('public.raw_ingest') is not null").fetchone()[0] and not baseline:
        raise SetupError("the target already has the warehouse tables but no ops.schema_migrations; if migrations were applied by"
                         " hand, re-run with --baseline NNNN (the last file applied, e.g. --baseline 0007) to record them")
    for path in files:
        if path.name in applied and applied[path.name] != checksum(path):
            r.counts["checksum_mismatch"].append(path.name)
            print(f"apply_migrations: WARNING {path.name} changed since it was applied; migrations are append-only, add a new file")
    pending = [p for p in files if p.name not in applied]
    if baseline:
        pending_after = [p for p in pending if prefix(p) > baseline[:4]]
        to_baseline = [p for p in pending if p not in pending_after]
    else:
        pending_after, to_baseline = pending, []
    r.counts["pending"] = len(pending_after)
    notes = preflight(conn, pending_after)
    conn.commit()
    for note in notes:
        print(f"apply_migrations: preflight: {note}")
    if dry_run:
        for p in to_baseline:
            print(f"apply_migrations: would baseline {p.name}")
        for p in pending_after:
            print(f"apply_migrations: pending {p.name}")
        print(f"apply_migrations: pending: {len(pending_after)}")
        return
    conn.execute(BOOKKEEPING)
    for p in to_baseline:
        conn.execute("insert into ops.schema_migrations (name, checksum, baselined) values (%s, %s, true) on conflict do nothing",
                     (p.name, checksum(p)))
        r.counts["baselined"].append(p.name)
        print(f"apply_migrations: baselined {p.name}")
    conn.commit()
    for p in pending_after:
        with conn.transaction():
            conn.execute("select pg_advisory_xact_lock(hashtext('apply_migrations'))")
            if conn.execute("select 1 from ops.schema_migrations where name = %s", (p.name,)).fetchone():
                continue
            print(f"apply_migrations: applying {p.name}")
            try:
                conn.execute(p.read_text())
            except psycopg.Error as exc:
                raise SetupError(f"{p.name} failed and was rolled back: {type(exc).__name__}: {str(exc).splitlines()[0]}") from None
            conn.execute("insert into ops.schema_migrations (name, checksum) values (%s, %s)", (p.name, checksum(p)))
        r.counts["applied"].append(p.name)
        r.open_if_possible()
    print(f"apply_migrations: migrations applied now: {len(r.counts['applied'])}")


# ---------- roles ----------

def role_urls(env: Mapping[str, str]) -> dict[str, str]:
    """role -> URL for the five roles, each checked to name its role (`role` or Supavisor's `role.<project-ref>`) and to
    carry a password. Errors name the variable only."""
    missing = [var for var in ROLE_VARS if not env.get(var)]
    if missing:
        raise MissingEnvVar(f"job 'apply_migrations' needs {', '.join(missing)}; set it in marketing-engineer/.env (see .env.example)")
    out = {}
    for var, role in ROLE_VARS.items():
        try:
            info = conninfo_to_dict(env[var])
        except psycopg.Error:
            raise RoleUrlError(f"{var} is not a Postgres connection string") from None
        user = info.get("user") or ""
        if user != role and not user.startswith(role + "."):
            raise RoleUrlError(f"{var} does not name role {role} (expected user {role} or {role}.<project-ref>)")
        if not info.get("password"):
            raise RoleUrlError(f"{var} has no password")
        out[role] = env[var]
    return out


def probe(url: str, role: str) -> bool:
    """True when the URL already logs in as `role` (nothing to change)."""
    try:
        with psycopg.connect(url, autocommit=True, **CONNECT) as conn:
            return conn.execute("select current_user").fetchone()[0] == role
    except psycopg.Error:
        return False


def login_statement(conn: psycopg.Connection, role: str, password: str) -> sql.Composed:
    """ALTER ROLE ... LOGIN PASSWORD '<SCRAM verifier>': the verifier is computed here, the plaintext is never sent."""
    verifier = conn.pgconn.encrypt_password(password.encode(), role.encode(), b"scram-sha-256").decode()
    return sql.SQL("alter role {} with login password {}").format(sql.Identifier(role), sql.Literal(verifier))


def set_role_logins(conn: psycopg.Connection, urls: dict[str, str], probe: Callable[[str, str], bool] = probe) -> list[str]:
    """LOGIN + password for every role whose URL does not already connect; returns the roles changed. Does not commit."""
    changed = []
    for role, url in urls.items():
        if probe(url, role):
            continue
        conn.execute(login_statement(conn, role, conninfo_to_dict(url)["password"]))
        changed.append(role)
    return changed


# ---------- Supabase platform ----------

def supabase_roles_present(conn: psycopg.Connection) -> bool:
    return conn.execute("select count(*) = %s from pg_roles where rolname = any(%s)",
                        (len(DATA_API_ROLES), list(DATA_API_ROLES))).fetchone()[0]


def data_api_exposure(conn: psycopg.Connection) -> list[str]:
    """What anon / authenticated can do on the warehouse (schema public), one line per role and kind; empty when nothing."""
    if not supabase_roles_present(conn):
        return []
    lines = []
    for role in DATA_API_ROLES:
        privs, n = conn.execute(
            "select string_agg(distinct x.priv, ', ' order by x.priv), count(distinct x.oid) from ("
            " select c.oid, priv from pg_class c join pg_namespace n on n.oid = c.relnamespace,"
            " unnest(array['select','insert','update','delete','truncate','references','trigger']) priv"
            " where n.nspname = 'public' and c.relkind in ('r','v','m','p','f') and has_table_privilege(%s, c.oid, priv)) x",
            (role,)).fetchone()
        if n:
            lines.append(f"{role}: {privs} on {n} warehouse relations")
        funcs = conn.execute(
            "select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace, aclexplode(p.proacl) a"
            " where n.nspname = 'public' and a.grantee = (select oid from pg_roles where rolname = %s)", (role,)).fetchone()[0]
        if funcs:
            lines.append(f"{role}: execute granted on {funcs} warehouse functions")
    return lines


def revoke_data_api(conn: psycopg.Connection) -> None:
    """Supabase's Data API roles lose every privilege in public, now and as default for later migrations. Does not commit."""
    roles = sql.SQL(", ").join(sql.Identifier(r) for r in DATA_API_ROLES)
    me = sql.Identifier(conn.execute("select current_user").fetchone()[0])
    for kind in ("tables", "sequences", "functions"):
        conn.execute(sql.SQL("revoke all on all {} in schema public from {}").format(sql.SQL(kind), roles))
        conn.execute(sql.SQL("alter default privileges for role {} in schema public revoke all on {} from {}").format(me, sql.SQL(kind), roles))


def storage_writer_setup(conn: psycopg.Connection, bucket: str, email: str):
    """The public bucket (created if absent) and three RLS policies on storage.objects for the one Auth user with `email`:
    insert, select (upsert reads first) and update, in that bucket only; no delete. Returns the user's id. Does not commit."""
    if not conn.execute("select to_regclass('storage.objects') is not null and to_regclass('storage.buckets') is not null"
                        " and to_regclass('auth.users') is not null").fetchone()[0]:
        raise SetupError("--storage-writer needs a Supabase target (storage.objects, storage.buckets, auth.users)")
    users = conn.execute("select id from auth.users where lower(email) = lower(%s)", (email,)).fetchall()
    if len(users) != 1:
        raise SetupError("--storage-writer: no Supabase Auth user has that email; create it in Dashboard > Authentication > Users")
    uid = users[0][0]
    conn.execute("insert into storage.buckets (id, name, public) values (%s, %s, true) on conflict (id) do nothing", (bucket, bucket))
    if not conn.execute("select public from storage.buckets where id = %s", (bucket,)).fetchone()[0]:
        raise SetupError(f"bucket {bucket!r} exists but is not public; Meta fetches creatives by URL and the storage adapter returns"
                         " public URLs. Make it public (Dashboard > Storage) or set SUPABASE_STORAGE_BUCKET to another bucket")
    cond = sql.SQL("bucket_id = {} and (select auth.uid()) = {}::uuid").format(sql.Literal(bucket), sql.Literal(str(uid)))
    for action, clause in (("insert", sql.SQL("with check ({})").format(cond)), ("select", sql.SQL("using ({})").format(cond)),
                           ("update", sql.SQL("using ({}) with check ({})").format(cond, cond))):
        name = sql.Identifier(f"me_storage_writer_{bucket}_{action}")
        conn.execute(sql.SQL("drop policy if exists {} on storage.objects").format(name))
        conn.execute(sql.SQL("create policy {} on storage.objects for {} to authenticated {}").format(name, sql.SQL(action), clause))
    return uid


# ---------- verify ----------

def is_remote(info: Mapping[str, str]) -> bool:
    host = info.get("host") or ""
    return not (host in LOCAL_HOSTS or host.startswith("/"))


def first_line(exc: Exception, info: Mapping[str, str]) -> str:
    """libpq's first error line with the URL's password scrubbed (libpq does not echo it; this makes sure)."""
    line = (str(exc).splitlines() or [""])[0]
    password = info.get("password") or ""
    return line.replace(password, "***") if password else line


def verify(env: Mapping[str, str]) -> int:
    """Connect with each role URL: it must be that role, not superuser, not BYPASSRLS. Reads only; 1 on any failure."""
    failures, checked_exposure = 0, False
    for var, role in ROLE_VARS.items():
        url = env.get(var)
        if not url:
            print(f"verify: FAIL {var} is unset")
            failures += 1
            continue
        info = conninfo_to_dict(url)
        if is_remote(info) and info.get("sslmode") not in TLS_MODES:
            print(f"verify: WARNING {var} points at a remote host without sslmode=require (libpq's default may fall back to plaintext)")
        try:
            conn = psycopg.connect(url, autocommit=True, **CONNECT)
        except psycopg.Error as exc:
            print(f"verify: FAIL {role} cannot connect with {var}: {type(exc).__name__}: {first_line(exc, info)}")
            failures += 1
            continue
        with conn:
            current, superuser, bypass = conn.execute(
                "select current_user, rolsuper, rolbypassrls from pg_roles where rolname = current_user").fetchone()
            if current != role:
                print(f"verify: FAIL {var} connects as {current}, expected {role}")
                failures += 1
                continue
            if superuser or bypass:
                print(f"verify: FAIL {role} is {'superuser' if superuser else 'BYPASSRLS'}; workers never hold such a role (NFR-1)")
                failures += 1
                continue
            try:
                print(f"verify: {role} families={conn.execute('select count(*) from families').fetchone()[0]}")
            except psycopg.errors.InsufficientPrivilege:
                print(f"verify: {role} connected; no select on families (0002 grants none to {role})")
            if not checked_exposure:
                checked_exposure = True
                for line in data_api_exposure(conn):
                    print(f"verify: FAIL Supabase Data API role {line}; run scripts/apply_migrations.py against this target")
                    failures += 1
    return 1 if failures else 0


# ---------- main ----------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="apply warehouse migrations once each, then role logins; --verify checks the five role URLs")
    ap.add_argument("--dry-run", action="store_true", help="list pending migrations; change nothing")
    ap.add_argument("--baseline", metavar="NNNN", help="record migrations up to this prefix as applied without running them")
    ap.add_argument("--storage-writer", metavar="EMAIL", help="Supabase only: bucket + RLS policy for this Auth user")
    ap.add_argument("--admin-env", default="WAREHOUSE_URL_ADMIN", help="variable holding the migrating role's URL")
    ap.add_argument("--verify", action="store_true", help="connect as each of the five roles and check them; reads only")
    args = ap.parse_args(argv)
    if args.baseline and not re.fullmatch(r"\d{4}(_[\w.-]+)?|schema\.sql", args.baseline):
        ap.error("--baseline takes a 4-digit migration prefix, e.g. 0007")
    baseline = "0001" if args.baseline == "schema.sql" else args.baseline

    load_env()
    if args.verify:
        return verify(os.environ)
    try:
        admin_url = os.environ.get(args.admin_env) or ""
        if not admin_url:
            raise MissingEnvVar(f"job 'apply_migrations' needs {args.admin_env}; set it in marketing-engineer/.env (see .env.example)")
        urls = role_urls(os.environ)
    except (MissingEnvVar, RoleUrlError) as exc:
        print(f"apply_migrations: {exc}", file=sys.stderr)
        return 2
    info = conninfo_to_dict(admin_url)
    try:
        conn = psycopg.connect(admin_url, **CONNECT)
    except psycopg.Error as exc:
        print(f"apply_migrations: cannot connect with {args.admin_env}: {type(exc).__name__}: {first_line(exc, info)}", file=sys.stderr)
        return 1
    with conn:
        print(f"apply_migrations: target {info.get('host') or 'socket'}:{info.get('port') or 5432}/{info.get('dbname') or ''}"
              f" as {conn.execute('select current_user').fetchone()[0]}")
        conn.commit()
        r = MigrateRun(conn)
        r.counts["dry_run"] = int(args.dry_run)
        try:
            r.open_if_possible()
            migrate(conn, r, migration_files(), dry_run=args.dry_run, baseline=baseline)
            if not args.dry_run:
                if supabase_roles_present(conn):
                    revoke_data_api(conn)
                    r.counts["data_api_revoked"] = 1
                    print("apply_migrations: supabase: anon and authenticated hold no privilege on the warehouse (tables, sequences, functions, defaults)")
                else:
                    print("apply_migrations: not a Supabase target (no anon / authenticated roles); Data API step skipped")
                if args.storage_writer:
                    storage_writer_setup(conn, os.environ.get("SUPABASE_STORAGE_BUCKET") or "creatives", args.storage_writer)
                    r.counts["storage_writer_policies"] = 1
                    print("apply_migrations: supabase: storage writer policies set on the bucket for the --storage-writer user")
                conn.commit()
                r.counts["roles_updated"] = set_role_logins(conn, urls)
                conn.commit()
                print(f"apply_migrations: roles updated now: {len(r.counts['roles_updated'])}")
        except (SetupError, psycopg.Error) as exc:
            error = str(exc) if isinstance(exc, SetupError) else f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
            print(f"apply_migrations: FAILED {error}", file=sys.stderr)
            r.close("failed", error[:2000])
            return 1
        except BaseException as exc:
            r.close("failed", f"{type(exc).__name__}: {exc}"[:2000])
            raise
        r.close("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
