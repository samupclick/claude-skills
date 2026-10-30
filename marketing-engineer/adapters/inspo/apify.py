"""Apify Meta Ad Library backend (INSPO_BACKEND=apify): FR-4, FR-5, FR-8; CRUCIBLE A19. Sam chose Apify over
scrapecreators on 2026-10-31 (DECISIONS.md); the scrapecreators backend stays.

`fetch_ads(brand, limit, page=...)` runs Apify's own actor `apify/facebook-ads-scraper` on the brand's Facebook page
(or a Meta Ad Library URL) from `clients.config.inspo.pages`, polls the run to its end and reads its dataset. One run
per brand. Every run is capped twice: `maxItems` (the actor bills per ad) and `maxTotalChargeUsd`. A run that has not
ended after `max_polls` polls is aborted, so it stops billing. The token travels in the `Authorization: Bearer` header,
never in a URL, and never reaches the ad CDN: `fetch_image` uses a separate client without it
(`adapters/inspo/shared.py`). `usage()` is the tally the intel worker writes to `runs.counts.inspo_usage`, including
Apify's own cost figure for the runs. Read-only: no write endpoint is called.

The dataset shape was seen in real runs on 2026-10-31 (fixtures/apify/README.md): one item per ad; for a page with no
ads, one summary item whose `results` is empty; for an input the actor cannot read, one error item. `item_rows`,
`error_items`, `item_id` and `normalise_item` are the only functions that know it.
"""
from __future__ import annotations

import time
from collections import Counter
from typing import Any, Callable

import httpx

from adapters import backoff
from adapters.env import require
from adapters.inspo.shared import USER_AGENT, CdnError, fetch_cdn_image, iso_date, url_host

API_BASE = "https://api.apify.com/v2"
ACTOR = "apify~facebook-ads-scraper"          # Apify's own actor (username~name), maintained by Apify
WAIT_SECONDS = 60                              # waitForFinish: the API's maximum long-poll
MAX_POLLS = 15                                 # about 15 minutes per brand, then the run is aborted
MAX_CHARGE_USD = 1.0                           # per run; 50 ads cost about 0.29 USD at the free-plan price
ENDED = ("SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED")
PAGE_HOSTS = ("facebook.com", "www.facebook.com", "m.facebook.com")


class ApifyError(RuntimeError):
    """Apify or the ad CDN refused or failed. Messages never carry the token."""


# ---------- the dataset shape: seen in real runs 2026-10-31; a different real shape changes only these ----------

def item_rows(payload: Any) -> list[dict[str, Any]]:
    """The ad items of a dataset (a bare JSON array). A page summary item contributes the ads in its `results`; an
    error item contributes nothing (`error_items`)."""
    rows = payload if isinstance(payload, list) else (payload or {}).get("items") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or "error" in row:
            continue
        if isinstance(row.get("results"), list) and "snapshot" not in row:
            out += [r for r in row["results"] if isinstance(r, dict)]
        else:
            out.append(row)
    return out


def error_items(payload: Any) -> list[str]:
    """`code: description` for each error item, e.g. no_items for a page the actor cannot read."""
    rows = payload if isinstance(payload, list) else []
    return [f"{r.get('error')}: {r.get('errorDescription') or '-'}" for r in rows if isinstance(r, dict) and r.get("error")]


def item_id(item: dict[str, Any]) -> str | None:
    value = item.get("adArchiveID") or item.get("adArchiveId") or item.get("ad_archive_id")
    return str(value) if value else None


def _text(value: Any) -> str | None:
    text = value.get("text") if isinstance(value, dict) else value
    text = str(text).strip() if text else None
    if text and text.startswith("{{") and text.endswith("}}"):   # a dynamic-creative placeholder, not copy
        return None
    return text


