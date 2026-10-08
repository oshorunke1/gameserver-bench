"""Seeded queue snapshot generator for the hidden test queues."""

import random

REGIONS = ["na-east", "na-west", "sa-east", "eu-west", "eu-central", "asia-se", "oce"]
NEIGHBORS = {
    "na-east": ["na-west", "sa-east", "eu-west"],
    "na-west": ["na-east", "oce", "asia-se"],
    "sa-east": ["na-east"],
    "eu-west": ["eu-central", "na-east"],
    "eu-central": ["eu-west"],
    "asia-se": ["oce", "na-west"],
    "oce": ["asia-se", "na-west"],
}
SIZE_WEIGHTS = [(1, 46), (2, 20), (3, 12), (4, 9), (5, 7), (6, 6)]


def _pick(rng, pairs):
    total = sum(w for _, w in pairs)
    roll = rng.uniform(0, total)
    for item, w in pairs:
        roll -= w
        if roll <= 0:
            return item
    return pairs[-1][0]


def generate(seed, n_parties, max_gap, region_weights=None, spread=1.0,
             neighbor_prob=0.3, dup_rate=0.03):
    rng = random.Random(seed)
    if region_weights is None:
        region_weights = [5, 4, 1, 5, 3, 2, 1]
    region_pairs = list(zip(REGIONS, region_weights))
    now = 1_760_000_000 + rng.randrange(100_000)
    parties = []
    all_members = []
    next_player = 1
    for _ in range(n_parties):
        home = _pick(rng, region_pairs)
        regions = [home] + [r for r in NEIGHBORS[home] if rng.random() < neighbor_prob]
        wait = min(int(rng.expovariate(1 / 260)), 1500)
        if all_members and rng.random() < dup_rate:
            # stale solo ticket for a player who is also queued in another party
            src = rng.choice(all_members)
            members = [dict(src)]
        else:
            size = _pick(rng, SIZE_WEIGHTS)
            base = rng.gauss(1500, 260 * spread)
            members = []
            for _ in range(size):
                skill = int(min(max(base + rng.gauss(0, 110), 500), 2900))
                members.append({"player_id": f"U{next_player:05d}", "skill": skill})
                next_player += 1
            all_members.extend(members)
        parties.append({"regions": regions, "enqueued_at": now - wait, "members": members})
    rng.shuffle(parties)
    ids = rng.sample(range(1000, 9999), len(parties))
    for party, pid in zip(parties, ids):
        party["party_id"] = f"P{pid}"
    parties = [
        {"party_id": p["party_id"], "regions": p["regions"],
         "enqueued_at": p["enqueued_at"], "members": p["members"]}
        for p in parties
    ]
    return {"snapshot_time": now, "max_skill_gap": max_gap, "parties": parties}
