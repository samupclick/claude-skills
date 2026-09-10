"""Routine definitions (T11, FR-48): config/routines.json is the machine-readable twin of SKILL.md §8, and the 08:00
routine can be dry-run locally against the dev warehouse (quiz decision 7). Nothing registers a Routine here."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ME_DIR = Path(__file__).resolve().parent.parent


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"script_{name}", ME_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_routines_json_matches_skill_md_section_8():
    mod = load_script("routines")
    defs = mod.load()
    assert [r["name"] for r in defs["routines"]] == ["me-morning", "me-evening", "me-monday"]
    assert [r["cron_utc"] for r in defs["routines"]] == ["0 6 * * *", "0 18 * * *", "0 7 * * 1"]   # 08:00 / 20:00 CEST, Monday 09:00
    assert defs["session"] == "fresh" and (ME_DIR.parent / defs["hook"]).exists()
    assert mod.drift(defs) == []
    assert len(mod.skill_table()) == 3
    # every step names a script path under marketing-engineer/ (built or owed to a later ticket) and the client placeholder
    for r in defs["routines"]:
        for s in r["steps"]:
            assert s["script"] and not s["script"].startswith("/") and "{client}" in s["args"]


def test_drift_is_detected():
    mod = load_script("routines")
    defs = mod.load()
    defs["routines"][0]["cron_utc"] = "0 5 * * *"
    defs["routines"].pop()
    problems = mod.drift(defs)
    assert any("me-morning.cron_utc differs" in p for p in problems) and any("me-monday: in SKILL.md §8 but not in routines.json" in p for p in problems)


def test_check_and_list_cli():
    res = subprocess.run([sys.executable, str(ME_DIR / "scripts" / "routines.py"), "check"], cwd=ME_DIR, capture_output=True, text=True)
    assert res.returncode == 0 and "matches SKILL.md §8 (3 routines)" in res.stdout
    res = subprocess.run([sys.executable, str(ME_DIR / "scripts" / "routines.py"), "list"], cwd=ME_DIR, capture_output=True, text=True)
    assert res.returncode == 0 and "me-morning  0 6 * * *" in res.stdout and "scripts/checkin.py" in res.stdout


def test_morning_routine_dry_run_fires_the_checkin(db_env, dev_root, monkeypatch):
    """The 08:00 prompt executed as its scripts: status, pull insights, apply actions --reconcile, check-in. A check-in
    .eml lands in the outbox and the runs summary lists the rows. A step whose script is not built yet is reported,
    never faked (the assertion below follows the file's existence, so the test held before T10 landed too)."""
    env = {**os.environ, "EMAIL_BACKEND": "file", "META_BACKEND": "fake", "CHECKIN_TO": "sam@example.invalid", "PIPELINE_PAUSED": "false"}
    res = subprocess.run([sys.executable, str(ME_DIR / "scripts" / "routines.py"), "dry-run", "me-morning"], cwd=ME_DIR, env=env,
                         capture_output=True, text=True)
    out = res.stdout + res.stderr
    assert "dry-run me-morning (0 6 * * * UTC) for client upclicklabs" in out
    assert "--- step 1: status" in out and "--- step 4: check-in" in out
    steps = out.split("--- steps", 1)[1].split("--- runs summary", 1)[0]
    outcome = {line.split()[0]: line.split()[-1] for line in steps.strip().splitlines()}
    assert outcome["status"] == "ok" and outcome["check-in"] == "ok" and outcome["apply"] == "ok", out
    built = (ME_DIR / "scripts" / "meta_insights.py").exists()
    assert outcome["pull"] == ("ok" if built else "built") and res.returncode == (0 if built else 1)
    assert "sent <" in out and list((dev_root / "outbox").glob("*.eml"))
    summary = out.split("--- runs summary", 1)[1]
    assert "executor   ok" in summary and "checkin    ok" in summary
    if built:
        assert "loop       ok" in summary


def test_dry_run_unknown_routine():
    res = subprocess.run([sys.executable, str(ME_DIR / "scripts" / "routines.py"), "dry-run", "me-never"], cwd=ME_DIR, capture_output=True, text=True)
    assert res.returncode == 2 and "no routine named 'me-never'" in res.stderr
