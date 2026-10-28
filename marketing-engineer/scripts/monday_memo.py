#!/usr/bin/env python3
"""The Monday memo: one email, exactly five sections in order. SKILL.md §3, §8 (`me-monday`); PRD FR-43, DR-3;
DECISIONS C1 (variant promotion), C5 (taste corrected by the market), C7, C8 (schema growth rule).

    scripts/monday_memo.py [--client upclicklabs] [--to sam@…] [--since 7d|ISO] [--now ISO] [--dry-run]

Sections, in this order and no others:
  1. learnings promoted (`supported`, `global`) or refuted (`refuted`, `retired`) since the window opened, and how
     many are still `proposed`;
  2. taste vs market, cumulative: every creative with a verdict from Sam (his latest `gate_scores` row) against its
     live performance (`mart_creative_performance`). A number below sample size (`targets.kill_impressions`) is
     labelled sub-sample and grades nothing; a creative Sam rejected never ran, so the market cannot grade the
     rejection until it is re-run or ablated; the agent's shadow verdict is counted against Sam's;
  3. variant -> family promotion proposals: a variant with at least `PROMOTE_MIN_AT_SAMPLE` creatives at sample size
     (DECISIONS C1), named with those creatives and its link CTR against the rest of its family. Nothing else is
     proposed, and no action is written (the executor has no `promote_variant` handler in phase 0; Sam decides);
  4. JSONB keys due for column promotion (DR-3): every key `warehouse/schema-notes.md` documents that the code reads
     in a worker other than the one that writes it, or in a mart (`keys_due`, a static scan of scripts/, warehouse/
     and funnel/; a read through a variable the scan does not know is missed, so the list can only be short);
  5. the next batch's proposals: the open proposal (an experiment without a `selections` row) with each brief's
     weekend template and the default the planner would take, or "none open".

The window opens at the previous memo that was sent or queued (a same-day duplicate or a dry run never moves it),
else 7 days ago; `--since` overrides it and `--now` fixes the reference time so the golden-file test is reproducible.
Every string out of a row passes the check-in's `clean()` (no URL survives, NFR-2); the HTML part is the escaped text. Delivery is the email adapter, to
`CHECKIN_TO` (or `--to`): `EMAIL_BACKEND=file` writes the .eml at once; `gmail_connector` queues the memo under
`memo-<slug>-<UTC day>` with the check-in's claim (`queue_checkin`), and the `me-monday` routine's last step delivers
it through the Gmail connector (`scripts/checkin.py --send-pending`, then `--mark-sent`). Refuses while paused (SKILL.md §0 step 4) or while an action is `applying` (§2). Worker
role only; the only warehouse write is the `runs` row.
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.email import get_email  # noqa: E402
from adapters.env import ME_DIR, require  # noqa: E402
from warehouse.client import client_by_slug, connect, format_where_are_we, run, where_are_we  # noqa: E402

WORKER = "memo"
WINDOW_DAYS = 7
PROMOTE_MIN_AT_SAMPLE = 3                 # DECISIONS C1: a variant at sample size across >= 3 creatives
SECTIONS = ("Learnings promoted / refuted", "Taste vs market", "Variant -> family promotion proposals",
            "JSONB keys due for column promotion", "Next batch's proposals")
PROMOTED, REFUTED = ("supported", "global"), ("refuted", "retired")
TRUTHY = ("1", "true", "yes", "on")
ALIASES = {"cfg": "config", "brief_spec": "spec"}   # variables the code uses for a JSONB column under another name
SETUP_WRITERS = {"seed"}                  # copies Sam's config file: not a worker, so its keys are due only when two workers read them


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"me_script_{name}", Path(__file__).with_name(f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_checkin = _load_script("checkin")
clean, ts, parse_when = _checkin.clean, _checkin.ts, _checkin.parse_when


def memo_key(slug: str, now: datetime) -> str:
    """The queue key under EMAIL_BACKEND=gmail_connector: one memo per client and UTC day (`scripts/checkin.py
    --send-pending` prints it for the Gmail connector, `--mark-sent memo-<slug>-<day> --message-id <id>` records it)."""
    return f"memo-{slug}-{now.astimezone(timezone.utc).date().isoformat()}"


class MemoRefused(RuntimeError):
    """The memo refused to run; the runs row closes `failed` with the reason."""


# ---------- DR-3: JSONB keys read by a second worker or a mart (pure, unit-tested) ----------

def jsonb_columns(schema_sql: str) -> dict[str, list[str]]:
    """Column name -> the tables that have a JSONB column of that name, from `create table` blocks."""
    out: dict[str, list[str]] = defaultdict(list)
    table = None
    for line in schema_sql.splitlines():
        m = re.match(r"create table (?:if not exists )?(\w+)", line)
        if m:
            table = m.group(1)
            continue
        col = re.match(r"\s+(\w+)\s+jsonb\b", line)
        if table and col:
            out[col.group(1)].append(table)
    return dict(out)


def _top_level_keys(cell: str) -> list[str]:
    """Backticked keys outside `{}` / `[]` in a schema-notes key cell; `a.b` counts as `a`; a placeholder such as
    `<any>` comes back as "" (it names no key)."""
    keys, depth = [], 0
    for token in re.finditer(r"`([^`]*)`|[{\[]|[}\]]", cell):
        text = token.group(0)
        if text in "{[":
            depth += 1
        elif text in "}]":
            depth = max(depth - 1, 0)
        elif depth == 0:
            name = token.group(1)
            if name.startswith("<"):
                keys.append("")
            elif (m := re.match(r"[A-Za-z_]\w*", name)):
                keys.append(m.group(0))
    return keys


def _writers(cell: str) -> set[str]:
    labels = set(re.findall(r"scripts/(\w+)\.py", cell))
    labels |= {f"warehouse/{m}" for m in re.findall(r"warehouse[./](client|launch)\b", cell)}
    labels |= {f"funnel/{m}" for m in re.findall(r"funnel/(\w+)\.py", cell)}
    labels |= set(re.findall(r"`(\w+)\(\)`", cell))
    return labels


def documented_keys(notes: str, columns: dict[str, list[str]]) -> dict[str, dict[str, set[str]]]:
    """`warehouse/schema-notes.md` § "JSONB keys in use" -> {table.column: {top-level key or "*": writer labels}}.
    A row without a backticked key ("whole file") documents every key of its column ("*"); `<any>` documents none
    (the row says each worker documents its own keys)."""
    section = notes.split("## JSONB keys in use", 1)[-1].split("\n## ", 1)[0]
    real = {f"{t}.{c}" for c, tables in columns.items() for t in tables}
    out: dict[str, dict[str, set[str]]] = {}
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]]
        if len(cells) < 3:
            continue
        column = cells[0].strip("`")
        if column not in real:
            continue
        keys = _top_level_keys(cells[1]) or ["*"]
        for key in filter(None, keys):
            out.setdefault(column, {}).setdefault(key, set()).update(_writers(cells[2]))
    return out


def expand_config_file(doc: dict[str, dict[str, set[str]]], root: Path) -> dict[str, dict[str, set[str]]]:
    """`clients.config` is `config/clients/<slug>.json` copied whole: its "*" row stands for the files' top-level keys."""
    config = doc.get("clients.config") or {}
    files = sorted((root / "config" / "clients").glob("*.json"))
    if "*" not in config or not files:
        return doc
    writers = config.pop("*")
    for f in files:
        for key in json.loads(f.read_text()):
            if not key.startswith("_"):
                config.setdefault(key, set()).update(writers)
    return doc


