"""Loads and saves player data for one game server process.

This is what is live right now. It works fine when a player only ever
touches one server, but it has no session locking at all, so two servers
can both think they own a player and the last writer wins. See the
README for the contract this class is supposed to meet.
"""

from .defaults import default_player_data


class SessionStore:
    def __init__(self, store, clock, server_id: str, lease_seconds: float = 30.0):
        self._store = store
        self._clock = clock
        self.server_id = server_id
        self.lease_seconds = float(lease_seconds)

    @staticmethod
    def _key(player_id: str) -> str:
        return f"player:{player_id}"

    def load(self, player_id: str) -> dict:
        snap = self._store.get(self._key(player_id))
        if snap is None:
            return default_player_data()
        return snap.value["data"]

    def save(self, player_id: str, data: dict) -> None:
        key = self._key(player_id)
        snap = self._store.get(key)
        version = snap.version if snap is not None else None
        self._store.put(key, {"data": data}, version)

    def renew(self, player_id: str) -> float:
        # nothing to renew yet
        return self._clock.now() + self.lease_seconds

    def release(self, player_id: str, data: dict) -> None:
        self.save(player_id, data)
