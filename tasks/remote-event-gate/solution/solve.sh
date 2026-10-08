#!/bin/bash
# swaps in the hardened gate and the safer dispatch loop
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cp "$HERE/gate.py" /app/gameserver/gate.py
cp "$HERE/server.py" /app/gameserver/server.py
cd /app && python -m pytest tests -q
