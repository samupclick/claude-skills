"""Supabase Storage (STORAGE_BACKEND=supabase) for FR-5 / FR-25 assets, over the Storage REST API with plain httpx.

`put(bytes, key)` uploads to `SUPABASE_STORAGE_BUCKET` (default `creatives`) with `x-upsert: true` and returns the
public object URL; `get(url)` reads such a URL back without credentials. The bucket is public: Meta fetches creative
images by URL, the gate derives sibling objects (`1080x1080.html`, `image.png`) from the stored asset URL, and
`creatives.asset_urls` lives forever, so a signed URL's query token and expiry would break all three.

Writes run as a dedicated Supabase Auth user (`SUPABASE_STORAGE_EMAIL` / `SUPABASE_STORAGE_PASSWORD`, signed in with
`SUPABASE_PUBLISHABLE_KEY`). Its only grant is the RLS policy `scripts/apply_migrations.py --storage-writer` puts on
`storage.objects`: insert / select / update in this bucket for that one user, no delete, nothing in the warehouse.
No worker holds the service role (NFR-1). Errors name variables, keys and HTTP statuses; secrets are scrubbed.
"""
from __future__ import annotations

import mimetypes
import os
import time
from typing import Any, Callable
from urllib.parse import quote, unquote, urlsplit

import httpx

from adapters import backoff
from adapters.env import MissingEnvVar, require

DEFAULT_BUCKET = "creatives"
CACHE_CONTROL = "3600"
CREDENTIAL_VARS = ("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_STORAGE_EMAIL", "SUPABASE_STORAGE_PASSWORD")
ATTEMPTS = 2
REFRESH_MARGIN_S = 60


class SupabaseStorageError(RuntimeError):
    """Supabase answered with an error, or with a body that does not match the assumed shape."""


