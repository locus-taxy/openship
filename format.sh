#!/bin/bash
# Format all Python files: Black + collapse 3+ newlines to one blank line

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "Running Black + collapse blank lines..."
"$ROOT/.venv/bin/python" "$ROOT/scripts/black_then_collapse.py"

echo "Done!"
