#!/usr/bin/env python3
"""Seed the local warehouse from the DRAFT files, as-is. Idempotent: a second run adds zero rows.

Connects as WAREHOUSE_URL_ADMIN (worker_rw has no insert on clients/offers/icps). Opens and closes a
`runs` row (worker 'seed') including on failure. Placeholder values are copied verbatim.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
from psycopg.types.json import Jsonb

from adapters.env import ME_DIR, load_env, require

CONFIG = ME_DIR / "config" / "clients" / "upclicklabs.json"
FAMILIES = ME_DIR / "references" / "families.md"


def parse_families(text: str) -> list[tuple[str, str]]:
    """(name, kind) from families.md: the format table, the hook-type line, the angle line."""
    out: list[tuple[str, str]] = []
    section = None
    for line in text.splitlines():
        if line.startswith("## "):
            head = line.lower()
            section = "format" if "format" in head else "hook_type" if "hook" in head else "angle" if "angle" in head else None
            continue
        if section == "format":
            m = re.match(r"^\|\s*`([a-z_]+)`\s*\|", line)
            if m:
                out.append((m.group(1), "format"))
        elif section in ("hook_type", "angle") and line.startswith("`"):
            out.extend((n, section) for n in re.findall(r"`([a-z_]+)`", line))
    return out


def name_conflicts(families: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Names listed under more than one kind. families.name is the primary key, so only the first kind lands."""
    kinds: dict[str, list[str]] = {}
    for name, kind in families:
        kinds.setdefault(name, []).append(kind)
    return {n: k for n, k in kinds.items() if len(k) > 1}


def seed(conn: psycopg.Connection, config: dict, families: list[tuple[str, str]]) -> dict[str, int]:
    counts = {"families": 0, "clients": 0, "offers": 0, "icps": 0}
    conflicts = name_conflicts(families)
    with conn.cursor() as cur:
        for name, kind in families:
            if name in conflicts:
                continue
            cur.execute("insert into families (name, kind) values (%s, %s) on conflict (name) do nothing", (name, kind))
            counts["families"] += cur.rowcount
        c = config["client"]
        cur.execute(
            """insert into clients (name, slug, site, industry, currency, daily_cap, config)
               values (%s, %s, %s, %s, %s, %s, %s) on conflict (slug) do nothing""",
            (c["name"], c["slug"], c.get("site"), c.get("industry"), config.get("currency", "EUR"),
             config.get("daily_cap"), Jsonb(config)),
        )
        counts["clients"] += cur.rowcount
        cur.execute("select id from clients where slug = %s", (c["slug"],))
        client_id = cur.fetchone()[0]

        o = config["offer"]
        cur.execute("select 1 from offers where client_id = %s and name = %s", (client_id, o["name"]))
        if cur.fetchone() is None:
            cur.execute(
                """insert into offers (client_id, name, promise, price_anchor, proof_points, landing_url, funnel_host,
                                       calendar_url, terminal_metric, quiz_config, offer_layer)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (client_id, o["name"], o.get("promise"), o.get("price_anchor"), o.get("proof_points", []),
                 o.get("landing_url"), o.get("funnel_host"), o.get("calendar_url"),
                 o.get("terminal_metric", "booked_call"), Jsonb(o.get("quiz_config", {})), Jsonb(o.get("offer_layer", {}))),
            )
            counts["offers"] += 1

        i = config["icp"]
        cur.execute("select 1 from icps where client_id = %s and label = %s", (client_id, i["label"]))
        if cur.fetchone() is None:
            cur.execute(
                """insert into icps (client_id, label, role, company_type, industry, geo, size_band, pains, outcomes)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (client_id, i["label"], i.get("role"), i.get("company_type"), i.get("industry"), i.get("geo", []),
                 i.get("size_band"), i.get("pains", []), i.get("outcomes", [])),
            )
            counts["icps"] += 1
    return counts


class FamilyNameConflict(RuntimeError):
    """families.md lists one name under two kinds; families.name is unique, so the seed cannot be complete."""


def main() -> int:
    load_env()
    url = require("seed", "WAREHOUSE_URL_ADMIN")["WAREHOUSE_URL_ADMIN"]
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:  # the runs row opens before anything that can fail, including parsing
            cur.execute("insert into runs (worker) values ('seed') returning id")
            run_id = cur.fetchone()[0]
        conn.commit()
        try:
            config = json.loads(CONFIG.read_text())
            families = parse_families(FAMILIES.read_text())
            counts = seed(conn, config, families)
            conn.commit()  # unambiguous rows stay even when the conflict below fails the run
            conflicts = name_conflicts(families)
            if conflicts:
                raise FamilyNameConflict(
                    "references/families.md reuses a name across kinds and families.name is unique; these were "
                    "NOT inserted, Sam to rename them: " + "; ".join(f"{n} ({', '.join(k)})" for n, k in conflicts.items()))
            with conn.cursor() as cur:
                cur.execute(
                    """update runs set status = 'ok', finished_at = now(), counts = %s,
                              client_id = (select id from clients where slug = %s) where id = %s""",
                    (Jsonb(counts), config["client"]["slug"], run_id),
                )
            conn.commit()
        except Exception as exc:  # noqa: BLE001 — record then re-raise
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute("""update runs set status = 'failed', finished_at = now(), error = %s,
                                  client_id = (select id from clients where slug = 'upclicklabs') where id = %s""",
                            (f"{type(exc).__name__}: {exc}"[:2000], run_id))
            conn.commit()
            if isinstance(exc, FamilyNameConflict):
                print(f"seed: run {run_id} FAILED: {exc}", file=sys.stderr)
                return 1
            raise
    print(f"seed: run {run_id} inserted {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
