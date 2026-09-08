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

`write_copy.json` and `image_text_check.json` (T5, `scripts/render_creatives.py`) are the same kind of exception:
hand-written, copy says FIXTURE, three copy outputs cycle in call order (one per chosen brief) and every overlay
carries the slots of both templates so any pick validates; the vision check always answers "no text" (placeholder
images do carry a small hash label, so this fixture is only right for dev mode). Re-record both with
`MODEL_BACKEND=claude` and `IMAGE_BACKEND=gemini` at go-live step 5.

`gate_checks.json`, `gate_vision.json`, `gate_rubric.json` (T6, `scripts/gate.py`): hand-written clean answers for the
model-judged hard checks (policy, brand flags, fabricated testimonial, coherence; likeness, depicted person, logos) and
two shadow rubric scorings that alternate approve / reject. The warehouse-computed checks (`components`, `landing`,
`verbatim`, rule-based `brand`) fail for real in dev mode; the model-judged failures are exercised with temporary
fixtures in `tests/test_gate.py`. Re-record with `MODEL_BACKEND=claude` at go-live.
