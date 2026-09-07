"""The `/quiz` and `/cal-webhook` function code, framework-free: `handle(Request, Deps) -> Response`.

Routes (all JSON):
  GET  /quiz/config?client=<slug>   what the page renders: questions, notice version, pixel / Turnstile keys
  POST /quiz/start                  consent passed, question 1 shown → `quiz_start` RPC; CAPI QuizStart (tracking consent only)
  POST /quiz                        answers + contact → `quiz_complete` RPC; CAPI QuizComplete once per lead
  POST /cal-webhook                 Cal.com booking, HMAC-verified → `lead_booked` RPC; CAPI Schedule once per lead

Rules enforced here: consent before any CAPI call (FR-33); Turnstile + per-IP rate limit on every POST;
the raw fbclid is hashed before it reaches the RPC and only ever sent in-flight to CAPI as `fbc` (DR-4);
a forged webhook is rejected with 401 and logged (FR-34); the `app` role is the only warehouse identity
here and it reaches tables through the 0004 RPCs only. Logs never carry PII: lead ids, never emails.
funnel/server.py runs this locally on FUNNEL_HOST; T13 ports it to the go-upclicklabs functions.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

from adapters.capi import Capi, get_capi, hash_user_field  # noqa: E402
from adapters.env import load_env  # noqa: E402
from adapters.turnstile import Turnstile, get_turnstile  # noqa: E402
from funnel import quiz  # noqa: E402
from warehouse.client import connect  # noqa: E402

MAX_BODY = 16 * 1024
DEFAULT_CLIENT = "upclicklabs"


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)   # lower-cased names
    body: bytes = b""
    remote_ip: str = "127.0.0.1"

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


@dataclass
class Response:
    status: int
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> bytes:
        return json.dumps(self.body, default=str).encode()


class RateLimiter:
    """Sliding one-minute window per key. Enforced even when TURNSTILE_BACKEND=pass (dev-mode.md)."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and q[0] <= now - 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            return True


@dataclass
class Deps:
    """Everything with a side effect, injected so tests can point them at scratch state."""
    db: Callable[[], psycopg.Connection]
    capi: Capi
    turnstile: Turnstile
    limiter: RateLimiter
    log: Callable[..., None]
    cal_webhook_secret: str
    funnel_host: str
    pixel_id: str | None = None
    turnstile_site_key: str | None = None
    test_event_code: str | None = None
    now: Callable[[], float] = time.time


def log_json(event: str, **fields: Any) -> None:
    """One JSON line per event on stderr (Vercel / Supabase collect stderr as function logs)."""
    print(json.dumps({"event": event, **fields}, default=str), file=sys.stderr, flush=True)


def deps_from_env() -> Deps:
    """Wire the dev / live backends from the environment (adapters own the env vars)."""
    load_env()
    return Deps(
        db=lambda: connect("app", job="quiz", autocommit=True),
        capi=get_capi(),
        turnstile=get_turnstile(),
        limiter=RateLimiter(int(os.environ.get("RATE_LIMIT_PER_MINUTE") or 20)),
        log=log_json,
        cal_webhook_secret=os.environ.get("CAL_WEBHOOK_SECRET") or "",
        funnel_host=os.environ.get("FUNNEL_HOST") or "http://localhost:8788",
        pixel_id=os.environ.get("META_PIXEL_ID") or None,
        turnstile_site_key=os.environ.get("TURNSTILE_SITE_KEY") or None,
        test_event_code=os.environ.get("META_TEST_EVENT_CODE") or None,
    )


# ---------- dispatch ----------

def handle(req: Request, deps: Deps) -> Response:
    path = req.path.rstrip("/") or "/"
    try:
        if req.method == "GET" and path == "/quiz/config":
            return get_config(req, deps)
        if req.method == "POST" and path == "/quiz/start":
            return post_start(req, deps)
        if req.method == "POST" and path == "/quiz":
            return post_complete(req, deps)
        if req.method == "POST" and path == "/cal-webhook":
            return post_cal_webhook(req, deps)
    except quiz.Invalid as exc:
        return Response(400, {"error": str(exc)})
    except psycopg.errors.NoDataFound as exc:
        return Response(404, {"error": _pg_message(exc)})
    except psycopg.errors.CheckViolation as exc:
        return Response(400, {"error": _pg_message(exc)})
    return Response(404, {"error": f"no route for {req.method} {path}"})


def _pg_message(exc: psycopg.Error) -> str:
    return (exc.diag.message_primary if exc.diag else str(exc)) or "database error"


def _json_body(req: Request) -> Any:
    if len(req.body) > MAX_BODY:
        raise quiz.Invalid("body: too large")
    try:
        return json.loads(req.body or b"null")
    except ValueError:
        raise quiz.Invalid("body: not JSON") from None


