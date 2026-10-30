"""What every live Ad Library backend shares: dates from the vendor rows, and the snapshot download from the ad CDN.

`fetch_cdn_image` downloads one snapshot over https from an ad CDN host only, checks every redirect before following
it (at most MAX_REDIRECTS), sends no vendor key (the client it is given carries none) and returns PNG. A failure
raises `CdnError`; each backend re-raises it as its own error type with the same message.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from PIL import Image, UnidentifiedImageError

from adapters import backoff

IMAGE_HOSTS = ("fbcdn.net", "fbsbx.com", "facebook.com", "cdninstagram.com")
MAX_REDIRECTS = 3
MAX_IMAGE_BYTES = 20 * 1024 * 1024
USER_AGENT = "upclicklabs-marketing-engineer/0.1 (intel worker; read-only)"


class CdnError(RuntimeError):
    """The ad CDN refused, failed or answered with something that is not an image."""


def iso_date(value: Any) -> str | None:
    """Unix seconds (or milliseconds), a digit string, or an ISO date/datetime -> YYYY-MM-DD."""
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value)
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()
    return str(value)[:10]


def url_host(url: str) -> tuple[str, str]:
    """(scheme, host) of `url`, both empty when it does not parse as an absolute URL."""
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, TypeError):
        return "", ""
    return parsed.scheme, (parsed.host or "").lower()


def is_cdn_url(url: str) -> bool:
    scheme, host = url_host(url)
    return scheme == "https" and any(host == h or host.endswith("." + h) for h in IMAGE_HOSTS)


def to_png(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            out = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise CdnError("the ad CDN answer is not an image") from exc
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def fetch_cdn_image(client: httpx.Client, url: str, *, attempts: int, sleep: Callable[[float], None]) -> bytes:
    """One snapshot image from the ad CDN as PNG. `client` must not follow redirects and must carry no vendor key."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        if not is_cdn_url(current):
            raise CdnError(f"snapshot image is not https on an ad CDN host (host {url_host(current)[1]!r}; "
                           f"allowed {', '.join(IMAGE_HOSTS)})")
        try:
            response = backoff.send(client, "GET", current, attempts=attempts, sleep=sleep)
        except httpx.TransportError as exc:
            raise CdnError(f"ad CDN unreachable: {type(exc).__name__}") from exc
        if not response.is_redirect:
            break
        current = str(httpx.URL(current).join(response.headers.get("location", "")))
    else:
        raise CdnError(f"ad CDN redirected more than {MAX_REDIRECTS} times")
    if response.status_code != 200:
        raise CdnError(f"ad CDN answered HTTP {response.status_code} for a snapshot image")
    if len(response.content) > MAX_IMAGE_BYTES:
        raise CdnError(f"snapshot image is larger than {MAX_IMAGE_BYTES} bytes")
    return to_png(response.content)
