"""scripts/meta_insights.py (T10) against the throwaway warehouse (conftest.test_db) and the fake Meta account under the
session DEV_ROOT. Nothing is mocked. Each test gets its own client row with its own campaign, ads and creatives, the
state T9 leaves behind after `activate`. Covers FR-2, FR-3, FR-38, FR-39, FR-40, FR-41 and stop point D."""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

from adapters.meta import get_meta
from warehouse.client import connect, insert

ME_DIR = Path(__file__).resolve().parent.parent
BASE_CONFIG = json.loads((ME_DIR / "config" / "clients" / "upclicklabs.json").read_text())
TODAY = dt.date(2026, 9, 10)


@pytest.fixture(scope="module")
def loop_mod():
    spec = importlib.util.spec_from_file_location("script_meta_insights", ME_DIR / "scripts" / "meta_insights.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Harness:
    def __init__(self, admin, worker, client, meta, mod, capsys):
        self.admin, self.worker, self.client, self.meta, self.mod, self.capsys = admin, worker, client, meta, mod, capsys
        self.client_id, self.slug = client["id"], client["slug"]
        self._n = 0

    # ---- what T9 leaves behind: a built campaign with ads and creatives
    def campaign(self, ads=2, adsets=1, budget=15, status="ACTIVE", active_on=None, families=None, components=("family", "template")):
        """One campaign in Meta and the warehouse; `ads` ads per ad set, each with its own creative. `active_on` backdates
        the ACTIVE period so the fake synthesises insights for those days."""
        self._n += 1
        name = f"{self.slug}-c{self._n}"
        camp = self.meta.create_campaign(name, objective="OUTCOME_LEADS")
        crow = insert(self.worker, "campaigns", client_id=self.client_id, kind="new_recipes", external_id=camp["id"], status=status,
                      terminal_metric="booked_call", optimisation_event="QuizStart")
        rows = []
        k = 0
        for i in range(adsets):
            adset = self.meta.create_adset(f"{name}-as{i}", campaign_id=camp["id"], daily_budget=budget, optimization_event="QuizStart", targeting={"geo": ["GB"]})
            for j in range(ads):
                fam = (families or ["ugc_selfie"])[k % len(families or ["ugc_selfie"])]
                creative = insert(self.worker, "creatives", client_id=self.client_id, status="live", headline=f"h{k}", primary_text=f"b{k}",
                                  renderer="html_template", template="job-photo-bubble")
                for ct in components:
                    insert(self.worker, "creative_components", creative_id=creative["id"], component_type=ct,
                           component_ref=fam if ct == "family" else f"{ct}-ref")
                mc = self.meta.create_creative(f"{name}-cr{k}", image_url="file:///x.png", body="b", title="t", link_url="http://localhost:8788/quiz")
                ad = self.meta.create_ad(f"{name}-ad{k}", adset_id=adset["id"], creative_id=mc["id"])
                rows.append(insert(self.worker, "ad_entities", client_id=self.client_id, campaign_id=crow["id"], creative_id=creative["id"],
                                   adset_id=adset["id"], adset_daily_budget=Decimal(str(budget)), ad_id=ad["id"], optimisation_event="QuizStart",
                                   status=status, review_status="APPROVED"))
                k += 1
        self.worker.commit()
        if status == "ACTIVE":
            on = active_on or TODAY
            self.meta.update("campaign", camp["id"], status="ACTIVE", on=on)
            for s in {r["adset_id"] for r in rows}:
                self.meta.update("adset", s, status="ACTIVE", on=on)
            for r in rows:
                self.meta.update("ad", r["ad_id"], status="ACTIVE", on=on)
        return crow, rows

    def metrics(self, ad, day, *, impressions, link_clicks, spend, fetched_on=None, **more):
        insert(self.worker, "ad_metrics_daily", ad_entity_id=ad["id"], day=day, fetched_on=fetched_on or TODAY, impressions=impressions,
               clicks=int(link_clicks * 1.2), link_clicks=link_clicks, spend=Decimal(str(spend)), **more)
        self.worker.commit()

    def leads(self, ad, n, *, stage="new", booked=False):
        for _ in range(n):
            insert(self.admin, "leads", client_id=self.client_id, ad_entity_id=ad["id"], creative_id=ad["creative_id"], stage=stage,
                   booked_verified_at=dt.datetime.now(dt.timezone.utc) if booked else None, consent={"tracking": True})
        self.admin.commit()

    def set_config(self, path, value):
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

    def runs(self):
        return self.q("select * from runs where client_id=%s and worker='loop' order by started_at", self.client_id)

    def actions(self, action_type=None):
        return self.q("select * from actions where client_id=%s and (%s::text is null or action_type=%s) order by created_at", self.client_id, action_type, action_type)

    def learnings(self):
        return self.q("select * from learnings where client_id=%s order by created_at, component_type, component_ref", self.client_id)

    def campaign_row(self, campaign_id):
        return self.q("select * from campaigns where id=%s", campaign_id)[0]

    def run(self, *args, today=TODAY):
        rc = self.mod.main(["--client", self.slug, *(["--today", today.isoformat()] if today else []), *args])
        out = self.capsys.readouterr()
        return rc, out.out + out.err


@pytest.fixture
def h(db_env, meta_root, monkeypatch, loop_mod, capsys):
    monkeypatch.setenv("DEV_ROOT", str(meta_root))
    monkeypatch.setenv("META_BACKEND", "fake")
    monkeypatch.setenv("META_FAKE_SEED", "10")
    monkeypatch.setenv("PIPELINE_PAUSED", "false")
    for var in ("META_FAKE_FAIL", "META_FAKE_THROTTLE_AFTER"):
        monkeypatch.delenv(var, raising=False)
    cfg = {k: BASE_CONFIG[k] for k in ("targets", "floors", "trust", "rate_limits", "campaign")}
    admin, worker = (connect(r, job="test") for r in ("sam_admin", "worker"))
    client = insert(admin, "clients", name="T10 test", slug=f"t10-{uuid.uuid4().hex[:8]}", daily_cap=Decimal("45.00"), currency="EUR", config=cfg)
    insert(admin, "offers", client_id=client["id"], name="AI visibility audit", funnel_host="http://localhost:8788")
    for fam in ("ugc_selfie", "stat_card"):
        admin.execute("insert into families (name, kind) values (%s, 'format') on conflict do nothing", (fam,))
    admin.commit()
    yield Harness(admin, worker, client, get_meta(), loop_mod, capsys)
    for c in (admin, worker):
        c.close()


# ---------- pure rules ----------

def test_lever_chain_is_fr2_and_hook_rate_only_for_video(loop_mod):
    m = loop_mod
    assert m.STATIC_CHAIN == ("cost_per_link_click", "quiz_start_rate", "quiz_complete_rate", "booking_rate", "cost_per_booked_call")
    assert m.lever_chain(False) == m.STATIC_CHAIN and m.lever_chain(True)[0] == "hook_rate"
    floors = BASE_CONFIG["floors"]
    kw = dict(video=False, floors=floors, cpl_target=None, kill_impressions=2000, sample_clicks=100)
    lever, reason = m.select_lever({"impressions": 500, "link_clicks": 10, "spend": 20}, **kw)
    assert lever == "cost_per_link_click" and "waiting for sample size (500/2000 impressions)" in reason and "config floor floors.cost_per_link_click" in reason
    lever, reason = m.select_lever({"impressions": 3000, "link_clicks": 30, "spend": 100}, **kw)
    assert lever == "cost_per_link_click" and "3.33 above benchmark 2.5 from config floor" in reason
    lever, reason = m.select_lever({"impressions": 3000, "link_clicks": 150, "spend": 100, "leads": 30}, **kw)
    assert lever == "quiz_start_rate" and reason.startswith("passed cost_per_link_click") and "0.2 below benchmark 0.5" in reason
    lever, reason = m.select_lever({"impressions": 3000, "link_clicks": 150, "spend": 100, "leads": 100, "completed": 50, "booked_verified": 20}, **kw)
    assert lever == "cost_per_booked_call" and "targets.cpl_target unset" in reason
    lever, reason = m.select_lever({"impressions": 3000, "link_clicks": 150, "spend": 100, "leads": 100, "completed": 50, "booked_verified": 20},
                                   **{**kw, "cpl_target": 10})
    assert lever == "cost_per_booked_call" and reason.startswith("every lever at or above benchmark")
    lever, reason = m.select_lever({"impressions": 3000, "link_clicks": 150, "spend": 100, "video_3s": 300}, **{**kw, "video": True})
    assert lever == "hook_rate" and "floors.hook_rate unset" in reason
    assert m.resolve_benchmark("cost_per_link_click", own={"cost_per_link_click": 1.9}, cross=None, floors=floors, cpl_target=None) == (1.9, "own history")
    assert m.resolve_benchmark("cost_per_link_click", own=None, cross={"cost_per_link_click": 2.1}, floors=floors, cpl_target=None) == (2.1, "mart_benchmarks")


def test_cpl_target_derivation_is_advisory_until_100_clicks(loop_mod):
    d = loop_mod.derive_cpl_target
    assert d(link_clicks=99, spend=300, booked_verified=5) == (None, "advisory: 99/100 link clicks")
    assert d(link_clicks=100, spend=300, booked_verified=0)[0] is None
    assert d(link_clicks=120, spend=300, booked_verified=5) == (Decimal("60.00"), "spend 300 / 5 verified bookings over 120 link clicks")
    assert d(link_clicks=120, spend=300, booked_verified=5, floor=80)[0] == Decimal("80")


def test_learning_gate_requires_clicks_effect_and_posterior(loop_mod):
    g = loop_mod.learning_gate
    assert g({"impressions": 1000, "link_clicks": 40}, {"impressions": 5000, "link_clicks": 200})[1].startswith("arm has 40 link clicks")
    assert "effect" in g({"impressions": 4000, "link_clicks": 60}, {"impressions": 4000, "link_clicks": 58})[1]
    fields, why = g({"impressions": 1000, "link_clicks": 52}, {"impressions": 1100, "link_clicks": 50})
    assert fields is None and why.startswith("posterior P(beat)")
    fields, why = g({"impressions": 4000, "link_clicks": 200}, {"impressions": 4000, "link_clicks": 60})
    assert why == "passed" and fields["direction"] == "beat" and fields["posterior"] >= 0.99 and fields["effect_size"] == pytest.approx(0.035)
    fields, _ = g({"impressions": 4000, "link_clicks": 60}, {"impressions": 4000, "link_clicks": 200})
    assert fields["direction"] == "miss" and fields["posterior"] >= 0.99
    assert loop_mod.posterior_beats(10, 100, 10, 100) == loop_mod.posterior_beats(10, 100, 10, 100), "seeded"
    assert loop_mod.scale_budget(15) == Decimal("18.00")


# ---------- FR-38 ----------

def test_pull_appends_daily_rows_and_a_restated_day_yields_two_rows_one_latest(h, monkeypatch):
    camp, ads = h.campaign(ads=2, active_on=TODAY - dt.timedelta(days=3))
    rc, out = h.run()
    assert rc == 0, out
    run_row = h.runs()[-1]
    assert run_row["status"] == "ok" and run_row["counts"]["metrics_rows_inserted"] == 8 and run_row["counts"]["ads"] == 2
    rows = h.q("select * from ad_metrics_daily where ad_entity_id = any(%s) order by day, fetched_on", [a["id"] for a in ads])
    assert len(rows) == 8 and {r["fetched_on"] for r in rows} == {TODAY} and min(r["day"] for r in rows) == TODAY - dt.timedelta(days=3)
    assert all(r["impressions"] > 0 and r["spend"] > 0 and r["quiz_starts"] >= 0 and r["link_ctr"] is not None for r in rows)
    spend = h.q("select * from account_spend_hourly where client_id=%s", h.client_id)
    assert len(spend) == 1 and spend[0]["spend_today"] > 0 and run_row["counts"]["spend_today"] == str(spend[0]["spend_today"])

    rc, out = h.run()                                                                    # same fetch date: nothing doubled
    assert h.runs()[-1]["counts"]["metrics_rows_inserted"] == 0 and h.runs()[-1]["counts"]["metrics_rows_seen"] == 8
    assert len(h.q("select * from account_spend_hourly where client_id=%s", h.client_id)) == 2

    monkeypatch.setenv("META_FAKE_SEED", "11")                                           # Meta restates yesterday's numbers
    tomorrow = TODAY + dt.timedelta(days=1)
    rc, out = h.run(today=tomorrow)
    assert rc == 0, out
    day = TODAY - dt.timedelta(days=1)
    both = h.q("select * from ad_metrics_daily where ad_entity_id=%s and day=%s order by fetched_on", ads[0]["id"], day)
    assert [r["fetched_on"] for r in both] == [TODAY, tomorrow] and both[0]["impressions"] != both[1]["impressions"]
    latest = h.q("select * from ad_metrics_latest where ad_entity_id=%s and day=%s", ads[0]["id"], day)
    assert len(latest) == 1 and latest[0]["fetched_on"] == tomorrow and latest[0]["impressions"] == both[1]["impressions"]
    assert h.q("select count(*) as n from ad_metrics_daily where ad_entity_id=%s", ads[0]["id"])[0]["n"] == 9   # 4 + 4 restated + 1 new day


# ---------- FR-2, FR-3 ----------

def test_active_lever_walks_the_chain_and_names_the_floor_source(h):
    camp, ads = h.campaign(ads=2, status="PAUSED")                                      # no Meta rows: the warehouse rows below decide
    h.metrics(ads[0], TODAY - dt.timedelta(days=1), impressions=3000, link_clicks=30, spend=100)
    rc, out = h.run()
    assert rc == 0, out
    row = h.campaign_row(camp["id"])
    assert row["active_lever"] == "cost_per_link_click" and row["active_lever"] in h.mod.STATIC_CHAIN
    assert "3.33 above benchmark 2.5 from config floor floors.cost_per_link_click at 3000/2000 impressions" in row["active_lever_reason"]
    assert "cpm 33.33 (context)" in row["active_lever_reason"] and row["active_lever_since"] is not None
    since = row["active_lever_since"]
    assert h.runs()[-1]["counts"]["campaigns_levered"] == 1 and h.runs()[-1]["counts"]["lever_changes"] == 1

    h.metrics(ads[0], TODAY - dt.timedelta(days=1), impressions=3000, link_clicks=150, spend=100, fetched_on=TODAY + dt.timedelta(days=1))   # restated: cheaper clicks
    rc, out = h.run()
    row = h.campaign_row(camp["id"])
    assert row["active_lever"] == "quiz_start_rate" and "passed cost_per_link_click = 0.6667 vs 2.5 (config floor" in row["active_lever_reason"]
    assert "quiz_start_rate = 0 below benchmark 0.5" in row["active_lever_reason"] and row["active_lever_since"] > since

    h.leads(ads[0], 50, stage="new")
    h.leads(ads[0], 30, stage="completed")
    h.leads(ads[0], 20, stage="booked", booked=True)
    rc, out = h.run()
    row = h.campaign_row(camp["id"])
    assert row["active_lever"] == "cost_per_booked_call" and "targets.cpl_target unset" in row["active_lever_reason"]
    h.set_config(["targets", "cpl_target"], 10)
    rc, out = h.run()
    row = h.campaign_row(camp["id"])
    assert row["active_lever"] == "cost_per_booked_call" and row["active_lever_reason"].startswith("every lever at or above benchmark")
    assert h.runs()[-1]["counts"]["lever_changes"] == 0


# ---------- FR-39, FR-40 ----------

def test_kill_scale_view_fixture_set_and_every_recommendation_becomes_a_proposal(h):
    camp, ads = h.campaign(ads=4, status="PAUSED")
    h.admin.execute("update ad_entities set status='ACTIVE' where campaign_id=%s", (camp["id"],))
    h.admin.commit()
    day = TODAY - dt.timedelta(days=1)
    h.metrics(ads[0], day, impressions=500, link_clicks=10, spend=10)                   # hold: below sample
    h.metrics(ads[1], day, impressions=2500, link_clicks=10, spend=40)                  # kill: CTR 0.004 < 0.01 at sample
    h.metrics(ads[2], day, impressions=1500, link_clicks=30, spend=60)                  # scale once cpl_target is set: 6 bookings at 10 each
    h.leads(ads[2], 6, stage="booked", booked=True)
    h.metrics(ads[3], day, impressions=1500, link_clicks=30, spend=60)                  # conversion-stage kill: 1 booking < (60/10)/3
    h.leads(ads[3], 1, stage="booked", booked=True)

    h.set_config(["targets", "ctr_floor"], None)                                      # the view says config_missing; §0 refuses before any decision
    view = {r["ad_id"]: r["recommendation"] for r in h.q("select * from mart_kill_scale_candidates where client_id=%s", h.client_id)}
    assert set(view.values()) == {"config_missing"} and len(view) == 4
    rc, out = h.run()
    assert rc == 2 and "targets.ctr_floor" in out and h.runs()[-1]["status"] == "failed" and h.actions() == []
    h.set_config(["targets", "ctr_floor"], 0.01)

    rc, out = h.run()                                                                   # cpl_target null: conversion rules hold
    assert rc == 0, out
    view = {r["ad_id"]: r["recommendation"] for r in h.q("select * from mart_kill_scale_candidates where client_id=%s", h.client_id)}
    assert view == {ads[0]["ad_id"]: "hold", ads[1]["ad_id"]: "kill", ads[2]["ad_id"]: "hold", ads[3]["ad_id"]: "hold"}
    kills = h.actions("kill")
    assert len(kills) == 1 and kills[0]["target_id"] == str(ads[1]["id"]) and kills[0]["rule"] == "ctr_floor" and kills[0]["status"] == "proposed"
    ev = kills[0]["evidence"]
    assert ev["impressions"] == 2500 and ev["link_clicks"] == 10 and ev["recommendation"] == "kill" and ev["advisory"] is False
    assert ev["window"]["fetched_on"] == TODAY.isoformat() and ev["ctr_floor"] == "0.01" and kills[0]["trust_level_at_proposal"] == "propose"
    assert "kill/scale view" in out and "recommendation" in out
    assert h.runs()[-1]["counts"]["candidates"] == {"config_missing": 0, "kill": 1, "scale": 0, "hold": 3}
    assert h.runs()[-1]["counts"]["cpl_target_derived"] is None and "advisory: 80/100 link clicks" in h.runs()[-1]["counts"]["cpl_target_reason"]

    h.set_config(["targets", "cpl_target"], 10)
    rc, out = h.run()
    view = {r["ad_id"]: r["recommendation"] for r in h.q("select * from mart_kill_scale_candidates where client_id=%s", h.client_id)}
    assert view == {ads[0]["ad_id"]: "hold", ads[1]["ad_id"]: "kill", ads[2]["ad_id"]: "scale", ads[3]["ad_id"]: "kill"}
    assert len(h.actions("kill")) == 2, "the open CTR kill is not proposed twice"
    conv = [a for a in h.actions("kill") if a["target_id"] == str(ads[3]["id"])][0]
    assert conv["rule"] == "cpl_expected_bookings" and conv["evidence"]["advisory"] is True and conv["evidence"]["booked_verified"] == 1
    scales = h.actions("scale")
    assert len(scales) == 1 and scales[0]["target_id"] == str(ads[2]["id"]) and scales[0]["rule"] == "cpl_scale"
    assert scales[0]["proposal"] == {"adset_daily_budget": "18.00", "from": "15.00"} and scales[0]["evidence"]["booked_verified"] == 6
    assert h.runs()[-1]["counts"]["kill_open"] == 1 and h.runs()[-1]["counts"]["scale_proposed"] == 1 and h.runs()[-1]["counts"]["kill_proposed"] == 1
    rc, out = h.run()
    assert len(h.actions()) == 3, "running again proposes nothing new"


def test_cpl_target_is_reported_after_100_clicks_never_written(h):
    camp, ads = h.campaign(ads=1, status="PAUSED")
    h.metrics(ads[0], TODAY - dt.timedelta(days=1), impressions=6000, link_clicks=120, spend=300)
    h.leads(ads[0], 5, stage="booked", booked=True)
    rc, out = h.run()
    counts = h.runs()[-1]["counts"]
    assert counts["cpl_target_derived"] == "60.00" and "Sam writes it as sam_admin" in out
    assert h.q("select config->'targets'->>'cpl_target' as t from clients where id=%s", h.client_id)[0]["t"] is None


# ---------- FR-41 ----------

def test_learnings_are_written_only_through_the_gates_and_updated_not_duplicated(h):
    camp, ads = h.campaign(ads=4, status="PAUSED", families=["ugc_selfie", "ugc_selfie", "stat_card", "stat_card"])
    day = TODAY - dt.timedelta(days=1)
    for a in ads[:2]:
        h.metrics(a, day, impressions=2000, link_clicks=100, spend=50)                # ugc_selfie: 5% CTR
    for a in ads[2:]:
        h.metrics(a, day, impressions=2000, link_clicks=30, spend=50)                 # stat_card: 1.5% CTR
    rc, out = h.run()
    assert rc == 0, out
    rows = h.learnings()
    assert [(r["component_type"], r["component_ref"], r["direction"]) for r in rows] == [("family", "stat_card", "miss"), ("family", "ugc_selfie", "beat")]
    beat = rows[1]
    assert beat["status"] == "proposed" and beat["created_by"] == "agent" and beat["scope"] == "client" and beat["posterior"] >= Decimal("0.99")
    assert beat["effect_size"] == Decimal("0.035") and beat["sample"] == 4000 and beat["evidence"]["sample_reached"] is True
    assert beat["evidence"]["arm"] == {"impressions": 4000, "link_clicks": 200, "creatives": sorted(str(a["creative_id"]) for a in ads[:2])}
    assert "ugc_selfie beats the other creatives on link CTR (5.00% vs 1.50%, 2 vs 2 creatives)" in beat["hypothesis"]
    counts = h.runs()[-1]["counts"]
    assert counts["learnings_written"] == 2 and counts["sample_reached"] == 4 and counts["learnings_refused"] == [] and "warnings" not in counts or counts.get("warnings") == []

    rc, out = h.run()
    assert len(h.learnings()) == 2 and h.runs()[-1]["counts"]["learnings_updated"] == 2 and h.runs()[-1]["counts"]["learnings_written"] == 0


def test_no_learning_below_the_gates_and_the_warning_only_at_sample_size(h):
    camp, ads = h.campaign(ads=2, status="PAUSED", families=["ugc_selfie", "stat_card"])
    day = TODAY - dt.timedelta(days=1)
    h.metrics(ads[0], day, impressions=900, link_clicks=20, spend=10)                   # below sample and below 50 clicks
    h.metrics(ads[1], day, impressions=900, link_clicks=18, spend=10)
    rc, out = h.run()
    counts = h.runs()[-1]["counts"]
    assert h.learnings() == [] and counts["sample_reached"] == 0 and counts.get("warnings", []) == [] and "WARNING" not in out
    assert any("below 50 per arm" in s for s in counts["learnings_refused"])

    other, (lone,) = h.campaign(ads=1, status="PAUSED", components=())                # at sample size, no components: nothing to gate
    h.admin.execute("delete from creative_components where creative_id in (select creative_id from ad_entities where campaign_id=%s)", (camp["id"],))
    h.admin.commit()
    h.metrics(lone, day, impressions=3000, link_clicks=60, spend=50)
    rc, out = h.run()
    counts = h.runs()[-1]["counts"]
    assert h.learnings() == [] and counts["sample_reached"] == 1 and counts["learnings_refused"] == []
    assert counts["warnings"] == ["zero learnings: 1 creative(s) at sample size (2000 impressions), no learning written and no gate reason recorded"]
    assert "WARNING zero learnings" in out


def test_stop_point_d_sam_writes_the_first_learning_by_hand(h):
    rc, out = h.run("--learning", "Screenshot-style ads out-click stat cards for B2B services founders")
    assert rc == 0, out
    rows = h.learnings()
    assert len(rows) == 1 and rows[0]["created_by"] == "sam" and rows[0]["status"] == "proposed" and rows[0]["scope"] == "client"
    assert rows[0]["evidence"] == {"sample_reached": False, "channel": "chat"} and rows[0]["component_type"] is None
    assert h.runs()[-1]["counts"] == {"learnings_written_by_sam": 1}
    rc, out = h.run("--learning", "  ")
    assert rc == 2 and "needs the hypothesis text" in out and len(h.learnings()) == 1


# ---------- refusals ----------

def test_paused_and_missing_config_refuse_and_close_the_runs_row(h, monkeypatch):
    monkeypatch.setenv("PIPELINE_PAUSED", "true")
    rc, out = h.run()
    assert rc == 2 and "paused" in out and h.runs()[-1]["status"] == "failed"
    monkeypatch.setenv("PIPELINE_PAUSED", "false")
    h.set_config(["targets", "kill_impressions"], None)
    rc, out = h.run()
    assert rc == 2 and "targets.kill_impressions" in out and h.runs()[-1]["status"] == "failed" and h.runs()[-1]["finished_at"] is not None
