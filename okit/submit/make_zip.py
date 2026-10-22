"""Build code.zip from a source directory, excluding data, caches, venvs and secrets.

  python -m okit.submit.make_zip --src code --out code.zip [--exclude "data/*"] [--dry-run]

Refuses to run if a file that looks like it contains an API key would be included.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import zipfile
from pathlib import Path

DEFAULT_EXCLUDES = [
    ".git/*",
    ".venv/*",
    "venv/*",
    "env/*",
    "*/__pycache__/*",
    "__pycache__/*",
    "*.pyc",
    ".mypy_cache/*",
    ".pytest_cache/*",
    ".ruff_cache/*",
    "*.egg-info/*",
    ".env",
    ".env.*",
    "*/.env",
    "node_modules/*",
    ".DS_Store",
    "*/.DS_Store",
    "data/*",
    "dataset/*",
    "*/dataset/*",
    ".cache/*",
    "cache/*",
    "runs/*",
    "*.zip",
]
_SECRET_PATTERNS = [
    re.compile(rb"sk-(proj-|ant-)?[A-Za-z0-9_\-]{20,}"),
    re.compile(rb"AIza[0-9A-Za-z_\-]{35}"),
    re.compile(rb"ghp_[A-Za-z0-9]{36}"),
]
_TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".cfg",
    ".ini",
    ".csv",
    ".ipynb",
    ".sh",
    ".ps1",
}


def collect(src: Path, excludes: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(src).as_posix()
        if any(fnmatch.fnmatch(rel, pat) for pat in excludes):
            continue
        files.append(p)
    return files


def find_secrets(files: list[Path]) -> list[str]:
    hits: list[str] = []
    for p in files:
        if p.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        data = p.read_bytes()
        if any(pat.search(data) for pat in _SECRET_PATTERNS):
            hits.append(str(p))
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="okit.submit.make_zip")
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    src = Path(args.src).resolve()
    out = Path(args.out).resolve()
    files = [f for f in collect(src, DEFAULT_EXCLUDES + args.exclude) if f.resolve() != out]
    secrets = find_secrets(files)
    if secrets:
        print("Refusing to zip, possible API keys in:\n  " + "\n  ".join(secrets))
        return 1
    total = sum(f.stat().st_size for f in files)
    for f in files:
        print(f"  {f.relative_to(src).as_posix()}")
    print(f"{len(files)} files, {total / 1024:.1f} KiB uncompressed")
    if args.dry_run:
        return 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=f.relative_to(src).as_posix())
    print(f"wrote {out} ({out.stat().st_size / 1024:.1f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
