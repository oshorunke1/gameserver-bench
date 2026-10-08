"""Sealed checks for the lockstep desync task.

Each hidden match runs on four separate peer processes with different
PYTHONHASHSEED values, scrambled command delivery and different process
histories. Every peer has to produce the same hashes, and those hashes and
the final state have to match a clean reference build of the documented rules.
"""

import functools
import json
import os
import random
import subprocess
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from refsim import World as RefWorld  # noqa: E402

NAMES = ["Vex", "amber", "Kiro", "nyx", "Bolt", "zara", "Orin", "milo", "Quill", "dax", "Ash", "bea"]
KINDS = ["soldier", "archer", "knight"]
SEEDS = [918273, 44021, 770331, 5150, 271828, 60606, 314159, 8675309]
TICKS = 600


def make_scenario(seed, ticks):
    # scripted "players" that look at the reference world so their orders
    # point at real units and they actually brawl and focus fire
    r = random.Random(seed)
    players = r.sample(NAMES, r.choice([2, 3, 3, 4, 4]))
    sim_seed = r.randrange(1 << 62)
    w = RefWorld(sim_seed, list(players))
    commands = []
    rally = {}
    for t in range(ticks):
        if t % 80 == 0:
            for p in players:
                rally[p] = (32 + r.uniform(-6, 6), 32 + r.uniform(-6, 6))
        batch = []
        for p in players:
            seq = r.randint(0, 5)
            own = [u.id for u in w.units.values() if u.owner == p]
            foes = [u.id for u in w.units.values() if u.owner != p]
            hi = max(1, w.next_id)

            def add(**kw):
                nonlocal seq
                c = {"tick": t, "player": p, "seq": seq}
                c.update(kw)
                batch.append(c)
                seq += r.randint(1, 3)

            if r.random() < 0.15:
                add(type="spawn", kind=r.choice(KINDS))
            if r.random() < 0.3:
                uid = r.choice(own) if own and r.random() < 0.9 else r.randint(1, hi)
                rx, ry = rally[p]
                add(type="move", unit=uid, x=round(rx + r.uniform(-3, 3), 3), y=round(ry + r.uniform(-3, 3), 3))
            if own and foes and r.random() < 0.12:
                target = r.choice(foes)
                for uid in r.sample(own, min(len(own), r.randint(2, 5))):
                    add(type="attack", unit=uid, target=target)
            if r.random() < 0.05:
                add(type="attack", unit=r.randint(1, hi), target=r.randint(1, hi))
            if r.random() < 0.02:
                add(type="stop", unit=r.choice(own) if own else 1)
            if r.random() < 0.01:
                add(type="dance", unit=r.randint(1, hi))
        if r.random() < 0.01:
            batch.append({"tick": t, "player": "ghost", "seq": 0, "type": "spawn", "kind": "knight"})
        for c in batch:
            w.submit(c)
        w.step()
        commands.extend(batch)
    return {"seed": sim_seed, "players": players, "ticks": ticks, "commands": commands}


def reference(scn):
    w = RefWorld(scn["seed"], list(scn["players"]))
    by_tick = {}
    for c in scn["commands"]:
        by_tick.setdefault(c["tick"], []).append(c)
    hashes = []
    for t in range(scn["ticks"]):
        for c in by_tick.get(t, []):
            w.submit(c)
        w.step()
        if (t + 1) % 10 == 0:
            hashes.append(w.state_hash())
    return hashes, json.loads(json.dumps(w.snapshot()))


# (PYTHONHASHSEED, shuffle seed, run a warmup match first)
PEERS = [("0", 101, "0"), ("1", 202, "1"), ("4242", 303, "1"), ("random", 404, "0")]


@functools.lru_cache(maxsize=None)
def run_peers(idx):
    seed = SEEDS[idx]
    data = {"main": make_scenario(seed, TICKS), "warmup": make_scenario(seed + 1, 120)}
    tmp = tempfile.mkdtemp(prefix="lockstep_")
    scn_path = os.path.join(tmp, "scenario.json")
    with open(scn_path, "w") as f:
        json.dump(data, f)
    procs = []
    for i, (hs, shuffle, warm) in enumerate(PEERS):
        out = os.path.join(tmp, f"peer{i}.json")
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = hs
        p = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "peer.py"), scn_path, out, str(shuffle + idx), warm],
            cwd=tmp, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        procs.append((p, out))
    results = []
    for p, out in procs:
        try:
            _, err = p.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            p.kill()
            pytest.fail("peer timed out")
        assert p.returncode == 0, f"peer crashed:\n{err[-3000:]}"
        with open(out) as f:
            results.append(json.load(f))
    return data["main"], results


@pytest.mark.parametrize("idx", range(len(SEEDS)))
def test_peers_stay_in_sync(idx):
    _, results = run_peers(idx)
    base = results[0]["hashes"]
    assert len(base) == TICKS // 10
    for i, res in enumerate(results):
        assert res["hashes"] == base, f"peer {i} desynced from peer 0"
        assert res["again"] == base, f"peer {i} gave different hashes on a rerun in the same process"


@pytest.mark.parametrize("idx", range(len(SEEDS)))
def test_matches_documented_rules(idx):
    scn, results = run_peers(idx)
    ref_hashes, ref_snap = reference(scn)
    for i, res in enumerate(results):
        assert res["snapshot"] == ref_snap, f"peer {i} final state does not follow the documented rules"
        assert res["snapshot2"] == ref_snap
        assert res["hashes"] == ref_hashes, f"peer {i} state hashes do not match the documented hash"
