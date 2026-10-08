"""Remembers results we already handed out so a replayed request is cheap."""

from .models import TradeResult


class ReceiptCache:
    def __init__(self) -> None:
        self._results: dict[str, TradeResult] = {}

    def get(self, request_id: str) -> TradeResult | None:
        return self._results.get(request_id)

    def remember(self, request_id: str, result: TradeResult) -> None:
        self._results[request_id] = result
