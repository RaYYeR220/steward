"""LLM client port: the real Qwen Cloud client and a scripted fake for tests."""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Protocol

from steward.config import QwenSettings


class LLMError(Exception):
    """Raised when the LLM API is unusable (no key, or failed after retry)."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string exactly as the model produced it


@dataclass(frozen=True)
class ChatResponse:
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResponse: ...


class QwenClient:
    """OpenAI-compatible client for Qwen Cloud; one retry on any API error."""

    def __init__(self, settings: QwenSettings) -> None:
        if not settings.api_key:
            raise LLMError("QWEN_API_KEY is not configured")
        from openai import OpenAI  # lazy: tests never import the package

        self._client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
        self._model = settings.model

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResponse:
        from openai import (
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
        )

        transient = (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model, messages=messages, tools=tools
                )
                break
            except transient as exc:
                last_error = exc
                if attempt == 1:
                    time.sleep(1.0)
            except Exception as exc:  # permanent (auth, bad request): no retry
                raise LLMError(f"Qwen API error: {exc}") from exc
        else:
            raise LLMError(f"Qwen API failed after retry: {last_error}")
        message = resp.choices[0].message
        calls = tuple(
            ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments)
            for c in (message.tool_calls or [])
        )
        usage = resp.usage
        return ChatResponse(
            content=message.content,
            tool_calls=calls,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )


@dataclass
class FakeLLM:
    """Scripted LLM for tests: returns canned responses in order, records inputs.

    Uses an index cursor so ``scripted`` is never mutated and the instance can
    be inspected after the run.
    """

    scripted: list[ChatResponse]
    received: list[list[dict]] = field(default_factory=list)
    _pos: int = field(default=0, init=False)

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResponse:
        self.received.append(copy.deepcopy(messages))
        if self._pos >= len(self.scripted):
            raise AssertionError("FakeLLM script exhausted")
        response = self.scripted[self._pos]
        self._pos += 1
        return response
