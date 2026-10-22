"""Thin adapters that translate okit's neutral types to each vendor SDK.

Adapters do no retries, caching or throttling: that lives in LLMClient so the
behaviour is identical across providers.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from okit.types import ImagePart, LLMResponse, Message, TextPart, ToolCall, ToolSpec, Usage


class TransientProviderError(Exception):
    """Retryable failure: rate limit, timeout, 5xx, dropped connection."""


class Provider(Protocol):
    name: str

    async def generate(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[Message],
        tools: list[ToolSpec] | None,
        tool_choice: str | None,
        max_tokens: int,
        temperature: float | None,
        timeout_s: float,
    ) -> LLMResponse: ...


def _require_env(var: str) -> str:
    value = os.environ.get(var)
    if not value:
        raise RuntimeError(f"{var} is not set; export it in your shell or .env")
    return value


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        import openai

        self._openai = openai
        self._client = openai.AsyncOpenAI(
            api_key=api_key or _require_env("OPENAI_API_KEY"),
            base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
            max_retries=0,
        )

    @staticmethod
    def _content(parts: list[TextPart | ImagePart]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in parts:
            if isinstance(p, TextPart):
                out.append({"type": "text", "text": p.text})
            else:
                url = f"data:{p.media_type};base64,{p.data_b64}"
                out.append({"type": "image_url", "image_url": {"url": url}})
        return out

    def _messages(self, system: str | None, messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
        for m in messages:
            if m.role == "tool":
                out.extend(
                    {"role": "tool", "tool_call_id": r.tool_call_id, "content": r.content}
                    for r in m.tool_results
                )
            elif m.role == "assistant":
                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": "".join(p.text for p in m.content if isinstance(p, TextPart))
                    or None,
                }
                if m.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                        }
                        for c in m.tool_calls
                    ]
                out.append(msg)
            else:
                out.append({"role": "user", "content": self._content(m.content)})
        return out

    async def generate(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[Message],
        tools: list[ToolSpec] | None,
        tool_choice: str | None,
        max_tokens: int,
        temperature: float | None,
        timeout_s: float,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._messages(system, messages),
            "max_completion_tokens": max_tokens,
            "timeout": timeout_s,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
            if tool_choice == "required":
                kwargs["tool_choice"] = "required"
            elif tool_choice:
                kwargs["tool_choice"] = {"type": "function", "function": {"name": tool_choice}}
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except (
            self._openai.RateLimitError,
            self._openai.APITimeoutError,
            self._openai.APIConnectionError,
            self._openai.InternalServerError,
        ) as exc:
            raise TransientProviderError(str(exc)) from exc

        choice = resp.choices[0]
        calls: list[ToolCall] = []
        for tc in choice.message.tool_calls or []:
            fn = getattr(tc, "function", None)
            if fn is None:
                continue
            try:
                args = json.loads(fn.arguments or "{}")
            except json.JSONDecodeError:
                args = {"__unparseable__": fn.arguments}
            calls.append(ToolCall(id=tc.id, name=fn.name, arguments=args))
        u = resp.usage
        cached = 0
        if u and u.prompt_tokens_details and u.prompt_tokens_details.cached_tokens:
            cached = u.prompt_tokens_details.cached_tokens
        return LLMResponse(
            text=choice.message.content or "",
            tool_calls=calls,
            usage=Usage(
                input_tokens=u.prompt_tokens if u else 0,
                output_tokens=u.completion_tokens if u else 0,
                cached_input_tokens=cached,
            ),
            stop_reason=choice.finish_reason or "",
            model=resp.model,
        )


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str | None = None) -> None:
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key or _require_env("ANTHROPIC_API_KEY"), max_retries=0
        )

    @staticmethod
    def _content(parts: list[TextPart | ImagePart]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in parts:
            if isinstance(p, TextPart):
                out.append({"type": "text", "text": p.text})
            else:
                out.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": p.media_type,
                            "data": p.data_b64,
                        },
                    }
                )
        return out

    def _messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "tool":
                out.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": r.tool_call_id,
                                "content": r.content,
                                "is_error": r.is_error,
                            }
                            for r in m.tool_results
                        ],
                    }
                )
            elif m.role == "assistant":
                blocks = self._content(m.content)
                blocks.extend(
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                    for c in m.tool_calls
                )
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": "user", "content": self._content(m.content)})
        return out

    async def generate(
        self,
        *,
        model: str,
        system: str | None,
        messages: list[Message],
        tools: list[ToolSpec] | None,
        tool_choice: str | None,
        max_tokens: int,
        temperature: float | None,
        timeout_s: float,
    ) -> LLMResponse:
        # Current Anthropic models reject sampling params; temperature is intentionally ignored.
        del temperature
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._messages(messages),
            "max_tokens": max_tokens,
            "timeout": timeout_s,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]
            if tool_choice == "required":
                kwargs["tool_choice"] = {"type": "any"}
            elif tool_choice:
                kwargs["tool_choice"] = {"type": "tool", "name": tool_choice}
        try:
            resp = await self._client.messages.create(**kwargs)
        except (
            self._anthropic.RateLimitError,
            self._anthropic.APITimeoutError,
            self._anthropic.APIConnectionError,
            self._anthropic.InternalServerError,
        ) as exc:
            raise TransientProviderError(str(exc)) from exc

        text: list[str] = []
        calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input)))
        return LLMResponse(
            text="".join(text),
            tool_calls=calls,
            usage=Usage(
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                cached_input_tokens=resp.usage.cache_read_input_tokens or 0,
            ),
            stop_reason=resp.stop_reason or "",
            model=resp.model,
        )


def make_provider(name: str) -> Provider:
    if name == "openai":
        return OpenAIProvider()
    if name == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"unknown provider {name!r}; expected 'openai' or 'anthropic'")
