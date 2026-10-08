"""Errors the inventory store can raise. The trade service catches these."""


class StoreError(Exception):
    """Base class for anything the store throws at us."""


class StoreUnavailable(StoreError):
    """The store couldn't be reached. Nothing was read or written."""


class VersionConflict(StoreError):
    """Someone else wrote a row after we read it, so the commit was refused."""


class DuplicateReceipt(StoreError):
    """A receipt with this id already exists, so the commit was refused."""


class UnknownPlayer(StoreError):
    """No inventory row exists for that player id."""
