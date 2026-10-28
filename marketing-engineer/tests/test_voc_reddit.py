"""VOC_BACKEND=reddit (FR-10, FR-11; CRUCIBLE A13): contract tests on httpx.MockTransport against fixtures/reddit/
(ASSUMED SHAPE, SYNTHETIC thread). Never the network, never a real credential. The normalised thread carries no author
field anywhere, drops deleted and removed comments, stops at the depth limit, and the client is polite: a minimum
interval between requests, backoff on 429, and the rate-limit window honoured."""
from __future__ import annotations

import importlib.util
import json
import sys
from uuid import uuid4

import httpx
import pytest

from adapters.env import ME_DIR, MissingEnvVar
from adapters.voc import get_voc, url_ref
from adapters.voc.reddit import (
    RedditAuthRequired, RedditError, RedditThreads, article_id, thread_title, walk_comments,
)

FIX = ME_DIR / "fixtures" / "reddit"
URL = "https://www.reddit.com/r/fixture_sub/comments/fx1abc/synthetic_thread/"
CLIENT_ID, SECRET = "fx-client-id-not-real", "fx-secret-not-real"


def exchange(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text())


def respond(name: str, **headers) -> httpx.Response:
    ex = exchange(name)
    return httpx.Response(ex["status"], json=ex["body"], headers={**ex.get("headers", {}), **headers})


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


class Reddit:
    """www.reddit.com (anonymous .json and the token endpoint) and oauth.reddit.com as fixtures."""

    def __init__(self, comments=None, token=None):
        self.requests: list[httpx.Request] = []
        self.comments = comments or (lambda request: respond("comments"))
        self.token = token or (lambda request: respond("access-token"))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "www.reddit.com" and request.url.path == "/api/v1/access_token":
            return self.token(request)
        if request.url.path.startswith("/comments/fx1abc"):
            return self.comments(request)
        return httpx.Response(404, json={"message": "Not Found", "error": 404})


def threads(reddit: Reddit, clock: Clock | None = None, **kw) -> RedditThreads:
    clock = clock or Clock()
    return RedditThreads(transport=httpx.MockTransport(reddit), clock=clock.time, sleep=clock.sleep, **kw)


def test_every_fixture_declares_its_assumed_shape_and_source():
    for f in sorted(FIX.glob("*.json")):
        shape = json.loads(f.read_text())["_shape"]
        assert shape.startswith("ASSUMED SHAPE from https://"), f
        assert "read 2026-10-28" in shape and "replace with a recorded response at go-live" in shape, f
    assert "SYNTHETIC" in (FIX / "README.md").read_text()


def test_anonymous_fetch_normalises_without_authors_deleted_removed_or_deep_comments():
    reddit = Reddit()
    thread = threads(reddit).fetch_thread(URL)
    (req,) = reddit.requests
    assert str(req.url).startswith("https://www.reddit.com/comments/fx1abc.json?")
    assert req.url.params["raw_json"] == "1" and req.url.params["depth"] == "3" and req.url.params["sort"] == "top"
    assert "authorization" not in req.headers
    ua = req.headers["user-agent"]
    assert ua.startswith("python:upclicklabs-marketing-engineer:") and "python-httpx" not in ua
    assert set(thread) == {"url", "title", "comments"} and thread["url"] == URL
    assert thread["title"] == "SYNTHETIC: Has anyone measured results from an 'AI search' agency?"
    ids = [c["id"] for c in thread["comments"]]
    assert ids == ["fxc1", "fxc2", "fxc3", "fxc7", "fxc9"]
    for c in thread["comments"]:
        assert set(c) == {"id", "text", "score"} and isinstance(c["score"], int) and c["text"]
    text = json.dumps(thread)
    for author in ("fx_user_", "fx_op_user", "AutoModerator", "t2_", "author", "Agency owner"):
        assert author not in text, f"{author!r} survived normalisation (A13)"
    assert "[deleted]" not in text and "[removed" not in text, "deleted and removed comments are dropped"
    assert "too deep" not in text, "depth limit: three levels"
    assert "self-promotion" not in text, "stickied moderator notices are not voice of customer"
    assert next(c for c in thread["comments"] if c["id"] == "fxc9")["text"].endswith("cite & nothing else moved the needle.")


