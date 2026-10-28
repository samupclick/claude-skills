"""scripts/apply_migrations.py (go-live swap step 1; DR-1, NFR-1) against throwaway databases on the local cluster:
every numbered migration once each with a bookkeeping table and a transaction per file, --dry-run, --baseline,
LOGIN + SCRAM verifiers for the five roles, a runs row, a non-superuser owner standing in for Supabase's `postgres`,
and the Supabase platform step (Data API roles revoked, storage writer policy) on Supabase-shaped stubs inside a
rolled-back transaction. Never mocked."""
from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

from warehouse.client import TABLES, migration_files

ME_DIR = Path(__file__).resolve().parent.parent
SCRIPT = ME_DIR / "scripts" / "apply_migrations.py"
ROLE_VARS = {"WAREHOUSE_URL_WORKER": "worker_rw", "WAREHOUSE_URL_EXECUTOR": "executor", "WAREHOUSE_URL_SAM_ADMIN": "sam_admin",
             "WAREHOUSE_URL_APP": "app", "WAREHOUSE_URL_MCP_RO": "mcp_ro"}
NAMES = [p.name for p in migration_files()]

_spec = importlib.util.spec_from_file_location("apply_migrations_under_test", SCRIPT)
am = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = am
_spec.loader.exec_module(am)


def retarget(url: str, *, db: str | None = None, user: str | None = None, password: str | None = None) -> str:
    parts = urlsplit(url)
    netloc = parts.netloc
    if user is not None:
        netloc = f"{user}:{password}@{netloc.rsplit('@', 1)[1]}"
    return urlunsplit(parts._replace(netloc=netloc, path=f"/{db}" if db else parts.path))


@pytest.fixture
def fresh_db(warehouse_env):
    """make(owner=None) -> the six WAREHOUSE_URL_* pointed at a new empty database; all dropped afterwards."""
    admin = warehouse_env["WAREHOUSE_URL_ADMIN"]
    created: list[str] = []

    def make(owner: str | None = None) -> dict[str, str]:
        name = f"gw_mig_{os.getpid()}_{len(created)}"
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name)))
            conn.execute(sql.SQL("create database {}").format(sql.Identifier(name))
                         + (sql.SQL(" owner {}").format(sql.Identifier(owner)) if owner else sql.SQL("")))
        created.append(name)
        return {k: retarget(v, db=name) for k, v in warehouse_env.items() if k.startswith("WAREHOUSE_URL_")}

    yield make
    with psycopg.connect(admin, autocommit=True) as conn:
        for name in created:
            conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name)))


def run_script(urls: dict[str, str], *args: str, **extra: str) -> subprocess.CompletedProcess:
    env = {**os.environ, **urls, **extra}
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ME_DIR, env=env, capture_output=True, text=True)


def role_snapshot(admin_url: str):
    with psycopg.connect(admin_url) as conn:
        return conn.execute("select rolname, rolcanlogin, md5(rolpassword) from pg_authid where rolname = any(%s) order by 1",
                            (list(ROLE_VARS.values()),)).fetchall()


def migrate_runs(admin_url: str):
    with psycopg.connect(admin_url) as conn:
        return conn.execute("select status, counts, error, finished_at is not null from runs where worker = 'migrate' "
                            "order by started_at, id").fetchall()


