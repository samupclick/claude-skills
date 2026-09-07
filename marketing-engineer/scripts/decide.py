#!/usr/bin/env python3
"""Record Sam's chat decisions on proposed actions (SKILL.md §5.3). T8.

    scripts/decide.py list                                   numbered table of proposed actions
    scripts/decide.py "approve 1,2; reject 3: reason"        Sam's reply, verbatim
    scripts/decide.py --as sam_admin "approve 4"             set_pause_flag / promote_trust / quote_release

Writes `status='approved'` with `decided_by='sam'`, `decided_at=now()`, `decision_channel='chat'` and
`approved_payload = proposal` (so the row counts toward `trust_streaks`), or `status='rejected'` with
`reject_reason`. Numbers are stable: an action's number is its rank by creation among all of the client's
actions, so `list` may show `#7, #9` and a reply sent after `#8` was decided still means the same rows. A
uuid (or its first 8 characters) also works. A `failed` row can be re-approved by number or id for a retry. Nothing is written unless every
reference in the reply resolves and the role may decide every type named: the 0002 trigger lets only
`sam_admin` approve the three Sam-only types, so this script refuses them under the executor role before
touching the database. Never calls Meta. Opens and closes a `runs` row (worker `decide`).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from psycopg.types.json import Jsonb  # noqa: E402

from warehouse.client import client_by_slug, connect, run  # noqa: E402

WORKER = "decide"
ADMIN_TYPES = ("set_pause_flag", "promote_trust", "quote_release")
CLAUSE = re.compile(r"^\s*(approve|reject)\s+([^:]+?)\s*(?::\s*(.*?))?\s*$", re.IGNORECASE | re.DOTALL)


class ReplyError(ValueError):
    """The reply does not parse or names something that does not exist; nothing was written."""


def parse_reply(text: str) -> list[tuple[str, list[str], str | None]]:
    """`approve 1,2; reject 3: reason` → [("approve", ["1","2"], None), ("reject", ["3"], "reason")]."""
    out: list[tuple[str, list[str], str | None]] = []
    for clause in filter(None, (c.strip() for c in text.split(";"))):
        m = CLAUSE.match(clause)
        if not m:
            raise ReplyError(f"cannot parse {clause!r}; expected `approve 1,2` or `reject 3: reason`")
        refs = [r.strip() for r in re.split(r"[,\s]+", m.group(2)) if r.strip()]
        if not refs:
            raise ReplyError(f"no action named in {clause!r}")
        out.append((m.group(1).lower(), refs, m.group(3) or None))
    return out


# Numbers are the action's rank by creation among every action of the client, so the number Sam saw in
# `list` still names the same row after other rows were decided, auto-applied, or proposed in between.
NUMBERED = "select *, row_number() over (order by created_at, id) as n from actions where client_id=%s"


def proposed(conn, client_id) -> list[dict[str, Any]]:
    return conn.execute(f"select * from ({NUMBERED}) x where status='proposed' order by n", (client_id,)).fetchall()


def resolve(conn, client_id, ref: str) -> dict[str, Any]:
    if ref.isdigit() and len(ref) <= 6:
        row = conn.execute(f"select * from ({NUMBERED}) x where n=%s", (client_id, int(ref))).fetchone()
        if row is None:
            raise ReplyError(f"there is no action #{ref}")
        if row["status"] not in ("proposed", "failed"):
            raise ReplyError(f"action #{ref} is {row['status']}, not proposed; nothing written")
        return row
    rows = conn.execute("select * from actions where client_id=%s and status in ('proposed','failed') and id::text like %s",
                        (client_id, ref.lower() + "%")).fetchall()
    if len(rows) != 1:
        raise ReplyError(f"{ref!r} matches {len(rows)} proposed/failed actions; give a number from `list` or a longer id")
    return rows[0]


def what_changes(a: dict[str, Any]) -> str:
    t, p = a["action_type"], a["proposal"] or {}
    return {
        "pause": "ad → PAUSED in Meta", "kill": "ad → ARCHIVED in Meta (final)", "activate": "ad/campaign → ACTIVE in Meta (spends)",
        "scale": f"ad set budget → {p.get('adset_daily_budget')}", "set_pause_flag": f"clients.paused → {p.get('paused')}",
        "promote_trust": f"trust.{a['target_id']}.level → {p.get('level')}", "quote_release": "release recorded; gate may use the quote",
        "build_campaign": f"campaign + {len(p.get('ad_sets', []) or [])} ad set(s) created paused in Meta",
    }.get(t, "no executor path in phase 0")


def format_listing(listing: list[dict[str, Any]]) -> str:
    if not listing:
        return "no proposed actions"
    lines = []
    for a in listing:
        ev = json.dumps(a["evidence"] or {}, sort_keys=True, default=str)
        lines.append(f"{a['n']:>3}  {a['action_type']:<15} {a['target_type']}/{str(a['target_id'])[:8]}  rule={a['rule'] or '-'}"
                     f"  evidence={ev[:120]}  → {what_changes(a)}  [{str(a['id'])[:8]}]")
    lines.append("reply: `approve 1,2; reject 3: reason` then `apply actions`")
    return "\n".join(lines)


def decide(conn, client_id, role: str, decided_by: str, text: str) -> dict[str, int]:
    plan: list[tuple[str, dict[str, Any], str | None]] = []
    for verb, refs, reason in parse_reply(text):
        if verb == "reject" and not reason:
            raise ReplyError(f"a rejection needs a reason: `reject {','.join(refs)}: why`")
        for ref in refs:
            plan.append((verb, resolve(conn, client_id, ref), reason))
    admin_only = sorted({a["action_type"] for verb, a, _ in plan if verb == "approve" and a["action_type"] in ADMIN_TYPES})
    if admin_only and role != "sam_admin":
        raise ReplyError(f"only sam_admin may approve {', '.join(admin_only)}; run with --as sam_admin (WAREHOUSE_URL_SAM_ADMIN)")
    counts = {"approved": 0, "rejected": 0}
    for verb, a, reason in plan:
        if verb == "approve":
            cur = conn.execute(
                "update actions set status='approved', decided_by=%s, decided_at=now(), decision_channel='chat',"
                " approved_payload=%s, reject_reason=null where id=%s and status in ('proposed','failed')",
                (decided_by, Jsonb(a["proposal"]), a["id"]))
        else:
            cur = conn.execute(
                "update actions set status='rejected', decided_by=%s, decided_at=now(), decision_channel='chat', reject_reason=%s"
                " where id=%s and status in ('proposed','failed')", (decided_by, reason, a["id"]))
        if cur.rowcount != 1:
            raise ReplyError(f"action {str(a['id'])[:8]} changed state while deciding; nothing written")
        counts["approved" if verb == "approve" else "rejected"] += 1
        print(f"{verb}d {a['action_type']} {a['target_type']}/{str(a['target_id'])[:8]} [{str(a['id'])[:8]}]" + (f": {reason}" if reason else ""))
    return counts


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Record Sam's chat approvals and rejections. SKILL.md §5.3.")
    p.add_argument("--client", default="upclicklabs")
    p.add_argument("--as", dest="role", choices=("executor", "sam_admin"), default="executor")
    p.add_argument("--decided-by", default="sam")
    p.add_argument("reply", nargs="*", help="`list`, or Sam's reply such as `approve 1,2; reject 3: reason`")
    args = p.parse_args(argv)
    text = " ".join(args.reply).strip()
    with connect(args.role, job="decide") as conn:
        client = client_by_slug(conn, args.client)
        if client is None:
            print(f"decide: no client with slug {args.client!r}", file=sys.stderr)
            return 1
        if not text or text.lower() == "list":
            print(format_listing(proposed(conn, client["id"])))
            return 0
        try:
            with run(conn, WORKER, client["id"]) as r:
                counts = decide(conn, client["id"], args.role, args.decided_by, text)
                for k, v in counts.items():
                    r.count(k, v)
        except ReplyError as exc:
            print(f"decide: {exc}", file=sys.stderr)
            return 2
        print(f"runs {r.id}: ok {json.dumps(r.counts, sort_keys=True)}; now run `apply actions`")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
