#!/usr/bin/env python3
"""`pull voc` — the language worker (T3, FR-10 to FR-13).

Sources → anonymised `voc_phrases` rows with a pointer, a weight, a visibility, and a trust tier:

- vault notes copied into `config/clients/<slug>/voc-seed/*.md` (the vault itself is never opened, and this
  file has no write path at all): `source='vault'`, `source_weight=3`, `visibility='internal'`, `trust_tier='owned'`,
  `source_ref` = the note's path;
- public threads from `voc.public_sources` in the client config, fetched through `adapters.voc`
  (fixture in dev mode, never the network): `source_weight=1`, `visibility='public'`, `trust_tier='public'`,
  `source_ref` = a hash of the URL (FR-11: never the URL, never the text).

Each source is recorded in `raw_ingest` (vault: path + content hash only; public: the fetched thread, no
authors, `purge_after` 90 days) and sent to the model adapter inside a delimited data block with the fixed
prompts in `references/prompts/language.md`. The model anonymises at extraction; `validate_phrase()` is the
second line of defence and rejects any phrase that still contains an identifier found in the source
(proper-noun runs, headcounts, amounts, emails, handles) or one the model says it removed.

Dedup is the schema's `unique (source_ref, phrase_normalised)`: every phrase is inserted and a duplicate is
the constraint firing, counted, never pre-filtered. Every invocation opens and closes a `runs` row (worker
`voc`), also on failure. A public source that fails is retried once; if it still fails the other sources
land and the run ends `failed` naming the hashed ref (SKILL.md §7). Exit 0 ok, 1 source failure, 2 refused
(paused, missing config, unknown client).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402

from adapters.env import ME_DIR, load_env  # noqa: E402
from adapters.model import Model, get_model  # noqa: E402
from adapters.voc import PublicThreads, get_voc, source_name, url_ref  # noqa: E402
from warehouse.client import (  # noqa: E402
    Run, client_by_slug, connect, format_where_are_we, insert, run, where_are_we,
)

WORKER = "voc"
CATEGORIES = ("pain", "outcome", "objection", "identity", "trigger")
PROMPTS = ME_DIR / "references" / "prompts" / "language.md"
PUBLIC_PURGE_DAYS = 90  # CRUCIBLE A13: PII sources purge at fetched_at + 90 days
REQUIRED_CONFIG = (("targets", "ctr_floor"), ("targets", "kill_impressions"), ("daily_cap",), ("currency",))

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "phrases": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "properties": {
                    "phrase": {"type": "string", "minLength": 8, "maxLength": 300},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                },
                "required": ["phrase", "category"],
                "additionalProperties": False,
            },
        },
        "identifiers_removed": {"type": "array", "items": {"type": "string", "maxLength": 120}},
    },
    "required": ["phrases", "identifiers_removed"],
    "additionalProperties": False,
}


class IdentifierLeak(ValueError):
    """A phrase still contains something that identifies the speaker (FR-11)."""


class SourceFailed(RuntimeError):
    """A public source failed twice; the run is `failed` and names the hashed ref, never the URL."""


class PipelinePaused(RuntimeError):
    """`clients.paused` or PIPELINE_PAUSED is set: only status, check-in, resume may run (SKILL.md §0)."""


class ConfigMissing(RuntimeError):
    """A required config key is absent (SKILL.md §0 step 1)."""


class ClientMissing(RuntimeError):
    """The slug has no `clients` row: run `scripts/dev_db.sh --seed` first."""


# ---------- text ----------

def normalise(phrase: str) -> str:
    """`phrase_normalised`: lower case, letters/digits/spaces only, single spaces."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", phrase.lower()).split())


_TOKEN = r"[A-Z][a-z]+(?:[A-Z][A-Za-z]+)*"  # Titlecase or CamelCase (BrightPath); never all-caps (SEO, AI, CEO)
_SUFFIXES = ("AB", "AG", "AS", "BV", "Co", "Corp", "GmbH", "Inc", "LLC", "Ltd", "Oy", "PLC", "SA", "plc")
_RUN = re.compile(rf"\b({_TOKEN}(?:[ \t]+(?:{_TOKEN}|{'|'.join(_SUFFIXES)})\.?)+)(?![A-Za-z])")
_LEADING_STOP = {"The", "A", "An", "My", "Our", "Your", "His", "Her", "Their", "This", "That", "These", "Those",
                 "When", "If", "And", "But", "So", "Then", "Just", "Or", "As", "At", "In", "On", "For", "With",
                 "From", "To", "Of", "It", "Its", "We", "They", "You", "He", "She", "Also", "Now"}
