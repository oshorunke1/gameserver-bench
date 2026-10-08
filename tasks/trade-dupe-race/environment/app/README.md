# tradesvc

Player to player trading for the live game. Each game server runs its own
`TradeService`, and every server talks to the same inventory store. When both
players press accept, the server calls:

```python
result = await service.execute_trade(request)   # TradeRequest -> TradeResult
```

Clients retry on timeouts and servers retry on handoff, so the same
`request_id` can reach any server, any number of times, even at the same time.

## Layout

- `tradesvc/models.py` data shapes, status and reason codes
- `tradesvc/errors.py` exceptions the store raises
- `tradesvc/store.py` in-memory store used in dev and tests
- `tradesvc/validation.py` offer checks and the item moves
- `tradesvc/receipts.py` per process result cache
- `tradesvc/service.py` the `TradeService` entry point
- `tests/` a few example tests (`pytest /app/tests`)

## Store contract

Prod swaps in a different store, so the service may only rely on this:

- `await get_inventory(player_id) -> (Inventory, version)` returns a private
  copy plus the row's current version. Raises `UnknownPlayer` for a missing row.
- `await get_receipt(receipt_id) -> object | None` returns whatever was stored
  under that id by an earlier commit, or None.
- `await commit(writes, receipt_id=None, receipt=None)` where `writes` maps
  player id to `(Inventory, expected_version)`. All or nothing. Raises
  `DuplicateReceipt` if `receipt_id` is already taken, otherwise
  `VersionConflict` if any row's version isn't `expected_version` (None skips
  that check). Every successful write bumps the row's version.
- Any call can raise `StoreUnavailable`. When it does, nothing was written.
- Every call awaits, so other coroutines run in between calls.

## Trade rules

1. Each side's offer is some gold plus a list of `(item_key, qty)` pairs. The
   same key may appear more than once in one offer, and that means the sum.
2. Rejected with `invalid_request`: initiator and target are the same player,
   any gold or qty is negative, any qty is zero, or both offers are completely
   empty.
3. Rejected with `unknown_player` if either player has no inventory row.
4. Rejected with `insufficient_gold` or `insufficient_items` if a side can't
   cover its whole offer.
5. After the trade a stack that hits zero is removed from `items`. Rejected
   with `inventory_full` if either player would end up holding more than
   `slot_limit` distinct item keys.
6. A completed trade moves everything both ways at once. Both inventories
   change together or neither does, no matter how many trades run at once or
   how many servers are involved.
7. A `request_id` is applied at most once, ever, across all servers. Calling
   again with the same request (same players and same offers once duplicate
   keys are summed, item order doesn't matter) after it completed returns
   `completed` again and changes nothing. Calling with an id that already
   completed but a different request returns `rejected` /
   `request_id_reused`. Rejected and failed calls aren't remembered, so the
   same id can be retried later and is judged fresh.
8. Store write races are our problem, not the player's. A version conflict is
   never reported to the caller; the trade is re-checked against fresh data
   and either completes or gets a normal rejection.
9. `StoreUnavailable` from any store call gives `failed` /
   `store_unavailable` and the trade isn't applied.

When more than one rejection applies, any of the matching codes is fine.
