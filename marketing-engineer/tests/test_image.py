import io

import pytest
from PIL import Image

from adapters.env import UnknownBackend
from adapters.image import get_image


def test_placeholder_is_deterministic_per_prompt(monkeypatch):
    monkeypatch.setenv("IMAGE_BACKEND", "placeholder")
    gen = get_image()
    a = gen.generate("desk photo, no text")
    assert a == gen.generate("desk photo, no text")
    assert a != gen.generate("desk photo, no text, blue")
    img = Image.open(io.BytesIO(a))
    assert img.size == (1080, 1080) and img.format == "PNG"
    assert gen.generate("x", size=(1200, 628)) != a


def test_unknown_backend_names_variable(monkeypatch):
    monkeypatch.setenv("IMAGE_BACKEND", "dalle")
    with pytest.raises(UnknownBackend, match="IMAGE_BACKEND"):
        get_image()
