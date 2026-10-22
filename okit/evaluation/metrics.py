"""Scoring of a predictions CSV against a labelled CSV, plus run-to-run regression diffs.

Field kinds:
  categorical  exact match after normalisation; accuracy, macro-F1, confusion matrix
  numeric      share within max(abs tolerance, rel tolerance * |gold|); MAE and median
                 relative error (use the latter when rows mix currencies or scales)
  set          delimiter-separated IDs; exact-set accuracy and mean Jaccard
                 ("none"/empty both mean the empty set)
"""

from __future__ import annotations

import csv
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

FieldKind = Literal["categorical", "numeric", "set"]
_EMPTY_SET_TOKENS = {"", "none", "null", "n/a", "[]"}


class FieldSpec(BaseModel):
    name: str
    kind: FieldKind = "categorical"
    tolerance: float = 0.0
    rel_tolerance: float = 0.0
    set_delimiters: str = r"[|,;\s]+"


class FieldScore(BaseModel):
    name: str
    kind: FieldKind
    n: int
    accuracy: float
    macro_f1: float | None = None
    mae: float | None = None
    median_rel_err: float | None = None
    mean_jaccard: float | None = None
    confusion: dict[str, dict[str, int]] = Field(default_factory=dict)
    errors: list[tuple[str, str, str]] = Field(default_factory=list)  # (row_id, gold, pred)


class ScoreReport(BaseModel):
    n_gold: int
    n_matched: int
    missing_ids: list[str]
    fields: list[FieldScore]
    row_exact: float


