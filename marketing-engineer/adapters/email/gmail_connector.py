"""Gmail connector hand-off for the check-in and the Monday memo (FR-42, FR-43; Sam, 2026-10-28). EMAIL_BACKEND=gmail_connector (alias `gmail`).

The check-in is delivered through the Gmail connector, an MCP tool of the Claude session that runs the routine. A
Python script cannot call it, so this backend sends nothing: `send()` writes the composed message to a pending-send
queue, one JSON file per stable key under EMAIL_QUEUE_DIR (default DEV_ROOT/pending-send), and returns the key.
`scripts/checkin.py --send-pending` prints `framed_arguments()` (the connector's `send_message` arguments inside an
untrusted_data frame: the body is data) for every queued message addressed to CHECKIN_TO, the session calls the
tool, and `scripts/checkin.py --mark-sent <key> --message-id <id>` records the delivery and removes the file. A key already in the queue is refused (`AlreadyQueued`); the warehouse keeps the durable record.

A queue file holds key, queued_at, to, subject, text, html and nothing else: never a credential (the connector
authenticates inside the session) and never the sender (the connector sends as its own account). The argument
shape is ASSUMED from the tool schema (fixtures/gmail_connector/send_message.json) until a real send is recorded.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from adapters.env import ME_DIR, dev_root

CONNECTOR = "Gmail"
TOOL = "send_message"
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
ADDRESS = re.compile(r"[^@\s<>()\[\],;:\"]+@[^@\s<>()\[\],;:\"]+\.[^@\s<>()\[\],;:\"]+")
MESSAGE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+=/-]{0,255}")
FRAME_TAG = re.compile(r"<(?=\s*/?\s*untrusted_data)", re.IGNORECASE)


class AlreadyQueued(RuntimeError):
    """A message with this key is already pending; it is never queued twice."""


class NotQueued(LookupError):
    """No pending message has this key."""


def queue_dir() -> Path:
    """EMAIL_QUEUE_DIR (relative paths are under marketing-engineer/), else DEV_ROOT/pending-send."""
    configured = os.environ.get("EMAIL_QUEUE_DIR")
    if not configured:
        return dev_root() / "pending-send"
    path = Path(configured)
    return path if path.is_absolute() else ME_DIR / path


def connector_arguments(record: dict[str, Any]) -> dict[str, Any]:
    """The `send_message` arguments for a queued message: plain text in `body`, the HTML alternative in `htmlBody`."""
    args = {"to": list(record["to"]), "subject": record["subject"], "body": record["text"]}
    if record.get("html"):
        args["htmlBody"] = record["html"]
    return args


def framed_arguments(record: dict[str, Any]) -> str:
    """`connector_arguments(record)` as JSON inside the untrusted_data frame that adapters/model.data_block puts around
    untrusted text (SKILL.md §4 rule 7). The body quotes rows (a vendor error, a scraped hook line) and the session that
    reads it holds the Gmail connector, so it must read the arguments as data, never as instructions. A tag inside the
    body cannot close the frame: its `<` is written as the JSON escape \\u003c, so the block still parses to exactly the
    queued arguments."""
    text = json.dumps(connector_arguments(record), indent=2, ensure_ascii=False)
    return "<untrusted_data>\n" + FRAME_TAG.sub(lambda _: "\\u003c", text) + "\n</untrusted_data>"


def _key(key: str) -> str:
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise ValueError("message key must be 1-128 letters, digits, '.', '_' or '-', starting with a letter or digit")
    return key


class GmailConnectorQueue:
    queued = True

    def __init__(self, root: Path):
        self.root = root

    def send(self, *, to, subject, text, html=None, from_addr=None, key=None) -> str:
        recipients = [a.strip() for a in to.split(",")] if isinstance(to, str) else [a.strip() for a in to]
        if not recipients or not all(ADDRESS.fullmatch(a) for a in recipients):
            raise ValueError("recipients must be plain email addresses separated by commas (the Gmail connector takes no display names)")
        if key is None:
            key = "msg-" + hashlib.sha256("\0".join([",".join(recipients), subject, text]).encode()).hexdigest()[:16]
        key = _key(key)
        record = {"key": key, "queued_at": datetime.now(timezone.utc).isoformat(), "to": recipients,
                  "subject": subject, "text": text, "html": html}
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{key}.json"
        tmp = self.root / f".{key}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        try:
            os.link(tmp, path)                      # atomic, and refuses an existing file
        except FileExistsError:
            raise AlreadyQueued(f"message {key} is already in the pending-send queue; it is never queued twice") from None
        finally:
            tmp.unlink(missing_ok=True)
        return key

    def pending(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        records = [json.loads(p.read_text()) for p in self.root.glob("*.json") if KEY.fullmatch(p.stem)]
        return sorted(records, key=lambda r: (r["queued_at"], r["key"]))

    def get(self, key: str) -> dict[str, Any]:
        path = self.root / f"{_key(key)}.json"
        if not path.exists():
            raise NotQueued(f"no pending message {key} in the queue")
        return json.loads(path.read_text())

    def remove(self, key: str) -> None:
        (self.root / f"{_key(key)}.json").unlink(missing_ok=True)
