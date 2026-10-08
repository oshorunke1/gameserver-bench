"""Where decoded client remote events come in and get sent to handlers."""

import json
import os

from . import gate
from .handlers import HANDLERS

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "data", "catalog.json")


def load_schemas():
    schemas = {}
    for name in sorted(os.listdir(SCHEMA_DIR)):
        if name.endswith(".json"):
            with open(os.path.join(SCHEMA_DIR, name), encoding="utf-8") as f:
                schema = json.load(f)
            schemas[schema["event"]] = schema
    return schemas


def load_catalog():
    with open(CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


class Server:
    def __init__(self, world, catalog, clock):
        self.world = world
        self.catalog = catalog
        self.clock = clock
        self.schemas = load_schemas()
        self.limiter = gate.RateLimiter(clock)

    def dispatch(self, player_id, event, payload):
        """Handle one remote event. Always returns a dict with an "ok" bool."""
        try:
            return self._dispatch(player_id, event, payload)
        except Exception:
            # the gate should have caught it already, this is just a seatbelt
            return {"ok": False, "error": "internal"}

    def _dispatch(self, player_id, event, payload):
        if type(player_id) is not str:
            return {"ok": False, "error": "unknown player"}
        player = self.world.players.get(player_id)
        if player is None or not player.online:
            return {"ok": False, "error": "unknown player"}
        if type(event) is not str or event not in self.schemas:
            return {"ok": False, "error": "unknown event"}
        schema = self.schemas[event]
        ctx = {"catalog": self.catalog, "players": self.world.players, "player": player}
        ok, reason = gate.validate(schema, payload, ctx)
        if not ok:
            return {"ok": False, "error": reason}
        if not self.limiter.allow(player_id, event, schema["rate"]):
            return {"ok": False, "error": "rate limited"}
        result = HANDLERS[event](self.world, player, payload, self.catalog)
        self.limiter.record(player_id, event)
        return result
