#!/usr/bin/env python3
"""Events Manager test tool for the quiz funnel (T7, FR-33, FR-34): drive the three events through the funnel and prove
dedup, consent, and the webhook signature check.

  python3 scripts/test_events.py                   # CAPI_BACKEND=fake against FUNNEL_HOST (starts a local runner if nothing answers)
  python3 scripts/test_events.py --no-serve        # fail instead of starting a runner
  python3 scripts/test_events.py --live            # the same events to Meta with META_TEST_EVENT_CODE (refuses without it)

What it does, as a synthetic prospect:
  1. consent {tracking: true}: start → complete → signed calendar webhook → the same webhook again
  2. consent {tracking: false}: start → complete → signed webhook
  3. a webhook with a forged signature
Then it checks the events. Fake mode reads DEV_ROOT/capi.jsonl and requires QuizStart, QuizComplete, Schedule exactly
once each for prospect 1 (dedup), none for prospect 2 (consent), and the forged webhook rejected.

--live sends through CAPI_BACKEND=live and only with META_TEST_EVENT_CODE set, so the events land in Events Manager's
Test events tab. When nothing answers on FUNNEL_HOST it starts the runner in-process on the live backend and requires
Meta to acknowledge each event once (events_received=1, fbtrace_id printed). Against a funnel it did not start (a
Vercel preview) it first asks /quiz/config whether that funnel has a test event code (capi_test_mode) and sends nothing
when it does not; it cannot see Meta's replies there, so it prints what Events Manager must show. Without --live the
script refuses CAPI_BACKEND=live, and against a funnel it did not start it asks /quiz/config for that funnel's backend
(capi_backend) and sends nothing unless it is `fake` (a deployment runs `live` and would send the synthetic prospects
to the production pixel). Turnstile: the token sent is Cloudflare's dummy token, which the `pass` backend and
Turnstile's test secret key accept and a production secret refuses.
Opens and closes a `runs` row (worker `test_events`, role worker_rw) including on failure; exit 1 = not green.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.capi import CapiError  # noqa: E402
from adapters.env import MissingEnvVar, UnknownBackend, dev_root, load_env, require  # noqa: E402
from funnel import quiz  # noqa: E402
from warehouse.client import client_by_slug, connect, run  # noqa: E402

CLIENT = "upclicklabs"
TURNSTILE_TOKEN = "XXXX.DUMMY.TOKEN.XXXX"


class NotGreen(RuntimeError):
    """A check failed; the message names the criterion."""


class RecordingCapi:
    """The in-process runner's CAPI backend, wrapped so --live can report what Meta answered for each event."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.backend = getattr(inner, "backend", None)
        self.sent: list[dict[str, Any]] = []

    def send(self, **event: Any) -> dict[str, Any]:
        entry = {"event_name": event["event_name"], "event_id": event["event_id"],
                 "test_event_code": bool(event.get("test_event_code"))}
        try:
            res = self.inner.send(**event)
        except Exception as exc:
            self.sent.append({**entry, "error": str(exc) if isinstance(exc, CapiError) else type(exc).__name__})
            raise
        self.sent.append({**entry, "events_received": res.get("events_received"), "fbtrace_id": res.get("fbtrace_id")})
        return res