def test_depth_and_comment_caps_are_parameters():
    shallow = threads(Reddit(), max_depth=1).fetch_thread(URL)
    assert [c["id"] for c in shallow["comments"]] == ["fxc1", "fxc9"]
    capped = threads(Reddit(), max_comments=2).fetch_thread(URL)
    assert [c["id"] for c in capped["comments"]] == ["fxc1", "fxc2"]


def test_shape_functions_read_the_listing_pair():
    body = exchange("comments")["body"]
    assert thread_title(body).startswith("SYNTHETIC")
    assert [c["id"] for c in walk_comments(body, max_depth=2, max_comments=50)] == ["fxc1", "fxc2", "fxc7", "fxc9"]


@pytest.mark.parametrize("url,expected", [
    (URL, "fx1abc"),
    ("https://old.reddit.com/r/x/comments/fx1abc/", "fx1abc"),
    ("https://reddit.com/comments/fx1abc", "fx1abc"),
    ("https://www.reddit.com/r/x/comments/fx1abc/slug/?utm_source=share", "fx1abc"),
    ("https://redd.it/fx1abc", "fx1abc"),
])
def test_article_id_from_thread_urls(url, expected):
    assert article_id(url) == expected


@pytest.mark.parametrize("url", [
    "PLACEHOLDER: https://www.reddit.com/r/…/1",
    "https://www.reddit.com/r/marketing/",
    "https://evil.example/r/x/comments/fx1abc/",
    "http://www.reddit.com/r/x/comments/fx1abc/",
])
def test_anything_but_a_reddit_thread_url_is_refused_without_echoing_it(url):
    reddit = Reddit()
    with pytest.raises(ValueError) as exc:
        threads(reddit).fetch_thread(url)
    assert url_ref(url) in str(exc.value) and "reddit.com/r" not in str(exc.value) and "evil" not in str(exc.value)
    assert reddit.requests == []


def test_oauth_app_only_token_is_fetched_once_and_used_on_oauth_reddit_com():
    reddit = Reddit()
    t = threads(reddit, client_id=CLIENT_ID, client_secret=SECRET)
    t.fetch_thread(URL)
    t.fetch_thread(URL)
    token_req, api1, api2 = reddit.requests
    assert token_req.method == "POST" and str(token_req.url) == "https://www.reddit.com/api/v1/access_token"
    assert token_req.headers["authorization"].startswith("Basic ")
    assert token_req.content == b"grant_type=client_credentials"
    for api in (api1, api2):
        assert api.url.host == "oauth.reddit.com" and api.url.path == "/comments/fx1abc"
        assert api.headers["authorization"] == "bearer fixture-token-not-real"
        assert api.headers["user-agent"].startswith("python:upclicklabs-marketing-engineer:")


def test_an_expired_token_is_refreshed_once_on_401():
    calls = {"n": 0}

    def comments(request):
        calls["n"] += 1
        return httpx.Response(401, json={"message": "Unauthorized", "error": 401}) if calls["n"] == 1 else respond("comments")

    reddit = Reddit(comments=comments)
    thread = threads(reddit, client_id=CLIENT_ID, client_secret=SECRET).fetch_thread(URL)
    assert len(thread["comments"]) == 5
    assert [r.url.path for r in reddit.requests] == ["/api/v1/access_token", "/comments/fx1abc",
                                                     "/api/v1/access_token", "/comments/fx1abc"]


def test_bad_credentials_name_the_variables_never_the_values():
    reddit = Reddit(token=lambda r: httpx.Response(401, json={"message": "Unauthorized", "error": 401}))
    with pytest.raises(RedditAuthRequired) as exc:
        threads(reddit, client_id=CLIENT_ID, client_secret=SECRET).fetch_thread(URL)
    msg = str(exc.value)
    assert "REDDIT_CLIENT_ID" in msg and "REDDIT_CLIENT_SECRET" in msg and SECRET not in msg and CLIENT_ID not in msg


