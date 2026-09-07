"""warehouse/client.py against a throwaway local Postgres (conftest.test_db): every migration applied,
the DRAFT seed loaded. Nothing is mocked. Covers FR-44, DR-1, DR-2, NFR-1, NFR-4 for T1."""
from __future__ import annotations

import datetime as dt
import re
import subprocess
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import psycopg
import pytest

from adapters.env import MissingEnvVar
from warehouse import client
from warehouse.client import TABLES, connect, insert, run, where_are_we, format_where_are_we

ME_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def worker(db_env):
    with connect("worker", job="test") as conn:
        yield conn
        if not conn.closed:
            conn.rollback()


@pytest.fixture
def admin(db_env):
    with connect("sam_admin", job="test") as conn:
        yield conn
        if not conn.closed:
            conn.rollback()


@pytest.fixture
def executor(db_env):
    with connect("executor", job="test") as conn:
        yield conn
        if not conn.closed:
            conn.rollback()


@pytest.fixture
def client_id(worker):
    return client.client_by_slug(worker, "upclicklabs")["id"]


# ---------- connections ----------

def test_connect_uses_the_role_named_and_dict_rows(db_env):
    for role, expected in [("worker", "worker_rw"), ("executor", "executor"), ("sam_admin", "sam_admin"), ("mcp_ro", "mcp_ro")]:
        with connect(role, job="test") as conn:
            row = conn.execute("select current_user as who, current_database() as db").fetchone()
            assert row == {"who": expected, "db": db_env["WAREHOUSE_URL_WORKER"].rsplit("/", 1)[1]}


def test_connect_names_the_missing_variable_and_never_its_value(db_env, monkeypatch):
    monkeypatch.delenv("WAREHOUSE_URL_EXECUTOR")
    monkeypatch.setattr(client, "load_env", lambda: None)  # .env in the checkout would supply it again
    with pytest.raises(MissingEnvVar) as exc:
        connect("executor", job="apply_actions")
    assert "WAREHOUSE_URL_EXECUTOR" in str(exc.value) and "postgresql://" not in str(exc.value)


def test_connect_rejects_unknown_role(db_env):
    with pytest.raises(client.UnknownRole, match="service"):
        connect("service", job="test")


def test_executor_url_is_used_only_by_the_executor():
    """NFR-1: WAREHOUSE_URL_EXECUTOR / connect('executor') appear only in the client, the executor, and tests."""
    hits = subprocess.run(
        ["grep", "-rlE", r"WAREHOUSE_URL_EXECUTOR|connect\(\s*['\"]executor", "--include=*.py", "--include=*.sh", "."],
        cwd=ME_DIR, capture_output=True, text=True).stdout.split()
    allowed = {"./warehouse/client.py", "./scripts/dev_db.sh", "./scripts/apply_actions.py"}
    assert {h for h in hits if not h.startswith("./tests/")} <= allowed, hits


# ---------- migrations ----------

def test_migration_files_are_every_numbered_file_in_order():
    names = [p.name for p in client.migration_files()]
    assert names[:3] == ["schema.sql", "0002_roles.sql", "0003_phase0_grants.sql"]
    assert names == sorted(names, key=lambda n: "0001" if n == "schema.sql" else n[:4])
    notes = (ME_DIR / "warehouse" / "schema-notes.md").read_text()
    for n in names[1:]:
        assert n in notes, f"{n} is not listed in warehouse/schema-notes.md"


