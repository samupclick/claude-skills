# Apify contract fixtures (INSPO_BACKEND=apify): ASSUMED SHAPE

`tests/test_inspo_apify.py` serves these through `httpx.MockTransport`. Nothing here was recorded from the vendor. Each
file is one HTTP exchange: `_shape` (where the shape comes from), `request`, `status`, `body`.

- The run endpoints and their `data` envelope come from Apify's API v2 docs, read 2026-10-31.
- The ad fields come from the README sample of Apify's own actor `apify/facebook-ads-scraper`, read 2026-10-31.
  - Confirmed there: `adArchiveID`, `pageID`, `pageName`, `startDate` / `endDate` (Unix seconds), `isActive`,
    `publisherPlatform`, `snapshot.body.text`, `snapshot.title` / `linkUrl` / `ctaText` / `displayFormat`, and the
    `snapshot.videos[]` and `snapshot.cards[]` keys.
  - Not seen, because the sample had none: the entries of `snapshot.images[]`. They are assumed to use the cards'
    `originalImageUrl` / `resizedImageUrl`.

Every ad is SYNTHETIC. At go-live, save one real run's dataset here, replacing these bodies. If the real shape differs,
change `item_rows`, `item_id` and `normalise_item` at the top of `adapters/inspo/apify.py` and nothing else.