def test_dry_run_lists_every_pending_migration_and_writes_nothing(fresh_db):
    urls = fresh_db()
    res = run_script(urls, "--dry-run")
    assert res.returncode == 0, res.stdout + res.stderr
    assert re.findall(r"^apply_migrations: pending (\S+)$", res.stdout, flags=re.M) == NAMES
    assert re.search(r"^apply_migrations: target localhost:5432/gw_mig_\d+_0 as postgres$", res.stdout, flags=re.M)
    with psycopg.connect(urls["WAREHOUSE_URL_ADMIN"]) as conn:
        assert conn.execute("select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                            "where n.nspname in ('public', 'ops')").fetchone()[0] == 0
        assert conn.execute("select to_regnamespace('ops')").fetchone()[0] is None


def test_applies_every_migration_once_then_a_second_run_changes_nothing(fresh_db):
    urls = fresh_db()
    admin = urls["WAREHOUSE_URL_ADMIN"]
    roles_before = role_snapshot(admin)
    first = run_script(urls)
    assert first.returncode == 0, first.stdout + first.stderr
    assert re.findall(r"^apply_migrations: applying (\S+)$", first.stdout, flags=re.M) == NAMES
    assert f"migrations applied now: {len(NAMES)}" in first.stdout and "roles updated now: 0" in first.stdout
    with psycopg.connect(admin) as conn:
        rows = conn.execute("select name, checksum, baselined from ops.schema_migrations order by name").fetchall()
        assert {r[0] for r in rows} == set(NAMES) and not any(r[2] for r in rows)
        for name, checksum, _ in rows:
            path = ME_DIR / "warehouse" / name
            assert checksum == hashlib.sha256(path.read_bytes()).hexdigest()
        base_tables = {r[0] for r in conn.execute(
            "select table_name from information_schema.tables where table_schema = 'public' and table_type = 'BASE TABLE'")}
        assert base_tables == set(TABLES)
        assert conn.execute("select 1 from pg_extension where extname = 'vector'").fetchone() == (1,)
    second = run_script(urls)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "migrations applied now: 0" in second.stdout and "roles updated now: 0" in second.stdout
    runs = migrate_runs(admin)
    assert [(r[0], r[3]) for r in runs] == [("ok", True), ("ok", True)]
    assert runs[0][1]["applied"] == NAMES and runs[1][1]["applied"] == [] and runs[1][1]["pending"] == 0
    assert runs[0][1]["roles_updated"] == [] and runs[0][1]["dry_run"] == 0
    assert role_snapshot(admin) == roles_before
    for out in (first.stdout + first.stderr, second.stdout + second.stderr):
        assert "dev-worker_rw" not in out and "dev-postgres" not in out


def test_dry_run_after_apply_reports_nothing_pending_and_records_a_run(fresh_db):
    urls = fresh_db()
    assert run_script(urls).returncode == 0
    res = run_script(urls, "--dry-run")
    assert res.returncode == 0 and "pending" not in res.stdout.replace("pending: 0", "")
    assert "apply_migrations: pending: 0" in res.stdout
    last = migrate_runs(urls["WAREHOUSE_URL_ADMIN"])[-1]
    assert last[0] == "ok" and last[1]["dry_run"] == 1 and last[1]["pending"] == 0


def test_failing_migration_rolls_back_its_file_and_closes_the_run_failed(fresh_db, monkeypatch, tmp_path, capsys):
    urls = fresh_db()
    broken = tmp_path / "0099_broken.sql"
    broken.write_text("create table broken_probe (id int);\nselect 1/0;\n")
    monkeypatch.setattr(am, "migration_files", lambda: [*migration_files(), broken])
    for k, v in urls.items():
        monkeypatch.setenv(k, v)
    assert am.main([]) == 1
    out = capsys.readouterr()
    assert "0099_broken.sql" in out.err and "division by zero" in out.err
    with psycopg.connect(urls["WAREHOUSE_URL_ADMIN"]) as conn:
        assert conn.execute("select to_regclass('public.broken_probe')").fetchone()[0] is None
        assert {r[0] for r in conn.execute("select name from ops.schema_migrations")} == set(NAMES)
    status, counts, error, closed = migrate_runs(urls["WAREHOUSE_URL_ADMIN"])[-1]
    assert status == "failed" and closed and "0099_broken.sql" in error and counts["applied"] == NAMES


def test_superuser_only_statement_is_refused_before_anything_is_applied(fresh_db, monkeypatch, tmp_path, capsys):
    urls = fresh_db()
    bad = tmp_path / "0099_system.sql"
    bad.write_text("-- alter system in a comment is fine\nalter system set work_mem = '64MB';\n")
    monkeypatch.setattr(am, "migration_files", lambda: [*migration_files(), bad])
    for k, v in urls.items():
        monkeypatch.setenv(k, v)
    assert am.main([]) == 1
    assert "0099_system.sql" in capsys.readouterr().err
    with psycopg.connect(urls["WAREHOUSE_URL_ADMIN"]) as conn:
        assert conn.execute("select to_regclass('public.runs'), to_regnamespace('ops')").fetchone() == (None, None)


def test_lint_flags_superuser_only_sql_and_passes_every_real_migration():
    assert am.lint("alter system set x = 1;")
    assert am.lint("create role boss login superuser;")
    assert am.lint("copy t from program 'cat /etc/passwd';")
    assert am.lint("create language plperlu;")
    assert am.lint("set session_replication_role = replica;")
    assert am.lint("create role worker_rw nologin nosuperuser;") == []
    assert am.lint("-- alter system set x = 1\nselect 1;") == []
    for path in migration_files():
        assert am.lint(path.read_text()) == [], path.name


def test_existing_warehouse_without_bookkeeping_needs_a_baseline(fresh_db):
    urls = fresh_db()
    admin = urls["WAREHOUSE_URL_ADMIN"]
    with psycopg.connect(admin) as conn:
        for path in migration_files():
            conn.execute(path.read_text())
        conn.commit()
    refused = run_script(urls)
    assert refused.returncode == 1 and "--baseline" in refused.stderr
    with psycopg.connect(admin) as conn:
        assert conn.execute("select to_regclass('ops.schema_migrations')").fetchone()[0] is None
    assert migrate_runs(admin)[-1][0] == "failed"
    last_prefix = NAMES[-1][:4]
    res = run_script(urls, "--baseline", last_prefix)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "migrations applied now: 0" in res.stdout
    with psycopg.connect(admin) as conn:
        rows = conn.execute("select name, baselined from ops.schema_migrations").fetchall()
    assert {r[0] for r in rows} == set(NAMES) and all(r[1] for r in rows)
    assert migrate_runs(admin)[-1][1]["baselined"] == NAMES


def test_checksum_drift_is_reported_not_reapplied(fresh_db):
    urls = fresh_db()
    assert run_script(urls).returncode == 0
    with psycopg.connect(urls["WAREHOUSE_URL_ADMIN"]) as conn:
        conn.execute("update ops.schema_migrations set checksum = repeat('0', 64) where name = '0003_phase0_grants.sql'")
    res = run_script(urls)
    assert res.returncode == 0
    assert "WARNING 0003_phase0_grants.sql changed since it was applied" in res.stdout
    assert migrate_runs(urls["WAREHOUSE_URL_ADMIN"])[-1][1]["checksum_mismatch"] == ["0003_phase0_grants.sql"]


def scram_matches(verifier: str, password: str) -> bool:
    m = re.fullmatch(r"SCRAM-SHA-256\$(\d+):([^$]+)\$([^:]+):(.+)", verifier)
    iterations, salt, stored = int(m.group(1)), base64.b64decode(m.group(2)), base64.b64decode(m.group(3))
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    return hashlib.sha256(client_key).digest() == stored


def test_role_logins_are_scram_verifiers_never_the_password(test_db):
    urls = {var: test_db[var] for var in ROLE_VARS}
    with psycopg.connect(test_db["WAREHOUSE_URL_ADMIN"]) as conn:
        stmt = am.login_statement(conn, "worker_rw", "plain-text-never-sent").as_string(conn)
        assert "plain-text-never-sent" not in stmt and "SCRAM-SHA-256$4096:" in stmt and stmt.startswith('alter role "worker_rw"')
        changed = am.set_role_logins(conn, am.role_urls(urls), probe=lambda url, role: False)
        assert changed == list(ROLE_VARS.values())
        for var, role in ROLE_VARS.items():
            can_login, verifier = conn.execute("select rolcanlogin, rolpassword from pg_authid where rolname = %s", (role,)).fetchone()
            assert can_login and scram_matches(verifier, urlsplit(urls[var]).password)
        conn.rollback()
        assert am.set_role_logins(conn, am.role_urls(urls)) == []
        conn.rollback()


def test_role_urls_must_name_their_role_and_carry_a_password(test_db):
    urls = {var: test_db[var] for var in ROLE_VARS}
    pooler = {**urls, "WAREHOUSE_URL_WORKER": retarget(urls["WAREHOUSE_URL_WORKER"], user="worker_rw.abcdefghijklmnop", password="pw")}
    assert am.role_urls(pooler)["worker_rw"].startswith("postgresql://worker_rw.abcdefghijklmnop:")
    wrong = {**urls, "WAREHOUSE_URL_WORKER": test_db["WAREHOUSE_URL_ADMIN"]}
    with pytest.raises(am.RoleUrlError) as exc:
        am.role_urls(wrong)
    assert "WAREHOUSE_URL_WORKER" in str(exc.value) and "dev-postgres" not in str(exc.value)
    nopw = {**urls, "WAREHOUSE_URL_APP": retarget(urls["WAREHOUSE_URL_APP"], user="app", password="").replace("app:@", "app@")}
    with pytest.raises(am.RoleUrlError, match="WAREHOUSE_URL_APP has no password"):
        am.role_urls(nopw)


def test_bad_role_url_stops_the_script_before_it_connects(fresh_db):
    urls = fresh_db()
    res = run_script({**urls, "WAREHOUSE_URL_WORKER": urls["WAREHOUSE_URL_ADMIN"]})
    assert res.returncode == 2 and "WAREHOUSE_URL_WORKER" in res.stderr
    assert "dev-postgres" not in res.stdout + res.stderr
    missing = run_script({**urls, "WAREHOUSE_URL_APP": ""})
    assert missing.returncode == 2 and "WAREHOUSE_URL_APP" in missing.stderr
    with psycopg.connect(urls["WAREHOUSE_URL_ADMIN"]) as conn:
        assert conn.execute("select to_regclass('public.runs')").fetchone()[0] is None


def test_migrations_apply_as_a_non_superuser_owner_like_supabase_postgres(warehouse_env, fresh_db):
    """Supabase's `postgres` is not a superuser: it owns the database, may CREATEROLE, and gets pgvector from the
    Dashboard (schema `extensions`, which Supabase puts on its search path) because vector is not a trusted extension.
    A local role with exactly that applies every migration; nothing in them needs more."""
    admin = warehouse_env["WAREHOUSE_URL_ADMIN"]
    role, password = f"me_migrator_{os.getpid()}", "dev-migrator-local-only"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("drop role if exists {}").format(sql.Identifier(role)))
        conn.execute(sql.SQL("create role {} login createrole password {}").format(sql.Identifier(role), sql.Literal(password)))
        conn.execute(sql.SQL("alter role {} set search_path = \"$user\", public, extensions").format(sql.Identifier(role)))
    try:
        urls = fresh_db(owner=role)
        with psycopg.connect(urls["WAREHOUSE_URL_ADMIN"], autocommit=True) as conn:   # the Dashboard's "enable pgvector"
            conn.execute("create schema extensions")
            conn.execute("create extension vector with schema extensions")
            conn.execute(sql.SQL("grant usage on schema extensions to {}").format(sql.Identifier(role)))
        urls["WAREHOUSE_URL_ADMIN"] = retarget(urls["WAREHOUSE_URL_ADMIN"], user=role, password=password)
        res = run_script(urls)
        assert res.returncode == 0, res.stdout + res.stderr
        assert f"migrations applied now: {len(NAMES)}" in res.stdout
        assert "extension vector is installed in schema extensions" in res.stdout
        with psycopg.connect(urls["WAREHOUSE_URL_ADMIN"]) as conn:
            assert conn.execute("select rolsuper from pg_roles where rolname = current_user").fetchone() == (False,)
            owner = conn.execute("select pg_get_userbyid(proowner) from pg_proc where proname = 'quiz_start'").fetchone()[0]
            assert owner == role
            assert conn.execute("select format_type(atttypid, atttypmod) from pg_attribute where attrelid = 'patterns'::regclass"
                                " and attname = 'embedding'").fetchone() == ("vector(1536)",)
            assert conn.execute("select status from runs where worker = 'migrate'").fetchone() == ("ok",)
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            for db in conn.execute("select datname from pg_database where pg_get_userbyid(datdba) = %s", (role,)).fetchall():
                conn.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(db[0])))
            conn.execute(sql.SQL("drop role if exists {}").format(sql.Identifier(role)))


