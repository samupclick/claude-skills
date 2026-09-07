#!/usr/bin/env python3
"""Local runner for the quiz funnel (dev-mode.md: FUNNEL_HOST=http://localhost:8788).

Serves funnel/static/ (the quiz page at / and /quiz) and routes the function paths to funnel/app.py,
one warehouse connection per request as role `app`. Emulates what Vercel + the Edge Functions do in
production; nothing here is deployed (T13). Usage: python3 funnel/server.py [--port 8788]
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.env import load_env  # noqa: E402
from funnel.app import Deps, Request, deps_from_env, handle  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
PAGES = {"/": "index.html", "/quiz": "index.html"}
API_PREFIXES = ("/quiz/config", "/quiz/start", "/cal-webhook")


def make_handler(deps: Deps) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "funnel-dev/0"

        def log_message(self, fmt, *args):  # one line per request on stderr, no query strings (they carry fbclid)
            print(f"{self.address_string()} {self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}",
                  file=sys.stderr, flush=True)

        def _api(self) -> bool:
            parts = urlsplit(self.path)
            path = parts.path.rstrip("/") or "/"
            return path in API_PREFIXES or (self.command == "POST" and path == "/quiz")

        def _serve_static(self, path: str) -> None:
            name = PAGES.get(path) or path.lstrip("/")
            target = (STATIC / name).resolve()
            if not str(target).startswith(str(STATIC)) or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            data = target.read_bytes()
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or "javascript" in ctype else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _dispatch(self) -> None:
            parts = urlsplit(self.path)
            path = parts.path.rstrip("/") or "/"
            if not self._api():
                if self.command == "GET":
                    self._serve_static(path)
                else:
                    self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            forwarded = self.headers.get("X-Forwarded-For")
            ip = forwarded.split(",")[0].strip() if forwarded else self.client_address[0]
            req = Request(method=self.command, path=path, query=dict(parse_qsl(parts.query)),
                          headers={k.lower(): v for k, v in self.headers.items()}, body=body, remote_ip=ip)
            res = handle(req, deps)
            data = res.json()
            self.send_response(res.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in res.headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._dispatch()

        def do_POST(self):
            self._dispatch()

    return Handler


def default_port() -> int:
    load_env()
    host = urlsplit(os.environ.get("FUNNEL_HOST") or "http://localhost:8788")
    return host.port or 8788


def serve(port: int, deps: Deps | None = None) -> ThreadingHTTPServer:
    """Bind and return the server (call serve_forever yourself); tests run it on a thread."""
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(deps or deps_from_env()))
    server.daemon_threads = True
    return server


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args(argv)
    port = args.port or default_port()
    server = serve(port)
    print(f"funnel: serving http://127.0.0.1:{port}/quiz (role app, CAPI_BACKEND={os.environ.get('CAPI_BACKEND')}, "
          f"TURNSTILE_BACKEND={os.environ.get('TURNSTILE_BACKEND')})", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