def _gate(req: Request, deps: Deps, bucket: str) -> Response | None:
    """Per-IP rate limit for every POST. Returns the 429 to send, or None to continue."""
    if not deps.limiter.allow(f"{bucket}:{req.remote_ip}"):
        deps.log("rate_limited", route=bucket, ip=req.remote_ip)
        return Response(429, {"error": "too many requests; try again in a minute"}, {"Retry-After": "60"})
    return None


def _turnstile(req: Request, deps: Deps, token: str) -> Response | None:
    if not deps.turnstile.verify(token, req.remote_ip):
        deps.log("turnstile_failed", ip=req.remote_ip)
        return Response(403, {"error": "verification failed; reload and try again"})
    return None


def _config(conn: psycopg.Connection, slug: str) -> dict[str, Any]:
    row = conn.execute("select quiz_config(%s::text) as cfg", (slug,)).fetchone()
    cfg = row["cfg"] if row else None
    if not cfg:
        raise quiz.Invalid("client: unknown")
    return cfg


def _notice_version(quiz_config: dict[str, Any]) -> str:
    return str(quiz_config.get("consent_notice_version") or quiz_config.get("version") or "v1")


# ---------- routes ----------

def get_config(req: Request, deps: Deps) -> Response:
    slug = req.query.get("client") or DEFAULT_CLIENT
    with deps.db() as conn:
        cfg = _config(conn, slug)
    qc = cfg.get("quiz_config") or {}
    questions = [{"id": q["id"], "text": q.get("text", ""), "options": list(q.get("options", []))}
                 for q in qc.get("questions", []) if isinstance(q, dict) and "id" in q]
    return Response(200, {
        "client": slug,
        "offer_name": cfg.get("offer_name"),
        "promise": cfg.get("promise"),
        "quiz_version": qc.get("version"),
        "notice_version": _notice_version(qc),
        "questions": questions,
        "pixel_id": deps.pixel_id,
        "turnstile_site_key": deps.turnstile_site_key,
    })


def post_start(req: Request, deps: Deps) -> Response:
    if r := _gate(req, deps, "start"):
        return r
    body = quiz.validate_start(_json_body(req))
    if r := _turnstile(req, deps, body["turnstile_token"]):
        return r
    utm = body.get("utm") or {}
    fbclid = body.get("fbclid") or None
    source = "meta" if fbclid or utm.get("source") in ("facebook", "fb", "instagram", "ig", "meta") else (utm.get("source") or "direct")
    with deps.db() as conn:
        cfg = _config(conn, body["client"])
        qc = cfg.get("quiz_config") or {}
        consent = quiz.consent_record(body["consent"], _notice_version(qc))
        row = conn.execute(
            "select * from quiz_start(%s::text, %s::jsonb, %s::jsonb, %s::text, %s::text, %s::text)",
            (body["client"], Jsonb(consent), Jsonb(utm), quiz.hash_fbclid(fbclid), qc.get("version"), source),
        ).fetchone()
    lead_id = str(row["lead_id"])
    deps.log("quiz_start", lead_id=lead_id, client=body["client"], creative_id=row["creative_id"], tracking=consent["tracking"])
    out: dict[str, Any] = {"lead_id": lead_id, "quiz_version": qc.get("version"), "event_id": None}
    if consent["tracking"]:
        eid = quiz.event_id(lead_id, "QuizStart")
        _send_event(deps, req, "QuizStart", eid, lead_id, fbclid=fbclid,
                    custom={"utm_content": utm.get("content"), "quiz_version": qc.get("version")})
        out["event_id"] = eid
    return Response(200, out)


def post_complete(req: Request, deps: Deps) -> Response:
    if r := _gate(req, deps, "complete"):
        return r
    raw = _json_body(req)
    if not isinstance(raw, dict) or "client" not in raw:
        raise quiz.Invalid("client: required")
    with deps.db() as conn:
        cfg = _config(conn, str(raw.get("client")))
        qc = cfg.get("quiz_config") or {}
        body = quiz.validate_complete(raw, qc)
        if r := _turnstile(req, deps, body["turnstile_token"]):
            return r
        score = quiz.qualification_score(body["answers"], qc)
        contact = body["contact"]
        row = conn.execute(
            "select * from quiz_complete(%s::uuid, %s::jsonb, %s::numeric, %s::text, %s::text, %s::text)",
            (body["lead_id"], Jsonb(body["answers"]), score, contact["email"], contact.get("name") or None,
             contact.get("phone") or None),
        ).fetchone()
    lead_id = body["lead_id"].lower()
    qualified = quiz.qualifies(score, qc)
    deps.log("quiz_complete", lead_id=lead_id, transitioned=row["transitioned"], score=score, qualified=qualified)
    out: dict[str, Any] = {
        "lead_id": lead_id, "qualification_score": score, "qualified": qualified,
        "calendar_url": quiz.booking_link(cfg.get("calendar_url"), lead_id) if qualified else None,
        "event_id": None,
    }
    if row["transitioned"] and row["tracking_consent"]:
        eid = quiz.event_id(lead_id, "QuizComplete")
        _send_event(deps, req, "QuizComplete", eid, lead_id, email=contact["email"],
                    custom={"utm_content": row["creative_id"], "quiz_version": qc.get("version"),
                            "qualification_score": score})
        out["event_id"] = eid
    return Response(200, out)


