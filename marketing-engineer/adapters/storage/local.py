"""Local storage: files under DEV_ROOT/storage, `file://` URLs."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, key: str) -> str:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"storage key escapes the storage root: {key!r}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path.as_uri()

    def get(self, url: str) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme != "file":
            raise ValueError(f"local storage only serves file:// URLs, got {parsed.scheme}://")
        path = Path(url2pathname(parsed.path)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("local storage only serves URLs under its own root")
        return path.read_bytes()
