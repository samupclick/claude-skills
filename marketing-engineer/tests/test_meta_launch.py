"""scripts/meta_launch.py (T9) and the `build_campaign` / cascade `activate` executor paths in
scripts/apply_actions.py, against the throwaway warehouse (conftest.test_db, migrations 0001–0007 applied) and the
fake Meta account under a scratch DEV_ROOT. Nothing is mocked. Each test gets its own client row with its own
offer, experiment, briefs, creatives (full components) and Sam's gate verdicts, the state T5/T6 leave behind.
Covers FR-1, FR-30, FR-31, FR-32, FR-37 and the "running it twice yields one action" criterion."""
from __future__ import annotations

import importlib.util
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from psycopg.types.json import Jsonb

from adapters.meta import get_meta
from warehouse.client import connect, insert
from warehouse.launch import REQUIRED_COMPONENTS, ProposalInvalid, ad_url, validate_build_campaign

ME_DIR = Path(__file__).resolve().parent.parent
BASE_CONFIG = json.loads((ME_DIR / "config" / "clients" / "upclicklabs.json").read_text())
FUNNEL = "http://localhost:8788"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"script_{name}", ME_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def launch_mod():
    return load_script("meta_launch")


@pytest.fixture(scope="module")
def apply_mod():
    return load_script("apply_actions")


@pytest.fixture(scope="module")
def decide_mod():
    return load_script("decide")


class Harness:
    def __init__(self, admin, worker, executor, client, offer, meta, mods, capsys):
        self.admin, self.worker, self.executor, self.client, self.offer, self.meta, self.capsys = admin, worker, executor, client, offer, meta, capsys
        self.launch_mod, self.apply_mod, self.decide_mod = mods
        self.client_id, self.slug = client["id"], client["slug"]

    # ---- what T4/T5/T6 leave behind
    def batch(self, recipes=3, per_recipe=2, verdict="approve", renderer="html_template", components=REQUIRED_COMPONENTS, name="batch-001"):
        """An experiment with `recipes` chosen briefs and `per_recipe` creatives each; Sam's latest verdict per creative
        is `verdict` (a string, or a callable of the creative index). Returns (experiment, creatives)."""
        exp = insert(self.worker, "experiments", client_id=self.client_id, offer_id=self.offer["id"], name=name, kind="new_recipes", capacity=6)
        pattern = insert(self.worker, "patterns", origin="external", source_list="dtc", family="ugc_selfie", status="proven", source_brand="AG1")
        creatives = []
        i = 0
        for r in range(recipes):
            brief = insert(self.worker, "briefs", client_id=self.client_id, experiment_id=exp["id"], offer_id=self.offer["id"],
                           source_pattern_id=pattern["id"], family="ugc_selfie", angle=f"angle {r}", spec={"proposal_number": r + 1, "chosen": True})
            for _ in range(per_recipe):
                i += 1
                c = insert(self.worker, "creatives", client_id=self.client_id, brief_id=brief["id"], experiment_id=exp["id"],
                           status="approved" if verdict == "approve" else "gated",
                           primary_text=f"body {i}", headline=f"headline {i}", renderer=renderer(i) if callable(renderer) else renderer,
                           template="job-photo-bubble", image_model="placeholder", asset_urls=[f"file:///dev/storage/creatives/{i}.png"],
                           sizes=["1080x1080"])
                for ct in components:
                    insert(self.worker, "creative_components", creative_id=c["id"], component_type=ct,
                           component_ref=f"{FUNNEL}/quiz" if ct == "landing_page" else f"{ct}-ref")
                insert(self.worker, "gate_scores", creative_id=c["id"], attempt=1, scored_by="agent", mode="shadow", verdict="approve",
                       decision_channel="auto", hard_checks={"components": "pass"}, passed=True)
                v = verdict(i) if callable(verdict) else verdict
                if v:
                    insert(self.worker, "gate_scores", creative_id=c["id"], attempt=1, scored_by="sam", mode="shadow", verdict=v,
                           decision_channel="chat", passed=v == "approve")
                creatives.append(c)
        self.worker.commit()
        return exp, creatives

    # ---- reads
    def q(self, sql, *params):
        rows = self.admin.execute(sql, params).fetchall()
        self.admin.rollback()
        return rows

    def actions(self, action_type=None):
        return self.q("select * from actions where client_id=%s and (%s::text is null or action_type=%s) order by created_at, id",
                      self.client_id, action_type, action_type)

    def action(self, action_id):
        return self.q("select * from actions where id=%s", action_id)[0]

    def campaigns(self):
        return self.q("select * from campaigns where client_id=%s order by created_at", self.client_id)

    def ads(self):
        return self.q("select * from ad_entities where client_id=%s order by adset_id, created_at", self.client_id)

    def runs(self, worker):
        return self.q("select * from runs where client_id=%s and worker=%s order by started_at", self.client_id, worker)

    def meta_objects(self, kind):
        """This client's objects in the fake account (one account serves the whole session; names carry the slug)."""
        return [o for o in json.loads(Path(self.meta.state_path).read_text())["objects"][kind].values() if o["name"].startswith(self.slug)]

    # ---- the scripts, in-process
    def launch(self):
        rc = self.launch_mod.main(["--client", self.slug])
        out = self.capsys.readouterr()
        return rc, out.out + out.err

    def approve(self, action_id):
        rc = self.decide_mod.main(["--client", self.slug, f"approve {str(action_id)[:8]}"])
        self.capsys.readouterr()
        assert rc == 0

    def apply(self, *args):
        rc = self.apply_mod.main(["--client", self.slug, *args])
        out = self.capsys.readouterr()
        return rc, out.out + out.err


