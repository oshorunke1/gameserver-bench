"""The in-memory game world. Handlers change this, nothing else should."""

from dataclasses import dataclass, field

SLOTS = ("weapon", "armor", "pet")


@dataclass
class Player:
    id: str
    coins: int = 0
    # item id -> how many the player holds. Items at zero get removed.
    inventory: dict = field(default_factory=dict)
    # slot name -> item id, or None when the slot is empty
    equipped: dict = field(default_factory=lambda: {s: None for s in SLOTS})
    # [x, y, z]
    pos: list = field(default_factory=lambda: [0, 0, 0])
    online: bool = True


class World:
    def __init__(self):
        self.players = {}
        # each entry is (player_id, channel, text)
        self.chat_log = []
        # each entry is a dict, see handlers.handle_trade_offer
        self.trades = []
        self.next_trade_id = 1

    def add_player(self, player_id, coins=0, inventory=None, equipped=None,
                   pos=(0, 0, 0), online=True):
        player = Player(
            id=player_id,
            coins=coins,
            inventory=dict(inventory or {}),
            pos=list(pos),
            online=online,
        )
        if equipped:
            player.equipped.update(equipped)
        self.players[player_id] = player
        return player
