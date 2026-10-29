"""scripts/preflight.py against httpx.MockTransport: one read-only call per backend whose variables are set, a
names-and-status line per service, and no secret value anywhere in the output, even when a vendor echoes it."""
import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

ME_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("preflight", ME_DIR / "scripts" / "preflight.py")
preflight = importlib.util.module_from_spec(_spec)
sys.modules["preflight"] = preflight   # dataclasses look the module up by name
_spec.loader.exec_module(preflight)

SECRETS = {
    "ANTHROPIC_API_KEY": "SENTINEL-anthropic-key-0001",
    "GEMINI_API_KEY": "SENTINEL-gemini-key-0002",
    "SCRAPECREATORS_API_KEY": "SENTINEL-scrape-key-0003",
    "META_ACCESS_TOKEN": "SENTINEL-meta-write-0004",
    "META_READ_TOKEN": "SENTINEL-meta-read-0005",
    "META_CAPI_TOKEN": "SENTINEL-meta-capi-0006",
    "SUPABASE_PUBLISHABLE_KEY": "SENTINEL-supabase-pub-0007",
    "TURNSTILE_SECRET_KEY": "SENTINEL-turnstile-0008",
    "REDDIT_CLIENT_ID": "SENTINEL-reddit-id-0009",
    "REDDIT_CLIENT_SECRET": "SENTINEL-reddit-secret-0010",
    "CAL_WEBHOOK_SECRET": "SENTINEL-cal-0011",
}
IDS = {"META_AD_ACCOUNT_ID": "1234567890", "META_PIXEL_ID": "555000111", "SUPABASE_URL": "https://abc.supabase.co"}


def echo(request):
    """Everything the request carried that might be a secret, as a vendor error body would quote it."""
    return f"{request.url} {dict(request.headers)} {request.content.decode(errors='replace')}"


def vendor(request, *, bad=(), noscope=()):
    """A fake of every vendor: valid keys pass, a key named in `bad` fails the way that vendor fails, a Meta token
    named in `noscope` authenticates but cannot read the ad account."""
    host, path = request.url.host, request.url.path
    auth = request.headers.get("authorization", "")
    if host == "api.anthropic.com" and path == "/v1/models":
        if "ANTHROPIC_API_KEY" in bad:
            return httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": echo(request)}})
        return httpx.Response(200, json={"data": [{"id": "claude-opus-5-5"}, {"id": "claude-opus-5"}], "has_more": False})
    if host == "generativelanguage.googleapis.com" and path == "/v1beta/models":
        if "GEMINI_API_KEY" in bad:
            return httpx.Response(400, json={"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": echo(request)}})
        return httpx.Response(200, json={"models": [{"name": "models/gemini-nano-banana-2.1"}]})
    if host == "api.scrapecreators.com" and path == "/v1/account/credit-balance":
        if "SCRAPECREATORS_API_KEY" in bad:
            return httpx.Response(401, json={"message": echo(request)})
        return httpx.Response(200, json={"creditCount": 333})
    if host == "graph.facebook.com":
        token = auth.removeprefix("Bearer ")
        if any(SECRETS[v] == token for v in bad if v.startswith("META_")):
            return httpx.Response(400, json={"error": {"code": 190, "type": "OAuthException", "message": echo(request)}})
        if path.endswith("/me"):
            return httpx.Response(200, json={"id": "42"})
        if path.endswith("/act_1234567890"):
            if any(SECRETS[v] == token for v in noscope):
                return httpx.Response(403, json={"error": {"code": 200, "type": "OAuthException", "message": echo(request)}})
            return httpx.Response(200, json={"account_status": 1, "currency": "USD", "timezone_name": "Europe/London",
                                             "spend_cap": "50000", "id": "act_1234567890"})
        if path.endswith("/555000111"):
            return httpx.Response(200, json={"id": "555000111"})
    if host == "abc.supabase.co" and path == "/auth/v1/health":
        if "SUPABASE_PUBLISHABLE_KEY" in bad:
            return httpx.Response(401, json={"message": echo(request)})
        return httpx.Response(200, json={"name": "GoTrue"})
    if host == "challenges.cloudflare.com":
        codes = ["invalid-input-secret"] if "TURNSTILE_SECRET_KEY" in bad else ["invalid-input-response"]
        return httpx.Response(200, json={"success": False, "error-codes": codes, "messages": [echo(request)]})
    if host == "www.reddit.com" and path == "/api/v1/access_token":
        if "REDDIT_CLIENT_SECRET" in bad:
            return httpx.Response(401, json={"message": "Unauthorized", "error": 401, "echo": echo(request)})
        return httpx.Response(200, json={"access_token": "SENTINEL-reddit-bearer", "token_type": "bearer", "expires_in": 86400})
    return httpx.Response(599, text=f"unexpected {request.method} {request.url}")


