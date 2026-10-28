"""Live Meta Marketing API backend (META_BACKEND=live): the MetaAds protocol over the Graph API with plain httpx.
FR-30, FR-31, FR-37, FR-38, NFR-1, NFR-4.

- version: META_API_VERSION, default v26.0 (Marketing API version table, released 2026-07-29, read 2026-10-28)
- tokens: write mode (`get_meta(write=True)`, scripts/apply_actions.py only) uses META_ACCESS_TOKEN; read mode (workers)
  uses META_READ_TOKEN, an ads_read token, and refuses every create/update before a request is made. The token travels
  in the Authorization header, never in a URL, and is scrubbed from every error message
- budgets: currency units at the interface, the ad account's minor units on the wire (offset from Meta's currency table)
- creatives: the Storage image is read through the storage adapter, uploaded to /act_<id>/adimages as bytes and
  referenced by `image_hash` in object_story_spec.link_data (not `picture`: the hash outlives a signed Storage URL)
- ad sets: OFFSITE_CONVERSIONS on META_PIXEL_ID. Schedule is a standard event; QuizStart / QuizComplete are custom
  events, optimised through the custom conversions in META_CUSTOM_CONVERSIONS ("QuizStart=<id>,QuizComplete=<id>"),
  which also map insights' `offsite_conversion.custom.<id>` back to our names. Advantage+ audience is set off so the
  configured geo and age band hold
- insights: one async report job per call, polled with growing waits, read page by page through cursors
- throttling: codes 4, 17, 32, 613, 80000-80014 wait as long as the usage headers say (estimated_time_to_regain_access,
  reset_time_duration) and retry within `max_wait`, then raise MetaThrottled with those headers; a response showing
  90% usage or more paces the next call. A write that failed any other way is never re-sent (the executor's name
  lookup finds a create that landed); reads retry transient errors
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Callable, Iterator

import httpx

from adapters.env import MissingEnvVar, require
from adapters.meta import MetaApiError, MetaThrottled, review_status

DEFAULT_API_VERSION = "v26.0"
GRAPH_HOST = "https://graph.facebook.com"
EDGES = {"campaign": "campaigns", "adset": "adsets", "creative": "adcreatives", "ad": "ads"}
FIELDS = {
    "campaign": "id,name,status,effective_status,objective,daily_budget,created_time",
    "adset": "id,name,status,effective_status,campaign_id,daily_budget,optimization_goal,promoted_object,targeting,created_time",
    "creative": "id,name,status,object_story_spec,created_time",
    "ad": "id,name,status,effective_status,adset_id,campaign_id,creative{id},ad_review_feedback,created_time",
}
LISTED_STATUSES = ["ACTIVE", "PAUSED", "PENDING_REVIEW", "DISAPPROVED", "PREAPPROVED", "PENDING_BILLING_INFO",
                   "CAMPAIGN_PAUSED", "ARCHIVED", "ADSET_PAUSED", "IN_PROCESS", "WITH_ISSUES"]
UPDATABLE = ("daily_budget", "name", "status")
INSIGHT_FIELDS = {
    "ad": "ad_id,ad_name,adset_id,campaign_id,impressions,reach,clicks,inline_link_clicks,spend,frequency,actions,date_start,date_stop",
    "account": "impressions,spend,date_start,date_stop",
}
EVENT_ORDER = ("QuizStart", "QuizComplete", "Schedule")
STANDARD_EVENTS = {"Schedule": "SCHEDULE", "Lead": "LEAD", "CompleteRegistration": "COMPLETE_REGISTRATION", "Contact": "CONTACT"}
STANDARD_ACTION_TYPES = {"Schedule": ("schedule_website", "offsite_conversion.fb_pixel_schedule")}
VIDEO_3S_ACTION = "video_view"
CTA_TYPE = "LEARN_MORE"
THROTTLE_CODES = frozenset({4, 17, 32, 613, *range(80000, 80015)})
USAGE_HEADERS = ("x-business-use-case-usage", "x-ad-account-usage", "x-app-usage", "x-fb-ads-insights-throttle")
PACE_AT = 90
PACE_DEFAULT_WAIT = 30.0
BACKOFF_BASE = 5.0
MAX_POLL_INTERVAL = 30.0
OFFSET_ONE = frozenset("CLP COP CRC HUF ISK IDR JPY KRW PYG TWD VND".split())
OFFSET_HUNDRED = frozenset("DZD ARS AUD BHD BDT BOB BGN BRL GBP CAD CNY HRK CZK DKK EGP EUR GTQ HNL HKD INR ILS JOD KES LVL LTL "
                           "MOP MYR MXN NZD NIO NGN NOK PKR PEN PHP PLN QAR RON RUB SAR RSD SGD SKK ZAR SEK CHF THB TRY AED UAH "
                           "USD UYU VEF FBZ VES".split())


def parse_custom_conversions(value: str) -> dict[str, str]:
    """META_CUSTOM_CONVERSIONS: `QuizStart=<id>,QuizComplete=<id>`; an empty value is an empty map."""
    out: dict[str, str] = {}
    for part in filter(None, (p.strip() for p in value.split(","))):
        event, sep, cid = (s.strip() for s in part.partition("="))
        if not sep or not event or not cid.isdigit():
            raise MetaApiError("META_CUSTOM_CONVERSIONS must read <Event>=<custom conversion id>[,<Event>=<id>…]")
        out[event] = cid
    return out


def _storage_get(url: str) -> bytes:
    from adapters.storage import get_storage

    return get_storage().get(url)


def _need(value: str, var: str, job: str) -> str:
    if not value:
        raise MissingEnvVar(f"job {job!r} needs {var}; set it in marketing-engineer/.env (see .env.example)")
    return value


def _encode(values: dict[str, Any] | None) -> dict[str, str] | None:
    if values is None:
        return None
    return {k: json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v) for k, v in values.items() if v is not None}


def _loads(text: str | None) -> Any:
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    n = _num(value)
    return int(n) if n is not None else 0


class LiveMeta:
    def __init__(self, *, token: str, ad_account_id: str, write: bool = False, page_id: str = "", pixel_id: str = "",
                 api_version: str = DEFAULT_API_VERSION, custom_conversions: dict[str, str] | None = None,
                 transport: httpx.BaseTransport | None = None, fetch_image: Callable[[str], bytes] | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 max_wait: float = 300.0, insights_timeout: float = 900.0, poll_interval: float = 2.0, timeout: float = 60.0):
        if not re.fullmatch(r"v\d+\.\d+", api_version or ""):
            raise MetaApiError(f"META_API_VERSION must name a Graph API version such as {DEFAULT_API_VERSION}")
        self.write = write
        self.account = "act_" + str(ad_account_id).strip().removeprefix("act_")
        self.page_id, self.pixel_id, self.api_version = page_id, pixel_id, api_version
        self.custom_conversions = dict(custom_conversions or {})
        self.max_wait, self.insights_timeout, self.poll_interval = max_wait, insights_timeout, poll_interval
        self.last_headers: dict[str, str] = {}
        self._token = token
        self._sleep, self._clock = sleep, clock
        self._fetch_image = fetch_image or _storage_get
        self._offset: int | None = None
        self._name_filter = True
        self._http = httpx.Client(base_url=f"{GRAPH_HOST}/{api_version}/", transport=transport, timeout=timeout,
                                  headers={"Authorization": f"Bearer {token}"})

    @classmethod
    def from_env(cls, *, write: bool) -> "LiveMeta":
        token_var = "META_ACCESS_TOKEN" if write else "META_READ_TOKEN"
        env = require("meta (executor, writes)" if write else "meta (worker, read-only)", token_var, "META_AD_ACCOUNT_ID")
        return cls(token=env[token_var], ad_account_id=env["META_AD_ACCOUNT_ID"], write=write,
                   page_id=os.environ.get("META_PAGE_ID") or "", pixel_id=os.environ.get("META_PIXEL_ID") or "",
                   api_version=os.environ.get("META_API_VERSION") or DEFAULT_API_VERSION,
                   custom_conversions=parse_custom_conversions(os.environ.get("META_CUSTOM_CONVERSIONS") or ""))

    def close(self) -> None:
        self._http.close()

    # ---- writes (executor only) ----------------------------------------------------------------
    def create_campaign(self, name, *, objective, status="PAUSED", daily_budget=None):
        self._writable("create_campaign")
        data: dict[str, Any] = {"name": name, "objective": objective, "status": status, "special_ad_categories": []}
        if daily_budget is None:
            data["is_adset_budget_sharing_enabled"] = False     # each recipe keeps its own ad set budget
        else:
            data["daily_budget"] = self.to_minor(daily_budget)
        return self._create("campaign", data)

    def create_adset(self, name, *, campaign_id, daily_budget, optimization_event, targeting, status="PAUSED"):
        self._writable("create_adset")
        data = {"name": name, "campaign_id": campaign_id, "status": status, "billing_event": "IMPRESSIONS",
                "optimization_goal": "OFFSITE_CONVERSIONS", "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "destination_type": "WEBSITE",
                "promoted_object": self._promoted_object(optimization_event), "targeting": meta_targeting(targeting)}
        data["daily_budget"] = self.to_minor(daily_budget)
        return self._create("adset", data)

    def create_creative(self, name, *, image_url, body, title, link_url, page_id=""):
        self._writable("create_creative")
        page = _need(page_id or self.page_id, "META_PAGE_ID", "meta create_creative")
        link_data = {"image_hash": self._upload_image(image_url), "link": link_url, "message": body, "name": title,
                     "call_to_action": {"type": CTA_TYPE, "value": {"link": link_url}}}
        return self._create("creative", {"name": name, "object_story_spec": {"page_id": page, "link_data": link_data}})

    def create_ad(self, name, *, adset_id, creative_id, status="PAUSED"):
        self._writable("create_ad")
        return self._create("ad", {"name": name, "adset_id": adset_id, "creative": {"creative_id": creative_id}, "status": status})

    def update(self, kind, object_id, **fields):
        """Fields: status, name, daily_budget (currency units). `on=` is the fake account's dating knob: accepted for
        today only, since Meta dates a change when it happens. review_status / ad_review_feedback are Meta's to set."""
        self._writable("update")
        self._edge(kind)
        on = fields.pop("on", None)
        if on is not None and on != date.today():
            raise MetaApiError(f"on={on} backdates a change, which only the fake account can do")
        unknown = sorted(set(fields) - set(UPDATABLE))
        if unknown:
            raise MetaApiError(f"Meta update of a {kind} takes {list(UPDATABLE)}, not {unknown}")
        data: dict[str, Any] = {k: fields[k] for k in ("status", "name") if k in fields}
        if fields.get("daily_budget") is not None:
            data["daily_budget"] = self.to_minor(fields["daily_budget"])
        if data:
            self._request("POST", str(object_id), data=data, write=True)
        return self.get(kind, object_id)

    # ---- reads ---------------------------------------------------------------------------------
    def get(self, kind, object_id):
        self._edge(kind)
        return self._normalise(kind, self._request("GET", str(object_id), params={"fields": FIELDS[kind]}))

    def find_by_name(self, kind, name):
        """Name lookup before every create (SKILL.md §6 step 6). Meta's name filter narrows the listing; the exact
        comparison is ours. A refused filter (code 100) falls back to the full listing for this client's lifetime."""
        edge = self._edge(kind)
        params: dict[str, Any] = {"fields": FIELDS[kind], "limit": 200}
        if kind != "creative":
            params["effective_status"] = LISTED_STATUSES
        if self._name_filter:
            try:
                return self._scan(kind, edge, name, {**params, "filtering": [{"field": "name", "operator": "EQUAL", "value": name}]})
            except MetaThrottled:
                raise
            except MetaApiError as exc:
                if getattr(exc, "code", None) != 100:
                    raise
                self._name_filter = False
        return self._scan(kind, edge, name, params)

    def insights(self, *, level, since, until, ids=None):
        if level not in ("ad", "account"):
            raise MetaApiError(f"insights supports level=ad|account, got {level}")
        if ids is not None and not ids:
            return []
        data: dict[str, Any] = {"level": level, "time_range": {"since": since.isoformat(), "until": until.isoformat()},
                                "time_increment": 1, "fields": INSIGHT_FIELDS[level]}
        if ids:
            data["filtering"] = [{"field": "ad.id", "operator": "IN", "value": [str(i) for i in ids]}]
        job = self._request("POST", f"{self.account}/insights", data=data)
        report = str(job.get("report_run_id") or "")
        if not report:
            raise MetaApiError("Meta accepted the insights job but returned no report_run_id")
        self._await_report(report)
        rows = [self._insight_row(level, r) for r in self._pages(f"{report}/insights", {"limit": 500})]
        rows.sort(key=lambda r: (r["date_start"] or "", r.get("ad_id") or ""))
        return rows

    def account_spend_today(self, on=None):
        on = on or date.today()
        return round(sum(r["spend"] for r in self.insights(level="account", since=on, until=on)), 2)

    # ---- money ---------------------------------------------------------------------------------
    def to_minor(self, amount: Any) -> int:
        """Currency units (the warehouse's numeric(12,2)) to the account currency's minor units, half up."""
        try:
            value = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise MetaApiError(f"budget {amount!r} is not a number") from None
        if not value.is_finite() or value <= 0:
            raise MetaApiError(f"budget must be positive, got {amount!r}")
        return int((value * self._currency_offset()).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    def from_minor(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(Decimal(str(value)) / self._currency_offset())

    def _currency_offset(self) -> int:
        if self._offset is None:
            currency = str(self._request("GET", self.account, params={"fields": "id,currency"}).get("currency") or "").upper()
            if currency in OFFSET_ONE:
                self._offset = 1
            elif currency in OFFSET_HUNDRED:
                self._offset = 100
            else:
                raise MetaApiError(f"ad account currency {currency or 'unknown'} is not in Meta's currency table; budgets cannot be converted")
        return self._offset

    # ---- request building ----------------------------------------------------------------------
    def _writable(self, what: str) -> None:
        if not self.write:
            raise MetaApiError(f"{what} needs the executor's META_ACCESS_TOKEN (get_meta(write=True) in scripts/apply_actions.py); "
                               "this client holds META_READ_TOKEN and only reads")

    @staticmethod
    def _edge(kind: str) -> str:
        if kind not in EDGES:
            raise MetaApiError(f"unknown object kind {kind!r}")
        return EDGES[kind]

    def _create(self, kind: str, data: dict[str, Any]) -> dict[str, Any]:
        created = self._request("POST", f"{self.account}/{EDGES[kind]}", data=data, write=True)
        object_id = str(created.get("id") or "")
        if not object_id:
            raise MetaApiError(f"Meta created a {kind} but returned no id")
        return self.get(kind, object_id)

    def _promoted_object(self, event: str) -> dict[str, Any]:
        pixel = _need(self.pixel_id, "META_PIXEL_ID", "meta create_adset")
        if event in self.custom_conversions:
            return {"pixel_id": pixel, "custom_event_type": "OTHER", "custom_conversion_id": self.custom_conversions[event]}
        if event in STANDARD_EVENTS:
            return {"pixel_id": pixel, "custom_event_type": STANDARD_EVENTS[event]}
        raise MetaApiError(f"optimisation event {event!r} is a custom pixel event; Meta optimises it through a custom conversion: "
                           f"add {event}=<id> to META_CUSTOM_CONVERSIONS")

    def _upload_image(self, image_url: str) -> str:
        data = self._fetch_image(image_url)
        if not data:
            raise MetaApiError(f"creative image {image_url} is empty")
        images = self._request("POST", f"{self.account}/adimages", data={"bytes": base64.b64encode(data).decode()}, write=True).get("images")
        for image in (images or {}).values():
            if isinstance(image, dict) and image.get("hash"):
                return str(image["hash"])
        raise MetaApiError("adimages answered without an image hash")

    def _scan(self, kind: str, edge: str, name: str, params: dict[str, Any]) -> dict[str, Any] | None:
        for row in self._pages(f"{self.account}/{edge}", params):
            if row.get("name") == name:
                return self._normalise(kind, row)
        return None

    def _pages(self, path: str, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
        params = dict(params)
        while True:
            page = self._request("GET", path, params=params)
            yield from page.get("data") or []
            paging = page.get("paging") or {}
            after = (paging.get("cursors") or {}).get("after")
            if not paging.get("next") or not after:
                return
            params["after"] = after

    def _await_report(self, report: str) -> None:
        """Poll the async job until Meta says `Job Completed` at 100%; waits double up to MAX_POLL_INTERVAL."""
        deadline = self._clock() + self.insights_timeout
        interval = self.poll_interval
        while True:
            run = self._request("GET", report)
            status = run.get("async_status")
            if status == "Job Completed" and _int(run.get("async_percent_completion")) >= 100:
                return
            if status in ("Job Failed", "Job Skipped"):
                reason = run.get("error_message") or run.get("error_user_title") or "no reason given"
                raise MetaApiError(self._scrub(f"insights report {report} {status}: ({run.get('error_code')}/{run.get('error_subcode')}) {reason}"))
            if self._clock() + interval > deadline:
                raise MetaApiError(f"insights report {report} still {status!r} after {self.insights_timeout:.0f}s; the next pull asks again")
            self._sleep(interval)
            interval = min(interval * 2, MAX_POLL_INTERVAL)

    # ---- the wire ------------------------------------------------------------------------------
    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, data: dict[str, Any] | None = None,
                 write: bool = False) -> dict[str, Any]:
        deadline = self._clock() + self.max_wait
        attempt, just_waited = 0, False
        while True:
            if not just_waited:
                self._pace(deadline)
            just_waited = False
            try:
                resp = self._http.request(method, path, params=_encode(params), data=_encode(data))
            except httpx.TransportError as exc:
                if write:
                    raise MetaApiError(f"Meta {method} {path}: {type(exc).__name__}; the write may have landed, so it is not re-sent "
                                       "(the executor's name lookup decides on the next run)") from None
                wait = self._backoff(attempt)
                if not self._fits(wait, deadline):
                    raise MetaApiError(f"Meta {method} {path}: {type(exc).__name__} after {attempt + 1} attempt(s)") from None
                self._sleep(wait)
                attempt, just_waited = attempt + 1, True
                continue
            self.last_headers = {h: resp.headers[h] for h in USAGE_HEADERS if h in resp.headers}
            try:
                body = resp.json()
            except ValueError:
                body = {}
            error = body.get("error") if isinstance(body, dict) else None
            if resp.is_success and not error:
                return body if isinstance(body, dict) else {"data": body}
            error = error if isinstance(error, dict) else {}
            code = None if _num(error.get("code")) is None else _int(error.get("code"))
            if code in THROTTLE_CODES:
                wait = self._header_wait() or self._backoff(attempt)
                if self._fits(wait, deadline):
                    self._sleep(wait)
                    attempt, just_waited = attempt + 1, True
                    continue
                raise MetaThrottled(self._describe(method, path, resp, error) + "; throttled, usage headers attached", dict(self.last_headers))
            transient = resp.status_code >= 500 or error.get("is_transient") is True or code in (1, 2)
            if transient and not write:
                wait = self._backoff(attempt)
                if self._fits(wait, deadline):
                    self._sleep(wait)
                    attempt, just_waited = attempt + 1, True
                    continue
            exc = MetaApiError(self._describe(method, path, resp, error) + ("; not re-sent" if transient and write else ""))
            exc.code, exc.subcode = code, None if _num(error.get("error_subcode")) is None else _int(error.get("error_subcode"))
            raise exc

    def _describe(self, method: str, path: str, resp: httpx.Response, error: dict[str, Any]) -> str:
        code = error.get("code", "-")
        sub = error.get("error_subcode")
        text = f"Meta {method} {path} failed: HTTP {resp.status_code}, code {code}{f'/{sub}' if sub else ''}: {error.get('message') or resp.reason_phrase}"
        if error.get("error_user_title"):
            text += f" ({error['error_user_title']})"
        return self._scrub(text)

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "[token]") if self._token else text

    def _fits(self, wait: float, deadline: float) -> bool:
        return self._clock() + wait <= deadline

    @staticmethod
    def _backoff(attempt: int) -> float:
        return BACKOFF_BASE * 2 ** attempt

    def _header_wait(self) -> float | None:
        """Seconds the last usage headers ask for: estimated_time_to_regain_access (minutes) and reset_time_duration."""
        waits: list[float] = []
        buc = _loads(self.last_headers.get("x-business-use-case-usage"))
        for entries in (buc.values() if isinstance(buc, dict) else []):
            for entry in entries if isinstance(entries, list) else []:
                minutes = _num(entry.get("estimated_time_to_regain_access")) if isinstance(entry, dict) else None
                if minutes is not None:
                    waits.append(minutes * 60)
        account = _loads(self.last_headers.get("x-ad-account-usage"))
        if isinstance(account, dict) and _num(account.get("reset_time_duration")) is not None:
            waits.append(_num(account["reset_time_duration"]))
        return max(waits) if waits else None

    def _utilisation(self) -> float:
        values: list[float] = []
        buc = _loads(self.last_headers.get("x-business-use-case-usage"))
        for entries in (buc.values() if isinstance(buc, dict) else []):
            for entry in entries if isinstance(entries, list) else []:
                if isinstance(entry, dict):
                    values += [v for k in ("call_count", "total_cputime", "total_time") if (v := _num(entry.get(k))) is not None]
        for header, keys in (("x-ad-account-usage", ("acc_id_util_pct",)), ("x-app-usage", ("call_count", "total_cputime", "total_time")),
                             ("x-fb-ads-insights-throttle", ("app_id_util_pct", "acc_id_util_pct"))):
            usage = _loads(self.last_headers.get(header))
            if isinstance(usage, dict):
                values += [v for k in keys if (v := _num(usage.get(k))) is not None]
        return max(values) if values else 0.0

    def _pace(self, deadline: float) -> None:
        if self._utilisation() < PACE_AT:
            return
        wait = self._header_wait()
        wait = PACE_DEFAULT_WAIT if wait is None else wait
        if wait > 0 and self._fits(wait, deadline):
            self._sleep(wait)

    # ---- normalising Meta's answers to the fake's shapes ----------------------------------------
    def _normalise(self, kind: str, raw: dict[str, Any]) -> dict[str, Any]:
        base = {"id": str(raw.get("id")), "name": raw.get("name"), "status": raw.get("status")}
        if kind == "campaign":
            return {**base, "effective_status": raw.get("effective_status"), "objective": raw.get("objective"),
                    "daily_budget": self.from_minor(raw.get("daily_budget")), "created_time": raw.get("created_time")}
        if kind == "adset":
            return {**base, "effective_status": raw.get("effective_status"), "campaign_id": _str_or_none(raw.get("campaign_id")),
                    "daily_budget": self.from_minor(raw.get("daily_budget")), "optimization_event": self._event_of(raw.get("promoted_object")),
                    "targeting": our_targeting(raw.get("targeting")), "created_time": raw.get("created_time")}
        if kind == "creative":
            spec = raw.get("object_story_spec") or {}
            link = spec.get("link_data") or {}
            return {**base, "page_id": _str_or_none(spec.get("page_id")), "image_hash": link.get("image_hash"),
                    "image_url": link.get("picture"), "body": link.get("message"), "title": link.get("name"),
                    "link_url": link.get("link"), "created_time": raw.get("created_time")}
        feedback = raw.get("ad_review_feedback") if isinstance(raw.get("ad_review_feedback"), dict) else {}
        return {**base, "effective_status": raw.get("effective_status"), "adset_id": _str_or_none(raw.get("adset_id")),
                "campaign_id": _str_or_none(raw.get("campaign_id")), "creative_id": _str_or_none((raw.get("creative") or {}).get("id")),
                "ad_review_feedback": feedback, "review_status": review_status(raw.get("effective_status"), feedback),
                "created_time": raw.get("created_time")}

    def _event_of(self, promoted: Any) -> str | None:
        promoted = promoted if isinstance(promoted, dict) else {}
        cid = str(promoted.get("custom_conversion_id") or "")
        for event, known in self.custom_conversions.items():
            if cid and known == cid:
                return event
        return next((event for event, meta_type in STANDARD_EVENTS.items() if meta_type == promoted.get("custom_event_type")), None)

    def _action_types(self) -> dict[str, tuple[str, ...]]:
        """Our event name → Meta action types that count it, in priority order; the first one present wins."""
        names = [*EVENT_ORDER, *(e for e in self.custom_conversions if e not in EVENT_ORDER)]
        out: dict[str, tuple[str, ...]] = {}
        for name in names:
            types = ((f"offsite_conversion.custom.{self.custom_conversions[name]}",) if name in self.custom_conversions else ()) \
                + STANDARD_ACTION_TYPES.get(name, ())
            if types:
                out[name] = types
        return out

    def _insight_row(self, level: str, raw: dict[str, Any]) -> dict[str, Any]:
        spend = round(float(Decimal(str(raw.get("spend") or 0))), 2)
        if level == "account":
            return {"date_start": raw.get("date_start"), "date_stop": raw.get("date_stop"), "spend": spend, "impressions": _int(raw.get("impressions"))}
        by_type = {a.get("action_type"): a.get("value") for a in raw.get("actions") or [] if isinstance(a, dict)}
        actions = []
        for name, types in self._action_types().items():
            hit = next((t for t in types if t in by_type), None)
            if hit is not None:
                actions.append({"action_type": name, "value": _int(by_type[hit])})
        return {"date_start": raw.get("date_start"), "date_stop": raw.get("date_stop"), "ad_id": _str_or_none(raw.get("ad_id")),
                "ad_name": raw.get("ad_name"), "adset_id": _str_or_none(raw.get("adset_id")), "campaign_id": _str_or_none(raw.get("campaign_id")),
                "impressions": _int(raw.get("impressions")), "reach": _int(raw.get("reach")), "clicks": _int(raw.get("clicks")),
                "link_clicks": _int(raw.get("inline_link_clicks")), "spend": spend, "frequency": _num(raw.get("frequency")),
                "video_3s": _int(by_type[VIDEO_3S_ACTION]) if VIDEO_3S_ACTION in by_type else None, "actions": actions}


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def meta_targeting(targeting: dict[str, Any]) -> dict[str, Any]:
    """Our launch targeting {geo, age_min, age_max} (warehouse/launch.py) as Meta's spec, Advantage+ audience off so the
    configured geo and age band are constraints, not suggestions. A spec already in Meta's shape passes through."""
    if "geo_locations" in targeting:
        return dict(targeting)
    countries = [str(c) for c in targeting.get("geo") or []]
    if not countries:
        raise MetaApiError("targeting needs at least one country in `geo`")
    spec: dict[str, Any] = {"geo_locations": {"countries": countries}}
    for key in ("age_min", "age_max"):
        if targeting.get(key) is not None:
            spec[key] = int(targeting[key])
    spec["targeting_automation"] = {"advantage_audience": 0}
    return spec


def our_targeting(spec: Any) -> dict[str, Any] | None:
    if not isinstance(spec, dict):
        return None
    out: dict[str, Any] = {"geo": list((spec.get("geo_locations") or {}).get("countries") or [])}
    for key in ("age_min", "age_max"):
        if spec.get(key) is not None:
            out[key] = spec[key]
    return out
