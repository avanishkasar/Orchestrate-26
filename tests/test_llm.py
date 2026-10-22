from __future__ import annotations

import time
from pathlib import Path

import pytest
from pydantic import BaseModel

from okit.llm.cache import DiskCache, cache_key
from okit.llm.client import StructuredOutputError
from okit.llm.ledger import Price, compute_cost, read_ledger
from okit.llm.providers import TransientProviderError
from okit.llm.ratelimit import RateLimiter
from okit.types import LLMResponse, Message, ToolCall, Usage


class Verdict(BaseModel):
    label: str
    confidence: float


def _resp(text: str = "", calls: list[ToolCall] | None = None) -> LLMResponse:
    return LLMResponse(
        text=text,
        tool_calls=calls or [],
        usage=Usage(input_tokens=100, output_tokens=10),
        model="m",
    )


def test_cache_key_is_order_independent() -> None:
    a = cache_key(model="m", prompt_version="v1", schema_version="s", payload={"a": 1, "b": 2})
    b = cache_key(model="m", prompt_version="v1", schema_version="s", payload={"b": 2, "a": 1})
    c = cache_key(model="m", prompt_version="v2", schema_version="s", payload={"a": 1, "b": 2})
    assert a == b != c


def test_disk_cache_roundtrip_and_torn_file(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    cache.set("ab" * 32, {"x": 1})
    assert cache.get("ab" * 32) == {"x": 1}
    torn = tmp_path / "cd" / f"{'cd' * 32}.json"
    torn.parent.mkdir()
    torn.write_text("{", encoding="utf-8")
    assert cache.get("cd" * 32) is None
    assert not torn.exists()


def test_compute_cost_uses_cached_rate() -> None:
    price = Price(input=2.0, output=8.0, cached_input=0.5)
    cost = compute_cost(
        Usage(input_tokens=1_000_000, output_tokens=0, cached_input_tokens=500_000), price
    )
    assert cost == pytest.approx(1.0 + 0.25)
    assert compute_cost(Usage(input_tokens=1), None) is None


async def test_retry_then_success_records_failures(make_client, tmp_path: Path) -> None:
    client, _ = make_client([TransientProviderError("429"), _resp("ok")])
    out = await client.generate(model="m", messages=[Message.user("hi")])
    assert out.text == "ok"
    recs = read_ledger(tmp_path / "usage.jsonl")
    assert [r.ok for r in recs] == [False, True]
    assert recs[1].cost_usd == pytest.approx((100 * 1.0 + 10 * 2.0) / 1e6)


async def test_retries_exhausted_raises(make_client) -> None:
    client, _ = make_client([TransientProviderError("x")] * 5)
    with pytest.raises(TransientProviderError, match="after 5 attempts"):
        await client.generate(model="m", messages=[Message.user("hi")])


async def test_cache_hit_skips_provider(make_client, tmp_path: Path) -> None:
    client, prov = make_client([_resp("first")], cache=True)
    a = await client.generate(model="m", messages=[Message.user("hi")])
    b = await client.generate(model="m", messages=[Message.user("hi")])
    assert a.text == b.text == "first"
    assert len(prov.calls) == 1
    recs = read_ledger(tmp_path / "usage.jsonl")
    assert [r.cache_hit for r in recs] == [False, True]
    assert recs[1].cost_usd == 0.0


async def test_structured_repairs_invalid_output(make_client) -> None:
    bad = ToolCall(id="1", name="submit", arguments={"label": "x"})
    good = ToolCall(id="2", name="submit", arguments={"label": "x", "confidence": 0.8})
    client, prov = make_client([_resp(calls=[bad]), _resp(calls=[good])])
    v = await client.structured(Verdict, model="m", messages=[Message.user("classify")])
    assert v == Verdict(label="x", confidence=0.8)
    repair_msgs = prov.calls[1]["messages"]
    assert repair_msgs[-1].tool_results[0].is_error  # type: ignore[index,union-attr]


async def test_structured_gives_up(make_client) -> None:
    client, _ = make_client([_resp("no tool")] * 3)
    with pytest.raises(StructuredOutputError):
        await client.structured(Verdict, model="m", messages=[Message.user("x")], repair_attempts=2)


async def test_rate_limiter_blocks_when_tpm_exhausted() -> None:
    lim = RateLimiter(tpm=600)  # 10 tokens/s
    await lim.acquire(600)
    start = time.monotonic()
    await lim.acquire(3)
    assert 0.2 <= time.monotonic() - start < 1.0
