"""Tiny game server simulator so you can poke at SessionStore by hand.

Each GameServer wraps one SessionStore and keeps the live copy of each
connected player's data in memory, the way the real server does.

    cd /app && python -m savesys.server_sim
"""

from .clock import SimClock
from .datastore import DataStore
from .errors import LeaseLost, SaveFailed, SessionLocked
from .session import SessionStore


class GameServer:
    def __init__(self, store, clock, server_id: str, lease_seconds: float = 30.0):
        self.server_id = server_id
        self.sessions = SessionStore(store, clock, server_id, lease_seconds)
        self.players: dict[str, dict] = {}
        self.kicked: list[str] = []

    def join(self, player_id: str) -> bool:
        try:
            self.players[player_id] = self.sessions.load(player_id)
            return True
        except SessionLocked as err:
            print(f"[{self.server_id}] {player_id} still locked by {err.owner}, try later")
            return False

    def give_coins(self, player_id: str, amount: int) -> None:
        self.players[player_id]["coins"] += amount

    def autosave(self) -> None:
        for player_id, data in list(self.players.items()):
            try:
                self.sessions.save(player_id, data)
            except LeaseLost:
                # someone else owns this player now, so drop our copy
                self.players.pop(player_id)
                self.kicked.append(player_id)
            except SaveFailed:
                pass  # just try again next tick

    def leave(self, player_id: str) -> None:
        data = self.players.pop(player_id)
        try:
            self.sessions.release(player_id, data)
        except LeaseLost:
            self.kicked.append(player_id)


def demo() -> None:
    clock = SimClock()
    store = DataStore()
    a = GameServer(store, clock, "server-a")
    b = GameServer(store, clock, "server-b")
    a.join("p1")
    a.give_coins("p1", 50)
    a.autosave()
    print("b joins while a has p1:", b.join("p1"))
    a.leave("p1")
    print("b joins after a let go:", b.join("p1"), b.players.get("p1"))


if __name__ == "__main__":
    demo()
