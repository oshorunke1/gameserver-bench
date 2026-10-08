# Trade dupe exploit

Live ops ticket: players are duplicating items and gold through the trade
window. Reports mention spamming accept, trading the same rare item to two
friends at once, and odd offers that show the same stack twice. We run one
`TradeService` per game server and every server shares one inventory store,
so whatever the fix is has to hold across servers, not just inside one
process.

The service lives in `/app/tradesvc`. Read `/app/README.md` first. Its
"Store contract" and "Trade rules" sections are the spec for this ticket and
everything in them is required behaviour.

Fix the service so that every rule in the README holds when many trades run
at the same time across several `TradeService` instances that share one
store, including when the same request arrives on several servers at once and
when store calls fail.

What we'll check:

- `TradeService(store, slot_limit=...)` and `await
  service.execute_trade(request)` keep their current signatures, and the
  result is a `TradeResult` with the request's `request_id`, a `status` of
  `completed`, `rejected` or `failed`, and a `reason` (None when completed)
  using the codes in `tradesvc/models.py`.
- Your code is run against a different store implementation that follows the
  README contract exactly, with arbitrary awaits between calls and calls that
  sometimes raise `StoreUnavailable`. Only use the documented store methods
  and don't rely on anything specific to `InMemoryStore`.
- Every row the store ever holds is valid: no negative gold, no zero or
  negative stacks, no player above the slot limit.
- The final stored state equals the starting state plus exactly one
  application of every trade that returned `completed`, and nothing else.
- Keep the class, function and exception names in `models.py`, `errors.py`
  and `service.py` importable as they are now.

You can change anything else inside `/app/tradesvc`. The example tests in
`/app/tests` should keep passing. The data our checks use is different from
anything in the repo.