@pytest.fixture
def h(db_env, meta_root, monkeypatch, launch_mod, apply_mod, decide_mod, capsys):
    monkeypatch.setenv("DEV_ROOT", str(meta_root))
    monkeypatch.setenv("META_BACKEND", "fake")
    monkeypatch.setenv("META_FAKE_SEED", "9")
    monkeypatch.setenv("PIPELINE_PAUSED", "false")
    monkeypatch.setenv("FUNNEL_HOST", FUNNEL)
    for var in ("META_FAKE_FAIL", "META_FAKE_THROTTLE_AFTER"):
        monkeypatch.delenv(var, raising=False)
    cfg = {k: BASE_CONFIG[k] for k in ("targets", "trust", "rate_limits", "campaign")}
    admin, worker, executor = (connect(r, job="test") for r in ("sam_admin", "worker", "executor"))
    client = insert(admin, "clients", name="T9 test", slug=f"t9-{uuid.uuid4().hex[:8]}", daily_cap=Decimal("45.00"), currency="EUR", config=cfg)
    offer = insert(admin, "offers", client_id=client["id"], name="AI visibility audit", terminal_metric="booked_call", funnel_host=FUNNEL,
                   offer_layer={"cta_mechanic": "book_15_min"})
    admin.execute("insert into families (name, kind) values ('ugc_selfie', 'format') on conflict do nothing")
    admin.commit()
    yield Harness(admin, worker, executor, client, offer, get_meta(), (launch_mod, apply_mod, decide_mod), capsys)
    for c in (admin, worker, executor):
        c.close()


# ---------- boundary (FR-30) ----------

def test_launcher_never_calls_meta_and_writes_proposals_only():
    src = (ME_DIR / "scripts" / "meta_launch.py").read_text()
    assert "adapters.meta" not in src and "get_meta" not in src
    for endpoint in ("create_campaign(", "create_adset(", "create_creative(", "create_ad(", "meta.update("):
        assert endpoint not in src, endpoint
    assert 'connect("worker"' in src and 'connect("executor"' not in src and "WAREHOUSE_URL_EXECUTOR" not in src


# ---------- the proposal ----------

