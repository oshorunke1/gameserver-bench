"""Lockstep sim. Every peer runs this with the same inputs and has to land
on the exact same state, bit for bit.
"""

import math

from . import rules
from .hashing import hash_snapshot
from .rng import Rng


def _clamp(v):
    return max(0.0, min(rules.MAP_SIZE, v))


class Unit:
    __slots__ = ("id", "owner", "kind", "x", "y", "hp", "ready", "target", "dest")

    def __init__(self, uid, owner, kind, x, y):
        self.id = uid
        self.owner = owner
        self.kind = kind
        self.x = x
        self.y = y
        self.hp = rules.KINDS[kind]["hp"]
        self.ready = 0
        self.target = None
        self.dest = None


class World:
    def __init__(self, seed, players):
        self.rng = Rng(seed)
        self.tick = 0
        self.mine = rules.MINE_START
        names = sorted(players)
        self.gold = {n: rules.START_GOLD for n in names}
        self.bases = {n: rules.BASES[i] for i, n in enumerate(names)}
        # keyed by unit id, ids only go up so insertion order is id order
        self.units = {}
        self.next_id = 1
        self.inbox = []

    # network side

    def submit(self, cmd):
        self.inbox.append(dict(cmd))

    # one sim tick

    def step(self):
        now = self.tick
        due = [c for c in self.inbox if c.get("tick") == now]
        self.inbox = [c for c in self.inbox if isinstance(c.get("tick"), int) and c["tick"] > now]
        due.sort(key=lambda c: (str(c.get("player")), c.get("seq", 0)))
        for cmd in due:
            self._apply(cmd)
        self._income()
        self._move()
        self._combat(now)
        self.tick += 1

    def _own(self, player, uid):
        u = self.units.get(uid) if isinstance(uid, int) else None
        if u is None or u.owner != player:
            return None
        return u

    def _apply(self, cmd):
        player = cmd.get("player")
        if player not in self.gold:
            return
        kind = cmd.get("type")
        if kind == "spawn":
            self._spawn(player, cmd.get("kind"))
        elif kind == "move":
            u = self._own(player, cmd.get("unit"))
            if u is None:
                return
            u.dest = (_clamp(float(cmd["x"])), _clamp(float(cmd["y"])))
            u.target = None
        elif kind == "attack":
            u = self._own(player, cmd.get("unit"))
            tid = cmd.get("target")
            t = self.units.get(tid) if isinstance(tid, int) else None
            if u is None or t is None or t.owner == player:
                return
            u.target = t.id
            u.dest = None
        elif kind == "stop":
            u = self._own(player, cmd.get("unit"))
            if u is None:
                return
            u.target = None
            u.dest = None

    def _spawn(self, player, kind):
        spec = rules.KINDS.get(kind)
        if spec is None or self.gold[player] < spec["cost"]:
            return
        alive = sum(1 for u in self.units.values() if u.owner == player)
        if alive >= rules.POP_CAP:
            return
        self.gold[player] -= spec["cost"]
        bx, by = self.bases[player]
        jx = (self.rng.random() * 2.0 - 1.0) * rules.SPAWN_JITTER
        jy = (self.rng.random() * 2.0 - 1.0) * rules.SPAWN_JITTER
        u = Unit(self.next_id, player, kind, _clamp(bx + jx), _clamp(by + jy))
        self.next_id += 1
        self.units[u.id] = u

    def _income(self):
        for name in sorted(self.gold):
            take = min(rules.INCOME_PER_TICK, self.mine)
            self.mine -= take
            self.gold[name] += take

    def _move(self):
        for uid in sorted(self.units):
            u = self.units[uid]
            spec = rules.KINDS[u.kind]
            if u.target is not None:
                t = self.units[u.target]
                dx = t.x - u.x
                dy = t.y - u.y
                dist = math.hypot(dx, dy)
                if dist > spec["range"]:
                    step = min(spec["speed"], dist - spec["range"])
                    u.x = _clamp(u.x + dx / dist * step)
                    u.y = _clamp(u.y + dy / dist * step)
            elif u.dest is not None:
                dx = u.dest[0] - u.x
                dy = u.dest[1] - u.y
                dist = math.hypot(dx, dy)
                if dist <= spec["speed"]:
                    u.x, u.y = u.dest
                    u.dest = None
                else:
                    u.x = _clamp(u.x + dx / dist * spec["speed"])
                    u.y = _clamp(u.y + dy / dist * spec["speed"])

    def _combat(self, now):
        order = sorted(self.units)
        hits = {}
        for uid in order:
            u = self.units[uid]
            spec = rules.KINDS[u.kind]
            if now < u.ready:
                continue
            t = None
            if u.target is not None:
                cand = self.units[u.target]
                if math.hypot(cand.x - u.x, cand.y - u.y) <= spec["range"]:
                    t = cand
            else:
                best_d = None
                for oid in order:
                    o = self.units[oid]
                    if o.owner == u.owner:
                        continue
                    d = math.hypot(o.x - u.x, o.y - u.y)
                    if d <= spec["range"] and (best_d is None or d < best_d):
                        t = o
                        best_d = d
            if t is None:
                continue
            d = math.hypot(t.x - u.x, t.y - u.y)
            dmg = spec["damage"] * (1.0 - rules.FALLOFF_PER_TILE * d)
            if self.rng.random() < rules.CRIT_CHANCE:
                dmg *= rules.CRIT_MULT
            hits.setdefault(t.id, []).append(dmg)
            u.ready = now + spec["cooldown"]
        for tid in sorted(hits):
            total = 0.0
            for dmg in hits[tid]:
                total += dmg
            self.units[tid].hp -= total
        dead = [uid for uid in order if self.units[uid].hp <= 0.0]
        for uid in dead:
            del self.units[uid]
        if dead:
            gone = set(dead)
            for u in self.units.values():
                if u.target in gone:
                    u.target = None

    # what peers compare

    def snapshot(self):
        units = []
        for uid in sorted(self.units):
            u = self.units[uid]
            units.append({
                "id": u.id,
                "owner": u.owner,
                "kind": u.kind,
                "x": u.x,
                "y": u.y,
                "hp": u.hp,
                "ready": u.ready,
                "target": u.target,
                "dest": list(u.dest) if u.dest is not None else None,
            })
        return {"tick": self.tick, "mine": self.mine, "gold": dict(self.gold), "units": units}

    def state_hash(self):
        return hash_snapshot(self.snapshot())
