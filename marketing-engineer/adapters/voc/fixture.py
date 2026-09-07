"""Fixture threads: every fixtures/voc/*.json is one thread in the normalised shape, matched by its `url`."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FixtureThreads:
    def __init__(self, fixture_dir: str | Path):
        self.fixture_dir = Path(fixture_dir)
        self._by_url: dict[str, dict[str, Any]] | None = None

    def _index(self) -> dict[str, dict[str, Any]]:
        if self._by_url is None:
            self._by_url = {}
            for path in sorted(self.fixture_dir.glob("*.json")):
                thread = json.loads(path.read_text())
                self._by_url[thread["url"]] = normalise(thread)
        return self._by_url

    def fetch_thread(self, url: str) -> dict[str, Any]:
        thread = self._index().get(url)
        if thread is None:
            raise FileNotFoundError(
                f"no voc fixture thread for the configured URL ({len(self._index())} fixtures in {self.fixture_dir}); "
                "the fixture backend never fetches the network: add a fixture or set VOC_BACKEND=reddit (T13)")
        return thread


def normalise(thread: dict[str, Any]) -> dict[str, Any]:
    """Our shape, strictly: url, title, comments[{id, text, score}]. Anything else (authors above all) is dropped."""
    return {
        "url": thread["url"],
        "title": str(thread.get("title") or ""),
        "comments": [
            {"id": str(c["id"]), "text": str(c["text"]), "score": int(c.get("score") or 0)}
            for c in thread.get("comments") or []
        ],
    }