SUPABASE_STUB = """
do $$ begin create role anon nologin; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated nologin; exception when duplicate_object then null; end $$;
create schema auth;
create table auth.users (id uuid primary key default gen_random_uuid(), email text);
create function auth.uid() returns uuid language sql stable as $f$
  select coalesce(nullif(current_setting('request.jwt.claim.sub', true), ''),
                  (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'))::uuid
$f$;
create schema storage;
create table storage.buckets (id text primary key, name text not null, public boolean default false);
create table storage.objects (id uuid primary key default gen_random_uuid(), bucket_id text references storage.buckets(id),
                              name text, owner uuid, metadata jsonb);
alter table storage.objects enable row level security;
grant usage on schema auth, storage to anon, authenticated;
grant all on storage.objects, storage.buckets to anon, authenticated;
"""


class _Rollback(Exception):
    pass


def as_user(conn, uid, statement: str, params=()) -> int:
    """One statement as `authenticated` with JWT sub `uid` (None = no user), in a savepoint that is always rolled back."""
    result: dict[str, int] = {}
    try:
        with conn.transaction():
            conn.execute("set local role authenticated")
            conn.execute("select set_config('request.jwt.claims', %s, true)", (json.dumps({"sub": str(uid)} if uid else {}),))
            result["rows"] = conn.execute(statement, params).rowcount
            raise _Rollback
    except _Rollback:
        return result["rows"]


