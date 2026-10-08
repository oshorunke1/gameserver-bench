# Lockstep peers desync

Our skirmish mode uses deterministic lockstep. Every peer runs the sim in `/app/lockstep/` on the same command stream and peers trade `state_hash()` values to check they agree. In live matches the hashes drift apart, sometimes on the first tick, sometimes deep into a fight, and players get kicked with a desync error.

Your job is to make the sim fully deterministic. Two peers that build `World(seed, players)` with the same seed and the same set of players, and get the same commands, must report identical `snapshot()` and `state_hash()` values after every `step()`. That has to hold when:

- the peers are separate Python processes with different `PYTHONHASHSEED` values
- the `players` list is passed in a different order
- commands are `submit()`ted in a different order, and some arrive a few ticks before the tick they are for
- the process already ran other matches before this one, or runs the same match twice
- the machine is slow, fast, or busy

The gameplay rules are written down in `/app/RULES.md`, with balance numbers in `/app/lockstep/rules.py`. Where the code disagrees with `RULES.md`, the doc is right. Do not change gameplay: unit stats, costs, damage, income, spawn rules, targeting, crits and the state hash format all have to behave exactly as documented. Turning off features, freezing units or making the hash ignore state will fail grading.

Keep the public API the same: `from lockstep import World`, then `World(seed, players)`, `submit(cmd)`, `step()`, `snapshot()`, `state_hash()`, and the `tick` attribute. Keep `rules.py`, `rng.py` and `hashing.py` as they are.

`/app/scenarios/demo.json` is a recorded match and `python /app/tools/replay.py scenarios/demo.json [--shuffle N]` (run from `/app`) replays it and prints hashes, handy for comparing runs.

Grading runs unseen matches on several separate peer processes and checks that every peer agrees with every other one and with the documented rules, tick by tick.
