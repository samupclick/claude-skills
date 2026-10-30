"""scripts/seed.py parsing: families.md is read as-is and cross-kind name reuse is reported, not hidden."""
import importlib.util
from pathlib import Path

ME_DIR = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("seed", ME_DIR / "scripts" / "seed.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def test_parse_families_reads_all_three_kinds_from_the_draft():
    fams = seed.parse_families((ME_DIR / "references" / "families.md").read_text())
    kinds = {k for _, k in fams}
    assert kinds == {"format", "hook_type", "angle"}
    assert ("job_photo_bubble", "format") in fams and ("number", "hook_type") in fams and ("pain_led", "angle") in fams
    assert len([f for f in fams if f[1] == "format"]) == 16


def test_name_conflicts_reports_names_used_for_two_kinds():
    fams = [("pain", "hook_type"), ("contrarian", "hook_type"), ("contrarian", "angle"), ("pain_led", "angle")]
    assert seed.name_conflicts(fams) == {"contrarian": ["hook_type", "angle"]}
    assert seed.name_conflicts([("a", "format")]) == {}


# ---------- --config: a second client seeds from its own file (hand-off Step 6) ----------

import json  # noqa: E402
import uuid  # noqa: E402

import psycopg  # noqa: E402
import pytest  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402


def _client_config(tmp_path, slug):
    cfg = json.loads((ME_DIR / "config" / "clients" / "upclicklabs.json").read_text())
    cfg["client"] = {**cfg["client"], "name": "Seed Test", "slug": slug, "site": "https://example.com"}
    cfg["currency"] = "USD"
    cfg["offer"] = {**cfg["offer"], "name": "Seed test pillow", "terminal_metric": "purchase",
                    "landing_url": "https://example.com/products/pillow", "funnel_host": None}
    cfg["icp"] = {**cfg["icp"], "label": "seed test icp"}
    path = tmp_path / f"{slug}.json"
    path.write_text(json.dumps(cfg))
    return path


def _cleanup(admin_url, slug):
    with psycopg.connect(admin_url) as conn:
        cid = conn.execute("select id from clients where slug = %s", (slug,)).fetchone()
        if cid:
            for table in ("runs", "offers", "icps"):
                conn.execute(f"delete from {table} where client_id = %s", cid)
            conn.execute("delete from clients where id = %s", cid)


def test_main_seeds_the_client_its_config_names(db_env, tmp_path, capsys):
    slug = f"seedtest-{uuid.uuid4().hex[:8]}"
    path = _client_config(tmp_path, slug)
    try:
        assert seed.main(["--config", str(path)]) == 0
        assert "'clients': 1, 'offers': 1, 'icps': 1" in capsys.readouterr().out
        with psycopg.connect(db_env["WAREHOUSE_URL_ADMIN"], row_factory=dict_row) as conn:
            client = conn.execute("select id, currency, config->'client'->>'slug' as cfg_slug from clients where slug = %s",
                                  (slug,)).fetchone()
            offer = conn.execute("select terminal_metric, landing_url, funnel_host from offers where client_id = %s",
                                 (client["id"],)).fetchone()
            run = conn.execute("select status, client_id from runs where worker = 'seed' and client_id = %s",
                               (client["id"],)).fetchone()
        assert (client["currency"], client["cfg_slug"]) == ("USD", slug)
        assert offer == {"terminal_metric": "purchase", "landing_url": "https://example.com/products/pillow", "funnel_host": None}
        assert run["status"] == "ok"

        assert seed.main(["--config", str(path)]) == 0   # idempotent: the second run adds nothing
        assert "'clients': 0, 'offers': 0, 'icps': 0" in capsys.readouterr().out
    finally:
        _cleanup(db_env["WAREHOUSE_URL_ADMIN"], slug)


def test_main_without_config_still_seeds_upclicklabs():
    assert seed.parse_args([]).config == ME_DIR / "config" / "clients" / "upclicklabs.json"


def test_a_broken_config_fails_the_run_without_blaming_upclicklabs(db_env, tmp_path):
    path = tmp_path / "circadian-broken.json"
    path.write_text("{ not json")
    with pytest.raises(json.JSONDecodeError):
        seed.main(["--config", str(path)])
    with psycopg.connect(db_env["WAREHOUSE_URL_ADMIN"], row_factory=dict_row) as conn:
        run = conn.execute("select status, client_id, error from runs where worker = 'seed' "
                           "order by started_at desc limit 1").fetchone()
        conn.execute("delete from runs where worker = 'seed' and status = 'failed' and error like 'JSONDecodeError%%'")
    assert run["status"] == "failed" and run["client_id"] is None and run["error"].startswith("JSONDecodeError")


def test_refresh_config_rewrites_the_client_config_from_its_file(db_env, tmp_path, capsys):
    slug = f"seedtest-{uuid.uuid4().hex[:8]}"
    path = _client_config(tmp_path, slug)
    try:
        assert seed.main(["--config", str(path)]) == 0
        cfg = json.loads(path.read_text())
        cfg["inspo"] = {"dtc_seed": ["Fixture Pillow"], "pages": {"Fixture Pillow": "https://www.facebook.com/fixture"}}
        cfg["daily_cap"] = 60
        path.write_text(json.dumps(cfg))
        assert seed.main(["--config", str(path)]) == 0     # without the flag an existing client is left as it was
        with psycopg.connect(db_env["WAREHOUSE_URL_ADMIN"], row_factory=dict_row) as conn:
            assert conn.execute("select config->'inspo' as i from clients where slug = %s", (slug,)).fetchone()["i"] != cfg["inspo"]
        capsys.readouterr()
        assert seed.main(["--config", str(path), "--refresh-config"]) == 0
        assert "'config_refreshed': 1" in capsys.readouterr().out
        with psycopg.connect(db_env["WAREHOUSE_URL_ADMIN"], row_factory=dict_row) as conn:
            row = conn.execute("select config, daily_cap from clients where slug = %s", (slug,)).fetchone()
        assert row["config"]["inspo"] == cfg["inspo"] and float(row["daily_cap"]) == 60
    finally:
        _cleanup(db_env["WAREHOUSE_URL_ADMIN"], slug)