def test_0003_grants_worker_updates_and_keeps_actions_locked(worker, admin, client_id):
    fam = insert(admin, "families", name="t1_grant_family", kind="format")
    admin.commit()
    creative = insert(worker, "creatives", client_id=client_id)
    brief = insert(worker, "briefs", client_id=client_id, angle="pain_led", family=fam["name"])
    campaign = insert(worker, "campaigns", client_id=client_id, kind="new_recipes")
    worker.commit()
    worker.execute("update creatives set status='gated', version=version+1, asset_urls=%s, sizes=%s where id=%s",
                   (["file:///a.png"], ["1080x1080"], creative["id"]))
    worker.execute("update briefs set spec=%s where id=%s", (client.Jsonb({"chosen": True}), brief["id"]))
    worker.execute("update campaigns set active_lever='ctr', active_lever_reason='floor', active_lever_since=now() where id=%s",
                   (campaign["id"],))
    row = worker.execute("select c.status, c.version, b.spec, k.active_lever from creatives c, briefs b, campaigns k"
                         " where c.id=%s and b.id=%s and k.id=%s", (creative["id"], brief["id"], campaign["id"])).fetchone()
    assert row == {"status": "gated", "version": 2, "spec": {"chosen": True}, "active_lever": "ctr"}
    worker.rollback()
    for stmt in ["update creatives set primary_text='x' where id=%s",
                 "update briefs set angle='x' where id=%s",
                 "update campaigns set daily_budget=1 where id=%s"]:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            worker.execute(stmt, (creative["id"],))
        worker.rollback()
    action = insert(worker, "actions", client_id=client_id, action_type="pause", target_type="creative",
                    target_id=str(creative["id"]), proposal_key="t1-grant-check")
    worker.commit()
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        worker.execute("update actions set status='approved' where id=%s", (action["id"],))
    worker.rollback()


# ---------- FR-44 guards ----------

def test_worker_can_only_propose_actions(worker, executor, client_id):
    proposed = insert(worker, "actions", client_id=client_id, action_type="kill", target_type="ad_entity",
                      target_id="ad-1", rule="ctr_floor", proposal={"pause": True}, evidence={"impressions": 2500},
                      proposal_key="t1-kill-ad-1")
    worker.commit()
    assert proposed["status"] == "proposed" and proposed["proposal"] == {"pause": True}
    with pytest.raises(psycopg.errors.RaiseException, match="workers may only propose"):
        insert(worker, "actions", client_id=client_id, action_type="kill", target_type="ad_entity", target_id="ad-2",
               proposal_key="t1-kill-ad-2", status="approved")
    worker.rollback()
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        worker.execute("update actions set status='approved' where id=%s", (proposed["id"],))
    worker.rollback()
    executor.execute("update actions set status='approved', decided_by='sam', decision_channel='chat' where id=%s", (proposed["id"],))
    assert executor.execute("select status from actions where id=%s", (proposed["id"],)).fetchone()["status"] == "approved"
    executor.rollback()


def test_executor_cannot_approve_promote_trust(worker, executor, client_id):
    row = insert(worker, "actions", client_id=client_id, action_type="promote_trust", target_type="trust", target_id="kill",
                 proposal_key="t1-promote-kill")
    worker.commit()
    with pytest.raises(psycopg.errors.RaiseException, match="only sam_admin may approve promote_trust"):
        executor.execute("update actions set status='approved' where id=%s", (row["id"],))
    executor.rollback()


# ---------- insert helpers: every table in schema.sql ----------

def test_every_base_table_has_a_helper_and_nothing_else(admin):
    live = {r["table_name"] for r in admin.execute(
        "select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE'"
        " and table_name <> 'dev_migrations'")}
    assert set(TABLES) == live
    for t in TABLES:
        assert callable(getattr(client, f"insert_{t}")), t


def test_insert_rejects_unknown_generated_and_unknown_table(worker, client_id):
    with pytest.raises(client.UnknownColumn, match="ad_metrics_daily.cpm"):
        insert(worker, "ad_metrics_daily", ad_entity_id=client_id, day=dt.date.today(), cpm=1)
    with pytest.raises(client.UnknownColumn, match="patterns.colour"):
        insert(worker, "patterns", colour="red")
    with pytest.raises(client.UnknownTable, match="pattern"):
        insert(worker, "pattern", family="x")
    worker.rollback()


