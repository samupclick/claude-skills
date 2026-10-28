"""WSGI adapter for funnel/app.py's handle(Request, Deps): what the Vercel Python runtime calls through api/funnel.py.
FR-32 to FR-35, DR-4, NFR-1.

- one Deps per process, built on the first request (the cold start). The warehouse is role `app` from
  WAREHOUSE_URL_APP only, checked once per process with `current_user`: any other login, a superuser or a BYPASSRLS
  role is refused
- on Vercel (VERCEL=1) the function serves only with CAPI_BACKEND=live and TURNSTILE_BACKEND=live, and never while
  credentials that belong to other jobs are in its environment (the other WAREHOUSE_URL_* roles, META_ACCESS_TOKEN,
  META_READ_TOKEN). Refusals are a 503 and one `function_misconfigured` log line naming variables, never values
- the visitor IP comes from Vercel's x-vercel-forwarded-for / x-real-ip / x-forwarded-for (Vercel overwrites them; the
  first valid address wins); bodies over 64 KB are refused unread
- vercel.json sends the four routes to FUNCTION_PATH with a `route` hint, used only when the runtime hands the
  function its own path instead of the visitor's
- an unexpected error is a 500 with no detail and one `function_error` log line carrying its type only
"""
from __future__ import annotations

import ipaddress
import os
import threading
from http import HTTPStatus
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import parse_qsl

import psycopg

from adapters.capi import CapiError
from adapters.env import MissingEnvVar, UnknownBackend
from funnel.app import Deps, Request, Response, deps_from_env, handle, log_json

FUNCTION_PATH = "/api/funnel"
ROUTE_HINTS = {"config": "/quiz/config", "start": "/quiz/start", "complete": "/quiz", "cal-webhook": "/cal-webhook"}
MAX_READ = 64 * 1024
APP_URL = "WAREHOUSE_URL_APP"
FOREIGN_CREDENTIALS = ("META_ACCESS_TOKEN", "META_READ_TOKEN")   # plus every WAREHOUSE_URL_* but APP_URL
LIVE_ON_VERCEL = ("CAPI_BACKEND", "TURNSTILE_BACKEND")
IP_HEADERS = ("HTTP_X_VERCEL_FORWARDED_FOR", "HTTP_X_REAL_IP", "HTTP_X_FORWARDED_FOR", "REMOTE_ADDR")


class Misconfigured(RuntimeError):
    """The function's environment or warehouse login is wrong for this job. Names variables and roles, never values."""


def check_environment(environ: Mapping[str, str] = os.environ) -> None:
    roles = sorted(n for n in environ if n.startswith("WAREHOUSE_URL_") and n != APP_URL and environ.get(n))
    foreign = roles + [n for n in FOREIGN_CREDENTIALS if environ.get(n)]
    if foreign:
        raise Misconfigured(f"the funnel function must not hold {', '.join(foreign)}: those belong to other jobs "
                            "(SKILL.md §1); remove them from this Vercel project")
    if environ.get("VERCEL"):
        for var in LIVE_ON_VERCEL:
            if environ.get(var) != "live":
                raise Misconfigured(f"{var} must be live on Vercel (the dev backends neither send nor check anything)")


def app_role_db(connect_app: Callable[[], psycopg.Connection]) -> Callable[[], psycopg.Connection]:
    """Wrap the `app` connection factory so the first connection proves who it logged in as."""
    verified = threading.Event()

    def db() -> psycopg.Connection:
        conn = connect_app()
        if not verified.is_set():
            row = conn.execute("select current_user as role, r.rolsuper as su, r.rolbypassrls as bypass "
                               "from pg_roles r where r.rolname = current_user").fetchone()
            role, su, bypass = (row["role"], row["su"], row["bypass"]) if isinstance(row, dict) else row
            if role != "app" or su or bypass:
                conn.close()
                flags = "".join(f" ({f})" for f, on in (("superuser", su), ("BYPASSRLS", bypass)) if on)
                raise Misconfigured(f"WAREHOUSE_URL_APP logs in as {role}{flags}; the funnel function connects as role app only")
            verified.set()
        return conn

    return db


def serverless_deps() -> Deps:
    check_environment()
    deps = deps_from_env()
    deps.db = app_role_db(deps.db)
    if os.environ.get("VERCEL_ENV") == "production" and deps.test_event_code:
        log_json("capi_test_mode_in_production", variable="META_TEST_EVENT_CODE",
                 note="server events go to Events Manager's test tab; unset it in the Production environment")
    return deps


def client_ip(environ: Mapping[str, Any]) -> str:
    for key in IP_HEADERS:
        value = environ.get(key)
        if value:
            try:
                return str(ipaddress.ip_address(str(value).split(",")[0].strip()))
            except ValueError:
                continue
    return "0.0.0.0"


def _text(value: str) -> str:
    """Undo PEP 3333's latin-1 transport of str values (the runtime encodes UTF-8 bytes that way)."""
    try:
        return value.encode("latin1").decode("utf-8", "replace")
    except UnicodeEncodeError:
        return value


def request_from_environ(environ: Mapping[str, Any]) -> Request | Response:
    query = dict(parse_qsl(environ.get("QUERY_STRING") or ""))
    hint = query.pop("route", None)
    path = _text(environ.get("PATH_INFO") or "/")
    if path.rstrip("/") == FUNCTION_PATH:
        path = ROUTE_HINTS.get(hint or "", path)
    headers = {k[5:].replace("_", "-").lower(): _text(str(v)) for k, v in environ.items() if k.startswith("HTTP_")}
    if environ.get("CONTENT_TYPE"):
        headers["content-type"] = environ["CONTENT_TYPE"]
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return Response(400, {"error": "bad content-length"})
    if length > MAX_READ:
        return Response(413, {"error": "too large"})
    body = environ["wsgi.input"].read(length) if length > 0 else b""
    return Request(method=str(environ.get("REQUEST_METHOD") or "GET").upper(), path=path, query=query, headers=headers,
                   body=body, remote_ip=client_ip(environ))


def _safe(exc: BaseException) -> str:
    if isinstance(exc, (Misconfigured, MissingEnvVar, UnknownBackend, CapiError)):
        return f"{type(exc).__name__}: {exc}"
    return type(exc).__name__


def _respond(start_response: Callable[..., Any], res: Response) -> Iterable[bytes]:
    data = res.json()
    headers = [("Content-Type", "application/json"), ("Content-Length", str(len(data))), ("Cache-Control", "no-store"),
               ("X-Content-Type-Options", "nosniff"), *res.headers.items()]
    start_response(f"{res.status} {HTTPStatus(res.status).phrase}", headers)
    return [data]


def make_app(build_deps: Callable[[], Deps], log: Callable[..., None] = log_json) -> Callable[..., Iterable[bytes]]:
    """A WSGI callable over handle(); `build_deps` runs on the first request and again after a failure."""
    lock = threading.Lock()
    built: list[Deps] = []

    def deps() -> Deps:
        with lock:
            if not built:
                built.append(build_deps())
            return built[0]

    def app(environ, start_response):
        req = request_from_environ(environ)
        if isinstance(req, Response):
            return _respond(start_response, req)
        try:
            res = handle(req, deps())
        except (Misconfigured, MissingEnvVar, UnknownBackend, CapiError) as exc:   # handle() logs CAPI send failures itself
            log("function_misconfigured", error=_safe(exc))
            res = Response(503, {"error": "service unavailable"})
        except Exception as exc:
            log("function_error", method=req.method, path=req.path, error=_safe(exc))
            res = Response(500, {"error": "internal error"})
        return _respond(start_response, res)

    return app
