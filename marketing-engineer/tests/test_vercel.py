"""Vercel packaging of the quiz funnel (api/funnel.py, funnel/wsgi.py, vercel.json, .vercelignore, api/requirements.txt).
No Vercel account exists, so nothing is deployed: the function is invoked the way vercel-runtime 0.24.1 does
(vercel_runtime/vc_init.py and resolver.py, read 2026-10-28 from the published wheel), the upload set is computed from
.vercelignore with git's gitignore matcher, and the uploaded files alone are imported in an isolated interpreter against
the test warehouse. CAPI and Turnstile are the live adapters on httpx.MockTransport. FR-32 to FR-35, DR-4, NFR-1."""
from __future__ import annotations

import ast
import http.client
import importlib.metadata
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import psycopg
import pytest

from adapters.capi import hash_user_field
from adapters.capi.live import LiveCapi
from adapters.turnstile.live import LiveTurnstile
from funnel import quiz
from funnel.app import Deps, RateLimiter
from funnel.wsgi import (FUNCTION_PATH, ROUTE_HINTS, Misconfigured, app_role_db, check_environment, client_ip,
                         make_app)
from warehouse.client import connect

ME_DIR = Path(__file__).resolve().parent.parent
VERCEL = json.loads((ME_DIR / "vercel.json").read_text())
PIXEL = "123456789012345"
TOKEN = "EAAC-capi-token-never-printed"
SECRET = "0x4AAAA-turnstile-secret-never-printed"
CAL = "cal-secret"
IP = "203.0.113.7"
UA = "Mozilla/5.0 (Vercel test)"
GOOD = {"q1": "B2B services", "q2": "Referrals", "q3": "No"}


# ---------- the runtime, as vc_init 0.24.1 runs a WSGI app ----------

def load_entrypoint(root: Path):
    """vercel_runtime.resolver.import_module: spec_from_file_location under a module name, then the top-level variable."""
    spec = importlib.util.spec_from_file_location(f"vc_entry_{abs(hash(str(root)))}", root / "api" / "funnel.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def positional_params(obj) -> int:
    """vercel_runtime.resolver._get_positional_param_count: 2 means WSGI (environ, start_response)."""
    return sum(1 for p in inspect.signature(obj).parameters.values()
               if p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD))


class VercelRuntime:
    """vc_init's WSGI Handler on a ThreadingHTTPServer (127.0.0.1, ephemeral port); `call` proxies one request the way
    vc_handler does (http.client with the event's method, path and header pairs, content-length added when missing)."""

    def __init__(self, app):
        wsgi_app = app

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_request(self):
                parts = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                env = {
                    "CONTENT_LENGTH": str(len(body)), "CONTENT_TYPE": self.headers.get("content-type", ""),
                    "SCRIPT_NAME": "", "PATH_INFO": parts.path, "QUERY_STRING": parts.query,
                    "REMOTE_ADDR": self.headers.get("x-forwarded-for", self.headers.get("x-real-ip")),
                    "REQUEST_METHOD": self.command, "SERVER_NAME": self.headers.get("host", "lambda"),
                    "SERVER_PORT": self.headers.get("x-forwarded-port", "80"), "SERVER_PROTOCOL": "HTTP/1.1",
                    "wsgi.errors": sys.stderr, "wsgi.input": BytesIO(body), "wsgi.multiprocess": False,
                    "wsgi.multithread": False, "wsgi.run_once": False,
                    "wsgi.url_scheme": self.headers.get("x-forwarded-proto", "http"), "wsgi.version": (1, 0),
                }
                for key, value in env.items():
                    if isinstance(value, str):
                        env[key] = value.encode("utf-8").decode("latin1", "replace")
                for k, v in self.headers.items():
                    if k.lower() != "transfer-encoding":
                        env["HTTP_" + k.replace("-", "_").upper()] = v

                def start_response(status, headers, exc_info=None):
                    self.send_response(int(status.split(" ", maxsplit=1)[0]))
                    for name, value in headers:
                        self.send_header(name, value)
                    self.end_headers()
                    return self.wfile.write

                response = wsgi_app(env, start_response)
                try:
                    for data in response:
                        if data:
                            self.wfile.write(data)
                            self.wfile.flush()
                finally:
                    if hasattr(response, "close"):
                        response.close()

            do_GET = do_POST = do_PUT = do_DELETE = do_OPTIONS = handle_request

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def call(self, method: str, target: str, body: bytes | dict | None = None, headers: dict | None = None):
        data = json.dumps(body).encode() if isinstance(body, dict) else (body or b"")
        pairs = {"host": "go.upclicklabs.com", "x-forwarded-for": IP, "x-real-ip": IP, "x-vercel-forwarded-for": IP,
                 "x-forwarded-proto": "https", "user-agent": UA, "content-type": "application/json", **(headers or {})}
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=30)
        try:
            conn.putrequest(method, target, skip_host=True, skip_accept_encoding=True)
            for k, v in pairs.items():
                conn.putheader(k, v)
            conn.putheader("content-length", str(len(data)))
            conn.endheaders(data)
            res = conn.getresponse()
            raw = res.read()
            return res.status, {k.lower(): v for k, v in res.getheaders()}, json.loads(raw) if raw else None
        finally:
            conn.close()


