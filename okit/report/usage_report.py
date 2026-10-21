"""Render usage.jsonl into a markdown usage/cost report.

  python -m okit.report.usage_report --ledger runs/usage.jsonl --rows 250 --out usage_report.md

Cache hits are counted separately and cost $0; tokens and cost cover live calls only.
"""

from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from pathlib import Path

from okit.llm.ledger import UsageRecord, read_ledger


def _money(x: float | None) -> str:
    return "unknown (no price)" if x is None else f"${x:.4f}"


def _sum_cost(recs: list[UsageRecord]) -> float | None:
    costs = [r.cost_usd for r in recs if not r.cache_hit]
    return None if any(c is None for c in costs) else sum(c for c in costs if c is not None)


def render(records: list[UsageRecord], n_rows: int | None = None) -> str:
    live = [r for r in records if not r.cache_hit and r.ok]
    failed = [r for r in records if not r.ok]
    hits = [r for r in records if r.cache_hit]
    lines = [
        "# Usage report",
        "",
        "Generated from the append-only usage ledger; every model call is one ledger line.",
        "",
        f"- Live calls: **{len(live)}** · cache hits: **{len(hits)}** · failed attempts: "
        f"**{len(failed)}**",
        f"- Total input tokens: **{sum(r.input_tokens for r in live):,}** "
        f"(cached by provider: {sum(r.cached_input_tokens for r in live):,})",
        f"- Total output tokens: **{sum(r.output_tokens for r in live):,}**",
        f"- Total cost: **{_money(_sum_cost(live))}**",
    ]
    if n_rows:
        total = _sum_cost(live)
        per_row = None if total is None else total / n_rows
        lines.append(
            f"- Rows: {n_rows} · cost per row: **{_money(per_row)}**"
            f" · live calls per row: {len(live) / n_rows:.2f}"
        )

    by_model: dict[tuple[str, str], list[UsageRecord]] = defaultdict(list)
    for r in live:
        by_model[(r.provider, r.model)].append(r)
    lines += [
        "",
        "## Per model",
        "",
        "| provider | model | calls | input tok | output tok | avg in/call | avg out/call | "
        "p50 latency ms | p95 latency ms | cost |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (prov, model), recs in sorted(by_model.items()):
        lat = sorted(r.latency_ms for r in recs)
        p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))]
        tin, tout = sum(r.input_tokens for r in recs), sum(r.output_tokens for r in recs)
        lines.append(
            f"| {prov} | {model} | {len(recs)} | {tin:,} | {tout:,} | {tin / len(recs):,.0f} | "
            f"{tout / len(recs):,.0f} | {statistics.median(lat):,.0f} | {p95:,.0f} | "
            f"{_money(_sum_cost(recs))} |"
        )

    by_purpose: dict[str, list[UsageRecord]] = defaultdict(list)
    for r in live:
        by_purpose[r.purpose].append(r)
    lines += [
        "",
        "## Per purpose",
        "",
        "| purpose | calls | input tok | output tok | cost |",
        "|---|---|---|---|---|",
    ]
    for purpose, recs in sorted(by_purpose.items()):
        lines.append(
            f"| {purpose} | {len(recs)} | {sum(r.input_tokens for r in recs):,} | "
            f"{sum(r.output_tokens for r in recs):,} | {_money(_sum_cost(recs))} |"
        )

    if failed:
        lines += ["", "## Failed attempts (retried or fell back)", ""]
        errs: dict[str, int] = defaultdict(int)
        for r in failed:
            errs[(r.error or "unknown").split(":", 1)[-1].strip()[:120]] += 1
        lines += [f"- {n}× {e}" for e, n in sorted(errs.items(), key=lambda kv: -kv[1])[:15]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="okit.report.usage_report")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--rows", type=int)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    text = render(read_ledger(args.ledger), args.rows)
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
