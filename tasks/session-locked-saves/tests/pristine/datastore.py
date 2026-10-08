"""In-memory stand-in for the cloud key-value store the servers save to.

How it behaves, which matches the real service closely enough:

* get(key) gives back a Snapshot(value, version) or None if the key was
  never written. The value is a deep copy, so editing it changes nothing.
* put(key, value, expected_version) is a conditional write. It only goes
  through if the key's current version equals expected_version (use None
  for a key that does not exist yet). On success the version goes up by
  one and the new version number is returned. If the version does not
  match you get VersionConflict and nothing is written.
* put can fail. DataStoreUnavailable means the write did NOT happen.
  WriteTimeout means we lost the reply, so the write may or may not have
  happened. get never fails.

The inject_faults and before_next_put helpers are how tests make bad
things happen at exact moments. Game code should never call them.
"""

import copy
from dataclasses import dataclass
from typing import Any, Callable, Optional


class DataStoreUnavailable(Exception):
    """The store refused the write. Nothing was written."""


class WriteTimeout(Exception):
    """The reply got lost. The write may or may not have been applied."""


class VersionConflict(Exception):
    """expected_version did not match. Nothing was written."""

    def __init__(self, key: str, expected: Optional[int], actual: Optional[int]):
        super().__init__(f"{key}: expected version {expected}, found {actual}")
        self.key = key
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True)
class Snapshot:
    value: Any
    version: int


FAULT_KINDS = ("unavailable", "timeout_before", "timeout_after")


class DataStore:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[Any, int]] = {}
        self._faults: list[str] = []
        self._hooks: list[Callable[[], None]] = []
        self.put_calls = 0

    def get(self, key: str) -> Optional[Snapshot]:
        row = self._rows.get(key)
        if row is None:
            return None
        return Snapshot(copy.deepcopy(row[0]), row[1])

    def put(self, key: str, value: Any, expected_version: Optional[int]) -> int:
        self.put_calls += 1
        # grab the fault for this call before running any hook, so a hook
        # that writes on its own never eats a fault meant for this call
        hook = self._hooks.pop(0) if self._hooks else None
        fault = self._faults.pop(0) if self._faults else None
        if hook is not None:
            hook()
        if fault == "unavailable":
            raise DataStoreUnavailable(key)
        if fault == "timeout_before":
            raise WriteTimeout(key)
        current = self._rows.get(key)
        current_version = current[1] if current is not None else None
        if current_version != expected_version:
            raise VersionConflict(key, expected_version, current_version)
        new_version = (current_version or 0) + 1
        self._rows[key] = (copy.deepcopy(value), new_version)
        if fault == "timeout_after":
            # the write landed but the caller never hears about it
            raise WriteTimeout(key)
        return new_version

    # test helpers below, game code should leave these alone

    def inject_faults(self, *kinds: str) -> None:
        """Queue faults for the next put calls, one per call, in order."""
        for kind in kinds:
            if kind not in FAULT_KINDS:
                raise ValueError(f"unknown fault {kind}")
            self._faults.append(kind)

    def clear_faults(self) -> None:
        self._faults.clear()

    def before_next_put(self, hook: Callable[[], None]) -> None:
        """Run hook inside the next put call, before the version check."""
        self._hooks.append(hook)

    def keys(self) -> list[str]:
        return sorted(self._rows)
