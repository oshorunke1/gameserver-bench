"""Sealed verifier for trade-dupe-race.

Drives the agent's TradeService against our own store that follows the
documented contract, adds random awaits between every call, can fail calls on
purpose, and checks every committed row as it lands. Only results and stored
state are graded.
"""

import asyncio
import random
import sys

import pytest

sys.path.insert(0, "/app")

from tradesvc import TradeService  # noqa: E402
from tradesvc.errors import (  # noqa: E402
    DuplicateReceipt,
    StoreUnavailable,
    UnknownPlayer,
    VersionConflict,
)
from tradesvc.models import Inventory, TradeOffer, TradeRequest  # noqa: E402

VALID_REASONS = {
    "invalid_request",
    "unknown_player",
    "insufficient_gold",
    "insufficient_items",
    "inventory_full",
    "request_id_reused",
}


class HarnessStore:
    def __init__(self, players, *, seed=0, slot_limit=30, max_ticks=3, fail_rate=0.0):
        self.rows = {pid: [int(g), dict(items), 1] for pid, (g, items) in players.items()}
        self.receipts = {}
        self.receipt_tick = {}
        self.rng = random.Random(seed)
        self.max_ticks = max_ticks
        self.fail_rate = fail_rate
        self.fail_next = {"get_inventory": 0, "get_receipt": 0, "commit": 0}
        self.slot_limit = slot_limit
        self.violations = []
        self.tick = 0
        self.commits = 0

    async def _io(self, op):
        for _ in range(self.rng.randint(0, self.max_ticks)):
            await asyncio.sleep(0)
        self.tick += 1
        if self.fail_next[op] > 0:
            self.fail_next[op] -= 1
            raise StoreUnavailable(op)
        if self.fail_rate and self.rng.random() < self.fail_rate:
            raise StoreUnavailable(op)

    async def get_inventory(self, player_id):
        await self._io("get_inventory")
        row = self.rows.get(player_id)
        if row is None:
            raise UnknownPlayer(player_id)
        return Inventory(row[0], dict(row[1])), row[2]

    async def get_receipt(self, receipt_id):
        await self._io("get_receipt")
        return self.receipts.get(receipt_id)

    async def commit(self, writes, receipt_id=None, receipt=None):
        await self._io("commit")
        if receipt_id is not None and receipt_id in self.receipts:
            raise DuplicateReceipt(receipt_id)
        staged = {}
        for pid, (inv, expected) in dict(writes).items():
            row = self.rows.get(pid)
            if row is None:
                raise UnknownPlayer(pid)
            if expected is not None and row[2] != expected:
                raise VersionConflict(pid)
            staged[pid] = (inv.gold, dict(inv.items))
        for pid, (gold, items) in staged.items():
            row = self.rows[pid]
            row[0], row[1] = gold, items
            row[2] += 1
            self._check_row(pid, gold, items)
        if receipt_id is not None:
            self.receipts[receipt_id] = receipt
            self.receipt_tick[receipt_id] = self.tick
        self.commits += 1

    def _check_row(self, pid, gold, items):
        if not isinstance(gold, int) or gold < 0:
            self.violations.append(f"{pid} gold went to {gold!r}")
        for key, qty in items.items():
            if not isinstance(qty, int) or qty <= 0:
                self.violations.append(f"{pid} holds {qty!r} of {key}")
        if len(items) > self.slot_limit:
            self.violations.append(f"{pid} holds {len(items)} keys")

    def state(self):
        return {pid: (row[0], dict(row[1])) for pid, row in self.rows.items()}


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=120))


def offer(gold=0, *items):
    return TradeOffer(gold=gold, items=tuple(items))


def req(rid, a, b, a_offer, b_offer):
    return TradeRequest(rid, a, b, a_offer, b_offer)


def totals(state):
    gold = sum(g for g, _ in state.values())
    items = {}
    for _, inv in state.values():
        for k, q in inv.items():
            items[k] = items.get(k, 0) + q
    return gold, items


def base_players():
    return {
        "ossa": (240, {"glass_wyrm_scale": 6, "tidecaller_horn": 1, "sap_bomb": 20}),
        "veylin": (55, {"bramble_charm": 2, "sap_bomb": 3}),
        "durro": (900, {}),
    }