def test_every_helper_round_trips(worker, admin, client_id):
    """One row per table through its helper, read back by primary key as sam_admin, equal to what was returned.
    Worker-writable tables go through worker_rw; the rest (clients, offers, icps, leads, lead_contacts,
    erasure_requests) through sam_admin, which is the role that owns them."""
    today = dt.date.today()
    fam = client.insert_families(worker, name="t1_rt_format", kind="format")
    fam2 = client.insert_families(worker, name="t1_rt_hook", kind="hook_type", status="proposed", promoted_from_variant="v1")
    offer = client.insert_offers(admin, client_id=client_id, name="t1 offer", proof_points=["a", "b"],
                                 quiz_config={"version": "t"}, offer_layer={"offer_mechanic": "x"})
    icp = client.insert_icps(admin, client_id=client_id, label="t1 icp", geo=["GB"], pains=["p"], outcomes=[])
    client2 = client.insert_clients(admin, name="T1 Co", slug="t1co", daily_cap=Decimal("12.50"), config={"targets": {}})
    admin.commit()  # the worker connection must see the offer and icp
    raw = client.insert_raw_ingest(worker, source="ad_library", client_id=client_id, external_id="x1",
                                   dedup_key="ad_library:x1:abc", payload={"k": [1, 2]})
    voc = client.insert_voc_phrases(worker, client_id=client_id, icp_id=icp["id"], phrase="It never ranks",
                                    phrase_normalised="it never ranks", category="pain", source="vault",
                                    source_ref="vault:note-1", source_weight=3, trust_tier="owned", visibility="internal")
    pattern = client.insert_patterns(worker, client_id=None, origin="external", source_list="dtc", family=fam["name"],
                                     variant="v1", hook_type="number", angle="pain_led", source_strength=3,
                                     source_brand="AG1", source_url="https://example.invalid/ad", start_date=today,
                                     days_running=31, concurrent_variants=3, recipe={"format_layer": {"copy_length": "short"}})
    hook = client.insert_hooks(worker, client_id=client_id, text="3 reasons", hook_type="number", pattern_id=pattern["id"])
    exp = client.insert_experiments(worker, client_id=client_id, offer_id=offer["id"], name="batch-1", capacity=6,
                                    budget_share=Decimal("0.500"), result={})
    brief = client.insert_briefs(worker, client_id=client_id, experiment_id=exp["id"], offer_id=offer["id"], icp_id=icp["id"],
                                 source_pattern_id=pattern["id"], changed_ingredients=["offer", "voc_phrases"],
                                 family=fam["name"], angle="pain_led", hook_id=hook["id"], voc_phrase_ids=[voc["id"]],
                                 visual_spec="photo", cta="Book", spec={"n": 1})
    sel = client.insert_selections(worker, client_id=client_id, experiment_id=exp["id"], proposed=[brief["id"]],
                                   chosen=[brief["id"]], rejected=[], reason="ok", selected_by="sam")
    creative = client.insert_creatives(worker, client_id=client_id, brief_id=brief["id"], experiment_id=exp["id"],
                                       primary_text="p", headline="h", renderer="html_template", template="job-photo-bubble",
                                       image_model="placeholder", fidelity_score=Decimal("0.900"), asset_urls=["file:///x.png"],
                                       sizes=["1080x1080"])
    comp = client.insert_creative_components(worker, creative_id=creative["id"], component_type="family", component_ref=fam["name"])
    gate = client.insert_gate_scores(worker, creative_id=creative["id"], scored_by="agent", mode="shadow", verdict="approve",
                                     decision_channel="auto", scores={"clarity": 4}, avg_score=Decimal("4.00"),
                                     hard_checks={"policy": "pass"}, policy_flags=[], hard_blocks=[], passed=True, feedback={})
    campaign = client.insert_campaigns(worker, client_id=client_id, offer_id=offer["id"], kind="new_recipes", external_id="c-1",
                                       daily_budget=Decimal("30.00"), spend_cap=Decimal("500.00"))
    ad = client.insert_ad_entities(worker, client_id=client_id, campaign_id=campaign["id"], creative_id=creative["id"],
                                   recipe_pattern_id=pattern["id"], adset_id="as-1", adset_daily_budget=Decimal("10.00"),
                                   ad_id="ad-1", optimisation_event="QuizStart", review_feedback={})
    metric = client.insert_ad_metrics_daily(worker, ad_entity_id=ad["id"], day=today, impressions=1000, reach=900, clicks=20,
                                            link_clicks=15, spend=Decimal("12.34"), quiz_starts=3, quiz_completes=2, schedules=1,
                                            video_3s=None, frequency=Decimal("1.100"))
    spend = client.insert_account_spend_hourly(worker, client_id=client_id, observed_at=dt.datetime(2026, 9, 7, 12, tzinfo=dt.timezone.utc),
                                               spend_today=Decimal("5.00"))
    post = client.insert_posts(worker, client_id=client_id, creative_id=creative["id"], channel="x", external_id="p-1", text="t",
                               hook_id=hook["id"])
    post_metric = client.insert_post_metrics_daily(worker, post_id=post["id"], day=today, impressions=100, engagements=10)
    worker.commit()  # sam_admin must see the ad entity and creative
    lead = client.insert_leads(admin, client_id=client_id, offer_id=offer["id"], ad_entity_id=ad["id"], creative_id=creative["id"],
                               source="quiz", utm={"utm_content": str(creative["id"])}, fbclid_hash="h", quiz_version="v1-draft",
                               quiz_answers={"q1": "SaaS"}, qualification_score=Decimal("2.00"),
                               consent={"tracking": True, "notice_version": "1"}, stage="completed", value=None)
    contact = client.insert_lead_contacts(admin, lead_id=lead["id"], email="lead@example.invalid", name="L")
    erasure = client.insert_erasure_requests(admin, client_id=client_id, lead_id=lead["id"], email_hash="eh", fanout={"warehouse": None})
    action = client.insert_actions(worker, client_id=client_id, action_type="build_campaign", target_type="campaign",
                                   target_id=str(campaign["id"]), rule="launch", proposal={"ad_sets": 3},
                                   proposal_key="t1-rt-build", evidence={})
    run_row = client.insert_runs(worker, worker="intel", client_id=client_id, counts={"patterns": 1}, tokens_used=10, api_calls=2)
    learning = client.insert_learnings(worker, client_id=client_id, icp_id=icp["id"], scope="client", hypothesis="h",
                                       component_type="family", component_ref=fam["name"], direction="beat",
                                       effect_size=Decimal("0.01000"), sample=2000, posterior=Decimal("0.900"),
                                       evidence={"sample_reached": False}, created_by="sam")
    worker.commit()
    admin.commit()

    # metric generated columns are computed by Postgres, never passed in
    assert metric["cpm"] == Decimal("12.3400") and metric["link_ctr"] == Decimal("0.01500")
    assert post_metric["engagement_rate"] == Decimal("0.10000")
    assert isinstance(pattern["id"], UUID) and isinstance(brief["voc_phrase_ids"][0], UUID)
    assert brief["voc_phrase_ids"] == [voc["id"]] and sel["chosen"] == [brief["id"]] and sel["rejected"] == []
    assert raw["payload"] == {"k": [1, 2]} and run_row["status"] == "running"

    expected = {
        "families": (fam, "name"), "offers": (offer, "id"), "icps": (icp, "id"), "clients": (client2, "id"),
        "raw_ingest": (raw, "id"), "voc_phrases": (voc, "id"), "patterns": (pattern, "id"), "hooks": (hook, "id"),
        "experiments": (exp, "id"), "briefs": (brief, "id"), "selections": (sel, "id"), "creatives": (creative, "id"),
        "gate_scores": (gate, "id"), "campaigns": (campaign, "id"), "ad_entities": (ad, "id"), "posts": (post, "id"),
        "leads": (lead, "id"), "lead_contacts": (contact, "lead_id"), "erasure_requests": (erasure, "id"),
        "actions": (action, "id"), "runs": (run_row, "id"), "learnings": (learning, "id"),
    }
    for table, (row, pk) in expected.items():
        back = admin.execute(f"select * from {table} where {pk} = %s", (row[pk],)).fetchone()
        assert back == row, table
    assert admin.execute("select * from families where name=%s", (fam2["name"],)).fetchone() == fam2
    assert admin.execute("select * from creative_components where creative_id=%s", (creative["id"],)).fetchone() == comp
    assert admin.execute("select * from ad_metrics_daily where ad_entity_id=%s and day=%s and fetched_on=%s",
                         (ad["id"], today, metric["fetched_on"])).fetchone() == metric
    assert admin.execute("select * from account_spend_hourly where client_id=%s and observed_at=%s",
                         (client_id, spend["observed_at"])).fetchone() == spend
    assert admin.execute("select * from post_metrics_daily where post_id=%s", (post["id"],)).fetchone() == post_metric
    # DR-2: the marts see the rows through the helpers
    perf = admin.execute("select impressions, link_ctr from mart_creative_performance where creative_id=%s", (creative["id"],)).fetchone()
    assert perf == {"impressions": 1000, "link_ctr": Decimal("0.01500")}
    assert admin.execute("select recommendation from mart_kill_scale_candidates where ad_entity_id=%s", (ad["id"],)).fetchall() == []


