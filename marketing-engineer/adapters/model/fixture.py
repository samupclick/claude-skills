"""Fixture model: replays fixtures/model/<task>.json. A file holds one object, or {"outputs": [...]} replayed in order."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adapters.model import ModelOutputInvalid, ModelResult, build_user, validate


class FixtureModel:
    def __init__(self, fixture_dir: str | Path):
        self.fixture_dir = Path(fixture_dir)
        self.last_prompt: dict[str, str] = {}
        self.last_images = 0
        self._cursor: dict[str, int] = {}

    def generate_json(self, *, task, system, instructions, untrusted, schema, max_tokens=4096, images=None):
        self.last_prompt = {"system": system, "user": build_user(instructions, untrusted)}
        self.last_images = len(images or [])
        path = self.fixture_dir / f"{task}.json"
        if not path.exists():
            raise FileNotFoundError(f"model fixture {path} not found; record one or set MODEL_BACKEND=claude")
        payload = json.loads(path.read_text())
        if isinstance(payload, dict) and "outputs" in payload:
            outputs = payload["outputs"]
            if not outputs:
                raise ModelOutputInvalid(f"{task}: fixture {path} has no outputs")
            i = self._cursor.get(task, 0)
            self._cursor[task] = i + 1
            output = outputs[i % len(outputs)]
        else:
            output = payload
        return ModelResult(output=validate(task, output, schema), tokens_used=0, backend="fixture")