_FIGURES = (
    re.compile(r"[€$£]\s?\d[\d,.]*\s?[kKmM]?(?![A-Za-z0-9])"),                     # £20k, €40,000
    re.compile(r"(?<![\w.])\d[\d,.]*\s?[kKmM](?![A-Za-z0-9])"),                    # 40k, 2m
    re.compile(r"\b\d[\d,.]*[\s-]*(?:staff|people|person|employees|heads|fte)s?\b", re.I),  # 48 staff, 35 person
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),                                       # emails
    re.compile(r"(?<![\w.])@\w{3,}"),                                              # @handles
    re.compile(r"\+?\d[\d ()-]{7,}\d"),                                            # phone numbers
)


def identifiers(text: str) -> set[str]:
    """Identifiers that must not survive into a phrase, found by rule in the source text: runs of two or more
    proper-noun tokens (names, companies), headcounts, money amounts, emails, handles, phone numbers. Single
    capitalised words are left alone (ChatGPT, Google, a city) so the model's own list covers those."""
    found: set[str] = set()
    for m in _RUN.finditer(text):
        tokens = m.group(1).rstrip(".").split()
        while tokens and tokens[0] in _LEADING_STOP:
            tokens.pop(0)
        if len(tokens) >= 2:
            found.add(" ".join(tokens))
    for pat in _FIGURES:
        found.update(m.group(0).strip() for m in pat.finditer(text))
    return {f for f in found if len(f) >= 2}


def _pattern(identifier: str) -> re.Pattern[str]:
    parts = [re.escape(p) for p in identifier.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.I)


def leaked(phrase: str, ids: set[str]) -> str | None:
    """The first identifier (longest first) that appears in the phrase as a whole word or phrase, else None."""
    for identifier in sorted((i for i in ids if i.strip()), key=lambda i: (-len(i), i)):
        if _pattern(identifier.strip()).search(phrase):
            return identifier
    return None


def validate_phrase(phrase: str, ids: set[str]) -> None:
    hit = leaked(phrase, ids)
    if hit is not None:
        raise IdentifierLeak(f"phrase still contains identifier {hit!r}")


def strip_frontmatter(text: str) -> str:
    return re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.S)


def thread_text(thread: dict[str, Any]) -> str:
    """The untrusted text for one public thread: title, then each comment as a bullet. No authors exist in the shape."""
    lines = [thread.get("title") or ""]
    lines += [f"- {c['text']}" for c in thread.get("comments") or []]
    return "\n".join(lines).strip()


# ---------- sources ----------

@dataclass
class Source:
    kind: str            # vault | public
    ref: str             # voc_phrases.source_ref: note path or hashed URL
    text: str            # untrusted text for the model
    source: str          # voc_phrases.source: vault | reddit | quora | ...
    source_weight: int
    visibility: str
    trust_tier: str
    dedup_key: str       # raw_ingest.dedup_key: source + external id + content hash
    payload: dict[str, Any]
    fetched_at: datetime
    purge_after: datetime | None


def vault_sources(seed_dir: Path) -> list[Source]:
    """Every note in the seed folder, sorted by name (README excluded). Reads only."""
    out: list[Source] = []
    for path in sorted(p for p in seed_dir.glob("*.md") if p.name.lower() != "readme.md"):
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        ref = str(path.relative_to(ME_DIR)) if path.resolve().is_relative_to(ME_DIR) else str(path)
        out.append(Source(
            kind="vault", ref=ref, text=strip_frontmatter(raw.decode("utf-8")), source="vault",
            source_weight=3, visibility="internal", trust_tier="owned",
            dedup_key=f"vault:{ref}:{sha[:16]}",
            payload={"kind": "vault_note", "path": ref, "sha256": sha, "bytes": len(raw)},
            fetched_at=datetime.now(timezone.utc), purge_after=None,
        ))
    return out


