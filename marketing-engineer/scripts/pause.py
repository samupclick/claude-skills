#!/usr/bin/env python3
"""`pause the pipeline` / `resume the pipeline` (T11). SKILL.md §3, §4 rule 1, §5.3; PRD FR-44, FR-47.

    scripts/pause.py [--client upclicklabs] pause  [--reason "why"]
    scripts/pause.py [--client upclicklabs] resume [--reason "why"]
    scripts/pause.py [--client upclicklabs] status

`pause` and `resume` write one *proposed* `set_pause_flag` action as `worker_rw` (`proposal = {paused, reason}`,
`rule = 'sam_request'`); nothing here flips `clients.paused`. Sam approves it with
`scripts/decide.py --as sam_admin "approve N"` and applies it with `scripts/apply_actions.py --role sam_admin`
(the 0002 trigger lets only `sam_admin` approve this type; the executor applies it even while paused).
One open proposal per direction at a time: a second `pause` prints the existing row instead of a duplicate.
`status` prints `clients.paused`, `PIPELINE_PAUSED`, and the open pause proposals. Opens and closes a `runs`
row (worker `pause`) for `pause` and `resume`. No side effect anywhere (SKILL.md §4 rule 1).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from warehouse.client import client_by_slug, connect, insert, run  # noqa: E402

WORKER = "pause"
RULE = "sam_request"
TRUTHY = ("1", "true", "yes", "on")
NUMBERED = "select *, row_number() over (order by created_at, id) as n from actions where client_id=%s"


def env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in TRUTHY


def open_proposals(conn, client_id) -> list[dict[str, Any]]:
    return conn.execute(f"select * from ({NUMBERED}) x where action_type='set_pause_flag' and status in ('proposed','approved') order by n",
                        (client_id,)).fetchall()


def propose(conn, client: dict[str, Any], r, paused: bool, reason: str) -> tuple[dict[str, Any], bool]:
    """Insert the proposal unless one for the same direction is already open. Returns (row, created)."""
    for row in open_proposals(conn, client["id"]):
        if (row["proposal"] or {}).get("paused") is paused and row["rule"] == RULE:
            conn.rollback()
            r.count("duplicate")
            return row, False
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    row = insert(conn, "actions", client_id=client["id"], action_type="set_pause_flag", target_type="client",
                 target_id=str(client["id"]), rule=RULE, proposal={"paused": paused, "reason": reason},
                 proposal_key=f"pause:{client['id']}:{'pause' if paused else 'resume'}:{stamp}",
                 evidence={"requested_by": "sam", "channel": "chat", "paused_before": client["paused"],
                           "pipeline_paused_env": env_flag("PIPELINE_PAUSED")})
    conn.commit()
    r.count("proposed")
    return row, True


def number_of(conn, client_id, action_id) -> int:
    return conn.execute(f"select n from ({NUMBERED}) x where id=%s", (client_id, action_id)).fetchone()["n"]


def format_status(client: dict[str, Any], proposals: list[dict[str, Any]]) -> str:
    lines = [f"clients.paused   {'yes' if client['paused'] else 'no'}",
             f"PIPELINE_PAUSED  {'yes' if env_flag('PIPELINE_PAUSED') else 'no'}",
             f"open set_pause_flag proposals  {len(proposals)}"]
    for p in proposals:
        prop = p["proposal"] or {}
        lines.append(f"  #{p['n']} {p['status']} paused→{prop.get('paused')} rule={p['rule']} reason={prop.get('reason') or '-'} [{str(p['id'])[:8]}]")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Propose set_pause_flag for Sam to approve as sam_admin. SKILL.md §3.")
    p.add_argument("--client", default="upclicklabs")
    p.add_argument("--reason", default="")
    p.add_argument("command", choices=("pause", "resume", "status"))
    args = p.parse_args(argv)
    with connect("worker", job="pause") as conn:
        client = client_by_slug(conn, args.client)
        if client is None:
            print(f"pause: no client with slug {args.client!r}", file=sys.stderr)
            return 1
        if args.command == "status":
            print(format_status(client, open_proposals(conn, client["id"])))
            return 0
        paused = args.command == "pause"
        reason = args.reason or f"{args.command} requested by Sam in chat"
        with run(conn, WORKER, client["id"]) as r:
            row, created = propose(conn, client, r, paused, reason)
            n = number_of(conn, client["id"], row["id"])
            conn.rollback()
        verb = "proposed" if created else "already open"
        print(f"set_pause_flag paused→{paused} {verb} as #{n} [{str(row['id'])[:8]}]: {reason}")
        print(f"next: scripts/decide.py --as sam_admin \"approve {n}\"  then  scripts/apply_actions.py --role sam_admin"
              "  (WAREHOUSE_URL_SAM_ADMIN; only sam_admin may approve set_pause_flag)")
        print(f"runs {r.id}: ok {json.dumps(r.counts, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
