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