def transport(bad=(), calls=None, noscope=()):
    def handler(request):
        if calls is not None:
            calls.append((request.method, request.url.host, request.url.path))
        return vendor(request, bad=bad, noscope=noscope)
    return httpx.MockTransport(handler)


def all_output(results, capsys):
    lines = preflight.render_lines(results)
    md = preflight.render_markdown(results, generated="2026-10-29")
    return "\n".join(lines) + "\n" + md + capsys.readouterr().out


def by_service(results):
    return {r.service: r for r in results}


def warehouse_local(env):
    return None


def test_every_backend_ok_with_one_read_only_call_each(capsys):
    calls = []
    env = {**SECRETS, **IDS}
    results = preflight.run_checks(env, transport=transport(calls=calls), verify_warehouse=warehouse_local)
    got = {s: r.status for s, r in by_service(results).items()}
    assert got == {"anthropic": "ok", "gemini": "ok", "scrapecreators": "ok", "meta write token": "ok",
                   "meta read token": "ok", "meta capi token": "ok", "supabase": "ok", "warehouse": "not set",
                   "turnstile": "ok", "reddit": "ok", "cal.com": "set"}
    assert "claude-opus-5-5 listed" in by_service(results)["anthropic"].detail
    assert "gemini-nano-banana-2.1 listed" in by_service(results)["gemini"].detail
    assert "333 credits" in by_service(results)["scrapecreators"].detail
    assert "act_1234567890 active, USD, spend_cap set" in by_service(results)["meta read token"].detail
    assert "pixel 555000111 readable" in by_service(results)["meta capi token"].detail
    assert {m for m, _, _ in calls} <= {"GET", "POST"}
    posts = {(h, p) for m, h, p in calls if m == "POST"}
    assert posts == {("challenges.cloudflare.com", "/turnstile/v0/siteverify"), ("www.reddit.com", "/api/v1/access_token")}
    assert not any("adimages" in p or "/ads" in p or "/campaigns" in p for _, _, p in calls)
    assert "SENTINEL" not in all_output(results, capsys)


def test_failures_are_labelled_and_no_echoed_secret_is_printed(capsys):
    bad = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "SCRAPECREATORS_API_KEY", "META_ACCESS_TOKEN",
           "SUPABASE_PUBLISHABLE_KEY", "TURNSTILE_SECRET_KEY", "REDDIT_CLIENT_SECRET")
    results = preflight.run_checks({**SECRETS, **IDS}, transport=transport(bad=bad), verify_warehouse=warehouse_local)
    got = {s: r.status for s, r in by_service(results).items()}
    for service in ("anthropic", "gemini", "scrapecreators", "meta write token", "supabase", "turnstile", "reddit"):
        assert got[service] == "auth failed", (service, by_service(results)[service])
    assert got["meta read token"] == "ok"
    out = all_output(results, capsys)
    for value in SECRETS.values():
        assert value not in out
    assert "SENTINEL" not in out
    assert preflight.exit_code(results) == 1