def post_cal_webhook(req: Request, deps: Deps) -> Response:
    if r := _gate(req, deps, "cal-webhook"):
        return r
    if len(req.body) > MAX_BODY * 4:
        deps.log("cal_webhook_rejected", reason="too_large", ip=req.remote_ip)
        return Response(413, {"error": "too large"})
    sig = req.header("x-cal-signature-256")
    if not quiz.cal_signature_ok(deps.cal_webhook_secret, req.body, sig):
        deps.log("cal_webhook_rejected", reason="bad_signature" if sig else "missing_signature", ip=req.remote_ip)
        return Response(401, {"error": "invalid signature"})
    try:
        payload = json.loads(req.body)
    except ValueError:
        deps.log("cal_webhook_rejected", reason="not_json", ip=req.remote_ip)
        return Response(400, {"error": "not JSON"})
    if not isinstance(payload, dict):
        deps.log("cal_webhook_rejected", reason="not_object", ip=req.remote_ip)
        return Response(400, {"error": "not an object"})
    trigger = payload.get("triggerEvent")
    if trigger != "BOOKING_CREATED":
        deps.log("cal_webhook_ignored", trigger=trigger)
        return Response(200, {"updated": False, "ignored": trigger})
    lead_id = quiz.booking_lead_id(payload)
    if not lead_id:
        deps.log("cal_webhook_unmatched", reason="no_lead_id", uid=(payload.get("payload") or {}).get("uid"))
        return Response(202, {"updated": False, "unmatched": True})
    booked_at = (payload.get("payload") or {}).get("startTime") or payload.get("createdAt")
    with deps.db() as conn:
        try:
            row = conn.execute("select * from lead_booked(%s::uuid, %s::timestamptz)", (lead_id, booked_at)).fetchone()
        except psycopg.errors.NoDataFound:
            deps.log("cal_webhook_unmatched", reason="unknown_lead", lead_id=lead_id)
            return Response(202, {"updated": False, "unmatched": True})
        except psycopg.errors.InvalidDatetimeFormat:
            row = conn.execute("select * from lead_booked(%s::uuid, null)", (lead_id,)).fetchone()
    deps.log("lead_booked", lead_id=lead_id, updated=row["updated"])
    out: dict[str, Any] = {"updated": row["updated"], "event_id": None}
    if row["updated"] and row["tracking_consent"]:
        eid = quiz.event_id(lead_id, "Schedule")
        _send_event(deps, req, "Schedule", eid, lead_id, action_source="system_generated",
                    custom={"utm_content": row["creative_id"]})
        out["event_id"] = eid
    return Response(200, out)


# ---------- CAPI ----------

def _send_event(deps: Deps, req: Request, name: str, eid: str, lead_id: str, *, fbclid: str | None = None,
                email: str | None = None, action_source: str = "website", custom: dict[str, Any] | None = None) -> None:
    """Server-side event with the shared event_id. Called only after the consent check by the route."""
    now = int(deps.now())
    user_data: dict[str, Any] = {"external_id": [hash_user_field(lead_id)]}
    if action_source == "website":
        user_data["client_ip_address"] = req.remote_ip
        ua = req.header("user-agent")
        if ua:
            user_data["client_user_agent"] = ua[:512]
    if fbclid:
        user_data["fbc"] = quiz.fbc_param(fbclid, now * 1000)
    if email:
        user_data["em"] = [hash_user_field(email)]
    host = urlsplit(deps.funnel_host)
    deps.capi.send(
        event_name=name, event_id=eid, event_time=now,
        event_source_url=f"{host.scheme}://{host.netloc}/quiz",
        action_source=action_source, user_data=user_data,
        custom_data={k: (str(v) if v is not None else None) for k, v in (custom or {}).items() if v is not None},
        test_event_code=deps.test_event_code,
    )
    deps.log("capi_sent", event_name=name, event_id=eid)
