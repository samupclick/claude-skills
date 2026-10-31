"""Gemini image generation (IMAGE_BACKEND=gemini): FR-24, FR-25; CRUCIBLE §4 Friday item 7.

`generate(prompt, size)` sends the producer's prompt verbatim (its no-text instruction included) to
`POST {API_BASE}/models/<IMAGE_MODEL>:generateContent` with the key in the `x-goog-api-key` header (never the URL),
asks for the supported aspect ratio nearest to `size`, and returns a PNG of exactly `size` (centre crop and Lanczos
resize with Pillow). `IMAGE_MODEL` defaults to `DEFAULT_MODEL`, the GA model Google's Gemini API release notes name
as the current Nano Banana line (2026-10-06; read through search summaries on 2026-10-28, confirm with the go-live test
generation). No image for a content reason raises `ImageBlocked`; an HTTP failure raises `GeminiError`, naming
GEMINI_API_KEY for a key problem, never its value. The response shape is ASSUMED (fixtures/gemini/README.md):
`block_reason`, `image_part` and `answer_text` are the only functions that know it.

`references` (PNG or JPEG bytes, at most `MAX_REFERENCES`) go first as inline image parts, in order, then the prompt
text, which names them `[Image 1]`, `[Image 2]`... (Jacob Katz's Circadian method: real photos as ground truth for the
scene and the fill). The request part shape `inline_data` / `mime_type` is ASSUMED from Google's REST examples.
"""
from __future__ import annotations

import base64
import binascii
import io
import math
import os
import re
import time
from typing import Any, Callable, Sequence

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from adapters import backoff
from adapters.env import UnknownBackend, require
from adapters.image import MAX_REFERENCES, ImageBlocked
from adapters.model import image_media_type

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-nano-banana-2.1"
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9.\-]*$")
ASPECT_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")
DONE = frozenset({"STOP", "FINISH_REASON_UNSPECIFIED", ""})


class GeminiError(RuntimeError):
    """The Gemini API failed or refused the request. Messages never carry the key."""


# ---------- the response shape: ASSUMED until go-live step 5; a different real shape changes only these ----------

def block_reason(body: dict[str, Any]) -> tuple[str, str] | None:
    """(reason, stage) when the prompt was blocked or the output filtered; None when generation finished normally."""
    feedback = body.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        return str(feedback["blockReason"]), "prompt"
    candidates = body.get("candidates") or []
    if not candidates:
        return "NO_CANDIDATES", "output"
    reason = str(candidates[0].get("finishReason") or "")
    return None if reason in DONE else (reason, "output")


def _parts(body: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = body.get("candidates") or [{}]
    return list((candidates[0].get("content") or {}).get("parts") or [])


def image_part(body: dict[str, Any]) -> bytes | None:
    """The last inline image of the first candidate that is not an interim `thought` image."""
    inline = [p.get("inlineData") or p.get("inline_data") for p in _parts(body) if not p.get("thought")]
    inline = [i for i in inline if i and str(i.get("mimeType") or i.get("mime_type") or "image/").startswith("image/")]
    if not inline:
        return None
    try:
        return base64.b64decode(inline[-1].get("data") or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise GeminiError("Gemini returned image data that is not base64") from exc


def answer_text(body: dict[str, Any]) -> str:
    return " ".join(str(p["text"]).strip() for p in _parts(body) if p.get("text") and not p.get("thought"))[:200]


# ---------- the backend ----------

def aspect_ratio(size: tuple[int, int]) -> str:
    """The supported ratio nearest (in log space) to width/height."""
    target = math.log(size[0] / size[1])

    def distance(ratio: str) -> float:
        w, h = ratio.split(":")
        return abs(math.log(int(w) / int(h)) - target)

    return min(ASPECT_RATIOS, key=distance)


def fit_png(data: bytes, size: tuple[int, int]) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            rgb = img.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise GeminiError("Gemini returned image bytes Pillow cannot read") from exc
    out = rgb if rgb.size == tuple(size) else ImageOps.fit(rgb, tuple(size), method=Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def reference_parts(references: Sequence[bytes]) -> list[dict[str, Any]]:
    """The reference photos as inline image parts, in order. Anything but PNG or JPEG, or more than MAX_REFERENCES,
    is refused before a request is made."""
    if len(references) > MAX_REFERENCES:
        raise ValueError(f"{len(references)} reference images; send at most {MAX_REFERENCES}")
    return [{"inline_data": {"mime_type": image_media_type(data), "data": base64.b64encode(data).decode()}}
            for data in references]


class GeminiImage:
    def __init__(self, api_key: str, *, model_id: str = DEFAULT_MODEL, transport: httpx.BaseTransport | None = None,
                 base_url: str = API_BASE, sleep: Callable[[float], None] = time.sleep, timeout: float = 180.0,
                 attempts: int = 3):
        if not MODEL_ID.match(model_id):
            raise UnknownBackend(f"IMAGE_MODEL={model_id!r} is not a model id (lower-case letters, digits, dots, dashes)")
        self.model_id = model_id
        self._key = api_key
        self._client = httpx.Client(base_url=base_url.rstrip("/") + "/", transport=transport, timeout=timeout,
                                    headers={"x-goog-api-key": api_key, "content-type": "application/json"})
        self._sleep, self._attempts = sleep, attempts
        self.calls = 0

    @classmethod
    def from_env(cls) -> "GeminiImage":
        key = require("producer", "GEMINI_API_KEY")["GEMINI_API_KEY"]
        return cls(key, model_id=os.environ.get("IMAGE_MODEL") or DEFAULT_MODEL)

    def generate(self, prompt: str, *, size: tuple[int, int] = (1080, 1080), references: Sequence[bytes] = ()) -> bytes:
        body = {
            "contents": [{"role": "user", "parts": [*reference_parts(references), {"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"aspectRatio": aspect_ratio(size)}},
        }

        def tick() -> None:
            self.calls += 1

        try:
            response = backoff.send(self._client, "POST", f"models/{self.model_id}:generateContent", json=body,
                                    attempts=self._attempts, sleep=self._sleep, on_attempt=tick)
        except httpx.TransportError as exc:
            raise GeminiError(f"Gemini unreachable: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise self._http_error(response)
        try:
            answer = response.json()
        except ValueError as exc:
            raise GeminiError("Gemini answered with something that is not JSON") from exc
        blocked = block_reason(answer)
        if blocked and blocked[1] == "prompt":
            raise ImageBlocked(blocked[0], stage="prompt", detail=answer_text(answer))
        data = image_part(answer)
        if data is None:
            reason, stage = blocked or ("NO_IMAGE", "output")
            raise ImageBlocked(reason, stage=stage, detail=answer_text(answer))
        return fit_png(data, size)

    def close(self) -> None:
        self._client.close()

    def _http_error(self, response: httpx.Response) -> GeminiError:
        try:
            error = (response.json() or {}).get("error") or {}
        except ValueError:
            error = {}
        message = str(error.get("message") or response.text or "")[:300].replace(self._key, "***")
        reasons = {str(d.get("reason")) for d in error.get("details") or [] if isinstance(d, dict)}
        if response.status_code in (401, 403) or "API_KEY_INVALID" in reasons:
            return GeminiError(f"Gemini refused the key (HTTP {response.status_code}: {message}); check GEMINI_API_KEY")
        return GeminiError(f"Gemini HTTP {response.status_code} {error.get('status') or ''}: {message}".strip())
