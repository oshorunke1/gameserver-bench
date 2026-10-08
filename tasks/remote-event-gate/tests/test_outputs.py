"""Sealed verifier for remote-event-gate.

Drives gameserver.server.Server with seeded streams of legit and hostile remote
events against worlds and catalogs that don't appear anywhere in /app. A small
reference model written straight from docs/PROTOCOL.md says what should be
accepted and what the world should look like afterwards. After every single
event we check: no exception, the right ok flag, and an identical world.
"""

import math
import random
import reprlib
import sys
import unicodedata

import pytest

sys.path.insert(0, "/app")
sys.setrecursionlimit(max(sys.getrecursionlimit(), 1000))

from gameserver.clock import ManualClock  # noqa: E402
from gameserver.server import Server  # noqa: E402
from gameserver.world import World  # noqa: E402

SLOTS = ("weapon", "armor", "pet")
RATES = {
    "purchase": (5, 1.0),
    "equip": (10, 1.0),
    "chat": (3, 2.0),
    "move": (20, 1.0),
    "trade_offer": (2, 10.0),
}
EVENTS = tuple(RATES)
BOUND = 4096
MAX_STEP = 64
ID_FIRST = set("abcdefghijklmnopqrstuvwxyz")
ID_REST = ID_FIRST | set("0123456789_")

SHORT = reprlib.Repr()
SHORT.maxlevel = 3
SHORT.maxstring = 60
SHORT.maxother = 60


# ---------------------------------------------------------------- reference

def is_int(v, lo, hi):
    return type(v) is int and lo <= v <= hi


def is_num(v, lo, hi):
    if type(v) is int:
        return lo <= v <= hi
    if type(v) is float:
        return math.isfinite(v) and lo <= v <= hi
    return False


def is_id(v):
    if type(v) is not str or not (1 <= len(v) <= 32):
        return False
    if v[0] not in ID_FIRST:
        return False
    return all(c in ID_REST for c in v[1:])


def is_text(v, lo, hi):
    if type(v) is not str or not (lo <= len(v) <= hi):
        return False
    for c in v:
        if unicodedata.category(c) in ("Cc", "Cs"):
            return False
    return v.strip() != ""


def has_keys(d, required, optional=()):
    if type(d) is not dict:
        return False
    allowed = set(required) | set(optional)
    for k in d:
        if type(k) is not str or k not in allowed:
            return False
    return all(k in d for k in required)


