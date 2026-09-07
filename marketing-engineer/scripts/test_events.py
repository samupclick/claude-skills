#!/usr/bin/env python3
"""Events Manager test tool for the quiz funnel (T7): drive the three events through the running funnel
and prove dedup, consent, and the webhook signature check.

  python3 scripts/test_events.py            # against FUNNEL_HOST (starts a local runner if nothing answers)
  python3 scripts/test_events.py --no-serve # fail instead of starting a runner

What it does, as a synthetic prospect:
  1. consent {tracking: true}: start → complete → signed calendar webhook → the same webhook again
  2. consent {tracking: false}: start → complete → signed webhook
  3. a webhook with a forged signature
Then it checks the events: with CAPI_BACKEND=fake it reads DEV_ROOT/capi.jsonl and requires QuizStart,
QuizComplete, Schedule exactly once each for prospect 1 (dedup), none for prospect 2 (consent), and
that the forged webhook was rejected. With CAPI_BACKEND=live the same events reach Meta with
META_TEST_EVENT_CODE, and the script prints what Events Manager's test tool must show.
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
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.env import dev_root, load_env, require  # noqa: E402
from funnel import quiz  # noqa: E402
from warehouse.client import client_by_slug, connect, run  # noqa: E402

CLIENT = "upclicklabs"


class NotGreen(RuntimeError):
    """A check failed; the message names the criterion."""


def _call(host: str, method: str, path: str, body: dict | bytes | None = None, headers: dict | None = None) -> tuple[int, dict]:
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    req = urllib.request.Request(host + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def _listening(host: str) -> bool:
    u = urlsplit(host)
    try:
        with socket.create_connection((u.hostname or "127.0.0.1", u.port or 80), timeout=1):
            return True
    except OSError:
        return False


def _start_runner(host: str) -> None:
    from funnel.server import serve
    u = urlsplit(host)
    server = serve(u.port or 8788)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for _ in range(50):
        if _listening(host):
            return
        time.sleep(0.1)
    raise NotGreen(f"local runner did not come up on {host}")


def prospect(host: str, secret: str, tracking: bool, questions: list[dict], r) -> dict:
    """One synthetic prospect through start → complete → webhook (twice). Returns ids and statuses."""
    consent = {"tracking": tracking, "marketing": False, "verbatim_use": False}
    utm = {"source": "facebook", "medium": "paid", "campaign": "test_events", "content": "test-events-no-creative"}
    status, body = _call(host, "POST", "/quiz/start", {"client": CLIENT, "consent": consent, "utm": utm,
                                                       "fbclid": "IwARtest_events_fbclid", "turnstile_token": "dev-pass"})
    if status != 200:
        raise NotGreen(f"/quiz/start returned {status}: {body.get('error')}")
    lead_id = body["lead_id"]
    r.count("quiz_start")
    answers = {q["id"]: q["options"][0] for q in questions}
    contact = {"email": f"test-events+{lead_id[:8]}@example.com", "name": "Test Events", "phone": None}
    status, body = _call(host, "POST", "/quiz", {"client": CLIENT, "lead_id": lead_id, "answers": answers,
                                                 "contact": contact, "turnstile_token": "dev-pass"})
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


def check_fake(prospects: list[dict]) -> list[str]:
    path = dev_root() / "capi.jsonl"
    events = [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []
    lines = []
    for p in prospects:
        mine = [e for e in events if e["event_id"].startswith(p["lead_id"] + ":")]
        by_name: dict[str, list[str]] = {}
        for e in mine:
            by_name.setdefault(e["event_name"], []).append(e["event_id"])
        if p["tracking"]:
            for name in quiz.EVENT_NAMES:
                ids = by_name.get(name, [])
                if len(ids) != 1:
                    raise NotGreen(f"{name} for lead {p['lead_id']}: expected exactly one event_id, found {len(ids)}")
                lines.append(f"  {name:<12} {ids[0]}  once ✓")
        elif mine:
            raise NotGreen(f"lead {p['lead_id']} declined tracking but {len(mine)} CAPI event(s) were sent")
        else:
            lines.append(f"  no consent   {p['lead_id']}  zero events ✓")
    return lines


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="quiz funnel event test (Events Manager test tool stand-in)")
    ap.add_argument("--no-serve", action="store_true", help="do not start a local runner when FUNNEL_HOST is silent")
    args = ap.parse_args(argv)
    load_env()
    env = require("test_events", "FUNNEL_HOST", "CAL_WEBHOOK_SECRET", "CAPI_BACKEND")
    host, secret, backend = env["FUNNEL_HOST"].rstrip("/"), env["CAL_WEBHOOK_SECRET"], env["CAPI_BACKEND"]

    with connect("worker", job="test_events") as conn:
        client_id = (client_by_slug(conn, CLIENT) or {}).get("id")
        with run(conn, "test_events", client_id) as r:
            if not _listening(host):
                if args.no_serve:
                    raise NotGreen(f"nothing is listening on FUNNEL_HOST ({host}); run funnel/server.py")
                _start_runner(host)
            status, cfg = _call(host, "GET", f"/quiz/config?client={CLIENT}")
            if status != 200 or not cfg.get("questions"):
                raise NotGreen(f"/quiz/config returned {status}: {cfg.get('error') or 'no questions configured'}")
            p1 = prospect(host, secret, True, cfg["questions"], r)
            p2 = prospect(host, secret, False, cfg["questions"], r)
            forged(host, p1["lead_id"], r)
            print(f"test_events: funnel {host}, CAPI_BACKEND={backend}")
            if backend == "fake":
                for line in check_fake([p1, p2]):
                    print(line)
                print("test_events: green — each event_id once, none without consent, forged webhook rejected")
            else:
                print(f"  sent QuizStart / QuizComplete / Schedule for lead {p1['lead_id']} with test_event_code set;")
                print("  Events Manager → Test events must show the three events once each (server, deduplicated)")
                print(f"  and nothing for lead {p2['lead_id']}. Forged webhook rejected: yes.")
            r.count("prospects", 2)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except NotGreen as exc:
        print(f"test_events: NOT GREEN — {exc}", file=sys.stderr)
        sys.exit(1)
