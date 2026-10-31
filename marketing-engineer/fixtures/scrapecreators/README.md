# scrapecreators contract fixtures (INSPO_BACKEND=scrapecreators) — ASSUMED SHAPE

`tests/test_inspo_scrapecreators.py` serves these through `httpx.MockTransport`; nothing here was recorded from the
vendor. Each file is one HTTP exchange: `_shape` (where the shape comes from), `request`, `status`, `headers`, `body`.
The scrapecreators docs were not reachable from the build session (2026-10-28), so the endpoint paths, the `x-api-key`
header and the field names come from search-result summaries of the vendor's pages and from the T2 fixture assumption
in `fixtures/ad_library/`. Every ad is SYNTHETIC.

At go-live (dev-mode.md step 4) save one real call per endpoint here, replacing these bodies. If the real shape differs,
change the shape functions at the top of `adapters/inspo/scrapecreators.py` (`company_results`, `company_page_id`,
`page_rows`, `next_cursor`, `normalise`) and nothing else: the fixture backend uses the same functions.
