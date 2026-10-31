import pytest

from adapters.env import UnknownBackend
from adapters.storage import get_storage


def test_local_put_get_round_trip_under_dev_root(dev_root, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    storage = get_storage()
    url = storage.put(b"\x89PNG fake bytes", "creatives/abc/1080.png")
    assert url.startswith("file://")
    assert (dev_root / "storage" / "creatives" / "abc" / "1080.png").read_bytes() == b"\x89PNG fake bytes"
    assert storage.get(url) == b"\x89PNG fake bytes"


def test_local_rejects_path_escape_on_put_and_get(dev_root, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    with pytest.raises(ValueError):
        get_storage().put(b"x", "../outside.png")
    with pytest.raises(ValueError):
        get_storage().get("file:///etc/hostname")


def test_unknown_backend_names_variable(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    with pytest.raises(UnknownBackend, match="STORAGE_BACKEND"):
        get_storage()
