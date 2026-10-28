"""Image generation: `generate(prompt, size) -> PNG bytes` of exactly `size`. IMAGE_BACKEND=placeholder|gemini.

A live backend declares `model_id`; the producer records it as `creatives.image_model` (FR-21). gemini needs
`GEMINI_API_KEY` and takes the model from `IMAGE_MODEL` (default `adapters.image.gemini.DEFAULT_MODEL`). When the model
returns no image for a content reason (a blocked prompt, a filtered image, a text-only answer) the backend raises
`ImageBlocked`, which the producer counts as one failed attempt (FR-24), never a crashed batch.
"""
from __future__ import annotations

from typing import Protocol

from adapters.env import choose_backend


class ImageBlocked(RuntimeError):
    """No image this attempt for a content reason. `reason` is the vendor's code; `stage` is prompt or output."""

    def __init__(self, reason: str, *, stage: str = "output", detail: str = ""):
        self.reason, self.stage, self.detail = reason, stage, detail
        super().__init__(f"image model blocked the {stage}: {reason}" + (f" ({detail})" if detail else ""))


class ImageGen(Protocol):
    def generate(self, prompt: str, *, size: tuple[int, int] = (1080, 1080)) -> bytes: ...


def get_image() -> ImageGen:
    from adapters.image.gemini import GeminiImage
    from adapters.image.placeholder import PlaceholderImage

    return choose_backend("IMAGE_BACKEND", {
        "placeholder": PlaceholderImage,
        "gemini": GeminiImage.from_env,
    })
