from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from PIL import Image

from okit.evaluation.metrics import FieldSpec, diff_runs, read_csv, render_score_md, score
from okit.llm.ledger import UsageRecord
from okit.perception.image import load_image
from okit.report.usage_report import render
from okit.runner.checkpoint import load_checkpoint, run_rows
from okit.submit import make_zip
from okit.submit.validate_output import OutputSpec, validate


def _write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path


async def test_checkpoint_resume_retries_only_failures(tmp_path: Path) -> None:
    ck = tmp_path / "ck.jsonl"
    calls: list[str] = []
    fail_once = {"b"}

    async def fn(rid: str, row: int) -> dict[str, int]:
        calls.append(rid)
        if rid in fail_once:
            fail_once.discard(rid)
            raise ValueError("flaky")
        return {"v": row * 2}

    rows = [("a", 1), ("b", 2), ("c", 3)]
    first = await run_rows(rows, fn, checkpoint_path=ck, concurrency=2)
    assert [first[r].ok for r in "abc"] == [True, False, True]
    calls.clear()
    second = await run_rows(rows, fn, checkpoint_path=ck)
    assert calls == ["b"]
    assert all(o.ok for o in second.values())
    assert load_checkpoint(ck)["b"].result == {"v": 4}


def test_score_and_diff(tmp_path: Path) -> None:
    gold = _write_csv(
        tmp_path / "g.csv",
        [
            {"id": "1", "action": "mute", "conf": "0.80", "ev": "m1|m2"},
            {"id": "2", "action": "notify", "conf": "0.90", "ev": "none"},
            {"id": "3", "action": "digest", "conf": "0.85", "ev": "m9"},
        ],
    )
    a = _write_csv(
        tmp_path / "a.csv",
        [
            {"id": "1", "action": "mute", "conf": "0.82", "ev": "m2, m1"},
            {"id": "2", "action": "digest", "conf": "0.50", "ev": ""},
            {"id": "3", "action": "digest", "conf": "0.85", "ev": "m8"},
        ],
    )
    b = _write_csv(
        tmp_path / "b.csv",
        [
            {"id": "1", "action": "digest", "conf": "0.82", "ev": "m1|m2"},
            {"id": "2", "action": "notify", "conf": "0.50", "ev": "none"},
            {"id": "3", "action": "digest", "conf": "0.85", "ev": "m8"},
        ],
    )
    specs = [
        FieldSpec(name="action"),
        FieldSpec(name="conf", kind="numeric", tolerance=0.05),
        FieldSpec(name="ev", kind="set"),
    ]
    rep = score(read_csv(a, "id"), read_csv(gold, "id"), specs)
    by = {f.name: f for f in rep.fields}
    assert by["action"].accuracy == 2 / 3
    assert by["conf"].accuracy == 2 / 3
    assert by["ev"].accuracy == 2 / 3
    assert "Confusion" in render_score_md(rep)

    changes = diff_runs(read_csv(a, "id"), read_csv(b, "id"), specs, read_csv(gold, "id"))
    verdicts = {(c.row_id, c.field): c.verdict for c in changes}
    assert verdicts == {("1", "action"): "broke", ("2", "action"): "fixed"}


def test_validate_output(tmp_path: Path) -> None:
    spec = OutputSpec(
        id_column="id",
        columns=["id", "action", "conf"],
        required=["action"],
        enums={"action": ["mute", "notify"]},
        numeric_ranges={"conf": (0, 1)},
    )
    inp = _write_csv(tmp_path / "in.csv", [{"id": "1"}, {"id": "2"}, {"id": "3"}])
    out = _write_csv(
        tmp_path / "out.csv",
        [
            {"id": "1", "action": "mute", "conf": "0.8"},
            {"id": "2", "action": "MUTE", "conf": "1.4"},
            {"id": "2", "action": "", "conf": "x"},
        ],
    )
    rep = validate(spec, out, inp)
    joined = "\n".join(rep.errors)
    for needle in [
        "duplicate ids",
        "missing from output",
        "'MUTE' not in",
        "outside",
        "is blank",
        "not numeric",
    ]:
        assert needle in joined, needle

    good = _write_csv(
        tmp_path / "good.csv", [{"id": str(i), "action": "mute", "conf": "0.8"} for i in (1, 2, 3)]
    )
    assert validate(spec, good, inp).ok


def test_load_image_downscales_and_flattens_alpha(tmp_path: Path) -> None:
    p = tmp_path / "big.png"
    Image.new("RGBA", (4000, 2000), (255, 0, 0, 0)).save(p)
    img = load_image(p, max_edge_px=1000)
    assert (img.width, img.height) == (1000, 500)
    assert (img.original_width, img.original_height) == (4000, 2000)
    assert img.part.media_type == "image/jpeg"


def test_usage_report_flags_unknown_prices() -> None:
    def rec(model: str, cost: float | None, hit: bool = False, ok: bool = True) -> UsageRecord:
        return UsageRecord(
            ts="t",
            provider="p",
            model=model,
            purpose="perceive",
            row_id=None,
            input_tokens=100,
            output_tokens=10,
            cached_input_tokens=0,
            latency_ms=50.0,
            cache_hit=hit,
            cost_usd=cost,
            ok=ok,
            error=None if ok else "attempt 1: 429",
        )

    md = render(
        [rec("a", 0.01), rec("a", 0.02), rec("a", 0.0, hit=True), rec("a", None, ok=False)], 2
    )
    assert "Live calls: **2**" in md and "$0.0300" in md and "$0.0150" in md
    assert "unknown (no price)" in render([rec("b", None)])


def test_make_zip_excludes_data_and_blocks_secrets(tmp_path: Path) -> None:
    src = tmp_path / "code"
    (src / "data").mkdir(parents=True)
    (src / "data" / "big.csv").write_text("x", encoding="utf-8")
    (src / "main.py").write_text("print(1)\n", encoding="utf-8")
    (src / ".env").write_text("OPENAI_API_KEY=sk-proj-" + "a" * 30, encoding="utf-8")
    out = tmp_path / "code.zip"
    assert make_zip.main(["--src", str(src), "--out", str(out)]) == 0
    assert zipfile.ZipFile(out).namelist() == ["main.py"]

    (src / "leak.py").write_text('KEY = "sk-ant-' + "b" * 30 + '"\n', encoding="utf-8")
    assert make_zip.main(["--src", str(src), "--out", str(out)]) == 1


def test_spec_json_roundtrip(tmp_path: Path) -> None:
    raw = {"id_column": "id", "columns": ["id"], "numeric_ranges": {"c": [0, 1]}}
    spec = OutputSpec.model_validate(json.loads(json.dumps(raw)))
    assert spec.numeric_ranges["c"] == (0, 1)
