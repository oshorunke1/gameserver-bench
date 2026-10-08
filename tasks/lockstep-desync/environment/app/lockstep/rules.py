"""Balance numbers. Designers tweak these, so keep them in one spot."""

MAP_SIZE = 64.0
TICK_SECONDS = 0.05

START_GOLD = 300
MINE_START = 2410
INCOME_PER_TICK = 4
POP_CAP = 12

CRIT_CHANCE = 0.1
CRIT_MULT = 2.0
FALLOFF_PER_TILE = 0.04
SPAWN_JITTER = 2.0

# base spots, handed out by sorted player name
BASES = [(8.0, 8.0), (56.0, 56.0), (8.0, 56.0), (56.0, 8.0)]

KINDS = {
    "soldier": {"hp": 100.0, "speed": 1.25, "range": 1.5, "damage": 12.0, "cooldown": 3, "cost": 50},
    "archer": {"hp": 60.0, "speed": 1.0, "range": 5.0, "damage": 7.5, "cooldown": 4, "cost": 60},
    "knight": {"hp": 160.0, "speed": 0.8, "range": 1.75, "damage": 18.5, "cooldown": 5, "cost": 90},
}
