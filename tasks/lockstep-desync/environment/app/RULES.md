# Skirmish lockstep rules

This is the design doc for the sim in `lockstep/`. Balance numbers live in `lockstep/rules.py`. Formulas not spelled out here are whatever `lockstep/world.py` does today.

## Setup
- `World(seed, players)` makes a world. `players` is a list of player name strings, 2 to 4 of them.
- Every random number the sim uses comes from `world.rng`, a `lockstep.rng.Rng` seeded with `seed`.
- Players are ranked by plain Python string sort of their names. Rank i gets base `BASES[i]` and every "in player order" loop below uses this ranking.
- Each player starts with `START_GOLD`. The shared gold mine starts at `MINE_START`.
- Unit ids start at 1 in every world and go up by 1 for each unit spawned. Ids are never reused.

## Commands
A command is a dict with `tick`, `player`, `seq`, `type` and type specific fields. `world.submit(cmd)` can be called any time before that tick runs, in any order. Commands for a tick that already ran are dropped.

`world.step()` runs tick number `world.tick`, then adds 1 to `world.tick`. A tick has four phases, in this order.

### 1. Commands
Commands for this tick run sorted by `(player, seq)`, no matter what order they arrived in. Bad commands (unknown player or type, unit not alive or not yours) do nothing.
- `spawn` (`kind`): if the player has the gold and fewer than `POP_CAP` live units, pay the cost and make the unit at base plus jitter. Jitter draws two rng numbers, x first then y, each mapped to `(r * 2 - 1) * SPAWN_JITTER`. Position is clamped to the map.
- `move` (`unit`, `x`, `y`): set the destination (clamped), clear the attack target.
- `attack` (`unit`, `target`): target must be a live enemy unit. Sets the attack target, clears the destination.
- `stop` (`unit`): clears both.

### 2. Income
In player order, each player takes `min(INCOME_PER_TICK, mine)` gold out of the mine.

### 3. Movement
Units go in ascending id order. A unit with an attack target walks toward it until it is within range. Otherwise a unit with a destination walks toward it at its speed and snaps onto it once within one step.

### 4. Combat
Units go in ascending id order. A unit can swing when the current tick number is at least its `ready` tick. Its target is its attack target if that is in range, or, with no attack target, the nearest enemy in range (ties go to the lowest id). Every swing draws exactly one rng number for the crit roll, so it crits when that number is below `CRIT_CHANCE`. After a swing, `ready = tick + cooldown`. Cooldowns are counted in ticks only.

Damage is `damage * (1 - FALLOFF_PER_TILE * distance)`, times `CRIT_MULT` on a crit. All swings land at the same time: each target's hits are added one at a time into a running total that starts at 0.0, in ascending attacker id, and that total comes off its hp. Then units at 0 hp or less die and anyone targeting them loses that target.

## State hash
`world.snapshot()` returns the documented state dict (tick, mine, gold, units sorted by id). `world.state_hash()` is the sha256 hex digest of `json.dumps(snapshot, sort_keys=True, separators=(",", ":"))`. Peers trade this hash to catch desyncs.
