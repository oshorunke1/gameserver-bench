"""In-memory stand-in for the inventory database.

Prod uses a document store with per-row versions and multi-row transactions.
This one behaves the same way as far as the service can tell, including the
awaits, so coroutines can interleave between a read and a write.
"""

import asyncio

from .errors import DuplicateReceipt, UnknownPlayer, VersionConflict
from .models import Inventory


class InMemoryStore:
    def __init__(self, players: dict[str, Inventory], latency_ticks: int = 1):
        # player id -> [inventory, version]
        self._rows = {pid: [inv.copy(), 1] for pid, inv in players.items()}
        self._receipts: dict[str, object] = {}
        self.latency_ticks = latency_ticks

    async def _io(self) -> None:
        # pretend we're waiting on the network
        for _ in range(self.latency_ticks):
            await asyncio.sleep(0)

    async def get_inventory(self, player_id: str) -> tuple[Inventory, int]:
        await self._io()
        row = self._rows.get(player_id)
        if row is None:
            raise UnknownPlayer(player_id)
        return row[0].copy(), row[1]

    async def get_receipt(self, receipt_id: str) -> object | None:
        await self._io()
        return self._receipts.get(receipt_id)

    async def commit(self, writes, receipt_id=None, receipt=None) -> None:
        """Write several rows (and maybe one receipt) all or nothing.

        writes maps player id -> (Inventory, expected_version). An expected
        version of None skips the version check for that row.
        """
        await self._io()
        # everything below runs without yielding, so it's atomic
        if receipt_id is not None and receipt_id in self._receipts:
            raise DuplicateReceipt(receipt_id)
        for pid, (_, expected) in writes.items():
            row = self._rows.get(pid)
            if row is None:
                raise UnknownPlayer(pid)
            if expected is not None and row[1] != expected:
                raise VersionConflict(pid)
        for pid, (inv, _) in writes.items():
            row = self._rows[pid]
            row[0] = inv.copy()
            row[1] += 1
        if receipt_id is not None:
            self._receipts[receipt_id] = receipt

    def snapshot(self) -> dict[str, Inventory]:
        """Sync peek at every row, handy for tests and admin tools."""
        return {pid: row[0].copy() for pid, row in self._rows.items()}
