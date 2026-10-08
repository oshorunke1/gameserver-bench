"""A few happy path checks. Run with: cd /app && python -m pytest tests -q"""

from gameserver.clock import ManualClock
from gameserver.server import Server, load_catalog
from gameserver.world import World


def make_server():
    world = World()
    world.add_player("alice", coins=1000, inventory={"wooden_sword": 1, "health_potion": 5})
    world.add_player("bob", coins=50)
    return Server(world, load_catalog(), ManualClock())


def test_purchase():
    server = make_server()
    assert server.dispatch("alice", "purchase", {"item_id": "leather_vest", "qty": 2})["ok"]
    assert server.world.players["alice"].coins == 840


def test_equip_and_chat():
    server = make_server()
    assert server.dispatch("alice", "equip", {"slot": "weapon", "item_id": "wooden_sword"})["ok"]
    assert server.dispatch("alice", "chat", {"channel": "global", "text": "gg"})["ok"]


def test_move_and_trade():
    server = make_server()
    assert server.dispatch("alice", "move", {"x": 10, "y": 0.5, "z": -3})["ok"]
    offer = {"to": "bob", "items": [{"item_id": "health_potion", "qty": 2}], "coins": 100}
    assert server.dispatch("alice", "trade_offer", offer)["ok"]
    assert server.world.players["alice"].inventory["health_potion"] == 3