# ---------- vendor stubs (fixtures/capi, fixtures/turnstile) ----------

def fixture(vendor: str, name: str) -> tuple[int, dict]:
    raw = json.loads((ME_DIR / "fixtures" / vendor / f"{name}.json").read_text())
    raw.pop("_shape")
    return raw.pop("_status", 200), raw


class Vendors:
    """graph.facebook.com /events and Cloudflare siteverify, each recording what it was sent. siteverify treats tokens
    as single-use, the way Cloudflare documents it."""

    def __init__(self):
        self.events: list[dict] = []
        self.capi_forms: list[dict] = []
        self.siteverify_forms: list[dict] = []
        self.seen_tokens: set[str] = set()

    def graph(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.capi_forms.append({**form, "path": request.url.path})
        self.events.extend(json.loads(form["data"]))
        status, body = fixture("capi", "events_received")
        return httpx.Response(status, json=body)

    def siteverify(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.siteverify_forms.append(form)
        token = form["response"]
        name = "timeout_or_duplicate" if token in self.seen_tokens else ("success" if token.startswith("good-") else "invalid_response")
        self.seen_tokens.add(token)
        return httpx.Response(200, json=fixture("turnstile", name)[1])


@pytest.fixture
def logs():
    return []


@pytest.fixture
def vendors():
    return Vendors()


@pytest.fixture
def live_deps(db_env, vendors, logs):
    return Deps(
        db=app_role_db(lambda: connect("app", job="test", autocommit=True)),
        capi=LiveCapi(pixel_id=PIXEL, token=TOKEN, transport=httpx.MockTransport(vendors.graph), sleep=lambda s: None),
        turnstile=LiveTurnstile(secret=SECRET, transport=httpx.MockTransport(vendors.siteverify), sleep=lambda s: None,
                                log=lambda event, **f: logs.append({"event": event, **f})),
        limiter=RateLimiter(1000), log=lambda event, **f: logs.append({"event": event, **f}),
        cal_webhook_secret=CAL, funnel_host="https://go.upclicklabs.com", pixel_id=PIXEL,
        turnstile_site_key="0x4AAAA-site-key", test_event_code="TEST123",
    )


@pytest.fixture
def admin(db_env):
    with connect("sam_admin", job="test") as conn:
        yield conn


# ---------- the entrypoint the runtime loads ----------

def test_entrypoint_is_a_wsgi_app_the_runtime_detects():
    mod = load_entrypoint(ME_DIR)
    assert positional_params(mod.app) == 2 and not inspect.iscoroutinefunction(mod.app)
    assert getattr(mod.app, "asgi", None) is None
    assert [n for n in ("app", "application", "handler") if hasattr(mod, n)] == ["app"]
    assert (ME_DIR / "api" / ".python-version").read_text().strip() == "3.13"


def test_four_routes_through_the_runtime_with_the_live_adapters(live_deps, vendors, admin, logs):
    with VercelRuntime(make_app(lambda: live_deps)) as rt:
        status, headers, cfg = rt.call("GET", "/quiz/config?client=upclicklabs")
        assert status == 200 and [q["id"] for q in cfg["questions"]] == ["q1", "q2", "q3"]
        assert cfg["capi_test_mode"] is True and cfg["pixel_id"] == PIXEL and "TEST123" not in json.dumps(cfg)
        assert headers["content-type"] == "application/json" and headers["cache-control"] == "no-store"

        consent = {"tracking": True, "marketing": False, "verbatim_use": False}
        status, _, started = rt.call("POST", "/quiz/start", {"client": "upclicklabs", "consent": consent,
                                                             "utm": {"source": "facebook"}, "fbclid": "IwARvercel",
                                                             "turnstile_token": "good-1"})
        assert status == 200, started
        lead = started["lead_id"]
        status, _, done = rt.call("POST", "/quiz", {"client": "upclicklabs", "lead_id": lead, "answers": GOOD,
                                                    "contact": {"email": "Pat@Example.com", "name": "Pat", "phone": None},
                                                    "turnstile_token": "good-2"})
        assert status == 200 and done["event_id"] == f"{lead}:QuizComplete", done
        hook = json.dumps({"triggerEvent": "BOOKING_CREATED", "payload": {"uid": "v1", "startTime": "2026-11-02T10:00:00Z",
                                                                          "metadata": {"lead_id": lead}}}).encode()
        status, _, booked = rt.call("POST", "/cal-webhook", hook, {"x-cal-signature-256": quiz.cal_signature(CAL, hook)})
        assert status == 200 and booked == {"updated": True, "event_id": f"{lead}:Schedule"}
        assert rt.call("GET", "/quiz")[0] == 404 and rt.call("DELETE", "/quiz/start")[0] == 404

    assert [f["remoteip"] for f in vendors.siteverify_forms] == [IP, IP]
    assert [f["response"] for f in vendors.siteverify_forms] == ["good-1", "good-2"]
    assert {f["path"] for f in vendors.capi_forms} == {f"/v26.0/{PIXEL}/events"}
    assert {f["test_event_code"] for f in vendors.capi_forms} == {"TEST123"}
    assert all(f["access_token"] == TOKEN for f in vendors.capi_forms)
    by = {e["event_name"]: e for e in vendors.events}
    assert sorted(by) == ["QuizComplete", "QuizStart", "Schedule"]
    assert {e["event_id"] for e in vendors.events} == {f"{lead}:QuizStart", f"{lead}:QuizComplete", f"{lead}:Schedule"}
    assert by["QuizStart"]["user_data"]["client_ip_address"] == IP and by["QuizStart"]["user_data"]["client_user_agent"] == UA
    assert by["QuizStart"]["user_data"]["fbc"].endswith(".IwARvercel")
    assert by["QuizComplete"]["user_data"]["em"] == [hash_user_field("pat@example.com")]
    assert by["QuizStart"]["event_source_url"] == "https://go.upclicklabs.com/quiz"
    assert by["Schedule"]["action_source"] == "system_generated"
    assert "example.com" not in json.dumps(vendors.events).lower()
    row = admin.execute("select stage, booked_verified_at from leads where id = %s", (lead,)).fetchone()
    assert row["stage"] == "booked" and row["booked_verified_at"] is not None
    assert [l["event"] for l in logs if l["event"].startswith("capi_")] == ["capi_sent"] * 3


def test_a_replayed_turnstile_token_is_refused(live_deps, vendors):
    consent = {"tracking": False, "marketing": False, "verbatim_use": False}
    body = {"client": "upclicklabs", "consent": consent, "turnstile_token": "good-replay"}
    with VercelRuntime(make_app(lambda: live_deps)) as rt:
        assert rt.call("POST", "/quiz/start", body)[0] == 200
        status, _, out = rt.call("POST", "/quiz/start", body)
    assert status == 403 and "verification" in out["error"]
    assert vendors.events == []


def test_the_function_path_with_a_route_hint_reaches_the_same_handler(live_deps):
    """If the platform hands the function its own path instead of the visitor's, the `route` hint in vercel.json's
    dest names the route; a direct call without one is a 404."""
    with VercelRuntime(make_app(lambda: live_deps)) as rt:
        status, _, cfg = rt.call("GET", f"{FUNCTION_PATH}?route=config&client=upclicklabs")
        assert status == 200 and cfg["questions"]
        status, _, out = rt.call("POST", f"{FUNCTION_PATH}?route=start",
                                 {"client": "upclicklabs", "consent": {"tracking": False, "marketing": False, "verbatim_use": False},
                                  "turnstile_token": "good-hint"})
        assert status == 200 and out["lead_id"]
        assert rt.call("GET", FUNCTION_PATH)[0] == 404
        status, _, cfg = rt.call("GET", "/quiz/config?client=upclicklabs&route=config")
        assert status == 200 and cfg["client"] == "upclicklabs"


def test_bodies_over_64kb_are_refused_unread_and_bad_json_is_a_400(live_deps):
    with VercelRuntime(make_app(lambda: live_deps)) as rt:
        status, _, out = rt.call("POST", "/cal-webhook", b"x" * (64 * 1024 + 1))
        assert status == 413 and out == {"error": "too large"}
        assert rt.call("POST", "/quiz/start", b"{not json")[0] == 400


def test_client_ip_prefers_vercels_headers_and_ignores_garbage():
    assert client_ip({"HTTP_X_VERCEL_FORWARDED_FOR": "198.51.100.1", "HTTP_X_FORWARDED_FOR": "10.0.0.1", "REMOTE_ADDR": "10.0.0.2"}) == "198.51.100.1"
    assert client_ip({"HTTP_X_REAL_IP": "2001:db8::1"}) == "2001:db8::1"
    assert client_ip({"HTTP_X_VERCEL_FORWARDED_FOR": "not-an-ip", "HTTP_X_FORWARDED_FOR": "198.51.100.2, 10.0.0.1"}) == "198.51.100.2"
    assert client_ip({"REMOTE_ADDR": None}) == "0.0.0.0"


def test_unexpected_errors_are_a_500_without_detail(live_deps, logs, monkeypatch):
    def broken():
        raise psycopg.OperationalError("connection to server failed: password authentication failed for user app")
    monkeypatch.setattr(live_deps, "db", broken)
    seen = []
    with VercelRuntime(make_app(lambda: live_deps, log=lambda event, **f: seen.append({"event": event, **f}))) as rt:
        status, _, out = rt.call("GET", "/quiz/config?client=upclicklabs")
    assert status == 500 and out == {"error": "internal error"}
    assert seen == [{"event": "function_error", "method": "GET", "path": "/quiz/config", "error": "OperationalError"}]


# ---------- guards: the role for the job, live backends, nobody else's credentials ----------

def test_the_function_refuses_credentials_that_belong_to_other_jobs():
    ok = {"VERCEL": "1", "CAPI_BACKEND": "live", "TURNSTILE_BACKEND": "live", "WAREHOUSE_URL_APP": "postgresql://app@x/db"}
    check_environment(ok)
    for var in ("WAREHOUSE_URL_WORKER", "WAREHOUSE_URL_EXECUTOR", "WAREHOUSE_URL_SAM_ADMIN", "WAREHOUSE_URL_ADMIN",
                "WAREHOUSE_URL_MCP_RO", "META_ACCESS_TOKEN", "META_READ_TOKEN"):
        with pytest.raises(Misconfigured, match=var) as exc:
            check_environment({**ok, var: "s3cret-value"})
        assert "s3cret-value" not in str(exc.value)


@pytest.mark.parametrize("var, value", [("CAPI_BACKEND", "fake"), ("TURNSTILE_BACKEND", "pass"), ("TURNSTILE_BACKEND", None)])
def test_on_vercel_both_backends_must_be_live(var, value):
    env = {"VERCEL": "1", "CAPI_BACKEND": "live", "TURNSTILE_BACKEND": "live", var: value}
    with pytest.raises(Misconfigured, match=var):
        check_environment({k: v for k, v in env.items() if v is not None})
    check_environment({k: v for k, v in env.items() if k != "VERCEL" and v is not None})   # local runs keep the dev backends


def test_a_misconfigured_function_answers_503_and_names_the_variable(live_deps):
    seen = []

    def build():
        check_environment({"VERCEL": "1", "CAPI_BACKEND": "live", "TURNSTILE_BACKEND": "live", "WAREHOUSE_URL_WORKER": "pg://worker:pw@x"})
    with VercelRuntime(make_app(build, log=lambda event, **f: seen.append({"event": event, **f}))) as rt:
        status, _, out = rt.call("GET", "/quiz/config?client=upclicklabs")
    assert status == 503 and out == {"error": "service unavailable"}
    assert seen[0]["event"] == "function_misconfigured" and "WAREHOUSE_URL_WORKER" in seen[0]["error"]
    assert "pw@" not in json.dumps(seen)


def test_the_warehouse_login_must_be_role_app(db_env, live_deps, monkeypatch):
    seen = []
    monkeypatch.setattr(live_deps, "db", app_role_db(lambda: psycopg.connect(db_env["WAREHOUSE_URL_WORKER"], autocommit=True)))
    with VercelRuntime(make_app(lambda: live_deps, log=lambda event, **f: seen.append({"event": event, **f}))) as rt:
        status, _, out = rt.call("GET", "/quiz/config?client=upclicklabs")
    assert status == 503 and out == {"error": "service unavailable"}
    assert seen[0]["event"] == "function_misconfigured" and "WAREHOUSE_URL_APP" in seen[0]["error"]
    assert "worker_rw" in seen[0]["error"] and "dev-worker_rw" not in json.dumps(seen)
    with pytest.raises(Misconfigured, match="superuser"):
        with app_role_db(lambda: psycopg.connect(db_env["WAREHOUSE_URL_ADMIN"], autocommit=True))() as conn:
            pass


# ---------- vercel.json ----------

def vercel_route(method: str, path: str) -> str | None:
    """Vercel's `routes`: the first route whose src matches the whole pathname (case-insensitive) and whose methods,
    when given, include the request method."""
    for r in VERCEL["routes"]:
        if r.get("methods") and method not in r["methods"]:
            continue
        if re.fullmatch(r["src"], path, flags=re.I):
            return r["dest"]
    return None


def test_vercel_json_routes_the_four_function_paths_and_serves_the_page():
    assert VERCEL["framework"] is None and VERCEL["outputDirectory"] == "funnel/static" and "builds" not in VERCEL
    assert set(VERCEL["functions"]) == {"api/funnel.py"} and (ME_DIR / "api" / "funnel.py").exists()
    out = ME_DIR / VERCEL["outputDirectory"]
    for method, path, hint in [("GET", "/quiz/config", "config"), ("POST", "/quiz/start", "start"), ("POST", "/quiz", "complete"),
                               ("POST", "/cal-webhook", "cal-webhook"), ("POST", "/quiz/start/", "start")]:
        dest = vercel_route(method, path)
        assert dest == f"{FUNCTION_PATH}?route={hint}", (method, path, dest)
        assert ROUTE_HINTS[hint] == path.rstrip("/")
    assert vercel_route("GET", "/quiz") == "/index.html" and (out / "index.html").is_file()
    assert vercel_route("GET", "/quiz.js") is None and (out / "quiz.js").is_file() and (out / "quiz.css").is_file()
    assert vercel_route("GET", "/quiz/start") is None and vercel_route("PUT", "/quiz") is None
    page = (out / "index.html").read_text()
    for ref in re.findall(r'(?:src|href)="(/[^"#]+)"', page):
        assert (out / ref.lstrip("/")).is_file(), ref
    assert VERCEL["functions"]["api/funnel.py"]["maxDuration"] <= 60


# ---------- what gets uploaded, and that it runs on its own ----------

EXPECTED_UPLOAD = {
    "vercel.json", "api/funnel.py", "api/requirements.txt", "api/.python-version",
    "funnel/__init__.py", "funnel/app.py", "funnel/quiz.py", "funnel/wsgi.py",
    "funnel/static/index.html", "funnel/static/quiz.css", "funnel/static/quiz.js",
    "adapters/__init__.py", "adapters/env.py", "adapters/graph.py", "adapters/capi/__init__.py", "adapters/capi/live.py",
    "adapters/turnstile/__init__.py", "adapters/turnstile/live.py",
    "warehouse/__init__.py", "warehouse/client.py",
}


def uploaded_files(tmp_path: Path) -> set[str]:
    """The project tree as a CLI deploy would see it (git-tracked or not, plus a local .env, .dev state and bytecode),
    mirrored as empty files and filtered by .vercelignore through git's gitignore matcher."""
    mirror = tmp_path / "mirror"
    for path in ME_DIR.rglob("*"):
        if path.is_file():
            target = mirror / path.relative_to(ME_DIR)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
    for extra in (".env", ".env.local", ".dev/capi.jsonl", "funnel/__pycache__/app.cpython-313.pyc", "adapters/capi/.env",
                  "api/__pycache__/funnel.cpython-313.pyc"):
        (mirror / extra).parent.mkdir(parents=True, exist_ok=True)
        (mirror / extra).touch()
    subprocess.run(["git", "init", "-q", str(mirror)], check=True)
    (mirror / ".git" / "info" / "exclude").write_text((ME_DIR / ".vercelignore").read_text())
    res = subprocess.run(["git", "-c", "core.excludesFile=/dev/null", "ls-files", "--others", "--exclude-standard", "-z"],
                         cwd=mirror, capture_output=True, check=True)
    return {p for p in res.stdout.decode().split("\0") if p}


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_vercelignore_uploads_only_what_the_function_imports_and_the_page(tmp_path):
    files = uploaded_files(tmp_path)
    assert files == EXPECTED_UPLOAD, (sorted(files - EXPECTED_UPLOAD), sorted(EXPECTED_UPLOAD - files))


def test_api_requirements_name_every_third_party_import_of_the_bundle():
    local = {"api", "funnel", "adapters", "warehouse"}
    imported: set[str] = set()
    for rel in EXPECTED_UPLOAD:
        if rel.endswith(".py"):
            for node in ast.walk(ast.parse((ME_DIR / rel).read_text())):
                if isinstance(node, ast.Import):
                    imported |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".")[0])
    third_party = sorted(imported - local - set(sys.stdlib_module_names) - {"__future__"})
    assert third_party == ["dotenv", "httpx", "jsonschema", "psycopg"]
    dists = importlib.metadata.packages_distributions()
    names = {re.split(r"[\[=<>~! ]", line.strip())[0].lower() for line in (ME_DIR / "api" / "requirements.txt").read_text().splitlines()
             if line.strip() and not line.startswith("#")}
    for module in third_party:
        assert {d.lower() for d in dists[module]} & names, f"{module} is imported by the bundle but not in api/requirements.txt"
    assert "playwright" not in names and "anthropic" not in names and "pytest" not in names


