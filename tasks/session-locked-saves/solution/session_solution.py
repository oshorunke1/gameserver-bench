"""Loads and saves player data for one game server process, with session locking.

Every record in the store looks like this

    {"data": {...}, "lock": {"owner", "lock_id", "expires_at"} or None, "write_id": "..."}

lock_id is fresh for every successful load, so "do I still hold this player"
is just "is the lock_id in the record the one I got when I loaded". write_id
is fresh for every write attempt, so after a WriteTimeout we can read the
record back and tell whether our write landed.
"""

import copy
import uuid

from .datastore import DataStoreUnavailable, VersionConflict, WriteTimeout
from .defaults import default_player_data
from .errors import LeaseLost, SaveFailed, SessionLocked

MAX_FAILED_WRITES = 5


class SessionStore:
    def __init__(self, store, clock, server_id: str, lease_seconds: float = 30.0):
        self._store = store
        self._clock = clock
        self.server_id = server_id
        self.lease_seconds = float(lease_seconds)
        # player_id -> the lock_id we got when we loaded them
        self._held: dict[str, str] = {}

    @staticmethod
    def _key(player_id: str) -> str:
        return f"player:{player_id}"

    def _write(self, player_id: str, build) -> dict:
        """Read, build the next record, conditional write, repeat until it sticks.

        build(record) gets the current record (or None) and either returns the
        new record or raises to bail out. Version conflicts just mean someone
        else wrote first, so we read again and let build decide again.
        """
        key = self._key(player_id)
        failed = 0
        while True:
            snap = self._store.get(key)
            record = snap.value if snap is not None else None
            version = snap.version if snap is not None else None
            new_record = build(record)
            write_id = uuid.uuid4().hex
            new_record["write_id"] = write_id
            try:
                self._store.put(key, new_record, version)
                return new_record
            except VersionConflict:
                continue
            except DataStoreUnavailable:
                failed += 1
            except WriteTimeout:
                # no idea if it landed, so go look
                check = self._store.get(key)
                if check is not None and check.value.get("write_id") == write_id:
                    return new_record
                failed += 1
            if failed >= MAX_FAILED_WRITES:
                raise SaveFailed(player_id)

    def load(self, player_id: str) -> dict:
        new_lock_id = uuid.uuid4().hex
        mine = self._held.get(player_id)

        def build(record):
            now = self._clock.now()
            lock = record.get("lock") if record is not None else None
            if (
                lock is not None
                and lock["lock_id"] != mine
                and lock["owner"] != self.server_id
                and now < lock["expires_at"]
            ):
                raise SessionLocked(player_id, lock["owner"], lock["expires_at"])
            data = record["data"] if record is not None else default_player_data()
            return {
                "data": data,
                "lock": {
                    "owner": self.server_id,
                    "lock_id": new_lock_id,
                    "expires_at": now + self.lease_seconds,
                },
            }

        record = self._write(player_id, build)
        self._held[player_id] = new_lock_id
        return copy.deepcopy(record["data"])

    def _held_write(self, player_id: str, data, keep_lock: bool) -> dict:
        mine = self._held.get(player_id)

        def build(record):
            lock = record.get("lock") if record is not None else None
            if mine is None or lock is None or lock["lock_id"] != mine:
                raise LeaseLost(player_id)
            new_data = record["data"] if data is None else data
            if not keep_lock:
                return {"data": new_data, "lock": None}
            return {
                "data": new_data,
                "lock": {
                    "owner": self.server_id,
                    "lock_id": mine,
                    "expires_at": self._clock.now() + self.lease_seconds,
                },
            }

        try:
            return self._write(player_id, build)
        except LeaseLost:
            self._held.pop(player_id, None)
            raise

    def save(self, player_id: str, data: dict) -> None:
        self._held_write(player_id, copy.deepcopy(data), keep_lock=True)

    def renew(self, player_id: str) -> float:
        record = self._held_write(player_id, None, keep_lock=True)
        return record["lock"]["expires_at"]

    def release(self, player_id: str, data: dict) -> None:
        self._held_write(player_id, copy.deepcopy(data), keep_lock=False)
        self._held.pop(player_id, None)
