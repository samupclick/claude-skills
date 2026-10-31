"""scripts/monday_memo.py (FR-43) against the throwaway warehouse (conftest.test_db) and the file email backend under a
scratch DEV_ROOT. Nothing is mocked. Each test gets its own client row. The golden body covers the five sections in
order, the honesty rules (sub-sample numbers grade nothing, a rejection the market never saw is not graded), the
NFR-2 content rules, and the DR-3 key scan over a small code tree written by the test (the real tree changes with
every ticket; `test_key_scan_on_this_repository` checks the scan against the real one).

Regenerate the golden after a deliberate format change: `MEMO_GOLDEN_WRITE=1 python3 -m pytest tests/test_monday_memo.py -k golden`
and review the diff; the scenario uses fixed ids and timestamps so the body is byte-identical between runs."""
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
GOLDEN = ME_DIR / "fixtures" / "monday" / "golden-body.txt"
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 14, 7, 0, tzinfo=UTC)          # a Monday, 07:00 UTC (the me-monday cron)
SINCE = NOW - dt.timedelta(days=7)
CFG = {"targets": {"ctr_floor": 0.01, "kill_impressions": 2000}, "batch": {"recipes": 3, "executions_per_recipe": 2}}


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"memo_test_{name}", ME_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def memo_mod():
    return load_script("monday_memo")


def fixed(n: int) -> str:
    return str(uuid.UUID(int=(0x43000000 + n) << 96))


# ---------- the DR-3 key scan (pure) ----------

NOTES = """# notes

## JSONB keys in use

| Column | Key | Written by | Meaning |
|--------|-----|-----------|---------|
| `clients.config` | whole file | `scripts/seed.py` | the config |
| `briefs.spec` | `proposal_number`, `format_layer` {`family`, `copy_length`}, `source` {`brand`} | `scripts/alpha.py` | the brief |
| `actions.evidence` | `window` {since, until}, `rule` | `scripts/alpha.py` | kill evidence |
| `learnings.evidence` | `sample_reached` (true) | `scripts/beta.py` | the learning |
| `runs.counts` | `<any>` | `warehouse.client.run()` | counters; each worker documents its own keys |
| `runs.counts` | `proposals` | `scripts/alpha.py` | proposals written |
| `campaigns.active_lever_reason` | text | `scripts/beta.py` | not jsonb |

## Next section
"""

SCHEMA = """create table clients (
  id uuid primary key,
  config       jsonb not null default '{}'
);
create table briefs (
  id uuid primary key,
  spec                jsonb default '{}'
);
create table actions (
  id uuid primary key,
  evidence          jsonb not null default '{}'
);
create table learnings (
  id uuid primary key,
  evidence       jsonb not null default '{}'
);
create table runs (
  id uuid primary key,
  counts       jsonb default '{}'
);
create view mart_floor with (security_invoker = true) as
select id, (config->'targets'->>'ctr_floor')::numeric as ctr_floor from clients;
create view plain_view with (security_invoker = true) as
select b.spec->>'proposal_number' as n from briefs b;
"""

ALPHA = '''"""alpha writes briefs.spec and reads it back."""
SQL = "select * from briefs b order by (b.spec->>'proposal_number')::int"
def f(b, config, r):
    layer = (b.get("spec") or {}).get("format_layer") or {}
    config["targets"]["ctr_floor"]
    r.counts["proposals"] = 3
    return spec.get("source")
'''

BETA = '''"""beta reads what alpha wrote."""
def g(c, cfg, a):
    n = (c.get("brief_spec") or {}).get("proposal_number")
    x = c["spec"]["proposal_number"]
    floor = cfg.get("targets")
    ok = a["evidence"].get("sample_reached")
    return r.counts.get("proposals")
'''


def code_tree(root: Path) -> Path:
    (root / "warehouse").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "warehouse" / "schema-notes.md").write_text(NOTES)
    (root / "warehouse" / "schema.sql").write_text(SCHEMA)
    (root / "scripts" / "alpha.py").write_text(ALPHA)
    (root / "scripts" / "beta.py").write_text(BETA)
    return root


