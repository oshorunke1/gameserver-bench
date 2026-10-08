"""A clock the server reads instead of the wall clock, so replays stay deterministic."""


class ManualClock:
    def __init__(self, start=0.0):
        self._now = float(start)

    def now(self):
        return self._now

    def advance(self, seconds):
        self._now += seconds

    def set(self, value):
        self._now = float(value)