class Reference:
    def __init__(self, catalog, players):
        self.catalog = catalog
        self.players = {}
        for pid, spec in players.items():
            self.players[pid] = {
                "coins": spec["coins"],
                "inv": dict(spec["inventory"]),
                "eq": {s: spec["equipped"].get(s) for s in SLOTS},
                "pos": list(spec["pos"]),
                "online": spec["online"],
            }
        self.chat = []
        self.trades = []
        self.next_id = 1
        self.history = {}

    def owned(self, p, item):
        return p["inv"].get(item, 0) >= 1

    def valid(self, pid, ev, pl):
        p = self.players[pid]
        if ev == "purchase":
            if not has_keys(pl, ("item_id", "qty")):
                return False
            item, qty = pl["item_id"], pl["qty"]
            if not is_id(item) or item not in self.catalog or not is_int(qty, 1, 99):
                return False
            if self.catalog[item]["price"] * qty > p["coins"]:
                return False
            return p["inv"].get(item, 0) + qty <= 999
        if ev == "equip":
            if not has_keys(pl, ("slot", "item_id")):
                return False
            slot, item = pl["slot"], pl["item_id"]
            if type(slot) is not str or slot not in SLOTS:
                return False
            if not is_id(item) or not self.owned(p, item):
                return False
            return item in self.catalog and self.catalog[item]["slot"] == slot
        if ev == "chat":
            if not has_keys(pl, ("channel", "text")):
                return False
            ch = pl["channel"]
            if type(ch) is not str or ch not in ("global", "team"):
                return False
            return is_text(pl["text"], 1, 200)
        if ev == "move":
            if not has_keys(pl, ("x", "y", "z")):
                return False
            vals = [pl["x"], pl["y"], pl["z"]]
            if not all(is_num(v, -BOUND, BOUND) for v in vals):
                return False
            d = math.hypot(vals[0] - p["pos"][0], vals[1] - p["pos"][1], vals[2] - p["pos"][2])
            return d <= MAX_STEP
        if ev == "trade_offer":
            if not has_keys(pl, ("to", "items"), ("coins",)):
                return False
            to = pl["to"]
            if type(to) is not str or to == pid or to not in self.players:
                return False
            if not self.players[to]["online"]:
                return False
            coins = pl.get("coins", 0)
            if not is_int(coins, 0, 1_000_000) or coins > p["coins"]:
                return False
            items = pl["items"]
            if type(items) is not list or not (1 <= len(items) <= 8):
                return False
            seen = []
            equipped = [v for v in p["eq"].values() if v is not None]
            for e in items:
                if not has_keys(e, ("item_id", "qty")):
                    return False
                item, qty = e["item_id"], e["qty"]
                if not is_id(item) or not self.owned(p, item) or not is_int(qty, 1, 999):
                    return False
                if item in seen:
                    return False
                seen.append(item)
                have = p["inv"][item] - (1 if item in equipped else 0)
                if qty > have:
                    return False
            return True
        return False

    def verdict(self, pid, ev, pl, now):
        if type(pid) is not str or pid not in self.players or not self.players[pid]["online"]:
            return False
        if type(ev) is not str or ev not in RATES:
            return False
        if not self.valid(pid, ev, pl):
            return False
        cap, window = RATES[ev]
        recent = [t for t in self.history.get((pid, ev), []) if now - t < window]
        return len(recent) < cap

    def apply(self, pid, ev, pl, now):
        p = self.players[pid]
        self.history.setdefault((pid, ev), []).append(now)
        if ev == "purchase":
            p["coins"] -= self.catalog[pl["item_id"]]["price"] * pl["qty"]
            p["inv"][pl["item_id"]] = p["inv"].get(pl["item_id"], 0) + pl["qty"]
        elif ev == "equip":
            p["eq"][pl["slot"]] = pl["item_id"]
        elif ev == "chat":
            self.chat.append((pid, pl["channel"], pl["text"]))
        elif ev == "move":
            p["pos"] = [pl["x"], pl["y"], pl["z"]]
        elif ev == "trade_offer":
            offered = {}
            for e in pl["items"]:
                p["inv"][e["item_id"]] -= e["qty"]
                if p["inv"][e["item_id"]] == 0:
                    del p["inv"][e["item_id"]]
                offered[e["item_id"]] = e["qty"]
            coins = pl.get("coins", 0)
            p["coins"] -= coins
            self.trades.append({"id": self.next_id, "from": pid, "to": pl["to"],
                                "items": offered, "coins": coins})
            self.next_id += 1

    def snapshot(self):
        players = {}
        for pid, p in self.players.items():
            players[pid] = (p["coins"], dict(p["inv"]), dict(p["eq"]), list(p["pos"]), p["online"])
        return players, list(self.chat), [dict(t) for t in self.trades]


def read_world(world):
    players = {}
    for pid, p in world.players.items():
        inv = {k: v for k, v in p.inventory.items() if v != 0}
        eq = {s: p.equipped.get(s) for s in SLOTS}
        players[pid] = (p.coins, inv, eq, list(p.pos), p.online)
    return players, list(world.chat_log), [dict(t) for t in world.trades]


# ---------------------------------------------------------------- hidden worlds

WORDS = ["ember", "frost", "void", "rune", "storm", "jade", "ash", "tide", "onyx",
         "sol", "moss", "iron", "glim", "dusk", "nova", "pike", "warden", "fang"]
KINDS = {"weapon": ["blade", "axe", "bow", "staff"], "armor": ["plate", "cloak", "helm"],
         "pet": ["wisp", "owl", "drake"], None: ["elixir", "scroll", "shard", "token"]}


def make_catalog(rng):
    catalog = {}
    while len(catalog) < 16:
        slot = rng.choice(list(KINDS))
        name = rng.choice(WORDS) + "_" + rng.choice(KINDS[slot])
        if rng.random() < 0.4:
            name += str(rng.randint(2, 99))
        catalog[name] = {"price": rng.choice([1, 3, 7, 25, 60, 150, 400, 999, 2500]), "slot": slot}
    return catalog


