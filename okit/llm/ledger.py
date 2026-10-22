"""Append-only usage ledger (usage.jsonl) and cost computation.

Prices are never hardcoded: load them from a JSON file you fill in from the
vendor's pricing page on the day, e.g.
    {"gpt-4.1": {"input": 2.0, "output": 8.0, "cached_input": 0.5}}
(USD per 1M tokens). Unknown models are recorded with cost_usd = null so the
report shows the gap instead of inventing a number.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from okit.types import Usage


class Price(BaseModel):
    input: float
    output: float
    cached_input: float | None = None


class UsageRecord(BaseModel):
    ts: str
    provider: str
    model: str
    purpose: str
    row_id: str | None
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    latency_ms: float
    cache_hit: bool
    cost_usd: float | None
    ok: bool
    error: str | None = None


def load_prices(path: str | Path | None) -> dict[str, Price]:
    if path is None or not Path(path).exists():
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    # Keys starting with "_" are comments.
    return {m: Price.model_validate(p) for m, p in raw.items() if not m.startswith("_")}


def compute_cost(usage: Usage, price: Price | None) -> float | None:
    if price is None:
        return None
    cached = usage.cached_input_tokens
    cached_rate = price.cached_input if price.cached_input is not None else price.input
    uncached = max(usage.input_tokens - cached, 0)
    return (
        uncached * price.input + cached * cached_rate + usage.output_tokens * price.output
    ) / 1e6


class Ledger:
    def __init__(self, path: str | Path, prices: dict[str, Price] | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.prices = prices or {}
        self._lock = asyncio.Lock()

    def price_for(self, model: str) -> Price | None:
        if model in self.prices:
            return self.prices[model]
        # Vendors return dated snapshots ("gpt-4.1-2025-04-14"); fall back to the longest prefix.
        matches = [k for k in self.prices if model.startswith(k)]
        return self.prices[max(matches, key=len)] if matches else None

    async def record(
        self,
        *,
        provider: str,
        model: str,
        purpose: str,
        row_id: str | None,
        usage: Usage,
        latency_ms: float,
        cache_hit: bool,
        ok: bool,
        error: str | None = None,
    ) -> UsageRecord:
        rec = UsageRecord(
            ts=datetime.now(UTC).isoformat(),
            provider=provider,
            model=model,
            purpose=purpose,
            row_id=row_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            latency_ms=round(latency_ms, 1),
            cache_hit=cache_hit,
            cost_usd=0.0 if cache_hit else compute_cost(usage, self.price_for(model)),
            ok=ok,
            error=error,
        )
        async with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(rec.model_dump_json() + "\n")
        return rec


def read_ledger(path: str | Path) -> list[UsageRecord]:
    p = Path(path)
    if not p.exists():
        return []
    return [
        UsageRecord.model_validate_json(line)
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
