"""CLI:
  python -m okit.evaluation score --pred out.csv --gold sample.csv --id id \
      --cat action,message_type --num confidence:0.05 --set evidence_ids --out evaluation/score.md
  python -m okit.evaluation diff --a runA.csv --b runB.csv --gold sample.csv --id id --cat action
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from okit.evaluation.metrics import (
    FieldSpec,
    diff_runs,
    read_csv,
    render_diff_md,
    render_score_md,
    score,
)


def _specs(args: argparse.Namespace) -> list[FieldSpec]:
    specs = [FieldSpec(name=n, kind="categorical") for n in _split(args.cat)]
    for item in _split(args.num):
        name, _, tol = item.partition(":")
        specs.append(FieldSpec(name=name, kind="numeric", tolerance=float(tol or 0)))
    specs += [FieldSpec(name=n, kind="set") for n in _split(args.set)]
    if not specs:
        raise SystemExit("give at least one of --cat / --num / --set")
    return specs


def _split(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def _emit(text: str, out: str | None) -> None:
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
    sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="okit.evaluation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("score", "diff"):
        p = sub.add_parser(name)
        p.add_argument("--id", required=True)
        p.add_argument("--cat")
        p.add_argument("--num", help="name[:abs_tolerance],...")
        p.add_argument("--set")
        p.add_argument("--out")
        p.add_argument("--gold", required=name == "score")
    sub.choices["score"].add_argument("--pred", required=True)
    sub.choices["diff"].add_argument("--a", required=True)
    sub.choices["diff"].add_argument("--b", required=True)
    args = ap.parse_args(argv)

    specs = _specs(args)
    gold = read_csv(args.gold, args.id) if args.gold else None
    if args.cmd == "score":
        assert gold is not None
        _emit(render_score_md(score(read_csv(args.pred, args.id), gold, specs)), args.out)
    else:
        changes = diff_runs(read_csv(args.a, args.id), read_csv(args.b, args.id), specs, gold)
        _emit(render_diff_md(changes), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
