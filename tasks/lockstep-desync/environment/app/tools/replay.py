"""Replay a recorded match and print the state hash every 50 ticks.

    python tools/replay.py scenarios/demo.json
    python tools/replay.py scenarios/demo.json --shuffle 7

--shuffle scrambles the order commands get submitted in, like packets
showing up out of order. Two runs should print the same hashes.
"""

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lockstep import World  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--shuffle", type=int, default=None)
    args = ap.parse_args()

    with open(args.scenario) as f:
        scn = json.load(f)

    w = World(scn["seed"], scn["players"])
    by_tick = {}
    for c in scn["commands"]:
        by_tick.setdefault(c["tick"], []).append(c)
    if args.shuffle is not None:
        r = random.Random(args.shuffle)
        for lst in by_tick.values():
            r.shuffle(lst)

    for t in range(scn["ticks"]):
        for c in by_tick.get(t, []):
            w.submit(c)
        w.step()
        if (t + 1) % 50 == 0:
            print(f"tick {t + 1:4d}  {w.state_hash()}")
    print(f"units alive: {len(w.snapshot()['units'])}")


if __name__ == "__main__":
    main()
