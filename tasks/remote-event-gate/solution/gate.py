"""Hardened payload checks for client remote events.

The idea is simple. We only ever walk the payload as far as the schema says
it should go, so weird nesting or self referencing containers never get
explored. Every type check is exact, so bools, floats and friends can't
sneak into int fields. Returns (True, None) or (False, reason).
"""

import math
import re
import unicodedata
from collections import deque

ID_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,31}", re.ASCII)


class Reject(Exception):
    pass


def _is_int(value):
    return type(value) is int


def _check_int(spec, value):
    if not _is_int(value):
        raise Reject("not an int")
    if not (spec["min"] <= value <= spec["max"]):
        raise Reject("out of range")


def _check_number(spec, value):
    if type(value) is int:
        pass
    elif type(value) is float:
        if not math.isfinite(value):
            raise Reject("not finite")
    else:
        raise Reject("not a number")
    if not (spec["min"] <= value <= spec["max"]):
        raise Reject("out of range")


def _check_string(spec, value):
    if type(value) is not str:
        raise Reject("not a string")
    if not (spec.get("min_len", 0) <= len(value) <= spec["max_len"]):
        raise Reject("bad length")
    if spec.get("printable"):
        for ch in value:
            if unicodedata.category(ch) in ("Cc", "Cs"):
                raise Reject("unprintable character")
        if not value.strip():
            raise Reject("blank")


def _check_id(spec, value, ctx):
    if type(value) is not str or len(value) > 32 or not ID_PATTERN.fullmatch(value):
        raise Reject("bad id")
    ref = spec.get("ref")
    if ref == "catalog" and value not in ctx["catalog"]:
        raise Reject("unknown item")
    if ref == "owned":
        count = ctx["player"].inventory.get(value, 0)
        if not (_is_int(count) and count >= 1):
            raise Reject("not owned")


def _check_player_ref(value, ctx):
    if type(value) is not str:
        raise Reject("bad player")
    other = ctx["players"].get(value)
    if other is None or not other.online or other is ctx["player"]:
        raise Reject("bad player")


def _check_object(fields, value, ctx):
    if type(value) is not dict:
        raise Reject("not an object")
    for key in value:
        if type(key) is not str or key not in fields:
            raise Reject("extra key")
    for name, spec in fields.items():
        if name not in value:
            if spec.get("optional"):
                continue
            raise Reject("missing " + name)
        _check_field(spec, value[name], ctx)


def _check_list(spec, value, ctx):
    if type(value) is not list:
        raise Reject("not a list")
    if not (spec.get("min_items", 0) <= len(value) <= spec["max_items"]):
        raise Reject("bad list length")
    for entry in value:
        _check_field(spec["item"], entry, ctx)
    key = spec.get("unique_by")
    if key:
        seen = set()
        for entry in value:
            if entry[key] in seen:
                raise Reject("duplicate entry")
            seen.add(entry[key])


def _check_field(spec, value, ctx):
    kind = spec["type"]
    if kind == "int":
        _check_int(spec, value)
    elif kind == "number":
        _check_number(spec, value)
    elif kind == "string":
        _check_string(spec, value)
    elif kind == "enum":
        if type(value) is not str or value not in spec["values"]:
            raise Reject("bad enum")
    elif kind == "id":
        _check_id(spec, value, ctx)
    elif kind == "player_ref":
        _check_player_ref(value, ctx)
    elif kind == "list":
        _check_list(spec, value, ctx)
    elif kind == "object":
        _check_object(spec["fields"], value, ctx)
    else:
        raise Reject("schema has unknown type " + str(kind))


# per event business rules, run after the shape checks pass

def _rules_purchase(schema, payload, ctx):
    player = ctx["player"]
    item = ctx["catalog"][payload["item_id"]]
    if item["price"] * payload["qty"] > player.coins:
        raise Reject("not enough coins")
    if player.inventory.get(payload["item_id"], 0) + payload["qty"] > 999:
        raise Reject("stack full")


def _rules_equip(schema, payload, ctx):
    item = ctx["catalog"].get(payload["item_id"])
    if item is None or item.get("slot") != payload["slot"]:
        raise Reject("wrong slot")


def _rules_move(schema, payload, ctx):
    pos = ctx["player"].pos
    dist = math.hypot(payload["x"] - pos[0], payload["y"] - pos[1], payload["z"] - pos[2])
    if not dist <= schema["max_step"]:
        raise Reject("moved too far")


def _rules_trade(schema, payload, ctx):
    player = ctx["player"]
    if payload.get("coins", 0) > player.coins:
        raise Reject("not enough coins")
    equipped = set(v for v in player.equipped.values() if v is not None)
    for entry in payload["items"]:
        have = player.inventory.get(entry["item_id"], 0)
        if entry["item_id"] in equipped:
            have -= 1
        if entry["qty"] > have:
            raise Reject("not enough items")


RULES = {
    "purchase": _rules_purchase,
    "equip": _rules_equip,
    "move": _rules_move,
    "trade_offer": _rules_trade,
}


def validate(schema, payload, ctx):
    try:
        _check_object(schema["fields"], payload, ctx)
        rule = RULES.get(schema["event"])
        if rule:
            rule(schema, payload, ctx)
    except Reject as err:
        return False, str(err)
    return True, None


class RateLimiter:
    """Sliding window per player per event. Only accepted events get recorded."""

    def __init__(self, clock):
        self.clock = clock
        self.history = {}

    def allow(self, player_id, event, rule):
        now = self.clock.now()
        times = self.history.get((player_id, event))
        if not times:
            return True
        while times and not (now - times[0] < rule["window"]):
            times.popleft()
        return len(times) < rule["max"]

    def record(self, player_id, event):
        self.history.setdefault((player_id, event), deque()).append(self.clock.now())
