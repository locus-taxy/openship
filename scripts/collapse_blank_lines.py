#!/usr/bin/env python3
"""Collapse 3+ consecutive newlines to 2 (one blank line between blocks).

Used after Black so top-level spacing matches a single blank line, not PEP 8's two.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SKIP_PARTS = frozenset({"venv", ".venv", "node_modules", "ui", "__pycache__"})

BLANK_RUN = re.compile(r"\n{3,}")

def should_skip(path: Path) -> bool:
    return any(p in SKIP_PARTS for p in path.parts)

def fix_content(content: str) -> str:
    return BLANK_RUN.sub("\n\n", content)

def process_file(path: Path) -> bool:
    if not path.is_file() or should_skip(path.resolve()):
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    fixed = fix_content(text)
    if fixed == text:
        return False
    path.write_text(fixed, encoding="utf-8")
    print(f"Fixed: {path}")
    return True

def main() -> int:
    changed = False
    args = sys.argv[1:]
    if args and args[0] == "--all":
        root = Path(".")
        for f in sorted(root.rglob("*.py")):
            if process_file(f):
                changed = True
    else:
        for arg in args:
            if process_file(Path(arg)):
                changed = True
    return 1 if changed else 0

if __name__ == "__main__":
    raise SystemExit(main())
