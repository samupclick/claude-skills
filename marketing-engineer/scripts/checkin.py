#!/usr/bin/env python3
"""The daily check-in (T11): one email, exactly five parts in order. SKILL.md §3, §4 rule 2, §7, §8;
PRD FR-42, FR-47 (the two brakes the executor does not own), NFR-2, NFR-6.

    scripts/checkin.py [--client upclicklabs] [--to sam@…] [--since 24h|ISO] [--now ISO]
                       [--stale-minutes 15] [--dry-run]

Parts, in this order and no others (FR-42, DECISIONS.md component 9):
  1. actions waiting for Sam, numbered as `scripts/decide.py list` numbers them, one-line reason each;
  2. actions the executor applied since the window opened (auto or approved in chat);
  3. active lever per campaign, with its reason and whether it moved inside the window;
  4. learnings written since the window opened, one line each;
  5. warnings: pause flags, `runs` rows left `running` by a crashed script, failed runs, `applying` rows,
     failed actions, sources blocked by two failures (FR-8), spend against `daily_cap`, the latest loop run's
     warnings and refused learnings (FR-41, `runs.counts` of `scripts/meta_insights.py`) or the "zero learnings"
     case judged from state when no loop ran, brake proposals made by this run, brake config that is missing.

The window opens at the previous successful check-in (`runs.worker='checkin'`), else 24 hours ago; `--since`
overrides it and `--now` fixes the reference time so the golden-file test is reproducible.

Brakes (FR-47) evaluated here, as proposed `set_pause_flag` rows that then show in part 1: a worker whose
runs failed above `config.brakes.error_rate_threshold` over `error_rate_window_hours` (at least
`error_rate_min_runs` runs), and lead velocity above `lead_velocity_multiplier` × the median daily lead
count of the previous `lead_velocity_window_days` days (baseline floored at `lead_velocity_min_baseline`).
Missing brake config is a warning, never a default (CRUCIBLE A11 spirit: `config_missing`, not a guess).
An `applying` row (SKILL.md §7) suspends the brake proposals; the email still goes out and says so.

Content rules (NFR-2, SKILL.md §4 rule 7): every string that comes out of a row passes `clean()`, which
removes every URL, strips control characters, and truncates; the HTML alternative is the escaped text. No
URL of ours exists in phase 0 either (approvals are chat replies), so the body carries no URL at all.
Delivery is the email adapter (`EMAIL_BACKEND=file` in dev mode, `gmail` at go-live); the count that Slack
would carry is printed to stdout. Worker role only; the only warehouse writes are `runs` and proposals.
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.email import get_email  # noqa: E402
from adapters.env import require  # noqa: E402
from warehouse.client import blocked_sources, client_by_slug, connect, format_where_are_we, insert, run, where_are_we  # noqa: E402

WORKER = "checkin"
STALE_MINUTES = 15                        # same threshold as the executor's reconcile (SKILL.md §6 step 8)
PARTS = ("Actions waiting", "Actions taken", "Active lever per campaign", "New learnings", "Warnings")
BRAKE_KEYS = ("error_rate_threshold", "error_rate_window_hours", "error_rate_min_runs",
              "lead_velocity_multiplier", "lead_velocity_window_days", "lead_velocity_min_baseline")
ADMIN_TYPES = ("set_pause_flag", "promote_trust", "quote_release")
TRUTHY = ("1", "true", "yes", "on")
URL = re.compile(r"\b(?:[a-z][a-z0-9+.-]*://|www\.)\S+", re.IGNORECASE)
NUMBERED = "select *, row_number() over (order by created_at, id) as n from actions where client_id=%s"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"me_script_{name}", Path(__file__).with_name(f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ConfigError(RuntimeError):
    """clients.config lacks a key the check-in refuses to run without (SKILL.md §0 step 1)."""


def env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in TRUTHY


def check_config(client: dict[str, Any]) -> None:
    cfg = client.get("config") or {}
    targets = cfg.get("targets") or {}
    missing = [k for k, v in (("targets.ctr_floor", targets.get("ctr_floor")),
                              ("targets.kill_impressions", targets.get("kill_impressions")),
                              ("daily_cap", client.get("daily_cap")), ("currency", client.get("currency"))) if v is None]
    if missing:
        raise ConfigError(f"clients.config for {client['slug']!r} is missing {', '.join(missing)}; refusing to run")


# ---------- content hygiene (NFR-2) ----------

def clean(value: Any, limit: int = 200) -> str:
    """Row text as one printable line with every URL removed. Dicts and lists are compact sorted JSON."""
    if value is None:
        return "-"
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return str(value)
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    text = URL.sub("[url removed]", text)
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    text = re.sub(r"\s+", " ", text).strip() or "-"
    return text if len(text) <= limit else text[: limit - 1] + "…"


def ts(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def parse_when(text: str | None, now: datetime) -> datetime | None:
    """`24h`, `90m`, `3d`, or an ISO timestamp (naive means UTC)."""
    if not text:
        return None
    m = re.fullmatch(r"(\d+)([hmd])", text.strip())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return now - timedelta(**{{"h": "hours", "m": "minutes", "d": "days"}[unit]: n})
    dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------- the composer ----------

class Checkin:
    def __init__(self, conn, client: dict[str, Any], r, *, now: datetime, since: datetime, stale_minutes: int):
        self.conn, self.client, self.run = conn, client, r
        self.client_id, self.slug = client["id"], client["slug"]
        self.cfg = client.get("config") or {}
        self.now, self.since, self.stale = now, since, timedelta(minutes=stale_minutes)
        self.decide = _load_script("decide")
        self.brake_notes: list[str] = []      # what the brakes did this run, for part 5
        self.stuck = self.q1("select count(*) as n from actions where client_id=%s and status='applying'", self.client_id)["n"]

    # ---- reads
    def q(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        return self.conn.execute(sql, params).fetchall()

    def q1(self, sql: str, *params: Any) -> dict[str, Any]:
        return self.conn.execute(sql, params).fetchone()

    def paused(self) -> tuple[bool, bool]:
        row = self.q1("select paused from clients where id=%s", self.client_id)
        return bool(row and row["paused"]), env_flag("PIPELINE_PAUSED")

    # ---- FR-47 brakes owned by the check-in
    def brake_config(self) -> tuple[dict[str, Any], list[str]]:
        brakes = self.cfg.get("brakes") or {}
        return brakes, [k for k in BRAKE_KEYS if brakes.get(k) is None]

    def brakes(self) -> None:
        brakes, missing = self.brake_config()
        if self.stuck:
            self.brake_notes.append(f"brakes not evaluated: {self.stuck} action(s) in `applying` (only the executor's reconcile mode may run)")
            return
        if any(k.startswith("error_rate") for k in missing):
            self.brake_notes.append("error-rate brake not evaluated: clients.config.brakes lacks "
                                    + ", ".join(k for k in missing if k.startswith("error_rate")))
        else:
            self.error_rate_brake(brakes)
        if any(k.startswith("lead_velocity") for k in missing):
            self.brake_notes.append("lead-velocity brake not evaluated: clients.config.brakes lacks "
                                    + ", ".join(k for k in missing if k.startswith("lead_velocity")))
        else:
            self.lead_velocity_brake(brakes)

    def error_rate_brake(self, brakes: dict[str, Any]) -> None:
        """A worker whose finished runs in the window failed above the threshold proposes set_pause_flag."""
        window = timedelta(hours=float(brakes["error_rate_window_hours"]))
        rows = self.q(
            "select worker, count(*) as total, count(*) filter (where status='failed') as failed"
            " from runs where client_id=%s and status in ('ok','failed') and started_at >= %s and started_at < %s and id <> %s"
            " group by worker order by worker", self.client_id, self.now - window, self.now, self.run.id)
        for row in rows:
            rate = row["failed"] / row["total"]
            if row["total"] < int(brakes["error_rate_min_runs"]) or rate <= float(brakes["error_rate_threshold"]):
                continue
            self.propose_pause(
                key=f"brake:error_rate:{row['worker']}:{self.now.astimezone(timezone.utc).strftime('%Y-%m-%dT%H')}",
                rule="worker_error_rate", dedup_field="worker",
                reason=f"worker {row['worker']} failed {row['failed']} of {row['total']} runs in the last {brakes['error_rate_window_hours']}h",
                evidence={"worker": row["worker"], "failed": row["failed"], "total": row["total"], "rate": round(rate, 3),
                          "threshold": brakes["error_rate_threshold"], "window_hours": brakes["error_rate_window_hours"],
                          "observed_at": self.now.isoformat()})

    def lead_velocity_brake(self, brakes: dict[str, Any]) -> None:
        """Leads in the last 24h above multiplier × the median daily count of the previous N days propose set_pause_flag."""
        days = int(brakes["lead_velocity_window_days"])
        day = timedelta(days=1)
        last24 = self.q1("select count(*) as n from leads where client_id=%s and created_at >= %s and created_at < %s",
                         self.client_id, self.now - day, self.now)["n"]
        daily = [self.q1("select count(*) as n from leads where client_id=%s and created_at >= %s and created_at < %s",
                         self.client_id, self.now - day * (i + 2), self.now - day * (i + 1))["n"] for i in range(days)]
        median = statistics.median(daily) if daily else 0
        baseline = max(float(median), float(brakes["lead_velocity_min_baseline"]))
        limit = float(brakes["lead_velocity_multiplier"]) * baseline
        if last24 <= limit:
            return
        self.propose_pause(
            key=f"brake:lead_velocity:{self.client_id}:{self.now.astimezone(timezone.utc).date().isoformat()}",
            rule="lead_velocity", dedup_field=None,
            reason=f"{last24} leads in 24h against a {days}-day median of {median:g} (limit {limit:g})",
            evidence={"leads_24h": last24, "daily_counts": daily, "median": float(median), "baseline": baseline,
                      "multiplier": brakes["lead_velocity_multiplier"], "window_days": days, "observed_at": self.now.isoformat()})

    def propose_pause(self, *, key: str, rule: str, dedup_field: str | None, reason: str, evidence: dict[str, Any]) -> None:
        """One open (proposed/approved) set_pause_flag per rule (and per `dedup_field` value) at a time; keys make re-runs idempotent."""
        dedup_value = evidence.get(dedup_field, "") if dedup_field else ""
        exists = self.q1(
            "select 1 from actions where proposal_key=%s or (client_id=%s and action_type='set_pause_flag' and rule=%s"
            " and status in ('proposed','approved') and coalesce(evidence->>%s, '') = %s)",
            key, self.client_id, rule, dedup_field or "", dedup_value)
        if exists:
            self.conn.rollback()
            return
        insert(self.conn, "actions", client_id=self.client_id, action_type="set_pause_flag", target_type="client",
               target_id=str(self.client_id), rule=rule, proposal={"paused": True, "reason": reason},
               proposal_key=key, evidence=evidence)
        self.conn.commit()
        self.run.count("brake_proposed")
        self.brake_notes.append(f"brake tripped ({rule}): {reason}; set_pause_flag proposed, approve it as sam_admin")
        print(f"brake: proposed set_pause_flag ({rule}: {reason})")

    # ---- the five parts
    def part_waiting(self) -> list[str]:
        rows = self.q(f"select * from ({NUMBERED}) x where status='proposed' order by n", self.client_id)
        lines = []
        for a in rows:
            p, ev = a["proposal"] or {}, a["evidence"] or {}
            reason = p.get("reason") if isinstance(p, dict) and p.get("reason") else ev
            admin = " (approve as sam_admin)" if a["action_type"] in ADMIN_TYPES else ""
            lines.append(f"#{a['n']} {a['action_type']} {a['target_type']}/{str(a['target_id'])[:8]} — rule: {clean(a['rule'])}"
                         f" — reason: {clean(reason, 160)} — if applied: {clean(self.decide.what_changes(a), 80)}{admin}")
        approved = self.q1("select count(*) as n from actions where client_id=%s and status='approved'", self.client_id)["n"]
        last = self.q1("select counts from runs where client_id=%s and worker='executor' and status='ok' order by started_at desc limit 1",
                       self.client_id)
        held = {k: v for k, v in ((last or {}).get("counts") or {}).items() if k.startswith("skipped_") and v}
        if approved:
            lines.append(f"approved and waiting for `apply actions`: {approved}")
        if held:
            lines.append("held by the executor on its last run: " + ", ".join(f"{k[8:]} {v}" for k, v in sorted(held.items())))
        if rows:
            lines.append("reply in chat: `approve 1,2; reject 3: reason`, then `apply actions`")
        self.run.count("waiting", len(rows))
        return lines

    def part_taken(self) -> list[str]:
        rows = self.q("select * from actions where client_id=%s and status='applied' and applied_at >= %s and applied_at < %s"
                      " order by applied_at, id", self.client_id, self.since, self.now)
        lines = []
        for a in rows:
            how = "autonomous" if a["decision_channel"] == "auto" else f"approved by {clean(a['decided_by'], 40)} ({clean(a['decision_channel'], 20)})"
            lines.append(f"{a['action_type']} {a['target_type']}/{str(a['target_id'])[:8]} — {how} — rule: {clean(a['rule'])} — applied {ts(a['applied_at'])}")
        self.run.count("taken", len(rows))
        return lines

    def part_levers(self) -> list[str]:
        rows = self.q("select * from campaigns where client_id=%s and status <> 'ARCHIVED' order by created_at, id", self.client_id)
        lines = []
        for c in rows:
            label = f"{c['kind']} [{c['status']}] {clean(c['external_id'], 40) if c['external_id'] else 'not built'}"
            if c["active_lever"] is None:
                lines.append(f"{label} — lever not set (no `pull insights` yet)")
                continue
            moved = c["active_lever_since"] is not None and self.since <= c["active_lever_since"] < self.now
            lines.append(f"{label} — lever: {clean(c['active_lever'], 60)} — reason: {clean(c['active_lever_reason'], 120)}"
                         f" — since {ts(c['active_lever_since'])} — moved: {'yes' if moved else 'no'}")
        self.run.count("campaigns", len(rows))
        return lines

    def part_learnings(self) -> list[str]:
        rows = self.q("select * from learnings where (client_id=%s or scope='global') and created_at >= %s and created_at < %s"
                      " order by created_at, id", self.client_id, self.since, self.now)
        lines = []
        for l in rows:
            stats = (f"direction {clean(l['direction'], 10)}, effect {clean(l['effect_size'], 12)}, sample {clean(l['sample'], 12)},"
                     f" posterior {clean(l['posterior'], 12)}")
            sample_flag = " [sample_reached=false]" if (l["evidence"] or {}).get("sample_reached") is False else ""
            lines.append(f"{l['status']} ({l['scope']}) — {clean(l['hypothesis'], 160)} — {stats} — by {clean(l['created_by'], 20)}{sample_flag}")
        self.run.count("learnings", len(rows))
        return lines

    def part_warnings(self) -> list[str]:
        w: list[str] = []
        client_paused, env_paused = self.paused()
        if client_paused:
            w.append("clients.paused is true: only status, check-in, resume may run")
        if env_paused:
            w.append("PIPELINE_PAUSED is set: only status, check-in, resume may run")
        for r in self.q("select * from runs where status='running' and started_at < %s and id <> %s and client_id=%s"
                        " order by started_at, id", self.now - self.stale, self.run.id, self.client_id):
            w.append(f"runs row left `running` by a crashed {clean(r['worker'], 30)} run since {ts(r['started_at'])} [{str(r['id'])[:8]}]")
        for r in self.q("select * from runs where status='failed' and started_at >= %s and started_at < %s and client_id=%s"
                        " order by started_at, id", self.since, self.now, self.client_id):
            w.append(f"{clean(r['worker'], 30)} run failed at {ts(r['started_at'])}: {clean(r['error'], 160)}")
        if self.stuck:
            w.append(f"{self.stuck} action(s) stuck in `applying`: run `apply actions --reconcile`; every other worker is blocked")
        for a in self.q("select a.* from actions a join runs r on r.id = a.executor_run_id where a.client_id=%s and a.status='failed'"
                        " and r.started_at >= %s and r.started_at < %s order by r.started_at, a.created_at, a.id", self.client_id, self.since, self.now):
            w.append(f"{a['action_type']} {a['target_type']}/{str(a['target_id'])[:8]} failed ({a['attempts']} attempt(s)): {clean(a['last_error'], 120)}")
        for source in blocked_sources(self.conn, self.client_id):
            w.append(f"source {clean(source, 60)} failed twice: `plan batch` is blocked until `acknowledge {clean(source, 60)}`")
        spend = self.q1("select spend_today, observed_at from account_spend_hourly where client_id=%s and observed_at::date = %s::date"
                        " order by observed_at desc limit 1", self.client_id, self.now)
        cap = self.client.get("daily_cap")
        if spend and cap is not None and spend["spend_today"] > cap:
            w.append(f"account spend today {spend['spend_today']} {self.client['currency']} exceeds daily_cap {cap} (observed {ts(spend['observed_at'])})")
        if not self.q1("select check_daily_cap(%s) as ok", self.client_id)["ok"]:
            w.append(f"check_daily_cap is false: active budgets exceed daily_cap {cap}; nothing may be activated or scaled")
        w.extend(self.zero_learnings())
        w.extend(self.brake_notes)
        self.run.count("warnings", len(w))
        return w

    def zero_learnings(self) -> list[str]:
        """SKILL.md §4 rule 2 / FR-41. The loop (`scripts/meta_insights.py`, T10) judges this at pull time and leaves
        its lines in `runs.counts.warnings`; the latest loop run of the window is quoted here. Without a loop run in
        the window the check-in judges from state: a creative at sample size and no learning written or refused."""
        loop = self.q1("select counts from runs where client_id=%s and worker='loop' and status='ok' and started_at >= %s and started_at < %s"
                       " order by started_at desc limit 1", self.client_id, self.since, self.now)
        if loop is not None:
            counts = loop["counts"] or {}
            lines = [f"pull insights: {clean(w, 200)}" for w in (counts.get("warnings") or []) if isinstance(w, str)]
            refused = counts.get("learnings_refused") or []
            if refused and not counts.get("learnings_written"):
                lines.append(f"pull insights refused {len(refused)} learning(s) below the FR-41 gates: {clean(refused[:3], 200)}")
            return lines
        kill = (self.cfg.get("targets") or {}).get("kill_impressions")
        if kill is None:
            return []
        at_sample = self.q1("select count(*) as n from mart_creative_performance where client_id=%s and impressions >= %s",
                            self.client_id, int(kill))["n"]
        if not at_sample:
            return []
        written = self.q1("select count(*) as n from learnings where client_id=%s and created_at >= %s and created_at < %s",
                          self.client_id, self.since, self.now)["n"]
        if written:
            return []
        return [f"zero learnings: {at_sample} creative(s) reached sample size ({kill} impressions) and no learnings row was written"
                " and no `pull insights` ran since the window opened"]

    # ---- assembly
    def compose(self) -> tuple[str, str, str, dict[str, int]]:
        """Returns (subject, text body, html body, counts per part)."""
        self.brakes()
        parts = [self.part_waiting(), self.part_taken(), self.part_levers(), self.part_learnings(), self.part_warnings()]
        keys = ("waiting", "taken", "campaigns", "learnings", "warnings")
        counts = {k: self.run.counts.get(k, 0) for k in keys}    # part 1 counts actions, not its helper lines
        head = f"Check-in — {self.slug} — {ts(self.now)} (window since {ts(self.since)})"
        out = [head, ""]
        for i, (title, key, lines) in enumerate(zip(PARTS, keys, parts), start=1):
            out.append(f"{i}. {title} ({counts[key]})")
            out.extend(f"   - {line}" for line in lines or ["none"])
            out.append("")
        text = "\n".join(out).rstrip() + "\n"
        html_body = f"<pre style=\"font-family: ui-monospace, monospace; white-space: pre-wrap\">{html.escape(text)}</pre>\n"
        subject = (f"[me] check-in {self.slug} {self.now.astimezone(timezone.utc).date().isoformat()}: "
                   f"{counts['waiting']} waiting, {counts['taken']} taken, {counts['warnings']} warnings")
        return subject, text, html_body, counts


def previous_checkin(conn, client_id) -> datetime | None:
    row = conn.execute("select max(started_at) as at from runs where client_id=%s and worker=%s and status='ok'", (client_id, WORKER)).fetchone()
    return row["at"] if row else None


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compose and send the five-part daily check-in. SKILL.md §3, FR-42.")
    p.add_argument("--client", default="upclicklabs")
    p.add_argument("--to", help="recipient; default CHECKIN_TO from the environment")
    p.add_argument("--since", help="window start: `24h`, `3d`, or an ISO timestamp; default the previous successful check-in, else 24h")
    p.add_argument("--now", help="reference time as an ISO timestamp (tests); default the current time")
    p.add_argument("--stale-minutes", type=int, default=STALE_MINUTES, help="a `running` runs row older than this is reported as crashed")
    p.add_argument("--dry-run", action="store_true", help="print the email instead of sending it; brakes still propose")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    now = parse_when(args.now, datetime.now(timezone.utc)) or datetime.now(timezone.utc)
    with connect("worker", job="checkin") as conn:
        client = client_by_slug(conn, args.client)
        if client is None:
            print(f"checkin: no client with slug {args.client!r}", file=sys.stderr)
            return 1
        try:
            with run(conn, WORKER, client["id"]) as r:
                print(format_where_are_we(where_are_we(conn, args.client)))
                check_config(client)
                to = args.to or (None if args.dry_run else require("checkin", "CHECKIN_TO")["CHECKIN_TO"])
                since = parse_when(args.since, now) or previous_checkin(conn, client["id"]) or now - timedelta(hours=24)
                conn.rollback()
                r.counts["since"] = since.isoformat()
                r.counts["now"] = now.isoformat()
                subject, text, html_body, counts = Checkin(conn, client, r, now=now, since=since, stale_minutes=args.stale_minutes).compose()
                conn.rollback()
                if args.dry_run:
                    print(f"subject: {subject}\n{text}", end="")
                    r.count("sent", 0)
                else:
                    message_id = get_email().send(to=to, subject=subject, text=text, html=html_body)
                    r.count("sent")
                    print(f"sent {message_id}: {subject}")
                print("counts: " + " ".join(f"{k}={v}" for k, v in counts.items()))   # what Slack would carry (FR-42)
        except ConfigError as exc:
            print(f"checkin: {exc}", file=sys.stderr)
            return 2
        print(f"runs {r.id}: ok {json.dumps(r.counts, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
