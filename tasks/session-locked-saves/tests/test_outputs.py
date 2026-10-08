"""Sealed checks for SessionStore.

Everything runs on the shared SimClock and the in-memory DataStore, so the
results never depend on real time. The fuzz section replays seeded random
histories of loads, saves, renews, releases, crashes, restarts and store
faults across several servers and compares every outcome to a small model
of the contract in /app/README.md.
"""

import copy
import random
import sys

import pytest

sys.path.insert(0, "/app")

from savesys.clock import SimClock  # noqa: E402
from savesys.datastore import DataStore  # noqa: E402
from savesys.defaults import default_player_data  # noqa: E402
from savesys.errors import LeaseLost, SaveFailed, SessionLocked  # noqa: E402
from savesys.session import SessionStore  # noqa: E402

DEFAULT = {"coins": 0, "level": 1, "inventory": []}


def blob(coins, level=3, items=("rune",)):
    return {"coins": coins, "level": level, "inventory": list(items)}


@pytest.fixture
def env():
    return SimClock(1000.0), DataStore()


def make(env, server_id, lease=12.5):
    clock, store = env
    return SessionStore(store, clock, server_id, lease)


# plain lock behaviour


def test_defaults_are_fresh_each_time(env):
    a = make(env, "eu-1")
    first = a.load("p-1")
    assert first == DEFAULT
    first["inventory"].append("cursed_item")
    first["coins"] = 77
    assert a.load("p-2") == DEFAULT
    assert default_player_data() == DEFAULT


def test_locked_error_reports_owner_and_lease_end(env):
    clock, _ = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    clock.advance(3)
    a.load("p-1")
    with pytest.raises(SessionLocked) as err:
        b.load("p-1")
    assert err.value.owner == "eu-1"
    assert err.value.expires_at == pytest.approx(1015.5)


def test_lease_boundary_is_exact(env):
    clock, _ = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    data = a.load("p-1")
    data["coins"] = 11
    a.save("p-1", data)
    clock.set(1012.499)
    with pytest.raises(SessionLocked):
        b.load("p-1")
    clock.set(1012.5)
    assert b.load("p-1")["coins"] == 11


def test_returned_data_is_not_shared_with_the_store(env):
    a, b = make(env, "eu-1"), make(env, "us-3")
    data = a.load("p-1")
    data["coins"] = 5
    a.save("p-1", data)
    data["coins"] = 6000
    data["inventory"].append("ghost")
    a.release("p-1", blob(9))
    got = b.load("p-1")
    assert got == blob(9)
    got["inventory"].append("ghost")
    b.release("p-1", blob(10))
    assert a.load("p-1") == blob(10)


def test_release_hands_off_immediately_and_old_owner_is_out(env):
    a, b = make(env, "eu-1"), make(env, "us-3")
    a.load("p-1")
    a.release("p-1", blob(42))
    assert b.load("p-1") == blob(42)
    for call in (lambda: a.save("p-1", blob(1)), lambda: a.renew("p-1"), lambda: a.release("p-1", blob(1))):
        with pytest.raises(LeaseLost):
            call()
    b.release("p-1", blob(43))
    assert make(env, "ap-2").load("p-1") == blob(43)


def test_calls_without_a_load_are_rejected(env):
    a, b = make(env, "eu-1"), make(env, "us-3")
    with pytest.raises(LeaseLost):
        a.save("ghost", blob(1))
    with pytest.raises(LeaseLost):
        a.renew("ghost")
    b.load("p-1")
    with pytest.raises(LeaseLost):
        a.save("p-1", blob(1))
    with pytest.raises(LeaseLost):
        a.release("p-1", blob(1))
    b.release("p-1", b.load("p-1"))
    assert make(env, "ap-2").load("p-1") == DEFAULT  # nothing a wrote ever landed


def test_renew_returns_new_lease_end_and_extends(env):
    clock, _ = env
    a, b = make(env, "eu-1", lease=8.0), make(env, "us-3")
    a.load("p-1")
    clock.advance(6)
    assert a.renew("p-1") == pytest.approx(1014.0)
    clock.advance(6)
    with pytest.raises(SessionLocked) as err:
        b.load("p-1")
    assert err.value.expires_at == pytest.approx(1014.0)


def test_save_after_untaken_expiry_still_works_and_extends(env):
    clock, _ = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    a.load("p-1")
    clock.advance(40)
    a.save("p-1", blob(3))
    clock.advance(12)
    with pytest.raises(SessionLocked) as err:
        b.load("p-1")
    assert err.value.expires_at == pytest.approx(1052.5)
    clock.advance(1)
    assert b.load("p-1") == blob(3)


