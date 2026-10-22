"""Per-row checkpoint/resume with bounded concurrency.

Each finished row is appended to a JSONL file as soon as it completes, so a
crash, rate-limit storm or Ctrl+C loses at most the rows in flight. On resume,
rows that succeeded are skipped and rows that failed are retried.
"""

from __future__ import annotations

import asyncio
import json
import traceback
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class RowOutcome(BaseModel):
    row_id: str
    ok: bool
    result: Any = None
    error: str | None = None


def load_checkpoint(path: str | Path) -> dict[str, RowOutcome]:
    p = Path(path)
    done: dict[str, RowOutcome] = {}
    if not p.exists():
        return done
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = RowOutcome.model_validate_json(line)
        except ValueError:
            continue  # torn final line from a killed process
        # Later lines win, so a retried success overrides an earlier failure.
        done[rec.row_id] = rec
    return done


async def run_rows(
    rows: Iterable[tuple[str, Any]],
    fn: Callable[[str, Any], Awaitable[Any]],
    *,
    checkpoint_path: str | Path,
    concurrency: int = 4,
    resume: bool = True,
    on_progress: Callable[[int, int, RowOutcome], None] | None = None,
) -> dict[str, RowOutcome]:
    """Run fn(row_id, row) for every row; return outcomes keyed by row_id.

    fn's return value must be JSON-serialisable (or a Pydantic model).
    Exceptions are captured per row and never abort the batch.
    """
    path = Path(checkpoint_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not resume:
        path.unlink(missing_ok=True)
    outcomes = {k: v for k, v in load_checkpoint(path).items() if v.ok}

    items = list(rows)
    ids = [rid for rid, _ in items]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate row ids in input")
    pending = [(rid, row) for rid, row in items if rid not in outcomes]
    total, finished = len(pending), 0
    sem = asyncio.Semaphore(concurrency)
    write_lock = asyncio.Lock()

    async def one(rid: str, row: Any) -> None:
        nonlocal finished
        async with sem:
            try:
                value = await fn(rid, row)
                if isinstance(value, BaseModel):
                    value = value.model_dump(mode="json")
                out = RowOutcome(row_id=rid, ok=True, result=value)
            except Exception as exc:
                tb = traceback.format_exception_only(type(exc), exc)[-1].strip()
                out = RowOutcome(row_id=rid, ok=False, error=tb[:1_000])
        async with write_lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(out.model_dump(mode="json"), ensure_ascii=False) + "\n")
            outcomes[rid] = out
            finished += 1
            if on_progress:
                on_progress(finished, total, out)

    await asyncio.gather(*(one(rid, row) for rid, row in pending))
    return {rid: outcomes[rid] for rid in ids}
