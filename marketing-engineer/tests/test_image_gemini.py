"""IMAGE_BACKEND=gemini (FR-24, FR-25): contract tests on httpx.MockTransport against fixtures/gemini/ (ASSUMED SHAPE).
Never the network, never a real key; image bytes are generated here, nothing binary is committed. The prompt goes
out verbatim (the producer's no-text instruction included), the answer comes back as a PNG of exactly the asked size,
and a safety block is an `ImageBlocked` the producer counts as one failed attempt."""
from __future__ import annotations

import base64
import importlib.util
import io
import json

import httpx
import pytest
from PIL import Image

from adapters.env import ME_DIR, MissingEnvVar, UnknownBackend
from adapters.image import ImageBlocked, get_image
from adapters.image.gemini import DEFAULT_MODEL, GeminiError, GeminiImage, aspect_ratio

FIX = ME_DIR / "fixtures" / "gemini"
KEY = "gm-test-key-not-real"
FINAL, THOUGHT = (20, 120, 220), (250, 10, 10)

spec = importlib.util.spec_from_file_location("render_creatives_for_gemini", ME_DIR / "scripts" / "render_creatives.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)
PROMPT = rc.image_prompt("a founder at a tidy desk, morning light", "close crop")


def picture(size, colour, fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format=fmt)
    return buf.getvalue()


def exchange(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text())


def respond(name: str, *, size=(1024, 1024), fmt="PNG", mime="image/png") -> httpx.Response:
    """The fixture exchange with the image placeholders replaced by bytes generated here."""
    ex = exchange(name)
    for cand in ex["body"].get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            inline = part.get("inlineData")
            if inline and inline["data"] == "<PNG_BASE64>":
                inline.update(mimeType=mime, data=base64.b64encode(picture(size, FINAL, fmt)).decode())
            elif inline and inline["data"] == "<THOUGHT_PNG_BASE64>":
                inline["data"] = base64.b64encode(picture(size, THOUGHT)).decode()
    return httpx.Response(ex["status"], json=ex["body"], headers=ex.get("headers"))


class Google:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return answer(request) if callable(answer) else answer


def gen(google: Google, sleeps: list[float] | None = None, model: str = DEFAULT_MODEL) -> GeminiImage:
    return GeminiImage(KEY, model_id=model, transport=httpx.MockTransport(google),
                       sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_every_fixture_declares_its_assumed_shape_and_source():
    for f in sorted(FIX.glob("*.json")):
        shape = json.loads(f.read_text())["_shape"]
        assert shape.startswith("ASSUMED SHAPE from https://ai.google.dev/"), f
        assert "read 2026-10-28" in shape and "replace with a recorded response at go-live" in shape, f
    assert not [p for p in FIX.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]


def test_generate_sends_the_prompt_verbatim_and_returns_exactly_the_size_as_png():
    google = Google(respond("generate-content"))
    png = gen(google).generate(PROMPT, size=(1080, 1080))
    (req,) = google.requests
    assert req.method == "POST"
    assert str(req.url) == f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_MODEL}:generateContent"
    assert req.headers["x-goog-api-key"] == KEY and KEY not in str(req.url), "the key travels in a header, never the URL"
    body = json.loads(req.content)
    assert body["contents"] == [{"role": "user", "parts": [{"text": PROMPT}]}]
    assert body["contents"][0]["parts"][0]["text"].endswith(rc.NO_TEXT_INSTRUCTION), "FR-24: the no-text instruction is kept"
    config = body["generationConfig"]
    assert "IMAGE" in config["responseModalities"] and config["imageConfig"] == {"aspectRatio": "1:1"}
    img = Image.open(io.BytesIO(png))
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and img.format == "PNG" and img.size == (1080, 1080)
    assert img.convert("RGB").getpixel((540, 540)) == FINAL, "the final image, not the interim `thought` one"


def test_other_sizes_ask_for_the_nearest_ratio_and_are_cropped_to_exact_size():
    google = Google(respond("generate-content", size=(1344, 768), fmt="JPEG", mime="image/jpeg"))
    png = gen(google).generate(PROMPT, size=(1200, 628))
    assert json.loads(google.requests[0].content)["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9"
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG" and img.size == (1200, 628)
    assert aspect_ratio((1080, 1350)) == "4:5" and aspect_ratio((1080, 1920)) == "9:16" and aspect_ratio((1080, 1080)) == "1:1"


def test_a_blocked_prompt_is_image_blocked_with_the_reason():
    with pytest.raises(ImageBlocked) as exc:
        gen(Google(respond("blocked-prompt"))).generate(PROMPT)
    assert exc.value.reason == "SAFETY" and exc.value.stage == "prompt" and "SAFETY" in str(exc.value)


def test_a_blocked_image_is_image_blocked_with_the_finish_reason():
    with pytest.raises(ImageBlocked) as exc:
        gen(Google(respond("blocked-image"))).generate(PROMPT)
    assert exc.value.reason == "IMAGE_SAFETY" and exc.value.stage == "output"


def test_a_text_only_answer_is_image_blocked_and_carries_the_models_words():
    with pytest.raises(ImageBlocked) as exc:
        gen(Google(respond("text-only"))).generate(PROMPT)
    assert exc.value.reason == "NO_IMAGE" and "can't generate" in str(exc.value)


def test_an_invalid_key_names_the_variable_never_the_value():
    with pytest.raises(GeminiError) as exc:
        gen(Google(respond("error-api-key-invalid"))).generate(PROMPT)
    assert "GEMINI_API_KEY" in str(exc.value) and KEY not in str(exc.value)
    assert not isinstance(exc.value, ImageBlocked), "a bad key is a crash, not a failed attempt"


def test_a_bad_request_carries_googles_message():
    bad = httpx.Response(400, json={"error": {"code": 400, "message": "Unsupported aspect ratio", "status": "INVALID_ARGUMENT"}})
    with pytest.raises(GeminiError, match="Unsupported aspect ratio"):
        gen(Google(bad)).generate(PROMPT)


def test_429_and_503_are_retried_with_backoff():
    sleeps: list[float] = []
    google = Google(httpx.Response(429, headers={"retry-after": "3"}), httpx.Response(503), respond("generate-content"))
    png = gen(google, sleeps).generate(PROMPT)
    assert len(google.requests) == 3 and sleeps[0] == 3.0 and len(sleeps) == 2 and png[:8] == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(GeminiError, match="503"):
        gen(Google(httpx.Response(503)), []).generate(PROMPT)


def test_image_model_comes_from_env_with_a_documented_default(monkeypatch):
    monkeypatch.setenv("IMAGE_BACKEND", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(MissingEnvVar, match="GEMINI_API_KEY"):
        get_image()
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.delenv("IMAGE_MODEL", raising=False)
    assert get_image().model_id == DEFAULT_MODEL == "gemini-nano-banana-2.1"
    monkeypatch.setenv("IMAGE_MODEL", "gemini-3-pro-image")
    assert get_image().model_id == "gemini-3-pro-image"
    monkeypatch.setenv("IMAGE_MODEL", "../../v1/files")
    with pytest.raises(UnknownBackend, match="IMAGE_MODEL"):
        get_image()


def test_model_id_lands_in_the_request_path():
    google = Google(respond("generate-content"))
    gen(google, model="gemini-3-pro-image").generate(PROMPT)
    assert google.requests[0].url.path == "/v1beta/models/gemini-3-pro-image:generateContent"


# ---------- reference photos (Circadian: Jacob's method, real photos as ground truth) ----------

def test_reference_photos_go_first_as_inline_images_then_the_prompt_text():
    google = Google(respond("generate-content"))
    scene, hulls = picture((64, 48), (200, 180, 160), "JPEG"), picture((32, 32), (90, 60, 30), "PNG")
    gen(google).generate(PROMPT, size=(1080, 1080), references=[scene, hulls])
    parts = json.loads(google.requests[0].content)["contents"][0]["parts"]
    assert [list(p) for p in parts] == [["inline_data"], ["inline_data"], ["text"]]
    assert parts[0]["inline_data"] == {"mime_type": "image/jpeg", "data": base64.b64encode(scene).decode()}
    assert parts[1]["inline_data"] == {"mime_type": "image/png", "data": base64.b64encode(hulls).decode()}
    assert parts[2]["text"] == PROMPT and parts[2]["text"].endswith(rc.NO_TEXT_INSTRUCTION), "the instruction still comes last"


def test_a_reference_that_is_not_png_or_jpeg_or_too_many_is_refused_before_any_call():
    google = Google(respond("generate-content"))
    with pytest.raises(ValueError, match="PNG nor JPEG"):
        gen(google).generate(PROMPT, references=[b"GIF89a not a photo"])
    with pytest.raises(ValueError, match="at most 6"):
        gen(google).generate(PROMPT, references=[picture((8, 8), FINAL)] * 7)
    assert google.requests == []


def test_the_placeholder_accepts_and_ignores_references():
    from adapters.image.placeholder import PlaceholderImage
    png = PlaceholderImage().generate(PROMPT, size=(64, 64), references=[picture((8, 8), FINAL)])
    assert Image.open(io.BytesIO(png)).size == (64, 64)