def test_reload_by_holder_refreshes(env):
    clock, _ = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    a.load("p-1")
    a.save("p-1", blob(8))
    clock.advance(10)
    assert a.load("p-1") == blob(8)
    clock.advance(10)
    with pytest.raises(SessionLocked):
        b.load("p-1")
    a.save("p-1", blob(9))


def test_zombie_server_cannot_roll_back_progress(env):
    clock, _ = env
    a, b, c = make(env, "eu-1"), make(env, "us-3"), make(env, "ap-2")
    a.load("p-1")
    a.save("p-1", blob(100))
    clock.advance(20)
    assert b.load("p-1") == blob(100)
    b.save("p-1", blob(150))
    for call in (lambda: a.save("p-1", blob(120)), lambda: a.renew("p-1"), lambda: a.release("p-1", blob(120))):
        with pytest.raises(LeaseLost):
            call()
    with pytest.raises(SessionLocked) as err:
        c.load("p-1")
    assert err.value.owner == "us-3"
    with pytest.raises(LeaseLost):
        a.save("p-1", blob(121))
    b.release("p-1", blob(151))
    assert c.load("p-1") == blob(151)


def test_crash_keeps_last_save_only(env):
    clock, _ = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    data = a.load("p-1")
    data["coins"] = 30
    a.save("p-1", data)
    data["coins"] = 31  # never saved, then the server dies
    del a
    clock.advance(12)
    with pytest.raises(SessionLocked):
        b.load("p-1")
    clock.advance(0.5)
    assert b.load("p-1")["coins"] == 30


def test_restarted_server_takes_over_its_own_players(env):
    a_old = make(env, "eu-1")
    a_old.load("p-1")
    a_old.save("p-1", blob(70))
    a_new = make(env, "eu-1")
    assert a_new.load("p-1") == blob(70)
    with pytest.raises(LeaseLost):
        a_old.save("p-1", blob(1))
    with pytest.raises(LeaseLost):
        a_old.release("p-1", blob(1))
    with pytest.raises(SessionLocked) as err:
        make(env, "us-3").load("p-1")
    assert err.value.owner == "eu-1"
    a_new.release("p-1", blob(71))
    assert make(env, "us-3").load("p-1") == blob(71)


def test_players_are_locked_independently(env):
    a, b = make(env, "eu-1"), make(env, "us-3")
    a.load("p-1")
    b.load("p-2")
    a.save("p-1", blob(1))
    b.save("p-2", blob(2))
    with pytest.raises(SessionLocked):
        a.load("p-2")
    with pytest.raises(LeaseLost):
        a.save("p-2", blob(5))
    b.release("p-2", blob(3))
    assert a.load("p-2") == blob(3)


# races driven through the store hook


def test_race_on_first_load(env):
    _, store = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    seen = {}
    store.before_next_put(lambda: seen.setdefault("b", b.load("p-1")))
    with pytest.raises(SessionLocked) as err:
        a.load("p-1")
    assert err.value.owner == "us-3"
    assert seen["b"] == DEFAULT
    b.save("p-1", blob(4))
    with pytest.raises(LeaseLost):
        a.save("p-1", blob(5))


def test_race_on_takeover_of_expired_lease(env):
    clock, store = env
    a, b, c = make(env, "eu-1"), make(env, "us-3"), make(env, "ap-2")
    a.load("p-1")
    a.save("p-1", blob(12))
    clock.advance(30)
    store.before_next_put(lambda: c.load("p-1"))
    with pytest.raises(SessionLocked) as err:
        b.load("p-1")
    assert err.value.owner == "ap-2"
    with pytest.raises(LeaseLost):
        a.save("p-1", blob(13))
    c.release("p-1", blob(14))
    assert b.load("p-1") == blob(14)


def test_steal_lands_in_the_middle_of_a_save(env):
    clock, store = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    a.load("p-1")
    a.save("p-1", blob(50))

    def steal():
        clock.advance(13)
        b.load("p-1")

    store.before_next_put(steal)
    with pytest.raises(LeaseLost):
        a.save("p-1", blob(999))
    b.release("p-1", b.load("p-1"))
    assert make(env, "ap-2").load("p-1") == blob(50)


def test_steal_lands_in_the_middle_of_a_release(env):
    clock, store = env
    a, b, c = make(env, "eu-1"), make(env, "us-3"), make(env, "ap-2")
    a.load("p-1")
    a.save("p-1", blob(60))

    def steal():
        clock.advance(20)
        b.load("p-1")

    store.before_next_put(steal)
    with pytest.raises(LeaseLost):
        a.release("p-1", blob(999))
    with pytest.raises(SessionLocked) as err:
        c.load("p-1")
    assert err.value.owner == "us-3"
    b.release("p-1", blob(61))
    assert c.load("p-1") == blob(61)


