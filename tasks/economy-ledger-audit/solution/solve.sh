#!/bin/bash
set -euo pipefail

# drop the reference audit script into place and try it on the example
cp /solution/audit.py /app/audit.py
python3 /app/audit.py /app/example/events.jsonl /tmp/example_out.json
python3 -c "import json,sys; a=json.load(open('/tmp/example_out.json')); b=json.load(open('/app/example/expected.json')); sys.exit(0 if a==b else 1)"
python3 /app/audit.py /app/events.jsonl /app/report.json