# ---------- plain behaviour ----------


def test_swap_moves_both_sides_and_drops_empty_stacks():
    store = HarnessStore(base_players(), seed=11)
    svc = TradeService(store)
    r = req(
        "q-swap",
        "ossa",
        "veylin",
        offer(15, ("tidecaller_horn", 1), ("sap_bomb", 5)),
        offer(0, ("bramble_charm", 2)),
    )
    res = run(svc.execute_trade(r))
    assert (res.status, res.reason) == ("completed", None)
    assert res.request_id == "q-swap"
    s = store.state()
    assert s["ossa"] == (225, {"glass_wyrm_scale": 6, "sap_bomb": 15, "bramble_charm": 2})
    assert s["veylin"] == (70, {"sap_bomb": 8, "tidecaller_horn": 1})
    assert not store.violations


def test_replay_on_another_server_is_a_noop():
    store = HarnessStore(base_players(), seed=12)
    one, two = TradeService(store), TradeService(store)
    r = req("q-rep", "durro", "veylin", offer(300), offer(0, ("sap_bomb", 1)))

    async def go():
        a = await one.execute_trade(r)
        b = await two.execute_trade(r)
        c = await one.execute_trade(r)
        return a, b, c

    results = run(go())
    assert [x.status for x in results] == ["completed"] * 3
    s = store.state()
    assert s["durro"] == (600, {"sap_bomb": 1})
    assert s["veylin"] == (355, {"bramble_charm": 2, "sap_bomb": 2})


def test_replay_with_items_listed_differently_is_same_request():
    store = HarnessStore(base_players(), seed=13)
    svc = TradeService(store)
    first = req("q-order", "ossa", "durro", offer(0, ("sap_bomb", 4), ("glass_wyrm_scale", 2)), offer(40))
    again = req(
        "q-order",
        "ossa",
        "durro",
        offer(0, ("glass_wyrm_scale", 2), ("sap_bomb", 1), ("sap_bomb", 3)),
        offer(40),
    )

    async def go():
        return await svc.execute_trade(first), await TradeService(store).execute_trade(again)

    a, b = run(go())
    assert a.status == b.status == "completed"
    assert store.state()["ossa"] == (280, {"glass_wyrm_scale": 4, "tidecaller_horn": 1, "sap_bomb": 16})


def test_reused_request_id_with_different_trade_is_refused():
    store = HarnessStore(base_players(), seed=14)
    svc = TradeService(store)
    first = req("q-reuse", "durro", "ossa", offer(100), offer(0, ("sap_bomb", 2)))
    other = req("q-reuse", "durro", "ossa", offer(100), offer(0, ("sap_bomb", 9)))

    async def go():
        a = await svc.execute_trade(first)
        before = store.state()
        b = await TradeService(store).execute_trade(other)
        c = await svc.execute_trade(other)
        return a, b, c, before

    a, b, c, before = run(go())
    assert a.status == "completed"
    assert (b.status, b.reason) == ("rejected", "request_id_reused")
    assert (c.status, c.reason) == ("rejected", "request_id_reused")
    assert store.state() == before


def test_repeated_key_is_summed_when_short():
    store = HarnessStore(base_players(), seed=15)
    svc = TradeService(store)
    before = store.state()
    r = req("q-dup1", "ossa", "veylin", offer(0, ("glass_wyrm_scale", 4), ("glass_wyrm_scale", 4)), offer(0))
    res = run(svc.execute_trade(r))
    assert (res.status, res.reason) == ("rejected", "insufficient_items")
    assert store.state() == before
    assert not store.violations


def test_repeated_key_is_summed_when_covered():
    store = HarnessStore(base_players(), seed=16)
    svc = TradeService(store)
    r = req(
        "q-dup2",
        "ossa",
        "veylin",
        offer(0, ("sap_bomb", 7), ("sap_bomb", 6), ("sap_bomb", 7)),
        offer(5),
    )
    res = run(svc.execute_trade(r))
    assert res.status == "completed"
    s = store.state()
    assert s["ossa"] == (245, {"glass_wyrm_scale": 6, "tidecaller_horn": 1})
    assert s["veylin"] == (50, {"bramble_charm": 2, "sap_bomb": 23})


