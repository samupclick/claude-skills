#!/usr/bin/env python3
"""Routine definitions for the phase-0 reactor stand-in (T11). SKILL.md §8, PRD FR-48, CRUCIBLE A23.

    scripts/routines.py list                 the four routines: name, cron (UTC), environment, prompt
    scripts/routines.py check                config/routines.json against the SKILL.md §8 table, the connectors and the
                                             executor's isolation (exit 1 on any problem)
    scripts/routines.py dry-run <name>       run the routine's steps locally, in order, against the dev warehouse
    scripts/routines.py register --print     the exact create_trigger arguments per routine; registers nothing

`dry-run` is quiz decision 7 (Sam, 2026-09-04): the routine's prompt is executed as its scripts, one subprocess
per step with the environment as it is (dev backends, `.env`), and ends with the runs summary the prompt asks
for (every `runs` row opened since the dry-run began). A step whose script does not exist yet is reported as
"not built" and the dry-run continues, so the steps after it are still exercised; the exit code is 1 when any
step did not run clean. A step with `connector` is finished by the session through that claude.ai connector
(the check-in's `--send-pending` prints the Gmail connector call); the dry-run runs the script part only.

Isolation (SKILL.md §1): a routine's session gives every step, and the agent itself, one environment. The agent reads
the check-in's untrusted text, runs Bash and holds the Gmail connector, so the Meta write token cannot sit beside it:
`scripts/apply_actions.py` runs only in `me-executor`, alone, with no connector, in the `marketing-engineer-executor`
environment, and nothing else runs there (`isolation_problems`, part of `check`). The dry-run of any other routine
blanks the executor-only variables, so a worker step that needed them fails here first.

Registration as Claude Code Routines is T13 step 7 and Sam approves it; nothing here registers anything.
`register --print` gives one `create_trigger` argument set per routine: the routine's name and prompt, the cron in
CRON_TZ form kept in UTC as the §8 table states it, a fresh session per fire, `connectors` = the union of the
routine's step connectors (`[]` stores none, so a routine that sends no email gets no connector), the
`environment_id` of its environment (a placeholder naming it: Sam fills in the id `list_environments` gives; without
it the trigger would inherit the registering session's environment), and `initiation: human_request` (Sam asks for it
at go-live).
"""
from __future__ import annotations

import argparse
import json
import os
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
KNOWN_CONNECTORS = ("Gmail",)
EXECUTOR_SCRIPT = "scripts/apply_actions.py"
EXECUTOR_ENVIRONMENT = "marketing-engineer-executor"
EXECUTOR_ONLY = ("META_ACCESS_TOKEN", "META_PAGE_ID", "WAREHOUSE_URL_EXECUTOR")   # SKILL.md §1: the executor's alone


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


def connectors(routine: dict[str, Any]) -> list[str]:
    """The claude.ai connectors the routine's session needs: the union of its steps' `connector`."""
    return sorted({s["connector"] for s in routine["steps"] if s.get("connector")})


def connector_drift(defs: dict[str, Any]) -> list[str]:
    """A prompt that tells the session to use a connector must have a step naming it, and the other way round."""
    out = []
    for r in defs["routines"]:
        named = set(connectors(r))
        said = {c for c in set(KNOWN_CONNECTORS) | named if f"{c} connector" in r["prompt"]}
        out += [f"{r['name']}: the prompt uses the {c} connector but no step names connector {c!r}, so its trigger would lack it"
                for c in sorted(said - named)]
        out += [f"{r['name']}: a step names connector {c!r} but the prompt never says to use the {c} connector" for c in sorted(named - said)]
    return out


