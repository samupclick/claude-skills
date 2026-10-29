"""adapters/model/claude.py against a fake Anthropic client: the request it sends to Claude Opus 5.5 (thinking is always
on and counts against max_tokens, explicit effort, server-side refusal fallback, structured output) and how it reads the
response (truncation, refusal, fallback boundary, JSON and schema checks). FR-49, NFR-4."""
import json
from types import SimpleNamespace as NS

import pytest

from adapters.model import ModelOutputInvalid, ModelRefused, get_model
from adapters.model.claude import ClaudeModel, request_max_tokens

SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string"}}, "required": ["verdict"],
          "additionalProperties": False}
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16


def text(t):
    return NS(type="text", text=t)


def response(content, stop_reason="end_turn", model="claude-opus-5-5", stop_details=None, usage=(100, 40)):
    return NS(content=content, stop_reason=stop_reason, model=model, stop_details=stop_details,
              usage=NS(input_tokens=usage[0], output_tokens=usage[1]))


class FakeClient:
    """Only client.beta.messages.create exists: a call to client.messages.create would raise AttributeError."""

    def __init__(self, resp):
        self.calls = []
        self.beta = NS(messages=NS(create=self._create))
        self._resp = resp

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._resp


def run(resp, *, max_tokens=1500, effort="high", images=None):
    model = ClaudeModel(model_id="claude-opus-5-5", effort=effort)
    model._client = FakeClient(resp)
    result = model.generate_json(task="rubric", system="SYS", instructions="Score it.", untrusted="ad text",
                                 schema=SCHEMA, max_tokens=max_tokens, images=images)
    return model, result


def test_request_kwargs_for_opus_5_5():
    model, result = run(response([NS(type="thinking", thinking=""), text('{"verdict": "pass"}')]), images=[PNG])
    (kwargs,) = model._client.calls
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["max_tokens"] == 16000, "the caller's 1500 is the answer budget; thinking gets headroom on top"
    assert kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert kwargs["fallbacks"] == "default"
    assert kwargs["output_config"] == {"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}}
    assert kwargs["system"] == "SYS"
    (msg,) = kwargs["messages"]
    assert msg["role"] == "user"
    assert [b["type"] for b in msg["content"]] == ["image", "text"]
    assert msg["content"][0]["source"]["media_type"] == "image/png"
    for banned in ("thinking", "temperature", "top_p", "top_k", "tool_choice", "budget_tokens", "stream"):
        assert banned not in kwargs, f"{banned} returns a 400 on Opus 5.5 or is not used here"
    assert result.output == {"verdict": "pass"} and result.backend == "claude"
    assert result.tokens_used == 140 and result.model == "claude-opus-5-5"


@pytest.mark.parametrize("caller, sent", [(512, 16000), (800, 16000), (1500, 16000), (2048, 16000), (4096, 16096),
                                          (6000, 18000), (8000, 20000), (19000, 20000), (25000, 25000)])
def test_answer_budget_plus_thinking_headroom_stays_non_streaming(caller, sent):
    assert request_max_tokens(caller) == sent
    assert request_max_tokens(caller) >= caller, "never below the caller's own answer budget"


def test_truncation_at_max_tokens_is_invalid_output_naming_both_budgets():
    with pytest.raises(ModelOutputInvalid, match=r"rubric: output truncated at max_tokens=16000 \(answer budget 800"):
        run(response([NS(type="thinking", thinking="")], stop_reason="max_tokens"), max_tokens=800)


def test_refusal_raises_model_refused_even_after_the_fallback():
    details = NS(type="refusal", category="cyber", explanation=None)
    with pytest.raises(ModelRefused, match="rubric: model refused.*cyber"):
        run(response([NS(type="fallback", from_=NS(model="claude-opus-5-5"), to=NS(model="claude-opus-4-8"))],
                     stop_reason="refusal", model="claude-opus-4-8", stop_details=details))


def test_fallback_answer_is_read_after_the_last_fallback_block():
    content = [text('{"verdict": "declined partial"}'),
               NS(type="fallback", from_=NS(model="claude-opus-5-5"), to=NS(model="claude-opus-4-8")),
               NS(type="thinking", thinking=""), text('{"verdict": "fail"}')]
    _, result = run(response(content, model="claude-opus-4-8"))
    assert result.output == {"verdict": "fail"}
    assert result.model == "claude-opus-4-8", "the model that served the answer is recorded"


def test_non_json_and_schema_breaking_output_are_invalid():
    with pytest.raises(ModelOutputInvalid, match="not JSON"):
        run(response([text("verdict: pass")]))
    with pytest.raises(ModelOutputInvalid, match="failed schema"):
        run(response([text('{"verdict": 3}')]))
    with pytest.raises(ModelOutputInvalid, match="no text block"):
        run(response([NS(type="thinking", thinking="")]))


def test_effort_comes_from_model_effort_default_high(monkeypatch):
    monkeypatch.setenv("MODEL_BACKEND", "claude")
    monkeypatch.delenv("MODEL_ID", raising=False)
    monkeypatch.delenv("MODEL_EFFORT", raising=False)
    model = get_model()
    assert (model.model_id, model.effort) == ("claude-opus-5-5", "high")
    monkeypatch.setenv("MODEL_EFFORT", "xhigh")
    assert get_model().effort == "xhigh"
    monkeypatch.setenv("MODEL_EFFORT", "turbo")
    with pytest.raises(ValueError, match="MODEL_EFFORT='turbo'"):
        get_model()


def test_env_example_defaults_to_opus_5_5_and_names_model_effort():
    from adapters.env import ME_DIR
    lines = (ME_DIR / ".env.example").read_text().splitlines()
    assert "MODEL_ID=claude-opus-5-5" in lines
    assert any(line.lstrip("# ").startswith("MODEL_EFFORT=") for line in lines)
