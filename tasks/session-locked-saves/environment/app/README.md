# savesys

Player save data for our game servers. Every running server process makes
one `SessionStore` and uses it to load a player when they join, save them
on autosave ticks, and release them when they leave or hop servers.

## Layout

- `savesys/datastore.py` the key-value store (conditional writes, versions, failures). Read its docstring.
- `savesys/clock.py` the simulated clock every server shares.
- `savesys/errors.py` `SessionLocked`, `LeaseLost`, `SaveFailed`.
- `savesys/defaults.py` starting data for a brand new player.
- `savesys/session.py` `SessionStore`, the thing that needs work.
- `savesys/server_sim.py` a small server loop showing how game code calls it.
- `tests/` a few example tests. Run them with `cd /app && pytest tests`.

`datastore.py`, `clock.py`, `errors.py` and `defaults.py` are shared with
other teams and must not change.

## SessionStore contract

`SessionStore(store, clock, server_id, lease_seconds=30.0)`. One instance is
one running server process. A server that crashes and restarts makes a new
instance with the same `server_id`.

A player's session is held by at most one instance at a time. Holding it
comes with a lease that ends at `expires_at`. A lease is expired once
`clock.now() >= expires_at`.

`load(player_id) -> dict` takes the session and returns the player's saved
data, or `default_player_data()` if they have never been saved.
- If the session is held by an instance with a different `server_id` and its
  lease has not expired, raise `SessionLocked(player_id, owner, expires_at)`
  with that holder's `server_id` and lease end, and change nothing.
- An expired lease can be taken. A session held by another instance with the
  same `server_id` is taken right away (that instance crashed). Loading a
  player this instance already holds just refreshes the lease.
- On success this instance holds the session with `expires_at = now + lease_seconds`.

`save(player_id, data) -> None` stores `data` and sets `expires_at = now + lease_seconds`.

`renew(player_id) -> float` sets `expires_at = now + lease_seconds` and returns it.

`release(player_id, data) -> None` stores `data` and frees the session in a
single write. Any server can load the player straight after. This instance
no longer holds it.

An instance holds a session from its successful `load` until it releases it
or any other `load` (from any instance) takes the session. An expired lease
that nobody has taken is still held. `save`, `renew` and `release` on a
session this instance does not hold raise `LeaseLost(player_id)` and change
nothing.

Other servers can act between any read and write you make, so never
overwrite a session or save that is not yours.

## Store failures

`DataStoreUnavailable` means the write did not happen. `WriteTimeout` means it
may have happened, and the call must work out which. A write that really did
land counts as success. Once a single public call has had 5 writes that did
not land, it raises `SaveFailed(player_id)`, and the store and this
instance's sessions stay exactly as they were before that call.

How the record is laid out in the store is up to you. Only `SessionStore`
reads it.
