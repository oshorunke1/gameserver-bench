"""One simulated peer. Runs a scenario against /app's sim with a messy
command delivery order and writes its hashes and final snapshot out.

usage: python peer.py scenario.json out.json shuffle_seed warmup(0|1)
"""

import json
import random
import sys

sys.path.insert(0, "/app")

from lockstep import World  # noqa: E402


def run(scn, shuffle_seed):
    r = random.Random(shuffle_seed)
    players = list(scn["players"])
    r.shuffle(players)
    w = World(scn["seed"], players)
    # each command shows up somewhere from 0 to 3 ticks early, in a scrambled order
    by_tick = {}
    for c in scn["commands"]:
        at = max(0, c["tick"] - r.randint(0, 3))
        by_tick.setdefault(at, []).append(dict(c))
    for lst in by_tick.values():
        r.shuffle(lst)
    hashes = []
    for t in range(scn["ticks"]):
        for c in by_tick.get(t, []):
            w.submit(c)
        w.step()
        if (t + 1) % 10 == 0:
            hashes.append(w.state_hash())
    return hashes, w.snapshot()


def main():
    scn_path, out_path, shuffle_seed, warmup = sys.argv[1:5]
    shuffle_seed = int(shuffle_seed)
    with open(scn_path) as f:
        data = json.load(f)
    # poke the global rng so nothing can lean on its state
    random.seed(shuffle_seed * 7919 + 13)
    if warmup == "1":
        # another match in the same process first, like a server hosting back to back games
        run(data["warmup"], shuffle_seed + 1)
        random.random()
    hashes, snap = run(data["main"], shuffle_seed)
    # and the same match again in this process, should be identical
    again, snap2 = run(data["main"], shuffle_seed + 2)
    with open(out_path, "w") as f:
        json.dump({"hashes": hashes, "snapshot": snap, "again": again, "snapshot2": snap2}, f)


if __name__ == "__main__":
    main()
