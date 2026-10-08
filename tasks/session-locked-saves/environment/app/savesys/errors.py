"""Errors that SessionStore raises to the game server code."""


class SessionLocked(Exception):
    """Another server is still holding this player's session."""

    def __init__(self, player_id: str, owner: str, expires_at: float):
        super().__init__(f"{player_id} is locked by {owner} until {expires_at}")
        self.player_id = player_id
        self.owner = owner
        self.expires_at = expires_at


class LeaseLost(Exception):
    """This server does not hold the player's session (any more)."""

    def __init__(self, player_id: str):
        super().__init__(f"session for {player_id} is not held by this server")
        self.player_id = player_id


class SaveFailed(Exception):
    """The datastore kept failing and we gave up on this call."""

    def __init__(self, player_id: str):
        super().__init__(f"gave up writing {player_id} after repeated store failures")
        self.player_id = player_id