# store failures


def test_timeout_that_landed_on_save(env):
    _, store = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    a.load("p-1")
    store.inject_faults("timeout_after")
    a.save("p-1", blob(21))
    store.clear_faults()
    a.save("p-1", blob(22))
    with pytest.raises(SessionLocked):
        b.load("p-1")
    a.release("p-1", a.load("p-1"))
    assert b.load("p-1") == blob(22)


def test_timeout_that_landed_on_release(env):
    _, store = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    a.load("p-1")
    store.inject_faults("timeout_after")
    a.release("p-1", blob(31))
    store.clear_faults()
    assert b.load("p-1") == blob(31)
    with pytest.raises(LeaseLost):
        a.save("p-1", blob(0))


def test_timeout_that_landed_on_load(env):
    _, store = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    store.inject_faults("timeout_after")
    assert a.load("p-1") == DEFAULT
    store.clear_faults()
    a.save("p-1", blob(1))
    with pytest.raises(SessionLocked):
        b.load("p-1")
    store.inject_faults("timeout_after")
    assert a.renew("p-1") == pytest.approx(1012.5)
    store.clear_faults()
    a.release("p-1", blob(2))
    assert b.load("p-1") == blob(2)


def test_timeout_that_did_not_land_is_retried(env):
    clock, store = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    a.load("p-1")
    store.inject_faults("timeout_before", "unavailable", "timeout_before", "unavailable")
    a.save("p-1", blob(44))
    store.clear_faults()
    store.inject_faults("timeout_before", "timeout_before", "timeout_before", "timeout_after")
    a.release("p-1", blob(45))
    store.clear_faults()
    assert b.load("p-1") == blob(45)


def test_five_failed_writes_gives_up_cleanly(env):
    clock, store = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    a.load("p-1")
    a.save("p-1", blob(10))
    clock.advance(5)
    store.inject_faults("unavailable", "timeout_before", "unavailable", "timeout_before", "unavailable")
    with pytest.raises(SaveFailed):
        a.save("p-1", blob(11))
    store.clear_faults()
    with pytest.raises(SessionLocked) as err:
        b.load("p-1")
    assert err.value.expires_at == pytest.approx(1012.5)  # lease was not pushed out
    store.inject_faults(*["unavailable"] * 5)
    with pytest.raises(SaveFailed):
        a.release("p-1", blob(12))
    store.clear_faults()
    with pytest.raises(SessionLocked):
        b.load("p-1")
    a.release("p-1", blob(13))
    assert b.load("p-1") == blob(13)


def test_failed_load_takes_nothing(env):
    _, store = env
    a, b = make(env, "eu-1"), make(env, "us-3")
    store.inject_faults(*["timeout_before"] * 5)
    with pytest.raises(SaveFailed):
        a.load("p-1")
    store.clear_faults()
    assert b.load("p-1") == DEFAULT
    with pytest.raises(LeaseLost):
        a.save("p-1", blob(1))


def test_failed_save_on_restarted_server_does_not_steal_twice(env):
    clock, store = env
    old = make(env, "eu-1")
    old.load("p-1")
    old.save("p-1", blob(5))
    new = make(env, "eu-1")
    store.inject_faults("timeout_after")
    assert new.load("p-1") == blob(5)
    store.clear_faults()
    with pytest.raises(LeaseLost):
        old.save("p-1", blob(6))
    new.save("p-1", blob(7))
    new.release("p-1", blob(8))
    assert make(env, "us-3").load("p-1") == blob(8)


# seeded fuzz against a model of the contract


class ModelInstance:
    def __init__(self, sid):
        self.sid = sid


class Model:
    def __init__(self, lease):
        self.lease = lease
        self.records = {}  # player -> {"data", "owner": ModelInstance or None, "exp"}

    def load(self, inst, player, now, landed_ok):
        rec = self.records.get(player)
        if rec is not None and rec["owner"] is not None:
            owner = rec["owner"]
            if owner is not inst and owner.sid != inst.sid and now < rec["exp"]:
                return ("locked", owner.sid, rec["exp"])
        if not landed_ok:
            return ("failed",)
        data = copy.deepcopy(rec["data"]) if rec is not None else copy.deepcopy(DEFAULT)
        self.records[player] = {"data": data, "owner": inst, "exp": now + self.lease}
        return ("ok", copy.deepcopy(data))

    def held_write(self, kind, inst, player, now, landed_ok, data=None):
        rec = self.records.get(player)
        if rec is None or rec["owner"] is not inst:
            return ("lost",)
        if not landed_ok:
            return ("failed",)
        if data is not None:
            rec["data"] = copy.deepcopy(data)
        rec["exp"] = now + self.lease
        if kind == "release":
            rec["owner"] = None
        if kind == "renew":
            return ("ok", rec["exp"])
        return ("ok", None)