def read_csv(path: str | Path, id_col: str) -> dict[str, dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        rid = (r.get(id_col) or "").strip()
        if not rid:
            raise ValueError(f"{path}: row without {id_col!r}")
        if rid in out:
            raise ValueError(f"{path}: duplicate id {rid!r}")
        out[rid] = r
    return out


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


def _to_set(v: str | None, delims: str) -> frozenset[str]:
    raw = _norm(v)
    if raw in _EMPTY_SET_TOKENS:
        return frozenset()
    return frozenset(
        t for t in re.split(delims, raw.strip("[]")) if t and t not in _EMPTY_SET_TOKENS
    )


def _to_float(v: str | None) -> float | None:
    try:
        return float(_norm(v).replace(",", ""))
    except ValueError:
        return None


def _match(spec: FieldSpec, gold: str | None, pred: str | None) -> bool:
    if spec.kind == "numeric":
        g, p = _to_float(gold), _to_float(pred)
        if g is None or p is None:
            return _norm(gold) == _norm(pred)
        return abs(g - p) <= max(spec.tolerance, spec.rel_tolerance * abs(g))
    if spec.kind == "set":
        return _to_set(gold, spec.set_delimiters) == _to_set(pred, spec.set_delimiters)
    return _norm(gold) == _norm(pred)


def macro_f1(pairs: list[tuple[str, str]]) -> float:
    labels = {g for g, _ in pairs} | {p for _, p in pairs}
    f1s: list[float] = []
    for lab in labels:
        tp = sum(1 for g, p in pairs if g == lab and p == lab)
        fp = sum(1 for g, p in pairs if g != lab and p == lab)
        fn = sum(1 for g, p in pairs if g == lab and p != lab)
        if tp == 0:
            f1s.append(0.0)
            continue
        prec, rec = tp / (tp + fp), tp / (tp + fn)
        f1s.append(2 * prec * rec / (prec + rec))
    return sum(f1s) / len(f1s) if f1s else 0.0


def score(
    pred: dict[str, dict[str, str]], gold: dict[str, dict[str, str]], specs: list[FieldSpec]
) -> ScoreReport:
    ids = [i for i in gold if i in pred]
    missing = [i for i in gold if i not in pred]
    field_scores: list[FieldScore] = []
    all_right: Counter[str] = Counter()
    for spec in specs:
        right = 0
        errors: list[tuple[str, str, str]] = []
        pairs: list[tuple[str, str]] = []
        abs_err: list[float] = []
        rel_err: list[float] = []
        jac: list[float] = []
        for i in ids:
            g, p = gold[i].get(spec.name), pred[i].get(spec.name)
            ok = _match(spec, g, p)
            right += ok
            all_right[i] += ok
            if not ok:
                errors.append((i, g or "", p or ""))
            if spec.kind == "categorical":
                pairs.append((_norm(g), _norm(p)))
            elif spec.kind == "numeric":
                gf, pf = _to_float(g), _to_float(p)
                if gf is not None and pf is not None:
                    abs_err.append(abs(gf - pf))
                    rel_err.append(abs(gf - pf) / abs(gf) if gf else float(gf != pf))
            else:
                gs, ps = _to_set(g, spec.set_delimiters), _to_set(p, spec.set_delimiters)
                jac.append(1.0 if not gs and not ps else len(gs & ps) / len(gs | ps))
        confusion: dict[str, dict[str, int]] = defaultdict(dict)
        for g, p in pairs:
            confusion[g][p] = confusion[g].get(p, 0) + 1
        n = len(ids)
        field_scores.append(
            FieldScore(
                name=spec.name,
                kind=spec.kind,
                n=n,
                accuracy=right / n if n else 0.0,
                macro_f1=macro_f1(pairs) if spec.kind == "categorical" and pairs else None,
                mae=sum(abs_err) / len(abs_err) if abs_err else None,
                median_rel_err=statistics.median(rel_err) if rel_err else None,
                mean_jaccard=sum(jac) / len(jac) if jac else None,
                confusion=dict(confusion),
                errors=errors,
            )
        )
    exact = sum(1 for i in ids if all_right[i] == len(specs))
    return ScoreReport(
        n_gold=len(gold),
        n_matched=len(ids),
        missing_ids=missing,
        fields=field_scores,
        row_exact=exact / len(ids) if ids else 0.0,
    )


class RowChange(BaseModel):
    row_id: str
    field: str
    before: str
    after: str
    gold: str | None
    verdict: Literal["fixed", "broke", "still_wrong", "unscored"]


def diff_runs(
    a: dict[str, dict[str, str]],
    b: dict[str, dict[str, str]],
    specs: list[FieldSpec],
    gold: dict[str, dict[str, str]] | None = None,
) -> list[RowChange]:
    changes: list[RowChange] = []
    for i in a.keys() & b.keys():
        for spec in specs:
            va, vb = a[i].get(spec.name, ""), b[i].get(spec.name, "")
            if _match(spec, va, vb):
                continue
            g = gold[i].get(spec.name) if gold and i in gold else None
            if g is None:
                verdict: Literal["fixed", "broke", "still_wrong", "unscored"] = "unscored"
            else:
                ok_a, ok_b = _match(spec, g, va), _match(spec, g, vb)
                verdict = "fixed" if ok_b and not ok_a else "broke" if ok_a else "still_wrong"
            changes.append(
                RowChange(row_id=i, field=spec.name, before=va, after=vb, gold=g, verdict=verdict)
            )
    return sorted(changes, key=lambda c: (c.verdict, c.field, c.row_id))


def render_score_md(report: ScoreReport, title: str = "Evaluation") -> str:
    lines = [
        f"## {title}",
        "",
        f"Rows scored: **{report.n_matched}/{report.n_gold}** · all-fields-correct: "
        f"**{report.row_exact:.1%}**",
    ]
    if report.missing_ids:
        lines.append(f"\nMissing predictions: {', '.join(report.missing_ids[:20])}")
    lines += [
        "",
        "| field | kind | accuracy | macro-F1 | MAE | median rel err | mean Jaccard |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in report.fields:

        def fmt(x: float | None, pct: bool = False) -> str:
            return "–" if x is None else (f"{x:.1%}" if pct else f"{x:.3f}")

        lines.append(
            f"| {f.name} | {f.kind} | {fmt(f.accuracy, True)} | {fmt(f.macro_f1)} | "
            f"{fmt(f.mae)} | {fmt(f.median_rel_err, True)} | {fmt(f.mean_jaccard)} |"
        )
    for f in report.fields:
        if f.kind == "categorical" and f.confusion:
            labels = sorted(set(f.confusion) | {p for row in f.confusion.values() for p in row})
            lines += ["", f"### Confusion: `{f.name}` (rows = gold, cols = pred)", ""]
            lines.append("| gold \\ pred | " + " | ".join(labels) + " |")
            lines.append("|---" * (len(labels) + 1) + "|")
            for g in labels:
                row = f.confusion.get(g, {})
                lines.append(f"| {g} | " + " | ".join(str(row.get(p, 0)) for p in labels) + " |")
        if f.errors:
            lines += ["", f"### Errors: `{f.name}`", "", "| id | gold | pred |", "|---|---|---|"]
            lines += [f"| {i} | {g} | {p} |" for i, g, p in f.errors[:50]]
    return "\n".join(lines) + "\n"


def render_diff_md(changes: list[RowChange]) -> str:
    counts = Counter(c.verdict for c in changes)
    lines = [
        "## Run diff",
        "",
        f"Changed cells: **{len(changes)}** · fixed {counts['fixed']} · broke {counts['broke']} · "
        f"still wrong {counts['still_wrong']} · unscored {counts['unscored']}",
        "",
        "| verdict | id | field | before | after | gold |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {c.verdict} | {c.row_id} | {c.field} | {c.before} | {c.after} | {c.gold or ''} |"
        for c in changes
    ]
    return "\n".join(lines) + "\n"
