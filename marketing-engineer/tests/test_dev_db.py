"""scripts/dev_db.sh against the real local cluster: idempotent, five roles, seed adds zero rows twice."""
import importlib.util
import subprocess

import psycopg
import pytest

from pathlib import Path

ME_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("seed_module", ME_DIR / "scripts" / "seed.py")
seed_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_module)

SCRIPT = str(ME_DIR / "scripts" / "dev_db.sh")
ROLES = ["worker_rw", "executor", "sam_admin", "app", "mcp_ro"]


def run(*args):
    return subprocess.run([SCRIPT, *args], check=True, capture_output=True, text=True)


def snapshot(admin_url):
    with psycopg.connect(admin_url) as conn:
        roles = conn.execute("select rolname, rolcanlogin, md5(rolpassword) from pg_authid where rolname = any(%s) order by 1",
                             (ROLES,)).fetchall()
        migrations = conn.execute("select name from dev_migrations order by 1").fetchall()
        tables = conn.execute("select count(*) from information_schema.tables where table_schema='public'").fetchone()
    return roles, migrations, tables


def test_second_run_changes_nothing(warehouse_env):
    admin = warehouse_env["WAREHOUSE_URL_ADMIN"]
    before = snapshot(admin)
    out = run().stdout
    assert "migrations applied now: 0" in out and "roles updated now: 0" in out
    assert snapshot(admin) == before
    names = [m[0] for m in before[1]]
    assert "schema.sql" in names and "0002_roles.sql" in names
    assert all(can_login for _, can_login, _ in before[0])
    with psycopg.connect(admin) as conn:
        assert conn.execute("select 1 from pg_extension where extname='vector'").fetchone() == (1,)


def test_verify_prints_each_role(warehouse_env):
    out = run("--verify").stdout
    for role in ROLES:
        assert f"verify: {role}" in out, out
    assert "families=" in out


def seed():
    """--seed exits 1 while families.md reuses names across kinds (see the ticket); rows still land."""
    return subprocess.run([SCRIPT, "--seed"], capture_output=True, text=True)


def test_seed_is_idempotent_and_writes_a_runs_row(warehouse_env):
    admin = warehouse_env["WAREHOUSE_URL_ADMIN"]
    seed()
    with psycopg.connect(admin) as conn:
        counts = conn.execute("select (select count(*) from families), (select count(*) from clients),"
                              " (select count(*) from offers), (select count(*) from icps)").fetchone()
        runs_before = conn.execute("select count(*) from runs where worker='seed'").fetchone()[0]
    second = seed()
    assert second.returncode == 1 and "contrarian" in second.stderr and "identity" in second.stderr
    with psycopg.connect(admin) as conn:
        assert conn.execute("select (select count(*) from families), (select count(*) from clients),"
                            " (select count(*) from offers), (select count(*) from icps)").fetchone() == counts
        assert conn.execute("select count(*) from runs where worker='seed'").fetchone()[0] == runs_before + 1
        last = conn.execute("select status, finished_at is not null, client_id is not null, error from runs"
                            " where worker='seed' order by started_at desc limit 1").fetchone()
        assert last[:3] == ("failed", True, True) and "FamilyNameConflict" in last[3]
        expected = {n for n, _ in seed_module.parse_families((ME_DIR / "references" / "families.md").read_text())}
        expected -= set(seed_module.name_conflicts(seed_module.parse_families((ME_DIR / "references" / "families.md").read_text())))
        assert expected <= {r[0] for r in conn.execute("select name from families").fetchall()}
        assert conn.execute("select config->>'_status' from clients where slug='upclicklabs'").fetchone()[0].startswith("DRAFT")
        assert conn.execute("select o.promise from offers o join clients c on c.id=o.client_id where c.slug='upclicklabs'"
                            ).fetchone()[0].startswith("PLACEHOLDER")


def test_worker_cannot_insert_clients(warehouse_env):
    with psycopg.connect(warehouse_env["WAREHOUSE_URL_WORKER"]) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("insert into clients (name, slug) values ('x', 'x')")
