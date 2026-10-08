"""Checks and moves for one side of a trade."""

from .models import INSUFFICIENT_GOLD, INSUFFICIENT_ITEMS, Inventory, TradeOffer


def check_offer(inv: Inventory, offer: TradeOffer) -> str | None:
    """Return a reject reason if the player can't cover their offer."""
    if inv.gold < offer.gold:
        return INSUFFICIENT_GOLD
    for key, qty in offer.items:
        if inv.items.get(key, 0) < qty:
            return INSUFFICIENT_ITEMS
    return None


def fits(inv: Inventory, incoming: TradeOffer, slot_limit: int) -> bool:
    """Make sure the player has room for what they're getting."""
    return len(inv.items) + len(incoming.items) <= slot_limit


def apply_offer(giver: Inventory, receiver: Inventory, offer: TradeOffer) -> None:
    giver.gold -= offer.gold
    receiver.gold += offer.gold
    for key, qty in offer.items:
        left = giver.items.get(key, 0) - qty
        if left > 0:
            giver.items[key] = left
        else:
            # stack is used up so drop the key
            giver.items.pop(key, None)
        receiver.items[key] = receiver.items.get(key, 0) + qty
