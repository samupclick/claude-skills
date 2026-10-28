"""STORAGE_BACKEND=supabase (FR-5, FR-25, NFR-1) against httpx.MockTransport serving fixtures/supabase/ (ASSUMED SHAPE,
not live-verified): the writer signs in as a dedicated Auth user, uploads with x-upsert, returns the public object URL
the gate and Meta read; reads go to that URL without credentials; errors name variables and statuses, never values."""
from __future__ import annotations

import json
import re
from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from adapters.env import MissingEnvVar
from adapters.storage import get_storage
from adapters.storage.supabase import SupabaseStorage, SupabaseStorageError, content_type

ME_DIR = Path(__file__).resolve().parent.parent
FIXTURES = ME_DIR / "fixtures" / "supabase"
BASE = "https://proj-ref.supabase.co"
API_KEY = "sb_publishable_fixture-key-value"
EMAIL = "storage-writer@example.invalid"
PASSWORD = "fixture-password-value-not-real"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
HTML = b"<!doctype html>\n<html><body><p>FIXTURE words</p></body></html>"
CREATIVE_KEY = "creatives/upclicklabs/batch-001/00000000-0000-4000-8000-000000000001"


def fixture(name: str) -> dict:
    body = json.loads((FIXTURES / name).read_text())
    return {k: v for k, v in body.items() if not k.startswith("_")}


