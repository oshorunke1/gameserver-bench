"""A fake clock so tests can move time around without sleeping.

Every server in a test shares one SimClock. Time only moves when someone
calls advance() or set(), so nothing here ever depends on the real time.
"""


class SimClock:
    def __init__(self, start: float = 0.0):
        self._now = float(start)

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> float:
        if seconds < 0:
            raise ValueError("time only goes forward")
        self._now += float(seconds)
        return self._now

    def set(self, when: float) -> float:
        if when < self._now:
            raise ValueError("time only goes forward")
        self._now = float(when)
        return self._now
