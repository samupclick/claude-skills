"""scrapecreators Meta Ad Library backend (INSPO_BACKEND=scrapecreators): FR-4, FR-5, FR-8; CRUCIBLE A19.

`fetch_ads(brand)` looks the brand's page up once (search companies), then pages through the page's ads by cursor.
`fetch_image(url)` downloads one snapshot from the ad CDN (https, CDN hosts only, never with the key) and hands back
PNG. `usage()` is the vendor-call tally the intel worker writes to `runs.counts.inspo_usage`. Read-only: no write
endpoint exists here. The vendor shape is ASSUMED (fixtures/scrapecreators/README.md); everything that knows it is
in the shape functions below, which the fixture backend shares, so a different real shape changes only them.
"""
from __future__ import annotations

import io
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from PIL import Image, UnidentifiedImageError

from adapters import backoff
from adapters.env import require

API_BASE = "https://api.scrapecreators.com"
SEARCH_COMPANIES = "/v1/facebook/adLibrary/search/companies"
COMPANY_ADS = "/v1/facebook/adLibrary/company/ads"
IMAGE_HOSTS = ("fbcdn.net", "fbsbx.com", "facebook.com", "cdninstagram.com")
MAX_PAGES = 10
MAX_REDIRECTS = 3
MAX_IMAGE_BYTES = 20 * 1024 * 1024
USER_AGENT = "upclicklabs-marketing-engineer/0.1 (intel worker; read-only)"


class ScrapeCreatorsError(RuntimeError):
    """The vendor or the ad CDN refused or failed. Messages never carry the key."""


# ---------- the vendor shape: ASSUMED until go-live step 4; a different real shape changes only these ----------

def company_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(payload.get("searchResults") or payload.get("results") or [])


def company_page_id(payload: dict[str, Any], brand: str) -> str | None:
    """The page id for `brand`: an exact (case-insensitive) name match first, else the first result."""
    results = company_results(payload)
    wanted = brand.strip().casefold()
    exact = [r for r in results if str(r.get("name") or r.get("page_name") or "").strip().casefold() == wanted]
    for r in exact + results:
        page_id = r.get("page_id") or r.get("pageId") or r.get("id")
        if page_id:
            return str(page_id)
    return None


def page_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(payload.get("results") or payload.get("searchResults") or [])


def next_cursor(payload: dict[str, Any]) -> str | None:
    cursor = payload.get("cursor") or payload.get("next_cursor")
    return str(cursor) if cursor else None


def row_id(row: dict[str, Any]) -> str | None:
    value = row.get("ad_archive_id")
    return str(value) if value else None


def normalise(row: dict[str, Any], brand: str, source: str = "scrapecreators") -> dict[str, Any]:
    """Vendor row -> our ad dict (adapters/inspo/__init__.py). The raw row is kept for re-normalisation."""
    snap = row.get("snapshot") or {}
    body = snap.get("body")
    videos = snap.get("videos") or []
    images = [i.get("original_image_url") or i.get("resized_image_url") for i in snap.get("images") or []]
    images += [c.get("original_image_url") or c.get("resized_image_url") for c in snap.get("cards") or []]
    if not any(images):
        images += [v.get("video_preview_image_url") for v in videos]
    return {
        "source": source,
        "ad_id": row_id(row),
        "brand": brand,
        "page_name": row.get("page_name") or snap.get("page_name"),
        "start_date": iso_date(row.get("start_date")),
        "end_date": iso_date(row.get("end_date")),
        "is_active": bool(row.get("is_active")),
        "body": body.get("text") if isinstance(body, dict) else body,
        "title": snap.get("title"),
        "link_url": snap.get("link_url"),
        "cta": snap.get("cta_text"),
        "display_format": snap.get("display_format"),
        "images": list(dict.fromkeys(u for u in images if u)),
        "videos": [u for u in (v.get("video_hd_url") or v.get("video_sd_url") for v in videos) if u],
        "raw": row,
    }


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


# ---------- the backend ----------

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
        raise ScrapeCreatorsError("the ad CDN answer is not an image") from exc
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