@pytest.mark.parametrize(
    "r",
    [
        req("q-bad1", "ossa", "veylin", offer(0, ("sap_bomb", -3)), offer(0, ("bramble_charm", 1))),
        req("q-bad2", "ossa", "veylin", offer(0, ("sap_bomb", 0)), offer(0, ("bramble_charm", 1))),
        req("q-bad3", "ossa", "veylin", offer(-50), offer(0, ("bramble_charm", 1))),
        req("q-bad4", "veylin", "ossa", offer(10), offer(-200)),
        req("q-bad5", "ossa", "ossa", offer(0, ("tidecaller_horn", 1)), offer(0)),
        req("q-bad6", "durro", "veylin", offer(0), offer(0)),
    ],
    ids=["neg-qty", "zero-qty", "neg-gold", "neg-gold-target", "self-trade", "empty"],
)
def test_invalid_requests(r):
    store = HarnessStore(base_players(), seed=17)
    before = store.state()
    res = run(TradeService(store).execute_trade(r))
    assert (res.status, res.reason) == ("rejected", "invalid_request")
    assert store.state() == before
    assert not store.violations


def test_unknown_player():
    store = HarnessStore(base_players(), seed=18)
    before = store.state()
    res = run(TradeService(store).execute_trade(req("q-ghost", "ossa", "nobody_here", offer(5), offer(0))))
    assert (res.status, res.reason) == ("rejected", "unknown_player")
    assert store.state() == before


def _slot_players():
    return {
        "lark": (10, {"k1": 1, "k2": 1, "k3": 2}),
        "moss": (10, {"k3": 5, "k5": 1}),
    }


@pytest.mark.parametrize(
    "a_offer,b_offer,expect",
    [
        # lark is at 3 of 3, getting more of a stack it already owns is fine
        (offer(1), offer(0, ("k3", 2)), None),
        # new key in, old key fully out, still 3
        (offer(0, ("k1", 1)), offer(0, ("k5", 1)), None),
        # new key in, nothing out
        (offer(1), offer(0, ("k5", 1)), "inventory_full"),
        # moss gets two new keys and keeps both of its own, ends at 4
        (offer(0, ("k1", 1), ("k2", 1)), offer(0, ("k3", 1)), "inventory_full"),
    ],
    ids=["stack-onto-existing", "swap-slot", "no-room", "no-room-target"],
)
def test_slot_limit(a_offer, b_offer, expect):
    store = HarnessStore(_slot_players(), seed=19, slot_limit=3)
    before = store.state()
    svc = TradeService(store, slot_limit=3)
    res = run(svc.execute_trade(req("q-slot", "lark", "moss", a_offer, b_offer)))
    if expect is None:
        assert res.status == "completed", res
        assert store.state() != before
    else:
        assert (res.status, res.reason) == ("rejected", expect)
        assert store.state() == before
    assert not store.violations


# ---------- races between servers ----------


@pytest.mark.parametrize("seed", [101, 202, 303, 404, 505, 606])
def test_double_spend_across_servers(seed):
    players = {"ivo": (0, {"stormglass_idol": 1}), "pell": (500, {}), "quen": (500, {})}
    store = HarnessStore(players, seed=seed)
    s1, s2 = TradeService(store), TradeService(store)
    r1 = req(f"q-ds-a{seed}", "ivo", "pell", offer(0, ("stormglass_idol", 1)), offer(200))
    r2 = req(f"q-ds-b{seed}", "ivo", "quen", offer(0, ("stormglass_idol", 1)), offer(250))

    async def go():
        return await asyncio.gather(s1.execute_trade(r1), s2.execute_trade(r2))

    results = run(go())
    done = [x for x in results if x.status == "completed"]
    other = [x for x in results if x.status != "completed"]
    assert len(done) == 1, results
    assert (other[0].status, other[0].reason) == ("rejected", "insufficient_items")
    assert totals(store.state()) == (1000, {"stormglass_idol": 1})
    assert not store.violations


