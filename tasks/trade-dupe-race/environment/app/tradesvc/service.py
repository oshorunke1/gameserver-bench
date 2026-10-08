"""Player to player trading.

The game server calls execute_trade once both players hit accept. Clients
retry on timeouts, so the same request_id can show up more than once.
"""

from .errors import StoreUnavailable, UnknownPlayer
from .models import (
    COMPLETED,
    DEFAULT_SLOT_LIMIT,
    FAILED,
    INVENTORY_FULL,
    REJECTED,
    STORE_UNAVAILABLE,
    UNKNOWN_PLAYER,
    TradeRequest,
    TradeResult,
)
from .receipts import ReceiptCache
from .validation import apply_offer, check_offer, fits


class TradeService:
    def __init__(self, store, *, slot_limit: int = DEFAULT_SLOT_LIMIT):
        self._store = store
        self._slot_limit = slot_limit
        self._cache = ReceiptCache()

    async def execute_trade(self, req: TradeRequest) -> TradeResult:
        cached = self._cache.get(req.request_id)
        if cached is not None:
            return cached
        try:
            result = await self._run(req)
        except StoreUnavailable:
            result = TradeResult(req.request_id, FAILED, STORE_UNAVAILABLE)
        self._cache.remember(req.request_id, result)
        return result

    async def _run(self, req: TradeRequest) -> TradeResult:
        prior = await self._store.get_receipt(req.request_id)
        if prior is not None:
            return prior

        try:
            a, _ = await self._store.get_inventory(req.initiator)
            b, _ = await self._store.get_inventory(req.target)
        except UnknownPlayer:
            return TradeResult(req.request_id, REJECTED, UNKNOWN_PLAYER)

        reason = check_offer(a, req.initiator_offer) or check_offer(b, req.target_offer)
        if reason:
            return TradeResult(req.request_id, REJECTED, reason)
        if not fits(b, req.initiator_offer, self._slot_limit) or not fits(
            a, req.target_offer, self._slot_limit
        ):
            return TradeResult(req.request_id, REJECTED, INVENTORY_FULL)

        apply_offer(a, b, req.initiator_offer)
        apply_offer(b, a, req.target_offer)
        await self._store.commit({req.initiator: (a, None), req.target: (b, None)})

        result = TradeResult(req.request_id, COMPLETED)
        await self._store.commit({}, receipt_id=req.request_id, receipt=result)
        return result