def test_worker_cannot_insert_where_0002_gives_no_grant(worker, client_id):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        client.insert_leads(worker, client_id=client_id)
    worker.rollback()


# ---------- runs context manager ----------

def test_run_closes_ok_with_counts(worker, admin, client_id):
    with run(worker, "intel", client_id=client_id) as r:
        assert admin.execute("select status, finished_at from runs where id=%s", (r.id,)).fetchone() == {"status": "running", "finished_at": None}
        r.count("patterns", 3)
        r.count("patterns")
        r.count("raw_ingest", 5)
        r.tokens_used = 1234
        r.api_calls = 7
        insert(worker, "hooks", client_id=client_id, text="written inside the run")
    row = admin.execute("select * from runs where id=%s", (r.id,)).fetchone()
    assert row["status"] == "ok" and row["finished_at"] is not None and row["error"] is None
    assert row["counts"] == {"patterns": 4, "raw_ingest": 5} and row["tokens_used"] == 1234 and row["api_calls"] == 7
    assert row["worker"] == "intel" and row["client_id"] == client_id
    assert admin.execute("select count(*) from hooks where text='written inside the run'").fetchone()["count"] == 1


def test_run_closes_failed_with_error_and_rolls_back_the_body(worker, admin, client_id):
    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom):
        with run(worker, "voc", client_id=client_id) as r:
            r.count("phrases", 2)
            insert(worker, "hooks", client_id=client_id, text="rolled back with the failed run")
            raise Boom("source unreachable")
    row = admin.execute("select * from runs where id=%s", (r.id,)).fetchone()
    assert row["status"] == "failed" and row["finished_at"] is not None
    assert row["error"] == "Boom: source unreachable" and row["counts"] == {"phrases": 2}
    assert admin.execute("select count(*) from hooks where text='rolled back with the failed run'").fetchone()["count"] == 0