def test_anonymous_403_says_oauth_is_needed_and_names_the_variables_not_the_url():
    reddit = Reddit(comments=lambda r: httpx.Response(403, json={"message": "Forbidden", "error": 403}))
    with pytest.raises(RedditAuthRequired) as exc:
        threads(reddit).fetch_thread(URL)
    msg = str(exc.value)
    assert "REDDIT_CLIENT_ID" in msg and "REDDIT_CLIENT_SECRET" in msg and url_ref(URL) in msg and "fixture_sub" not in msg


def test_429_backs_off_with_retry_after_then_succeeds():
    calls = {"n": 0}

    def comments(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "7", "x-ratelimit-remaining": "0", "x-ratelimit-reset": "30"})
        return respond("comments")

    clock = Clock()
    thread = threads(Reddit(comments=comments), clock).fetch_thread(URL)
    assert len(thread["comments"]) == 5 and clock.sleeps == [7.0]


def test_429_without_retry_after_waits_for_the_rate_limit_reset():
    calls = {"n": 0}

    def comments(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "30"})
        return respond("comments")

    clock = Clock()
    threads(Reddit(comments=comments), clock).fetch_thread(URL)
    assert clock.sleeps == [30.0]


def test_persistent_429_fails_after_the_retries_without_the_url():
    clock = Clock()
    reddit = Reddit(comments=lambda r: httpx.Response(429, headers={"retry-after": "1"}))
    with pytest.raises(RedditError, match="429") as exc:
        threads(reddit, clock).fetch_thread(URL)
    assert len(reddit.requests) == 3 and "fixture_sub" not in str(exc.value)


def test_requests_keep_a_minimum_interval_and_respect_a_spent_window():
    clock = Clock()
    t = threads(Reddit(), clock, min_interval=6.0)
    t.fetch_thread(URL)
    assert clock.sleeps == [], "the first request goes at once"
    clock.now += 2.0
    t.fetch_thread(URL)
    assert clock.sleeps == [4.0], "six seconds between requests, two already passed"

    spent = Reddit(comments=lambda r: respond("comments", **{"x-ratelimit-remaining": "0", "x-ratelimit-reset": "45"}))
    clock = Clock()
    t = threads(spent, clock, min_interval=1.0)
    t.fetch_thread(URL)
    t.fetch_thread(URL)
    assert clock.sleeps == [45.0], "a spent window waits for its reset, not just the interval"


def test_selector_anonymous_by_default_oauth_with_both_variables(monkeypatch):
    monkeypatch.setenv("VOC_BACKEND", "reddit")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "")
    anon = get_voc()
    assert isinstance(anon, RedditThreads) and anon.oauth is False and anon.min_interval == 6.0
    monkeypatch.setenv("REDDIT_CLIENT_ID", CLIENT_ID)
    with pytest.raises(MissingEnvVar) as exc:
        get_voc()
    assert "REDDIT_CLIENT_SECRET" in str(exc.value) and CLIENT_ID not in str(exc.value)
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", SECRET)
    live = get_voc()
    assert live.oauth is True and live.min_interval == 1.0
    monkeypatch.setenv("REDDIT_USER_AGENT", "python:upclicklabs-voc:1.0 (by /u/fixture)")
    assert get_voc().user_agent == "python:upclicklabs-voc:1.0 (by /u/fixture)"


def test_pull_voc_public_sources_ingest_the_reddit_thread_without_authors():
    """The language worker's fetch step on this backend: hashed ref, purge date, payload in the normalised shape."""
    spec = importlib.util.spec_from_file_location("pull_voc_reddit", ME_DIR / "scripts" / "pull_voc.py")
    pv = importlib.util.module_from_spec(spec)
    sys.modules["pull_voc_reddit"] = pv
    spec.loader.exec_module(pv)
    from warehouse.client import Run

    r = Run(id=uuid4(), worker="voc", client_id=None)
    sources, failed = pv.public_sources([URL], threads(Reddit()), r)
    assert failed == [] and len(sources) == 1
    src = sources[0]
    assert src.ref == url_ref(URL) and src.source == "reddit" and src.visibility == "public" and src.purge_after
    assert set(src.payload) == {"url", "title", "comments"} and "fx_user_" not in json.dumps(src.payload)
    assert "SYNTHETIC: Prospects now literally say an AI suggested us." in src.text