def _sql_reads(text: str, cols: str):
    for m in re.finditer(rf"(?<![\w.])(?:\w+\.)?({cols})\s*(?:->>?|\?)\s*'([A-Za-z_]\w*)'", text):
        yield m.group(1), m.group(2)


def _py_reads(line: str, cols: str):
    pattern = rf"\b({cols})\b[\"']?\s*[\])]?(?:\s*or\s*\{{\}}\s*\)?)?\s*(?:\.get\(\s*|\[\s*)[\"']([A-Za-z_]\w*)[\"']\s*\]?"
    for m in re.finditer(pattern, line):
        if re.match(r"\s*(?:=(?!=)|\+=|-=)", line[m.end():]):
            continue                                   # an assignment writes the key
        yield ALIASES.get(m.group(1), m.group(1)), m.group(2)


def code_reads(root: Path, columns: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Every read of a `<jsonb column>` key in the code: SQL (`col->'key'`, `col->>'key'`, `col ? 'key'`) in .sql and
    .py files, Python (`col["key"]`, `col.get("key")`, through `(x.get("col") or {})`). Reader labels: the script
    stem, `warehouse/<module>`, `funnel/<module>`, or the SQL view (`mart <name>` for a mart, `view <name>`) or
    function it sits in."""
    names = sorted(set(columns) | set(ALIASES), key=len, reverse=True)
    cols = "|".join(re.escape(n) for n in names)
    files = sorted(root.glob("scripts/*.py")) + sorted(root.glob("warehouse/*.py")) + sorted(root.glob("funnel/*.py")) \
        + sorted(root.glob("warehouse/*.sql"))
    reads = []
    for path in files:
        rel = path.relative_to(root)
        label = path.stem if rel.parts[0] == "scripts" else f"{rel.parts[0]}/{path.stem}"
        current = None
        for n, line in enumerate(path.read_text().splitlines(), start=1):
            if path.suffix == ".sql":
                head = re.search(r"create\s+(?:or\s+replace\s+)?(view|function)\s+(\w+)", line, re.I)
                if head:
                    kind, name = head.group(1).lower(), head.group(2)
                    current = f"mart {name}" if kind == "view" and name.startswith("mart_") else f"{kind} {name}"
                elif re.search(r"create\s+table", line, re.I):
                    current = None
                found = list(_sql_reads(line, cols))
                reader = current or str(rel)
            else:
                found = list(_sql_reads(line, cols)) + list(_py_reads(line, cols))
                reader = label
            for col, key in found:
                reads.append({"reader": reader, "column": ALIASES.get(col, col), "key": key, "where": f"{rel}:{n}"})
    return reads


def keys_due(root: Path = ME_DIR) -> list[dict[str, Any]]:
    """DR-3: documented JSONB keys read by a mart, or by a second worker: a worker other than the one that writes the
    key (the first worker that needed it), or two readers when the writer is setup (`SETUP_WRITERS`). Sorted by
    column, key."""
    columns = jsonb_columns((root / "warehouse" / "schema.sql").read_text())
    doc = expand_config_file(documented_keys((root / "warehouse" / "schema-notes.md").read_text(), columns), root)
    readers: dict[tuple[str, str], set[str]] = defaultdict(set)
    places: dict[tuple[str, str], set[str]] = defaultdict(set)
    writers: dict[tuple[str, str], set[str]] = {}
    for read in code_reads(root, columns):
        candidates = [f"{t}.{read['column']}" for t in columns.get(read["column"], []) if f"{t}.{read['column']}" in doc]
        explicit = [c for c in candidates if read["key"] in doc[c]]
        for column in explicit or [c for c in candidates if "*" in doc[c]]:
            k = (column, read["key"])
            readers[k].add(read["reader"])
            places[k].add(read["where"])
            writers[k] = doc[column].get(read["key"]) or doc[column].get("*") or set()
    due = []
    for k in sorted(readers):
        others = readers[k] - writers[k]
        mart = any(r.startswith("mart ") for r in readers[k])
        if mart or (others and len(readers[k] | (writers[k] - SETUP_WRITERS)) >= 2):
            due.append({"column": k[0], "key": k[1], "readers": sorted(readers[k]), "writers": sorted(writers[k]), "mart": mart,
                        "places": len(places[k])})
    return due


# ---------- the composer ----------

def pct(value: Any) -> str:
    return "-" if value is None else f"{float(value) * 100:.2f}%"


class Memo:
    def __init__(self, conn, client: dict[str, Any], r, *, now: datetime, since: datetime, code_root: Path):
        self.conn, self.client, self.run = conn, client, r
        self.client_id, self.slug = client["id"], client["slug"]
        self.cfg = client.get("config") or {}
        self.now, self.since, self.code_root = now, since, code_root
        self.kill = int((self.cfg.get("targets") or {})["kill_impressions"])
        self.floor = float((self.cfg.get("targets") or {})["ctr_floor"])

    def q(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        return self.conn.execute(sql, params).fetchall()

    # ---- 1
    def learnings(self) -> list[str]:
        rows = self.q("select * from learnings where (client_id=%s or scope='global') and status = any(%s) and updated_at >= %s and updated_at < %s"
                      " order by updated_at, id", self.client_id, list(PROMOTED + REFUTED), self.since, self.now)
        lines = [f"{l['status']} ({l['scope']}) — {clean(l['hypothesis'], 160)} — {clean(l['component_type'], 30)}={clean(l['component_ref'], 60)},"
                 f" effect {clean(l['effect_size'], 12)}, sample {clean(l['sample'], 12)}, posterior {clean(l['posterior'], 12)}"
                 f" — {'promoted' if l['status'] in PROMOTED else 'refuted'} {ts(l['updated_at'])}" for l in rows]
        if not rows:
            lines.append(f"none promoted or refuted since {ts(self.since)}")
        proposed = self.q("select count(*) as n from learnings where (client_id=%s or scope='global') and status='proposed'", self.client_id)[0]["n"]
        if proposed:
            lines.append(f"{proposed} learning(s) still proposed: `supported` needs a replication or an ablation (FR-41)")
        self.run.counts["learnings"] = len(rows)
        return lines

    # ---- 2
    TASTE_SQL = """
    with sam as (select distinct on (g.creative_id) g.creative_id, g.verdict from gate_scores g join creatives c on c.id = g.creative_id
                  where c.client_id = %s and g.scored_by = 'sam' order by g.creative_id, g.attempt desc, g.created_at desc),
         agent as (select distinct on (g.creative_id) g.creative_id, g.verdict, g.avg_score from gate_scores g join creatives c on c.id = g.creative_id
                    where c.client_id = %s and g.scored_by = 'agent' order by g.creative_id, g.attempt desc, g.created_at desc)
    select c.id, c.status, c.template, c.version, b.family, (b.spec->>'proposal_number')::int as proposal_number, e.name as experiment,
           s.verdict as sam, a.verdict as agent, a.avg_score, p.impressions, p.link_clicks, p.link_ctr
      from sam s join creatives c on c.id = s.creative_id
      left join agent a on a.creative_id = c.id left join briefs b on b.id = c.brief_id
      left join experiments e on e.id = c.experiment_id left join mart_creative_performance p on p.creative_id = c.id
     order by e.created_at nulls last, proposal_number nulls last, c.created_at, c.id
    """

    def taste(self) -> list[str]:
        rows = self.q(self.TASTE_SQL, self.client_id, self.client_id)
        self.run.counts["taste_creatives"] = len(rows)
        if not rows:
            return ["no creative has a verdict from Sam yet"]
        lines = []
        approved = [c for c in rows if c["sam"] == "approve"]
        delivered = [c for c in approved if c["impressions"]]
        at_sample = [c for c in delivered if int(c["impressions"]) >= self.kill]
        for c in delivered:
            name = f"{clean(c['experiment'], 30)} #{c['proposal_number']} {clean(c['family'], 30)}/{clean(c['template'], 30)} v{c['version']} [{str(c['id'])[:8]}]"
            agent = f"agent shadow {c['agent'] or '-'} ({clean(c['avg_score'], 6)})"
            if int(c["impressions"]) >= self.kill:
                side = "above" if float(c["link_ctr"] or 0) >= self.floor else "below"
                lines.append(f"approved {name}: link CTR {pct(c['link_ctr'])} over {c['impressions']} impressions, {side} the {pct(self.floor)} floor — {agent}")
            else:
                lines.append(f"approved {name}: sub-sample ({c['impressions']} of {self.kill} impressions): grades nothing yet"
                             f" (link CTR {pct(c['link_ctr'])} so far) — {agent}")
        above = sum(1 for c in at_sample if float(c["link_ctr"] or 0) >= self.floor)
        if at_sample:
            lines.append(f"at sample size: {len(at_sample)} of {len(approved)} approved; the market agrees with Sam's approval on {above}"
                         f" (at or above the CTR floor) and not on {len(at_sample) - above}")
        else:
            lines.append(f"no approved creative has reached sample size ({self.kill} impressions): every number above is sub-sample and grades"
                         " nothing yet (FR-41)")
        silent = len(approved) - len(delivered)
        if silent:
            lines.append(f"{silent} approved creative(s) have no delivery yet")
        rejected = [c for c in rows if c["sam"] == "reject"]
        if rejected:
            lines.append(f"{len(rejected)} rejected by Sam never ran: the market cannot grade a rejection until it is re-run or ablated (DECISIONS C5)")
        both = [c for c in rows if c["agent"]]
        agree = sum(1 for c in both if c["agent"] == c["sam"])
        lines.append(f"agent shadow verdict agreed with Sam on {agree} of {len(both)} (the rubric stays shadow until it is promoted)")
        self.run.counts["at_sample"] = len(at_sample)
        return lines

    # ---- 3
    VARIANTS_SQL = """
    select v.component_ref as variant, f.component_ref as family, count(*) as creatives,
           count(*) filter (where p.impressions >= %s) as at_sample,
           coalesce(sum(p.impressions) filter (where p.impressions >= %s), 0) as impressions,
           coalesce(sum(p.link_clicks) filter (where p.impressions >= %s), 0) as link_clicks,
           array_agg(c.id order by c.created_at, c.id) filter (where p.impressions >= %s) as sample_ids
      from creatives c
      join creative_components v on v.creative_id = c.id and v.component_type = 'variant'
      join creative_components f on f.creative_id = c.id and f.component_type = 'family'
      left join mart_creative_performance p on p.creative_id = c.id
     where c.client_id = %s
       and not exists (select 1 from families x where x.promoted_from_variant = v.component_ref)
     group by v.component_ref, f.component_ref
     order by at_sample desc, v.component_ref, f.component_ref
    """
    FAMILY_REST_SQL = """
    select coalesce(sum(p.impressions), 0) as impressions, coalesce(sum(p.link_clicks), 0) as link_clicks
      from creatives c
      join creative_components f on f.creative_id = c.id and f.component_type = 'family' and f.component_ref = %s
      join creative_components v on v.creative_id = c.id and v.component_type = 'variant' and v.component_ref <> %s
      join mart_creative_performance p on p.creative_id = c.id
     where c.client_id = %s and p.impressions >= %s
    """

    def variants(self) -> list[str]:
        rows = self.q(self.VARIANTS_SQL, self.kill, self.kill, self.kill, self.kill, self.client_id)
        proposals = [v for v in rows if int(v["at_sample"]) >= PROMOTE_MIN_AT_SAMPLE]
        self.run.counts["variant_proposals"] = len(proposals)
        lines = []
        for v in proposals:
            ctr = int(v["link_clicks"]) / int(v["impressions"]) if int(v["impressions"]) else None
            rest = self.q(self.FAMILY_REST_SQL, v["family"], v["variant"], self.client_id, self.kill)[0]
            vs = (f"{pct(int(rest['link_clicks']) / int(rest['impressions']))} for the rest of {clean(v['family'], 40)} at sample size"
                  if int(rest["impressions"]) else f"no other variant of {clean(v['family'], 40)} at sample size to compare")
            ids = ", ".join(str(i)[:8] for i in v["sample_ids"] or [])
            lines.append(f"propose `{clean(v['variant'], 80)}` (family {clean(v['family'], 40)}) as a family: {v['at_sample']} creatives at sample size"
                         f" [{ids}]; link CTR {pct(ctr)} over {v['impressions']} impressions vs {vs}")
        if proposals:
            lines.append("approve or reject in chat; the executor applies no `promote_variant` in phase 0, so an approved promotion is a"
                         " references/families.md change Sam makes")
        elif rows:
            best = rows[0]
            lines.append(f"none: no variant has {PROMOTE_MIN_AT_SAMPLE} creatives at sample size ({self.kill} impressions); closest:"
                         f" `{clean(best['variant'], 80)}` ({clean(best['family'], 40)}) with {best['at_sample']} of {PROMOTE_MIN_AT_SAMPLE}")
        else:
            lines.append("none: no creative carries a variant component yet")
        return lines

    # ---- 4
    def keys(self) -> list[str]:
        due = keys_due(self.code_root)
        self.run.counts["keys_due"] = len(due)
        if not due:
            return ["none: no documented JSONB key is read by a second worker or a mart"]
        lines = [f"{len(due)} key(s) in {len({d['column'] for d in due})} column(s) are read by a second worker or a mart: each is due for a"
                 " real column through a numbered migration (DR-3); static scan of scripts/, warehouse/, funnel/ against"
                 " warehouse/schema-notes.md"]
        for d in due:
            written = ", ".join(d["writers"]) or "not named in schema-notes"
            lines.append(f"{d['column']}.{d['key']} — read by {', '.join(d['readers'])} ({d['places']} place(s)); written by {written}")
        return lines

    # ---- 5
    OPEN_SQL = """
    select e.* from experiments e where e.client_id = %s and e.kind = 'new_recipes'
       and not exists (select 1 from selections s where s.experiment_id = e.id) order by e.created_at desc limit 1
    """

    def next_batch(self) -> list[str]:
        exp = self.q(self.OPEN_SQL, self.client_id)
        if not exp:
            self.run.counts["open_proposals"] = 0
            return ["none open: no proposal is waiting for picks; `plan batch` proposes one when capacity frees (FR-16)"]
        planner = _load_script("plan_batch")
        briefs = self.q("select b.*, h.text as hook_text from briefs b left join hooks h on h.id = b.hook_id where b.experiment_id = %s",
                        exp[0]["id"])
        briefs.sort(key=planner.proposal_number)
        self.run.counts["open_proposals"] = len(briefs)
        n = int((self.cfg.get("batch") or {}).get("recipes") or 0)
        lines = [f"{clean(exp[0]['name'], 40)} waits for picks: {len(briefs)} proposals (capacity {exp[0]['capacity']})"]
        for b in briefs:
            spec = b.get("spec") or {}
            src = spec.get("source") or {}
            lines.append(f"#{planner.proposal_number(b)} {clean(b['family'], 40)} / {clean(src.get('variant'), 60)} — {clean(b.get('hook_text') or spec.get('hook_line'), 100)}"
                         f" — {clean(b['angle'], 30)} — {clean(src.get('brand'), 40)} ({clean(src.get('source_strength'), 6)})"
                         f" — template {planner.template_for(b['family']) or 'NONE'}")
        if n:
            picks, _ = planner.default_picks(briefs, n)
            default = ", ".join(f"#{k}" for k in picks) if len(picks) == n else "none (too few proposals have a template)"
            lines.append(f"reply `my picks: n, n, n` with exactly {n} numbers; default after 20 minutes: {default}")
        return lines

    # ---- assembly
    def compose(self) -> tuple[str, str, str, dict[str, int]]:
        parts = [self.learnings(), self.taste(), self.variants(), self.keys(), self.next_batch()]
        keys = ("learnings", "taste_creatives", "variant_proposals", "keys_due", "open_proposals")
        counts = {k: int(self.run.counts.get(k, 0)) for k in keys}
        out = [f"Monday memo — {self.slug} — {ts(self.now)} (window since {ts(self.since)})", ""]
        for i, (title, key, lines) in enumerate(zip(SECTIONS, keys, parts), start=1):
            out.append(f"{i}. {title} ({counts[key]})")
            out.extend(f"   - {line}" for line in lines)
            out.append("")
        text = "\n".join(out).rstrip() + "\n"
        html_body = f"<pre style=\"font-family: ui-monospace, monospace; white-space: pre-wrap\">{html.escape(text)}</pre>\n"
        subject = (f"[me] monday memo {self.slug} {self.now.astimezone(timezone.utc).date().isoformat()}: {counts['learnings']} promoted/refuted, "
                   f"{counts['variant_proposals']} variant proposal(s), {counts['keys_due']} key(s) due, {counts['open_proposals']} open proposal(s)")
        return subject, text, html_body, counts


def previous_memo(conn, client_id) -> datetime | None:
    """The last memo that was sent or queued (`checkin.window_anchor`): a same-day duplicate or a dry run never moves it."""
    return _checkin.window_anchor(conn, client_id, WORKER)


def check_ready(client: dict[str, Any], status: dict[str, Any]) -> None:
    targets = (client.get("config") or {}).get("targets") or {}
    missing = [k for k, v in (("targets.ctr_floor", targets.get("ctr_floor")), ("targets.kill_impressions", targets.get("kill_impressions")),
                              ("daily_cap", client.get("daily_cap")), ("currency", client.get("currency"))) if v is None]
    if missing:
        raise MemoRefused(f"clients.config for {client['slug']!r} is missing {', '.join(missing)}; refusing to run")
    if client.get("paused") or (os.environ.get("PIPELINE_PAUSED") or "").strip().lower() in TRUTHY:
        raise MemoRefused("pipeline paused (clients.paused or PIPELINE_PAUSED): only status, check-in, resume may run (SKILL.md §0)")
    if status and status.get("actions_stuck"):
        raise MemoRefused(f"{status['actions_stuck']} action(s) in `applying`; only the executor's reconcile mode may run (SKILL.md §2)")


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compose and send the five-section Monday memo. SKILL.md §3, FR-43.")
    p.add_argument("--client", default="upclicklabs")
    p.add_argument("--to", help="recipient; default CHECKIN_TO from the environment")
    p.add_argument("--since", help="window start: `7d`, `24h`, or an ISO timestamp; default the previous memo sent or queued, else 7 days")
    p.add_argument("--now", help="reference time as an ISO timestamp (tests); default the current time")
    p.add_argument("--dry-run", action="store_true", help="print the memo instead of sending it")
    p.add_argument("--code-root", type=Path, default=ME_DIR, help="tree the DR-3 key scan reads (tests); default marketing-engineer/")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    now = parse_when(args.now, datetime.now(timezone.utc)) or datetime.now(timezone.utc)
    with connect("worker", job=WORKER) as conn:
        client = client_by_slug(conn, args.client)
        if client is None:
            print(f"monday_memo: no client with slug {args.client!r}", file=sys.stderr)
            return 1
        try:
            with run(conn, WORKER, client["id"]) as r:
                status = where_are_we(conn, args.client)
                print(format_where_are_we(status))
                check_ready(client, status)
                to = args.to or (None if args.dry_run else require(WORKER, "CHECKIN_TO")["CHECKIN_TO"])
                since = parse_when(args.since, now) or previous_memo(conn, client["id"]) or now - timedelta(days=WINDOW_DAYS)
                conn.rollback()
                r.counts["since"] = since.isoformat()
                r.counts["now"] = now.isoformat()
                subject, text, html_body, counts = Memo(conn, client, r, now=now, since=since, code_root=args.code_root).compose()
                conn.rollback()
                if args.dry_run:
                    print(f"subject: {subject}\n{text}", end="")
                    r.count("sent", 0)
                else:
                    mailer = get_email()
                    if mailer.queued:     # EMAIL_BACKEND=gmail_connector: the routine session sends it (checkin.py --send-pending)
                        _checkin.queue_checkin(conn, r, mailer, client, memo_key(client["slug"], now), to=to, subject=subject,
                                               text=text, html_body=html_body, worker=WORKER)
                    else:
                        message_id = mailer.send(to=to, subject=subject, text=text, html=html_body)
                        r.count("sent")
                        print(f"sent {message_id}: {subject}")
        except MemoRefused as exc:
            print(f"monday_memo: refused: {exc}", file=sys.stderr)
            return 2
        print(f"runs {r.id}: ok {json.dumps(r.counts, sort_keys=True, default=str)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