def test_documented_keys_take_top_level_keys_writers_and_wildcards(memo_mod):
    doc = memo_mod.documented_keys(NOTES, {"config": ["clients"], "spec": ["briefs"], "evidence": ["actions", "learnings"], "counts": ["runs"]})
    assert set(doc) == {"clients.config", "briefs.spec", "actions.evidence", "learnings.evidence", "runs.counts"}, "text columns are not JSONB"
    assert doc["briefs.spec"]["proposal_number"] == {"alpha"} and set(doc["briefs.spec"]) == {"proposal_number", "format_layer", "source"}
    assert doc["clients.config"] == {"*": {"seed"}}, "a row without a backticked key documents the whole object"
    assert doc["runs.counts"] == {"proposals": {"alpha"}}, "`<any>` documents nothing: each worker documents its own keys"
    assert set(doc["actions.evidence"]) == {"window", "rule"}, "nested keys inside {} are not top-level keys"


def test_key_scan_finds_reads_by_a_second_worker_or_a_mart(memo_mod, tmp_path):
    due = memo_mod.keys_due(code_tree(tmp_path / "code"))
    by = {(d["column"], d["key"]): d for d in due}
    # read by beta and a view besides its writer alpha
    assert by[("briefs.spec", "proposal_number")]["readers"] == ["alpha", "beta", "view plain_view"]
    # clients.config is a whole-file row: any key read by two workers or by a mart is due
    assert by[("clients.config", "targets")]["readers"] == ["alpha", "beta", "mart mart_floor"] and by[("clients.config", "targets")]["mart"]
    # `ok = a["evidence"].get(...)`: the reader is beta, which also wrote it (writer of learnings.evidence) -> not due
    assert ("learnings.evidence", "sample_reached") not in by
    # alpha writes and reads its own format_layer / source: one worker, no mart -> not due
    assert ("briefs.spec", "format_layer") not in by and ("briefs.spec", "source") not in by
    # an assignment is a write, not a read: alpha's `r.counts["proposals"] = 3` is not counted; beta reads it -> due
    assert by[("runs.counts", "proposals")]["readers"] == ["beta"] and by[("runs.counts", "proposals")]["writers"] == ["alpha"]
    assert [(d["column"], d["key"]) for d in due] == sorted((d["column"], d["key"]) for d in due)
    assert by[("briefs.spec", "proposal_number")]["places"] == 4 and all(d["places"] >= 1 for d in due)


def test_whole_config_file_row_expands_to_the_config_files_keys(memo_mod, tmp_path):
    root = code_tree(tmp_path / "code")
    (root / "config" / "clients").mkdir(parents=True)
    (root / "config" / "clients" / "acme.json").write_text('{"_status": "DRAFT", "targets": {"ctr_floor": 0.01}, "batch": {}}')
    (root / "scripts" / "gamma.py").write_text('def h(config):' + chr(10) + '    return config.get("questions"), config["batch"]' + chr(10))
    by = {(d["column"], d["key"]): d for d in memo_mod.keys_due(root)}
    assert ("clients.config", "targets") in by, "a key of the config file read by two workers and a mart"
    assert ("clients.config", "questions") not in by, "a `config` variable that is not the client config reads no documented key"
    assert ("clients.config", "batch") not in by, "read by one worker only, and seed.py is setup, not a first worker"


def test_key_scan_on_this_repository(memo_mod):
    due = {(d["column"], d["key"]): d for d in memo_mod.keys_due(ME_DIR)}
    pn = due[("briefs.spec", "proposal_number")]["readers"]
    assert {"gate", "plan_batch", "render_creatives"} <= set(pn)
    targets = due[("clients.config", "targets")]
    assert targets["mart"] and "mart mart_kill_scale_candidates" in targets["readers"]
    assert ("raw_ingest.payload", "sha256") not in due, "a key nothing reads is never due"


# ---------- the memo against the warehouse ----------

class Harness:
    def __init__(self, admin, client, mod, capsys, outbox, code_root):
        self.admin, self.client, self.mod, self.capsys, self.outbox, self.code_root = admin, client, mod, capsys, outbox, code_root
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

    def run(self, *args, now=NOW, since=SINCE):
        argv = ["--client", self.slug, "--now", now.isoformat(), "--code-root", str(self.code_root), *args]
        if since is not None:
            argv += ["--since", since.isoformat()]
        rc = self.mod.main(argv)
        out = self.capsys.readouterr()
        return rc, out.out + out.err

    def emails(self):
        return [BytesParser(policy=policy.default).parsebytes(f.read_bytes()) for f in sorted(self.outbox.glob("*.eml"))]

    def body(self, msg):
        return msg.get_body(preferencelist=("plain",)).get_content()

    def runs(self):
        return self.q("select * from runs where client_id=%s and worker='memo' order by started_at", self.client_id)