@pytest.mark.parametrize("seed", [7, 8, 9, 10])
def test_compatible_trades_all_land(seed):
    players = {"hub": (100, {"ash_tonic": 9}), "x1": (0, {}), "x2": (0, {}), "x3": (0, {})}
    store = HarnessStore(players, seed=seed)
    servers = [TradeService(store) for _ in range(3)]
    reqs = [
        req(f"q-ok-{seed}-{i}", "hub", f"x{i + 1}", offer(30, ("ash_tonic", 3)), offer(0))
        for i in range(3)
    ]

    async def go():
        return await asyncio.gather(*(servers[i].execute_trade(r) for i, r in enumerate(reqs)))

    results = run(go())
    assert [x.status for x in results] == ["completed"] * 3, results
    s = store.state()
    assert s["hub"] == (10, {})
    for i in range(3):
        assert s[f"x{i + 1}"] == (30, {"ash_tonic": 3})


@pytest.mark.parametrize("seed", [31, 32, 33, 34])
def test_crossing_trades_do_not_hang(seed):
    players = {"nim": (50, {"reed_flute": 2}), "orr": (50, {"cinder_moth": 2})}
    store = HarnessStore(players, seed=seed)
    s1, s2 = TradeService(store), TradeService(store)
    r1 = req(f"q-x1-{seed}", "nim", "orr", offer(0, ("reed_flute", 1)), offer(0, ("cinder_moth", 1)))
    r2 = req(f"q-x2-{seed}", "orr", "nim", offer(10), offer(5))

    async def go():
        return await asyncio.gather(
            s1.execute_trade(r1), s2.execute_trade(r2), s1.execute_trade(r2), s2.execute_trade(r1)
        )

    results = run(go())
    assert all(x.status == "completed" for x in results), results
    s = store.state()
    assert s["nim"] == (55, {"reed_flute": 1, "cinder_moth": 1})
    assert s["orr"] == (45, {"reed_flute": 1, "cinder_moth": 1})


@pytest.mark.parametrize("seed", [41, 42, 43, 44, 45])
def test_concurrent_replays_apply_once(seed):
    players = {"wren": (1000, {"fen_lantern": 4}), "yaro": (0, {})}
    store = HarnessStore(players, seed=seed)
    servers = [TradeService(store) for _ in range(3)]
    r = req(f"q-cr-{seed}", "wren", "yaro", offer(400, ("fen_lantern", 2)), offer(0))

    async def go():
        return await asyncio.gather(*(servers[i % 3].execute_trade(r) for i in range(5)))

    results = run(go())
    assert all(x.status == "completed" for x in results), results
    s = store.state()
    assert s["wren"] == (600, {"fen_lantern": 2})
    assert s["yaro"] == (400, {"fen_lantern": 2})


# ---------- store outages ----------


@pytest.mark.parametrize("op", ["commit", "get_inventory", "get_receipt"])
def test_outage_fails_cleanly_and_retry_works(op):
    store = HarnessStore(base_players(), seed=51)
    svc = TradeService(store)
    r = req(f"q-out-{op}", "durro", "ossa", offer(120), offer(0, ("tidecaller_horn", 1)))
    before = store.state()
    store.fail_next[op] = 1

    async def go():
        first = await svc.execute_trade(r)
        mid = store.state()
        second = await svc.execute_trade(r)
        return first, mid, second

    first, mid, second = run(go())
    if op == "get_receipt" and first.status == "completed":
        # a service that never reads receipts on the happy path is fine
        pass
    else:
        assert (first.status, first.reason) == ("failed", "store_unavailable")
        assert mid == before
    assert second.status == "completed"
    s = store.state()
    assert s["durro"] == (780, {"tidecaller_horn": 1})
    assert s["ossa"][0] == 360


# ---------- big randomized soak ----------

KEYS = ["rime_shard", "owl_feather", "brass_cog", "wisp_jar", "ember_seed", "salt_pearl", "bog_iron", "sky_silk"]


def _soak_world(rng, n_players, slot_limit):
    players = {}
    for i in range(n_players):
        keys = rng.sample(KEYS, rng.randint(1, slot_limit))
        players[f"pl{i:02d}"] = (rng.randint(0, 300), {k: rng.randint(1, 12) for k in keys})
    return players


