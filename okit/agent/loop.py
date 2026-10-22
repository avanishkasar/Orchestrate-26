"""Bounded single-agent tool loop with a deterministic fallback.

The model must finish by calling the `submit` tool with arguments matching the
result schema. The loop stops and calls `fallback()` when any of these happen:
step cap, tool-call cap, token or USD budget exceeded, provider failure, or
repeated invalid submissions. The returned AgentResult says which path produced
the answer, so evaluation can compare agent vs fallback per row.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from okit.llm.client import LLMClient
from okit.llm.ledger import compute_cost
from okit.llm.providers import TransientProviderError
from okit.types import Message, ToolCall, ToolResult, ToolSpec, Usage

T = TypeVar("T", bound=BaseModel)
A = TypeVar("A", bound=BaseModel)

StopReason = Literal[
    "submitted", "max_steps", "max_tool_calls", "budget", "provider_error", "invalid_submissions"
]


@dataclass(frozen=True)
class Tool(Generic[A]):
    name: str
    description: str
    args_model: type[A]
    fn: Callable[[A], Any] | Callable[[A], Awaitable[Any]]

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.args_model.model_json_schema(),
        )

    async def __call__(self, raw_args: dict[str, Any]) -> Any:
        args = self.args_model.model_validate(raw_args)
        out = self.fn(args)
        return await out if inspect.isawaitable(out) else out


@dataclass
class AgentConfig:
    model: str
    system: str
    max_steps: int = 8
    max_tool_calls: int = 12
    max_tokens_per_step: int = 1_500
    budget_tokens: int | None = 60_000
    budget_usd: float | None = None
    max_invalid_submissions: int = 2
    submit_tool_name: str = "submit"
    submit_description: str = "Submit the final decision. Call exactly once, when you are done."
    max_tool_result_chars: int = 6_000
    prompt_version: str = "agent-v1"


@dataclass
class TraceStep:
    step: int
    tool: str
    arguments: dict[str, Any]
    result_preview: str
    is_error: bool


@dataclass
class AgentResult(Generic[T]):
    output: T
    source: Literal["agent", "fallback"]
    stop_reason: StopReason
    steps: list[TraceStep] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = 0.0

    def trace_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "stop_reason": self.stop_reason,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "steps": [s.__dict__ for s in self.steps],
            "output": self.output.model_dump(mode="json"),
        }


def _serialise(value: Any, limit: int) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return (
        text if len(text) <= limit else text[:limit] + f"... [truncated {len(text) - limit} chars]"
    )


async def run_agent(
    client: LLMClient,
    *,
    config: AgentConfig,
    tools: list[Tool[Any]],
    result_schema: type[T],
    messages: list[Message],
    fallback: Callable[[], Awaitable[T]],
    validate: Callable[[T], list[str]] | None = None,
    row_id: str | None = None,
    trace_dir: str | Path | None = None,
) -> AgentResult[T]:
    """`validate` returns a list of problems (empty = accept). Problems are sent back
    to the model as a tool error so it can correct itself within the step budget."""
    by_name = {t.name: t for t in tools}
    if config.submit_tool_name in by_name:
        raise ValueError(f"tool name {config.submit_tool_name!r} is reserved for submission")
    submit_spec = ToolSpec(
        name=config.submit_tool_name,
        description=config.submit_description,
        parameters=result_schema.model_json_schema(),
    )
    specs = [t.spec for t in tools] + [submit_spec]
    price = client.ledger.price_for(config.model)

    convo = list(messages)
    steps: list[TraceStep] = []
    in_tok = out_tok = tool_calls = invalid = 0
    stop: StopReason = "max_steps"
    submitted: T | None = None

    def cost() -> float | None:
        return compute_cost(Usage(input_tokens=in_tok, output_tokens=out_tok), price)

    for step in range(1, config.max_steps + 1):
        if config.budget_tokens is not None and in_tok + out_tok >= config.budget_tokens:
            stop = "budget"
            break
        spent = cost()
        if config.budget_usd is not None and spent is not None and spent >= config.budget_usd:
            stop = "budget"
            break
        try:
            resp = await client.generate(
                model=config.model,
                system=config.system,
                messages=convo,
                tools=specs,
                tool_choice="required",
                max_tokens=config.max_tokens_per_step,
                purpose="agent",
                row_id=row_id,
                prompt_version=config.prompt_version,
            )
        except TransientProviderError:
            stop = "provider_error"
            break
        in_tok += resp.usage.input_tokens
        out_tok += resp.usage.output_tokens

        if not resp.tool_calls:
            convo.append(Message.user(f"Call a tool, or `{config.submit_tool_name}` to finish."))
            continue

        convo.append(Message(role="assistant", tool_calls=resp.tool_calls))
        results: list[ToolResult] = []
        for call in resp.tool_calls:
            tool_calls += 1
            result = await _execute(call, by_name, config, result_schema, validate)
            if not isinstance(result, ToolResult):
                submitted = result
                results.append(ToolResult(tool_call_id=call.id, content="accepted"))
                steps.append(TraceStep(step, call.name, call.arguments, "accepted", False))
                continue
            if call.name == config.submit_tool_name:
                invalid += 1
            results.append(result)
            steps.append(
                TraceStep(step, call.name, call.arguments, result.content[:300], result.is_error)
            )
        convo.append(Message(role="tool", tool_results=results))

        if submitted is not None:
            stop = "submitted"
            break
        if invalid > config.max_invalid_submissions:
            stop = "invalid_submissions"
            break
        if tool_calls >= config.max_tool_calls:
            stop = "max_tool_calls"
            break

    if submitted is not None:
        final = AgentResult(submitted, "agent", stop, steps, in_tok, out_tok, cost())
    else:
        final = AgentResult(await fallback(), "fallback", stop, steps, in_tok, out_tok, cost())

    if trace_dir is not None and row_id is not None:
        d = Path(trace_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{row_id}.json").write_text(
            json.dumps(final.trace_json(), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return final


async def _execute(
    call: ToolCall,
    by_name: dict[str, Tool[Any]],
    config: AgentConfig,
    result_schema: type[T],
    validate: Callable[[T], list[str]] | None,
) -> ToolResult | T:
    if call.name == config.submit_tool_name:
        try:
            out = result_schema.model_validate(call.arguments)
        except ValidationError as exc:
            return ToolResult(
                tool_call_id=call.id, content=f"Invalid submission:\n{exc}", is_error=True
            )
        problems = validate(out) if validate else []
        if problems:
            body = "Submission rejected by validator:\n- " + "\n- ".join(problems)
            return ToolResult(tool_call_id=call.id, content=body, is_error=True)
        return out

    tool = by_name.get(call.name)
    if tool is None:
        names = ", ".join([*by_name, config.submit_tool_name])
        return ToolResult(
            tool_call_id=call.id,
            content=f"Unknown tool {call.name!r}. Available: {names}",
            is_error=True,
        )
    try:
        value = await tool(call.arguments)
    except ValidationError as exc:
        return ToolResult(tool_call_id=call.id, content=f"Bad arguments:\n{exc}", is_error=True)
    except Exception as exc:
        # Tool bugs are reported to the model, not raised: it can try another route.
        return ToolResult(
            tool_call_id=call.id, content=f"Tool error: {type(exc).__name__}: {exc}", is_error=True
        )
    return ToolResult(tool_call_id=call.id, content=_serialise(value, config.max_tool_result_chars))
