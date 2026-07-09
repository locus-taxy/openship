#!/usr/bin/env python3
"""Run Black, then collapse 3+ newlines to 2.

Exit 1 only if any file's content changed net (Black alone always exits 1 when it
expands spacing even if collapse restores the previous bytes).
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
# venv layout differs by OS: Windows uses Scripts\black.exe, Unix uses bin/black.
_VENV_BIN = ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")
BLACK = _VENV_BIN / ("black.exe" if os.name == "nt" else "black")
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

def digest(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None

def snap(paths: list[Path]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in paths:
        if not p.is_file():
            continue
        h = digest(p)
        if h is not None:
            out[str(p.resolve())] = h
    return out

def main() -> int:
    if not BLACK.is_file():
        print("openship: black not found in .venv - run: make setup", file=sys.stderr)
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
