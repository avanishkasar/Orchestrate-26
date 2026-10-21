from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from okit.agent.loop import AgentConfig, Tool, run_agent
from okit.llm.providers import TransientProviderError
from okit.types import LLMResponse, Message, ToolCall, Usage


class Decision(BaseModel):
    action: str
    reason: str


class LookupArgs(BaseModel):
    key: str


def _r(*calls: ToolCall) -> LLMResponse:
    return LLMResponse(
        tool_calls=list(calls), usage=Usage(input_tokens=50, output_tokens=5), model="m"
    )


def _lookup_tool(seen: list[str]) -> Tool[LookupArgs]:
    def fn(a: LookupArgs) -> dict[str, str]:
        seen.append(a.key)
        if a.key == "boom":
            raise RuntimeError("db down")
        return {"policy": "mute scams"}

    return Tool("lookup", "Look up a policy by key.", LookupArgs, fn)


async def _fallback() -> Decision:
    return Decision(action="digest", reason="fallback")


async def test_agent_uses_tool_then_submits(make_client, tmp_path: Path) -> None:
    seen: list[str] = []
    client, _ = make_client(
        [
            _r(ToolCall(id="a", name="lookup", arguments={"key": "scam"})),
            _r(
                ToolCall(
                    id="b", name="submit", arguments={"action": "mute", "reason": "scam policy"}
                )
            ),
        ]
    )
    res = await run_agent(
        client,
        config=AgentConfig(model="m", system="s"),
        tools=[_lookup_tool(seen)],
        result_schema=Decision,
        messages=[Message.user("row")],
        fallback=_fallback,
        row_id="r1",
        trace_dir=tmp_path,
    )
    assert res.source == "agent" and res.stop_reason == "submitted"
    assert res.output.action == "mute"
    assert seen == ["scam"]
    assert (tmp_path / "r1.json").exists()
    assert res.input_tokens == 100


async def test_tool_errors_are_returned_not_raised(make_client) -> None:
    client, _ = make_client(
        [
            _r(ToolCall(id="a", name="lookup", arguments={"key": "boom"})),
            _r(ToolCall(id="b", name="nope", arguments={})),
            _r(ToolCall(id="c", name="submit", arguments={"action": "notify", "reason": "ok"})),
        ]
    )
    res = await run_agent(
        client,
        config=AgentConfig(model="m", system="s"),
        tools=[_lookup_tool([])],
        result_schema=Decision,
        messages=[Message.user("row")],
        fallback=_fallback,
    )
    assert res.source == "agent"
    assert [s.is_error for s in res.steps] == [True, True, False]
    assert "db down" in res.steps[0].result_preview


async def test_validator_rejection_then_fallback(make_client) -> None:
    sub = ToolCall(id="x", name="submit", arguments={"action": "notify", "reason": "r"})
    client, _ = make_client([_r(sub), _r(sub), _r(sub)])
    res = await run_agent(
        client,
        config=AgentConfig(model="m", system="s", max_invalid_submissions=2),
        tools=[],
        result_schema=Decision,
        messages=[Message.user("row")],
        fallback=_fallback,
        validate=lambda d: ["high-risk row cannot be notify"] if d.action == "notify" else [],
    )
    assert res.source == "fallback" and res.stop_reason == "invalid_submissions"
    assert res.output.reason == "fallback"


async def test_step_cap_and_provider_error_fall_back(make_client) -> None:
    client, _ = make_client(
        [_r(ToolCall(id=str(i), name="lookup", arguments={"key": "k"})) for i in range(3)]
    )
    res = await run_agent(
        client,
        config=AgentConfig(model="m", system="s", max_steps=3),
        tools=[_lookup_tool([])],
        result_schema=Decision,
        messages=[Message.user("row")],
        fallback=_fallback,
    )
    assert (res.source, res.stop_reason) == ("fallback", "max_steps")

    client, _ = make_client([TransientProviderError("x")] * 5)
    res = await run_agent(
        client,
        config=AgentConfig(model="m", system="s"),
        tools=[],
        result_schema=Decision,
        messages=[Message.user("row")],
        fallback=_fallback,
    )
    assert (res.source, res.stop_reason) == ("fallback", "provider_error")


async def test_token_budget(make_client) -> None:
    client, _ = make_client([_r(ToolCall(id="a", name="lookup", arguments={"key": "k"}))])
    res = await run_agent(
        client,
        config=AgentConfig(model="m", system="s", budget_tokens=40),
        tools=[_lookup_tool([])],
        result_schema=Decision,
        messages=[Message.user("row")],
        fallback=_fallback,
    )
    assert res.stop_reason == "budget"