@pytest.fixture
def h(db_env, dev_root, monkeypatch, memo_mod, capsys, tmp_path):
    monkeypatch.setenv("EMAIL_BACKEND", "file")
    monkeypatch.setenv("CHECKIN_TO", "sam@example.invalid")
    monkeypatch.setenv("PIPELINE_PAUSED", "false")
    admin = connect("sam_admin", job="test")
    client = insert(admin, "clients", name="FR-43 test", slug=f"memo-{uuid.uuid4().hex[:8]}", daily_cap=Decimal("45.00"), currency="EUR", config=CFG)
    admin.commit()
    yield Harness(admin, client, memo_mod, capsys, dev_root / "outbox", code_tree(tmp_path / "code"))
    admin.close()


def golden_scenario(h: Harness):
    """A week of pipeline life with fixed ids and timestamps: learnings promoted, refuted, still proposed and promoted
    before the window; batch-001 picked, gated, launched (three creatives of one variant at sample size, one
    sub-sample, one rejected, one approved without delivery); batch-002 open with four proposals."""
    at = lambda d, hh, mm=0: dt.datetime(2026, 9, d, hh, mm, tzinfo=UTC)  # noqa: E731
    h.sql("update clients set id=%s, slug='memo-golden' where id=%s", fixed(0), h.client_id)
    h.client_id, h.slug = uuid.UUID(fixed(0)), "memo-golden"
    cid = h.client_id
    # section 1
    h.ins("learnings", id=fixed(1), client_id=cid, scope="client", hypothesis="screenshot-ad beats stat-card on link CTR",
          component_type="template", component_ref="screenshot-ad", direction="beat", effect_size=Decimal("0.00400"), sample=6400,
          posterior=Decimal("0.950"), status="supported", created_by="agent", created_at=at(1, 6), updated_at=at(10, 6))
    h.ins("learnings", id=fixed(2), client_id=cid, scope="client", hypothesis="pain_led angle misses (notes www.example.invalid/x)",
          component_type="angle", component_ref="pain_led", direction="miss", effect_size=Decimal("0.00100"), sample=2100,
          posterior=Decimal("0.400"), status="refuted", created_by="agent", created_at=at(2, 6), updated_at=at(12, 6))
    h.ins("learnings", id=fixed(3), client_id=cid, scope="client", hypothesis="hand-written by Sam", status="proposed", created_by="sam",
          evidence={"sample_reached": False}, created_at=at(9, 6), updated_at=at(9, 6))
    h.ins("learnings", id=fixed(4), client_id=cid, scope="client", hypothesis="promoted before the window", status="supported",
          created_by="agent", created_at=at(1, 6), updated_at=at(5, 6))
    # batch-001: picked, produced, gated, launched
    b1 = h.ins("experiments", id=fixed(10), client_id=cid, name="batch-001", capacity=6, created_at=at(1, 8))
    brief_a = h.ins("briefs", id=fixed(11), client_id=cid, experiment_id=b1["id"], family="screenshot_ad", angle="outcome_led",
                    spec={"proposal_number": 1, "chosen": True}, created_at=at(1, 8, 1))
    brief_b = h.ins("briefs", id=fixed(12), client_id=cid, experiment_id=b1["id"], family="screenshot_ad", angle="proof_led",
                    spec={"proposal_number": 3, "chosen": True}, created_at=at(1, 8, 2))
    h.ins("selections", id=fixed(13), client_id=cid, experiment_id=b1["id"], proposed=[brief_a["id"], brief_b["id"]],
          chosen=[brief_a["id"], brief_b["id"]], rejected=[], selected_by="sam", created_at=at(1, 9))
    camp = h.ins("campaigns", id=fixed(14), client_id=cid, kind="new_recipes", external_id="cmp-memo", status="ACTIVE", created_at=at(2, 9))
    creatives = [  # (n, brief, variant, status, sam, agent, impressions, clicks)
        (1, brief_a, "notes-app checklist", "live", "approve", "approve", 2400, 30),
        (2, brief_a, "notes-app checklist", "live", "approve", "reject", 2100, 15),
        (3, brief_b, "notes-app checklist", "live", "approve", "approve", 2050, 25),
        (4, brief_b, "email inbox https://evil.example/x", "live", "approve", "approve", 800, 12),
        (5, brief_b, "email inbox https://evil.example/x", "archived", "reject", "reject", None, None),
        (6, brief_a, "notes-app checklist", "approved", "approve", "approve", None, None),
    ]
    for n, brief, variant, status, sam, agent, imps, clicks in creatives:
        c = h.ins("creatives", id=fixed(20 + n), client_id=cid, brief_id=brief["id"], experiment_id=b1["id"], status=status,
                  renderer="html_template", template="screenshot-ad", image_model="placeholder", version=1, created_at=at(2, 10, n))
        h.ins("creative_components", creative_id=c["id"], component_type="family", component_ref="screenshot_ad")
        h.ins("creative_components", creative_id=c["id"], component_type="variant", component_ref=variant)
        h.ins("gate_scores", id=fixed(30 + n), creative_id=c["id"], attempt=1, scored_by="agent", mode="shadow", verdict=agent,
              decision_channel="auto", avg_score=Decimal("3.80") if agent == "approve" else Decimal("3.10"), passed=True, created_at=at(3, 10, n))
        h.ins("gate_scores", id=fixed(40 + n), creative_id=c["id"], attempt=1, scored_by="sam", mode="blocking", verdict=sam,
              decision_channel="chat", passed=True, created_at=at(3, 11, n))
        if imps is not None:
            ad = h.ins("ad_entities", id=fixed(50 + n), client_id=cid, campaign_id=camp["id"], creative_id=c["id"], adset_id="as-memo",
                       ad_id=f"ad-memo-{n}", status="ACTIVE", created_at=at(4, 9, n))
            h.ins("ad_metrics_daily", ad_entity_id=ad["id"], day=dt.date(2026, 9, 12), fetched_on=dt.date(2026, 9, 13),
                  impressions=imps, link_clicks=clicks, spend=Decimal("20.00"))
    # batch-002: open, four proposals (one hook carries a URL that must not survive)
    b2 = h.ins("experiments", id=fixed(60), client_id=cid, name="batch-002", capacity=6, created_at=at(13, 18))
    for n, family, hook, brand in ((1, "screenshot_ad", "when a prospect asks an AI who does this, is it you?", "AG1"),
                                   (2, "stat_card", "one number your last agency never reported", "Ridge"),
                                   (3, "screenshot_ad", "see https://evil.example/now for the answer", "HexClad"),
                                   (4, "screenshot_ad", "three names, none of them yours", "Dr. Squatch")):
        hk = h.ins("hooks", id=fixed(70 + n), client_id=cid, text=hook, trust_tier="owned")
        h.ins("briefs", id=fixed(80 + n), client_id=cid, experiment_id=b2["id"], family=family, angle="outcome_led", hook_id=hk["id"],
              changed_ingredients=["offer", "product_nouns"],
              spec={"proposal_number": n, "chosen": None, "source": {"brand": brand, "variant": f"variant {n}", "source_strength": 4 - n}},
              created_at=at(13, 18, n))


