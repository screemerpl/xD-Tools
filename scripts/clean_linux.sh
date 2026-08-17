#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

for target in build dist .pytest_cache; do
    if [ -e "$target" ]; then
        echo "Removing $target"
        rm -rf "$target"
    fi
done

# PyInstaller regenerates this from scratch on every build (see
# scripts/build_linux.sh) -- it's a byproduct, not hand-maintained.
find . -maxdepth 1 -type f -name "*.spec" -print -delete

find src tests -type d -name "__pycache__" -exec rm -rf {} +
find src tests -type f -name "*.pyc" -delete
# editable installs (`pip install -e .`) leave an egg-info dir under src/
find src tests -type d -name "*.egg-info" -exec rm -rf {} +

# ...and some pip versions leave one at the repo root instead
find . -maxdepth 1 -type d -name "*.egg-info" -exec rm -rf {} +

if [ "${1:-}" = "--all" ] && [ -d ".venv" ]; then
    echo "Removing .venv"
    rm -rf .venv
fi

echo "Clean complete."