def test_run_closes_failed_after_a_database_error(worker, admin, client_id):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with run(worker, "planner", client_id=client_id) as r:
            worker.execute("update actions set status='approved'")
    row = admin.execute("select status, error from runs where id=%s", (r.id,)).fetchone()
    assert row["status"] == "failed" and row["error"].startswith("InsufficientPrivilege:")


def test_run_left_running_when_the_connection_dies_keeps_the_cause(worker, admin, client_id):
    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom) as exc:
        with run(worker, "loop", client_id=client_id) as r:
            worker.close()  # simulates a crash / lost connection inside the body
            raise Boom("insights source gone")
    assert any("stays 'running'" in n for n in exc.value.__notes__)
    assert admin.execute("select status, finished_at from runs where id=%s", (r.id,)).fetchone() == {"status": "running", "finished_at": None}


# ---------- the §2 and §4.2 queries ----------

def test_where_are_we_matches_skill_section_2(worker, admin, client_id):
    row = where_are_we(worker, "upclicklabs")
    assert list(row) == ["slug", "paused", "daily_cap", "currency", "proven_patterns", "voc_phrases", "latest_batch",
                         "capacity", "creatives_by_status", "actions_waiting", "actions_stuck", "ads_active",
                         "kill_scale_candidates", "learnings_proposed", "last_failure"]
    assert row["slug"] == "upclicklabs" and row["paused"] is False and row["daily_cap"] == Decimal("45.00") and row["currency"] == "EUR"
    assert where_are_we(worker, "no-such-client") is None
    text = format_where_are_we(row)
    assert text.splitlines()[0].startswith("slug") and "upclicklabs" in text and "actions_stuck" in text
    assert "stop" not in text.lower()
    stuck = dict(row, actions_stuck=2)
    assert "only the executor's reconcile mode" in format_where_are_we(stuck)


