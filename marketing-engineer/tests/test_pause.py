"""scripts/pause.py (T11): proposes set_pause_flag as a worker; Sam approves as sam_admin (decide.py) and
applies it (apply_actions.py --role sam_admin). Against the throwaway warehouse; nothing mocked. FR-44, FR-47."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from warehouse.client import connect, insert

ME_DIR = Path(__file__).resolve().parent.parent


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"script_{name}", ME_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def h(db_env, dev_root, monkeypatch, capsys):
    monkeypatch.setenv("PIPELINE_PAUSED", "false")
    monkeypatch.setenv("META_BACKEND", "fake")
    admin = connect("sam_admin", job="test")
    cfg = {"targets": {"ctr_floor": 0.01, "kill_impressions": 2000}, "trust": {}, "rate_limits": {}}
    client = insert(admin, "clients", name="T11 pause", slug=f"t11p-{uuid.uuid4().hex[:8]}", daily_cap=Decimal("45.00"), currency="EUR", config=cfg)
    admin.commit()
    mods = {n: load_script(n) for n in ("pause", "decide", "apply_actions")}

    class H:
        slug, client_id = client["slug"], client["id"]

        def run(self, script, *args):
            rc = mods[script].main(["--client", self.slug, *args])
            out = capsys.readouterr()
            return rc, out.out + out.err

        def q(self, sql, *params):
            rows = admin.execute(sql, params).fetchall()
            admin.rollback()
            return rows

        def proposals(self):
            return self.q("select * from actions where client_id=%s and action_type='set_pause_flag' order by created_at", self.client_id)

        def paused(self):
            return self.q("select paused from clients where id=%s", self.client_id)[0]["paused"]

    yield H()
    admin.close()


def test_pause_then_resume_round_trip_through_sam_admin(h):
    rc, out = h.run("pause", "pause", "--reason", "spend looks wrong")
    assert rc == 0 and "set_pause_flag paused→True proposed as #1" in out and "--as sam_admin" in out
    rows = h.proposals()
    assert len(rows) == 1 and rows[0]["status"] == "proposed" and rows[0]["rule"] == "sam_request"
    assert rows[0]["proposal"] == {"paused": True, "reason": "spend looks wrong"} and rows[0]["evidence"]["paused_before"] is False
    assert h.paused() is False                                       # a proposal flips nothing
    # a second `pause` is not a duplicate
    rc, out = h.run("pause", "pause")
    assert rc == 0 and "already open as #1" in out and len(h.proposals()) == 1
    # the executor role may not approve it; sam_admin may
    rc, out = h.run("decide", "approve 1")
    assert rc != 0 and "only sam_admin may approve set_pause_flag" in out
    rc, out = h.run("decide", "--as", "sam_admin", "approve 1")
    assert rc == 0 and h.proposals()[0]["status"] == "approved"
    rc, out = h.run("apply_actions", "--role", "sam_admin")
    assert rc == 0 and h.proposals()[0]["status"] == "applied" and h.paused() is True
    rc, out = h.run("pause", "status")
    assert rc == 0 and "clients.paused   yes" in out and "open set_pause_flag proposals  0" in out
    # resume while paused: the proposal goes through the same path and the executor applies it despite the pause
    rc, out = h.run("pause", "resume")
    assert rc == 0 and "paused→False proposed as #2" in out
    rc, _ = h.run("decide", "--as", "sam_admin", "approve 2")
    rc, _ = h.run("apply_actions", "--role", "sam_admin")
    assert rc == 0 and h.paused() is False
    runs = h.q("select worker, status, counts from runs where client_id=%s and worker='pause' order by started_at", h.client_id)
    assert [r["status"] for r in runs] == ["ok"] * 3 and runs[0]["counts"] == {"proposed": 1} and runs[1]["counts"] == {"duplicate": 1}


def test_status_reads_only_and_cli_runs_as_worker(h, db_env):
    res = subprocess.run([sys.executable, str(ME_DIR / "scripts" / "pause.py"), "--client", h.slug, "status"],
                         cwd=ME_DIR, env={**db_env, "PIPELINE_PAUSED": "true", "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    assert res.returncode == 0 and "PIPELINE_PAUSED  yes" in res.stdout and "clients.paused   no" in res.stdout
    assert h.q("select count(*) as n from runs where client_id=%s", h.client_id)[0]["n"] == 0
