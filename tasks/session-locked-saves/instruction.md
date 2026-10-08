Players are losing progress when they hop between game servers. The save service in `/app/savesys/session.py` has no session locking, so two servers can both hold the same player, and a server that hangs or crashes can later write an old copy of a player's data over newer progress. Store hiccups make it worse: a write that times out may still have landed.

Rewrite `SessionStore` in `/app/savesys/session.py` so it meets the contract in `/app/README.md` (the "SessionStore contract" and "Store failures" sections). The contract is the source of truth. In short:

- `load` takes a lease-based session lock on a player and returns their data, or raises `SessionLocked` with the current holder and lease end while another server's lease is live.
- `save`, `renew` and `release` only work while this instance still holds the session, and raise `LeaseLost` otherwise without changing anything in the store.
- Expired leases can be taken over, a restarted process (same `server_id`) takes over its own players at once, and a stale holder can never overwrite a newer save.
- `WriteTimeout` is ambiguous and must be resolved. A call gives up with `SaveFailed` after 5 writes that did not land, leaving everything as it was.

Inputs: the store, the shared simulated clock, a `server_id` and `lease_seconds`, all passed to the constructor. Every time check uses `clock.now()`.

Rules:
- Keep the constructor signature and the four public methods with the signatures already in `session.py`, and keep raising the exceptions from `savesys/errors.py`.
- Talk to the store only through `get` and `put`. The record layout inside the store is up to you.
- Do not edit `datastore.py`, `clock.py`, `errors.py` or `defaults.py`. They are restored before grading.
- Standard library only.

Your code will be checked against many multi-server scenarios that are not in `/app/tests`, including races where another server acts between your reads and writes, crashes, restarts, lease expiry and injected store faults. `python -m savesys.server_sim` and `pytest /app/tests` are there to help you get started.
