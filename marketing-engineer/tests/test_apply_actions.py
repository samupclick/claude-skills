"""scripts/apply_actions.py (T8) against the throwaway warehouse (conftest.test_db) and the fake Meta account
under a scratch DEV_ROOT. Nothing is mocked. Each test gets its own client row so leftovers from other
tests never reach its queries. Covers FR-44 to FR-47 and the concurrency / crash / reconcile criteria."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from adapters.meta import get_meta
from warehouse.client import connect, insert

ME_DIR = Path(__file__).resolve().parent.parent
BASE_CONFIG = json.loads((ME_DIR / "config" / "clients" / "upclicklabs.json").read_text())


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"script_{name}", ME_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def apply_mod():
    return load_script("apply_actions")


class Harness:
    """One client, three role connections, the fake Meta account, and the executor run in-process."""

    def __init__(self, admin, worker, executor, client, meta, mod, capsys):
        self.admin, self.worker, self.executor, self.client, self.meta, self.mod, self.capsys = admin, worker, executor, client, meta, mod, capsys
        self.client_id, self.slug = client["id"], client["slug"]
        self._n = 0

    # ---- fixtures in Meta + warehouse
    def launch(self, adsets=1, ads_per_set=1, budget=15, status="PAUSED"):
        self._n += 1
        name = f"{self.slug}-c{self._n}"
        camp = self.meta.create_campaign(name, objective="OUTCOME_LEADS", status=status)
        crow = insert(self.worker, "campaigns", client_id=self.client_id, kind="new_recipes", external_id=camp["id"], status=status)
        ads = []
        for i in range(adsets):
            adset = self.meta.create_adset(f"{name}-as{i}", campaign_id=camp["id"], daily_budget=budget,
                                           optimization_event="QuizStart", targeting={"geo": ["GB"]}, status=status)
            for j in range(ads_per_set):
                creative = self.meta.create_creative(f"{name}-cr{i}-{j}", image_url="file:///x.png", body="b", title="t",
                                                     link_url="http://localhost:8788/quiz?utm_content=x")
                ad = self.meta.create_ad(f"{name}-ad{i}-{j}", adset_id=adset["id"], creative_id=creative["id"], status=status)
                ads.append(insert(self.worker, "ad_entities", client_id=self.client_id, campaign_id=crow["id"], adset_id=adset["id"],
                                  adset_daily_budget=Decimal(str(budget)), ad_id=ad["id"], optimisation_event="QuizStart", status=status))
        self.worker.commit()
        return crow, ads

    def propose(self, action_type, target_type, target_id, proposal=None, rule=None, evidence=None, key=None):
        row = insert(self.worker, "actions", client_id=self.client_id, action_type=action_type, target_type=target_type,
                     target_id=str(target_id), proposal=proposal or {}, rule=rule, evidence=evidence or {},
                     proposal_key=key or f"{self.slug}:{action_type}:{target_id}:{uuid.uuid4().hex[:6]}")
        self.worker.commit()
        return row

    def approve(self, action_id, role=None, channel="chat"):
        conn = role or self.executor
        conn.execute("update actions set status='approved', decided_by='sam', decided_at=now(), decision_channel=%s,"
                     " approved_payload=proposal where id=%s", (channel, action_id))
        conn.commit()

    def approved(self, action_type, target_type, target_id, **kw):
        row = self.propose(action_type, target_type, target_id, **kw)
        self.approve(row["id"])
        return row

    def set_config(self, path: list[str], value):
        cfg = self.admin.execute("select config from clients where id=%s", (self.client_id,)).fetchone()["config"]
        node = cfg
        for k in path[:-1]:
            node = node.setdefault(k, {})
        node[path[-1]] = value
        self.admin.execute("update clients set config=%s where id=%s", (Jsonb(cfg), self.client_id))
        self.admin.commit()

    # ---- reads
    def q(self, sql, *params):
        rows = self.admin.execute(sql, params).fetchall()
        self.admin.rollback()
        return rows

    def action(self, action_id):
        return self.q("select * from actions where id=%s", action_id)[0]

    def ad(self, ad_entity_id):
        return self.q("select * from ad_entities where id=%s", ad_entity_id)[0]

    def paused(self):
        return self.q("select paused from clients where id=%s", self.client_id)[0]["paused"]

    def runs(self, worker="executor"):
        return self.q("select * from runs where client_id=%s and worker=%s order by started_at", self.client_id, worker)

    def pause_proposals(self):
        return self.q("select * from actions where client_id=%s and action_type='set_pause_flag' order by created_at", self.client_id)

    # ---- the executor
    def run(self, *args, role="executor"):
        rc = self.mod.main(["--client", self.slug, "--role", role, *args])
        out = self.capsys.readouterr()
        return rc, out.out + out.err


@pytest.fixture
def h(db_env, meta_root, monkeypatch, apply_mod, capsys):
    monkeypatch.setenv("DEV_ROOT", str(meta_root))
    monkeypatch.setenv("META_BACKEND", "fake")
    monkeypatch.setenv("META_FAKE_SEED", "3")
    monkeypatch.setenv("PIPELINE_PAUSED", "false")
    for var in ("META_FAKE_FAIL", "META_FAKE_THROTTLE_AFTER"):
        monkeypatch.delenv(var, raising=False)
    cfg = {k: BASE_CONFIG[k] for k in ("targets", "trust", "rate_limits", "campaign")}
    admin, worker, executor = (connect(r, job="test") for r in ("sam_admin", "worker", "executor"))
    client = insert(admin, "clients", name="T8 test", slug=f"t8-{uuid.uuid4().hex[:8]}", daily_cap=Decimal("45.00"), currency="EUR", config=cfg)
    admin.commit()
    yield Harness(admin, worker, executor, client, get_meta(), apply_mod, capsys)
    for c in (admin, worker, executor):
        c.close()


# ---------- boundary ----------

def test_meta_write_endpoints_exist_only_in_the_executor():
    hits = subprocess.run(
        ["grep", "-rlE", r"\b(create_campaign|create_adset|create_creative|create_ad)\(|\bmeta\.update\(", "--include=*.py", "."],
        cwd=ME_DIR, capture_output=True, text=True).stdout.split()
    outside = {p for p in hits if not p.startswith(("./tests/", "./adapters/meta/"))}
    assert outside == {"./scripts/apply_actions.py"}, outside
    decide_src = (ME_DIR / "scripts" / "decide.py").read_text()
    assert "adapters.meta" not in decide_src and "get_meta" not in decide_src


def test_0002_guards_raise_for_every_sam_only_type(h):
    """FR-44: the executor may transition actions, but not approve promote_trust / quote_release / set_pause_flag."""
    for t, target in (("promote_trust", "kill"), ("quote_release", str(uuid.uuid4())), ("set_pause_flag", h.client_id)):
        row = h.propose(t, {"promote_trust": "trust", "quote_release": "lead", "set_pause_flag": "client"}[t], target)
        with pytest.raises(psycopg.errors.RaiseException, match=f"only sam_admin may approve {t}"):
            h.executor.execute("update actions set status='approved' where id=%s", (row["id"],))
        h.executor.rollback()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            h.worker.execute("update actions set status='approved' where id=%s", (row["id"],))
        h.worker.rollback()
    with pytest.raises(psycopg.errors.RaiseException, match="workers may only propose"):
        insert(h.worker, "actions", client_id=h.client_id, action_type="pause", target_type="ad_entity", target_id="x",
               proposal_key=f"{h.slug}:approved-by-worker", status="approved")
    h.worker.rollback()


# ---------- the state machine ----------

def test_applies_approved_kill_and_pause_then_mirrors_meta(h):
    _, (a1, a2) = h.launch(adsets=2, status="ACTIVE")
    kill = h.approved("kill", "ad_entity", a1["id"], rule="ctr_floor", evidence={"impressions": 2500})
    pause = h.approved("pause", "ad_entity", a2["id"])
    rc, out = h.run()
    assert rc == 0 and out.startswith("slug") and "applied" in out
    assert h.meta.get("ad", a1["ad_id"])["status"] == "ARCHIVED" and h.meta.get("ad", a2["ad_id"])["status"] == "PAUSED"
    assert h.ad(a1["id"])["status"] == "ARCHIVED" and h.ad(a2["id"])["status"] == "PAUSED"
    run_row = h.runs()[-1]
    for row in (h.action(kill["id"]), h.action(pause["id"])):
        assert row["status"] == "applied" and row["applied_at"] is not None and row["attempts"] == 1
        assert row["executor_run_id"] == run_row["id"] and row["decision_channel"] == "chat" and row["last_error"] is None
    assert run_row["status"] == "ok" and run_row["finished_at"] is not None and run_row["counts"] == {"applied": 2}


def test_activate_checks_daily_cap_after_budgets_and_refuses_disapproved(h):
    _, ads = h.launch(adsets=5, budget=15)   # 5 ad sets at €15 against a €45 cap
    rows = [h.approved("activate", "ad_entity", a["id"]) for a in ads[:4]]
    h.admin.execute("update ad_entities set review_status='DISAPPROVED' where id=%s", (ads[4]["id"],))
    h.admin.commit()
    bad = h.approved("activate", "ad_entity", ads[4]["id"])
    rc, out = h.run()
    assert rc == 0
    for a, r in zip(ads[:3], rows[:3]):
        assert h.action(r["id"])["status"] == "applied"
        ad = h.ad(a["id"])
        assert ad["status"] == "ACTIVE" and ad["launched_at"] is not None and ad["review_status"] == "APPROVED"
        assert h.meta.get("ad", a["ad_id"])["status"] == "ACTIVE"
    fourth = h.action(rows[3]["id"])
    assert fourth["status"] == "failed" and fourth["last_error"] == "daily_cap" and fourth["attempts"] == 0
    assert h.ad(ads[3]["id"])["status"] == "PAUSED" and h.meta.get("ad", ads[3]["ad_id"])["status"] == "PAUSED"
    assert h.action(bad["id"])["last_error"] == "disapproved" and h.meta.get("ad", ads[4]["ad_id"])["status"] == "PAUSED"
    assert h.q("select check_daily_cap(%s) as ok", h.client_id)[0]["ok"] is True
    assert h.runs()[-1]["counts"] == {"applied": 3, "failed": 2}


def test_scale_enforces_step_and_cap_and_updates_every_ad_in_the_ad_set(h):
    _, ads = h.launch(adsets=3, ads_per_set=1, budget=15, status="ACTIVE")   # 45 = cap
    over = h.approved("scale", "ad_entity", ads[0]["id"], proposal={"adset_daily_budget": 18})
    rc, _ = h.run()
    assert h.action(over["id"])["last_error"] == "daily_cap"
    assert h.meta.get("adset", ads[0]["adset_id"])["daily_budget"] == 15.0
    h.approved("pause", "ad_entity", ads[2]["id"])                                   # frees €15
    ok = h.approved("scale", "ad_entity", ads[0]["id"], proposal={"adset_daily_budget": 18})
    step = h.approved("scale", "ad_entity", ads[1]["id"], proposal={"adset_daily_budget": 30})
    junk = h.approved("scale", "ad_entity", ads[1]["id"], proposal={})
    rc, _ = h.run()
    assert rc == 0
    assert h.action(ok["id"])["status"] == "applied" and h.meta.get("adset", ads[0]["adset_id"])["daily_budget"] == 18.0
    assert h.ad(ads[0]["id"])["adset_daily_budget"] == Decimal("18.00")
    assert h.action(step["id"])["last_error"].startswith("budget_step") and h.meta.get("adset", ads[1]["adset_id"])["daily_budget"] == 15.0
    assert "adset_daily_budget" in h.action(junk["id"])["last_error"]


def test_paused_client_and_global_flag_leave_rows_untouched(h, monkeypatch):
    _, (ad,) = h.launch(status="ACTIVE")
    kill = h.approved("kill", "ad_entity", ad["id"])
    h.admin.execute("update clients set paused=true where id=%s", (h.client_id,))
    h.admin.commit()
    rc, out = h.run()
    assert rc == 0 and "paused" in out
    assert h.action(kill["id"]) == h.action(kill["id"]) and h.action(kill["id"])["status"] == "approved"
    assert h.meta.get("ad", ad["ad_id"])["status"] == "ACTIVE" and h.runs()[-1]["counts"] == {"skipped_paused": 1}
    h.admin.execute("update clients set paused=false where id=%s", (h.client_id,))
    h.admin.commit()
    monkeypatch.setenv("PIPELINE_PAUSED", "true")
    rc, _ = h.run()
    assert h.action(kill["id"])["status"] == "approved" and h.action(kill["id"])["attempts"] == 0
    monkeypatch.setenv("PIPELINE_PAUSED", "false")
    rc, _ = h.run()
    assert h.action(kill["id"])["status"] == "applied" and h.meta.get("ad", ad["ad_id"])["status"] == "ARCHIVED"


def test_set_pause_flag_is_applied_only_under_sam_admin_and_works_while_paused(h):
    stop = h.propose("set_pause_flag", "client", h.client_id, proposal={"paused": True, "reason": "test"})
    h.approve(stop["id"], role=h.admin)
    rc, out = h.run()                                                                  # executor role
    assert rc == 0 and h.action(stop["id"])["status"] == "approved" and "sam_admin" in out and h.paused() is False
    rc, out = h.run(role="sam_admin")
    assert rc == 0 and h.action(stop["id"])["status"] == "applied" and h.paused() is True
    assert h.runs()[-1]["counts"] == {"applied": 1}
    _, (ad,) = h.launch(status="ACTIVE")
    kill = h.approved("kill", "ad_entity", ad["id"])
    rc, out = h.run(role="sam_admin")                                                  # never touches Meta
    assert h.action(kill["id"])["status"] == "approved" and "executor role" in out
    resume = h.propose("set_pause_flag", "client", h.client_id, proposal={"paused": False, "reason": "resume"})
    h.approve(resume["id"], role=h.admin)
    rc, _ = h.run(role="sam_admin")
    assert h.action(resume["id"])["status"] == "applied" and h.paused() is False
    rc, _ = h.run()
    assert h.action(kill["id"])["status"] == "applied"


# ---------- FR-46 trust ----------

def test_trust_execute_auto_applies_never_counts_rate_limits_and_demotes_on_failure(h, monkeypatch):
    _, ads = h.launch(adsets=6, budget=5, status="ACTIVE")
    h.set_config(["trust", "kill"], {"threshold": 2, "unit": "action", "level": "execute"})
    k1, k2 = (h.approved("kill", "ad_entity", a["id"]) for a in ads[:2])
    h.run()
    streak = lambda: h.q("select streak, threshold, level from trust_streaks where client_id=%s and action_type='kill'", h.client_id)[0]
    assert streak() == {"streak": 2, "threshold": 2, "level": "execute"}

    k3 = h.propose("kill", "ad_entity", ads[2]["id"])                                  # no approval
    rc, out = h.run()
    row = h.action(k3["id"])
    assert row["status"] == "applied" and row["decision_channel"] == "auto" and row["decided_by"] == "executor"
    assert row["approved_payload"] == row["proposal"] and row["decided_at"] is not None
    assert h.meta.get("ad", ads[2]["ad_id"])["status"] == "ARCHIVED" and "(auto)" in out
    assert streak()["streak"] == 2, "an auto decision never increments a streak"
    assert h.runs()[-1]["counts"] == {"applied_auto": 1}

    k4 = h.propose("kill", "ad_entity", ads[3]["id"])                                  # 3 kills applied today already
    rc, out = h.run()
    assert h.action(k4["id"])["status"] == "proposed" and "max_kills_per_day=3" in out
    assert h.runs()[-1]["counts"] == {"skipped_rate_limit": 1}
    h.set_config(["rate_limits", "max_kills_per_day"], 10)
    rc, out = h.run()
    assert h.action(k4["id"])["status"] == "proposed" and "max_share_of_live_ads_killed_per_day=0.5" in out
    h.set_config(["rate_limits", "max_share_of_live_ads_killed_per_day"], 1.0)
    rc, _ = h.run()
    assert h.action(k4["id"])["status"] == "applied"

    monkeypatch.setenv("META_FAKE_FAIL", "update")
    k5 = h.propose("kill", "ad_entity", ads[4]["id"])
    rc, _ = h.run()
    assert h.action(k5["id"])["status"] == "failed" and "injected failure before update" in h.action(k5["id"])["last_error"]
    assert h.meta.get("ad", ads[4]["ad_id"])["status"] == "ACTIVE" and h.ad(ads[4]["id"])["status"] == "ACTIVE"
    monkeypatch.delenv("META_FAKE_FAIL")
    k6 = h.propose("kill", "ad_entity", ads[5]["id"])
    rc, out = h.run()
    assert h.action(k6["id"])["status"] == "proposed" and "demoted" in out
    assert streak()["level"] == "execute", "config is unchanged; demotion is computed from the failure"

    blind = h.propose("promote_trust", "trust", "kill", proposal={"level": "execute"})
    weak = h.propose("promote_trust", "trust", "kill", proposal={"level": "execute", "backtest_accuracy": 0.7})
    promote = h.propose("promote_trust", "trust", "kill", proposal={"level": "execute", "backtest_accuracy": 0.85})
    for r in (blind, weak, promote):
        h.approve(r["id"], role=h.admin)
    rc, _ = h.run(role="sam_admin")
    assert "backtest_accuracy" in h.action(blind["id"])["last_error"] and "below 0.8" in h.action(weak["id"])["last_error"]
    assert h.action(promote["id"])["status"] == "applied"
    rc, _ = h.run()
    assert h.action(k6["id"])["status"] == "applied" and h.action(k6["id"])["decision_channel"] == "auto"


def test_scale_cooldown_applies_to_autonomous_scales(h):
    _, ads = h.launch(adsets=1, budget=10, status="ACTIVE")
    h.set_config(["trust", "scale"], {"threshold": 1, "unit": "action", "level": "execute"})
    first = h.approved("scale", "ad_entity", ads[0]["id"], proposal={"adset_daily_budget": 12})
    h.run()
    assert h.action(first["id"])["status"] == "applied"
    second = h.propose("scale", "ad_entity", ads[0]["id"], proposal={"adset_daily_budget": 14})
    rc, out = h.run()
    assert h.action(second["id"])["status"] == "proposed" and "one scale per ad per 72h" in out
    h.set_config(["rate_limits", "scale_cooldown_hours"], None)
    rc, out = h.run()
    assert h.action(second["id"])["status"] == "proposed" and "scale_cooldown_hours missing" in out


# ---------- FR-47 brakes ----------

def test_three_consecutive_failures_propose_set_pause_flag_once(h, monkeypatch):
    _, ads = h.launch(adsets=5, status="ACTIVE")
    monkeypatch.setenv("META_FAKE_FAIL", "update")
    kills = [h.approved("kill", "ad_entity", a["id"]) for a in ads[:2]]
    h.run()
    assert h.pause_proposals() == [] and all(h.action(k["id"])["status"] == "failed" for k in kills)
    third = h.approved("kill", "ad_entity", ads[2]["id"])
    rc, out = h.run()
    props = h.pause_proposals()
    assert len(props) == 1 and "brake: proposed set_pause_flag" in out
    p = props[0]
    assert p["status"] == "proposed" and p["rule"] == "three_consecutive_failures" and p["proposal"]["paused"] is True
    assert p["target_type"] == "client" and p["target_id"] == str(h.client_id)
    assert p["evidence"]["action_type"] == "kill" and len(p["evidence"]["action_ids"]) == 3 and str(third["id"]) in p["evidence"]["action_ids"]
    assert h.runs()[-1]["counts"] == {"failed": 1, "brake_proposed": 1}
    h.approved("kill", "ad_entity", ads[3]["id"])
    h.run()
    assert len(h.pause_proposals()) == 1, "one open brake proposal per rule and type"
    monkeypatch.delenv("META_FAKE_FAIL")
    okay = h.approved("kill", "ad_entity", ads[4]["id"])
    h.run()
    assert h.action(okay["id"])["status"] == "applied" and len(h.pause_proposals()) == 1


def test_hourly_spend_over_cap_proposes_pause_and_holds_budget_actions(h):
    _, ads = h.launch(adsets=2, status="ACTIVE")
    insert(h.worker, "account_spend_hourly", client_id=h.client_id, observed_at=dt.datetime.now(dt.timezone.utc), spend_today=Decimal("46.10"))
    h.worker.commit()
    h.admin.execute("update ad_entities set status='PAUSED' where id=%s", (ads[1]["id"],))
    h.admin.commit()
    h.meta.update("ad", ads[1]["ad_id"], status="PAUSED")
    activate = h.approved("activate", "ad_entity", ads[1]["id"])
    kill = h.approved("kill", "ad_entity", ads[0]["id"])
    rc, out = h.run()
    props = h.pause_proposals()
    assert len(props) == 1 and props[0]["rule"] == "hourly_spend_over_cap" and props[0]["evidence"]["spend_today"] == "46.10"
    assert h.action(activate["id"])["status"] == "approved" and h.meta.get("ad", ads[1]["ad_id"])["status"] == "PAUSED"
    assert h.action(kill["id"])["status"] == "applied"
    assert h.runs()[-1]["counts"] == {"applied": 1, "brake_proposed": 1, "skipped_brake": 1}
    h.run()
    assert len(h.pause_proposals()) == 1


# ---------- FR-45 concurrency, crash, reconcile ----------

def test_two_concurrent_executors_apply_each_action_once(h):
    _, ads = h.launch(adsets=4, status="ACTIVE")
    kills = [h.approved("kill", "ad_entity", a["id"]) for a in ads]
    cmd = [sys.executable, str(ME_DIR / "scripts" / "apply_actions.py"), "--client", h.slug]
    procs = [subprocess.Popen(cmd, cwd=ME_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for _ in range(2)]
    outs = [p.communicate(timeout=120)[0] for p in procs]
    assert [p.returncode for p in procs] == [0, 0], outs
    for k, a in zip(kills, ads):
        row = h.action(k["id"])
        assert row["status"] == "applied" and row["attempts"] == 1, row
        assert h.meta.get("ad", a["ad_id"])["status"] == "ARCHIVED"
    runs = h.runs()
    assert len(runs) == 2 and all(r["status"] == "ok" for r in runs)
    assert sum(r["counts"].get("applied", 0) for r in runs) == 4
    assert {r["executor_run_id"] for r in map(lambda k: h.action(k["id"]), kills)} <= {r["id"] for r in runs}


def test_crash_after_the_meta_call_marks_failed_mirrors_meta_and_converges_on_rerun(h, monkeypatch):
    _, (ad,) = h.launch()
    activate = h.approved("activate", "ad_entity", ad["id"])
    monkeypatch.setenv("META_FAKE_FAIL", "update:after")
    rc, out = h.run()
    row = h.action(activate["id"])
    assert row["status"] == "failed" and "injected failure after update" in row["last_error"] and row["attempts"] == 1
    assert h.meta.get("ad", ad["ad_id"])["status"] == "ACTIVE", "Meta applied it before the error"
    assert h.ad(ad["id"])["status"] == "ACTIVE", "the warehouse mirrors Meta even on the failure path"
    monkeypatch.delenv("META_FAKE_FAIL")
    h.approve(activate["id"])                                                          # Sam re-approves the failed row
    rc, _ = h.run()
    row = h.action(activate["id"])
    assert row["status"] == "applied" and row["attempts"] == 2 and row["last_error"] is None
    objs = json.loads((Path(h.meta.state_path)).read_text())["objects"]["ad"]
    assert [o["name"] for o in objs.values()].count(h.meta.get("ad", ad["ad_id"])["name"]) == 1


def test_ensure_object_reuses_the_object_a_crashed_create_left_behind(h, monkeypatch):
    mod = h.mod
    name = f"{h.slug}-orphan"
    monkeypatch.setenv("META_FAKE_FAIL", "create_campaign:after")
    with pytest.raises(Exception, match="after create_campaign"):
        mod.ensure_object(h.meta, "campaign", name, lambda: h.meta.create_campaign(name, objective="OUTCOME_LEADS"))
    monkeypatch.delenv("META_FAKE_FAIL")
    obj, created = mod.ensure_object(h.meta, "campaign", name, lambda: h.meta.create_campaign(name, objective="OUTCOME_LEADS"))
    assert created is False and obj["name"] == name
    objs = json.loads(Path(h.meta.state_path).read_text())["objects"]["campaign"]
    assert [o["name"] for o in objs.values()].count(name) == 1


def _stuck(h, action, minutes):
    """Put an approved action into `applying` under an executor run that started `minutes` ago."""
    run_row = insert(h.executor, "runs", worker="executor", client_id=h.client_id)
    h.executor.execute("update actions set status='applying', executor_run_id=%s, attempts=1 where id=%s", (run_row["id"], action["id"]))
    h.executor.commit()
    h.admin.execute("update runs set started_at = now() - make_interval(mins => %s), finished_at = now() - make_interval(mins => %s)"
                    " where id=%s", (minutes, minutes, run_row["id"]))
    h.admin.commit()


def test_reconcile_settles_stale_applying_rows_from_meta_and_never_resends(h):
    _, ads = h.launch(adsets=3)
    done, undone = (h.approved("activate", "ad_entity", a["id"]) for a in ads[:2])
    _stuck(h, done, 20)
    _stuck(h, undone, 20)
    h.meta.update("ad", ads[0]["ad_id"], status="ACTIVE")                              # the crashed executor got this far
    calls_before = json.loads(Path(h.meta.state_path).read_text())["calls"]
    rc, out = h.run()
    assert rc == 2 and "applying" in out and h.runs()[-1]["status"] == "failed" and "reconcile" in h.runs()[-1]["error"]
    assert h.action(done["id"])["status"] == "applying" and json.loads(Path(h.meta.state_path).read_text())["calls"] == calls_before
    later = h.approved("kill", "ad_entity", ads[2]["id"])
    rc, out = h.run("--reconcile")
    assert rc == 0, out
    assert h.action(done["id"])["status"] == "applied" and h.ad(ads[0]["id"])["status"] == "ACTIVE"
    failed = h.action(undone["id"])
    assert failed["status"] == "failed" and failed["last_error"].startswith("reconcile:") and "expected ACTIVE" in failed["last_error"]
    assert h.meta.get("ad", ads[1]["ad_id"])["status"] == "PAUSED", "never re-sent"
    assert h.action(later["id"])["status"] == "applied", "the normal pass runs once nothing is stuck"
    assert h.runs()[-1]["counts"] == {"reconciled_applied": 1, "reconciled_failed": 1, "applied": 1}


def test_young_applying_rows_block_both_modes(h):
    _, (ad,) = h.launch()
    fresh = h.approved("activate", "ad_entity", ad["id"])
    _stuck(h, fresh, 1)
    rc, out = h.run("--reconcile")
    assert rc == 2 and h.action(fresh["id"])["status"] == "applying"
    run_row = h.runs()[-1]
    assert run_row["status"] == "failed" and run_row["counts"] == {"applying_recent": 1}
    rc, out = h.run("--reconcile", "--stale-minutes", "0")
    assert rc == 0 and h.action(fresh["id"])["status"] == "failed"


# ---------- runs row and config refusal ----------

def test_config_missing_refuses_to_run_and_still_closes_the_runs_row(h):
    h.set_config(["targets", "ctr_floor"], None)
    rc, out = h.run()
    assert rc == 2 and "targets.ctr_floor" in out
    row = h.runs()[-1]
    assert row["status"] == "failed" and "targets.ctr_floor" in row["error"] and row["finished_at"] is not None


def test_target_problems_fail_the_row_without_touching_meta(h):
    _, (ad,) = h.launch(status="ACTIVE")
    junk = h.approved("kill", "ad_entity", "not-a-uuid")
    gone = h.approved("kill", "ad_entity", uuid.uuid4())
    other = h.approved("publish_post", "post", uuid.uuid4())
    rc, out = h.run()
    assert "not a uuid" in h.action(junk["id"])["last_error"] and "not found" in h.action(gone["id"])["last_error"]
    assert h.action(other["id"])["status"] == "approved" and "not handled in phase 0" in out
    assert h.meta.get("ad", ad["ad_id"])["status"] == "ACTIVE"
