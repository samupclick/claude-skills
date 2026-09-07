"""Placeholder images: solid colour from the prompt hash plus a small hash label. Same prompt, same bytes."""
from __future__ import annotations

import hashlib
import io

from PIL import Image, ImageDraw


def render_placeholder(label: str, *, size: tuple[int, int] = (1080, 1080)) -> bytes:
    digest = hashlib.sha256(label.encode()).hexdigest()
    colour = tuple(int(digest[i:i + 2], 16) for i in (0, 2, 4))
    img = Image.new("RGB", size, colour)
    draw = ImageDraw.Draw(img)
    text = digest[:12]
    ink = (255, 255, 255) if sum(colour) < 384 else (0, 0, 0)
    box = draw.textbbox((0, 0), text)
    draw.text(((size[0] - box[2]) / 2, (size[1] - box[3]) / 2), text, fill=ink)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class PlaceholderImage:
    def generate(self, prompt: str, *, size: tuple[int, int] = (1080, 1080)) -> bytes:
        return render_placeholder(prompt, size=size)
