"""Claude backend via the Anthropic SDK; structured output enforced with output_config.format.

On Claude Opus 5 / 5.5 thinking is always on (Opus 5.5 rejects `thinking: {type: "disabled"}` and `budget_tokens`
with a 400) and thinking tokens count against `max_tokens`. So the caller's `max_tokens` is the *answer* budget and
the request adds thinking headroom on top (`request_max_tokens`), kept at or below 20k so the call stays non-streaming
under the SDK's HTTP timeout. Depth is set with `output_config.effort` from MODEL_EFFORT (default "high"; Opus 5.5's
own default is "medium"). Refusals opt into the server-side fallback (`fallbacks="default"`, routed by refusal
category); the fallback model can refuse too, so `stop_reason == "refusal"` still raises. Not sent, because each
returns a 400 on Opus 5.5 or is unused here: `thinking`, `budget_tokens`, forced `tool_choice`, `temperature`,
`top_p`, `top_k`.
"""
from __future__ import annotations

import base64
import json
from typing import Any

from adapters.model import ModelOutputInvalid, ModelRefused, ModelResult, build_user, image_media_type, validate

EFFORTS = ("low", "medium", "high", "xhigh", "max")
FALLBACK_BETA = "server-side-fallback-2026-07-01"   # the header for the fallbacks="default" form (not -2026-06-01)
THINKING_HEADROOM = 12_000
MIN_REQUEST_TOKENS = 16_000
MAX_NON_STREAMING_TOKENS = 20_000


def request_max_tokens(answer_budget: int) -> int:
    """max_tokens to send: the answer budget plus thinking headroom, at least 16k, at most 20k (non-streaming), and
    never below the caller's own budget."""
    padded = min(max(answer_budget + THINKING_HEADROOM, MIN_REQUEST_TOKENS), MAX_NON_STREAMING_TOKENS)
    return max(answer_budget, padded)


class ClaudeModel:
    def __init__(self, model_id: str, effort: str = "high"):
        if effort not in EFFORTS:
            raise ValueError(f"MODEL_EFFORT={effort!r} is not one of {list(EFFORTS)}")
        self.model_id = model_id
        self.effort = effort
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
        requested = request_max_tokens(max_tokens)
        response = self._client_or_create().beta.messages.create(
            model=self.model_id,
            max_tokens=requested,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise ModelRefused(f"{task}: model refused ({getattr(response, 'stop_details', None)})")
        if response.stop_reason == "max_tokens":
            raise ModelOutputInvalid(f"{task}: output truncated at max_tokens={requested} "
                                     f"(answer budget {max_tokens} + thinking headroom)")
        # After a fallback, everything up to the last `fallback` block belongs to the model that declined.
        blocks = list(response.content)
        cut = max((i for i, b in enumerate(blocks) if b.type == "fallback"), default=-1)
        text = next((b.text for b in blocks[cut + 1:] if b.type == "text"), None)
        if text is None:
            raise ModelOutputInvalid(f"{task}: no text block in response (stop_reason={response.stop_reason})")
        try:
            output = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ModelOutputInvalid(f"{task}: model output is not JSON: {exc}") from exc
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return ModelResult(output=validate(task, output, schema), tokens_used=tokens, backend="claude",
                           model=getattr(response, "model", None) or self.model_id)
