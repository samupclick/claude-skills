# Model fixtures (MODEL_BACKEND=fixture)

One file per `task` name passed to `generate_json(task=...)`: `<task>.json`. Either a single JSON object,
or `{"outputs": [obj, obj, ...]}` replayed in call order (wrapping around). Every output is validated
against the schema the caller passes, so a stale fixture fails loudly. Record fixtures by running the
worker once with `MODEL_BACKEND=claude` and saving the validated output; never hand-write values that
look real.

`decompose_ad.json` (T2, `scripts/pull_inspo.py`) is the exception so far: SYNTHETIC, not recorded, because the
build container has no `ANTHROPIC_API_KEY` and the ad-library fixtures are placeholder images with synthetic
text, so a recorded decomposition would be meaningless anyway. Its six outputs cycle in call order and line up
with the six fixture ads per brand (see its `_shape`). Replace it with a recorded output at go-live step 4.

`voc_extract.json` (T3, `scripts/pull_voc.py`) is the same kind of exception: hand-written from the SYNTHETIC
voc-seed notes and `fixtures/voc/` threads, six outputs replayed in source order (three notes sorted by name,
then `voc.public_sources` in config order; see its `_order`). Re-record it with `MODEL_BACKEND=claude` once the
seed notes are real (go-live step 3).
