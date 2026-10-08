import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tradesvc import TradeService  # noqa: E402
from tradesvc.models import Inventory, TradeOffer, TradeRequest  # noqa: E402
from tradesvc.store import InMemoryStore  # noqa: E402


def make_store():
    return InMemoryStore(
        {
            "kai": Inventory(gold=500, items={"moonblade": 1, "pine_resin": 12}),
            "rue": Inventory(gold=80, items={"frost_lure": 3}),
        }
    )


def test_simple_swap():
    store = make_store()
    svc = TradeService(store)
    req = TradeRequest(
        "t-1",
        "kai",
        "rue",
        TradeOffer(gold=50, items=(("pine_resin", 4),)),
        TradeOffer(items=(("frost_lure", 1),)),
    )
    result = asyncio.run(svc.execute_trade(req))
    assert result.status == "completed"
    snap = store.snapshot()
    assert snap["kai"] == Inventory(450, {"moonblade": 1, "pine_resin": 8, "frost_lure": 1})
    assert snap["rue"] == Inventory(130, {"frost_lure": 2, "pine_resin": 4})


def test_replay_is_harmless():
    store = make_store()
    svc = TradeService(store)
    req = TradeRequest("t-2", "kai", "rue", TradeOffer(items=(("moonblade", 1),)), TradeOffer())

    async def go():
        first = await svc.execute_trade(req)
        second = await svc.execute_trade(req)
        return first, second

    first, second = asyncio.run(go())
    assert first.status == second.status == "completed"
    assert store.snapshot()["rue"].items["moonblade"] == 1


def test_not_enough_gold():
    store = make_store()
    svc = TradeService(store)
    req = TradeRequest("t-3", "rue", "kai", TradeOffer(gold=81), TradeOffer())
    result = asyncio.run(svc.execute_trade(req))
    assert (result.status, result.reason) == ("rejected", "insufficient_gold")
    assert store.snapshot()["rue"].gold == 80