def isolation_problems(defs: dict[str, Any]) -> list[str]:
    """The executor's write token never shares a session with anything else (SKILL.md §1): every routine names a known
    environment; a routine that runs scripts/apply_actions.py runs it alone, with no connector, in EXECUTOR_ENVIRONMENT;
    and no other step runs in that environment."""
    envs = defs.get("environments") or {}
    out = []
    for r in defs["routines"]:
        env = r.get("environment")
        others = [s["say"] for s in r["steps"] if s.get("script") != EXECUTOR_SCRIPT]
        if env not in envs:
            out.append(f"{r['name']}: environment {env!r} is not one of {sorted(envs)}")
        if len(others) < len(r["steps"]) and (others or connectors(r) or env != EXECUTOR_ENVIRONMENT):
            out.append(f"{r['name']}: runs {EXECUTOR_SCRIPT} beside other steps, a connector or outside {EXECUTOR_ENVIRONMENT}; "
                       f"its session would hand {', '.join(EXECUTOR_ONLY)} to all of them (SKILL.md §1)")
        if env == EXECUTOR_ENVIRONMENT and (others or connectors(r)):
            out.append(f"{r['name']}: {EXECUTOR_ENVIRONMENT} runs {EXECUTOR_SCRIPT} alone, with no connector; "
                       f"move {', '.join(others) or 'the connector'} to another environment")
    return out


def trigger_arguments(defs: dict[str, Any]) -> list[dict[str, Any]]:
    """One `create_trigger` argument set per routine (SKILL.md §8; registration is T13 step 7, Sam approves)."""
    return [{"name": r["name"], "cron_expression": f"CRON_TZ=UTC {r['cron_utc']}", "prompt": r["prompt"],
             "create_new_session_on_fire": True, "connectors": connectors(r),
             "environment_id": f"<environment_id of {r['environment']}>", "initiation": "human_request"}
            for r in defs["routines"]]


def format_register(defs: dict[str, Any]) -> str:
    lines = [f"# create_trigger arguments, one call per routine ({len(defs['routines'])}). Nothing was registered: registration is",
             "# the go-live swap (T13 step 7) and Sam approves it. `connectors: []` stores no connector. Replace each",
             "# environment_id placeholder with the id list_environments gives that environment; the executor's holds the",
             "# Meta write token and nothing else (SKILL.md §1, §8)."]
    for args in trigger_arguments(defs):
        lines += [f"--- {args['name']}", json.dumps(args, indent=2, ensure_ascii=False)]
    return "\n".join(lines)


def format_list(defs: dict[str, Any]) -> str:
    lines = [f"session={defs['session']}  hook={defs['hook']}  client={defs['client']}"]
    for r in defs["routines"]:
        lines.append(f"{r['name']:<11} {r['cron_utc']:<12} [{r['environment']}] {r['prompt']}")
        lines.extend(f"    {i}. {s['say']}  →  {s['script'] or '(no script: say so and stop)'}"
                     + (f"  →  {s['connector']} connector (session)" if s.get("connector") else "") for i, s in enumerate(r["steps"], 1))
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
    env = dict(os.environ)
    if routine.get("environment") != EXECUTOR_ENVIRONMENT:      # as at go-live: blank beats .env (load_env never overrides)
        env.update({var: "" for var in EXECUTOR_ONLY})
    for i, step in enumerate(routine["steps"], 1):
        script = ME_DIR / step["script"] if step.get("script") else None
        print(f"--- step {i}: {step['say']}")
        if script is None or not script.exists():
            print(f"    {step.get('script') or '(no script)'}: does not exist yet; the orchestrator says so and stops (SKILL.md §3)")
            outcomes.append((step["say"], "not built"))
            continue
        argv = [sys.executable, str(script), *(a.replace("{client}", slug) for a in step.get("args", []))]
        res = subprocess.run(argv, cwd=ME_DIR, env=env, capture_output=True, text=True)
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
    p.add_argument("command", choices=("list", "check", "dry-run", "register"))
    p.add_argument("name", nargs="?")
    p.add_argument("--client")
    p.add_argument("--print", dest="print_only", action="store_true", help="register: print the create_trigger arguments")
    args = p.parse_args(argv)
    load_env()
    defs = load()
    if args.command == "list":
        print(format_list(defs))
        return 0
    if args.command == "register":
        if not args.print_only:
            p.error("register only prints the create_trigger arguments (register --print); registering the routines is a"
                    " go-live step Sam approves (T13 step 7)")
        print(format_register(defs))
        return 0
    if args.command == "check":
        problems = drift(defs) + connector_drift(defs) + isolation_problems(defs)
        print("\n".join(problems) if problems else f"routines.json matches SKILL.md §8 ({len(defs['routines'])} routines)")
        return 1 if problems else 0
    if not args.name:
        p.error("dry-run needs a routine name")
    return dry_run(defs, args.name, args.client)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
