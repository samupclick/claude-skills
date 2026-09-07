"""Fake CAPI: appends one JSON line per event to DEV_ROOT/capi.jsonl so dedup tests can read event_id back."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class FakeCapi:
    def __init__(self, path: Path):
        self.path = path

    def send(self, *, event_name, event_id, event_time, event_source_url=None, action_source="website",
             user_data=None, custom_data=None, test_event_code=None):
        record = {"event_name": event_name, "event_id": event_id, "event_time": int(event_time),
                  "event_source_url": event_source_url, "action_source": action_source,
                  "user_data": user_data or {}, "custom_data": custom_data or {}, "test_event_code": test_event_code,
                  "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(record) + "\n")
        return {"events_received": 1, "fbtrace_id": "dev", "event_id": event_id}

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def seen(self, event_id: str) -> bool:
        return any(e["event_id"] == event_id for e in self.events())
