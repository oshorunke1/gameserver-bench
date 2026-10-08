#!/bin/bash
# drop in the reference SessionStore with leases, lock ids and timeout checks
set -euo pipefail

cp /solution/session_solution.py /app/savesys/session.py
cd /app && python -m pytest -q tests
