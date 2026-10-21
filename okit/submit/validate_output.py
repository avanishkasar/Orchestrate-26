"""Pre-submission gate for output.csv.

  python -m okit.submit.validate_output --spec output_spec.json --output output.csv --input test.csv

output_spec.json:
{
  "id_column": "message_id",
  "columns": ["message_id", "action", "reason", "confidence"],   # exact order
  "required": ["action", "reason"],                               # non-blank
  "enums": {"action": ["notify", "digest", "mute"]},
  "numeric_ranges": {"confidence": [0, 1]},
  "min_text_chars": {"reason": 25},
  "case_sensitive_enums": true
}
Exit code 0 = clean, 1 = errors. Warnings never fail the gate.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field


class OutputSpec(BaseModel):
    id_column: str
    columns: list[str]
    required: list[str] = Field(default_factory=list)
    enums: dict[str, list[str]] = Field(default_factory=dict)
    numeric_ranges: dict[str, tuple[float, float]] = Field(default_factory=dict)
    min_text_chars: dict[str, int] = Field(default_factory=dict)
    case_sensitive_enums: bool = True


class ValidationReport(BaseModel):
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path}: has a UTF-8 BOM; some graders read it into the first header")
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def validate(spec: OutputSpec, output: Path, input_csv: Path | None) -> ValidationReport:
    rep = ValidationReport()
    try:
        header, rows = _read(output)
    except (ValueError, UnicodeDecodeError) as exc:
        rep.errors.append(str(exc))
        return rep

    if header != spec.columns:
        rep.errors.append(f"header mismatch:\n  expected {spec.columns}\n  got      {header}")

    ids = [r.get(spec.id_column, "") for r in rows]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        rep.errors.append(f"duplicate ids: {dupes[:10]}")
    if any(not i.strip() for i in ids):
        rep.errors.append("blank id in output")

    if input_csv is not None:
        _, in_rows = _read(input_csv)
        want = [r.get(spec.id_column, "") for r in in_rows]
        missing, extra = set(want) - set(ids), set(ids) - set(want)
        if missing:
            rep.errors.append(
                f"{len(missing)} input ids missing from output, e.g. {sorted(missing)[:10]}"
            )
        if extra:
            rep.errors.append(f"{len(extra)} ids not in input, e.g. {sorted(extra)[:10]}")
        if not missing and not extra and ids != want:
            rep.warnings.append("row order differs from input order")

    enums = {
        col: set(v if spec.case_sensitive_enums else (x.lower() for x in v))
        for col, v in spec.enums.items()
    }
    for n, r in enumerate(rows, start=2):  # line 1 is the header
        rid = r.get(spec.id_column, f"line {n}")
        for col in spec.required:
            if not (r.get(col) or "").strip():
                rep.errors.append(f"{rid}: required column {col!r} is blank")
        for col, allowed in enums.items():
            val = r.get(col) or ""
            if not spec.case_sensitive_enums:
                val = val.lower()
            if val not in allowed:
                rep.errors.append(f"{rid}: {col}={val!r} not in {sorted(allowed)}")
        for col, (lo, hi) in spec.numeric_ranges.items():
            val = (r.get(col) or "").strip()
            try:
                x = float(val)
            except ValueError:
                rep.errors.append(f"{rid}: {col}={val!r} is not numeric")
                continue
            if not lo <= x <= hi:
                rep.errors.append(f"{rid}: {col}={x} outside [{lo}, {hi}]")
        for col, min_chars in spec.min_text_chars.items():
            if len((r.get(col) or "").strip()) < min_chars:
                rep.warnings.append(
                    f"{rid}: {col} shorter than {min_chars} chars (generic text gets capped)"
                )
        for col, val in r.items():
            if col is None:
                rep.errors.append(f"{rid}: more fields than header columns (unquoted comma?)")
            elif val and ("\n" in val or "\r" in val):
                rep.warnings.append(f"{rid}: newline inside {col!r}")

    for col in spec.min_text_chars:
        texts = [(r.get(col) or "").strip() for r in rows]
        common = Counter(texts).most_common(1)
        if common and len(texts) >= 10 and common[0][1] / len(texts) > 0.3:
            rep.warnings.append(
                f"{col}: {common[0][1]}/{len(texts)} rows share identical text; looks generic"
            )
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="okit.submit.validate_output")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--input")
    args = ap.parse_args(argv)
    spec = OutputSpec.model_validate(json.loads(Path(args.spec).read_text(encoding="utf-8")))
    rep = validate(spec, Path(args.output), Path(args.input) if args.input else None)
    for w in rep.warnings:
        print(f"WARN  {w}")
    for e in rep.errors:
        print(f"ERROR {e}")
    print("OK" if rep.ok else f"FAILED: {len(rep.errors)} error(s)")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
