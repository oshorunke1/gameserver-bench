"""Plain data shapes shared by the store and the trade service."""

from dataclasses import dataclass, field

COMPLETED = "completed"
REJECTED = "rejected"
FAILED = "failed"

INVALID_REQUEST = "invalid_request"
UNKNOWN_PLAYER = "unknown_player"
INSUFFICIENT_GOLD = "insufficient_gold"
INSUFFICIENT_ITEMS = "insufficient_items"
INVENTORY_FULL = "inventory_full"
REQUEST_ID_REUSED = "request_id_reused"
STORE_UNAVAILABLE = "store_unavailable"

DEFAULT_SLOT_LIMIT = 30


@dataclass
class Inventory:
    gold: int = 0
    # item key -> how many the player holds in that stack
    items: dict[str, int] = field(default_factory=dict)

    def copy(self) -> "Inventory":
        return Inventory(self.gold, dict(self.items))


@dataclass(frozen=True)
class TradeOffer:
    """What one side puts in the trade window."""

    gold: int = 0
    # list of (item key, quantity) pairs, the client can send the same key twice
    items: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class TradeRequest:
    request_id: str
    initiator: str
    target: str
    initiator_offer: TradeOffer
    target_offer: TradeOffer


@dataclass(frozen=True)
class TradeResult:
    request_id: str
    status: str
    reason: str | None = None
