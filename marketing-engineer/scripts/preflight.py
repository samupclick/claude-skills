#!/usr/bin/env python3
"""Prove each live credential with one read-only call; print names and status, never a value.

    source scripts/env_from_keychain.sh && python3 scripts/preflight.py [--write-status references/credentials-status.md]

Checks only what is already in this process's environment (it loads neither .env nor the keychain), so the Meta write
token is checked only when Sam runs it in the --with-meta-write subshell. Like `warehouse/client.py status` it is
read-only and opens no `runs` row. One line per service:

    <service>: ok | auth failed | wrong scope | not set | set | unreachable | error   (detail)

- anthropic       GET /v1/models; MODEL_ID (default claude-opus-5-5) must be listed
- gemini          GET /v1beta/models (x-goog-api-key); IMAGE_MODEL (default gemini-nano-banana-2.1) must be listed
- scrapecreators  GET /v1/account/credit-balance (x-api-key; the vendor's balance endpoint, spends no search credit)
- apify           GET /v2/users/me (Bearer header; spends nothing); reports the plan id, never the account name
- meta * token    GET /me per token (Bearer header); the write and read tokens then GET act_<id>?fields=account_status,
                  currency,timezone_name,spend_cap; the CAPI token GET <pixel id>?fields=id
- supabase        GET <SUPABASE_URL>/auth/v1/health with the publishable key as `apikey`
- warehouse       when WAREHOUSE_URL_WORKER points at a remote host (the Supabase pooler): scripts/apply_migrations.py
                  --verify, which reads the five role strings itself and only reads; the local dev cluster is `not set`
- turnstile       siteverify with a dummy token: invalid-input-response means the secret is accepted
- reddit          app-only client-credentials token
- cal.com         CAL_WEBHOOK_SECRET is a webhook signing secret: reported `set`, nothing to call

Every printed or written string is scrubbed of every credential value present, and vendor error bodies are never
printed: only HTTP status and the vendor's error code or type. Exit 1 when a set credential fails.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlsplit

import httpx

ME_DIR = Path(__file__).resolve().parent.parent
if str(ME_DIR) not in sys.path:
    sys.path.insert(0, str(ME_DIR))

from adapters.graph import base_url as graph_base, env_api_version, is_api_version  # noqa: E402
from adapters.image.gemini import API_BASE as GEMINI_BASE, DEFAULT_MODEL as DEFAULT_IMAGE_MODEL  # noqa: E402
from adapters.inspo.apify import API_BASE as APIFY_BASE  # noqa: E402
from adapters.inspo.scrapecreators import API_BASE as SCRAPECREATORS_BASE  # noqa: E402
from adapters.model import DEFAULT_MODEL_ID  # noqa: E402
from adapters.turnstile.live import SECRET_CODES, SITEVERIFY_URL  # noqa: E402
from adapters.voc.reddit import DEFAULT_USER_AGENT as REDDIT_USER_AGENT, TOKEN_URL as REDDIT_TOKEN_URL  # noqa: E402

ANTHROPIC_MODELS = "https://api.anthropic.com/v1/models"
SCRAPECREATORS_BALANCE = "/v1/account/credit-balance"
SECRET_VARS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "SCRAPECREATORS_API_KEY", "META_ACCESS_TOKEN", "META_READ_TOKEN",
               "META_CAPI_TOKEN", "META_TEST_EVENT_CODE", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_STORAGE_PASSWORD",
               "TURNSTILE_SECRET_KEY", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "CAL_WEBHOOK_SECRET",
               "VERCEL_AUTOMATION_BYPASS_SECRET", "APIFY_TOKEN")
WORKER_VAR = "WAREHOUSE_URL_WORKER"   # the only role string preflight reads; --verify reads the others (NFR-1)
LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "::1"})
FAILING = frozenset({"auth failed", "wrong scope", "unreachable", "error"})
META_ACCOUNT_STATUS = {1: "active", 2: "disabled", 3: "unsettled", 7: "pending risk review", 8: "pending settlement",
                       9: "in grace period", 100: "pending closure", 101: "closed"}
DEFAULT_TRANSPORT: httpx.BaseTransport | None = None   # tests swap in an httpx.MockTransport


@dataclass(frozen=True)
class Result:
    service: str
    variables: tuple[str, ...]
    status: str
    detail: str = ""


def _json(resp: httpx.Response) -> dict:
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _http_status(resp: httpx.Response, auth=(401,), scope=(403,)) -> tuple[str, str] | None:
    if resp.status_code in auth:
        return "auth failed", f"HTTP {resp.status_code}"
    if resp.status_code in scope:
        return "wrong scope", f"HTTP {resp.status_code}"
    if resp.status_code >= 300:
        return "error", f"HTTP {resp.status_code}"
    return None


# ---------- one check per service: (status, detail) ----------

def check_anthropic(env: Mapping[str, str], http: httpx.Client) -> tuple[str, str]:
    want = env.get("MODEL_ID") or DEFAULT_MODEL_ID
    ids: set[str] = set()
    params: dict[str, str | int] = {"limit": 1000}
    for _ in range(10):
        resp = http.get(ANTHROPIC_MODELS, params=params,
                        headers={"x-api-key": env["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
        failed = _http_status(resp)
        if failed:
            kind = (_json(resp).get("error") or {}).get("type")
            return failed[0], failed[1] + (f" {kind}" if kind else "")
        body = _json(resp)
        ids |= {m.get("id") for m in body.get("data", []) if isinstance(m, dict)}
        if not body.get("has_more") or not body.get("last_id"):
            break
        params = {"limit": 1000, "after_id": body["last_id"]}
    return ("ok", f"{want} listed") if want in ids else ("wrong scope", f"{want} not listed")


def check_gemini(env: Mapping[str, str], http: httpx.Client) -> tuple[str, str]:
    want = env.get("IMAGE_MODEL") or DEFAULT_IMAGE_MODEL
    names: set[str] = set()
    params: dict[str, str | int] = {"pageSize": 1000}
    for _ in range(10):
        resp = http.get(f"{GEMINI_BASE}/models", params=params, headers={"x-goog-api-key": env["GEMINI_API_KEY"]})
        failed = _http_status(resp, auth=(400, 401))
        if failed:
            kind = (_json(resp).get("error") or {}).get("status")
            return failed[0], failed[1] + (f" {kind}" if kind else "")
        body = _json(resp)
        names |= {str(m.get("name", "")).removeprefix("models/") for m in body.get("models", []) if isinstance(m, dict)}
        if not body.get("nextPageToken"):
            break
        params = {"pageSize": 1000, "pageToken": body["nextPageToken"]}
    return ("ok", f"{want} listed") if want in names else ("wrong scope", f"{want} not listed")


def check_scrapecreators(env: Mapping[str, str], http: httpx.Client) -> tuple[str, str]:
    resp = http.get(SCRAPECREATORS_BASE + SCRAPECREATORS_BALANCE, headers={"x-api-key": env["SCRAPECREATORS_API_KEY"]})
    if resp.status_code == 402:
        return "ok", "key accepted, out of credits (HTTP 402)"
    failed = _http_status(resp, auth=(401, 403), scope=())
    if failed:
        return failed
    credits = _json(resp).get("creditCount")   # ASSUMED SHAPE: the vendor's tutorial pages show {"creditCount": n}
    return "ok", f"{credits} credits" if isinstance(credits, int) else "balance endpoint answered"


def check_apify(env: Mapping[str, str], http: httpx.Client) -> tuple[str, str]:
    resp = http.get(f"{APIFY_BASE}/users/me", headers={"authorization": f"Bearer {env['APIFY_TOKEN']}"})
    failed = _http_status(resp, auth=(401, 403), scope=())
    if failed:
        return failed
    plan = (_json(resp).get("data") or {}).get("plan") or {}
    plan_id = plan.get("id") if isinstance(plan, dict) else None
    return "ok", f"token accepted, plan {plan_id}" if isinstance(plan_id, str) and plan_id.isalnum() else "token accepted"


def _meta_error(resp: httpx.Response) -> tuple[str, str] | None:
    if resp.status_code < 300:
        return None
    err = _json(resp).get("error") or {}
    code = err.get("code")
    if code == 190 or resp.status_code == 401:
        return "auth failed", f"code {code}" if code is not None else f"HTTP {resp.status_code}"
    if code in (10, 100) or (isinstance(code, int) and 200 <= code <= 299) or resp.status_code == 403:
        return "wrong scope", f"code {code}" if code is not None else f"HTTP {resp.status_code}"
    return "error", f"HTTP {resp.status_code}" + (f" code {code}" if code is not None else "")


def check_meta_token(var: str, target: str) -> Callable[[Mapping[str, str], httpx.Client], tuple[str, str]]:
    """GET /me for the token, then the object this token must read: `account` (write, read) or `pixel` (CAPI)."""
    def check(env: Mapping[str, str], http: httpx.Client) -> tuple[str, str]:
        version = env.get("META_API_VERSION") or env_api_version()
        if not is_api_version(version):
            return "error", "META_API_VERSION is not vNN.N"
        base = graph_base(version)
        headers = {"authorization": f"Bearer {env[var]}"}
        failed = _meta_error(resp := http.get(base + "me", params={"fields": "id"}, headers=headers))
        if failed:
            return failed[0], f"/me {failed[1]}"
        if target == "account":
            account = env.get("META_AD_ACCOUNT_ID", "").strip().removeprefix("act_")
            if not account:
                return "ok", "/me ok; META_AD_ACCOUNT_ID not set, account not checked"
            act = f"act_{account}"
            resp = http.get(base + act, params={"fields": "account_status,currency,timezone_name,spend_cap"},
                            headers=headers)
            failed = _meta_error(resp)
            if failed:
                return failed[0], f"/me ok; {act} {failed[1]}"
            body = _json(resp)
            status = META_ACCOUNT_STATUS.get(body.get("account_status"), f"status {body.get('account_status')}")
            cap = "set" if str(body.get("spend_cap") or "0") not in ("0", "") else "not set"
            return "ok", f"/me ok; {act} {status}, {body.get('currency')}, spend_cap {cap}, {body.get('timezone_name')}"
        pixel = env.get("META_PIXEL_ID", "").strip()
        if not pixel:
            return "ok", "/me ok; META_PIXEL_ID not set, pixel not checked"
        failed = _meta_error(http.get(base + pixel, params={"fields": "id"}, headers=headers))
        if failed:
            return failed[0], f"/me ok; pixel {pixel} {failed[1]}"
        return "ok", f"/me ok; pixel {pixel} readable"
    return check


def check_supabase(env: Mapping[str, str], http: httpx.Client) -> tuple[str, str]:
    url = env["SUPABASE_URL"].rstrip("/")
    if urlsplit(url).scheme != "https":
        return "error", "SUPABASE_URL is not https"
    resp = http.get(f"{url}/auth/v1/health", headers={"apikey": env["SUPABASE_PUBLISHABLE_KEY"]})
    return _http_status(resp) or ("ok", "auth health ok")


def check_turnstile(env: Mapping[str, str], http: httpx.Client) -> tuple[str, str]:
    resp = http.post(SITEVERIFY_URL, data={"secret": env["TURNSTILE_SECRET_KEY"], "response": "preflight-dummy-token"})
    failed = _http_status(resp, auth=(), scope=())
    if failed:
        return failed
    body = _json(resp)
    codes = set(body.get("error-codes") or [])
    if codes & SECRET_CODES:
        return "auth failed", ", ".join(sorted(codes & SECRET_CODES))
    if body.get("success"):
        return "ok", "accepted a dummy token: this is a test secret that always passes"
    if "invalid-input-response" in codes:
        return "ok", "secret accepted (invalid-input-response for the dummy token)"
    return "error", ", ".join(sorted(codes)) or "no error-codes"


def check_reddit(env: Mapping[str, str], http: httpx.Client) -> tuple[str, str]:
    resp = http.post(REDDIT_TOKEN_URL, auth=(env["REDDIT_CLIENT_ID"], env["REDDIT_CLIENT_SECRET"]),
                     data={"grant_type": "client_credentials"},
                     headers={"user-agent": env.get("REDDIT_USER_AGENT") or REDDIT_USER_AGENT})
    failed = _http_status(resp)
    if failed:
        return failed
    return ("ok", "app-only token issued") if _json(resp).get("access_token") else ("error", "no access_token")


# ---------- the warehouse ----------

def worker_url(env: Mapping[str, str]) -> str:
    """WAREHOUSE_URL_WORKER from the environment, else .env (read, not loaded)."""
    if env.get(WORKER_VAR):
        return env[WORKER_VAR]
    if (ME_DIR / ".env").exists():
        from dotenv import dotenv_values
        return dotenv_values(ME_DIR / ".env").get(WORKER_VAR) or ""
    return ""


def verify_warehouse(env: Mapping[str, str]) -> tuple[int, str]:
    """scripts/apply_migrations.py --verify: connects as each of the five roles and reads; prints names only."""
    res = subprocess.run([sys.executable, str(ME_DIR / "scripts" / "apply_migrations.py"), "--verify"],
                         cwd=ME_DIR, env={**os.environ, **env}, capture_output=True, text=True, timeout=120)
    return res.returncode, res.stdout


def check_warehouse(url: str, verify: Callable[[Mapping[str, str]], tuple[int, str]]) -> tuple[str, str]:
    if not url:
        return "not set", ""
    if (urlsplit(url).hostname or "") in LOCAL_HOSTS:
        return "not set", "no Supabase pooler strings yet: the role strings are the local dev cluster"
    rc, out = verify({WORKER_VAR: url})
    fails = sum(1 for line in out.splitlines() if "FAIL" in line)
    if rc == 0:
        return "ok", "apply_migrations.py --verify passed for the five roles"
    return ("auth failed" if fails else "error"), f"apply_migrations.py --verify: {fails} FAIL line(s)"


# ---------- running and printing ----------

def _secrets(env: Mapping[str, str], url: str) -> list[str]:
    values = [env[v] for v in SECRET_VARS if len(env.get(v) or "") >= 4]
    if (password := urlsplit(url).password) and len(password) >= 2:
        values.append(password)
    return sorted(set(values), key=len, reverse=True)


def scrub(text: str, secrets: list[str]) -> str:
    for s in secrets:
        text = text.replace(s, "<redacted>")
    return text


def run_checks(env: Mapping[str, str], *, transport: httpx.BaseTransport | None = None,
               verify_warehouse: Callable[[Mapping[str, str]], tuple[int, str]] | None = None) -> list[Result]:
    verify = verify_warehouse or globals()["verify_warehouse"]
    plan: list[tuple[str, tuple[str, ...], tuple[str, ...], Callable]] = [
        # service, variables shown, variables required, check
        ("anthropic", ("ANTHROPIC_API_KEY",), ("ANTHROPIC_API_KEY",), check_anthropic),
        ("gemini", ("GEMINI_API_KEY",), ("GEMINI_API_KEY",), check_gemini),
        ("scrapecreators", ("SCRAPECREATORS_API_KEY",), ("SCRAPECREATORS_API_KEY",), check_scrapecreators),
        ("meta write token", ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID"), ("META_ACCESS_TOKEN",),
         check_meta_token("META_ACCESS_TOKEN", "account")),
        ("meta read token", ("META_READ_TOKEN", "META_AD_ACCOUNT_ID"), ("META_READ_TOKEN",),
         check_meta_token("META_READ_TOKEN", "account")),
        ("meta capi token", ("META_CAPI_TOKEN", "META_PIXEL_ID"), ("META_CAPI_TOKEN",),
         check_meta_token("META_CAPI_TOKEN", "pixel")),
        ("supabase", ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"), ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"),
         check_supabase),
        ("warehouse", (WORKER_VAR,), (), None),
        ("turnstile", ("TURNSTILE_SECRET_KEY",), ("TURNSTILE_SECRET_KEY",), check_turnstile),
        ("reddit", ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"), ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"), check_reddit),
        ("cal.com", ("CAL_WEBHOOK_SECRET",), ("CAL_WEBHOOK_SECRET",), None),
        ("apify", ("APIFY_TOKEN",), ("APIFY_TOKEN",), check_apify),
    ]
    url = worker_url(env)
    secrets = _secrets(env, url)
    results: list[Result] = []
    with httpx.Client(transport=transport, timeout=20.0, follow_redirects=False) as http:
        for service, shown, required, check in plan:
            if service == "warehouse":
                status, detail = check_warehouse(url, verify)
            else:
                present = [v for v in required if env.get(v)]
                if not present:
                    status, detail = "not set", ""
                elif len(present) < len(required):
                    status, detail = "not set", "missing " + ", ".join(v for v in required if not env.get(v))
                elif check is None:
                    status, detail = "set", "webhook signing secret: no read-only call to make"
                else:
                    try:
                        status, detail = check(env, http)
                    except httpx.HTTPError as exc:
                        status, detail = "unreachable", type(exc).__name__
            results.append(Result(service, shown, status, scrub(detail, secrets)))
    return results


def render_lines(results: list[Result]) -> list[str]:
    return [f"{r.service}: {r.status}" + (f" ({r.detail})" if r.detail else "") for r in results]


def render_markdown(results: list[Result], generated: str) -> str:
    rows = "\n".join(f"| {r.service} | {', '.join(f'`{v}`' for v in r.variables)} | {r.status} | {r.detail} |"
                     for r in results)
    return f"""# Credentials status

Names and status only, written by `scripts/preflight.py --write-status` on {generated}. Each set credential was proven
with one read-only call; no value is recorded here or anywhere in git. The keychain item behind each variable is in
`scripts/env_from_keychain.sh`.

| Service | Variables | Status | Detail |
|---------|-----------|--------|--------|
{rows}
"""


def exit_code(results: list[Result]) -> int:
    return 1 if any(r.status in FAILING for r in results) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write-status", metavar="PATH", help="also write the names-and-status table as Markdown")
    args = ap.parse_args(argv)
    results = run_checks(os.environ, transport=DEFAULT_TRANSPORT, verify_warehouse=verify_warehouse)
    for line in render_lines(results):
        print(line)
    if args.write_status:
        Path(args.write_status).write_text(render_markdown(results, generated=date.today().isoformat()))
        print(f"preflight: wrote {args.write_status}")
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
