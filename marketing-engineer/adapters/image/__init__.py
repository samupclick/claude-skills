"""Image generation: `generate(prompt, size) -> PNG bytes`. IMAGE_BACKEND=placeholder|gemini."""
from __future__ import annotations

from typing import Protocol

from adapters.env import choose_backend, not_built


class ImageGen(Protocol):
    def generate(self, prompt: str, *, size: tuple[int, int] = (1080, 1080)) -> bytes: ...


def get_image() -> ImageGen:
    from adapters.image.placeholder import PlaceholderImage

    return choose_backend("IMAGE_BACKEND", {
        "placeholder": PlaceholderImage,
        "gemini": not_built("IMAGE_BACKEND", "gemini", "T13"),
    })
