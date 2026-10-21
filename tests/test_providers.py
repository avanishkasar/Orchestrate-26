from __future__ import annotations

from okit.llm.providers import AnthropicProvider, OpenAIProvider
from okit.types import ImagePart, Message, TextPart, ToolCall, ToolResult

CONVO = [
    Message(
        role="user",
        content=[TextPart(text="look"), ImagePart(media_type="image/jpeg", data_b64="AAA")],
    ),
    Message(role="assistant", tool_calls=[ToolCall(id="c1", name="zoom", arguments={"x": 1})]),
    Message(role="tool", tool_results=[ToolResult(tool_call_id="c1", content="ok", is_error=True)]),
]


def test_openai_translation() -> None:
    msgs = OpenAIProvider(api_key="test")._messages("sys", CONVO)
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool"]
    assert msgs[1]["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,AAA"
    assert msgs[2]["content"] is None
    assert msgs[2]["tool_calls"][0]["function"] == {"name": "zoom", "arguments": '{"x": 1}'}
    assert msgs[3] == {"role": "tool", "tool_call_id": "c1", "content": "ok"}


def test_anthropic_translation() -> None:
    msgs = AnthropicProvider(api_key="test")._messages(CONVO)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"][1]["source"] == {
        "type": "base64",
        "media_type": "image/jpeg",
        "data": "AAA",
    }
    assert msgs[1]["content"] == [
        {"type": "tool_use", "id": "c1", "name": "zoom", "input": {"x": 1}}
    ]
    assert msgs[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "c1",
        "content": "ok",
        "is_error": True,
    }
