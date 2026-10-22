from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from okit.llm.cache import DiskCache
from okit.llm.client import LLMClient
from okit.llm.ledger import Ledger, Price
from okit.types import LLMResponse


class FakeProvider:
    """Replays a scripted sequence of responses; records what it was sent."""

    name = "fake"

    def __init__(self, script: list[LLMResponse | Exception]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, object]] = []

    async def generate(self, **kwargs: object) -> LLMResponse:
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("FakeProvider script exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def make_client(tmp_path: Path) -> Callable[..., tuple[LLMClient, FakeProvider]]:
    def _make(
        script: list[LLMResponse | Exception], cache: bool = False
    ) -> tuple[LLMClient, FakeProvider]:
        prov = FakeProvider(script)
        ledger = Ledger(tmp_path / "usage.jsonl", {"m": Price(input=1.0, output=2.0)})
        client = LLMClient(
            prov,
            ledger=ledger,
            cache=DiskCache(tmp_path / "cache") if cache else None,
            base_delay_s=0.0,
            max_delay_s=0.0,
        )
        return client, prov

    return _make
