# Gemini image contract fixtures (IMAGE_BACKEND=gemini) — ASSUMED SHAPE

`tests/test_image_gemini.py` serves these through `httpx.MockTransport`; nothing here was recorded from Google. Each
file is one HTTP exchange: `_shape`, `request`, `status`, `headers`, `body`. Image data is never committed: the test
builds small PNG/JPEG bytes with Pillow and substitutes them for `<PNG_BASE64>` / `<THOUGHT_PNG_BASE64>`.

Files: a normal image response (with an interim `thought` image the adapter must skip), a blocked prompt
(`promptFeedback.blockReason`), a blocked image (`finishReason: IMAGE_SAFETY`), a text-only decline, and the
invalid-key error envelope. Go-live step 5 is one real generation: save its JSON here with the base64 replaced by the
placeholder, and change `image_part` / `block_reason` at the top of `adapters/image/gemini.py` if the shape differs.