def test_golden_body_five_sections_in_order(h):
    golden_scenario(h)
    rc, out = h.run()
    assert rc == 0, out
    msgs = h.emails()
    assert len(msgs) == 1 and msgs[0]["To"] == "sam@example.invalid" and msgs[0]["Subject"].startswith("[me] monday memo memo-golden 2026-09-14")
    body = h.body(msgs[0])
    if os.environ.get("MEMO_GOLDEN_WRITE"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(body)
    assert body == GOLDEN.read_text()
    headings = re.findall(r"^(\d)\. (.+?) \(\d+\)$", body, re.MULTILINE)
    assert [n for n, _ in headings] == ["1", "2", "3", "4", "5"]
    assert [t for _, t in headings] == list(h.mod.SECTIONS)
    sec = {int(n): part for n, part in re.findall(r"^(\d)\. .*?\n(.*?)(?=^\d\. |\Z)", body, re.MULTILINE | re.DOTALL)}
    # 1: promoted and refuted inside the window only; the still-proposed count is context
    assert "supported (client) — screenshot-ad beats stat-card" in sec[1] and "refuted (client) — pain_led angle misses" in sec[1]
    assert "promoted before the window" not in sec[1] and "1 learning(s) still proposed" in sec[1]
    # 2: honest about sample size; rejections are not graded by a market that never saw them
    assert "at sample size: 3 of 5 approved" in sec[2] and "sub-sample (800 of 2000 impressions): grades nothing yet" in sec[2]
    assert "1 approved creative(s) have no delivery yet" in sec[2] and "1 rejected by Sam never ran" in sec[2]
    assert "agent shadow verdict agreed with Sam on 5 of 6" in sec[2]
    # 3: one variant backed by three creatives at sample size; the other is named as the closest miss only when it is
    assert "propose `notes-app checklist` (family screenshot_ad)" in sec[3] and "3 creatives at sample size" in sec[3]
    assert "email inbox" not in sec[3], "a closest miss is named only when nothing is proposed"
    # 4: the DR-3 scan of the test's code tree
    assert "briefs.spec.proposal_number" in sec[4] and "clients.config.targets" in sec[4] and "mart mart_floor" in sec[4]
    # 5: the open proposal, with the template mark and the default the planner would take
    assert "batch-002 waits for picks: 4 proposals" in sec[5] and "#2 stat_card" in sec[5] and "template NONE" in sec[5]
    assert "default after 20 minutes: #1, #3, #4" in sec[5]
    # NFR-2: no URL from a row survives, the HTML part is the escaped text
    assert "http" not in body and "www." not in body and "[url removed]" in body
    html = msgs[0].get_body(preferencelist=("html",)).get_content()
    assert "<pre" in html and "Monday memo" in html
    r = h.runs()[-1]
    assert r["status"] == "ok" and r["counts"]["sent"] == 1 and r["counts"]["learnings"] == 2 and r["counts"]["variant_proposals"] == 1
    assert r["counts"]["open_proposals"] == 4 and r["counts"]["taste_creatives"] == 6 and r["counts"]["keys_due"] >= 3


def test_empty_client_says_none_in_every_section(h, monkeypatch):
    monkeypatch.setenv("CHECKIN_TO", "")
    rc, out = h.run("--dry-run")
    assert rc == 0, out
    assert "1. Learnings promoted / refuted (0)" in out and "none promoted or refuted since 2026-09-07 07:00 UTC" in out
    assert "no creative has a verdict from Sam yet" in out and "none: no creative carries a variant component yet" in out
    assert "none open: no proposal is waiting for picks" in out
    assert not h.outbox.exists() or not list(h.outbox.glob("*.eml"))
    assert h.runs()[-1]["counts"]["sent"] == 0


def test_paused_or_stuck_refuses_and_closes_the_runs_row(h, monkeypatch):
    monkeypatch.setenv("PIPELINE_PAUSED", "true")
    rc, out = h.run()
    assert rc == 2 and "paused" in out and h.runs()[-1]["status"] == "failed"
    monkeypatch.setenv("PIPELINE_PAUSED", "false")
    h.ins("actions", client_id=h.client_id, action_type="kill", target_type="ad_entity", target_id=fixed(99), proposal_key=f"memo:{uuid.uuid4()}",
          status="applying", executor_run_id=fixed(98))
    rc, out = h.run()
    assert rc == 2 and "applying" in out
    r = h.runs()[-1]
    assert r["status"] == "failed" and r["finished_at"] and "applying" in r["error"]
    assert h.emails() == []


def test_missing_recipient_fails_the_run_by_name(h, monkeypatch):
    monkeypatch.setenv("CHECKIN_TO", "")
    with pytest.raises(Exception, match="CHECKIN_TO"):
        h.run()
    r = h.runs()[-1]
    assert r["status"] == "failed" and "CHECKIN_TO" in r["error"]


def test_window_defaults_to_the_previous_memo(h):
    rc, _ = h.run(now=NOW - dt.timedelta(days=7), since=None)
    first = h.runs()[-1]
    assert first["counts"]["since"] == (NOW - dt.timedelta(days=14)).isoformat()   # no previous memo: 7 days
    rc, _ = h.run(since=None)
    assert h.runs()[-1]["counts"]["since"] == first["started_at"].isoformat()


def test_memo_goes_through_the_gmail_connector_queue_once_per_day(h, monkeypatch, dev_root):
    """EMAIL_BACKEND=gmail_connector (the go-live value): the memo is queued under memo-<slug>-<UTC day> with the
    check-in's claim, and the me-monday routine's last step delivers it with checkin.py --send-pending / --mark-sent."""
    monkeypatch.setenv("EMAIL_BACKEND", "gmail_connector")
    monkeypatch.delenv("EMAIL_QUEUE_DIR", raising=False)
    key = f"memo-{h.slug}-2026-09-14"
    rc, out = h.run()
    assert rc == 0 and f"queued {key}: [me] monday memo {h.slug} 2026-09-14" in out and "sent <" not in out
    assert [p.name for p in (dev_root / "pending-send").glob("*.json")] == [f"{key}.json"] and h.emails() == []
    r = h.runs()[-1]
    assert r["status"] == "ok" and r["counts"]["email_key"] == key and r["counts"]["queued"] == 1 and r["counts"]["sent"] == 0
    rc, out = h.run()                                                        # same day: never queued twice
    assert rc == 0 and f"not queued: memo {key} was already queued" in out and h.runs()[-1]["counts"]["duplicate"] == 1
    checkin = load_script("checkin")
    assert checkin.main(["--client", h.slug, "--send-pending"]) == 0
    out = h.capsys.readouterr().out
    assert f"--- {key}" in out and "Gmail connector tool send_message" in out and "1. Learnings promoted / refuted" in out
    assert checkin.main(["--client", h.slug, "--mark-sent", key, "--message-id", "19a2f3c4d5e6f708"]) == 0
    assert f"marked sent: {key}" in h.capsys.readouterr().out and not list((dev_root / "pending-send").glob("*.json"))
    rc, out = h.run()                                                        # delivered: the warehouse still refuses
    assert rc == 0 and "not queued" in out and "sent as 19a2f3c4d5e6f708" in out


def test_a_duplicate_or_a_dry_run_memo_never_moves_the_window(h, monkeypatch):
    """A second memo on the same Monday queues nothing and a mid-week dry run sends nothing: the next memo's window
    still opens at the memo that was queued, so no section-1 learning falls between two delivered memos."""
    monkeypatch.setenv("EMAIL_BACKEND", "gmail_connector")
    monkeypatch.delenv("EMAIL_QUEUE_DIR", raising=False)
    rc, _ = h.run(since=None)
    first = h.runs()[-1]
    assert rc == 0 and first["counts"]["queued"] == 1
    rc, out = h.run(since=None)
    assert "not queued" in out and h.runs()[-1]["counts"]["duplicate"] == 1 and h.runs()[-1]["status"] == "ok"
    rc, _ = h.run("--dry-run")
    assert h.runs()[-1]["status"] == "ok" and h.runs()[-1]["counts"]["sent"] == 0
    rc, _ = h.run(now=NOW + dt.timedelta(days=7), since=None)
    assert h.runs()[-1]["counts"]["since"] == first["started_at"].isoformat()


def test_memo_has_no_side_effect_beyond_the_email_adapter():
    src = (ME_DIR / "scripts" / "monday_memo.py").read_text()
    assert "get_email()" in src and "queue_checkin" in src and "adapters.meta" not in src and "smtplib" not in src and "insert_actions" not in src
    assert 'connect("worker"' in src and "WAREHOUSE_URL_EXECUTOR" not in src


def test_monday_routine_dry_run_sends_the_memo(db_env, dev_root):
    """The me-monday prompt executed as its scripts: status, then the memo through the file backend."""
    import psycopg
    with psycopg.connect(db_env["WAREHOUSE_URL_ADMIN"], autocommit=True) as admin:
        admin.execute("update clients set paused = false where slug = 'upclicklabs'")
        admin.execute("delete from actions where status = 'applying'")
    env = {**os.environ, "EMAIL_BACKEND": "file", "CHECKIN_TO": "sam@example.invalid", "PIPELINE_PAUSED": "false"}
    res = subprocess.run([sys.executable, str(ME_DIR / "scripts" / "routines.py"), "dry-run", "me-monday"], cwd=ME_DIR, env=env,
                         capture_output=True, text=True)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    steps = out.split("--- steps", 1)[1].split("--- runs summary", 1)[0]
    assert [line.split()[-1] for line in steps.strip().splitlines()] == ["ok", "ok", "ok"]   # file backend: nothing pending to send
    assert "not built" not in out and "sent <" in out and list((dev_root / "outbox").glob("*.eml"))
    assert "memo       ok" in out.split("--- runs summary", 1)[1]
