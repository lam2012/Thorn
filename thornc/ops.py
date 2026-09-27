"""In-memory catalog operations for the M3 runtime (stdlib only)."""

import random
from dataclasses import dataclass, field


@dataclass
class World:
    out: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    instant: str = ""
    rng: random.Random | None = field(default_factory=random.Random)

    @classmethod
    def make(cls, inputs: list[str], instant: str, seed: int | None) -> "World":
        rng = random.Random(seed) if seed is not None else None
        return cls([], list(inputs), instant, rng)