def test_storage_writer_policy_scopes_writes_to_one_user_and_one_bucket(test_db):
    with psycopg.connect(test_db["WAREHOUSE_URL_ADMIN"]) as conn:
        conn.execute(SUPABASE_STUB)
        writer = conn.execute("insert into auth.users (email) values ('Storage-Writer@example.invalid') returning id").fetchone()[0]
        other = conn.execute("insert into auth.users (email) values ('someone@example.invalid') returning id").fetchone()[0]
        assert am.storage_writer_setup(conn, "creatives", "storage-writer@example.invalid") == writer
        assert am.storage_writer_setup(conn, "creatives", "storage-writer@example.invalid") == writer
        assert conn.execute("select public from storage.buckets where id = 'creatives'").fetchone() == (True,)
        policies = conn.execute("select policyname, cmd, roles from pg_policies where schemaname = 'storage' order by 1").fetchall()
        assert [(p[1], p[2]) for p in policies] == [("INSERT", ["authenticated"]), ("SELECT", ["authenticated"]), ("UPDATE", ["authenticated"])]
        conn.execute("insert into storage.buckets (id, name, public) values ('other', 'other', true)")
        conn.execute("insert into storage.objects (bucket_id, name, owner) values ('creatives', 'inspo/seed.png', %s)", (writer,))
        insert = "insert into storage.objects (bucket_id, name, owner) values (%s, %s, auth.uid())"
        assert as_user(conn, writer, insert, ("creatives", "creatives/u/b/c/1080x1080.png")) == 1
        assert as_user(conn, writer, "update storage.objects set metadata = '{}' where name = 'inspo/seed.png'") == 1
        assert as_user(conn, writer, "delete from storage.objects where name = 'inspo/seed.png'") == 0
        assert as_user(conn, other, "select 1 from storage.objects") == 0
        for uid, bucket in ((other, "creatives"), (writer, "other"), (None, "creatives")):
            with pytest.raises(psycopg.errors.InsufficientPrivilege, match="row-level security"):
                as_user(conn, uid, insert, (bucket, "inspo/x.png"))
        with pytest.raises(am.SetupError, match="no Supabase Auth user"):
            am.storage_writer_setup(conn, "creatives", "nobody@example.invalid")
        conn.execute("insert into storage.buckets (id, name, public) values ('private', 'private', false)")
        with pytest.raises(am.SetupError, match="exists but is not public"):
            am.storage_writer_setup(conn, "private", "storage-writer@example.invalid")
        conn.rollback()