def normalise_item(item: dict[str, Any], brand: str, source: str = "apify") -> dict[str, Any]:
    """Apify dataset item -> our ad dict (adapters/inspo/__init__.py). The item is kept whole in `raw`. A dynamic
    creative's empty or placeholder fields fall back to its first card; a video ad is judged on its preview frames."""
    snap = item.get("snapshot") or {}
    cards = [c for c in snap.get("cards") or [] if isinstance(c, dict)]
    videos = [v for v in snap.get("videos") or [] if isinstance(v, dict)]
    first = cards[0] if cards else {}
    images = [i.get("originalImageUrl") or i.get("resizedImageUrl") for i in snap.get("images") or [] if isinstance(i, dict)]
    images += [c.get("originalImageUrl") or c.get("resizedImageUrl") for c in cards]
    if not any(images):
        images += [v.get("videoPreviewImageUrl") for v in videos] + [c.get("videoPreviewImageUrl") for c in cards]
    clips = [v.get("videoHdUrl") or v.get("videoSdUrl") for v in videos] + [c.get("videoHdUrl") or c.get("videoSdUrl") for c in cards]
    return {
        "source": source,
        "ad_id": item_id(item),
        "brand": brand,
        "page_name": item.get("pageName") or snap.get("pageName"),
        "start_date": iso_date(item.get("startDate") or item.get("startDateFormatted")),
        "end_date": iso_date(item.get("endDate") or item.get("endDateFormatted")),
        "is_active": bool(item.get("isActive")),
        "body": _text(snap.get("body")) or _text(first.get("body")),
        "title": _text(snap.get("title")) or _text(first.get("title")),
        "link_url": snap.get("linkUrl") or first.get("linkUrl"),
        "cta": snap.get("ctaText") or first.get("ctaText"),
        "display_format": snap.get("displayFormat"),
        "images": list(dict.fromkeys(u for u in images if u)),
        "videos": [u for u in clips if u],
        "raw": item,
    }


def run_input(page: str, limit: int) -> dict[str, Any]:
    """The actor's input: one start URL, at most `limit` ads. Any filter (active status, country) rides in an Ad
    Library URL, which takes priority over the actor's own fields."""
    return {"startUrls": [{"url": page}], "resultsLimit": limit}


def is_page_url(url: str | None) -> bool:
    scheme, host = url_host(url or "")
    return scheme == "https" and host in PAGE_HOSTS


# ---------- the backend ----------