def test_token_that_cannot_read_the_ad_account_is_wrong_scope():
    env = {"META_READ_TOKEN": SECRETS["META_READ_TOKEN"], "META_AD_ACCOUNT_ID": IDS["META_AD_ACCOUNT_ID"]}
    (r,) = [r for r in preflight.run_checks(env, transport=transport(noscope=("META_READ_TOKEN",)),
                                            verify_warehouse=warehouse_local) if r.service == "meta read token"]
    assert r.status == "wrong scope" and "act_1234567890" in r.detail


def test_model_not_listed_is_wrong_scope(monkeypatch):
    env = {"ANTHROPIC_API_KEY": SECRETS["ANTHROPIC_API_KEY"], "MODEL_ID": "claude-fable-5-1"}
    (r,) = [r for r in preflight.run_checks(env, transport=transport(), verify_warehouse=warehouse_local)
            if r.service == "anthropic"]
    assert (r.status, r.detail) == ("wrong scope", "claude-fable-5-1 not listed")


def test_nothing_set_makes_no_call_and_says_not_set():
    calls = []
    results = preflight.run_checks({}, transport=transport(calls=calls), verify_warehouse=warehouse_local)
    assert calls == []
    assert {r.status for r in results} == {"not set"}
    assert preflight.exit_code(results) == 0
    assert {"meta write token", "meta read token", "meta capi token"} <= {r.service for r in results}


def test_half_set_reddit_or_supabase_is_incomplete_not_a_call():
    calls = []
    env = {"REDDIT_CLIENT_ID": SECRETS["REDDIT_CLIENT_ID"], "SUPABASE_URL": IDS["SUPABASE_URL"]}
    results = by_service(preflight.run_checks(env, transport=transport(calls=calls), verify_warehouse=warehouse_local))
    assert calls == []
    assert results["reddit"].status == "not set" and "REDDIT_CLIENT_SECRET" in results["reddit"].detail
    assert results["supabase"].status == "not set" and "SUPABASE_PUBLISHABLE_KEY" in results["supabase"].detail


def test_unreachable_vendor_is_reported_without_the_key(capsys):
    def boom(request):
        raise httpx.ConnectError(f"cannot reach {request.url} with {request.headers.get('x-api-key')}")
    results = preflight.run_checks({"ANTHROPIC_API_KEY": SECRETS["ANTHROPIC_API_KEY"]},
                                   transport=httpx.MockTransport(boom), verify_warehouse=warehouse_local)
    (r,) = [r for r in results if r.service == "anthropic"]
    assert r.status == "unreachable" and "ConnectError" in r.detail
    assert "SENTINEL" not in all_output(results, capsys)


def test_remote_warehouse_strings_run_the_read_only_verify():
    seen = {}

    def verify(env):
        seen.update(env)
        return (0, "verify: worker_rw families=12\nverify: executor families=12")

    env = {"WAREHOUSE_URL_WORKER": "postgresql://worker_rw:pw@aws-0-eu-west-1.pooler.supabase.com:5432/postgres?sslmode=require"}
    (r,) = [r for r in preflight.run_checks(env, transport=transport(), verify_warehouse=verify) if r.service == "warehouse"]
    assert r.status == "ok"
    assert "WAREHOUSE_URL_WORKER" in seen
    assert "pw" not in r.detail


def test_main_prints_names_and_status_and_writes_the_status_file(tmp_path, monkeypatch, capsys):
    for k in list(SECRETS) + list(IDS) + ["MODEL_ID", "IMAGE_MODEL"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRETS["ANTHROPIC_API_KEY"])
    monkeypatch.setattr(preflight, "DEFAULT_TRANSPORT", transport())
    monkeypatch.setattr(preflight, "verify_warehouse", warehouse_local)
    status_file = tmp_path / "credentials-status.md"
    assert preflight.main(["--write-status", str(status_file)]) == 0
    out = capsys.readouterr().out
    assert "anthropic: ok (claude-opus-5-5 listed)" in out
    assert "gemini: not set" in out
    md = status_file.read_text()
    assert "| anthropic | `ANTHROPIC_API_KEY` | ok | claude-opus-5-5 listed |" in md
    assert "SENTINEL" not in out + md
