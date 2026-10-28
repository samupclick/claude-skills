"""Public Reddit threads (VOC_BACKEND=reddit): FR-10, FR-11; CRUCIBLE A13.

`fetch_thread(url)` reads one thread as JSON and returns `{url, title, comments[{id, text, score}]}`: no author field
exists anywhere in the result, deleted and removed comments and stickied moderator notices are dropped, replies stop
at `max_depth` levels and the walk at `max_comments`, and `more` stubs are not expanded. Two access paths:

- REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET set: app-only OAuth (client_credentials), API calls on oauth.reddit.com,
  at most one request a second (Reddit's free tier is 100 a minute per OAuth client);
- neither set: the anonymous `.json` endpoint on www.reddit.com, one request every six seconds. Third-party reports
  from mid-2026 say Reddit now answers anonymous `.json` with 403; that answer raises RedditAuthRequired naming the
  two variables, so the go-live setting is the OAuth pair.

Every request carries a descriptive User-Agent (REDDIT_USER_AGENT overrides it; Reddit asks for
`<platform>:<app id>:<version> (by /u/<username>)`), waits out a spent rate-limit window (X-Ratelimit-Remaining /
X-Ratelimit-Reset) and backs off on 429. Errors name the thread by its hashed ref, never by URL (FR-11). The
response shape is ASSUMED (fixtures/reddit/README.md): `listing_pair`, `thread_title` and `walk_comments` are the
only functions that know it.
"""
from __future__ import annotations

import html
import os
import re
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

from adapters import backoff
from adapters.env import require
from adapters.voc import url_ref

