from email import policy
from email.parser import BytesParser

import pytest

from adapters.env import UnknownBackend
from adapters.email import get_email


def test_file_backend_writes_eml_to_outbox(dev_root, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "file")
    mailer = get_email()
    msg_id = mailer.send(to="sam@example.invalid", subject="Check-in Monday", text="Part 1\nPart 2", html="<p>Part 1</p>")
    files = list((dev_root / "outbox").glob("*.eml"))
    assert len(files) == 1
    msg = BytesParser(policy=policy.default).parsebytes(files[0].read_bytes())
    assert msg["To"] == "sam@example.invalid" and msg["Subject"] == "Check-in Monday"
    assert msg["Message-ID"] == msg_id
    assert msg.get_body(preferencelist=("plain",)).get_content().strip() == "Part 1\nPart 2"
    assert "<p>Part 1</p>" in msg.get_body(preferencelist=("html",)).get_content()


def test_unknown_backend_names_variable(monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")
    with pytest.raises(UnknownBackend, match="EMAIL_BACKEND"):
        get_email()
