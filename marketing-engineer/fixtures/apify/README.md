# Apify contract fixtures (INSPO_BACKEND=apify): shapes seen in real runs

`tests/test_inspo_apify.py` serves these through `httpx.MockTransport`. Each file is one HTTP exchange: `_shape`,
`request`, `status`, `body`.

The shapes were seen in real runs of Apify's own actor `apify/facebook-ads-scraper` on 2026-10-31, against the five
Circadian rivals, through the API v2 endpoints for starting a run, polling it and reading its dataset. Keys and types
are as seen. Every value is SYNTHETIC: no third-party ad is committed.

What a run's dataset holds:

- **One item per ad.** Seen keys include `adArchiveID`, `pageID`, `pageName`, `startDate` / `endDate` (Unix seconds),
  `startDateFormatted`, `isActive`, `publisherPlatform`, and `snapshot` with `body.text`, `title`, `linkUrl`,
  `ctaText`, `displayFormat`, `images`, `videos`, `cards`. (`dataset-items.json`)
- **A page with no ads**: one summary item `{inputUrl, pageInfo, isResultComplete, totalCount, results: []}`. This is
  zero ads, not a failure. (`dataset-page-summary.json`)
- **An input the actor cannot read**, such as a page slug that is not the advertiser: one error item
  `{url, error: "no_items", errorDescription}`. The source fails. (`dataset-error.json`)

Not seen yet: a non-empty `snapshot.images[]` entry. Its keys are assumed to be the cards' `originalImageUrl` /
`resizedImageUrl`. If a later run differs, change `item_rows`, `error_items`, `item_id` and `normalise_item` at the top
of `adapters/inspo/apify.py` and nothing else.
