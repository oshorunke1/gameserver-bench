"""Player to player trading.

The game server calls execute_trade once both players hit accept. Clients
retry on timeouts, so the same request_id can show up more than once, on any
server, even at the same time. All the safety lives in the store: versioned
writes stop two trades from spending the same stuff, and the receipt rides
along in the same commit so a request can only ever land once.
"""

from .errors import DuplicateReceipt, StoreUnavailable, UnknownPlayer, VersionConflict
from .models import (
    COMPLETED,
    DEFAULT_SLOT_LIMIT,
    FAILED,
    INVENTORY_FULL,
    REJECTED,
    REQUEST_ID_REUSED,
    STORE_UNAVAILABLE,
    UNKNOWN_PLAYER,
    TradeRequest,
    TradeResult,
)
from .validation import apply_offer, check_offer, fingerprint, static_problem


class TradeService:
    def __init__(self, store, *, slot_limit: int = DEFAULT_SLOT_LIMIT):
        self._store = store
        self._slot_limit = slot_limit

    async def execute_trade(self, req: TradeRequest) -> TradeResult:
        rid = req.request_id
        problem = static_problem(req)
        if problem:
            return TradeResult(rid, REJECTED, problem)
        try:
            return await self._run(req)
        except UnknownPlayer:
            return TradeResult(rid, REJECTED, UNKNOWN_PLAYER)
        except StoreUnavailable:
            return TradeResult(rid, FAILED, STORE_UNAVAILABLE)

    async def _run(self, req: TradeRequest) -> TradeResult:
        rid = req.request_id
        fp = fingerprint(req)
        while True:
            a, a_ver = await self._store.get_inventory(req.initiator)
            b, b_ver = await self._store.get_inventory(req.target)
            # read the receipt after the rows, so if it's missing here the
            # rows we hold are from before any earlier copy of this request
            prior = await self._store.get_receipt(rid)
            if prior is not None:
                if prior.get("fingerprint") == fp:
                    return TradeResult(rid, COMPLETED)
                return TradeResult(rid, REJECTED, REQUEST_ID_REUSED)

            reason = check_offer(a, req.initiator_offer) or check_offer(b, req.target_offer)
            if reason:
                return TradeResult(rid, REJECTED, reason)

            apply_offer(a, b, req.initiator_offer)
            apply_offer(b, a, req.target_offer)
            if len(a.items) > self._slot_limit or len(b.items) > self._slot_limit:
                return TradeResult(rid, REJECTED, INVENTORY_FULL)

            try:
                await self._store.commit(
                    {req.initiator: (a, a_ver), req.target: (b, b_ver)},
                    receipt_id=rid,
                    receipt={"fingerprint": fp},
                )
            except (VersionConflict, DuplicateReceipt):
                # somebody beat us to it, reread and decide again
                continue
            return TradeResult(rid, COMPLETED)