class FakeSupabase:
    """The two Supabase endpoints the adapter uses, shaped by the fixtures. Holds objects in memory; refuses an upload
    whose bearer token is not the one it issued, the way RLS refuses an unknown user."""

    def __init__(self):
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.requests: list[httpx.Request] = []
        self.tokens = {"password": fixture("auth_token_password.json"), "refresh_token": fixture("auth_token_refresh.json")}
        self.valid_tokens = {t["access_token"] for t in self.tokens.values()}
        self.reject_password = False
        self.rls_refuses = False
        self.fail_next: list[int] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_next:
            return httpx.Response(self.fail_next.pop(0), text="upstream unavailable")
        path = request.url.path
        if path == "/auth/v1/token":
            return self.token(request)
        m = re.fullmatch(r"/storage/v1/object/public/([^/]+)/(.+)", path)
        if m and request.method == "GET":
            stored = self.objects.get((m.group(1), m.group(2)))
            if stored is None:
                return httpx.Response(400, json=fixture("storage_error_not_found.json"))
            return httpx.Response(200, content=stored[0], headers={"content-type": stored[1]})
        m = re.fullmatch(r"/storage/v1/object/([^/]+)/(.+)", path)
        if m and request.method == "POST":
            return self.upload(request, m.group(1), m.group(2))
        return httpx.Response(404, json={"statusCode": "404", "error": "not_found", "message": "no route"})

    def token(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["apikey"] == API_KEY
        grant = parse_qs(urlsplit(str(request.url)).query)["grant_type"][0]
        body = json.loads(request.content)
        if grant == "password":
            if self.reject_password or body != {"email": EMAIL, "password": PASSWORD}:
                return httpx.Response(400, json=fixture("auth_error_invalid_credentials.json"))
        elif grant == "refresh_token":
            assert body == {"refresh_token": self.tokens["password"]["refresh_token"]}
        return httpx.Response(200, json=self.tokens[grant])

    def upload(self, request: httpx.Request, bucket: str, key: str) -> httpx.Response:
        assert request.headers["apikey"] == API_KEY
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if self.rls_refuses or token not in self.valid_tokens:
            return httpx.Response(400, json=fixture("storage_error_rls.json"))
        if (bucket, key) in self.objects and request.headers.get("x-upsert") != "true":
            return httpx.Response(400, json={"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"})
        msg = BytesParser(policy=email_policy).parsebytes(
            b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.content)
        parts = {p.get_param("name", header="content-disposition"): p for p in msg.iter_parts()}
        file_part = parts["file"]
        self.objects[(bucket, key)] = (file_part.get_payload(decode=True), file_part.get_content_type())
        self.last_upload = {"filename": file_part.get_filename(), "content_type": file_part.get_content_type(),
                            "cache_control": parts["cacheControl"].get_payload(), "upsert": request.headers.get("x-upsert")}
        return httpx.Response(200, json={**fixture("storage_upload.json"), "Key": f"{bucket}/{key}"})


class Clock:
    def __init__(self, now: float = 1_793_181_600.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def server():
    return FakeSupabase()


def make(server, **kw) -> SupabaseStorage:
    opts = dict(api_key=API_KEY, email=EMAIL, password=PASSWORD, client=httpx.Client(transport=httpx.MockTransport(server)),
                sleep=lambda s: None)
    opts.update(kw)
    return SupabaseStorage(BASE, "creatives", **opts)


def leaked(text: str) -> list[str]:
    return [s for s in (API_KEY, PASSWORD, "fixture-access-token-1", "fixture-refresh-token-1") if s in text]


def test_put_signs_in_once_uploads_with_upsert_and_returns_the_public_url(server):
    storage = make(server)
    url = storage.put(PNG, f"{CREATIVE_KEY}/1080x1080.png")
    assert url == f"{BASE}/storage/v1/object/public/creatives/{CREATIVE_KEY}/1080x1080.png"
    token, upload = server.requests
    assert token.method == "POST" and token.url.path == "/auth/v1/token" and token.url.params["grant_type"] == "password"
    assert upload.method == "POST" and upload.url.path == f"/storage/v1/object/creatives/{CREATIVE_KEY}/1080x1080.png"
    assert upload.headers["authorization"] == "Bearer fixture-access-token-1"
    assert server.last_upload == {"filename": "1080x1080.png", "content_type": "image/png", "cache_control": "3600", "upsert": "true"}
    assert server.objects[("creatives", f"{CREATIVE_KEY}/1080x1080.png")][0] == PNG
    storage.put(HTML, f"{CREATIVE_KEY}/1080x1080.html")
    assert [r.url.path for r in server.requests].count("/auth/v1/token") == 1


def test_put_on_the_same_key_is_idempotent(server):
    storage = make(server)
    first = storage.put(PNG, "inspo/ag1/123/0.png")
    second = storage.put(PNG + b"v2", "inspo/ag1/123/0.png")
    assert first == second
    assert server.objects[("creatives", "inspo/ag1/123/0.png")][0] == PNG + b"v2"
    uploads = [r for r in server.requests if r.url.path.startswith("/storage/")]
    assert len(uploads) == 2 and all(r.headers["x-upsert"] == "true" for r in uploads)


def test_content_type_comes_from_the_bytes_then_the_key():
    assert content_type(PNG, "x.bin") == "image/png"
    assert content_type(JPEG, "x.png") == "image/jpeg"
    assert content_type(b"GIF89a....", "x") == "image/gif"
    assert content_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ", "x") == "image/webp"
    assert content_type(b"\xef\xbb\xbf  <!DOCTYPE HTML><html></html>", "x.png") == "text/html; charset=utf-8"
    assert content_type(b"<html><body>hi</body></html>", "x") == "text/html; charset=utf-8"
    assert content_type(b"{}", "notes.json") == "application/json"
    assert content_type(b"\x00\x01opaque", "blob") == "application/octet-stream"


def test_get_reads_the_public_url_without_credentials(server):
    storage = make(server)
    url = storage.put(JPEG, "inspo/ridge/9/1.png")
    assert storage.get(url) == JPEG
    read = server.requests[-1]
    assert read.method == "GET" and str(read.url) == url
    assert "authorization" not in read.headers and "apikey" not in read.headers


def test_reader_needs_no_writer_credentials(server):
    server.objects[("creatives", "inspo/ridge/9/1.png")] = (PNG, "image/png")
    reader = make(server, api_key=None, email=None, password=None)
    assert reader.get(f"{BASE}/storage/v1/object/public/creatives/inspo/ridge/9/1.png") == PNG
    with pytest.raises(MissingEnvVar) as exc:
        reader.put(PNG, "inspo/ridge/9/2.png")
    for var in ("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_STORAGE_EMAIL", "SUPABASE_STORAGE_PASSWORD"):
        assert var in str(exc.value)
    assert len(server.requests) == 1


def test_gate_sibling_urls_resolve_to_the_objects_the_producer_wrote(server):
    """scripts/gate.py derives `1080x1080.html` and `image.png` from the stored asset URL by regex (T5/T6 convention), so
    the URL must end in the key with no query string: the reason the bucket is public rather than signed."""
    storage = make(server)
    asset = storage.put(PNG, f"{CREATIVE_KEY}/1080x1080.png")
    html = storage.put(HTML, f"{CREATIVE_KEY}/1080x1080.html")
    image = storage.put(JPEG, f"{CREATIVE_KEY}/image.png")
    assert re.sub(r"\.png$", ".html", asset) == html
    assert re.sub(r"/1080x1080\.png$", "/image.png", asset) == image
    assert storage.get(re.sub(r"\.png$", ".html", asset)) == HTML
    assert server.objects[("creatives", f"{CREATIVE_KEY}/1080x1080.html")][1] == "text/html"


@pytest.mark.parametrize("url", [
    "https://evil.example/storage/v1/object/public/creatives/inspo/a.png",
    f"{BASE}/storage/v1/object/public/other-bucket/inspo/a.png",
    f"{BASE}/storage/v1/object/sign/creatives/inspo/a.png?token=abc",
    f"{BASE}/storage/v1/object/public/creatives/inspo/a.png?download=1",
    f"{BASE}/storage/v1/object/public/creatives/inspo/../../secret.png",
    "file:///etc/hostname",
])
def test_get_refuses_urls_outside_its_bucket(server, url):
    with pytest.raises(ValueError):
        make(server).get(url)
    assert server.requests == []


@pytest.mark.parametrize("key", ["", "/abs.png", "a/../b.png", "a//b.png", "./a.png", "a\\b.png", "a/b\n.png"])
def test_unsafe_keys_are_refused_before_any_request(server, key):
    with pytest.raises(ValueError):
        make(server).put(PNG, key)
    assert server.requests == []


def test_rls_refusal_names_the_key_and_vendor_message_never_a_secret(server):
    server.rls_refuses = True
    with pytest.raises(SupabaseStorageError) as exc:
        make(server).put(PNG, "inspo/ag1/1/0.png")
    text = str(exc.value)
    assert "inspo/ag1/1/0.png" in text and "row-level security" in text and "403" in text and "HTTP 400" in text
    assert leaked(text) == []


def test_bad_credentials_name_the_variables_never_the_values(server):
    server.reject_password = True
    with pytest.raises(SupabaseStorageError) as exc:
        make(server).put(PNG, "inspo/ag1/1/0.png")
    text = str(exc.value)
    assert "SUPABASE_STORAGE_EMAIL" in text and "SUPABASE_STORAGE_PASSWORD" in text and "invalid_credentials" in text
    assert EMAIL not in text and leaked(text) == []
    assert not any(r.url.path.startswith("/storage/") for r in server.requests)


def test_expired_session_is_refreshed_before_the_next_upload(server):
    clock = Clock()
    storage = make(server, clock=clock)
    storage.put(PNG, "inspo/a/1/0.png")
    clock.now += 3600
    storage.put(PNG, "inspo/a/1/1.png")
    grants = [r.url.params["grant_type"] for r in server.requests if r.url.path == "/auth/v1/token"]
    assert grants == ["password", "refresh_token"]
    assert server.requests[-1].headers["authorization"] == "Bearer fixture-access-token-2"


def test_rejected_token_signs_in_again_once(server):
    storage = make(server)
    storage.put(PNG, "inspo/a/1/0.png")
    server.valid_tokens = {"fixture-access-token-2"}
    storage.put(PNG, "inspo/a/1/1.png")
    paths = [(r.url.path, r.url.params.get("grant_type")) for r in server.requests]
    assert paths[-3:] == [("/storage/v1/object/creatives/inspo/a/1/1.png", None), ("/auth/v1/token", "refresh_token"),
                          ("/storage/v1/object/creatives/inspo/a/1/1.png", None)]


def test_transient_upstream_error_is_retried_once_then_raised(server):
    storage = make(server)
    server.fail_next = [503]
    assert storage.put(PNG, "inspo/a/1/0.png").endswith("/inspo/a/1/0.png")
    server.fail_next = [502, 504]
    with pytest.raises(SupabaseStorageError, match="HTTP 504"):
        storage.get(f"{BASE}/storage/v1/object/public/creatives/inspo/a/1/0.png")


def test_missing_object_is_an_error_naming_the_key(server):
    with pytest.raises(SupabaseStorageError, match="inspo/none.png.*Object not found"):
        make(server).get(f"{BASE}/storage/v1/object/public/creatives/inspo/none.png")


def test_upload_answer_for_another_key_is_a_contract_error(server):
    original = server.upload

    def wrong_key(request, bucket, key):
        original(request, bucket, key)
        return httpx.Response(200, json={**fixture("storage_upload.json"), "Key": "creatives/elsewhere.png"})

    server.upload = wrong_key
    with pytest.raises(SupabaseStorageError, match="Key"):
        make(server).put(PNG, "inspo/a/1/0.png")


def test_get_storage_selects_supabase_from_env(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(MissingEnvVar, match="SUPABASE_URL"):
        get_storage()
    monkeypatch.setenv("SUPABASE_URL", BASE + "/")
    monkeypatch.delenv("SUPABASE_STORAGE_BUCKET", raising=False)
    for var in ("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_STORAGE_EMAIL", "SUPABASE_STORAGE_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    storage = get_storage()
    assert isinstance(storage, SupabaseStorage)
    assert storage.public_url("inspo/a.png") == f"{BASE}/storage/v1/object/public/creatives/inspo/a.png"
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "creatives-test")
    assert "/public/creatives-test/" in get_storage().public_url("inspo/a.png")


def test_fixtures_carry_the_assumed_shape_note():
    files = sorted(FIXTURES.glob("*.json"))
    assert len(files) >= 6
    for f in files:
        first_key, note = next(iter(json.loads(f.read_text()).items()))
        assert first_key == "_shape", f.name
        assert re.fullmatch(r"ASSUMED SHAPE from https://\S+, read 2026-10-28; replace with a recorded response at go-live", note), f.name