def test_launch_proposes_one_build_campaign_and_running_twice_yields_one_action(h):
    exp, creatives = h.batch()
    rc, out = h.launch()
    assert rc == 0, out
    acts = h.actions("build_campaign")
    assert len(acts) == 1
    a = acts[0]
    assert a["status"] == "proposed" and a["target_type"] == "campaign" and a["trust_level_at_proposal"] == "propose"
    p = a["proposal"]
    assert p["campaign"]["name"] == f"{h.slug}-batch-001-new_recipes" and p["campaign"]["kind"] == "new_recipes"
    assert p["campaign"]["optimisation_event"] == "QuizStart" and p["campaign"]["terminal_metric"] == "booked_call"
    assert len(p["ad_sets"]) == 3 and [len(s["ads"]) for s in p["ad_sets"]] == [2, 2, 2]
    for s in p["ad_sets"]:
        assert s["daily_budget"] == "15" and s["optimisation_event"] == "QuizStart" and s["renderer"] == "html_template"
        assert s["targeting"] == {"geo": ["GB", "IE", "NL", "DE"], "age_min": 25, "age_max": 65}
        for ad in s["ads"]:
            assert ad["link_url"] == ad_url(f"{FUNNEL}/quiz", campaign_name=p["campaign"]["name"], creative_id=ad["creative_id"])   # FR-32
            assert ad["link_url"].startswith(f"{FUNNEL}/quiz?utm_source=facebook&utm_medium=paid&utm_campaign=") and f"utm_content={ad['creative_id']}" in ad["link_url"]
    assert ad_url("https://x.test/p?ref=a", campaign_name="c d", creative_id="id") == "https://x.test/p?ref=a&utm_source=facebook&utm_medium=paid&utm_campaign=c%20d&utm_content=id"
    assert {ad["creative_id"] for s in p["ad_sets"] for ad in s["ads"]} == {str(c["id"]) for c in creatives}
    assert p["cap_check"] == {"daily_cap": "45.00", "active_budget": "0", "proposed_budget": "45", "ok": True}
    assert a["evidence"]["ads"] == 6 and a["evidence"]["ad_sets"] == 3 and len(a["evidence"]["gate_score_ids"]) == 6
    camps = h.campaigns()                                                                      # FR-1: explicit, no external id yet
    assert len(camps) == 1 and str(camps[0]["id"]) == a["target_id"]
    assert camps[0]["terminal_metric"] == "booked_call" and camps[0]["optimisation_event"] == "QuizStart" and camps[0]["external_id"] is None
    assert "cap check  active 0 + proposed 45 <= daily_cap 45.00 -> ok" in out and "Reply `approve" in out
    run_row = h.runs("launcher")[-1]
    assert run_row["status"] == "ok" and run_row["counts"]["proposed"] == 1 and run_row["counts"]["ad_sets"] == 3 and run_row["counts"]["ads"] == 6

    rc, out = h.launch()                                                                       # twice → one action, reprinted
    assert rc == 0 and len(h.actions("build_campaign")) == 1 and len(h.campaigns()) == 1
    assert h.runs("launcher")[-1]["counts"] == {"creatives_approved": 6, "creatives_pending": 6, "reprinted": 1}
    assert p["campaign"]["name"] in out


def test_launch_refuses_when_the_gate_shipped_nothing(h):
    h.batch(verdict=None)                                                                     # agent approvals only
    rc, out = h.launch()
    assert rc == 2 and "gate (B) shipped nothing" in out and h.actions() == []
    row = h.runs("launcher")[-1]
    assert row["status"] == "failed" and "approve verdict" in row["error"]
    h.batch(verdict="reject", name="batch-002")
    rc, out = h.launch()
    assert rc == 2 and h.actions() == [] and h.campaigns() == []


def test_launch_honours_the_latest_sam_verdict_and_skips_launched_creatives(h):
    exp, creatives = h.batch(recipes=1, per_recipe=2)
    insert(h.worker, "gate_scores", creative_id=creatives[0]["id"], attempt=2, scored_by="sam", verdict="reject", decision_channel="chat",
           feedback={"reason": "hook is generic"})
    camp = insert(h.worker, "campaigns", client_id=h.client_id, kind="new_recipes", external_id=f"c-{uuid.uuid4().hex[:6]}")
    insert(h.worker, "ad_entities", client_id=h.client_id, campaign_id=camp["id"], creative_id=creatives[1]["id"], ad_id=f"ad-{uuid.uuid4().hex[:6]}")
    h.worker.commit()
    rc, out = h.launch()
    assert rc == 2 and "shipped nothing" in out, out


