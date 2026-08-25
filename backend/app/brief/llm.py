"""Injectable LLM client for brief prose. Fake for tests; Anthropic for prod."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class BriefLLMResponse:
    # section key -> {"text": str, "fact_ids": list[str]}
    sections: dict[str, dict]
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@runtime_checkable
class BriefLLMClient(Protocol):
    def compose(self, *, system: str, user: str, allowed_fact_ids: list[str]) -> BriefLLMResponse: ...


class FakeBriefLLM:
    """Scripted client. Provide ``responses`` (dicts of sections in order) or a
    ``handler(user, call_number) -> dict``."""

    def __init__(self, responses: list[dict] | None = None, *, model: str = "fake-brief-model",
                 handler: Callable[[str, int], dict] | None = None) -> None:
        self._responses = list(responses or [])
        self._handler = handler
        self._model = model
        self.calls: list[str] = []

    def compose(self, *, system: str, user: str, allowed_fact_ids: list[str]) -> BriefLLMResponse:
        self.calls.append(user)
        if self._handler is not None:
            sections = self._handler(user, len(self.calls))
        elif self._responses:
            sections = self._responses.pop(0)
        else:
            sections = {}
        return BriefLLMResponse(sections=sections, model=self._model, input_tokens=200, output_tokens=120)


class AnthropicBriefLLM:
    """Production client (Anthropic structured output). Lazy import."""

    def __init__(self, *, model: str = "claude-opus-5", client: Any | None = None,
                 max_tokens: int = 4000, effort: str = "low") -> None:
        self._model = model
        self._client = client
        self._max_tokens = max_tokens
        self._effort = effort

    def compose(self, *, system: str, user: str, allowed_fact_ids: list[str]) -> BriefLLMResponse:
        import json

        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        schema = {
            "type": "object", "additionalProperties": False,
            "properties": {
                "sections": {
                    "type": "object", "additionalProperties": {
                        "type": "object", "additionalProperties": False,
                        "properties": {
                            "text": {"type": "string"},
                            "fact_ids": {"type": "array", "items": {"type": "string", "enum": allowed_fact_ids}},
                        },
                        "required": ["text", "fact_ids"],
                    },
                }
            },
            "required": ["sections"],
        }
        resp = self._client.messages.create(
            model=self._model, max_tokens=self._max_tokens, system=system,
            messages=[{"role": "user", "content": user}], thinking={"type": "adaptive"},
            output_config={"effort": self._effort,
                           "format": {"type": "json_schema", "name": "sales_brief", "schema": schema}},
        )
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        data = json.loads(text)
        usage = getattr(resp, "usage", None)
        return BriefLLMResponse(
            sections=data.get("sections", {}), model=getattr(resp, "model", self._model),
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
        )
