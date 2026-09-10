"""scripts/checkin.py (T11) against the throwaway warehouse (conftest.test_db) and the file email backend under a
scratch DEV_ROOT. Nothing is mocked. Each test gets its own client row. FR-42 (five parts, golden body, NFR-2
content rules), FR-47 (error-rate and lead-velocity brakes with fixtures), SKILL.md §7 (crashed runs reported).

Regenerate the golden after a deliberate format change: `CHECKIN_GOLDEN_WRITE=1 python3 -m pytest tests/test_checkin.py -k golden`
and review the diff; the fixture uses fixed ids and timestamps so the body is byte-identical between runs."""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import re
import subprocess
import sys
import uuid
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

from warehouse.client import connect, insert

ME_DIR = Path(__file__).resolve().parent.parent
GOLDEN = ME_DIR / "fixtures" / "checkin" / "golden-body.txt"
NOW = dt.datetime(2026, 9, 10, 6, 0, tzinfo=dt.timezone.utc)
SINCE = NOW - dt.timedelta(hours=24)
UTC = dt.timezone.utc
BRAKES = {"error_rate_threshold": 0.3, "error_rate_window_hours": 1, "error_rate_min_runs": 3,
          "lead_velocity_multiplier": 3, "lead_velocity_window_days": 7, "lead_velocity_min_baseline": 1}
BASE_CFG = {"targets": {"ctr_floor": 0.01, "kill_impressions": 2000, "cpl_target": None}, "brakes": BRAKES}


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"script_{name}", ME_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def checkin_mod():
    return load_script("checkin")


def fixed(n: int) -> str:
    return str(uuid.UUID(int=(0x71100000 + n) << 96))


class Harness:
    def __init__(self, admin, worker, client, mod, capsys, outbox):
        self.admin, self.worker, self.client, self.mod, self.capsys, self.outbox = admin, worker, client, mod, capsys, outbox
        self.client_id, self.slug = client["id"], client["slug"]

    def ins(self, table, **v):
        row = insert(self.admin, table, **v)
        self.admin.commit()
        return row

    def sql(self, q, *params):
        self.admin.execute(q, params)
        self.admin.commit()

    def q(self, q, *params):
        rows = self.admin.execute(q, params).fetchall()
        self.admin.rollback()
        return rows

    def set_config(self, cfg):
        self.admin.execute("update clients set config=%s where id=%s", (Jsonb(cfg), self.client_id))
        self.admin.commit()

    def run(self, *args, now=NOW, since=SINCE):
        argv = ["--client", self.slug, "--now", now.isoformat(), *args]
        if since is not None:
            argv += ["--since", since.isoformat()]
        rc = self.mod.main(argv)
        out = self.capsys.readouterr()
        return rc, out.out + out.err

    def emails(self):
        out = []
        for f in sorted(self.outbox.glob("*.eml")):
            out.append(BytesParser(policy=policy.default).parsebytes(f.read_bytes()))
        return out

    def body(self, msg):
        return msg.get_body(preferencelist=("plain",)).get_content()

    def runs(self, worker="checkin"):
        return self.q("select * from runs where client_id=%s and worker=%s order by started_at", self.client_id, worker)

    def pause_proposals(self):
        return self.q("select * from actions where client_id=%s and action_type='set_pause_flag' order by created_at", self.client_id)


@pytest.fixture
def h(db_env, dev_root, monkeypatch, checkin_mod, capsys, request):
    monkeypatch.setenv("EMAIL_BACKEND", "file")
    monkeypatch.setenv("CHECKIN_TO", "sam@example.invalid")
    monkeypatch.setenv("PIPELINE_PAUSED", "false")
    admin, worker = (connect(r, job="test") for r in ("sam_admin", "worker"))
    slug = f"t11-{uuid.uuid4().hex[:8]}"
    client = insert(admin, "clients", name="T11 test", slug=slug, daily_cap=Decimal("45.00"), currency="EUR", config=BASE_CFG)
    admin.commit()
    yield Harness(admin, worker, client, checkin_mod, capsys, dev_root / "outbox")
    for c in (admin, worker):
        c.close()


# ---------- the golden scenario ----------