def test_validator_refuses_mixed_renderers_cap_excess_ad_set_count_bad_urls_and_missing_components(h):
    exp, creatives = h.batch(recipes=1, per_recipe=2)
    ids = [str(c["id"]) for c in creatives]
    comps = {i: set(REQUIRED_COMPONENTS) for i in ids}
    name = "camp"

    def ad(i, **over):
        return {"name": f"ad{i}", "creative_name": f"cr{i}", "creative_id": ids[i], "renderer": "html_template",
                "link_url": ad_url(f"{FUNNEL}/quiz", campaign_name=name, creative_id=ids[i]), "image_url": "file:///x.png", "title": "t", "body": "b", **over}

    def proposal(**over):
        base = {"campaign": {"name": name, "kind": "new_recipes", "objective": "OUTCOME_LEADS", "currency": "EUR",
                             "terminal_metric": "booked_call", "optimisation_event": "QuizStart"},
                "ad_sets": [{"name": "as1", "renderer": "html_template", "daily_budget": "15", "optimisation_event": "QuizStart",
                             "targeting": {"geo": ["GB"], "age_min": 25, "age_max": 65}, "ads": [ad(0), ad(1)]}]}
        base.update(over)
        return base

    def ok(p, active=0, components_by_creative=comps):
        return validate_build_campaign(p, daily_cap=45, active_budget=active, adsets_max=3, components_by_creative=components_by_creative)

    assert ok(proposal()) == Decimal("15")
    with pytest.raises(ProposalInvalid, match="FR-22"):
        p = proposal(); p["ad_sets"][0]["ads"][1]["renderer"] = "image_to_image"; ok(p)
    with pytest.raises(ProposalInvalid, match="exceeds daily_cap 45"):
        ok(proposal(), active=31)
    with pytest.raises(ProposalInvalid, match="daily_cap"):
        p = proposal(); p["ad_sets"][0]["daily_budget"] = "50"; ok(p)
    with pytest.raises(ProposalInvalid, match="adsets_max"):
        sets = [{**proposal()["ad_sets"][0], "name": f"as{i}", "ads": [ad(0, name=f"a{i}", creative_name=f"c{i}")]} for i in range(4)]
        validate_build_campaign(proposal(ad_sets=sets), daily_cap=100, active_budget=0, adsets_max=3)
    with pytest.raises(ProposalInvalid, match="FR-32"):
        p = proposal(); p["ad_sets"][0]["ads"][0]["link_url"] = f"{FUNNEL}/quiz?utm_content=other"; ok(p)
    with pytest.raises(ProposalInvalid, match="FR-21"):
        ok(proposal(), components_by_creative={ids[0]: set(REQUIRED_COMPONENTS) - {"hook"}, ids[1]: set(REQUIRED_COMPONENTS)})
    with pytest.raises(ProposalInvalid, match="FR-1"):
        p = proposal(); del p["campaign"]["terminal_metric"]; ok(p)
    with pytest.raises(ProposalInvalid, match="geo, age_min, age_max"):
        p = proposal(); p["ad_sets"][0]["targeting"] = {"geo": ["GB"]}; ok(p)


def test_launch_refuses_a_batch_that_does_not_fit_the_cap_or_the_ad_set_limit(h):
    h.admin.execute("update clients set daily_cap=30 where id=%s", (h.client_id,))
    h.admin.commit()
    h.batch()
    rc, out = h.launch()
    assert rc == 2 and "exceeds daily_cap 30" in out and h.actions() == [] and h.campaigns() == []
    assert h.runs("launcher")[-1]["counts"]["proposals_refused"] == 1
    h.admin.execute("update clients set daily_cap=100 where id=%s", (h.client_id,))
    h.admin.execute("delete from gate_scores where creative_id in (select id from creatives where client_id=%s)", (h.client_id,))
    h.admin.commit()
    h.batch(recipes=4, per_recipe=1, name="batch-002")
    rc, out = h.launch()
    assert rc == 2 and "adsets_max 3" in out and h.actions() == []


def test_launch_refuses_mixed_renderers_and_missing_components_before_proposing(h):
    h.batch(recipes=1, per_recipe=2, renderer=lambda i: "html_template" if i % 2 else "image_to_image")
    rc, out = h.launch()
    assert rc == 2 and "FR-22" in out and h.actions() == []
    h.admin.execute("delete from gate_scores where creative_id in (select id from creatives where client_id=%s)", (h.client_id,))
    h.admin.commit()
    h.batch(recipes=1, per_recipe=1, components=tuple(c for c in REQUIRED_COMPONENTS if c != "landing_page"), name="batch-002")
    rc, out = h.launch()
    assert rc == 2 and "landing_page" in out and "FR-21" in out and h.actions() == []


# ---------- apply: the executor builds paused objects ----------