def test_storage_writer_needs_a_supabase_target(test_db):
    with psycopg.connect(test_db["WAREHOUSE_URL_ADMIN"]) as conn:
        with pytest.raises(am.SetupError, match="Supabase"):
            am.storage_writer_setup(conn, "creatives", "storage-writer@example.invalid")


def test_supabase_data_api_roles_lose_every_warehouse_privilege(test_db):
    """Supabase's default privileges give anon and authenticated ALL on tables and functions postgres creates in public.
    The 0002 actions_guard only stops worker_rw, so without the revoke a publishable-key holder could approve actions
    over the Data API."""
    with psycopg.connect(test_db["WAREHOUSE_URL_ADMIN"]) as conn:
        conn.execute(SUPABASE_STUB)
        conn.execute("grant all on all tables in schema public to anon, authenticated")
        conn.execute("grant all on all functions in schema public to anon, authenticated")
        conn.execute("alter default privileges in schema public grant all on tables to anon, authenticated")
        exposure = am.data_api_exposure(conn)
        assert any(line.startswith("anon:") and "update" in line for line in exposure)
        assert any("execute" in line for line in exposure)
        assert am.supabase_roles_present(conn)
        am.revoke_data_api(conn)
        assert am.data_api_exposure(conn) == []
        assert conn.execute("select has_table_privilege('anon', 'actions', 'update'), has_table_privilege('authenticated', 'runs', 'select'),"
                            " has_function_privilege('anon', 'quiz_start(text, jsonb, jsonb, text, text, text)', 'execute')").fetchone() == (False, False, False)
        assert conn.execute("select has_table_privilege('worker_rw', 'runs', 'insert'), has_table_privilege('executor', 'actions', 'select'),"
                            " has_function_privilege('app', 'quiz_start(text, jsonb, jsonb, text, text, text)', 'execute')").fetchone() == (True, True, True)
        conn.execute("create table probe_after_revoke (id int)")
        assert conn.execute("select has_table_privilege('anon', 'probe_after_revoke', 'select')").fetchone() == (False,)
        conn.rollback()


