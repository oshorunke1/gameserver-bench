"""Checks and moves for one side of a trade."""

from .models import (
    INSUFFICIENT_GOLD,
    INSUFFICIENT_ITEMS,
    INVALID_REQUEST,
    Inventory,
    TradeOffer,
    TradeRequest,
)


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def totals(offer: TradeOffer) -> dict[str, int]:
    """Sum up the offer per item key, since the client can repeat a key."""
    out: dict[str, int] = {}
    for key, qty in offer.items:
        out[key] = out.get(key, 0) + qty
    return out


def static_problem(req: TradeRequest) -> str | None:
    """Stuff we can reject without touching the store."""
    if req.initiator == req.target:
        return INVALID_REQUEST
    for offer in (req.initiator_offer, req.target_offer):
        if not _is_count(offer.gold) or offer.gold < 0:
            return INVALID_REQUEST
        for entry in offer.items:
            if len(entry) != 2:
                return INVALID_REQUEST
            key, qty = entry
            if not isinstance(key, str) or not _is_count(qty) or qty <= 0:
                return INVALID_REQUEST
    a, b = req.initiator_offer, req.target_offer
    if a.gold == 0 and b.gold == 0 and not a.items and not b.items:
        return INVALID_REQUEST
    return None


def fingerprint(req: TradeRequest) -> tuple:
    """Same fingerprint means same trade, no matter how the items were listed."""
    return (
        req.initiator,
        req.target,
        req.initiator_offer.gold,
        tuple(sorted(totals(req.initiator_offer).items())),
        req.target_offer.gold,
        tuple(sorted(totals(req.target_offer).items())),
    )


def check_offer(inv: Inventory, offer: TradeOffer) -> str | None:
    if inv.gold < offer.gold:
        return INSUFFICIENT_GOLD
    for key, qty in totals(offer).items():
        if inv.items.get(key, 0) < qty:
            return INSUFFICIENT_ITEMS
    return None


def apply_offer(giver: Inventory, receiver: Inventory, offer: TradeOffer) -> None:
    giver.gold -= offer.gold
    receiver.gold += offer.gold
    for key, qty in totals(offer).items():
        left = giver.items[key] - qty
        if left > 0:
            giver.items[key] = left
        else:
            del giver.items[key]
        receiver.items[key] = receiver.items.get(key, 0) + qty
