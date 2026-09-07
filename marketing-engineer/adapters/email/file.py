"""File email: one RFC 5322 .eml per send under DEV_ROOT/outbox; golden-file tests read it back."""
from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path


class FileEmail:
    def __init__(self, outbox: Path):
        self.outbox = outbox

    def send(self, *, to, subject, text, html=None, from_addr=None):
        msg = EmailMessage()
        msg["From"] = from_addr or "pipeline@dev.local"
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain="dev.local")
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        self.outbox.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        local_part = msg["Message-ID"].strip("<>").split("@")[0]
        with open(self.outbox / f"{stamp}-{local_part}.eml", "xb") as f:
            f.write(bytes(msg))
        return msg["Message-ID"]
