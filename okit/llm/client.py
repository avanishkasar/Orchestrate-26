"""LLMClient: one entry point that adds caching, throttling, retries and the usage
ledger on top of any Provider.

Structured output uses a forced single tool call whose input schema is the
Pydantic model's JSON schema. It works the same on OpenAI and Anthropic, and a
validation failure is sent back to the model as a tool error for a bounded
number of repair attempts.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from okit.llm.cache import DiskCache, cache_key
from okit.llm.ledger import Ledger
from okit.llm.providers import Provider, TransientProviderError
from okit.llm.ratelimit import RateLimiter
from okit.types import ImagePart, LLMResponse, Message, TextPart, ToolResult, ToolSpec, Usage

T = TypeVar("T", bound=BaseModel)

# Rough estimate used only to pre-charge the TPM bucket; settle() corrects it.
_CHARS_PER_TOKEN = 4
_TOKENS_PER_IMAGE = 1_000


class StructuredOutputError(Exception):
    """The model never produced output that validated against the schema."""


def estimate_tokens(system: str | None, messages: list[Message], max_tokens: int) -> int:
    chars = len(system or "")
    images = 0
    for m in messages:
        for p in m.content:
            if isinstance(p, TextPart):
                chars += len(p.text)
            elif isinstance(p, ImagePart):
                images += 1
        chars += sum(len(r.content) for r in m.tool_results)
    return chars // _CHARS_PER_TOKEN + images * _TOKENS_PER_IMAGE + max_tokens


class LLMClient:
    def __init__(
        self,
        provider: Provider,
        *,
        ledger: Ledger,
        cache: DiskCache | None = None,
        limiter: RateLimiter | None = None,
        max_attempts: int = 5,
        base_delay_s: float = 1.0,
        max_delay_s: float = 30.0,
        timeout_s: float = 120.0,
    ) -> None:
        self.provider = provider
        self.ledger = ledger
        self.cache = cache
        self.limiter = limiter or RateLimiter()
        self.max_attempts = max_attempts
        self.base_delay_s = base_delay_s
        self.max_delay_s = max_delay_s
        self.timeout_s = timeout_s

    async def generate(
        self,
        *,
        model: str,
        messages: list[Message],
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        tool_choice: str | None = None,
        max_tokens: int = 2_048,
        temperature: float | None = None,
        purpose: str = "generate",
        row_id: str | None = None,
        prompt_version: str = "v1",
        use_cache: bool = True,
    ) -> LLMResponse:
        key: str | None = None
        if self.cache is not None and use_cache:
            key = cache_key(
                model=model,
                prompt_version=prompt_version,
                schema_version=self.provider.name,
                payload={
                    "system": system,
                    "messages": [m.model_dump() for m in messages],
                    "tools": [t.model_dump() for t in tools or []],
                    "tool_choice": tool_choice,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            hit = self.cache.get(key)
            if hit is not None:
                resp = LLMResponse.model_validate(hit)
                await self.ledger.record(
                    provider=self.provider.name,
                    model=model,
                    purpose=purpose,
                    row_id=row_id,
                    usage=resp.usage,
                    latency_ms=0.0,
                    cache_hit=True,
                    ok=True,
                )
                return resp

        estimate = estimate_tokens(system, messages, max_tokens)
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            await self.limiter.acquire(estimate)
            started = time.perf_counter()
            try:
                resp = await self.provider.generate(
                    model=model,
                    system=system,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout_s=self.timeout_s,
                )
            except TransientProviderError as exc:
                last_error = exc
                self.limiter.settle(estimate, 0)
                await self.ledger.record(
                    provider=self.provider.name,
                    model=model,
                    purpose=purpose,
                    row_id=row_id,
                    usage=Usage(),
                    latency_ms=(time.perf_counter() - started) * 1e3,
                    cache_hit=False,
                    ok=False,
                    error=f"attempt {attempt}: {exc}"[:500],
                )
                if attempt == self.max_attempts:
                    break
                # Full-jitter exponential backoff avoids synchronized retries across workers.
                cap = min(self.max_delay_s, self.base_delay_s * 2 ** (attempt - 1))
                await asyncio.sleep(random.uniform(0, cap))
                continue

            latency_ms = (time.perf_counter() - started) * 1e3
            self.limiter.settle(estimate, resp.usage.input_tokens + resp.usage.output_tokens)
            await self.ledger.record(
                provider=self.provider.name,
                model=resp.model or model,
                purpose=purpose,
                row_id=row_id,
                usage=resp.usage,
                latency_ms=latency_ms,
                cache_hit=False,
                ok=True,
            )
            if key is not None and self.cache is not None:
                self.cache.set(key, resp.model_dump())
            return resp

        raise TransientProviderError(
            f"{self.provider.name}/{model} failed after {self.max_attempts} attempts: {last_error}"
        )

    async def structured(
        self,
        schema: type[T],
        *,
        model: str,
        messages: list[Message],
        system: str | None = None,
        max_tokens: int = 2_048,
        temperature: float | None = None,
        purpose: str = "structured",
        row_id: str | None = None,
        prompt_version: str = "v1",
        repair_attempts: int = 2,
        tool_name: str = "submit",
        tool_description: str = "Submit the final structured answer. Call exactly once.",
    ) -> T:
        tool = ToolSpec(
            name=tool_name, description=tool_description, parameters=schema.model_json_schema()
        )
        convo = list(messages)
        errors: list[str] = []
        for attempt in range(repair_attempts + 1):
            resp = await self.generate(
                model=model,
                messages=convo,
                system=system,
                tools=[tool],
                tool_choice=tool_name,
                max_tokens=max_tokens,
                temperature=temperature,
                purpose=purpose if attempt == 0 else f"{purpose}:repair",
                row_id=row_id,
                prompt_version=prompt_version,
            )
            call = next((c for c in resp.tool_calls if c.name == tool_name), None)
            if call is None:
                errors.append(f"no {tool_name} call (stop_reason={resp.stop_reason})")
                convo = [*convo, Message.user(f"You must call the `{tool_name}` tool.")]
                continue
            try:
                return schema.model_validate(call.arguments)
            except ValidationError as exc:
                errors.append(str(exc))
                convo = [
                    *convo,
                    Message(role="assistant", tool_calls=[call]),
                    Message(
                        role="tool",
                        tool_results=[
                            ToolResult(
                                tool_call_id=call.id,
                                content=f"Schema validation failed, fix and resubmit:\n{exc}",
                                is_error=True,
                            )
                        ],
                    ),
                ]
        raise StructuredOutputError(
            f"{schema.__name__} invalid after {repair_attempts + 1} tries: {errors[-1]}"
        )
