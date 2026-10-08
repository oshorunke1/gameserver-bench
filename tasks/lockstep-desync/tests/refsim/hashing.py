"""State hash that peers trade every few ticks to spot desyncs."""

import hashlib
import json


def hash_snapshot(snap):
    blob = json.dumps(snap, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
