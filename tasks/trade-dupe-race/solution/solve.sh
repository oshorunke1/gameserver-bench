#!/bin/bash
# swaps in the fixed service and validation modules
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cp "$HERE/fixed/service.py" /app/tradesvc/service.py
cp "$HERE/fixed/validation.py" /app/tradesvc/validation.py
cd /app && python -m pytest -q tests