def test_where_are_we_counts_move_with_the_tables(worker, admin, client_id):
    before = where_are_we(worker, "upclicklabs")
    exp = insert(worker, "experiments", client_id=client_id, name="batch-wru", capacity=4)
    insert(worker, "creatives", client_id=client_id, experiment_id=exp["id"], status="gated")
    insert(worker, "actions", client_id=client_id, action_type="pause", target_type="creative", target_id="x", proposal_key="wru-1")
    insert(worker, "learnings", client_id=client_id, scope="client", hypothesis="wru")
    worker.commit()
    after = where_are_we(worker, "upclicklabs")
    assert after["latest_batch"] == "batch-wru" and after["capacity"] == 4
    assert after["creatives_by_status"].get("gated", 0) == (before["creatives_by_status"] or {}).get("gated", 0) + 1
    assert after["actions_waiting"] == before["actions_waiting"] + 1
    assert after["learnings_proposed"] == before["learnings_proposed"] + 1


def test_read_before_planning_queries(worker, client_id):
    insert(worker, "learnings", client_id=client_id, scope="client", hypothesis="local-proposed", posterior=Decimal("0.600"))
    insert(worker, "learnings", client_id=None, scope="global", hypothesis="global-supported", status="global", posterior=Decimal("0.900"))
    insert(worker, "learnings", client_id=client_id, scope="client", hypothesis="refuted-hidden", status="refuted")
    worker.commit()
    rows = client.learnings_before_planning(worker, client_id)
    names = [r["hypothesis"] for r in rows]
    assert "refuted-hidden" not in names and {"local-proposed", "global-supported"} <= set(names)
    assert set(rows[0]) == {"hypothesis", "status", "effect_size", "posterior"}
    keys = [(r["status"], r["posterior"] if r["posterior"] is not None else Decimal("-1")) for r in rows]
    assert keys == sorted(keys, reverse=True)  # status desc, then posterior desc nulls last
    board = client.leaderboard_before_planning(worker, client_id)
    assert board == [] or set(board[0]) == {"component_type", "component_ref", "creatives", "link_ctr", "link_ctr_lcb"}


def test_queries_are_verbatim_from_skill_md():
    skill = (ME_DIR / "SKILL.md").read_text()
    src = (ME_DIR / "warehouse" / "client.py").read_text()
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    for query in [client.WHERE_ARE_WE_SQL, client.LEARNINGS_BEFORE_PLANNING_SQL, client.LEADERBOARD_BEFORE_PLANNING_SQL]:
        assert norm(query.replace("%s", "$1")) in norm(skill)
    assert "WAREHOUSE_URL_EXECUTOR" in src
