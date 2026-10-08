"""A few example scenarios for SessionStore. Not the full picture."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from savesys.clock import SimClock  # noqa: E402
from savesys.datastore import DataStore  # noqa: E402
from savesys.errors import LeaseLost, SessionLocked  # noqa: E402
from savesys.session import SessionStore  # noqa: E402


@pytest.fixture
def world():
    clock = SimClock(100.0)
    store = DataStore()
    return clock, store


def test_new_player_starts_with_defaults(world):
    clock, store = world
    hub = SessionStore(store, clock, "hub-1")
    assert hub.load("alice") == {"coins": 0, "level": 1, "inventory": []}


def test_save_then_hop_after_release(world):
    clock, store = world
    hub = SessionStore(store, clock, "hub-1")
    arena = SessionStore(store, clock, "arena-7")
    data = hub.load("alice")
    data["coins"] = 40
    hub.save("alice", data)
    data["inventory"].append("wooden_sword")
    hub.release("alice", data)
    assert arena.load("alice") == {"coins": 40, "level": 1, "inventory": ["wooden_sword"]}


def test_second_server_is_locked_out(world):
    clock, store = world
    hub = SessionStore(store, clock, "hub-1")
    arena = SessionStore(store, clock, "arena-7")
    hub.load("bob")
    with pytest.raises(SessionLocked) as err:
        arena.load("bob")
    assert err.value.owner == "hub-1"
    assert err.value.expires_at == pytest.approx(130.0)


def test_old_owner_cannot_write_after_takeover(world):
    clock, store = world
    hub = SessionStore(store, clock, "hub-1")
    arena = SessionStore(store, clock, "arena-7")
    data = hub.load("carol")
    data["coins"] = 5
    hub.save("carol", data)
    clock.advance(31)
    assert arena.load("carol")["coins"] == 5
    with pytest.raises(LeaseLost):
        hub.save("carol", {"coins": 999, "level": 1, "inventory": []})
