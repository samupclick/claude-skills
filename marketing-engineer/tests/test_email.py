import json
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

from adapters.env import UnknownBackend
from adapters.email import AlreadyQueued, NotQueued, get_email

ME_DIR = Path(__file__).resolve().parent.parent


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


def test_file_backend_carries_the_message_key_as_a_header(dev_root, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "file")
    mailer = get_email()
    assert mailer.queued is False
    mailer.send(to="sam@example.invalid", subject="s", text="t", key="checkin-acme-2026-10-28")
    msg = BytesParser(policy=policy.default).parsebytes(next((dev_root / "outbox").glob("*.eml")).read_bytes())
    assert msg["X-Message-Key"] == "checkin-acme-2026-10-28"


# ---------- EMAIL_BACKEND=gmail_connector (Sam, 2026-10-28): queue for the routine session's Gmail connector ----------

SECRETS = {"ANTHROPIC_API_KEY": "sk-ant-sentinel-1", "META_ACCESS_TOKEN": "meta-sentinel-2", "GEMINI_API_KEY": "gem-sentinel-3",
           "SUPABASE_STORAGE_PASSWORD": "sb-sentinel-4", "SCRAPECREATORS_API_KEY": "sc-sentinel-5", "CAL_WEBHOOK_SECRET": "cal-sentinel-6"}
FIXTURE = json.loads((ME_DIR / "fixtures" / "gmail_connector" / "send_message.json").read_text())


@pytest.fixture
def queue(dev_root, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "gmail_connector")
    monkeypatch.delenv("EMAIL_QUEUE_DIR", raising=False)
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    return get_email()


def test_connector_backend_queues_one_json_file_per_key_and_returns_the_key(queue, dev_root):
    assert queue.queued is True
    key = queue.send(to="sam@example.invalid, ops@example.invalid", subject="Check-in", text="Part 1\nPart 2",
                     html="<pre>Part 1</pre>", from_addr="ignored@example.invalid", key="checkin-acme-2026-10-28")
    assert key == "checkin-acme-2026-10-28"
    files = list((dev_root / "pending-send").iterdir())
    assert [f.name for f in files] == ["checkin-acme-2026-10-28.json"]
    record = json.loads(files[0].read_text())
    assert set(record) == {"key", "queued_at", "to", "subject", "text", "html"}
    assert record["to"] == ["sam@example.invalid", "ops@example.invalid"] and record["text"] == "Part 1\nPart 2"
    raw = files[0].read_text()
    assert not any(v in raw for v in SECRETS.values()) and "ignored@" not in raw
    assert queue.pending() == [record] and queue.get(key) == record


def test_connector_backend_never_queues_a_key_twice(queue, dev_root):
    queue.send(to="sam@example.invalid", subject="first", text="one", key="checkin-acme-2026-10-28")
    with pytest.raises(AlreadyQueued, match="checkin-acme-2026-10-28"):
        queue.send(to="sam@example.invalid", subject="second", text="two", key="checkin-acme-2026-10-28")
    assert [r["subject"] for r in queue.pending()] == ["first"]
    assert [f.name for f in (dev_root / "pending-send").iterdir()] == ["checkin-acme-2026-10-28.json"]   # no temp file left
    queue.remove("checkin-acme-2026-10-28")
    assert queue.pending() == []
    with pytest.raises(NotQueued, match="checkin-acme-2026-10-28"):
        queue.get("checkin-acme-2026-10-28")


def test_connector_backend_without_a_key_derives_a_stable_one(queue):
    a = queue.send(to="sam@example.invalid", subject="s", text="same body")
    queue.remove(a)
    assert queue.send(to="sam@example.invalid", subject="s", text="same body") == a and a.startswith("msg-")


def test_gmail_alias_and_queue_dir_override(dev_root, monkeypatch, tmp_path):
    monkeypatch.setenv("EMAIL_BACKEND", "gmail")
    monkeypatch.setenv("EMAIL_QUEUE_DIR", str(tmp_path / "q"))
    mailer = get_email()
    assert type(mailer).__name__ == "GmailConnectorQueue"
    mailer.send(to="sam@example.invalid", subject="s", text="t", key="k1")
    assert (tmp_path / "q" / "k1.json").exists() and not (dev_root / "pending-send").exists()


def test_connector_backend_refuses_unsafe_keys_and_display_name_recipients(queue):
    for bad in ("../escape", "a/b", ".hidden", ""):
        with pytest.raises(ValueError, match="key"):
            queue.send(to="sam@example.invalid", subject="s", text="t", key=bad)
    with pytest.raises(ValueError, match="plain email addresses"):
        queue.send(to="Sam <sam@example.invalid>", subject="s", text="t", key="k2")
    assert queue.pending() == []


def test_connector_arguments_match_the_send_message_contract(queue):
    """Contract against fixtures/gmail_connector/send_message.json (ASSUMED SHAPE, see its _shape note): the arguments
    the session passes are tool parameters with the documented types, and the tool's returned `id` is a valid
    `--message-id` for scripts/checkin.py --mark-sent."""
    from adapters.email.gmail_connector import CONNECTOR, MESSAGE_ID, TOOL, connector_arguments

    assert FIXTURE["_shape"].startswith("ASSUMED SHAPE") and (FIXTURE["connector"], FIXTURE["tool"]) == (CONNECTOR, TOOL)
    a = FIXTURE["arguments"]
    key = queue.send(to=",".join(a["to"]), subject=a["subject"], text=a["body"], html=a["htmlBody"], key="checkin-upclicklabs-2026-10-28")
    args = connector_arguments(queue.get(key))
    assert args == a and set(args) <= set(FIXTURE["parameters"])
    assert all(isinstance(x, str) for x in args["to"]) and all(isinstance(args[k], str) for k in ("subject", "body", "htmlBody"))
    queue.remove(key)
    key = queue.send(to="sam@example.invalid", subject="s", text="plain only", key="k3")
    assert connector_arguments(queue.get(key)) == {"to": ["sam@example.invalid"], "subject": "s", "body": "plain only"}
    assert MESSAGE_ID.fullmatch(FIXTURE["result"]["id"])
    for bad in ("", "<id>", "two words", "x" * 300):
        assert not MESSAGE_ID.fullmatch(bad)
