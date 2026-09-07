"""Outbound email (check-in only). EMAIL_BACKEND=file|gmail. `send(...) -> Message-ID`."""
from __future__ import annotations

from typing import Protocol

from adapters.env import choose_backend, dev_root, not_built


class Email(Protocol):
    def send(self, *, to: str, subject: str, text: str, html: str | None = None, from_addr: str | None = None) -> str: ...


def get_email() -> Email:
    from adapters.email.file import FileEmail

    return choose_backend("EMAIL_BACKEND", {
        "file": lambda: FileEmail(dev_root() / "outbox"),
        "gmail": not_built("EMAIL_BACKEND", "gmail", "T13"),
    })
