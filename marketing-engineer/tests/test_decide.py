"""scripts/decide.py (T8): Sam's chat approvals and rejections as `actions` transitions, against the throwaway
warehouse. Each test gets its own client row."""
from __future__ import annotations

import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from warehouse.client import connect, insert

ME_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def decide_mod():
    spec = importlib.util.spec_from_file_location("script_decide", ME_DIR / "scripts" / "decide.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ctx(db_env, decide_mod, capsys):
    admin, worker = connect("sam_admin", job="test"), connect("worker", job="test")
    client = insert(admin, "clients", name="T8 decide", slug=f"t8d-{uuid.uuid4().hex[:8]}", daily_cap=Decimal("45.00"), config={})
    admin.commit()

    class Ctx:
        client_id, slug = client["id"], client["slug"]

        @staticmethod
        def propose(action_type, target_type="ad_entity", proposal=None, rule=None, evidence=None):
            row = insert(worker, "actions", client_id=client["id"], action_type=action_type, target_type=target_type,
                         target_id=str(uuid.uuid4()), proposal=proposal or {"n": 1}, rule=rule, evidence=evidence or {},
                         proposal_key=f"{client['slug']}:{uuid.uuid4().hex}")
            worker.commit()
            return row

        @staticmethod
        def action(action_id):
            row = admin.execute("select * from actions where id=%s", (action_id,)).fetchone()
            admin.rollback()
            return row

        @staticmethod
        def runs():
            rows = admin.execute("select * from runs where client_id=%s and worker='decide' order by started_at", (client["id"],)).fetchall()
            admin.rollback()
            return rows

        @staticmethod
        def run(*args, role="executor"):
            rc = decide_mod.main(["--client", client["slug"], "--as", role, *args])
            out = capsys.readouterr()
            return rc, out.out + out.err

    yield Ctx
    admin.close()
    worker.close()


def test_parse_reply(decide_mod):
    assert decide_mod.parse_reply("approve 1,2; reject 3: hook is generic; reject 5: looks like stock") == [
        ("approve", ["1", "2"], None), ("reject", ["3"], "hook is generic"), ("reject", ["5"], "looks like stock")]
    assert decide_mod.parse_reply("Approve 4 7") == [("approve", ["4", "7"], None)]
    assert decide_mod.parse_reply("approve 3f2a9c1e") == [("approve", ["3f2a9c1e"], None)]
    assert decide_mod.parse_reply("approve 20260907") == [("approve", ["20260907"], None)]   # an all-digit id prefix is an id
    with pytest.raises(decide_mod.ReplyError, match="cannot parse"):
        decide_mod.parse_reply("ship it")
    with pytest.raises(decide_mod.ReplyError):
        decide_mod.parse_reply("approve ; reject 1: x")


def test_list_numbers_proposed_actions_oldest_first_with_what_changes(ctx):
    a = ctx.propose("kill", rule="ctr_floor", evidence={"impressions": 2500, "link_ctr": 0.004})
    b = ctx.propose("scale", proposal={"adset_daily_budget": 18})
    rc, out = ctx.run("list")
    lines = out.rstrip().splitlines()
    assert rc == 0 and lines[0].startswith("  1  kill") and lines[1].startswith("  2  scale")
    assert "rule=ctr_floor" in lines[0] and '"impressions": 2500' in lines[0] and "ARCHIVED" in lines[0] and str(a["id"])[:8] in lines[0]
    assert "ad set budget → 18" in lines[1] and str(b["id"])[:8] in lines[1]
    assert lines[-1].startswith("reply:")
    assert ctx.runs() == [], "list reads only (SKILL.md §3: status-style reads write nothing)"


def test_approve_and_reject_write_chat_decisions_and_a_runs_row(ctx):
    a, b, c = ctx.propose("kill"), ctx.propose("activate", proposal={"x": [1, 2]}), ctx.propose("scale", proposal={"adset_daily_budget": 9})
    rc, out = ctx.run("approve 1,2; reject 3: too early")
    assert rc == 0, out
    for row in (ctx.action(a["id"]), ctx.action(b["id"])):
        assert row["status"] == "approved" and row["decided_by"] == "sam" and row["decision_channel"] == "chat"
        assert row["approved_payload"] == row["proposal"] and row["decided_at"] is not None and row["reject_reason"] is None
    rej = ctx.action(c["id"])
    assert rej["status"] == "rejected" and rej["reject_reason"] == "too early" and rej["decision_channel"] == "chat" and rej["decided_by"] == "sam"
    run_row = ctx.runs()[-1]
    assert run_row["status"] == "ok" and run_row["counts"] == {"approved": 2, "rejected": 1} and run_row["finished_at"] is not None
    streak = ctx.action(a["id"])  # the approved rows count toward trust_streaks as human, unchanged decisions
    assert streak["approved_payload"] == streak["proposal"]
    rc, out = ctx.run("list")
    assert out.startswith("no proposed actions")


def test_nothing_is_written_when_any_reference_fails(ctx):
    a, b = ctx.propose("kill"), ctx.propose("pause")
    rc, out = ctx.run("approve 1; reject 2")
    assert rc == 2 and "needs a reason" in out
    rc, out = ctx.run("approve 1,9")
    assert rc == 2 and "no action #9" in out
    rc, out = ctx.run("approve 2; reject 1: no")
    assert rc == 0
    rc, out = ctx.run("approve 1")
    assert rc == 2 and "action #1 is rejected" in out
    assert ctx.action(a["id"])["status"] == "rejected" and ctx.action(b["id"])["status"] == "approved"
    assert [r["status"] for r in ctx.runs()] == ["failed", "failed", "ok", "failed"]


def test_numbers_are_stable_when_rows_leave_the_listing(ctx):
    a, b, c = ctx.propose("kill"), ctx.propose("kill"), ctx.propose("activate")
    rc, out = ctx.run("list")
    assert [l.split()[0] for l in out.rstrip().splitlines()[:-1]] == ["1", "2", "3"]
    with connect("executor", job="test") as ex:   # #1 is auto-applied by the executor before Sam replies
        ex.execute("update actions set status='applied', decision_channel='auto', decided_by='executor' where id=%s", (a["id"],))
        ex.commit()
    rc, out = ctx.run("list")
    assert [l.split()[0] for l in out.rstrip().splitlines()[:-1]] == ["2", "3"]
    rc, out = ctx.run("approve 2")
    assert rc == 0 and ctx.action(b["id"])["status"] == "approved" and ctx.action(c["id"])["status"] == "proposed"


def test_sam_only_types_are_refused_under_the_executor_role_and_accepted_under_sam_admin(ctx):
    flag = ctx.propose("set_pause_flag", target_type="client", proposal={"paused": True, "reason": "test"})
    trust = ctx.propose("promote_trust", target_type="trust", proposal={"level": "execute"})
    kill = ctx.propose("kill")
    rc, out = ctx.run("approve 1,2,3")
    assert rc == 2 and "only sam_admin may approve promote_trust, set_pause_flag" in out and "WAREHOUSE_URL_SAM_ADMIN" in out
    assert all(ctx.action(r["id"])["status"] == "proposed" for r in (flag, trust, kill)), "atomic: nothing written"
    rc, out = ctx.run("approve 1,2,3", role="sam_admin")
    assert rc == 0, out
    assert all(ctx.action(r["id"])["status"] == "approved" for r in (flag, trust, kill))
    assert ctx.action(flag["id"])["decision_channel"] == "chat"


def test_failed_rows_can_be_re_approved_by_id_for_a_retry(ctx):
    a = ctx.propose("activate")
    ctx.run("approve 1")
    with connect("executor", job="test") as ex:
        ex.execute("update actions set status='failed', last_error='daily_cap' where id=%s", (a["id"],))
        ex.commit()
    rc, out = ctx.run("approve 1")
    assert rc == 0 and ctx.action(a["id"])["status"] == "approved", "a failed row can be retried by its stable number"
    with connect("executor", job="test") as ex:
        ex.execute("update actions set status='failed', last_error='daily_cap' where id=%s", (a["id"],))
        ex.commit()
    rc, out = ctx.run(f"approve {str(a['id'])[:8]}")
    assert rc == 0, out
    row = ctx.action(a["id"])
    assert row["status"] == "approved" and row["decision_channel"] == "chat"
