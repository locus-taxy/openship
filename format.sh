#!/bin/bash
# Format all Python files: Black + collapse double blank lines to single

set -e

echo "Running Black formatter..."
black .

echo "Collapsing double blank lines to single..."
python -c "
import os, re, glob
for f in glob.glob('**/*.py', recursive=True):
    if any(skip in f for skip in ['venv', 'node_modules', 'ui', '__pycache__']):
        continue
    content = open(f).read()
    fixed = re.sub(r'\n{3,}', '\n\n', content)
    if fixed != content:
        open(f, 'w').write(fixed)
        print(f'  Fixed: {f}')
"

echo "Done!"
