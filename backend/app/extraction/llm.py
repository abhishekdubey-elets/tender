"""LLM client abstraction.

The service depends only on the :class:`LLMClient` protocol, so tests inject a
scripted :class:`FakeLLMClient` and production uses :class:`AnthropicLLMClient`.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class LLMError(Exception):
    """Transport/provider error (retryable)."""


@dataclass(slots=True)
class LLMResponse:
    data: dict           # parsed structured output
    model: str           # exact model id/version used
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_text: str | None = None


@runtime_checkable
class LLMClient(Protocol):
    def complete_structured(
        self, *, system: str, user: str, schema: dict, model: str | None = None
    ) -> LLMResponse: ...


class AnthropicLLMClient:
    """Production client using the Anthropic SDK with structured output.

    Determinism note: current Claude models do not accept ``temperature``; we
    pin the model, prompt version and a low effort setting for stability, and the
    service caches by input hash. ``anthropic`` is imported lazily so tests never
    require it.
    """

    def __init__(
        self,
        *,
        model: str = "claude-opus-5",
        client: Any | None = None,
        effort: str = "low",
        max_tokens: int = 8000,
    ) -> None:
        self._model = model
        self._client = client
        self._effort = effort
        self._max_tokens = max_tokens

    def _ensure_client(self) -> Any:
        if self._client is None:
            import anthropic  # lazy

            self._client = anthropic.Anthropic()
        return self._client

    def complete_structured(
        self, *, system: str, user: str, schema: dict, model: str | None = None
    ) -> LLMResponse:
        client = self._ensure_client()
        used_model = model or self._model
        try:
            resp = client.messages.create(
                model=used_model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={
                    "effort": self._effort,
                    "format": {
                        "type": "json_schema",
                        "name": "government_events",
                        "schema": schema,
                    },
                },
            )
        except Exception as exc:  # includes anthropic API errors
            raise LLMError(str(exc)) from exc

        text = "".join(
            getattr(block, "text", "") for block in resp.content if getattr(block, "type", None) == "text"
        )
        try:
            data = json.loads(text)
        except (ValueError, TypeError) as exc:
            raise LLMError(f"model did not return valid JSON: {exc}") from exc
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            data=data,
            model=getattr(resp, "model", used_model),
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            raw_text=text,
        )


class FakeLLMClient:
    """Scripted client for tests.

    Provide ``responses`` (dicts returned in order; an ``Exception`` instance is
    raised to simulate transport errors) or a ``handler(user, call_number)`` that
    returns a dict per call.
    """

    def __init__(
        self,
        responses: list[Any] | None = None,
        *,
        model: str = "fake-model-1",
        handler: Callable[[str, int], Any] | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._handler = handler
        self._model = model
        self.calls: list[dict] = []

    def complete_structured(
        self, *, system: str, user: str, schema: dict, model: str | None = None
    ) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "schema": schema})
        if self._handler is not None:
            data = self._handler(user, len(self.calls))
        elif self._responses:
            data = self._responses.pop(0)
        else:
            raise LLMError("no scripted response available")
        if isinstance(data, Exception):
            raise data
        return LLMResponse(
            data=data,
            model=model or self._model,
            input_tokens=100,
            output_tokens=50,
            raw_text=json.dumps(data),
        )