def content_type(data: bytes, key: str) -> str:
    """The MIME type from the leading bytes; the key's extension only when the bytes say nothing."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    head = data[:64].removeprefix(b"\xef\xbb\xbf").lstrip().lower()
    if head.startswith((b"<!doctype html", b"<html")):
        return "text/html; charset=utf-8"
    return mimetypes.guess_type(key)[0] or "application/octet-stream"


def check_key(key: str) -> str:
    parts = key.split("/")
    if (not key or key.startswith("/") or "\\" in key or any(p in ("", ".", "..") for p in parts)
            or any(ord(c) < 32 or ord(c) == 127 for c in key)):
        raise ValueError(f"storage key is not a clean relative path: {key!r}")
    return key


class SupabaseStorage:
    def __init__(self, base_url: str, bucket: str = DEFAULT_BUCKET, *, api_key: str | None = None,
                 email: str | None = None, password: str | None = None, client: httpx.Client | None = None,
                 clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep):
        self.base = base_url.rstrip("/")
        self.bucket = bucket
        self._credentials = dict(zip(CREDENTIAL_VARS, (api_key, email, password), strict=True))
        self._http = client or httpx.Client(timeout=30.0)
        self._clock = clock
        self._sleep = sleep
        self._session: dict[str, Any] | None = None

    @classmethod
    def from_env(cls) -> "SupabaseStorage":
        url = require("storage (STORAGE_BACKEND=supabase)", "SUPABASE_URL")["SUPABASE_URL"]
        return cls(url, os.environ.get("SUPABASE_STORAGE_BUCKET") or DEFAULT_BUCKET,
                   **{k: os.environ.get(v) or None for k, v in zip(("api_key", "email", "password"), CREDENTIAL_VARS, strict=True)})

    # ---------- URLs ----------

    def public_url(self, key: str) -> str:
        return f"{self.base}/storage/v1/object/public/{quote(self.bucket, safe='')}/{quote(check_key(key), safe='/')}"

    def key_for(self, url: str) -> str:
        """The object key of a public URL in this bucket; anything else is refused (no fetch of foreign URLs)."""
        prefix = f"{self.base}/storage/v1/object/public/{quote(self.bucket, safe='')}/"
        parts = urlsplit(url)
        if not url.startswith(prefix) or parts.query or parts.fragment:
            raise ValueError(f"supabase storage only serves public URLs under its own bucket {self.bucket!r}")
        return check_key(unquote(url[len(prefix):]))

    # ---------- the Storage interface ----------

    def put(self, data: bytes, key: str) -> str:
        check_key(key)
        target = f"{self.base}/storage/v1/object/{quote(self.bucket, safe='')}/{quote(key, safe='/')}"
        ctype = content_type(data, key)

        def upload() -> httpx.Response:
            return self._send("POST", target, headers={**self._auth_headers(), "x-upsert": "true"},
                              files={"file": (key.rsplit("/", 1)[-1], data, ctype)}, data={"cacheControl": CACHE_CONTROL})

        resp = upload()
        if resp.status_code in (400, 401, 403):  # an expired or revoked token reads like a refusal: sign in again once
            self._session = self._sign_in(refresh=True)
            resp = upload()
        body = self._json(resp, f"upload {key!r}")
        if body.get("Key") != f"{self.bucket}/{key}":
            raise SupabaseStorageError(f"supabase storage upload {key!r}: answer's Key is not '<bucket>/<key>' (assumed shape changed)")
        return self.public_url(key)

    def get(self, url: str) -> bytes:
        key = self.key_for(url)
        resp = self._send("GET", self.public_url(key))
        if resp.status_code != 200:
            raise self._error(resp, f"read {key!r}")
        return resp.content

    # ---------- auth ----------

    def _auth_headers(self) -> dict[str, str]:
        if self._session is None or self._clock() >= self._session["expires_at"] - REFRESH_MARGIN_S:
            self._session = self._sign_in(refresh=self._session is not None)
        return {"apikey": self._credentials["SUPABASE_PUBLISHABLE_KEY"], "authorization": f"Bearer {self._session['access_token']}"}

    def _sign_in(self, *, refresh: bool) -> dict[str, Any]:
        missing = [name for name, value in self._credentials.items() if not value]
        if missing:
            raise MissingEnvVar(f"storage writes (STORAGE_BACKEND=supabase) need {', '.join(missing)}; "
                                "set it in marketing-engineer/.env (see .env.example)")
        url = f"{self.base}/auth/v1/token"
        headers = {"apikey": self._credentials["SUPABASE_PUBLISHABLE_KEY"]}
        if refresh and self._session and self._session.get("refresh_token"):
            resp = self._send("POST", url, params={"grant_type": "refresh_token"}, headers=headers,
                              json={"refresh_token": self._session["refresh_token"]})
            if resp.status_code == 200:
                return self._session_from(resp)
        resp = self._send("POST", url, params={"grant_type": "password"}, headers=headers,
                          json={"email": self._credentials["SUPABASE_STORAGE_EMAIL"],
                                "password": self._credentials["SUPABASE_STORAGE_PASSWORD"]})
        if resp.status_code != 200:
            raise self._error(resp, "sign-in as SUPABASE_STORAGE_EMAIL with SUPABASE_STORAGE_PASSWORD")
        return self._session_from(resp)

    def _session_from(self, resp: httpx.Response) -> dict[str, Any]:
        body = self._json(resp, "sign-in")
        token, lifetime = body.get("access_token"), body.get("expires_in")
        if not isinstance(token, str) or not isinstance(lifetime, int):
            raise SupabaseStorageError("supabase auth answer lacks access_token / expires_in (assumed shape changed)")
        return {"access_token": token, "refresh_token": body.get("refresh_token"), "expires_at": self._clock() + lifetime}

    # ---------- HTTP ----------

    def _send(self, method: str, url: str, **kw: Any) -> httpx.Response:
        """One retry on a transport error, a 429 or a 5xx (the shared adapters/backoff.py); every call this adapter
        makes is idempotent (upsert)."""
        try:
            return backoff.send(self._http, method, url, attempts=ATTEMPTS, base_delay=1.0, sleep=self._sleep, **kw)
        except httpx.TransportError as exc:
            raise SupabaseStorageError(f"supabase {method} {urlsplit(url).path}: {type(exc).__name__} twice") from None

    def _json(self, resp: httpx.Response, what: str) -> dict[str, Any]:
        if resp.status_code != 200:
            raise self._error(resp, what)
        try:
            body = resp.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise SupabaseStorageError(f"supabase {what}: answer is not a JSON object (assumed shape changed)")
        return body

    def _error(self, resp: httpx.Response, what: str) -> SupabaseStorageError:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        body = body if isinstance(body, dict) else {}
        code = body.get("statusCode") or body.get("error_code") or body.get("code")
        label = body.get("error") if body.get("statusCode") else None
        message = next((str(body[k]) for k in ("message", "msg", "error_description") if body.get(k)), resp.text)
        status = " ".join(str(p) for p in (f"HTTP {resp.status_code}", code, label) if p)
        return SupabaseStorageError(self._scrub(f"supabase {what}: {status}: {message[:200]}"))

    def _scrub(self, text: str) -> str:
        session = self._session or {}
        secrets = {*self._credentials.values(), session.get("access_token"), session.get("refresh_token")}
        for s in sorted((s for s in secrets if s), key=len, reverse=True):
            text = text.replace(s, "***")
        return text