def test_local_target_is_not_supabase(test_db):
    with psycopg.connect(test_db["WAREHOUSE_URL_ADMIN"]) as conn:
        assert not am.supabase_roles_present(conn) and am.data_api_exposure(conn) == []


def remote(url: str, **params: str) -> str:
    """The same local database behind a remote-looking host name: libpq dials `hostaddr` and never resolves the name."""
    parts = urlsplit(url)
    userinfo, hostport = parts.netloc.rsplit("@", 1)
    query = "&".join(f"{k}={v}" for k, v in {"hostaddr": "127.0.0.1", **params}.items())
    return urlunsplit(parts._replace(netloc=f"{userinfo}@warehouse.remote.invalid:{hostport.rsplit(':', 1)[1]}", query=query))


def verify_env(urls: dict[str, str]) -> dict[str, str]:
    return {**os.environ, **urls}


def test_dev_db_verify_works_against_remote_urls_without_the_local_cluster(test_db, tmp_path):
    stubs, marker = tmp_path / "bin", tmp_path / "local-cluster-touched"
    stubs.mkdir()
    for tool in ("pg_lsclusters", "pg_ctlcluster", "pg_isready", "dpkg", "apt-get", "runuser", "sudo"):
        (stubs / tool).write_text(f"#!/bin/sh\necho {tool} >> '{marker}'\nexit 97\n")
        (stubs / tool).chmod(0o755)
    env = {**verify_env({var: remote(test_db[var], sslmode="require") for var in ROLE_VARS}), "PATH": f"{stubs}:{os.environ['PATH']}"}
    res = subprocess.run([str(ME_DIR / "scripts" / "dev_db.sh"), "--verify"], cwd=ME_DIR, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    for role in ROLE_VARS.values():
        assert f"verify: {role}" in res.stdout
    assert "verify: worker_rw families=" in res.stdout and "WARNING" not in res.stdout and "FAIL" not in res.stdout
    assert not marker.exists(), marker.read_text()


def test_verify_warns_on_a_remote_url_without_tls_and_fails_on_the_wrong_role(test_db):
    urls = {var: remote(test_db[var]) for var in ROLE_VARS}
    ok = subprocess.run([sys.executable, str(SCRIPT), "--verify"], cwd=ME_DIR, env=verify_env(urls), capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "verify: WARNING WAREHOUSE_URL_WORKER points at a remote host without sslmode=require" in ok.stdout
    wrong = {**urls, "WAREHOUSE_URL_EXECUTOR": test_db["WAREHOUSE_URL_ADMIN"],
             "WAREHOUSE_URL_APP": retarget(test_db["WAREHOUSE_URL_APP"], user="app", password="wrong-pass-value")}
    res = subprocess.run([sys.executable, str(SCRIPT), "--verify"], cwd=ME_DIR, env=verify_env(wrong), capture_output=True, text=True)
    assert res.returncode == 1
    assert "verify: FAIL WAREHOUSE_URL_EXECUTOR connects as postgres, expected executor" in res.stdout
    assert "verify: FAIL app cannot connect with WAREHOUSE_URL_APP" in res.stdout
    assert "verify: worker_rw families=" in res.stdout
    for secret in ("dev-postgres", "wrong-pass-value", "dev-worker_rw"):
        assert secret not in res.stdout + res.stderr


def test_verify_fails_while_supabase_data_api_roles_reach_the_warehouse(test_db, monkeypatch, capsys):
    urls = {var: test_db[var] for var in ROLE_VARS}
    assert am.verify(urls) == 0
    monkeypatch.setattr(am, "data_api_exposure", lambda conn: ["anon: insert, select, update on 31 warehouse relations"])
    assert am.verify(urls) == 1
    assert "verify: FAIL Supabase Data API role anon: insert, select, update on 31 warehouse relations" in capsys.readouterr().out