def test_apply_builds_paused_objects_writes_external_ids_and_urls_resolve(h):
    exp, creatives = h.batch()
    h.launch()
    a = h.actions("build_campaign")[0]
    h.approve(a["id"])
    rc, out = h.apply()
    assert rc == 0, out
    a = h.action(a["id"])
    assert a["status"] == "applied" and a["last_error"] is None and a["attempts"] == 1
    camp = h.campaigns()[0]
    assert camp["external_id"] is not None and camp["status"] == "PAUSED"
    mcamp = h.meta.get("campaign", camp["external_id"])
    assert mcamp["status"] == "PAUSED" and mcamp["name"] == a["proposal"]["campaign"]["name"] and mcamp["objective"] == "OUTCOME_LEADS"
    ads = h.ads()
    assert len(ads) == 6 and len({r["adset_id"] for r in ads}) == 3
    for r in ads:
        assert r["status"] == "PAUSED" and r["review_status"] == "APPROVED" and r["adset_daily_budget"] == Decimal("15.00")
        assert r["campaign_id"] == camp["id"] and r["optimisation_event"] == "QuizStart" and r["launched_at"] is None
        mad = h.meta.get("ad", r["ad_id"])
        assert mad["status"] == "PAUSED" and mad["effective_status"] == "PAUSED" and mad["adset_id"] == r["adset_id"]
        adset = h.meta.get("adset", r["adset_id"])
        assert adset["daily_budget"] == 15.0 and adset["optimization_event"] == "QuizStart" and adset["campaign_id"] == camp["external_id"]
        assert adset["targeting"] == {"geo": ["GB", "IE", "NL", "DE"], "age_min": 25, "age_max": 65}
        creative = h.meta.get("creative", mad["creative_id"])
        assert creative["link_url"].endswith(f"utm_content={r['creative_id']}")
        with connect("app", job="test", autocommit=True) as app:                        # FR-32: the URL resolves creative and ad
            lead = app.execute("select * from quiz_start(%s, '{\"tracking\": true}', %s)",
                               (h.slug, Jsonb({"source": "facebook", "content": str(r["creative_id"])}))).fetchone()
        assert lead["creative_id"] == r["creative_id"] and lead["ad_entity_id"] == r["id"]
    assert {c["id"] for c in creatives} == {r["creative_id"] for r in ads}
    assert all(r["recipe_pattern_id"] is not None for r in ads)
    assert {r["status"] for r in h.q("select status from creatives where client_id=%s", h.client_id)} == {"approved"}, "paused build: not live yet"
    assert len(h.meta_objects("campaign")) == 1 and len(h.meta_objects("adset")) == 3 and len(h.meta_objects("ad")) == 6
    counts = h.runs("executor")[-1]["counts"]
    assert counts["applied"] == 1 and counts["meta_created"] == 16 and "meta_reused" not in counts
    assert h.q("select check_daily_cap(%s) as ok", h.client_id)[0]["ok"] is True

    rc, out = h.launch()                                                                # the built campaign now waits for activate
    acts = h.actions("activate")
    assert rc == 0 and len(acts) == 1 and acts[0]["proposal"] == {"cascade": True, "ad_entity_ids": [str(r["id"]) for r in ads]}
    assert acts[0]["evidence"]["cap_check"]["ok"] is True and acts[0]["evidence"]["review_status"] == {"APPROVED": 6}
    assert len(h.actions("build_campaign")) == 1 and "activate #" in out


def test_crash_mid_build_marks_failed_and_the_rerun_leaves_no_orphan(h, monkeypatch):
    exp, creatives = h.batch()
    h.launch()
    a = h.actions("build_campaign")[0]
    h.approve(a["id"])
    monkeypatch.setenv("META_FAKE_FAIL", "create_ad:after")                              # the third create_ad persists, then the run dies
    rc, out = h.apply()
    row = h.action(a["id"])
    assert row["status"] == "failed" and "after create_ad" in row["last_error"]
    camp = h.campaigns()[0]
    assert camp["external_id"] is not None, "the campaign id landed before the crash"
    assert len(h.meta_objects("campaign")) == 1 and len(h.meta_objects("adset")) == 1 and len(h.meta_objects("ad")) == 1
    assert len(h.ads()) == 1, "the ad Meta created before the crash is mirrored even though the run failed"
    monkeypatch.delenv("META_FAKE_FAIL")
    h.approve(a["id"])
    rc, out = h.apply()
    row = h.action(a["id"])
    assert row["status"] == "applied" and row["attempts"] == 2, out
    names = lambda kind: [o["name"] for o in h.meta_objects(kind)]
    assert len(names("campaign")) == 1 and len(names("adset")) == 3 and len(names("ad")) == 6 and len(names("creative")) == 6
    assert len(set(names("ad"))) == 6 and len(set(names("adset"))) == 3, "no duplicates by name"
    ads = h.ads()
    assert len(ads) == 6 and len({r["ad_id"] for r in ads}) == 6 and len(h.campaigns()) == 1
    counts = h.runs("executor")[-1]["counts"]
    assert counts["meta_reused"] == 4 and counts["meta_created"] == 12     # campaign, ad set 1, creative 1 and the crashed ad are found by name


