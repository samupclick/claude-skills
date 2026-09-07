"""Public VOC threads (Reddit, later Quora and review sites). VOC_BACKEND=fixture|reddit.

`fetch_thread(url)` returns one normalised thread: `url`, `title`, `comments` (list of `{id, text, score}`).
There is no author field anywhere in the shape, by design (CRUCIBLE A13): the worker never needs usernames
and the row it writes to `raw_ingest` must not carry them. The fixture backend reads `fixtures/voc/*.json`
(SYNTHETIC threads) and never touches the network; the live backend lands in T13 and normalises Reddit's
JSON into this same shape, here and only here.
"""
from __future__ import annotations

import hashlib
from typing import Any, Protocol

from adapters.env import ME_DIR, choose_backend, not_built

FIXTURE_DIR = ME_DIR / "fixtures" / "voc"


class PublicThreads(Protocol):
    def fetch_thread(self, url: str) -> dict[str, Any]: ...


def url_ref(url: str) -> str:
    """The pointer stored for a public source (FR-11: hashed URL, never the URL). Stable across runs."""
    return "sha256:" + hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:32]


def source_name(url: str) -> str:
    """`voc_phrases.source` for a public URL: reddit | quora | g2 | clutch | linkedin | x | public."""
    host = url.lower()
    for key, name in (("reddit.", "reddit"), ("quora.", "quora"), ("g2.", "g2"), ("clutch.", "clutch"),
                      ("linkedin.", "linkedin"), ("x.com", "x"), ("twitter.", "x")):
        if key in host:
            return name
    return "public"


def get_voc() -> PublicThreads:
    import os

    from adapters.voc.fixture import FixtureThreads

    return choose_backend("VOC_BACKEND", {
        "fixture": lambda: FixtureThreads(os.environ.get("VOC_FIXTURE_DIR") or FIXTURE_DIR),
        "reddit": not_built("VOC_BACKEND", "reddit", "T13"),
    })