def _soak_offer(rng, owned):
    gold = rng.choice([0, 0, rng.randint(1, 120)])
    items = []
    for _ in range(rng.choice([0, 1, 1, 2])):
        key = rng.choice(owned) if rng.random() < 0.8 else rng.choice(KEYS)
        items.append((key, rng.randint(1, 5)))
        if rng.random() < 0.15:
            items.append((key, rng.randint(1, 5)))
    return TradeOffer(gold=gold, items=tuple(items))


def _delta(r):
    out = {}

    def add(pid, gold, items, sign):
        g, inv = out.setdefault(pid, [0, {}])
        out[pid][0] = g + sign * gold
        for k, q in items:
            inv[k] = inv.get(k, 0) + sign * q

    add(r.initiator, r.initiator_offer.gold, r.initiator_offer.items, -1)
    add(r.target, r.initiator_offer.gold, r.initiator_offer.items, 1)
    add(r.target, r.target_offer.gold, r.target_offer.items, -1)
    add(r.initiator, r.target_offer.gold, r.target_offer.items, 1)
    return out


@pytest.mark.parametrize(
    "seed,fail_rate",
    [(9001, 0.0), (9002, 0.0), (9003, 0.04), (9004, 0.04), (9005, 0.08), (9006, 0.0)],
)
def test_soak(seed, fail_rate):
    rng = random.Random(seed)
    slot_limit = 5
    players = _soak_world(rng, 10, slot_limit)
    store = HarnessStore(players, seed=seed + 1, slot_limit=slot_limit, max_ticks=4, fail_rate=fail_rate)
    servers = [TradeService(store, slot_limit=slot_limit) for _ in range(3)]

    names = sorted(players)
    reqs = []
    for i in range(160):
        a, b = rng.sample(names, 2)
        ao, bo = _soak_offer(rng, sorted(players[a][1])), _soak_offer(rng, sorted(players[b][1]))
        if ao.gold == 0 and not ao.items and bo.gold == 0 and not bo.items:
            ao = TradeOffer(gold=1)
        reqs.append(req(f"soak-{seed}-{i}", a, b, ao, bo))
    calls = [(r, rng.randrange(3), rng.randint(0, 40)) for r in reqs]
    for r in rng.sample(reqs, 40):
        calls.append((r, rng.randrange(3), rng.randint(0, 60)))
    rng.shuffle(calls)

    log = []

    async def one(r, server, delay):
        for _ in range(delay):
            await asyncio.sleep(0)
        start = store.tick
        res = await servers[server].execute_trade(r)
        log.append((r, start, res))

    async def go():
        await asyncio.gather(*(one(*c) for c in calls))

    run(go())

    assert not store.violations, store.violations[:5]
    completed = {}
    for r, start, res in log:
        assert res.request_id == r.request_id
        assert res.status in {"completed", "rejected", "failed"}, res
        if res.status == "rejected":
            assert res.reason in VALID_REASONS, res
            assert res.reason not in {"invalid_request", "unknown_player", "request_id_reused"}, res
        if res.status == "failed":
            assert res.reason == "store_unavailable", res
        if res.status == "completed":
            completed[r.request_id] = r
    assert len(completed) >= 15, f"only {len(completed)} trades went through"

    # a call that starts after its request already landed must say completed
    for r, start, res in log:
        landed = store.receipt_tick.get(r.request_id)
        if r.request_id in completed and landed is not None and start > landed:
            assert res.status in {"completed", "failed"}, (r.request_id, res)

    expected = {pid: [g, dict(inv)] for pid, (g, inv) in players.items()}
    for r in completed.values():
        for pid, (g, inv) in _delta(r).items():
            expected[pid][0] += g
            for k, q in inv.items():
                expected[pid][1][k] = expected[pid][1].get(k, 0) + q
    expected = {pid: (g, {k: q for k, q in inv.items() if q != 0}) for pid, (g, inv) in expected.items()}
    assert store.state() == expected
    assert totals(store.state()) == totals({pid: (g, inv) for pid, (g, inv) in players.items()})
