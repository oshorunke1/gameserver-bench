"""Reference party matchmaker.

Usage: python3 matcher.py <queue.json> <matches.json>

How it works, roughly. Each match is picked by a bounded branch and bound
search over the parties that can play in one region, sorted by wait so the
long waiters get looked at first. A few different seed orders build full
solutions, then every match gets re-solved against the leftover pool and
whole regions get torn down and rebuilt to squeeze in extra matches. It is
fully deterministic, no clocks involved, so the verifier can rerun it and
get the same score every time.
"""

import json
import random
import sys

TEAM = 6
WAIT_CAP = 1200
GAP_PENALTY = 2.0
POOL_LIMIT = 40
NODE_LIMIT = 2500


class Party:
    __slots__ = ("idx", "pid", "size", "sum", "lo", "hi", "pv", "value",
                 "regions", "players", "conflicts")


def load(queue):
    now = queue["snapshot_time"]
    parties = []
    owner = {}
    for n, raw in enumerate(queue["parties"]):
        p = Party()
        p.idx = n
        p.pid = raw["party_id"]
        skills = [m["skill"] for m in raw["members"]]
        p.size = len(skills)
        p.sum = sum(skills)
        p.lo = min(skills)
        p.hi = max(skills)
        wait = min(max(now - raw["enqueued_at"], 0), WAIT_CAP)
        p.pv = 100.0 + wait / 10.0
        p.value = p.pv * p.size
        p.regions = list(raw["regions"])
        p.players = frozenset(m["player_id"] for m in raw["members"])
        p.conflicts = []
        parties.append(p)
        for pl in p.players:
            owner.setdefault(pl, []).append(n)
    for group in owner.values():
        for a in group:
            for b in group:
                if a != b and b not in parties[a].conflicts:
                    parties[a].conflicts.append(b)
    return parties


class State:
    def __init__(self, parties, max_gap):
        self.parties = parties
        self.max_gap = max_gap
        self.assigned = [False] * len(parties)
        self.blocked = [0] * len(parties)
        self.matches = []  # (region, team_a idx list, team_b idx list, obj)
        self.regions = sorted({r for p in parties for r in p.regions})
        self.by_region = {r: [p for p in parties if r in p.regions] for r in self.regions}
        for r in self.regions:
            self.by_region[r].sort(key=lambda p: (-p.pv, -p.size, p.idx))

    def usable(self, i):
        return not self.assigned[i] and self.blocked[i] == 0

    def _take(self, i, delta):
        self.assigned[i] = delta > 0
        for j in self.parties[i].conflicts:
            self.blocked[j] += delta

    def add(self, match):
        for i in match[1] + match[2]:
            self._take(i, 1)
        self.matches.append(match)

    def remove(self, match):
        for i in match[1] + match[2]:
            self._take(i, -1)
        self.matches.remove(match)

    def score(self):
        return sum(m[3] for m in self.matches)

    def pool(self, region, exclude=None):
        out = []
        for p in self.by_region[region]:
            if p.idx != exclude and self.usable(p.idx):
                out.append(p)
                if len(out) >= POOL_LIMIT:
                    break
        return out

    def best_match(self, region, pool, seed=None, floor=float("-inf")):
        """Branch and bound for the best single match from pool.

        Returns (obj, team_a, team_b) or None if nothing beats floor.
        """
        cands = pool
        m = len(cands)
        lim = 6 * self.max_gap
        suf_lo = [10 ** 9] * (m + 1)
        suf_hi = [-10 ** 9] * (m + 1)
        for k in range(m - 1, -1, -1):
            suf_lo[k] = min(suf_lo[k + 1], cands[k].lo)
            suf_hi[k] = max(suf_hi[k + 1], cands[k].hi)
        best = [floor, None, None]
        nodes = [0]
        team_a = []
        team_b = []
        chosen = set()

        def go(k, na, nb, sa, sb, val):
            nodes[0] += 1
            if nodes[0] > NODE_LIMIT:
                return
            if na == TEAM and nb == TEAM:
                gap = abs(sa - sb)
                if gap <= lim:
                    obj = val - GAP_PENALTY * gap / TEAM
                    if obj > best[0]:
                        best[0] = obj
                        best[1] = list(team_a)
                        best[2] = list(team_b)
                return
            if k >= m:
                return
            rem = 2 * TEAM - na - nb
            if val + rem * cands[k].pv <= best[0]:
                return
            ra = TEAM - na
            rb = TEAM - nb
            lo = (sa + ra * suf_lo[k]) - (sb + rb * suf_hi[k])
            hi = (sa + ra * suf_hi[k]) - (sb + rb * suf_lo[k])
            if lo > lim or hi < -lim:
                return
            c = cands[k]
            if chosen.isdisjoint(c.players):
                if na + c.size <= TEAM:
                    team_a.append(c.idx)
                    chosen.update(c.players)
                    go(k + 1, na + c.size, nb, sa + c.sum, sb, val + c.value)
                    chosen.difference_update(c.players)
                    team_a.pop()
                if nb + c.size <= TEAM and not (na == 0 and nb == 0):
                    team_b.append(c.idx)
                    chosen.update(c.players)
                    go(k + 1, na, nb + c.size, sa, sb + c.sum, val + c.value)
                    chosen.difference_update(c.players)
                    team_b.pop()
            go(k + 1, na, nb, sa, sb, val)

        if seed is not None:
            s = self.parties[seed]
            team_a.append(seed)
            chosen.update(s.players)
            go(0, s.size, 0, s.sum, 0, s.value)
        else:
            go(0, 0, 0, 0, 0, 0.0)
        if best[1] is None:
            return None
        return best[0], best[1], best[2]

    def seed_match(self, seed, regions=None):
        p = self.parties[seed]
        found = None
        for r in p.regions:
            if regions is not None and r not in regions:
                continue
            res = self.best_match(r, self.pool(r, exclude=seed), seed=seed,
                                  floor=found[0] if found else float("-inf"))
            if res is not None:
                found = (res[0], r, res[1], res[2])
        if found:
            self.add((found[1], found[2], found[3], found[0]))
            return True
        return False

    def construct(self, order, regions=None):
        for i in order:
            if self.usable(i):
                self.seed_match(i, regions)

    def snapshot(self):
        return list(self.matches)

    def restore(self, snap):
        for m in list(self.matches):
            self.remove(m)
        for m in snap:
            self.add(m)


