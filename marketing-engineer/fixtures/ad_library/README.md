# Ad Library fixtures (INSPO_BACKEND=fixture) — ASSUMED SHAPE

These files imitate what we *assume* a scrapecreators Meta Ad Library "company ads" response looks like
(`searchResults[]` with `ad_archive_id`, `page_name`, `start_date` / `end_date` as unix seconds,
`is_active`, `publisher_platform`, and a `snapshot` carrying `body.text`, `title`, `link_url`,
`cta_text`, `display_format`, `images[].original_image_url`, `videos[]`, `cards[]`). Nobody has seen a
real response yet (CRUCIBLE.md §4). Go-live step 4 saves one real call as `real-001.json`; if the shape
differs, fix `adapters/inspo/fixture.py::normalise` and nothing else.

Every ad body is synthetic and says so. Image URLs use the `fixture://` scheme; the fixture adapter
renders a deterministic placeholder PNG for them, so nothing binary lives in git. Five DTC seed brands,
five ads each, with a mix of active/inactive and start dates on both sides of the 30-day rule.
Regenerate with `python3 fixtures/ad_library/generate.py`.