def golden_scenario(h: Harness):
    """One day of pipeline life with fixed ids and timestamps; every part of the email has content and the
    untrusted strings carry URLs that must not survive. Numbers (#n) follow creation order, so the two brake
    proposals the run writes itself (created now) come last."""
    at = lambda d, hh, mm=0: dt.datetime(2026, 9, d, hh, mm, tzinfo=UTC)  # noqa: E731
    h.sql("update clients set id=%s, slug='t11-golden' where id=%s", fixed(0), h.client_id)   # fixed id and slug: the body names both
    h.client_id, h.slug = uuid.UUID(fixed(0)), "t11-golden"
    cid = h.client_id
    camp = h.ins("campaigns", id=fixed(1), client_id=cid, kind="new_recipes", external_id="cmp-1001", status="ACTIVE",
                 daily_budget=Decimal("45.00"), active_lever="cost_per_link_click",
                 active_lever_reason="config floor cost_per_link_click 2.5 (no own history, see http://example.invalid/floors)",
                 active_lever_since=at(9, 20), created_at=at(8, 9))
    h.ins("campaigns", id=fixed(2), client_id=cid, kind="ablation", status="PAUSED", created_at=at(8, 9, 1))
    ad = h.ins("ad_entities", id=fixed(3), client_id=cid, campaign_id=camp["id"], adset_id="as-1", adset_daily_budget=Decimal("15.00"),
               ad_id="ad-1001", status="ACTIVE", created_at=at(8, 10))
    ad2 = h.ins("ad_entities", id=fixed(4), client_id=cid, campaign_id=camp["id"], adset_id="as-2", adset_daily_budget=Decimal("15.00"),
                ad_id="ad-1002", status="ACTIVE", created_at=at(8, 10, 1))
    # runs: an ok executor run that held one row, a crashed producer run, a failed intel run inside the window,
    # and three producer runs in the last hour of which two failed (error-rate brake fixture)
    ex_run = h.ins("runs", id=fixed(10), worker="executor", client_id=cid, started_at=at(9, 18), finished_at=at(9, 18, 1), status="ok",
                   counts={"applied": 1, "skipped_rate_limit": 1})
    h.ins("runs", id=fixed(11), worker="producer", client_id=cid, started_at=at(9, 22), status="running")
    h.ins("runs", id=fixed(12), worker="intel", client_id=cid, started_at=at(9, 23), finished_at=at(9, 23, 2), status="failed",
          error="RuntimeError: scrapecreators 503 at https://api.example.invalid/v1/ads?brand=AG1", counts={"sources_failed": ["AG1"]})
    h.ins("runs", id=fixed(13), worker="intel", client_id=cid, started_at=at(9, 23, 30), finished_at=at(9, 23, 31), status="failed",
          error="RuntimeError: scrapecreators 503 again", counts={"sources_failed": ["AG1"]})
    for i, status in enumerate(("failed", "ok", "failed")):
        h.ins("runs", id=fixed(20 + i), worker="producer", client_id=cid, started_at=at(10, 5, 10 + i), finished_at=at(10, 5, 11 + i),
              status=status, error="ValueError: render timed out" if status == "failed" else None)
    # actions in creation order: #1 kill proposed, #2 activate applied (chat), #3 kill applied (auto),
    # #4 pause failed by the executor, #5 brake proposal from the executor, #6 scale approved
    h.ins("actions", id=fixed(30), client_id=cid, action_type="kill", target_type="ad_entity", target_id=ad["id"], rule="ctr_floor",
          proposal_key="g:kill:1", evidence={"impressions": 2500, "link_ctr": 0.004, "source": "https://example.invalid/ad/1"},
          created_at=at(8, 12))
    h.ins("actions", id=fixed(31), client_id=cid, action_type="activate", target_type="ad_entity", target_id=ad2["id"], rule="sam_launch",
          proposal_key="g:activate:2", status="applied", decided_by="sam", decided_at=at(9, 11), decision_channel="chat",
          approved_payload={}, applied_at=at(9, 12), executor_run_id=ex_run["id"], attempts=1, created_at=at(9, 10))
    h.ins("actions", id=fixed(32), client_id=cid, action_type="kill", target_type="ad_entity", target_id=ad2["id"], rule="ctr_floor",
          proposal_key="g:kill:3", status="applied", decided_by="executor", decided_at=at(9, 18), decision_channel="auto",
          applied_at=at(9, 18, 30), executor_run_id=ex_run["id"], attempts=1, created_at=at(9, 15))
    h.ins("actions", id=fixed(33), client_id=cid, action_type="pause", target_type="ad_entity", target_id=ad["id"], rule="sam_request",
          proposal_key="g:pause:4", status="failed", decided_by="sam", decided_at=at(9, 17), decision_channel="chat",
          last_error="Meta 400: see https://developers.example.invalid/docs/errors#400", executor_run_id=ex_run["id"], attempts=1,
          created_at=at(9, 16))
    h.ins("actions", id=fixed(34), client_id=cid, action_type="set_pause_flag", target_type="client", target_id=str(cid),
          rule="three_consecutive_failures", proposal={"paused": True, "reason": "pause failed 3 times in a row"},
          proposal_key="g:brake:5", evidence={"action_type": "pause", "action_ids": [fixed(33)], "errors": ["Meta 400"]}, created_at=at(9, 19))
    h.ins("actions", id=fixed(35), client_id=cid, action_type="scale", target_type="ad_entity", target_id=ad2["id"], rule="scale_rule",
          proposal={"adset_daily_budget": 18}, proposal_key="g:scale:6", status="approved", decided_by="sam", decided_at=at(9, 21),
          decision_channel="chat", approved_payload={"adset_daily_budget": 18}, created_at=at(9, 20))
    h.ins("learnings", id=fixed(40), client_id=cid, scope="client", hypothesis="job-photo-bubble beats screenshot-ad on link CTR (notes: www.example.invalid/notes)",
          component_type="template", component_ref="job-photo-bubble", direction="beat", effect_size=Decimal("0.00450"), sample=120,
          posterior=Decimal("0.610"), evidence={"sample_reached": False}, status="proposed", created_by="sam", created_at=at(9, 21))
    h.ins("account_spend_hourly", client_id=cid, observed_at=at(10, 5), spend_today=Decimal("52.00"))
    # leads: one per day for the 7 baseline days, twelve in the last 24 hours (lead-velocity brake fixture)
    for i in range(7):
        h.ins("leads", client_id=cid, created_at=NOW - dt.timedelta(days=i + 1, hours=3))
    for i in range(12):
        h.ins("leads", client_id=cid, created_at=NOW - dt.timedelta(hours=1 + i))


