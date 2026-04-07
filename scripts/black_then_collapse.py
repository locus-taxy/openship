#!/usr/bin/env python3
"""Run Black, then collapse 3+ newlines to 2.

Exit 1 only if any file's content changed net (Black alone always exits 1 when it
expands spacing even if collapse restores the previous bytes).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLACK = ROOT / ".venv" / "bin" / "black"
COLLAPSE = ROOT / "scripts" / "collapse_blank_lines.py"
SKIP_PARTS = frozenset({"venv", ".venv", "node_modules", "ui", "__pycache__"})

def iter_py_under_root() -> list[Path]:
    out: list[Path] = []
    for p in ROOT.rglob("*.py"):
        try:
            rel = p.relative_to(ROOT)
        except ValueError:
            continue
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        out.append(p)
    return sorted(out)

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def snap(paths: list[Path]) -> dict[str, str]:
    return {str(p.resolve()): digest(p) for p in paths if p.is_file()}

def main() -> int:
    if not BLACK.is_file():
        print("openship: missing .venv/bin/black — run: make setup", file=sys.stderr)
        return 1

    py = sys.executable
    argv = sys.argv[1:]

    if argv:
        paths = [
            (ROOT / a).resolve() if not Path(a).is_absolute() else Path(a).resolve() for a in argv
        ]
        before = snap(paths)
        r = subprocess.run([str(BLACK), *argv], cwd=ROOT)
        if r.returncode not in (0, 1):
            return r.returncode
        r2 = subprocess.run([py, str(COLLAPSE), *argv], cwd=ROOT)
        if r2.returncode not in (0, 1):
            return r2.returncode
    else:
        paths = iter_py_under_root()
        before = snap(paths)
        r = subprocess.run([str(BLACK), "."], cwd=ROOT)
        if r.returncode not in (0, 1):
            return r.returncode
        r2 = subprocess.run([py, str(COLLAPSE), "--all"], cwd=ROOT)
        if r2.returncode not in (0, 1):
            return r2.returncode

    after = snap(paths)
    keys = set(before) | set(after)
    changed = any(before.get(k) != after.get(k) for k in keys)
    return 1 if changed else 0

if __name__ == "__main__":
    raise SystemExit(main())
