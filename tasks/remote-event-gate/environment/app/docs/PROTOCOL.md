# Remote event protocol

Clients fire remote events. The transport decodes each one into a Python value
and calls `Server.dispatch(player_id, event, payload)`. `player_id` comes from
the connection. `event` and `payload` come from the client and can be anything
a decoder could hand you: `dict`, `list`, `str`, `bytes`, `int` (any size),
`float` (including NaN and infinities), `bool`, `None`, nested in any shape,
including containers that contain themselves and nesting tens of thousands of
levels deep. Dict keys are not guaranteed to be strings.

An event is **accepted** only when every rule below holds. Otherwise it is
**rejected**: `dispatch` returns `{"ok": False, ...}` and the world is left
exactly as it was. Accepted events run their handler and return `{"ok": True, ...}`.

## General rules

- The sender must exist in `world.players` and be `online`.
- `event` must be one of `purchase`, `equip`, `chat`, `move`, `trade_offer`.
- `payload` must be a `dict` whose keys are exactly the schema's field names.
  Missing required fields and any extra key reject the event. Fields marked
  `optional` may be left out.

## Field types (see `gameserver/schemas/*.json`)

- `int`: a Python `int` that is not a `bool`, within `min..max` inclusive.
  Floats are rejected even when they hold a whole number.
- `number`: an `int` (not `bool`) or a finite `float`, within `min..max` inclusive.
- `string`: a `str` whose length in code points is within `min_len..max_len`.
  With `printable`, it may not contain any character whose Unicode category is
  `Cc` (control) or `Cs` (surrogate, what undecodable bytes turn into), and
  `text.strip()` must not be empty.
- `enum`: a `str` equal to one of `values`.
- `id`: a `str` that fully matches `[a-z][a-z0-9_]{0,31}` (ASCII only, no
  trailing newline). `ref: catalog` means it must be a key of the catalog.
  `ref: owned` means the sender's inventory count for it is at least 1.
- `player_ref`: a `str` naming a player in `world.players` who is online and
  is not the sender.
- `list`: a `list` with `min_items..max_items` entries, each matching `item`.
  `unique_by` means no two entries share that field's value.
- `object`: a `dict` with exactly the listed fields, same rules as payloads.

## Event rules

- `purchase`: `price * qty` must be at most the sender's coins, and the
  sender's count of that item after buying must be at most 999.
- `equip`: the catalog `slot` of the item must equal the requested `slot`.
- `move`: the straight line distance (`math.hypot` of the three deltas) from
  the sender's current position to the new one must be at most `max_step`.
- `trade_offer`: `coins` (0 when left out) must be at most the sender's coins.
  For each entry, `qty` must be at most the sender's count of that item, minus
  one if that item is currently equipped in any slot.

## Rate limits

Each schema has `rate: {max, window}` per player per event. Read time only
from `server.clock.now()`. An event that passes every other rule is still
rejected if the same player already had `max` accepted events of the same
type at times `t` with `now - t < window`. Rejected events never count.