def orders(parties, rng, extra):
    n = len(parties)
    idx = list(range(n))
    out = [
        sorted(idx, key=lambda i: (-parties[i].pv, -parties[i].size, i)),
        sorted(idx, key=lambda i: (-parties[i].size, -parties[i].pv, i)),
        sorted(idx, key=lambda i: (len(parties[i].regions), -parties[i].pv, i)),
    ]
    for _ in range(extra):
        noisy = {i: parties[i].pv + rng.uniform(0, 60) + 8 * parties[i].size for i in idx}
        out.append(sorted(idx, key=lambda i: (-noisy[i], i)))
    return out


def improve(state, rng):
    parties = state.parties
    for _ in range(3):
        before = state.score()
        # re-solve each match against the free pool, keep only real gains
        for match in list(state.matches):
            if match not in state.matches:
                continue
            state.remove(match)
            members = match[1] + match[2]
            regions = sorted({r for i in members for r in parties[i].regions})
            found = None
            floor = match[3] + 1e-6
            for r in regions:
                res = state.best_match(r, state.pool(r), floor=found[0] if found else floor)
                if res is not None:
                    found = (res[0], r, res[1], res[2])
            if found:
                state.add((found[1], found[2], found[3], found[0]))
            else:
                state.add(match)
        # leftovers might fit together now
        state.construct(sorted(range(len(parties)), key=lambda i: (-parties[i].pv, i)))
        # tear down one region at a time and rebuild it with a few orders
        for r in state.regions:
            for variant in range(3):
                snap = state.snapshot()
                old = state.score()
                for m in list(state.matches):
                    if m[0] == r:
                        state.remove(m)
                free = [p.idx for p in state.by_region[r] if state.usable(p.idx)]
                if variant == 0:
                    free.sort(key=lambda i: (-parties[i].size, -parties[i].pv, i))
                elif variant == 1:
                    free.sort(key=lambda i: (len(parties[i].regions), -parties[i].pv, i))
                else:
                    rng.shuffle(free)
                state.construct(free, regions={r})
                state.construct(sorted(range(len(parties)), key=lambda i: (-parties[i].pv, i)))
                if state.score() <= old + 1e-6:
                    state.restore(snap)
        if state.score() <= before + 1e-6:
            break


def solve(queue):
    parties = load(queue)
    rng = random.Random(20240611)
    best_snap = None
    best_score = float("-inf")
    state = State(parties, queue["max_skill_gap"])
    for order in orders(parties, rng, extra=2):
        state.restore([])
        state.construct(order)
        improve(state, rng)
        if state.score() > best_score + 1e-9:
            best_score = state.score()
            best_snap = state.snapshot()
    matches = []
    for region, team_a, team_b, _ in best_snap or []:
        matches.append({
            "region": region,
            "team_a": [parties[i].pid for i in team_a],
            "team_b": [parties[i].pid for i in team_b],
        })
    return {"matches": matches}


def main():
    with open(sys.argv[1]) as f:
        queue = json.load(f)
    result = solve(queue)
    with open(sys.argv[2], "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
