"""What a brand new player starts with."""


def default_player_data() -> dict:
    # hand out a fresh dict every time so nobody shares the same list
    return {"coins": 0, "level": 1, "inventory": []}
