"""Claude backend via the Anthropic SDK; structured output enforced with output_config.format."""
from __future__ import annotations

import base64
import json
from typing import Any

from adapters.model import ModelOutputInvalid, ModelRefused, ModelResult, build_user, image_media_type, validate


class ClaudeModel:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.last_prompt: dict[str, str] = {}
        self._client: Any = None

    def _client_or_create(self):
        if self._client is None:
            import anthropic  # the only vendor import for model calls (FR-49)

            self._client = anthropic.Anthropic()
        return self._client

    def generate_json(self, *, task, system, instructions, untrusted, schema, max_tokens=4096, images=None):
        user = build_user(instructions, untrusted)
        self.last_prompt = {"system": system, "user": user}
        content: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": image_media_type(img),
                                         "data": base64.b64encode(img).decode("ascii")}}
            for img in images or []
        ]
        content.append({"type": "text", "text": user})
        response = self._client_or_create().messages.create(
            model=self.model_id,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        if response.stop_reason == "refusal":
            raise ModelRefused(f"{task}: model refused ({getattr(response, 'stop_details', None)})")
        if response.stop_reason == "max_tokens":
            raise ModelOutputInvalid(f"{task}: output truncated at max_tokens={max_tokens}")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ModelOutputInvalid(f"{task}: no text block in response (stop_reason={response.stop_reason})")
        try:
            output = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ModelOutputInvalid(f"{task}: model output is not JSON: {exc}") from exc
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return ModelResult(output=validate(task, output, schema), tokens_used=tokens, backend="claude")
