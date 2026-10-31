"""Object storage: `put(bytes, key) -> url`, `get(url) -> bytes`. STORAGE_BACKEND=local|supabase."""
from __future__ import annotations

from typing import Protocol

from adapters.env import choose_backend, dev_root


class Storage(Protocol):
    def put(self, data: bytes, key: str) -> str: ...
    def get(self, url: str) -> bytes: ...


def get_storage() -> Storage:
    from adapters.storage.local import LocalStorage
    from adapters.storage.supabase import SupabaseStorage

    return choose_backend("STORAGE_BACKEND", {
        "local": lambda: LocalStorage(dev_root() / "storage"),
        "supabase": SupabaseStorage.from_env,
    })
