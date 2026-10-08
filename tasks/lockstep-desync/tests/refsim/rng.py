"""Tiny seeded RNG so every peer rolls the same numbers.

It's splitmix64. We don't use the random module for sim stuff because
its output isn't something we want to bet a desync on.
"""

MASK64 = (1 << 64) - 1


class Rng:
    def __init__(self, seed):
        self.state = seed & MASK64

    def next_u64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
        return z ^ (z >> 31)

    def random(self):
        # 53 random bits mapped into [0, 1)
        return (self.next_u64() >> 11) * (1.0 / (1 << 53))
