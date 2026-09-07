"""Object storage: `put(bytes, key) -> url`, `get(url) -> bytes`. STORAGE_BACKEND=local|supabase."""
from __future__ import annotations

from typing import Protocol

from adapters.env import choose_backend, dev_root, not_built


class Storage(Protocol):
    def put(self, data: bytes, key: str) -> str: ...
    def get(self, url: str) -> bytes: ...


def get_storage() -> Storage:
    from adapters.storage.local import LocalStorage

    return choose_backend("STORAGE_BACKEND", {
        "local": lambda: LocalStorage(dev_root() / "storage"),
        "supabase": not_built("STORAGE_BACKEND", "supabase", "T13"),
    })
