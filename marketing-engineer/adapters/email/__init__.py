"""Outbound email (the check-in, FR-42, and the Monday memo, FR-43). EMAIL_BACKEND=file|gmail_connector (`gmail` is an alias of gmail_connector).

`send(..., key=None) -> str`. `file` writes an .eml under DEV_ROOT/outbox and returns its Message-ID (`queued = False`).
`gmail_connector` queues the composed message for the routine session's Gmail connector and returns the key
(`queued = True`); `scripts/checkin.py --send-pending` / `--mark-sent` finish the delivery (adapters/email/gmail_connector.py).
"""
from __future__ import annotations

from typing import Protocol

from adapters.email.gmail_connector import CONNECTOR, MESSAGE_ID, TOOL, AlreadyQueued, NotQueued, connector_arguments, framed_arguments  # noqa: F401
from adapters.env import choose_backend, dev_root


class Email(Protocol):
    queued: bool

    def send(self, *, to: str, subject: str, text: str, html: str | None = None, from_addr: str | None = None,
             key: str | None = None) -> str: ...


def get_email() -> Email:
    from adapters.email.file import FileEmail
    from adapters.email.gmail_connector import GmailConnectorQueue, queue_dir

    def connector() -> GmailConnectorQueue:
        return GmailConnectorQueue(queue_dir())

    return choose_backend("EMAIL_BACKEND", {
        "file": lambda: FileEmail(dev_root() / "outbox"),
        "gmail_connector": connector,
        "gmail": connector,
    })
