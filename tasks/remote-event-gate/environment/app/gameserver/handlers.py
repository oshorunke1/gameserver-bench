"""Event handlers. These trust the payload completely, the gate is supposed to
have checked everything already. Don't change what they do to the world."""


def handle_purchase(world, player, payload, catalog):
    item_id = payload["item_id"]
    qty = payload["qty"]
    cost = catalog[item_id]["price"] * qty
    player.coins -= cost
    player.inventory[item_id] = player.inventory.get(item_id, 0) + qty
    return {"ok": True, "coins": player.coins}


def handle_equip(world, player, payload, catalog):
    player.equipped[payload["slot"]] = payload["item_id"]
    return {"ok": True}


def handle_chat(world, player, payload, catalog):
    world.chat_log.append((player.id, payload["channel"], payload["text"]))
    return {"ok": True}


def handle_move(world, player, payload, catalog):
    player.pos = [payload["x"], payload["y"], payload["z"]]
    return {"ok": True}


def handle_trade_offer(world, player, payload, catalog):
    # the offered stuff goes into escrow until the other side answers
    offered = {}
    for entry in payload["items"]:
        item_id = entry["item_id"]
        qty = entry["qty"]
        player.inventory[item_id] = player.inventory.get(item_id, 0) - qty
        if player.inventory[item_id] == 0:
            del player.inventory[item_id]
        offered[item_id] = qty
    coins = payload.get("coins", 0)
    player.coins -= coins
    trade = {
        "id": world.next_trade_id,
        "from": player.id,
        "to": payload["to"],
        "items": offered,
        "coins": coins,
    }
    world.next_trade_id += 1
    world.trades.append(trade)
    return {"ok": True, "trade_id": trade["id"]}


HANDLERS = {
    "purchase": handle_purchase,
    "equip": handle_equip,
    "chat": handle_chat,
    "move": handle_move,
    "trade_offer": handle_trade_offer,
}
