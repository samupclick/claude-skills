"""Skill finish (T12, FR-48 / DR-3 / NFR-6): SKILL.md describes what exists, every worker's fixed prompts live in
references/prompts/<worker>.md and are loaded from there, warehouse/schema-notes.md covers every JSONB column and
every runs.counts key the scripts write, and a fresh session's "where are we" runs end to end as worker_rw."""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ME_DIR = Path(__file__).resolve().parent.parent
SKILL = (ME_DIR / "SKILL.md").read_text()
NOTES = (ME_DIR / "warehouse" / "schema-notes.md").read_text()


def section(number: int) -> str:
    m = re.search(rf"^## {number}\. .*?$(.*?)(?=^## \d+\. |\Z)", SKILL, flags=re.M | re.S)
    assert m, f"SKILL.md has no section {number}"
    return m.group(1)


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"skill_test_{name}", ME_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod   # dataclasses resolve `from __future__ import annotations` through sys.modules
    spec.loader.exec_module(mod)
    return mod


def test_run_mode_table_names_scripts_that_exist_or_says_not_built():
    rows = [line for line in section(3).splitlines() if line.startswith("| `")]
    assert len(rows) >= 15
    seen_not_built = []
    for row in rows:
        paths = re.findall(r"`((?:scripts|warehouse)/[\w.]+\.py)", row)
        if "not built in phase 0" in row:
            absent = re.findall(r"`((?:scripts|warehouse)/[\w.]+\.py)` does not exist", row)
            assert absent, f"a not-built row must name the missing script: {row}"
            for p in absent:
                assert not (ME_DIR / p).exists(), f"{p} exists but SKILL.md §3 says it does not"
            for p in set(paths) - set(absent):
                assert (ME_DIR / p).exists(), f"SKILL.md §3 points at missing {p}: {row}"
            seen_not_built.append(row)
        else:
            for p in paths:
                assert (ME_DIR / p).exists(), f"SKILL.md §3 points at missing {p}: {row}"
    assert len(seen_not_built) == 2 and any("monday_memo.py" in r for r in seen_not_built) and any("onboard.py" in r for r in seen_not_built)


def test_repo_layout_lists_only_files_that_exist():
    block = re.search(r"```\n(.*?)```", section(9), flags=re.S).group(1)
    names = set(re.findall(r"[\w.-]+\.(?:py|sql|md|html|json|sh|example|toml|txt)\b", block))
    assert {"SKILL.md", "schema.sql", "0007_launch.sql", "intel.md", "client.py", "routines.py", "CHANGELOG.md"} <= names
    for name in names:
        assert list(ME_DIR.rglob(name)), f"SKILL.md §9 lists {name}, which does not exist under marketing-engineer/"
    assert (ME_DIR.parent / ".claude" / "hooks" / "session-start.sh").exists()
    for absent in ("monday_memo.py", "onboard.py", "meta-launch-playbook.md"):
        assert absent not in names


WORKER_PROMPTS = {
    "pull_inspo": ("intel.md", ("system", "instructions")),
    "pull_voc": ("language.md", ("system", "instructions")),
    "plan_batch": ("planner.md", ("system", "instructions")),
    "render_creatives": ("producer.md", ("system", "instructions", "vision system", "vision instructions")),
    "gate": ("gate.md", ("checks system", "checks instructions", "vision system", "vision instructions", "rubric system", "rubric instructions")),
}


def test_every_worker_prompt_loads_from_references_prompts():
    for script, (filename, keys) in WORKER_PROMPTS.items():
        path = ME_DIR / "references" / "prompts" / filename
        assert path.exists(), f"{script} has no references/prompts/{filename}"
        mod = load_script(script)
        assert mod.PROMPTS == path
        loaded = mod.load_prompts()
        loaded = dict(zip(("system", "instructions"), loaded)) if isinstance(loaded, tuple) else loaded
        for key in keys:
            assert loaded[key].strip(), f"{filename} has an empty '{key}' section"
        text = path.read_text()
        for key in keys:
            assert re.search(rf"^## {re.escape(key)}\s*$", text, flags=re.M | re.I), f"{filename} lacks a '## {key.capitalize()}' heading"
    inspo = load_script("pull_inspo")
    system, instructions = inspo.load_prompts()
    assert inspo.DECOMPOSE_SYSTEM == system and inspo.DECOMPOSE_INSTRUCTIONS == instructions
    # no worker builds a system prompt from a literal: the file is the only source
    for py in (ME_DIR / "scripts").glob("*.py"):
        src = py.read_text()
        assert not re.search(r"system\s*=\s*[\"'(]", src), f"{py.name} carries a literal system prompt"
    m = re.search(r"references/prompts/<worker>\.md` \(([^)]*)\)", section(3))
    assert m, "SKILL.md §3 must name the worker prompt files"
    assert set(re.findall(r"`(\w+)`", m.group(1))) == {"intel", "language", "planner", "producer", "gate"}


def test_schema_notes_cover_every_jsonb_column_and_counter_key():
    schema = (ME_DIR / "warehouse" / "schema.sql").read_text()
    columns = []
    table = None
    for line in schema.splitlines():
        m = re.match(r"create table (?:if not exists )?(\w+)", line)
        if m:
            table = m.group(1)
        else:
            col = re.match(r"\s+(\w+)\s+jsonb\b", line)
            if table and col:
                columns.append(f"{table}.{col.group(1)}")
    assert len(columns) >= 20
    for col in columns:
        assert f"`{col}`" in NOTES, f"schema-notes.md does not mention JSONB column {col}"
    for py in list((ME_DIR / "scripts").glob("*.py")) + [ME_DIR / "warehouse" / "client.py"]:
        for key in set(re.findall(r'\.count\("([a-z_]+)"', py.read_text())):
            assert f"`{key}`" in NOTES, f"runs.counts key {key!r} written by {py.name} is not in schema-notes.md"


def test_where_are_we_runs_end_to_end_as_a_fresh_session(db_env):
    """SKILL.md §0 step 3 / §3 first row: the status command a fresh session runs before anything else, as worker_rw,
    against a warehouse with every migration and the DRAFT seed applied. Reads only; exit 0; the §2 columns printed."""
    res = subprocess.run([sys.executable, str(ME_DIR / "warehouse" / "client.py"), "status", "upclicklabs"],
                         cwd=ME_DIR, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    for col in ("slug", "paused", "daily_cap", "currency", "proven_patterns", "voc_phrases", "latest_batch", "capacity",
                "creatives_by_status", "actions_waiting", "actions_stuck", "ads_active", "kill_scale_candidates",
                "learnings_proposed", "last_failure"):
        assert re.search(rf"^{col}\s", res.stdout, flags=re.M), f"{col} missing from the status table:\n{res.stdout}"
    assert "upclicklabs" in res.stdout
    missing = subprocess.run([sys.executable, str(ME_DIR / "warehouse" / "client.py"), "status", "nobody"],
                             cwd=ME_DIR, capture_output=True, text=True)
    assert missing.returncode == 1 and "no client with slug" in missing.stderr