def run_real(fn):
    try:
        return ("ok", fn())
    except SessionLocked as err:
        return ("locked", err.owner, err.expires_at)
    except LeaseLost:
        return ("lost",)
    except SaveFailed:
        return ("failed",)


def random_faults(rng):
    roll = rng.random()
    if roll < 0.55:
        return [], True
    if roll < 0.9:
        bad = [rng.choice(["unavailable", "timeout_before"]) for _ in range(rng.randint(0, 4))]
        if rng.random() < 0.6:
            bad.append("timeout_after")
        return bad, True
    return [rng.choice(["unavailable", "timeout_before"]) for _ in range(5)], False


def assert_same(expected, got, where):
    assert expected[0] == got[0], f"{where}: expected {expected}, got {got}"
    if expected[0] == "locked":
        assert got[1] == expected[1], f"{where}: wrong owner in {got}"
        assert got[2] == pytest.approx(expected[2], abs=1e-9), f"{where}: wrong lease end in {got}"
    elif expected[0] == "ok" and expected[1] is not None:
        if isinstance(expected[1], float):
            assert got[1] == pytest.approx(expected[1], abs=1e-9), f"{where}: renew returned {got[1]}"
        else:
            assert got[1] == expected[1], f"{where}: load returned {got[1]}"


def fuzz_one(seed):
    rng = random.Random(seed * 7919 + 17)
    lease = rng.choice([6.0, 9.5, 15.0, 22.25])
    clock = SimClock(rng.choice([0.0, 250.0, 86400.0]))
    store = DataStore()
    model = Model(lease)
    sids = ["srv-a", "srv-b", "srv-c"]
    players = ["u1", "u2", "u3", "u4"]
    live = {}
    zombies = []
    for sid in sids:
        live[sid] = (SessionStore(store, clock, sid, lease), ModelInstance(sid))

    for step in range(90):
        where = f"seed {seed} step {step}"
        op = rng.choices(
            ["load", "save", "renew", "release", "tick", "restart"],
            weights=[30, 30, 8, 12, 15, 5],
        )[0]
        if op == "tick":
            clock.advance(rng.choice([0.5, 1.0, 2.5, 4.0, 7.0, 13.0, lease]))
            continue
        if op == "restart":
            sid = rng.choice(sids)
            zombies.append(live[sid])
            live[sid] = (SessionStore(store, clock, sid, lease), ModelInstance(sid))
            continue
        if zombies and rng.random() < 0.2:
            real, fake = rng.choice(zombies)
        else:
            real, fake = live[rng.choice(sids)]
        player = rng.choice(players)
        faults, landed_ok = random_faults(rng)
        store.clear_faults()
        store.inject_faults(*faults)
        now = clock.now()
        if op == "load":
            expected = model.load(fake, player, now, landed_ok)
            got = run_real(lambda: real.load(player))
            assert_same(expected, got, f"{where} load {player}")
            if got[0] == "ok":
                got[1]["inventory"].append("tamper")
                got[1]["coins"] = -1
        else:
            data = None
            if op in ("save", "release"):
                data = blob(rng.randint(0, 10**6), rng.randint(1, 99), rng.sample(["axe", "bow", "gem", "map", "orb"], rng.randint(0, 3)))
            expected = model.held_write(op, fake, player, now, landed_ok, data)
            if op == "save":
                got = run_real(lambda: real.save(player, data))
            elif op == "release":
                got = run_real(lambda: real.release(player, data))
            else:
                got = run_real(lambda: real.renew(player))
            if op != "renew" and got[0] == "ok":
                got = ("ok", None)
            assert_same(expected, got, f"{where} {op} {player}")
            if data is not None:
                data["coins"] = -5
        store.clear_faults()

    clock.advance(lease * 10)
    auditor = SessionStore(store, clock, "auditor", lease)
    for player, rec in model.records.items():
        assert auditor.load(player) == rec["data"], f"seed {seed}: final data for {player}"


@pytest.mark.parametrize("block", range(8))
def test_seeded_histories(block):
    for seed in range(block * 25, block * 25 + 25):
        fuzz_one(seed)
