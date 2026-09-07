"""Quiz funnel (T7) against the throwaway Postgres (conftest.test_db, 0001–0004 applied, DRAFT seed).
Nothing is mocked: the RPCs run as role `app`, CAPI is the fake adapter writing DEV_ROOT/capi.jsonl,
Turnstile is `pass`. Covers FR-32 to FR-35 and DR-4."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg
import pytest
from psycopg.errors import InsufficientPrivilege

from adapters.capi import get_capi
from adapters.turnstile import get_turnstile
from funnel import quiz
from funnel.app import Deps, RateLimiter, Request, handle
from warehouse.client import client_by_slug, connect, insert

ME_DIR = Path(__file__).resolve().parent.parent
SECRET = "test-secret"
CONFIG = json.loads((ME_DIR / "config" / "clients" / "upclicklabs.json").read_text())
QUIZ = CONFIG["offer"]["quiz_config"]
GOOD_ANSWERS = {"q1": "B2B services", "q2": "Referrals", "q3": "No"}   # qualification: 2 + 0 + 2 = 4


# ---------- fixtures ----------

@pytest.fixture
def logs():
    return []


@pytest.fixture
def deps(db_env, dev_root, monkeypatch, logs):
    monkeypatch.setenv("CAPI_BACKEND", "fake")
    monkeypatch.setenv("TURNSTILE_BACKEND", "pass")
    return Deps(
        db=lambda: connect("app", job="test", autocommit=True),
        capi=get_capi(), turnstile=get_turnstile(), limiter=RateLimiter(1000),
        log=lambda event, **f: logs.append({"event": event, **f}),
        cal_webhook_secret=SECRET, funnel_host="http://localhost:8788", now=lambda: 1_757_000_000.0,
    )


@pytest.fixture
def admin(db_env):
    with connect("sam_admin", job="test") as conn:
        yield conn
        if not conn.closed:
            conn.rollback()


def post(deps, path, body, ip="10.0.0.1", headers=None, raw=None):
    data = raw if raw is not None else json.dumps(body).encode()
    return handle(Request("POST", path, headers={"user-agent": "pytest", **(headers or {})}, body=data, remote_ip=ip), deps)


def start(deps, tracking=True, utm=None, fbclid="IwAR0abc", client="upclicklabs", ip="10.0.0.1"):
    consent = {"tracking": tracking, "marketing": False, "verbatim_use": True}
    return post(deps, "/quiz/start", {"client": client, "consent": consent, "utm": utm or {}, "fbclid": fbclid,
                                      "turnstile_token": "dev-pass"}, ip=ip)


def complete(deps, lead_id, answers=None, email="Person@Example.com", name="Pat", ip="10.0.0.1"):
    return post(deps, "/quiz", {"client": "upclicklabs", "lead_id": lead_id, "answers": answers or GOOD_ANSWERS,
                                "contact": {"email": email, "name": name, "phone": None}, "turnstile_token": "dev-pass"}, ip=ip)


def webhook(deps, lead_id, secret=SECRET, sign=True, trigger="BOOKING_CREATED", ip="10.0.0.2"):
    raw = json.dumps({"triggerEvent": trigger, "createdAt": "2026-09-07T10:00:00Z",
                      "payload": {"uid": "abc", "startTime": "2026-09-09T10:00:00Z", "metadata": {"lead_id": lead_id}}}).encode()
    headers = {"x-cal-signature-256": quiz.cal_signature(secret, raw)} if sign else {}
    return post(deps, "/cal-webhook", None, ip=ip, headers=headers, raw=raw)


def lead_row(admin, lead_id):
    return admin.execute("select * from leads where id = %s", (lead_id,)).fetchone()


# ---------- 0004: RPC only, PII isolation (DR-4) ----------

def test_app_cannot_insert_leads_directly_but_the_rpc_works(db_env):
    """0004 revokes the direct inserts 0002 granted; the SECURITY DEFINER RPCs are the only path (DR-4, FR-33)."""
    def as_app(sql):
        with connect("app", job="test", autocommit=True) as conn:
            assert conn.execute("select current_user").fetchone()["current_user"] == "app"
            return conn.execute(sql).fetchone()
    for sql in ("insert into leads (client_id) values (gen_random_uuid())",
                "insert into lead_contacts (lead_id, email) values (gen_random_uuid(), 'x@example.com')",
                "select email from lead_contacts",
                "select consent from leads",
                "select id from clients",
                "update leads set booked_verified_at = now()"):
        with pytest.raises(InsufficientPrivilege):
            as_app(sql)
    row = as_app("select * from quiz_start('upclicklabs', '{\"tracking\": true}')")
    assert row["lead_id"] and row["client_id"] and row["offer_id"]
    assert as_app("select id from leads limit 1") is None  # 0002's column grant stays, but its RLS shows app no rows


def test_rpc_refuses_a_raw_fbclid_and_stores_the_hash(db_env, admin):
    with connect("app", job="test", autocommit=True) as conn:
        with pytest.raises(psycopg.errors.CheckViolation, match="hashed"):
            conn.execute("select * from quiz_start('upclicklabs', '{}', '{}', 'IwAR0raw_click_id')")
        h = hashlib.sha256(b"IwAR0raw_click_id").hexdigest()
        lead = conn.execute("select * from quiz_start('upclicklabs', '{}', '{}', %s)", (h,)).fetchone()["lead_id"]
    assert lead_row(admin, lead)["fbclid_hash"] == h


def test_pii_lands_only_in_lead_contacts(deps, admin):
    lead = start(deps).body["lead_id"]
    res = complete(deps, lead, email=" Person@Example.com ", name="Pat Example")
    assert res.status == 200, res.body
    row = lead_row(admin, lead)
    dump = json.dumps(row, default=str).lower()
    assert "example.com" not in dump and "pat" not in dump
    contact = admin.execute("select * from lead_contacts where lead_id = %s", (lead,)).fetchone()
    assert contact["email"] == "person@example.com" and contact["name"] == "Pat Example"
    assert row["fbclid_hash"] == hashlib.sha256(b"IwAR0abc").hexdigest() and "IwAR0abc" not in dump
    assert row["purge_after"] is not None
    with connect("mcp_ro", job="test") as ro:
        with pytest.raises(InsufficientPrivilege):
            ro.execute("select consent, fbclid_hash, quiz_answers from leads").fetchall()


def test_funnel_code_reaches_tables_through_the_rpcs_only():
    src = "\n".join(p.read_text() for p in (ME_DIR / "funnel").glob("*.py"))
    assert "insert into" not in src.lower() and "update leads" not in src.lower()
    for fn in ("quiz_start(", "quiz_complete(", "lead_booked(", "quiz_config("):
        assert fn in src


# ---------- FR-33: consent, dedup, Turnstile, rate limits ----------

def test_full_flow_fires_each_event_once_with_shared_event_ids(deps, admin, dev_root):
    r1 = start(deps, utm={"source": "facebook", "content": "not-a-uuid"})
    assert r1.status == 200 and r1.body["event_id"] == f"{r1.body['lead_id']}:QuizStart"
    lead = r1.body["lead_id"]
    assert lead_row(admin, lead)["stage"] == "new" and lead_row(admin, lead)["source"] == "meta"

    r2 = complete(deps, lead)
    assert r2.status == 200 and r2.body["event_id"] == f"{lead}:QuizComplete"
    assert r2.body["qualification_score"] == 4.0 and r2.body["qualified"] is True
    assert r2.body["calendar_url"] is None  # DRAFT config: calendar_url is a PLACEHOLDER, not a URL
    row = lead_row(admin, lead)
    assert row["stage"] == "completed" and row["quiz_answers"] == GOOD_ANSWERS and float(row["qualification_score"]) == 4.0
    assert row["consent"]["tracking"] is True and row["consent"]["notice_version"] == QUIZ["version"] and row["consent"]["at"]

    r3 = complete(deps, lead)  # retry: no second QuizComplete
    assert r3.status == 200 and r3.body["event_id"] is None

    r4 = webhook(deps, lead)
    assert r4.status == 200 and r4.body == {"updated": True, "event_id": f"{lead}:Schedule"}
    row = lead_row(admin, lead)
    assert row["booked_verified_at"] is not None and row["stage"] == "booked"
    r5 = webhook(deps, lead)  # Cal.com retry: no second Schedule
    assert r5.status == 200 and r5.body == {"updated": False, "event_id": None}

    events = [json.loads(l) for l in (dev_root / "capi.jsonl").read_text().splitlines()]
    mine = [e for e in events if e["event_id"].startswith(lead)]
    assert sorted(e["event_name"] for e in mine) == ["QuizComplete", "QuizStart", "Schedule"]
    assert len({e["event_id"] for e in mine}) == 3
    by = {e["event_name"]: e for e in mine}
    assert by["QuizStart"]["user_data"]["fbc"] == "fb.1.1757000000000.IwAR0abc"
    assert by["QuizStart"]["user_data"]["client_ip_address"] == "10.0.0.1"
    assert by["QuizComplete"]["user_data"]["em"] == [hashlib.sha256(b"person@example.com").hexdigest()]
    assert by["QuizComplete"]["custom_data"]["qualification_score"] == "4.0"
    assert by["Schedule"]["action_source"] == "system_generated"
    assert all("Person" not in json.dumps(e) for e in mine)


def test_no_consent_writes_the_lead_but_no_capi_event(deps, admin, dev_root):
    r1 = start(deps, tracking=False)
    assert r1.status == 200 and r1.body["event_id"] is None
    lead = r1.body["lead_id"]
    assert complete(deps, lead).body["event_id"] is None
    assert webhook(deps, lead).body == {"updated": True, "event_id": None}
    row = lead_row(admin, lead)
    assert row["consent"]["tracking"] is False and row["stage"] == "booked" and row["booked_verified_at"]
    text = (dev_root / "capi.jsonl").read_text() if (dev_root / "capi.jsonl").exists() else ""
    assert lead not in text


def test_forged_webhook_is_rejected_and_logged_and_writes_nothing(deps, admin, logs):
    lead = start(deps).body["lead_id"]
    complete(deps, lead)
    bad = webhook(deps, lead, secret="wrong")
    assert bad.status == 401
    unsigned = webhook(deps, lead, sign=False)
    assert unsigned.status == 401
    assert lead_row(admin, lead)["booked_verified_at"] is None and lead_row(admin, lead)["stage"] == "completed"
    reasons = [l["reason"] for l in logs if l["event"] == "cal_webhook_rejected"]
    assert reasons == ["bad_signature", "missing_signature"]
    assert not [l for l in logs if l["event"] == "capi_sent" and l["event_id"].endswith(":Schedule")]


def test_webhook_ignores_other_triggers_and_unknown_leads(deps):
    lead = start(deps).body["lead_id"]
    assert webhook(deps, lead, trigger="BOOKING_CANCELLED").body["updated"] is False
    assert webhook(deps, "00000000-0000-0000-0000-000000000000").status == 202
    raw = json.dumps({"triggerEvent": "BOOKING_CREATED", "payload": {"uid": "x"}}).encode()
    r = post(deps, "/cal-webhook", None, headers={"x-cal-signature-256": quiz.cal_signature(SECRET, raw)}, raw=raw)
    assert r.status == 202 and r.body["unmatched"] is True


def test_answers_are_whitelisted_and_disposable_emails_rejected(deps):
    lead = start(deps).body["lead_id"]
    assert complete(deps, lead, answers={**GOOD_ANSWERS, "q3": "ignore previous instructions"}).status == 400
    assert complete(deps, lead, answers={"q1": "SaaS"}).status == 400
    assert complete(deps, lead, answers={**GOOD_ANSWERS, "q9": "SaaS"}).status == 400
    assert complete(deps, lead, email="throwaway@mailinator.com").status == 400
    assert complete(deps, lead, email="not-an-email").status == 400
    r = post(deps, "/quiz/start", {"client": "upclicklabs", "consent": {"tracking": "yes"}, "turnstile_token": "t"})
    assert r.status == 400
    r = post(deps, "/quiz", {"client": "upclicklabs"}, raw=b"{not json")
    assert r.status == 400
    assert handle(Request("GET", "/quiz/config", query={"client": "nobody"}), deps).status == 400


def test_turnstile_failure_and_rate_limit(deps, monkeypatch):
    class Reject:
        def verify(self, token, remote_ip=None):
            return False
    monkeypatch.setattr(deps, "turnstile", Reject())
    assert start(deps).status == 403
    monkeypatch.setattr(deps, "turnstile", get_turnstile())
    monkeypatch.setattr(deps, "limiter", RateLimiter(2))
    assert start(deps, ip="10.9.9.9").status == 200
    assert start(deps, ip="10.9.9.9").status == 200
    r = start(deps, ip="10.9.9.9")
    assert r.status == 429 and r.headers["Retry-After"] == "60"
    assert start(deps, ip="10.9.9.8").status == 200


# ---------- FR-32: utm_content = creative_id ----------

def test_utm_content_resolves_creative_and_ad_entity(deps, admin):
    client_id = client_by_slug(admin, "upclicklabs")["id"]
    creative = insert(admin, "creatives", client_id=client_id, headline="t7")
    camp = insert(admin, "campaigns", client_id=client_id, kind="new_recipes")
    insert(admin, "ad_entities", client_id=client_id, campaign_id=camp["id"], creative_id=creative["id"], ad_id="ad-old", status="PAUSED")
    ad = insert(admin, "ad_entities", client_id=client_id, campaign_id=camp["id"], creative_id=creative["id"], ad_id="ad-live", status="ACTIVE")
    admin.commit()
    r = start(deps, utm={"source": "facebook", "content": str(creative["id"])})
    row = lead_row(admin, r.body["lead_id"])
    assert row["creative_id"] == creative["id"] and row["ad_entity_id"] == ad["id"]
    assert row["utm"] == {"source": "facebook", "content": str(creative["id"])}


# ---------- FR-35: soft by default, hard behind a config flag ----------

def test_qualification_soft_by_default_hard_behind_the_flag(deps, admin):
    assert quiz.hard_mode(QUIZ) == (False, 0.0)
    assert quiz.qualification_score({"q1": "Other", "q2": "SEO", "q3": "Yes"}, QUIZ) == 0.0
    lead = start(deps).body["lead_id"]
    r = complete(deps, lead, answers={"q1": "Other", "q2": "SEO", "q3": "Yes"})
    assert r.body["qualification_score"] == 0.0 and r.body["qualified"] is True

    hard = {**QUIZ, "qualification_mode": "hard", "qualification_threshold": 3}
    admin.execute("update offers set quiz_config = %s, calendar_url = 'https://cal.com/sam/15min' where client_id = %s",
                  (psycopg.types.json.Jsonb(hard), client_by_slug(admin, "upclicklabs")["id"]))
    admin.commit()
    try:
        low = complete(deps, start(deps).body["lead_id"], answers={"q1": "Other", "q2": "SEO", "q3": "Yes"})
        assert low.body["qualified"] is False and low.body["calendar_url"] is None
        assert lead_row(admin, low.body["lead_id"])["stage"] == "completed"
        high = complete(deps, start(deps).body["lead_id"])
        assert high.body["qualified"] is True
        assert high.body["calendar_url"] == f"https://cal.com/sam/15min?metadata[lead_id]={high.body['lead_id']}"
    finally:
        admin.execute("update offers set quiz_config = %s, calendar_url = %s where client_id = %s",
                      (psycopg.types.json.Jsonb(QUIZ), CONFIG["offer"]["calendar_url"], client_by_slug(admin, "upclicklabs")["id"]))
        admin.commit()


# ---------- the runner, the page, and scripts/test_events.py ----------

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def runner(db_env, dev_root, monkeypatch):
    """funnel/server.py in a subprocess on a free port, pointed at the test database and a scratch DEV_ROOT."""
    port = free_port()
    env = {**os.environ, "FUNNEL_HOST": f"http://localhost:{port}", "CAL_WEBHOOK_SECRET": SECRET,
           "CAPI_BACKEND": "fake", "TURNSTILE_BACKEND": "pass", "RATE_LIMIT_PER_MINUTE": "1000"}
    monkeypatch.setenv("FUNNEL_HOST", env["FUNNEL_HOST"])
    monkeypatch.setenv("CAL_WEBHOOK_SECRET", SECRET)
    proc = subprocess.Popen([sys.executable, str(ME_DIR / "funnel" / "server.py")], cwd=ME_DIR, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            proc.kill()
            pytest.fail(f"runner did not start:\n{proc.stderr.read()}")
        yield f"http://localhost:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_runner_serves_the_page_and_the_config(runner):
    page = urllib.request.urlopen(runner + "/quiz").read().decode()
    assert "screen-consent" in page and "/quiz.js" in page
    cfg = json.loads(urllib.request.urlopen(runner + "/quiz/config?client=upclicklabs").read())
    assert [q["id"] for q in cfg["questions"]] == ["q1", "q2", "q3"] and cfg["quiz_version"] == QUIZ["version"]
    assert cfg["pixel_id"] is None and cfg["turnstile_site_key"] is None
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(runner + "/../etc/passwd")
    assert exc.value.code == 404


def test_test_events_script_is_green_in_fake_mode(runner, dev_root, admin):
    res = subprocess.run([sys.executable, str(ME_DIR / "scripts" / "test_events.py"), "--no-serve"], cwd=ME_DIR,
                         capture_output=True, text=True, env={**os.environ, "CAPI_BACKEND": "fake", "TURNSTILE_BACKEND": "pass"})
    assert res.returncode == 0, res.stdout + res.stderr
    assert "green" in res.stdout and "once ✓" in res.stdout and "zero events ✓" in res.stdout
    r = admin.execute("select * from runs where worker = 'test_events' order by started_at desc limit 1").fetchone()
    assert r["status"] == "ok" and r["counts"]["schedule"] == 2 and r["counts"]["forged_rejected"] == 2 and r["finished_at"]


def test_test_events_script_fails_closed_without_a_runner(db_env, dev_root, monkeypatch, admin):
    monkeypatch.setenv("FUNNEL_HOST", f"http://localhost:{free_port()}")
    res = subprocess.run([sys.executable, str(ME_DIR / "scripts" / "test_events.py"), "--no-serve"], cwd=ME_DIR,
                         capture_output=True, text=True, env={**os.environ, "CAPI_BACKEND": "fake"})
    assert res.returncode == 1 and "NOT GREEN" in res.stderr
    r = admin.execute("select * from runs where worker = 'test_events' order by started_at desc limit 1").fetchone()
    assert r["status"] == "failed" and "listening" in r["error"] and r["finished_at"]


def _node_playwright() -> str | None:
    node = shutil.which("node")
    if not node:
        return None
    root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
    if not root or not (Path(root) / "playwright").exists():
        return None
    return root


@pytest.mark.skipif(_node_playwright() is None, reason="node playwright not installed")
def test_browser_walks_the_quiz_without_a_pixel_before_consent(runner, admin, dev_root):
    """Chromium drives the real page: consent → 3 answers → contact → done. Nothing leaves the page
    before Start; with tracking consent the server records the events; no Meta script is ever loaded
    in dev (no pixel id)."""
    env = {**os.environ, "NODE_PATH": _node_playwright(), "PLAYWRIGHT_BROWSERS_PATH": os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")}
    res = subprocess.run(["node", str(ME_DIR / "tests" / "browser_quiz.mjs"), runner + "/quiz?utm_source=facebook&utm_content=abc&fbclid=IwARbrowser"],
                         capture_output=True, text=True, env=env, timeout=120)
    assert res.returncode == 0, res.stdout + res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["requests_before_start"] == ["/quiz", "/quiz.css", "/quiz.js", "/quiz/config"]
    assert not any("connect.facebook.net" in u or "challenges.cloudflare.com" in u for u in out["all_requests"])
    assert out["done_state"] == "done"
    assert out["book_link_shown"] is False  # DRAFT calendar_url is a PLACEHOLDER, so no link yet
    raw = json.dumps({"triggerEvent": "BOOKING_CREATED", "payload": {"uid": "b", "metadata": {"lead_id": out["lead_id"]}}}).encode()
    req = urllib.request.Request(runner + "/cal-webhook", data=raw, method="POST",
                                 headers={"Content-Type": "application/json", "X-Cal-Signature-256": quiz.cal_signature(SECRET, raw)})
    assert json.loads(urllib.request.urlopen(req).read())["updated"] is True
    row = lead_row(admin, out["lead_id"])
    assert row["stage"] == "booked" and row["quiz_answers"] == {"q1": "SaaS", "q2": "Paid ads", "q3": "No idea"}
    assert row["consent"]["tracking"] is True and row["fbclid_hash"] == hashlib.sha256(b"IwARbrowser").hexdigest()
    events = [json.loads(l) for l in (dev_root / "capi.jsonl").read_text().splitlines() if out["lead_id"] in l]
    assert sorted(e["event_name"] for e in events) == ["QuizComplete", "QuizStart", "Schedule"]