def public_sources(urls: list[str], threads: PublicThreads, r: Run) -> tuple[list[Source], list[str]]:
    """Fetch each configured thread, retrying once. Returns (sources, hashed refs that failed twice)."""
    out: list[Source] = []
    failed: list[str] = []
    for url in urls:
        ref = url_ref(url)
        thread = None
        for attempt in (1, 2):
            try:
                thread = threads.fetch_thread(url)
                break
            except Exception as exc:  # noqa: BLE001 — any failure of the source counts; retried once (SKILL.md §7)
                print(f"pull_voc: {ref} attempt {attempt} failed: {type(exc).__name__}", file=sys.stderr)
                if attempt == 1:
                    r.count("source_retries")
        if thread is None:
            failed.append(ref)
            r.count("sources_failed")
            continue
        text = thread_text(thread)
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        src = source_name(url)
        now = datetime.now(timezone.utc)
        out.append(Source(
            kind="public", ref=ref, text=text, source=src, source_weight=1, visibility="public", trust_tier="public",
            dedup_key=f"{src}:{ref}:{sha[:16]}", payload=thread,
            fetched_at=now, purge_after=now + timedelta(days=PUBLIC_PURGE_DAYS),
        ))
    return out, failed


# ---------- extraction ----------

def load_prompts(path: Path = PROMPTS) -> tuple[str, str]:
    """(system, instructions) from references/prompts/language.md."""
    text = path.read_text()
    sections = re.split(r"^## (\w+)\s*$", text, flags=re.M)
    found = {sections[i].lower(): sections[i + 1].strip() for i in range(1, len(sections) - 1, 2)}
    if "system" not in found or "instructions" not in found:
        raise RuntimeError(f"{path} needs '## System' and '## Instructions' sections")
    return found["system"], found["instructions"]


def extract(model: Model, src: Source, prompts: tuple[str, str], r: Run | None = None
            ) -> tuple[list[dict[str, str]], list[str]]:
    """One model call for one source. Returns (phrases that passed the validator, identifiers that leaked)."""
    system, instructions = prompts
    result = model.generate_json(task="voc_extract", system=system, instructions=instructions,
                                 untrusted=src.text, schema=SCHEMA, max_tokens=2048)
    if r is not None:
        r.api_calls = (r.api_calls or 0) + 1
        r.tokens_used = (r.tokens_used or 0) + result.tokens_used
    ids = identifiers(src.text) | {i.strip() for i in result.output["identifiers_removed"] if i.strip()}
    kept: list[dict[str, str]] = []
    rejected: list[str] = []
    for p in result.output["phrases"]:
        hit = leaked(p["phrase"], ids)
        if hit is None:
            kept.append({"phrase": p["phrase"].strip(), "category": p["category"]})
        else:
            rejected.append(hit)
    return kept, rejected


# ---------- warehouse ----------

def insert_unless_duplicate(conn: psycopg.Connection, table: str, **values: Any) -> dict[str, Any] | None:
    """Insert and let the unique constraint decide: a duplicate rolls back to a savepoint and returns None."""
    try:
        with conn.transaction():
            return insert(conn, table, **values)
    except psycopg.errors.UniqueViolation:
        return None


COUNT_KEYS = ("sources_vault", "sources_public", "sources_failed", "source_retries", "raw_ingest_inserted",
              "raw_ingest_duplicates", "phrases_extracted", "phrases_inserted", "phrases_duplicates",
              "phrases_rejected_identifiers")


def ingest(conn: psycopg.Connection, r: Run, client_id: UUID, icp_id: UUID | None, src: Source,
           model: Model, prompts: tuple[str, str]) -> dict[str, int]:
    """raw_ingest row, model extraction, voc_phrases rows; committed per source so a later failure keeps it."""
    raw = insert_unless_duplicate(conn, "raw_ingest", source=src.source, client_id=client_id, external_id=src.ref,
                                  dedup_key=src.dedup_key, trust_tier=src.trust_tier, fetched_at=src.fetched_at,
                                  purge_after=src.purge_after, payload=src.payload)
    r.count("raw_ingest_inserted" if raw else "raw_ingest_duplicates")
    kept, rejected = extract(model, src, prompts, r)
    stats = {"extracted": len(kept) + len(rejected), "inserted": 0, "duplicates": 0, "rejected": len(rejected)}
    r.count("phrases_extracted", stats["extracted"])
    r.count("phrases_rejected_identifiers", len(rejected))
    for hit in rejected:
        print(f"pull_voc: {src.ref}: rejected a phrase that still contained {hit!r}", file=sys.stderr)
    for p in kept:
        row = insert_unless_duplicate(
            conn, "voc_phrases", client_id=client_id, icp_id=icp_id, phrase=p["phrase"],
            phrase_normalised=normalise(p["phrase"]), category=p["category"], source=src.source, source_ref=src.ref,
            source_weight=src.source_weight, trust_tier=src.trust_tier, visibility=src.visibility,
        )
        stats["inserted" if row else "duplicates"] += 1
    r.count("phrases_inserted", stats["inserted"])
    r.count("phrases_duplicates", stats["duplicates"])
    conn.commit()
    return stats