def make_players(rng, catalog):
    names = ["Kai", "nyx_77", "Rook", "luna.v", "B0lt", "player one", "Zed", "ivy-x", "Q"]
    rng.shuffle(names)
    items = sorted(catalog)
    players = {}
    for i, pid in enumerate(names[:7]):
        inv = {}
        for item in rng.sample(items, rng.randint(2, 8)):
            inv[item] = rng.choice([1, 1, 2, 3, 5, 12, 40, 997])
        equipped = {}
        for item in inv:
            slot = catalog[item]["slot"]
            if slot and slot not in equipped and rng.random() < 0.6:
                equipped[slot] = item
        pos = [rng.randint(-50, 50), rng.choice([0, 0.5, 12.25]), rng.randint(-50, 50)]
        if i == 0:
            pos = [BOUND - 10, 0, -BOUND + 3]
        players[pid] = {"coins": rng.choice([0, 40, 900, 25000, 400000, 3_000_000]),
                        "inventory": inv, "equipped": equipped, "pos": pos,
                        "online": i < 5}
    return players


def build(seed):
    rng = random.Random(seed)
    catalog = make_catalog(rng)
    players = make_players(rng, catalog)
    world = World()
    for pid, spec in players.items():
        world.add_player(pid, coins=spec["coins"], inventory=dict(spec["inventory"]),
                         equipped=dict(spec["equipped"]), pos=tuple(spec["pos"]),
                         online=spec["online"])
    clock = ManualClock()
    server = Server(world, {k: dict(v) for k, v in catalog.items()}, clock)
    ref = Reference(catalog, players)
    return rng, server, ref, clock


# ---------------------------------------------------------------- legit payloads

TEXT_POOL = ["gg", "anyone up for the raid?", "  lol  ", "nice shot \U0001F525\U0001F525",
             "你好，朋友", "café crème", "مرحبا",
             "\U0001F468‍\U0001F469‍\U0001F467 fam", " wp ", "a b",
             "x" * 200, "\U0001F600" * 200, "1", "?"]
TEXT_CHARS = ("abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789 .,!?'\"-_:;()"
              "éñüßλж中文あ가​‍ "
              "\U0001F3AE\U0001F47E❤️")


def legit_text(rng):
    if rng.random() < 0.5:
        return rng.choice(TEXT_POOL)
    n = rng.randint(1, 200)
    s = "".join(rng.choice(TEXT_CHARS) for _ in range(n))
    if not s.strip():
        s = "k" + s[1:]
    return s