def test_reconcile_settles_a_stale_build_by_name(h, apply_mod):
    exp, creatives = h.batch(recipes=1, per_recipe=1)
    h.launch()
    a = h.actions("build_campaign")[0]
    h.approve(a["id"])
    rc, _ = h.apply()
    assert h.action(a["id"])["status"] == "applied"
    run_row = insert(h.executor, "runs", worker="executor", client_id=h.client_id)
    h.executor.execute("update actions set status='applying', executor_run_id=%s where id=%s", (run_row["id"], a["id"]))
    h.executor.commit()
    h.admin.execute("update runs set started_at = now() - interval '30 minutes' where id=%s", (run_row["id"],))
    h.admin.execute("delete from ad_entities where client_id=%s", (h.client_id,))
    h.admin.commit()
    rc, out = h.apply("--reconcile")
    assert rc == 0, out
    assert h.action(a["id"])["status"] == "applied" and len(h.ads()) == 1, "the mirror re-creates the ad row from Meta by name"
    assert h.runs("executor")[-1]["counts"] == {"reconciled_applied": 1}


def test_executor_refuses_a_build_over_the_cap_and_a_tampered_proposal(h):
    exp, creatives = h.batch()
    h.launch()
    a = h.actions("build_campaign")[0]
    p = json.loads(json.dumps(a["proposal"]))
    p["ad_sets"][0]["daily_budget"] = "40"                                                # 40 + 15 + 15 = 70 > 45
    h.admin.execute("update actions set proposal=%s where id=%s", (Jsonb(p), a["id"]))
    h.admin.commit()
    h.approve(a["id"])
    rc, out = h.apply()
    row = h.action(a["id"])
    assert row["status"] == "failed" and "daily_cap" in row["last_error"] and row["attempts"] == 0
    assert h.meta_objects("campaign") == [] and h.campaigns()[0]["external_id"] is None
    p["ad_sets"][0]["daily_budget"] = "15"
    p["ad_sets"][0]["ads"][0]["link_url"] = f"{FUNNEL}/quiz?utm_content=nope"
    h.admin.execute("update actions set proposal=%s where id=%s", (Jsonb(p), a["id"]))
    h.admin.commit()
    h.approve(a["id"])
    rc, out = h.apply()
    assert "FR-32" in h.action(a["id"])["last_error"] and h.meta_objects("campaign") == []


# ---------- activate: the cap invariant and FR-37 ----------

def test_activate_cascade_turns_the_campaign_on_under_the_cap(h):
    exp, creatives = h.batch()
    h.launch()
    h.approve(h.actions("build_campaign")[0]["id"])
    h.apply()
    h.launch()
    act = h.actions("activate")[0]
    h.approve(act["id"])
    rc, out = h.apply()
    assert rc == 0 and h.action(act["id"])["status"] == "applied", out
    camp = h.campaigns()[0]
    assert camp["status"] == "ACTIVE" and h.meta.get("campaign", camp["external_id"])["status"] == "ACTIVE"
    ads = h.ads()
    assert all(r["status"] == "ACTIVE" and r["launched_at"] is not None for r in ads) and len(ads) == 6
    for r in ads:
        mad = h.meta.get("ad", r["ad_id"])
        assert mad["status"] == "ACTIVE" and mad["effective_status"] == "ACTIVE", "ad, ad set and campaign are all on"
    assert h.q("select check_daily_cap(%s) as ok", h.client_id)[0]["ok"] is True          # 3 ad sets x 15 = 45 <= 45 (0007)
    assert h.q("select count(*) as n from ad_entities where client_id=%s and status='ACTIVE'", h.client_id)[0]["n"] == 6
    assert {r["status"] for r in h.q("select status from creatives where client_id=%s", h.client_id)} == {"live"}, "status flow: approved → live"
    rc, out = h.launch()                                                                # nothing left to launch
    assert rc == 2 and "shipped nothing" in out and len(h.actions("activate")) == 1
    assert h.runs("launcher")[-1]["status"] == "failed"