def load_config(slug: str) -> dict[str, Any]:
    return json.loads((ME_DIR / "config" / "clients" / f"{slug}.json").read_text())


def check_config(config: dict[str, Any]) -> None:
    for path in REQUIRED_CONFIG:
        node: Any = config
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if node is None:
            raise ConfigMissing(f"config is missing {'.'.join(path)}")
    if not isinstance(config.get("voc"), dict) or not config["voc"].get("seed_dir"):
        raise ConfigMissing("config is missing voc.seed_dir")


def paused(client: dict[str, Any]) -> bool:
    return bool(client.get("paused")) or os.environ.get("PIPELINE_PAUSED", "").strip().lower() in ("1", "true", "yes")


def pull_voc(conn: psycopg.Connection, r: Run, config: dict[str, Any], client: dict[str, Any],
             model: Model, threads: PublicThreads) -> list[tuple[str, dict[str, int]]]:
    for key in COUNT_KEYS:
        r.count(key, 0)
    icp = conn.execute("select id from icps where client_id = %s limit 1", (client["id"],)).fetchone()
    icp_id = icp["id"] if icp else None
    prompts = load_prompts()
    seed_dir = Path(config["voc"]["seed_dir"])
    if not seed_dir.is_absolute():
        seed_dir = ME_DIR / seed_dir
    vault = vault_sources(seed_dir)
    r.count("sources_vault", len(vault))
    public, failed = public_sources(list(config["voc"].get("public_sources") or []), threads, r)
    r.count("sources_public", len(public))
    summary: list[tuple[str, dict[str, int]]] = []
    for src in vault + public:
        summary.append((src.ref, ingest(conn, r, client["id"], icp_id, src, model, prompts)))
    if failed:
        raise SourceFailed(f"{len(failed)} public source(s) failed twice: {', '.join(failed)}; the other sources were committed")
    return summary


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="pull voc: vault seed notes + public threads -> voc_phrases")
    parser.add_argument("--client", default="upclicklabs", help="client slug (config/clients/<slug>.json)")
    args = parser.parse_args(argv)
    load_env()
    config = load_config(args.client)
    summary: list[tuple[str, dict[str, int]]] = []
    r: Run | None = None
    with connect("worker", job="pull voc") as conn:
        client = client_by_slug(conn, args.client)
        try:
            with run(conn, WORKER, client["id"] if client else None) as r:
                if client is None:
                    raise ClientMissing(f"no clients row for slug {args.client!r}; run scripts/dev_db.sh --seed")
                print(format_where_are_we(where_are_we(conn, args.client)))
                check_config(config)
                if paused(client):
                    raise PipelinePaused("pipeline paused (clients.paused or PIPELINE_PAUSED); pull voc refused")
                summary = pull_voc(conn, r, config, client, get_model(), get_voc())
        except (PipelinePaused, ConfigMissing, ClientMissing) as exc:
            print(f"pull_voc: refused: {exc} (runs row {r.id} closed as failed)", file=sys.stderr)
            return 2
        except SourceFailed as exc:
            print(f"pull_voc: run {r.id} FAILED: {exc}", file=sys.stderr)
            return 1
    assert r is not None
    print("\nsource_ref                                                     extracted inserted duplicates rejected")
    for ref, s in summary:
        print(f"{ref[:62].ljust(62)} {s['extracted']:>9} {s['inserted']:>8} {s['duplicates']:>10} {s['rejected']:>8}")
    print(f"\npull_voc: run {r.id} ok; counts {json.dumps(r.counts, sort_keys=True)}; api_calls {r.api_calls}; tokens {r.tokens_used}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