BUNDLE_PROBE = r"""
import importlib.util, inspect, io, json, sys
root = sys.argv[1]
spec = importlib.util.spec_from_file_location("vc_entry_bundle", root + "/api/funnel.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
out = {}
def start_response(status, headers, exc_info=None):
    out["status"] = status
environ = {"REQUEST_METHOD": "GET", "PATH_INFO": "/quiz/config", "QUERY_STRING": "client=upclicklabs", "CONTENT_LENGTH": "0",
           "CONTENT_TYPE": "", "SCRIPT_NAME": "", "REMOTE_ADDR": "203.0.113.9", "SERVER_NAME": "go.upclicklabs.com",
           "SERVER_PORT": "443", "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.input": io.BytesIO(b""), "wsgi.errors": sys.stderr,
           "wsgi.url_scheme": "https", "wsgi.version": (1, 0), "wsgi.multiprocess": False, "wsgi.multithread": False,
           "wsgi.run_once": False, "HTTP_X_VERCEL_FORWARDED_FOR": "203.0.113.9"}
body = json.loads(b"".join(mod.app(environ, start_response)))
local = sorted({m.__file__ for n, m in list(sys.modules.items())
                if getattr(m, "__file__", None) and n.split(".")[0] in ("funnel", "adapters", "warehouse")})
print(json.dumps({"status": out["status"], "body": body, "local": local}))
"""