class ScrapeCreatorsAdLibrary:
    def __init__(self, api_key: str, *, transport: httpx.BaseTransport | None = None, base_url: str = API_BASE,
                 sleep: Callable[[float], None] = time.sleep, timeout: float = 30.0, attempts: int = 3):
        self._key = api_key
        self._api = httpx.Client(base_url=base_url, transport=transport, timeout=timeout,
                                 headers={"x-api-key": api_key, "accept": "application/json", "user-agent": USER_AGENT})
        self._cdn = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False,
                                 headers={"user-agent": USER_AGENT})
        self._sleep, self._attempts = sleep, attempts
        self._page_ids: dict[str, str] = {}
        self.calls: Counter[str] = Counter()

    @classmethod
    def from_env(cls) -> "ScrapeCreatorsAdLibrary":
        return cls(require("intel", "SCRAPECREATORS_API_KEY")["SCRAPECREATORS_API_KEY"])

    def usage(self) -> dict[str, Any]:
        return {"backend": "scrapecreators", "api_calls": self.calls["search_companies"] + self.calls["company_ads"],
                "search_companies": self.calls["search_companies"], "company_ads": self.calls["company_ads"],
                "image_fetches": self.calls["image_fetches"]}

    def fetch_ads(self, brand: str, limit: int = 50) -> list[dict[str, Any]]:
        page_id = self._page_id(brand)
        rows: dict[str, dict[str, Any]] = {}
        cursor: str | None = None
        cursors: set[str] = set()
        for _ in range(MAX_PAGES):
            payload = self._get(COMPANY_ADS, {"pageId": page_id, **({"cursor": cursor} if cursor else {})}, "company_ads")
            for row in page_rows(payload):
                ad_id = row_id(row)
                if ad_id and ad_id not in rows:
                    rows[ad_id] = row
            cursor = next_cursor(payload)
            if len(rows) >= limit or cursor is None or cursor in cursors:
                break
            cursors.add(cursor)
        return [normalise(row, brand) for row in list(rows.values())[:limit]]

    def fetch_image(self, url: str) -> bytes:
        self.calls["image_fetches"] += 1
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if not is_cdn_url(current):
                raise ScrapeCreatorsError(f"snapshot image is not https on an ad CDN host (host {url_host(current)[1]!r}; "
                                          f"allowed {', '.join(IMAGE_HOSTS)})")
            try:
                response = backoff.send(self._cdn, "GET", current, attempts=self._attempts, sleep=self._sleep)
            except httpx.TransportError as exc:
                raise ScrapeCreatorsError(f"ad CDN unreachable: {type(exc).__name__}") from exc
            if not response.is_redirect:
                break
            current = str(httpx.URL(current).join(response.headers.get("location", "")))
        else:
            raise ScrapeCreatorsError(f"ad CDN redirected more than {MAX_REDIRECTS} times")
        if response.status_code != 200:
            raise ScrapeCreatorsError(f"ad CDN answered HTTP {response.status_code} for a snapshot image")
        if len(response.content) > MAX_IMAGE_BYTES:
            raise ScrapeCreatorsError(f"snapshot image is larger than {MAX_IMAGE_BYTES} bytes")
        return to_png(response.content)

    def close(self) -> None:
        self._api.close()
        self._cdn.close()

    def _page_id(self, brand: str) -> str:
        if brand not in self._page_ids:
            page_id = company_page_id(self._get(SEARCH_COMPANIES, {"query": brand}, "search_companies"), brand)
            if page_id is None:
                raise ScrapeCreatorsError(f"no Ad Library page found for brand {brand!r}")
            self._page_ids[brand] = page_id
        return self._page_ids[brand]

    def _get(self, path: str, params: dict[str, str], kind: str) -> dict[str, Any]:
        def tick() -> None:
            self.calls[kind] += 1

        try:
            response = backoff.send(self._api, "GET", path, params=params, attempts=self._attempts, sleep=self._sleep,
                                    on_attempt=tick)
        except httpx.TransportError as exc:
            raise ScrapeCreatorsError(f"scrapecreators {kind} unreachable: {type(exc).__name__}") from exc
        if response.status_code in (401, 403):
            raise ScrapeCreatorsError(f"scrapecreators refused the key (HTTP {response.status_code}); "
                                      "check SCRAPECREATORS_API_KEY")
        if response.status_code == 402:
            raise ScrapeCreatorsError("scrapecreators answered HTTP 402 (out of credits?); top up the account")
        if response.status_code >= 400:
            raise ScrapeCreatorsError(f"scrapecreators {kind} HTTP {response.status_code}: {self._message(response)}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ScrapeCreatorsError(f"scrapecreators {kind}: the answer is not JSON") from exc
        if not isinstance(payload, dict):
            raise ScrapeCreatorsError(f"scrapecreators {kind}: expected a JSON object, got {type(payload).__name__}")
        if payload.get("success") is False:
            raise ScrapeCreatorsError(f"scrapecreators {kind} reported failure: {self._message(response)}")
        return payload

    def _message(self, response: httpx.Response) -> str:
        try:
            body = response.json()
            text = str(body.get("message") or body.get("error") or body) if isinstance(body, dict) else str(body)
        except ValueError:
            text = response.text
        return text.replace(self._key, "***")[:200] if self._key else text[:200]
