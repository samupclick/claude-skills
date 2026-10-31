"""T3: scripts/pull_voc.py — FR-10 to FR-13 against the real local warehouse (never mocked)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import dict_row

from tests.conftest import ME_DIR

SCRIPT = ME_DIR / "scripts" / "pull_voc.py"
SEED_DIR = ME_DIR / "config" / "clients" / "upclicklabs" / "voc-seed"
NOTE_1 = SEED_DIR / "2026-08-12-call-fake-nordic-consulting.md"

spec = importlib.util.spec_from_file_location("pull_voc", SCRIPT)
pull_voc = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(ME_DIR))
sys.modules["pull_voc"] = pull_voc  # dataclasses resolve annotations through sys.modules
spec.loader.exec_module(pull_voc)


def _tree_digest(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def _run_script(env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "VOC_FIXTURE_DIR"}
    env.update({"MODEL_BACKEND": "fixture", "VOC_BACKEND": "fixture", "PIPELINE_PAUSED": "false", **(env_extra or {})})
    return subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, env=env, cwd=ME_DIR)


@pytest.fixture
def worker(db_env):
    with psycopg.connect(db_env["WAREHOUSE_URL_WORKER"], row_factory=dict_row) as conn:
        yield conn


@pytest.fixture
def admin(db_env):
    with psycopg.connect(db_env["WAREHOUSE_URL_ADMIN"], row_factory=dict_row, autocommit=True) as conn:
        yield conn


@pytest.fixture
def clean(admin):
    admin.execute("delete from voc_phrases; delete from raw_ingest; delete from runs where worker = 'voc'")
    yield
    admin.execute("delete from voc_phrases; delete from raw_ingest; delete from runs where worker = 'voc'")


# ---------- pure functions ----------

def test_normalise_is_case_punctuation_and_whitespace_insensitive():
    a = pull_voc.normalise("  How is this different from SEO?  Honestly…  ")
    b = pull_voc.normalise("how is this different from seo honestly")
    assert a == b == "how is this different from seo honestly"


def test_identifiers_found_in_the_seeded_fake_notes():
    ids = pull_voc.identifiers(NOTE_1.read_text())
    assert {"Henrik Lindqvist", "Nordic Consulting AB", "48 staff", "40k"} <= ids
    assert not any(w in ids for w in ("ChatGPT", "SEO", "AI", "Our", "Call"))
    ids2 = pull_voc.identifiers((SEED_DIR / "2026-08-19-call-fake-brightpath.md").read_text())
    assert {"Priya Raman", "BrightPath Software Ltd", "120 staff"} <= ids2
    thread = json.loads((ME_DIR / "fixtures" / "voc" / "placeholder-3.json").read_text())
    ids3 = pull_voc.identifiers(pull_voc.thread_text(thread))
    assert {"Brightwell Systems", "Tom Harrington", "200 staff"} <= ids3


def test_seeded_fake_name_fails_the_validator():
    ids = pull_voc.identifiers(NOTE_1.read_text())
    with pytest.raises(pull_voc.IdentifierLeak, match="Henrik Lindqvist"):
        pull_voc.validate_phrase("As Henrik Lindqvist said, our referrals are drying up", ids)
    with pytest.raises(pull_voc.IdentifierLeak, match="40k"):
        pull_voc.validate_phrase("we spent about 40k with our last agency", ids)
    with pytest.raises(pull_voc.IdentifierLeak, match="Nordic Consulting AB"):
        pull_voc.validate_phrase("nordic consulting ab is invisible", ids)
    # word boundaries: the region is not the company, a surname inside another word is not a leak
    pull_voc.validate_phrase("who does consulting in the Nordics", ids)
    pull_voc.validate_phrase("we spent a lot with our last SEO agency", ids)


def test_model_output_with_a_leaked_name_is_rejected_not_inserted(tmp_path, monkeypatch):
    """The validator is the second line of defence behind the model: a fixture that leaks the seeded name
    never reaches voc_phrases, and the rejection is counted."""
    from adapters.model.fixture import FixtureModel

    (tmp_path / "voc_extract.json").write_text(json.dumps({
        "phrases": [
            {"phrase": "Henrik Lindqvist says our referrals are drying up", "category": "trigger"},
            {"phrase": "Our referrals are drying up. Everyone's first step now is asking an AI.", "category": "trigger"},
        ],
        "identifiers_removed": ["Nordic Consulting AB"],
    }))
    src = pull_voc.vault_sources(SEED_DIR)[0]
    kept, rejected = pull_voc.extract(FixtureModel(tmp_path), src, pull_voc.load_prompts())
    assert [p["phrase"] for p in kept] == ["Our referrals are drying up. Everyone's first step now is asking an AI."]
    assert rejected == ["Henrik Lindqvist"]


def test_untrusted_text_enters_the_prompt_only_inside_the_data_block(tmp_path):
    from adapters.model.fixture import FixtureModel

    (tmp_path / "voc_extract.json").write_text(json.dumps({"phrases": [], "identifiers_removed": []}))
    model = FixtureModel(tmp_path)
    src = pull_voc.vault_sources(SEED_DIR)[0]
    system, instructions = pull_voc.load_prompts()
    pull_voc.extract(model, src, (system, instructions))
    user = model.last_prompt["user"]
    assert model.last_prompt["system"] == system
    assert user.index(instructions) < user.index("<untrusted_data>") < user.index("Henrik Lindqvist") < user.index("</untrusted_data>")
    assert "Henrik Lindqvist" not in system and "Henrik Lindqvist" not in instructions


def test_vault_sources_are_internal_weight_3_owned_and_skip_the_readme():
    srcs = pull_voc.vault_sources(SEED_DIR)
    assert [Path(s.ref).name for s in srcs] == sorted(p.name for p in SEED_DIR.glob("*.md") if p.name != "README.md")
    for s in srcs:
        assert (s.source, s.source_weight, s.visibility, s.trust_tier) == ("vault", 3, "internal", "owned")
        assert s.ref.startswith("config/clients/upclicklabs/voc-seed/") and "fake" in s.ref
        assert "tags:" not in s.text, "frontmatter is stripped before the text goes anywhere"


# ---------- schema facts (FR-11, FR-13) ----------

def test_schema_has_no_quotes_column_and_the_dedup_unique_constraint(worker):
    cols = {r["column_name"] for r in worker.execute(
        "select column_name from information_schema.columns where table_name = 'voc_phrases'").fetchall()}
    assert "quotes" not in cols and "quote" not in cols
    uniques = worker.execute("""
        select array_agg(a.attname order by k.n) as cols
        from pg_constraint c
        join lateral unnest(c.conkey) with ordinality as k(attnum, n) on true
        join pg_attribute a on a.attrelid = c.conrelid and a.attnum = k.attnum
        where c.conrelid = 'voc_phrases'::regclass and c.contype = 'u'
        group by c.oid""").fetchall()
    assert ["source_ref", "phrase_normalised"] in [u["cols"] for u in uniques]


# ---------- the script end to end ----------

def test_pull_voc_end_to_end(clean, worker, admin):
    before = _tree_digest(SEED_DIR)
    res = _run_script()
    assert res.returncode == 0, res.stdout + res.stderr
    assert _tree_digest(SEED_DIR) == before, "FR-10: the vault/seed folder is read-only to the worker"
    assert "where are we" in res.stdout.lower() or "slug" in res.stdout
    for secret in ("dev-worker_rw", "dev-postgres"):
        assert secret not in res.stdout + res.stderr

    rows = worker.execute("select * from voc_phrases order by created_at, phrase").fetchall()
    assert len(rows) >= 15
    vault = [r for r in rows if r["source"] == "vault"]
    public = [r for r in rows if r["source"] != "vault"]
    assert vault and public
    for r in vault:
        assert (r["visibility"], r["source_weight"], r["trust_tier"]) == ("internal", 3, "owned")
        assert r["source_ref"].startswith("config/clients/upclicklabs/voc-seed/") and r["source_ref"].endswith(".md")
    for r in public:
        assert (r["visibility"], r["source_weight"], r["trust_tier"], r["source"]) == ("public", 1, "public", "reddit")
        assert r["source_ref"].startswith("sha256:") and "http" not in r["source_ref"] and "reddit" not in r["source_ref"]
    assert {r["source_ref"] for r in public} == {pull_voc.url_ref(u) for u in pull_voc.load_config("upclicklabs")["voc"]["public_sources"]}
    assert len({r["source_ref"] for r in vault}) == 3 and len({r["source_ref"] for r in public}) == 3
    for r in rows:
        assert r["phrase_normalised"] == pull_voc.normalise(r["phrase"])
        assert r["category"] in pull_voc.CATEGORIES and r["client_id"] and r["icp_id"]
        assert r["frequency"] == 1 and r["embedding"] is None

    # FR-11: nothing identifying survived, checked against every source's own identifiers
    all_ids: set[str] = set()
    for src in pull_voc.vault_sources(SEED_DIR):
        all_ids |= pull_voc.identifiers(src.text)
    for f in (ME_DIR / "fixtures" / "voc").glob("*.json"):
        all_ids |= pull_voc.identifiers(pull_voc.thread_text(json.loads(f.read_text())))
    all_ids |= {"Henrik", "Lindqvist", "Priya", "Raman", "Stockholm", "Manchester", "Leeds", "Acme", "Brightwell", "Harrington"}
    for r in rows:
        assert pull_voc.leaked(r["phrase"], all_ids) is None, r["phrase"]

    # raw_ingest: one row per source; public payloads purge after 90 days and carry no author
    raw = worker.execute("select * from raw_ingest order by source").fetchall()
    assert len(raw) == 6
    for r in raw:
        if r["source"] == "vault":
            assert r["trust_tier"] == "owned" and r["purge_after"] is None
            assert set(r["payload"]) == {"kind", "path", "sha256", "bytes"}, "pointer and hash only, never the note text"
        else:
            assert r["trust_tier"] == "public" and r["purge_after"] is not None
            assert (r["purge_after"] - r["fetched_at"]).days == 90
            assert "author" not in json.dumps(r["payload"]).lower()
        assert r["dedup_key"] and r["client_id"]

    run = worker.execute("select * from runs where worker = 'voc' order by started_at desc limit 1").fetchone()
    assert run["status"] == "ok" and run["finished_at"] is not None and run["error"] is None
    assert run["counts"]["phrases_inserted"] == len(rows) and run["counts"]["phrases_duplicates"] == 0
    assert run["counts"]["sources_vault"] == 3 and run["counts"]["sources_public"] == 3
    assert run["counts"]["phrases_rejected_identifiers"] == 0 and run["api_calls"] == 6
    assert str(run["id"]) in res.stdout

    # re-run: the unique constraint is exercised, zero rows added
    res2 = _run_script()
    assert res2.returncode == 0, res2.stdout + res2.stderr
    assert worker.execute("select count(*) n from voc_phrases").fetchone()["n"] == len(rows)
    assert worker.execute("select count(*) n from raw_ingest").fetchone()["n"] == 6
    run2 = worker.execute("select * from runs where worker = 'voc' order by started_at desc limit 1").fetchone()
    assert run2["id"] != run["id"] and run2["status"] == "ok"
    assert run2["counts"]["phrases_inserted"] == 0 and run2["counts"]["phrases_duplicates"] == len(rows)
    assert run2["counts"]["raw_ingest_inserted"] == 0 and run2["counts"]["raw_ingest_duplicates"] == 6


def test_failed_public_source_is_retried_once_then_the_run_fails_with_vault_rows_kept(clean, worker, tmp_path):
    empty = tmp_path / "no-threads"
    empty.mkdir()
    res = _run_script({"VOC_FIXTURE_DIR": str(empty)})
    assert res.returncode == 1, res.stdout + res.stderr
    run = worker.execute("select * from runs where worker = 'voc' order by started_at desc limit 1").fetchone()
    assert run["status"] == "failed" and run["finished_at"] is not None
    assert "SourceFailed" in run["error"] and "sha256:" in run["error"]
    assert "http" not in run["error"] and "reddit.com" not in res.stderr
    assert run["counts"]["sources_failed"] == 3 and run["counts"]["source_retries"] == 3
    n = worker.execute("select count(*) n from voc_phrases where source = 'vault'").fetchone()["n"]
    assert n >= 10, "vault phrases committed before the public source failed"
    assert worker.execute("select count(*) n from voc_phrases where source <> 'vault'").fetchone()["n"] == 0


def test_paused_pipeline_refuses_and_still_closes_the_runs_row(clean, worker):
    res = _run_script({"PIPELINE_PAUSED": "true"})
    assert res.returncode == 2
    run = worker.execute("select * from runs where worker = 'voc' order by started_at desc limit 1").fetchone()
    assert run["status"] == "failed" and "paused" in run["error"].lower()
    assert worker.execute("select count(*) n from voc_phrases").fetchone()["n"] == 0


def test_worker_cannot_insert_a_phrase_that_bypasses_the_check_constraints(clean, worker):
    """The role for the job is worker_rw; the schema, not the script, has the last word on categories."""
    client = worker.execute("select id from clients where slug = 'upclicklabs'").fetchone()
    with pytest.raises(psycopg.errors.CheckViolation):
        worker.execute("insert into voc_phrases (client_id, phrase, phrase_normalised, category, source_ref) values (%s, 'x y z', 'x y z', 'praise', 'r')", (client["id"],))


# ---------- static guarantees ----------

def test_no_write_path_to_the_vault_and_no_wrong_role():
    text = SCRIPT.read_text() + "".join(p.read_text() for p in (ME_DIR / "adapters" / "voc").glob("*.py"))
    for bad in (r"write_text", r"write_bytes", r"open\([^)]*['\"][wa]", r"shutil\.", r"os\.remove", r"\.unlink\(", r"\.rename\(", r"rmtree", r"os\.rename", r"\.touch\("):
        assert not re.search(bad, text), bad
    assert 'connect("worker"' in SCRIPT.read_text()
    assert "executor" not in SCRIPT.read_text().lower().replace("apply_actions", "")
    assert "vault_path" not in SCRIPT.read_text(), "the worker reads the seed folder, never the vault itself"
