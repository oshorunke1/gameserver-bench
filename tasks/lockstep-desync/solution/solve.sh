#!/bin/bash
# reference fix: drop in the cleaned up world.py
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cp "$HERE/fixed/lockstep/world.py" /app/lockstep/world.py
find /app -name "__pycache__" -type d -prune -exec rm -rf {} +
cd /app
python tools/replay.py scenarios/demo.json | tail -2