class ApifyAdLibrary:
    def __init__(self, token: str, *, transport: httpx.BaseTransport | None = None, base_url: str = API_BASE,
                 sleep: Callable[[float], None] = time.sleep, timeout: float = WAIT_SECONDS + 30.0, attempts: int = 3,
                 max_polls: int = MAX_POLLS, max_charge_usd: float = MAX_CHARGE_USD, poll_pause: float = 5.0):
        self._token = token
        self._api = httpx.Client(base_url=base_url.rstrip("/") + "/", transport=transport, timeout=timeout,
                                 headers={"authorization": f"Bearer {token}", "accept": "application/json",
                                          "user-agent": USER_AGENT})
        self._cdn = httpx.Client(transport=transport, timeout=30.0, follow_redirects=False, headers={"user-agent": USER_AGENT})
        self._sleep, self._attempts = sleep, attempts
        self.max_polls, self.max_charge_usd, self.poll_pause = max_polls, max_charge_usd, poll_pause
        self.calls: Counter[str] = Counter()
        self.runs = 0
        self.items = 0
        self.usage_usd = 0.0

    @classmethod
    def from_env(cls) -> "ApifyAdLibrary":
        return cls(require("intel", "APIFY_TOKEN")["APIFY_TOKEN"])

    def usage(self) -> dict[str, Any]:
        return {"backend": "apify", "api_calls": sum(n for k, n in self.calls.items() if k != "image_fetches"),
                "runs": self.runs, "items": self.items, "usage_usd": round(self.usage_usd, 4),
                "image_fetches": self.calls["image_fetches"]}

    def fetch_ads(self, brand: str, limit: int = 50, *, page: str | None = None) -> list[dict[str, Any]]:
        if not is_page_url(page):
            raise ApifyError(f"no https Facebook page or Ad Library URL for brand {brand!r} in clients.config.inspo.pages "
                             f"(got {page!r}); the apify backend runs on a page, not a name")
        started = self._data(self._call("POST", f"actors/{ACTOR}/runs", "start_run", json=run_input(str(page), limit),
                                        params={"maxItems": limit, "maxTotalChargeUsd": self.max_charge_usd,
                                                "waitForFinish": WAIT_SECONDS}))
        self.runs += 1
        run_id = str(started.get("id") or "")
        if not run_id:
            raise ApifyError(f"Apify started a run for {brand!r} without an id")
        run = self._wait(run_id, brand)
        payload = self._call("GET", f"datasets/{run.get('defaultDatasetId')}/items", "dataset_items",
                             params={"clean": "true", "format": "json", "limit": limit})
        rows: dict[str, dict[str, Any]] = {}
        ads = item_rows(payload)
        errors = error_items(payload)
        if errors and not ads:
            raise ApifyError(f"Apify could not read the page for {brand!r} ({page}): {'; '.join(errors)[:300]}")
        for item in ads:
            ad_id = item_id(item)
            if ad_id and ad_id not in rows:
                rows[ad_id] = item
        self.items += len(rows)
        return [normalise_item(item, brand) for item in list(rows.values())[:limit]]

    def fetch_image(self, url: str) -> bytes:
        self.calls["image_fetches"] += 1
        try:
            return fetch_cdn_image(self._cdn, url, attempts=self._attempts, sleep=self._sleep)
        except CdnError as exc:
            raise ApifyError(str(exc)) from exc

    def close(self) -> None:
        self._api.close()
        self._cdn.close()

    def _wait(self, run_id: str, brand: str) -> dict[str, Any]:
        for poll in range(1, self.max_polls + 1):
            run = self._data(self._call("GET", f"actor-runs/{run_id}", "get_run", params={"waitForFinish": WAIT_SECONDS}))
            status = str(run.get("status") or "")
            if status in ENDED:
                if isinstance(run.get("usageTotalUsd"), (int, float)):
                    self.usage_usd += float(run["usageTotalUsd"])
                if status != "SUCCEEDED":
                    raise ApifyError(f"Apify run {run_id} for {brand!r} ended {status}: {run.get('statusMessage') or '-'}")
                return run
            if poll < self.max_polls:
                self._sleep(self.poll_pause)
        try:
            self._call("POST", f"actor-runs/{run_id}/abort", "abort_run")
            note = "aborted"
        except ApifyError:
            note = "could not be aborted; abort it in the Apify console"
        raise ApifyError(f"Apify run {run_id} for {brand!r} did not finish after {self.max_polls} polls; {note}")

    def _call(self, method: str, path: str, kind: str, **kwargs: Any) -> Any:
        def tick() -> None:
            self.calls[kind] += 1

        try:
            response = backoff.send(self._api, method, path, attempts=self._attempts, sleep=self._sleep, on_attempt=tick,
                                    **kwargs)
        except httpx.TransportError as exc:
            raise ApifyError(f"Apify {kind} unreachable: {type(exc).__name__}") from exc
        if response.status_code in (401, 403):
            raise ApifyError(f"Apify refused the token (HTTP {response.status_code}); check APIFY_TOKEN")
        if response.status_code == 402:
            raise ApifyError("Apify answered HTTP 402 (out of credit, or over the run's maxTotalChargeUsd)")
        if response.status_code >= 400:
            raise ApifyError(f"Apify {kind} HTTP {response.status_code}: {self._message(response)}")
        try:
            return response.json()
        except ValueError as exc:
            raise ApifyError(f"Apify {kind}: the answer is not JSON") from exc

    @staticmethod
    def _data(payload: Any) -> dict[str, Any]:
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ApifyError("Apify answered without a `data` object")
        return data

    def _message(self, response: httpx.Response) -> str:
        try:
            body = response.json()
            error = body.get("error") if isinstance(body, dict) else None
            text = str((error or {}).get("message") or error or body) if isinstance(body, dict) else str(body)
        except ValueError:
            text = response.text
        return text.replace(self._token, "***")[:200] if self._token else text[:200]
