import os
import subprocess
from pathlib import Path

import pytest

ME_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def dev_root(tmp_path, monkeypatch):
    """Point every dev backend at a scratch DEV_ROOT so tests never touch marketing-engineer/.dev."""
    root = tmp_path / ".dev"
    monkeypatch.setenv("DEV_ROOT", str(root))
    return root


@pytest.fixture(scope="session")
def warehouse_env():
    """Local Postgres with 0001 + 0002 applied via scripts/dev_db.sh; returns the .env values. Never mocked."""
    res = subprocess.run([str(ME_DIR / "scripts" / "dev_db.sh")], capture_output=True, text=True)
    assert res.returncode == 0, f"dev_db.sh failed:\n{res.stdout}\n{res.stderr}"
    from dotenv import dotenv_values
    return dotenv_values(ME_DIR / ".env")


@pytest.fixture(scope="session")
def test_db(warehouse_env):
    """Throwaway database on the local cluster: every numbered migration in warehouse/ applied in order,
    the DRAFT seed loaded, dropped at the end of the session. Returns the six WAREHOUSE_URL_* values
    pointed at it. Use `db_env` (function-scoped) to put them in the environment so `warehouse.client.connect()`
    and scripts run in a subprocess hit this database instead of the dev database `gw`.
    Reused by every ticket after T1; never mocked.
    """
    import json
    import psycopg
    from urllib.parse import urlsplit, urlunsplit
    from warehouse.client import migration_files

    name = f"gw_test_{os.getpid()}"
    keys = [k for k in warehouse_env if k.startswith("WAREHOUSE_URL_")]
    urls = {k: urlunsplit(urlsplit(warehouse_env[k])._replace(path=f"/{name}")) for k in keys}

    with psycopg.connect(warehouse_env["WAREHOUSE_URL_ADMIN"], autocommit=True) as admin:
        admin.execute(f'drop database if exists "{name}" with (force)')
        admin.execute(f'create database "{name}"')
    with psycopg.connect(urls["WAREHOUSE_URL_ADMIN"]) as conn:
        for path in migration_files():
            conn.execute(path.read_text())
            conn.commit()
        import importlib.util
        spec = importlib.util.spec_from_file_location("seed_for_tests", ME_DIR / "scripts" / "seed.py")
        seed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed)
        families = seed.parse_families((ME_DIR / "references" / "families.md").read_text())
        seed.seed(conn, json.loads((ME_DIR / "config" / "clients" / "upclicklabs.json").read_text()), families)
        conn.commit()

    try:
        yield urls
    finally:
        with psycopg.connect(warehouse_env["WAREHOUSE_URL_ADMIN"], autocommit=True) as admin:
            admin.execute(f'drop database if exists "{name}" with (force)')


@pytest.fixture
def db_env(test_db, monkeypatch):
    """WAREHOUSE_URL_* in os.environ pointed at the throwaway database for one test (and its subprocesses)."""
    for k, v in test_db.items():
        monkeypatch.setenv(k, v)
    return test_db


@pytest.fixture(scope="session")
def meta_root(tmp_path_factory):
    """One fake Meta account (DEV_ROOT) for the whole session, shared by every test module that writes Meta ids into
    the test database: its ids keep incrementing, so the warehouse's (platform, external_id) / (platform, ad_id)
    uniqueness holds across T8 and T9 tests that share `test_db`. Modules set DEV_ROOT to it per test."""
    return tmp_path_factory.mktemp("meta-dev")
