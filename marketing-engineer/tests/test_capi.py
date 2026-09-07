import json

import pytest

from adapters.capi import get_capi, hash_user_field


def test_fake_records_event_id_to_jsonl(dev_root, monkeypatch):
    monkeypatch.setenv("CAPI_BACKEND", "fake")
    capi = get_capi()
    res = capi.send(event_name="QuizStart", event_id="lead-1:QuizStart", event_time=1_757_000_000,
                    event_source_url="http://localhost:8788/quiz", action_source="website",
                    user_data={"em": hash_user_field(" Person@Example.com ")}, custom_data={"utm_content": "c1"})
    assert res["events_received"] == 1
    lines = (dev_root / "capi.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["event_id"] == "lead-1:QuizStart" and rec["event_name"] == "QuizStart"
    assert rec["user_data"]["em"] == hash_user_field("person@example.com")
    assert capi.seen("lead-1:QuizStart") and not capi.seen("lead-2:QuizStart")
    capi.send(event_name="QuizStart", event_id="lead-1:QuizStart", event_time=1_757_000_001)
    assert [e["event_id"] for e in capi.events()] == ["lead-1:QuizStart", "lead-1:QuizStart"]


def test_hash_user_field_normalises_then_sha256():
    assert hash_user_field(" A@B.com") == hash_user_field("a@b.com")
    assert len(hash_user_field("a@b.com")) == 64
