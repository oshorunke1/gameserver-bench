"""Payload checks for client remote events.

This was thrown together for the alpha and only checks the basics. Returns
(True, None) when the payload looks fine, otherwise (False, reason).
"""

import json
import re

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
MAX_PAYLOAD_BYTES = 4096


def _check_field(spec, value, ctx):
    kind = spec["type"]
    if kind == "int":
        if not isinstance(value, int):
            return "not an int"
        if value < spec["min"] or value > spec["max"]:
            return "out of range"
    elif kind == "number":
        if not isinstance(value, (int, float)):
            return "not a number"
        if value < spec["min"] or value > spec["max"]:
            return "out of range"
    elif kind == "string":
        if not isinstance(value, str):
            return "not a string"
        if len(value) > spec["max_len"]:
            return "too long"
    elif kind == "enum":
        if value not in set(spec["values"]):
            return "bad enum"
    elif kind == "id":
        if not isinstance(value, str) or not ID_PATTERN.match(value):
            return "bad id"
        if spec.get("ref") == "catalog" and value not in ctx["catalog"]:
            return "unknown item"
    elif kind == "player_ref":
        if value not in ctx["players"]:
            return "unknown player"
    elif kind == "list":
        if not isinstance(value, list):
            return "not a list"
        if len(value) > spec["max_items"]:
            return "too many entries"
        for entry in value:
            problem = _check_field(spec["item"], entry, ctx)
            if problem:
                return problem
    elif kind == "object":
        if not isinstance(value, dict):
            return "not an object"
        for name, sub in spec["fields"].items():
            if name not in value:
                return "missing " + name
            problem = _check_field(sub, value[name], ctx)
            if problem:
                return problem
    return None


def validate(schema, payload, ctx):
    # keep giant payloads out
    if len(json.dumps(payload)) > MAX_PAYLOAD_BYTES:
        return False, "payload too big"
    if not isinstance(payload, dict):
        return False, "payload must be an object"
    for name, spec in schema["fields"].items():
        if name not in payload:
            if spec.get("optional"):
                continue
            return False, "missing " + name
        problem = _check_field(spec, payload[name], ctx)
        if problem:
            return False, name + ": " + problem
    return True, None


class RateLimiter:
    """Counts events per player per second bucket."""

    def __init__(self, clock):
        self.clock = clock
        self.buckets = {}

    def allow(self, player_id, event, rule):
        bucket = (player_id, event, int(self.clock.now()))
        self.buckets[bucket] = self.buckets.get(bucket, 0) + 1
        return self.buckets[bucket] <= rule["max"]
