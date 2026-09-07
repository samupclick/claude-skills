"""VOC_BACKEND=fixture: public threads come from fixtures/voc/*.json, never the network, never with authors."""
import json

import pytest

from adapters.voc import FIXTURE_DIR, get_voc, source_name, url_ref
from tests.conftest import ME_DIR

CONFIG = json.loads((ME_DIR / "config" / "clients" / "upclicklabs.json").read_text())


@pytest.fixture
def threads(monkeypatch):
    monkeypatch.setenv("VOC_BACKEND", "fixture")
    monkeypatch.delenv("VOC_FIXTURE_DIR", raising=False)
    return get_voc()


def test_every_configured_public_source_has_a_fixture_thread(threads):
    urls = CONFIG["voc"]["public_sources"]
    assert 2 <= len(urls) <= 3, "T3 deliverable: 2–3 thread URLs from config"
    for url in urls:
        t = threads.fetch_thread(url)
        assert t["url"] == url and t["title"] and len(t["comments"]) >= 3
        for c in t["comments"]:
            assert set(c) == {"id", "text", "score"}, "no author field, by design (A13)"


def test_fixture_files_are_marked_synthetic():
    assert "SYNTHETIC" in (FIXTURE_DIR / "README.md").read_text()
    for f in FIXTURE_DIR.glob("*.json"):
        payload = json.loads(f.read_text())
        assert "synthetic" in payload["_shape"].lower(), f
        assert not any("author" in c for c in payload["comments"]), f


def test_unknown_url_is_an_error_that_never_prints_the_url(threads):
    with pytest.raises(FileNotFoundError) as exc:
        threads.fetch_thread("https://www.reddit.com/r/nowhere/comments/abc/secret-thread/")
    assert "secret-thread" not in str(exc.value)
    assert "T13" in str(exc.value)


def test_live_backend_lands_in_t13(monkeypatch):
    monkeypatch.setenv("VOC_BACKEND", "reddit")
    with pytest.raises(NotImplementedError, match="T13"):
        get_voc()


def test_url_ref_is_a_stable_hash_without_the_url():
    url = "https://www.reddit.com/r/marketing/comments/xyz/some-thread/"
    ref = url_ref(url)
    assert ref == url_ref(url) and ref.startswith("sha256:") and "reddit" not in ref and "xyz" not in ref
    assert url_ref(url + " ") == ref


def test_source_name_from_host():
    assert source_name("https://www.reddit.com/r/x/") == "reddit"
    assert source_name("https://www.quora.com/q") == "quora"
    assert source_name("https://example.org/forum") == "public"