def _call(host: str, method: str, path: str, body: dict | bytes | None = None, headers: dict | None = None) -> tuple[int, dict]:
    """One request to the funnel. A Vercel preview sits behind Deployment Protection: with
    VERCEL_AUTOMATION_BYPASS_SECRET set, every request carries it in x-vercel-protection-bypass."""
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    bypass = os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET")
    req = urllib.request.Request(host + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {}),
                                          **({"x-vercel-protection-bypass": bypass} if bypass else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def _listening(host: str) -> bool:
    u = urlsplit(host)
    try:
        with socket.create_connection((u.hostname or "127.0.0.1", u.port or (443 if u.scheme == "https" else 80)), timeout=1):
            return True
    except OSError:
        return False


def _start_runner(host: str, record: bool):
    """funnel/server.py's runner on a thread in this process, its CAPI backend wrapped when `record`."""
    from funnel.app import deps_from_env
    from funnel.server import serve

    deps = deps_from_env()
    recorder = None
    if record:
        recorder = deps.capi = RecordingCapi(deps.capi)
    server = serve(urlsplit(host).port or 8788, deps)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for _ in range(50):
        if _listening(host):
            return server, recorder
        time.sleep(0.1)
    server.server_close()
    raise NotGreen(f"local runner did not come up on {host}")


def prospect(host: str, secret: str, tracking: bool, questions: list[dict], r) -> dict:
    """One synthetic prospect through start → complete → webhook (twice). Returns ids and statuses."""
    consent = {"tracking": tracking, "marketing": False, "verbatim_use": False}
    utm = {"source": "facebook", "medium": "paid", "campaign": "test_events", "content": "test-events-no-creative"}
    status, body = _call(host, "POST", "/quiz/start", {"client": CLIENT, "consent": consent, "utm": utm,
                                                       "fbclid": "IwARtest_events_fbclid", "turnstile_token": TURNSTILE_TOKEN})
    if status == 403:
        raise NotGreen("/quiz/start returned 403: the funnel's Turnstile refused the dummy token; give that environment "
                       "TURNSTILE_BACKEND=pass or Cloudflare's test secret key as TURNSTILE_SECRET_KEY")
    if status != 200:
        raise NotGreen(f"/quiz/start returned {status}: {body.get('error')}")
    lead_id = body["lead_id"]
    r.count("quiz_start")
    answers = {q["id"]: q["options"][0] for q in questions}
    contact = {"email": f"test-events+{lead_id[:8]}@example.com", "name": "Test Events", "phone": None}
    status, body = _call(host, "POST", "/quiz", {"client": CLIENT, "lead_id": lead_id, "answers": answers,
                                                 "contact": contact, "turnstile_token": TURNSTILE_TOKEN})
    if status != 200:
        raise NotGreen(f"/quiz returned {status}: {body.get('error')}")
    r.count("quiz_complete")
    hook = json.dumps({"triggerEvent": "BOOKING_CREATED", "createdAt": "2026-09-07T10:00:00Z",
                       "payload": {"uid": f"test-{lead_id[:8]}", "startTime": "2026-09-09T10:00:00Z",
                                   "metadata": {"lead_id": lead_id}}}).encode()
    sig = {"X-Cal-Signature-256": quiz.cal_signature(secret, hook)}
    s1, b1 = _call(host, "POST", "/cal-webhook", hook, sig)
    s2, b2 = _call(host, "POST", "/cal-webhook", hook, sig)
    if s1 != 200 or not b1.get("updated"):
        raise NotGreen(f"signed webhook not accepted: {s1} {b1}")
    if s2 != 200 or b2.get("updated"):
        raise NotGreen(f"webhook retry was applied twice: {s2} {b2}")
    r.count("schedule")
    return {"lead_id": lead_id, "tracking": tracking}


def forged(host: str, lead_id: str, r) -> None:
    hook = json.dumps({"triggerEvent": "BOOKING_CREATED", "payload": {"uid": "forged", "metadata": {"lead_id": lead_id}}}).encode()
    status, _ = _call(host, "POST", "/cal-webhook", hook, {"X-Cal-Signature-256": "0" * 64})
    if status != 401:
        raise NotGreen(f"forged webhook was not rejected (status {status})")
    status, _ = _call(host, "POST", "/cal-webhook", hook)
    if status != 401:
        raise NotGreen(f"unsigned webhook was not rejected (status {status})")
    r.count("forged_rejected", 2)


def _by_lead(events: list[dict], prospects: list[dict], line) -> list[str]:
    """For each prospect: the tracking one needs exactly one entry per event name, the declined one none."""
    lines = []
    for p in prospects:
        mine = [e for e in events if e["event_id"].startswith(p["lead_id"] + ":")]
        if p["tracking"]:
            for name in quiz.EVENT_NAMES:
                got = [e for e in mine if e["event_name"] == name]
                if len(got) != 1:
                    raise NotGreen(f"{name} for lead {p['lead_id']}: expected exactly one event_id, found {len(got)}")
                lines.append(line(got[0]))
        elif mine:
            raise NotGreen(f"lead {p['lead_id']} declined tracking but {len(mine)} CAPI event(s) were sent")
        else:
            lines.append(f"  no consent   {p['lead_id']}  zero events ✓")
    return lines


def check_fake(prospects: list[dict]) -> list[str]:
    path = dev_root() / "capi.jsonl"
    events = [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []
    return _by_lead(events, prospects, lambda e: f"  {e['event_name']:<12} {e['event_id']}  once ✓")


def check_live(recorder: RecordingCapi, prospects: list[dict], r) -> list[str]:
    def line(e: dict) -> str:
        if e.get("error"):
            raise NotGreen(f"{e['event_name']} {e['event_id']} was not accepted by Meta: {e['error']}")
        if e.get("events_received") != 1 or not e["test_event_code"]:
            raise NotGreen(f"{e['event_name']} {e['event_id']}: events_received={e.get('events_received')}, "
                           f"test_event_code {'set' if e['test_event_code'] else 'missing'}")
        r.count("capi_accepted")
        return f"  {e['event_name']:<12} {e['event_id']}  events_received=1 fbtrace_id={e['fbtrace_id']} ✓"
    return _by_lead(recorder.sent, prospects, line)


def events_manager(pixel_id: str | None, p1: dict, p2: dict) -> list[str]:
    return [
        f"  Events Manager → Data sources → pixel {pixel_id or '<META_PIXEL_ID>'} → Test events (the code in META_TEST_EVENT_CODE),",
        "  within a few minutes:",
        *(f"    {name:<12} 1 event, received from Server, event ID {p1['lead_id']}:{name}" for name in quiz.EVENT_NAMES),
        f"    nothing for lead {p2['lead_id']} (tracking declined)",
        "  Walk the page in the same Test events session with tracking allowed and QuizStart / QuizComplete show Browser",
        "  and Server once each, deduplicated on the same event IDs.",
    ]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="quiz funnel event test (Events Manager test tool stand-in)")
    ap.add_argument("--no-serve", action="store_true", help="do not start a local runner when FUNNEL_HOST is silent")
    ap.add_argument("--live", action="store_true",
                    help="send through CAPI_BACKEND=live to Events Manager's Test events tab (needs META_TEST_EVENT_CODE)")
    args = ap.parse_args(argv)
    load_env()
    env = require("test_events", "FUNNEL_HOST", "CAL_WEBHOOK_SECRET")
    host, secret = env["FUNNEL_HOST"].rstrip("/"), env["CAL_WEBHOOK_SECRET"]
    server = None

    with connect("worker", job="test_events") as conn:
        client_id = (client_by_slug(conn, CLIENT) or {}).get("id")
        with run(conn, "test_events", client_id) as r:
            try:
                if args.live:
                    require("test_events --live", "META_TEST_EVENT_CODE")
                    os.environ["CAPI_BACKEND"] = "live"
                elif os.environ.get("CAPI_BACKEND") != "fake":
                    raise NotGreen(f"CAPI_BACKEND={os.environ.get('CAPI_BACKEND')} sends events to Meta: run with --live, "
                                   "which needs META_TEST_EVENT_CODE so they land in the Test events tab")
                recorder = None
                if not _listening(host):
                    if args.no_serve:
                        raise NotGreen(f"nothing is listening on FUNNEL_HOST ({host}); run funnel/server.py")
                    server, recorder = _start_runner(host, record=args.live)
                status, cfg = _call(host, "GET", f"/quiz/config?client={CLIENT}")
                if status != 200 or not cfg.get("questions"):
                    raise NotGreen(f"/quiz/config returned {status}: {cfg.get('error') or 'no questions configured'}")
                if not args.live and server is None and cfg.get("capi_backend") != "fake":
                    raise NotGreen(f"the funnel at {host} reports capi_backend {cfg.get('capi_backend')!r}: without --live this "
                                   "script drives only a funnel on CAPI_BACKEND=fake (its own runner or funnel/server.py); "
                                   "nothing was sent")
                if args.live and recorder is None and cfg.get("capi_test_mode") is not True:
                    raise NotGreen(f"the funnel at {host} reports capi_test_mode false: set META_TEST_EVENT_CODE in that "
                                   "environment first; nothing was sent")
                p1 = prospect(host, secret, True, cfg["questions"], r)
                p2 = prospect(host, secret, False, cfg["questions"], r)
                forged(host, p1["lead_id"], r)
                print(f"test_events: funnel {host}, CAPI_BACKEND={'live' if args.live else 'fake'}")
                if not args.live:
                    for line in check_fake([p1, p2]):
                        print(line)
                    print("test_events: green — each event_id once, none without consent, forged webhook rejected")
                elif recorder is not None:
                    for line in check_live(recorder, [p1, p2], r):
                        print(line)
                    print("test_events: green — Meta acknowledged each event once with the test event code, none "
                          "without consent, forged webhook rejected. Confirm in Events Manager:")
                    for line in events_manager(os.environ.get("META_PIXEL_ID"), p1, p2):
                        print(line)
                else:
                    print(f"  sent QuizStart / QuizComplete / Schedule for lead {p1['lead_id']} through a funnel this script")
                    print("  did not start, so it cannot see Meta's replies; forged webhook rejected: yes. Check:")
                    for line in events_manager(cfg.get("pixel_id"), p1, p2):
                        print(line)
                r.count("prospects", 2)
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (NotGreen, MissingEnvVar, UnknownBackend) as exc:
        print(f"test_events: NOT GREEN — {exc}", file=sys.stderr)
        sys.exit(1)