def legit(rng, ref, pid, ev):
    p = ref.players[pid]
    cat = ref.catalog
    if ev == "purchase":
        options = [i for i in cat if cat[i]["price"] <= p["coins"] and p["inv"].get(i, 0) < 999]
        if not options:
            return None
        item = rng.choice(options)
        top = min(99, p["coins"] // cat[item]["price"], 999 - p["inv"].get(item, 0))
        return {"item_id": item, "qty": rng.choice([1, top, rng.randint(1, top)])}
    if ev == "equip":
        options = [i for i, c in p["inv"].items() if c >= 1 and cat.get(i, {}).get("slot")]
        if not options:
            return None
        item = rng.choice(options)
        return {"slot": cat[item]["slot"], "item_id": item}
    if ev == "chat":
        return {"channel": rng.choice(["global", "team"]), "text": legit_text(rng)}
    if ev == "move":
        x0, y0, z0 = p["pos"]
        for _ in range(50):
            if rng.random() < 0.2:
                axis = rng.randrange(3)
                step = rng.choice([MAX_STEP, -MAX_STEP])
                delta = [0, 0, 0]
                delta[axis] = step
                new = [x0 + delta[0], y0 + delta[1], z0 + delta[2]]
            else:
                new = [x0 + rng.uniform(-40, 40), y0 + rng.uniform(-30, 30), z0 + rng.uniform(-40, 40)]
                if rng.random() < 0.4:
                    new = [round(v) for v in new]
                elif rng.random() < 0.3:
                    new = [round(v * 4) / 4 for v in new]
                d = math.hypot(new[0] - x0, new[1] - y0, new[2] - z0)
                if abs(d - MAX_STEP) < 1e-6:
                    continue
            new = [max(-BOUND, min(BOUND, v)) for v in new]
            if math.hypot(new[0] - x0, new[1] - y0, new[2] - z0) <= MAX_STEP:
                return {"x": new[0], "y": new[1], "z": new[2]}
        return None
    if ev == "trade_offer":
        others = [o for o, q in ref.players.items() if o != pid and q["online"]]
        equipped = set(v for v in p["eq"].values() if v)
        spare = {i: c - (1 if i in equipped else 0) for i, c in p["inv"].items()}
        spare = {i: c for i, c in spare.items() if c >= 1}
        if not others or not spare:
            return None
        picks = rng.sample(sorted(spare), rng.randint(1, min(8, len(spare))))
        payload = {"to": rng.choice(others),
                   "items": [{"item_id": i, "qty": rng.randint(1, min(999, spare[i]))} for i in picks]}
        if rng.random() < 0.6:
            payload["coins"] = rng.choice([0, rng.randint(0, min(p["coins"], 1_000_000))])
        return payload
    return None


# ---------------------------------------------------------------- hostile payloads

def deep_list(n):
    x = []
    for _ in range(n):
        x = [x]
    return x


def deep_dict(n):
    x = {}
    for _ in range(n):
        x = {"item_id": x}
    return x


def field_names(ev):
    return {"purchase": ["item_id", "qty"], "equip": ["slot", "item_id"], "chat": ["channel", "text"],
            "move": ["x", "y", "z"], "trade_offer": ["to", "items", "coins"]}[ev]


def int_fields(ev, pl):
    out = []
    if ev == "purchase":
        out.append((pl, "qty"))
    if ev == "trade_offer":
        out.append((pl, "coins"))
        out.extend((e, "qty") for e in pl["items"])
    return out


def any_field(rng, ev, pl):
    spots = [(pl, k) for k in field_names(ev)]
    if ev == "trade_offer":
        spots += [(e, k) for e in pl["items"] for k in ("item_id", "qty")]
    return rng.choice(spots)


def m_types(rng, ref, pid, ev, pl):
    holder, key = any_field(rng, ev, pl)
    holder[key] = rng.choice([None, "5", b"5", [], {}, 1.0, 2.5, "", [1, 2], {"a": 1}, (),
                              "global".encode(), bytearray(b"x"), 0, -1, 7])
    return pid, ev, pl


def m_bool_int(rng, ref, pid, ev, pl):
    if ev == "move":
        pl[rng.choice("xyz")] = rng.choice([True, False])
    elif int_fields(ev, pl):
        holder, key = rng.choice(int_fields(ev, pl))
        holder[key] = rng.choice([True, False])
    else:
        pl[rng.choice(field_names(ev))] = True
    return pid, ev, pl


def m_nonfinite(rng, ref, pid, ev, pl):
    bad = rng.choice([float("nan"), float("inf"), float("-inf"), -float("nan"), 1e308 * 10])
    if ev == "move":
        pl[rng.choice("xyz")] = bad
    elif int_fields(ev, pl):
        holder, key = rng.choice(int_fields(ev, pl))
        holder[key] = rng.choice([bad, float(holder.get(key, 1) or 1)])
    else:
        pl[rng.choice(field_names(ev))] = bad
    return pid, ev, pl


def m_bounds(rng, ref, pid, ev, pl):
    big = rng.choice([-1, 0, 100, 1000, 10**6 + 1, 2**31, 2**63, -(2**63), 10**30, 10**400, -(10**400)])
    if ev == "move":
        axis = rng.choice("xyz")
        pl[axis] = rng.choice([big, BOUND + 0.5, -BOUND - 1, 4097, 1e300])
    elif ev == "purchase":
        pl["qty"] = rng.choice([big, 0, -5, 100])
    elif ev == "trade_offer":
        if rng.random() < 0.5:
            pl["coins"] = rng.choice([big, -1, 1_000_001])
        else:
            rng.choice(pl["items"])["qty"] = rng.choice([big, 0, -3, 1000])
    else:
        return m_strings(rng, ref, pid, ev, pl)
    return pid, ev, pl


BAD_CHARS = ["\x00", "\n", "\t", "\r", "\x1b", "\x7f", "\x85", "\x9f", "\udc80", "\ud83d", "\udfff"]


def m_strings(rng, ref, pid, ev, pl):
    r = rng.random()
    if ev == "chat" and r < 0.6:
        t = legit_text(rng)
        choice = rng.randrange(5)
        if choice == 0:
            pl["text"] = t + "x" * (201 - len(t)) if len(t) < 201 else t + "x"
        elif choice == 1:
            pl["text"] = "spam " * 20000
        elif choice == 2:
            i = rng.randint(0, len(t))
            pl["text"] = t[:i] + rng.choice(BAD_CHARS) + t[i:]
        elif choice == 3:
            pl["text"] = rng.choice(["", " ", "   　 ", " ", "\n"])
        else:
            pl["text"] = b"\xff\xfehello".decode("utf-8", "surrogateescape")
        return pid, ev, pl
    holder, key = any_field(rng, ev, pl)
    val = holder.get(key)
    if type(val) is str:
        holder[key] = rng.choice([val + rng.choice(BAD_CHARS), val * 50, "x" * 100000,
                                  val + " ", " " + val, val.upper() + "Z"])
    else:
        holder[key] = "x" * rng.choice([201, 5000])
    return pid, ev, pl


ID_TRICKS = [
    lambda s: s + "\n",
    lambda s: s + "\r\n",
    lambda s: s.upper(),
    lambda s: s.replace("a", "а", 1) if "a" in s else "а" + s,
    lambda s: s + "１",
    lambda s: "_" + s,
    lambda s: "1" + s,
    lambda s: s + "-x",
    lambda s: s + "\x00",
    lambda s: s + "a" * 40,
    lambda s: s + " ",
    lambda s: s.encode(),
]


def m_ids(rng, ref, pid, ev, pl):
    trick = rng.choice(ID_TRICKS)
    if ev in ("purchase", "equip"):
        pl["item_id"] = trick(pl["item_id"])
    elif ev == "trade_offer":
        e = rng.choice(pl["items"])
        e["item_id"] = trick(e["item_id"])
    elif ev == "chat":
        pl["channel"] = rng.choice([trick("global"), "GLOBAL", "admin", "team\n"])
    else:
        return m_types(rng, ref, pid, ev, pl)
    return pid, ev, pl


def m_nesting(rng, ref, pid, ev, pl):
    depth = rng.choice([200, 5000, 40000])
    blob = deep_list(depth) if rng.random() < 0.5 else deep_dict(depth)
    r = rng.random()
    if r < 0.3:
        pl["junk"] = blob
    elif ev == "trade_offer" and r < 0.7:
        if rng.random() < 0.5:
            pl["items"] = blob if type(blob) is list else [blob]
        else:
            rng.choice(pl["items"])["item_id"] = blob
    else:
        holder, key = any_field(rng, ev, pl)
        holder[key] = blob
    return pid, ev, pl


def m_cycles(rng, ref, pid, ev, pl):
    r = rng.randrange(4)
    if r == 0:
        pl["self"] = pl
    elif r == 1:
        loop = []
        loop.append(loop)
        holder, key = any_field(rng, ev, pl)
        holder[key] = loop
    elif r == 2 and ev == "trade_offer":
        pl["items"].append(pl["items"])
    else:
        a, b = {}, {}
        a["item_id"] = b
        b["item_id"] = a
        holder, key = any_field(rng, ev, pl)
        holder[key] = a
    return pid, ev, pl


def m_keys(rng, ref, pid, ev, pl):
    r = rng.randrange(6)
    if r == 0:
        pl[rng.choice(["admin", "price", "player_id", "__proto__", "item_id ", "Qty"])] = rng.choice([True, 0, "x"])
    elif r == 1:
        pl[rng.choice([1, None, 2.5, ("item_id",), True, b"qty", frozenset()])] = 1
    elif r == 2:
        names = [k for k in field_names(ev) if k != "coins"]
        del pl[rng.choice(names)]
    elif r == 3 and ev == "trade_offer":
        e = rng.choice(pl["items"])
        if rng.random() < 0.5:
            e["bonus"] = 5
        else:
            del e[rng.choice(["item_id", "qty"])]
    elif r == 4:
        pl.clear()
    else:
        pl[rng.choice(["coins", "x", "slot", "text", "to"])] = 1
    return pid, ev, pl


def m_non_dict(rng, ref, pid, ev, pl):
    loop = []
    loop.append(loop)
    shapes = [None, [], "purchase", 5, b"{}", [pl], loop, True, 3.5, list(pl.items()),
              tuple(pl.values()), set(field_names(ev)), deep_list(30000)]
    return pid, ev, rng.choice(shapes)


def m_ownership(rng, ref, pid, ev, pl):
    p = ref.players[pid]
    unowned = [i for i in ref.catalog if p["inv"].get(i, 0) == 0]
    fake = rng.choice(["ghost_item", "admin_sword", "zz" + str(rng.randint(0, 99))])
    if ev == "equip":
        if rng.random() < 0.5 and unowned:
            item = rng.choice(unowned)
            pl["item_id"] = item
            pl["slot"] = ref.catalog[item]["slot"] or "weapon"
        else:
            wrong = [i for i in p["inv"] if ref.catalog.get(i, {}).get("slot") != pl["slot"]]
            pl["item_id"] = rng.choice(wrong) if wrong else fake
    elif ev == "trade_offer":
        e = rng.choice(pl["items"])
        e["item_id"] = rng.choice(unowned) if unowned and rng.random() < 0.7 else fake
    elif ev == "purchase":
        pl["item_id"] = fake
    else:
        return m_business(rng, ref, pid, ev, pl)
    return pid, ev, pl


def m_business(rng, ref, pid, ev, pl):
    p = ref.players[pid]
    if ev == "purchase":
        item = pl["item_id"]
        price = ref.catalog[item]["price"]
        pl["qty"] = min(99, p["coins"] // price + 1) if rng.random() < 0.6 else 99
    elif ev == "move":
        x0, y0, z0 = p["pos"]
        d = rng.choice([64.001, 65, 100, 500, 9000])
        pl["x"], pl["y"], pl["z"] = x0 + d, y0, z0
    elif ev == "trade_offer":
        r = rng.randrange(6)
        e = pl["items"][0]
        if r == 0:
            e["qty"] = p["inv"][e["item_id"]] + 1
        elif r == 1:
            eq = [v for v in p["eq"].values() if v]
            if eq:
                e["item_id"] = rng.choice(eq)
                e["qty"] = p["inv"][e["item_id"]]
        elif r == 2:
            pl["items"].append(dict(e))
        elif r == 3:
            pl["to"] = rng.choice([pid, "nobody_here", "", pid.upper()] +
                                  [o for o, q in ref.players.items() if not q["online"]])
        elif r == 4:
            pl["coins"] = p["coins"] + 1 if p["coins"] < 1_000_000 else 1_000_001
        else:
            pl["items"] = rng.choice([[], [dict(e) for _ in range(9)]])
    elif ev == "equip":
        return m_ownership(rng, ref, pid, ev, pl)
    else:
        return m_strings(rng, ref, pid, ev, pl)
    return pid, ev, pl


def m_routing(rng, ref, pid, ev, pl):
    r = rng.randrange(3)
    if r == 0:
        ev = rng.choice([None, ["purchase"], {"e": 1}, b"chat", "Purchase", "chat ", "give_item",
                         "__init__", "", 7, ("move",)])
    elif r == 1:
        offline = [o for o, q in ref.players.items() if not q["online"]]
        pid = rng.choice(offline + ["not_a_player"])
    else:
        pl["to"] = ["list", "of", "ids"] if ev == "trade_offer" else pl.get("to")
        pl["junk"] = {}
        ev = rng.choice(EVENTS)
    return pid, ev, pl


MUTATORS = {
    "types": m_types, "bool_int": m_bool_int, "nonfinite": m_nonfinite, "bounds": m_bounds,
    "strings": m_strings, "ids": m_ids, "nesting": m_nesting, "cycles": m_cycles,
    "keys": m_keys, "non_dict": m_non_dict, "ownership": m_ownership, "business": m_business,
    "routing": m_routing,
}


# ---------------------------------------------------------------- harness

def online(ref):
    return [p for p, q in ref.players.items() if q["online"]]


def pick_legit(rng, ref, pid=None):
    for _ in range(30):
        who = pid or rng.choice(online(ref))
        ev = rng.choice(EVENTS)
        pl = legit(rng, ref, who, ev)
        if pl is not None:
            return who, ev, pl
    return None


def fire(server, ref, clock, step, label, pid, ev, pl):
    now = clock.now()
    expected = ref.verdict(pid, ev, pl, now)
    if expected:
        ref.apply(pid, ev, pl, now)
    where = "step %d [%s] player=%r event=%s payload=%s" % (step, label, pid, SHORT.repr(ev), SHORT.repr(pl))
    try:
        result = server.dispatch(pid, ev, pl)
    except BaseException as err:  # noqa: B036
        pytest.fail("dispatch raised %s: %s at %s" % (type(err).__name__, SHORT.repr(err), where))
    if type(result) is not dict or type(result.get("ok")) is not bool:
        pytest.fail("dispatch returned %s instead of a dict with an ok bool at %s" % (SHORT.repr(result), where))
    if result["ok"] != expected:
        kind = "false rejection" if expected else "hostile or illegal event accepted"
        pytest.fail("%s at %s" % (kind, where))
    if read_world(server.world) != ref.snapshot():
        pytest.fail("world state differs from the reference after %s" % where)
    return expected


def run_stream(seed, steps, categories, hostile_share):
    rng, server, ref, clock = build(seed)
    clock.set(rng.randint(0, 5000) / 16)
    accepted = 0
    for step in range(steps):
        r = rng.random()
        if r < 0.3:
            pass
        elif r < 0.85:
            clock.advance(rng.randint(1, 8) / 16)
        else:
            clock.advance(rng.randint(16, 400) / 16)
        picked = pick_legit(rng, ref)
        if picked is None:
            continue
        pid, ev, pl = picked
        label = "legit"
        if rng.random() < hostile_share:
            label = rng.choice(categories)
            pid, ev, pl = MUTATORS[label](rng, ref, pid, ev, pl)
        if fire(server, ref, clock, step, label, pid, ev, pl):
            accepted += 1
    return accepted


# ---------------------------------------------------------------- tests

@pytest.mark.parametrize("seed", range(1001, 1009))
def test_legit_traffic_paced(seed):
    """Well paced legit traffic, every single event has to go through."""
    rng, server, ref, clock = build(seed)
    for step in range(250):
        clock.advance(rng.randint(1, 6) / 16)
        picked = pick_legit(rng, ref)
        if picked is None:
            continue
        pid, ev, pl = picked
        for _ in range(20):
            if ref.verdict(pid, ev, pl, clock.now()):
                break
            clock.advance(1)
        assert fire(server, ref, clock, step, "legit", pid, ev, pl)


@pytest.mark.parametrize("seed", range(2001, 2007))
def test_legit_bursts_rate_limits(seed):
    """Legit events in tight bursts, so the per player rate limits kick in."""
    rng, server, ref, clock = build(seed)
    step = 0
    for _ in range(40):
        clock.advance(rng.choice([0, 1, 3, 8, 15, 16, 17, 32, 160]) / 16)
        pid = rng.choice(online(ref))
        ev = rng.choice(EVENTS)
        for _ in range(rng.randint(2, 25)):
            pl = legit(rng, ref, pid, ev)
            if pl is None:
                break
            fire(server, ref, clock, step, "burst", pid, ev, pl)
            step += 1
            if rng.random() < 0.3:
                clock.advance(rng.randint(1, 4) / 16)


@pytest.mark.parametrize("category", sorted(MUTATORS))
def test_hostile_category(category):
    """Each kind of hostile payload on its own, mixed into legit traffic."""
    for seed in range(3):
        run_stream(3000 + seed * 97 + sorted(MUTATORS).index(category), 300, [category], 0.5)


@pytest.mark.parametrize("seed", range(4001, 4011))
def test_fuzz_mixed(seed):
    """Everything at once."""
    accepted = run_stream(seed, 600, sorted(MUTATORS), 0.45)
    assert accepted > 50