def test_activate_cascade_is_refused_over_the_cap(h):
    exp, creatives = h.batch()
    h.launch()
    h.approve(h.actions("build_campaign")[0]["id"])
    h.apply()
    other = insert(h.worker, "campaigns", client_id=h.client_id, kind="scaling", external_id=f"sc-{uuid.uuid4().hex[:6]}",
                   daily_budget=Decimal("10"), status="ACTIVE")
    h.worker.commit()
    rc, out = h.launch()
    assert rc == 2 and "activate refused" in out and "exceeds daily_cap 45.00" in out and h.actions("activate") == []
    assert h.runs("launcher")[-1]["counts"]["activate_refused_cap"] == 1
    h.admin.execute("update campaigns set status='PAUSED' where id=%s", (other["id"],))
    h.admin.commit()
    h.launch()
    act = h.actions("activate")[0]
    h.admin.execute("update campaigns set status='ACTIVE' where id=%s", (other["id"],))      # spends again before apply
    h.admin.commit()
    h.approve(act["id"])
    rc, out = h.apply()
    row = h.action(act["id"])
    assert row["status"] == "failed" and row["last_error"] == "daily_cap" and row["attempts"] == 0
    assert all(h.meta.get("ad", r["ad_id"])["status"] == "PAUSED" for r in h.ads())


def test_disapproved_ad_syncs_from_meta_and_refuses_activate(h):
    exp, creatives = h.batch()
    h.launch()
    h.approve(h.actions("build_campaign")[0]["id"])
    h.apply()
    ads = h.ads()
    h.meta.update("ad", ads[2]["ad_id"], review_status="DISAPPROVED", ad_review_feedback={"policy": "personal_attributes"})   # Meta's review turns one down
    h.launch()                                                                          # the warehouse still says APPROVED: proposed
    act = h.actions("activate")[0]
    h.approve(act["id"])
    rc, out = h.apply()
    row = h.action(act["id"])
    assert row["status"] == "failed" and row["last_error"] == f"disapproved: {ads[2]['ad_id']}", out
    synced = [r for r in h.ads() if r["id"] == ads[2]["id"]][0]
    assert synced["review_status"] == "DISAPPROVED" and synced["review_feedback"] == {"policy": "personal_attributes"}     # FR-37 sync
    assert all(h.meta.get("ad", r["ad_id"])["status"] == "PAUSED" for r in h.ads()) and h.campaigns()[0]["status"] == "PAUSED"
    assert all(r["status"] == "PAUSED" for r in h.ads())
    rc, out = h.launch()                                                                # now known: the launcher refuses to re-propose
    assert "activate refused" in out and ads[2]["ad_id"] in out and "FR-37" in out
    assert len(h.actions("activate")) == 1
    h.approve(act["id"])                                                                # a fixture with a DISAPPROVED ad: refused before applying
    rc, out = h.apply()
    row = h.action(act["id"])
    assert row["status"] == "failed" and row["last_error"].startswith("disapproved:") and row["attempts"] == 1


# ---------- 0007: the cap counts each ad set once ----------

def test_check_daily_cap_counts_each_ad_set_once(h):
    camp = insert(h.worker, "campaigns", client_id=h.client_id, kind="new_recipes", external_id=f"c-{uuid.uuid4().hex[:6]}")
    for adset, budget in (("set-a", 20), ("set-a", 20), ("set-b", 25), ("set-b", 25)):
        insert(h.worker, "ad_entities", client_id=h.client_id, campaign_id=camp["id"], adset_id=f"{h.slug}-{adset}",
               adset_daily_budget=Decimal(budget), ad_id=f"ad-{uuid.uuid4().hex[:6]}", status="ACTIVE")
    h.worker.commit()
    assert h.q("select check_daily_cap(%s) as ok", h.client_id)[0]["ok"] is True          # 20 + 25 = 45, not 90
    insert(h.worker, "ad_entities", client_id=h.client_id, campaign_id=camp["id"], adset_id=f"{h.slug}-set-c",
           adset_daily_budget=Decimal(1), ad_id=f"ad-{uuid.uuid4().hex[:6]}", status="ACTIVE")
    h.worker.commit()
    assert h.q("select check_daily_cap(%s) as ok", h.client_id)[0]["ok"] is False
