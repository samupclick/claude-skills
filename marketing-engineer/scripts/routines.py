#!/usr/bin/env python3
"""Routine definitions for the phase-0 reactor stand-in (T11). SKILL.md §8, PRD FR-48, CRUCIBLE A23.

    scripts/routines.py list                 the three routines: name, cron (UTC), prompt
    scripts/routines.py check                config/routines.json against the SKILL.md §8 table (exit 1 on drift)
    scripts/routines.py dry-run <name>       run the routine's steps locally, in order, against the dev warehouse

`dry-run` is quiz decision 7 (Sam, 2026-09-04): the routine's prompt is executed as its scripts, one subprocess
per step with the environment as it is (dev backends, `.env`), and ends with the runs summary the prompt asks
for (every `runs` row opened since the dry-run began). A step whose script does not exist yet is reported as
"not built" and the dry-run continues, so the steps after it are still exercised; the exit code is 1 when any
step did not run clean. Real registration as Claude Code Routines (`create_trigger`, fresh session per fire,
cron from `cron_utc`) is T13 step 7; nothing here registers anything.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.env import ME_DIR, load_env  # noqa: E402

ROUTINES = ME_DIR / "config" / "routines.json"
SKILL = ME_DIR / "SKILL.md"
ROW = re.compile(r"^\| `([a-z-]+)` \| `([^`]+)` \| `(.+)` \|$")


def load() -> dict[str, Any]:
    return json.loads(ROUTINES.read_text())


def skill_table() -> list[dict[str, str]]:
    """The §8 table rows of SKILL.md as {name, cron_utc, prompt}."""
    rows = []
    section = SKILL.read_text().split("## 8. Routines", 1)[1].split("\n## ", 1)[0]
    for line in section.splitlines():
        m = ROW.match(line.strip())
        if m:
            rows.append({"name": m.group(1), "cron_utc": m.group(2), "prompt": m.group(3)})
    return rows


def drift(defs: dict[str, Any]) -> list[str]:
    """Differences between config/routines.json and SKILL.md §8, as messages (empty when in sync)."""
    a = {r["name"]: r for r in skill_table()}
    b = {r["name"]: r for r in defs["routines"]}
    out = [f"{n}: in SKILL.md §8 but not in routines.json" for n in a if n not in b]
    out += [f"{n}: in routines.json but not in SKILL.md §8" for n in b if n not in a]
    for n in a.keys() & b.keys():
        for k in ("cron_utc", "prompt"):
            if a[n][k] != b[n][k]:
                out.append(f"{n}.{k} differs:\n  SKILL.md:      {a[n][k]}\n  routines.json: {b[n][k]}")
    return out


def format_list(defs: dict[str, Any]) -> str:
    lines = [f"session={defs['session']}  hook={defs['hook']}  client={defs['client']}"]
    for r in defs["routines"]:
        lines.append(f"{r['name']:<11} {r['cron_utc']:<12} {r['prompt']}")
        lines.extend(f"    {i}. {s['say']}  →  {s['script'] or '(no script: say so and stop)'}" for i, s in enumerate(r["steps"], 1))
    return "\n".join(lines)


def dry_run(defs: dict[str, Any], name: str, client: str | None = None) -> int:
    routine = next((r for r in defs["routines"] if r["name"] == name), None)
    if routine is None:
        print(f"routines: no routine named {name!r}; one of {[r['name'] for r in defs['routines']]}", file=sys.stderr)
        return 2
    slug = client or defs["client"]
    started = datetime.now(timezone.utc)
    print(f"dry-run {name} ({routine['cron_utc']} UTC) for client {slug}\nprompt: {routine['prompt']}\n")
    outcomes: list[tuple[str, str]] = []
    for i, step in enumerate(routine["steps"], 1):
        script = ME_DIR / step["script"] if step.get("script") else None
        print(f"--- step {i}: {step['say']}")
        if script is None or not script.exists():
            print(f"    {step.get('script') or '(no script)'}: does not exist yet; the orchestrator says so and stops (SKILL.md §3)")
            outcomes.append((step["say"], "not built"))
            continue
        argv = [sys.executable, str(script), *(a.replace("{client}", slug) for a in step.get("args", []))]
        res = subprocess.run(argv, cwd=ME_DIR, capture_output=True, text=True)
        for line in (res.stdout + res.stderr).rstrip().splitlines():
            print(f"    {line}")
        outcomes.append((step["say"], "ok" if res.returncode == 0 else f"exit {res.returncode}"))
    print("\n--- steps")
    for say, outcome in outcomes:
        print(f"    {say:<28} {outcome}")
    print("\n--- runs summary (rows opened by this dry-run)")
    try:
        from warehouse.client import client_by_slug, connect
        with connect("worker", job="routines") as conn:
            c = client_by_slug(conn, slug)
            rows = conn.execute("select worker, status, started_at, finished_at, counts, error from runs where started_at >= %s"
                                " and (client_id = %s or client_id is null) order by started_at", (started, c["id"] if c else None)).fetchall()
        for r in rows:
            print(f"    {r['worker']:<10} {r['status']:<8} {r['started_at']:%H:%M:%S}  {json.dumps(r['counts'] or {}, sort_keys=True, default=str)[:100]}"
                  + (f"  error={r['error'][:80]}" if r["error"] else ""))
        if not rows:
            print("    none")
    except Exception as exc:  # the summary must never hide the step outcomes
        print(f"    unavailable: {type(exc).__name__}: {exc}")
    return 0 if all(o == "ok" for _, o in outcomes) else 1


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Routine definitions for the phase-0 stand-in. SKILL.md §8.")
    p.add_argument("command", choices=("list", "check", "dry-run"))
    p.add_argument("name", nargs="?")
    p.add_argument("--client")
    args = p.parse_args(argv)
    load_env()
    defs = load()
    if args.command == "list":
        print(format_list(defs))
        return 0
    if args.command == "check":
        problems = drift(defs)
        print("\n".join(problems) if problems else f"routines.json matches SKILL.md §8 ({len(defs['routines'])} routines)")
        return 1 if problems else 0
    if not args.name:
        p.error("dry-run needs a routine name")
    return dry_run(defs, args.name, args.client)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