VERSION = "0.1"
DEFAULT_USER_AGENT = f"python:upclicklabs-marketing-engineer:{VERSION} (read-only voice-of-customer research)"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_BASE = "https://oauth.reddit.com"
PUBLIC_BASE = "https://www.reddit.com"
REDDIT_HOSTS = frozenset({"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "np.reddit.com", "m.reddit.com"})
THREAD_PATH = re.compile(r"^/(?:r/[^/]+/)?comments/([a-z0-9]+)(?:/|$)", re.I)
SHORT_PATH = re.compile(r"^/([a-z0-9]+)/?$", re.I)
GONE = re.compile(r"^\[(?:deleted|removed)(?: by [^\]]*)?\]$", re.I)


class RedditError(RuntimeError):
    """Reddit failed or answered something unexpected. Names the thread by hashed ref only."""


class RedditAuthRequired(RedditError):
    """Reddit refused the request for lack of (valid) app credentials. Names the variables, never their values."""


# ---------- the response shape: ASSUMED until a real response is saved; a different shape changes only these ----------

def listing_pair(body: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """(post listing, comment listing) from the two-element array Reddit returns for a thread."""
    if not (isinstance(body, list) and len(body) >= 2 and all(isinstance(x, dict) for x in body[:2])):
        raise RedditError("Reddit answered a thread request with an unexpected shape (expected [post, comments])")
    return body[0], body[1]


def thread_title(body: Any) -> str:
    post, _ = listing_pair(body)
    children = (post.get("data") or {}).get("children") or [{}]
    return html.unescape(str((children[0].get("data") or {}).get("title") or "")).strip()


def walk_comments(body: Any, *, max_depth: int, max_comments: int) -> list[dict[str, Any]]:
    """Depth-first, in Reddit's order: t1 comments above `max_depth` levels as {id, text, score}; nothing else kept."""
    _, comments = listing_pair(body)
    out: list[dict[str, Any]] = []

    def walk(listing: Any, level: int) -> None:
        if level >= max_depth or not isinstance(listing, dict):
            return
        for child in (listing.get("data") or {}).get("children") or []:
            if len(out) >= max_comments:
                return
            if not isinstance(child, dict) or child.get("kind") != "t1":
                continue
            data = child.get("data") or {}
            text = html.unescape(str(data.get("body") or "")).strip()
            notice = data.get("stickied") and data.get("distinguished") == "moderator"
            if text and not GONE.match(text) and not notice:
                out.append({"id": str(data.get("id")), "text": text, "score": int(data.get("score") or 0)})
            walk(data.get("replies"), level + 1)

    walk(comments, 0)
    return out


# ---------- the backend ----------

def article_id(url: str) -> str | None:
    """The thread id of an https reddit.com /comments/<id> or redd.it/<id> URL; None for anything else."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        return None
    match = SHORT_PATH.match(parts.path) if host == "redd.it" else THREAD_PATH.match(parts.path) if host in REDDIT_HOSTS else None
    return match.group(1).lower() if match else None


class RedditThreads:
    def __init__(self, *, client_id: str | None = None, client_secret: str | None = None, user_agent: str | None = None,
                 transport: httpx.BaseTransport | None = None, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, min_interval: float | None = None, max_depth: int = 3,
                 max_comments: int = 200, timeout: float = 30.0, attempts: int = 3):
        self.oauth = bool(client_id and client_secret)
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.min_interval = min_interval if min_interval is not None else (1.0 if self.oauth else 6.0)
        self.max_depth, self.max_comments = max_depth, max_comments
        self._auth = (client_id or "", client_secret or "")
        self._client = httpx.Client(transport=transport, timeout=timeout, follow_redirects=True, max_redirects=3,
                                    headers={"user-agent": self.user_agent, "accept": "application/json"})
        self._clock, self._sleep, self._attempts = clock, sleep, attempts
        self._token: str | None = None
        self._token_expires = 0.0
        self._not_before = 0.0
        self.calls = 0

    @classmethod
    def from_env(cls) -> "RedditThreads":
        agent = os.environ.get("REDDIT_USER_AGENT") or None
        if os.environ.get("REDDIT_CLIENT_ID") or os.environ.get("REDDIT_CLIENT_SECRET"):
            creds = require("voc", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")
            return cls(client_id=creds["REDDIT_CLIENT_ID"], client_secret=creds["REDDIT_CLIENT_SECRET"], user_agent=agent)
        return cls(user_agent=agent)

    def fetch_thread(self, url: str) -> dict[str, Any]:
        ref = url_ref(url)
        article = article_id(url)
        if article is None:
            raise ValueError(f"{ref} is not a Reddit thread URL (expected https on reddit.com with /comments/<id>, "
                             "or redd.it/<id>)")
        params = {"raw_json": "1", "sort": "top", "depth": str(self.max_depth), "limit": str(self.max_comments)}
        if self.oauth:
            body = self._oauth_get(f"{OAUTH_BASE}/comments/{article}", params, ref)
        else:
            body = self._json(self._request("GET", f"{PUBLIC_BASE}/comments/{article}.json", ref, params=params), ref)
        return {"url": url, "title": thread_title(body),
                "comments": walk_comments(body, max_depth=self.max_depth, max_comments=self.max_comments)}

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, url: str, ref: str, **kwargs: Any) -> httpx.Response:
        wait = self._not_before - self._clock()
        if wait > 0:
            self._sleep(wait)

        def tick() -> None:
            self.calls += 1

        try:
            response = backoff.send(self._client, method, url, attempts=self._attempts, sleep=self._sleep,
                                    on_attempt=tick, **kwargs)
        except httpx.TransportError as exc:
            raise RedditError(f"{ref}: Reddit unreachable ({type(exc).__name__})") from exc
        self._not_before = self._clock() + max(self.min_interval, self._window_wait(response))
        return response

    @staticmethod
    def _window_wait(response: httpx.Response) -> float:
        remaining = backoff.header_seconds(response.headers.get("x-ratelimit-remaining"))
        if remaining is None or remaining >= 1:
            return 0.0
        return backoff.header_seconds(response.headers.get("x-ratelimit-reset")) or 0.0

    def _oauth_get(self, url: str, params: dict[str, str], ref: str) -> Any:
        for attempt in (1, 2):
            response = self._request("GET", url, ref, params=params, headers={"authorization": f"bearer {self._bearer(ref)}"})
            if response.status_code == 401 and attempt == 1:
                self._token = None
                continue
            return self._json(response, ref)
        raise AssertionError("unreachable")

    def _bearer(self, ref: str) -> str:
        if self._token is None or self._clock() >= self._token_expires:
            response = self._request("POST", TOKEN_URL, ref, auth=self._auth, data={"grant_type": "client_credentials"})
            if response.status_code in (400, 401, 403):
                raise RedditAuthRequired(f"Reddit refused the app credentials (HTTP {response.status_code}); "
                                         "check REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
            if response.status_code >= 400:
                raise RedditError(f"{ref}: Reddit token endpoint answered HTTP {response.status_code}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise RedditError(f"{ref}: Reddit token endpoint answered something that is not JSON") from exc
            token = payload.get("access_token") if isinstance(payload, dict) else None
            if not token:
                raise RedditAuthRequired("Reddit issued no access token; check REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET")
            self._token = str(token)
            self._token_expires = self._clock() + max(float(payload.get("expires_in") or 3600) - 60, 60)
        return self._token

    def _json(self, response: httpx.Response, ref: str) -> Any:
        status = response.status_code
        if status in (401, 403):
            how = "the app token" if self.oauth else "an anonymous .json request"
            raise RedditAuthRequired(f"{ref}: Reddit answered HTTP {status} to {how}; set REDDIT_CLIENT_ID and "
                                     "REDDIT_CLIENT_SECRET (app-only OAuth, an approved Reddit app)")
        if status == 429:
            raise RedditError(f"{ref}: Reddit HTTP 429 (rate limited) after {self._attempts} tries")
        if status >= 400:
            raise RedditError(f"{ref}: Reddit answered HTTP {status}")
        try:
            return response.json()
        except ValueError as exc:
            raise RedditError(f"{ref}: Reddit answered something that is not JSON") from exc
