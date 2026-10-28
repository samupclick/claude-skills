"""The Meta Graph API host and version, shared by the Marketing API adapter (adapters/meta/live.py) and the
Conversions API adapter (adapters/capi/live.py), so both send to the same `META_API_VERSION`.

Default v26.0: the Marketing API version table lists v26.0 released 2026-07-29 (expiry TBD), v25.0 until 2027-02-23
and v24.0 until 2026-11-10 (developers.facebook.com, read 2026-10-28). The Conversions API is served by the same
Graph API versions. Override with META_API_VERSION (`vNN.N`).
"""
from __future__ import annotations

import os
import re

GRAPH_HOST = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v26.0"
_VERSION = re.compile(r"v\d+\.\d+")


def is_api_version(value: str | None) -> bool:
    """True for a Graph API version as it appears in the URL path (`v26.0`)."""
    return bool(_VERSION.fullmatch(value or ""))


def env_api_version() -> str:
    """META_API_VERSION when set, else DEFAULT_API_VERSION. The adapters validate it with `is_api_version`."""
    return os.environ.get("META_API_VERSION") or DEFAULT_API_VERSION


def base_url(api_version: str) -> str:
    return f"{GRAPH_HOST}/{api_version}/"