def test_golden_body_five_parts_in_order(h):
    golden_scenario(h)
    rc, out = h.run()
    assert rc == 0, out
    msgs = h.emails()
    assert len(msgs) == 1 and msgs[0]["To"] == "sam@example.invalid"
    body = h.body(msgs[0])
    if os.environ.get("CHECKIN_GOLDEN_WRITE"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(body)
    assert body == GOLDEN.read_text()
    headings = re.findall(r"^(\d)\. ([A-Za-z ]+?) \(\d+\)$", body, re.MULTILINE)
    assert [n for n, _ in headings] == ["1", "2", "3", "4", "5"]
    assert [t for _, t in headings] == ["Actions waiting", "Actions taken", "Active lever per campaign", "New learnings", "Warnings"]
    # NFR-2: nothing from a row carries a URL; the HTML part is the escaped text
    assert "http" not in body and "www." not in body and "[url removed]" in body
    html = msgs[0].get_body(preferencelist=("html",)).get_content()
    assert "<pre" in html and "&lt;" not in body and "clients.paused" in html
    # the run row is closed with the counts and the two brakes proposed
    r = h.runs()[-1]
    assert r["status"] == "ok" and r["counts"]["sent"] == 1 and r["counts"]["brake_proposed"] == 2
    assert r["counts"]["waiting"] == 4 and r["counts"]["taken"] == 2 and r["counts"]["learnings"] == 1
    assert "counts: waiting=4 taken=2 campaigns=2 learnings=1 warnings=" in out


def test_crashed_run_is_a_warning_and_a_fresh_one_is_not(h):
    h.ins("runs", worker="gate", client_id=h.client_id, started_at=NOW - dt.timedelta(hours=2), status="running")
    h.ins("runs", worker="planner", client_id=h.client_id, started_at=NOW - dt.timedelta(minutes=3), status="running")
    rc, _ = h.run()
    assert rc == 0
    body = h.body(h.emails()[-1])
    warnings = body.split("5. Warnings")[1]
    assert "runs row left `running` by a crashed gate run" in warnings
    assert "planner" not in warnings


def test_dry_run_prints_and_sends_nothing(h, monkeypatch):
    monkeypatch.setenv("CHECKIN_TO", "")
    rc, out = h.run("--dry-run")
    assert rc == 0 and "subject: [me] check-in" in out and "1. Actions waiting (0)" in out and "   - none" in out
    assert not h.outbox.exists() or not list(h.outbox.glob("*.eml"))
    assert h.runs()[-1]["counts"]["sent"] == 0


def test_missing_recipient_fails_the_run_by_name(h, monkeypatch):
    monkeypatch.setenv("CHECKIN_TO", "")   # empty beats .env: load_env never overrides a set variable
    with pytest.raises(Exception, match="CHECKIN_TO"):
        h.run()
    r = h.runs()[-1]
    assert r["status"] == "failed" and "CHECKIN_TO" in r["error"] and "sam@" not in r["error"]


def test_error_rate_brake_has_a_fixture_and_is_idempotent(h):
    for status in ("failed", "failed", "ok", "failed"):
        h.ins("runs", worker="gate", client_id=h.client_id, started_at=NOW - dt.timedelta(minutes=20), finished_at=NOW - dt.timedelta(minutes=19),
              status=status, error="boom" if status == "failed" else None)
    h.ins("runs", worker="planner", client_id=h.client_id, started_at=NOW - dt.timedelta(minutes=20), status="failed", error="one-off")  # 1 run: below min_runs
    rc, out = h.run()
    assert rc == 0 and "brake: proposed set_pause_flag (worker_error_rate" in out
    rows = h.pause_proposals()
    assert len(rows) == 1 and rows[0]["status"] == "proposed" and rows[0]["evidence"]["worker"] == "gate"
    assert rows[0]["evidence"]["failed"] == 3 and rows[0]["evidence"]["total"] == 4 and rows[0]["proposal"]["paused"] is True
    body = h.body(h.emails()[-1])
    assert "#1 set_pause_flag client/" in body and "(approve as sam_admin)" in body and "brake tripped (worker_error_rate)" in body
    rc, _ = h.run()
    assert rc == 0 and len(h.pause_proposals()) == 1
    # the trigger holds: the worker connection cannot approve its own brake
    import psycopg
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        h.worker.execute("update actions set status='approved' where id=%s", (rows[0]["id"],))
    h.worker.rollback()


def test_lead_velocity_brake_has_a_fixture_and_respects_the_baseline(h):
    for i in range(7):
        h.ins("leads", client_id=h.client_id, created_at=NOW - dt.timedelta(days=i + 1, hours=3))   # median 1/day
    for i in range(3):
        h.ins("leads", client_id=h.client_id, created_at=NOW - dt.timedelta(hours=1 + i))          # 3 <= 3 x 1: no trip
    rc, _ = h.run()
    assert rc == 0 and h.pause_proposals() == []
    h.ins("leads", client_id=h.client_id, created_at=NOW - dt.timedelta(hours=4))                   # 4 > 3: trip
    rc, out = h.run()
    assert rc == 0 and "brake: proposed set_pause_flag (lead_velocity" in out
    rows = h.pause_proposals()
    assert len(rows) == 1 and rows[0]["evidence"]["leads_24h"] == 4 and rows[0]["evidence"]["median"] == 1.0


def test_missing_brake_config_is_a_warning_not_a_default(h):
    h.set_config({"targets": BASE_CFG["targets"]})
    for i in range(30):
        h.ins("leads", client_id=h.client_id, created_at=NOW - dt.timedelta(hours=1))
    rc, _ = h.run()
    assert rc == 0 and h.pause_proposals() == []
    body = h.body(h.emails()[-1])
    assert "lead-velocity brake not evaluated: clients.config.brakes lacks lead_velocity_multiplier" in body
    assert "error-rate brake not evaluated" in body


def test_applying_row_suspends_brakes_but_the_email_still_goes(h):
    h.ins("actions", client_id=h.client_id, action_type="kill", target_type="ad_entity", target_id=fixed(99), proposal_key="g:applying",
          status="applying", executor_run_id=fixed(98))
    for i in range(30):
        h.ins("leads", client_id=h.client_id, created_at=NOW - dt.timedelta(hours=1))
    rc, _ = h.run()
    assert rc == 0 and h.pause_proposals() == []
    body = h.body(h.emails()[-1])
    assert "1 action(s) stuck in `applying`" in body and "brakes not evaluated: 1 action(s) in `applying`" in body


def test_zero_learnings_warning_only_when_a_creative_reached_sample_size(h):
    exp = h.ins("experiments", client_id=h.client_id, name="b1")
    cre = h.ins("creatives", client_id=h.client_id, experiment_id=exp["id"], status="approved", renderer="html_template",
                template="job-photo-bubble", image_model="placeholder")
    camp = h.ins("campaigns", client_id=h.client_id, kind="new_recipes", status="ACTIVE")
    ad = h.ins("ad_entities", client_id=h.client_id, campaign_id=camp["id"], creative_id=cre["id"], ad_id=f"ad-{uuid.uuid4().hex[:6]}", status="ACTIVE")
    h.ins("ad_metrics_daily", ad_entity_id=ad["id"], day=dt.date(2026, 9, 9), fetched_on=dt.date(2026, 9, 9), impressions=1500, link_clicks=10, spend=Decimal("12.00"))
    rc, _ = h.run()
    assert "zero learnings" not in h.body(h.emails()[-1])
    h.ins("ad_metrics_daily", ad_entity_id=ad["id"], day=dt.date(2026, 9, 9), fetched_on=dt.date(2026, 9, 10), impressions=2100, link_clicks=14, spend=Decimal("15.00"))
    rc, _ = h.run()
    assert "zero learnings: 1 creative(s) reached sample size (2000 impressions)" in h.body(h.emails()[-1])
    h.ins("learnings", client_id=h.client_id, scope="client", hypothesis="x", created_by="sam", created_at=NOW - dt.timedelta(hours=1))
    rc, _ = h.run()
    assert "zero learnings" not in h.body(h.emails()[-1])
    # once the loop ran in the window, its own judgement is quoted instead (T10 writes runs.counts.warnings / learnings_refused)
    h.ins("runs", worker="loop", client_id=h.client_id, status="ok", started_at=NOW - dt.timedelta(minutes=30), finished_at=NOW - dt.timedelta(minutes=29),
          counts={"warnings": ["zero learnings: 1 creative reached sample size, see https://example.invalid/x"],
                  "learnings_refused": ["template=job-photo-bubble: 12 clicks per arm < 50"], "learnings_written": 0})
    rc, _ = h.run()
    body = h.body(h.emails()[-1])
    assert "pull insights: zero learnings: 1 creative reached sample size, see [url removed]" in body
    assert "pull insights refused 1 learning(s) below the FR-41 gates" in body and "and no `pull insights` ran" not in body


def test_window_defaults_to_the_previous_successful_checkin(h):
    rc, _ = h.run(now=NOW - dt.timedelta(days=3), since=None)
    first = h.runs()[-1]
    assert first["counts"]["since"] == (NOW - dt.timedelta(days=4)).isoformat()   # no previous check-in: 24h
    rc, _ = h.run(since=None)
    second = h.runs()[-1]
    assert second["counts"]["since"] == first["started_at"].isoformat()


def test_cli_sends_through_the_file_backend(h, db_env, dev_root):
    env = {**os.environ, "PYTHONPATH": str(ME_DIR)}
    res = subprocess.run([sys.executable, str(ME_DIR / "scripts" / "checkin.py"), "--client", h.slug, "--now", NOW.isoformat()],
                         cwd=ME_DIR, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert res.stdout.startswith("slug") and "sent <" in res.stdout and "runs " in res.stdout
    assert len(h.emails()) == 1


def test_no_side_effect_beyond_email_adapter_and_proposals():
    src = (ME_DIR / "scripts" / "checkin.py").read_text() + (ME_DIR / "scripts" / "pause.py").read_text()
    assert "adapters.meta" not in src and "get_meta" not in src and "smtplib" not in src
    assert 'connect("worker"' in src and "WAREHOUSE_URL_EXECUTOR" not in src
