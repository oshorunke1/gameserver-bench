# Harden the remote event gate

Exploiters have found our game server. `/app/gameserver` receives client remote
events (`purchase`, `equip`, `chat`, `move`, `trade_offer`) as already decoded
Python values through `Server.dispatch(player_id, event, payload)` and runs a
handler for each one. The gate in front of the handlers (`gate.py`, called from
`server.py`) was written for the alpha and lets far too much through. Hostile
payloads currently crash the server, mint coins, dupe items, and teleport
players, and the rate limiting can be dodged.

Your job is to make the gate enforce the protocol in
`/app/docs/PROTOCOL.md`, with the per event schemas in
`/app/gameserver/schemas/`. That document is the source of truth for what is
legal, including types, ranges, strings, ids, ownership, per event rules and
per player rate limits.

Requirements:

- `dispatch` must never raise, whatever `event` and `payload` are, and must
  always return a dict whose `"ok"` value is a `bool`.
- A rejected event (`"ok": False`) must leave the world exactly as it was.
- Every event that follows the protocol must be accepted (`"ok": True`) and
  have exactly the effect its handler gives it today.
- Rate limits use only `server.clock.now()`, never the wall clock.

Constraints:

- Keep the public interface as it is: `Server(world, catalog, clock)`,
  `Server.dispatch`, `ManualClock`, `World.add_player`, and the data layout of
  `World` and `Player` in `world.py`. Don't change what the handlers do to the
  world when an event is accepted.
- The catalog is whatever dict gets passed to `Server`, not necessarily the
  one in `gameserver/data/catalog.json`.
- Standard library only.

You'll be graded by driving `Server` directly with seeded streams of legit and
hostile events against worlds, players and catalogs you haven't seen. After
every event the grader checks for exceptions, the accept or reject decision,
and the full world state. One crash, one wrongly accepted event or one wrongly
rejected event fails the task. `/app/tests` has a few happy path examples.
