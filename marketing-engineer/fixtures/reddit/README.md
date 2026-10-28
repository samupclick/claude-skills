# Reddit contract fixtures (VOC_BACKEND=reddit) — ASSUMED SHAPE, SYNTHETIC thread

`tests/test_voc_reddit.py` serves these through `httpx.MockTransport`; nothing here was recorded from Reddit. Each file
is one HTTP exchange: `_shape`, `request`, `status`, `headers`, `body`. The thread is invented; its author names
(`fx_user_*`) exist only so the tests can prove that no author survives normalisation (CRUCIBLE A13). It also carries a
`[deleted]`, a `[removed]` and a `[removed by Reddit]` comment, a stickied moderator notice, a comment below the depth
limit and two `more` stubs.

At go-live save one real response for a configured thread here (strip nothing; the adapter drops the authors) and,
when OAuth is used, never the token. If the real shape differs, change `thread_title` / `walk_comments` at the top
of `adapters/voc/reddit.py` and nothing else.