def test_the_uploaded_files_alone_serve_the_config_as_role_app(db_env, tmp_path):
    """The upload set copied to an empty directory, imported by an isolated interpreter (-I: no PYTHONPATH, no cwd on
    sys.path) the way the runtime loads the entrypoint, with only the function's variables set: no .env, no repo."""
    files = EXPECTED_UPLOAD if shutil.which("git") is None else uploaded_files(tmp_path)
    bundle = tmp_path / "bundle"
    for rel in files:
        (bundle / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ME_DIR / rel, bundle / rel)
    env = {"PATH": os.environ.get("PATH", ""), "VERCEL": "1", "VERCEL_ENV": "preview",
           "WAREHOUSE_URL_APP": db_env["WAREHOUSE_URL_APP"], "CAPI_BACKEND": "live", "TURNSTILE_BACKEND": "live",
           "META_PIXEL_ID": PIXEL, "META_CAPI_TOKEN": "dummy-capi-token", "TURNSTILE_SECRET_KEY": "dummy-turnstile-secret",
           "CAL_WEBHOOK_SECRET": CAL, "FUNNEL_HOST": "https://go.upclicklabs.com"}
    res = subprocess.run([sys.executable, "-I", "-c", BUNDLE_PROBE, str(bundle)], cwd=bundle, env=env,
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["status"] == "200 OK" and [q["id"] for q in out["body"]["questions"]] == ["q1", "q2", "q3"], out
    assert out["local"] and all(f.startswith(str(bundle)) for f in out["local"]), out["local"]

    res = subprocess.run([sys.executable, "-I", "-c", BUNDLE_PROBE, str(bundle)], cwd=bundle,
                         env={**env, "WAREHOUSE_URL_WORKER": db_env["WAREHOUSE_URL_WORKER"]},
                         capture_output=True, text=True, timeout=60)
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["status"].startswith("503") and "WAREHOUSE_URL_WORKER" in res.stderr
    assert "dev-worker_rw" not in res.stderr + res.stdout
