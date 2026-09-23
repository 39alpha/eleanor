import secrets
from dataclasses import dataclass
from typing import Self

from eleanor.settings import Settings
from eleanor.util import guard_is_int, require_opt_int


@dataclass(kw_only=True)
class NavigatorSettings(Settings): ...


@dataclass(init=False)
class SeedableNavigatorSettings(NavigatorSettings):
    seed: int

    def __init__(self, *, seed: int | None = None) -> None:
        super().__init__()
        self.seed = seed if seed is not None else secrets.randbits(63)
        guard_is_int(self.seed, "seed")

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        seed = require_opt_int(raw.get("seed"), "seed")
        return cls(seed=seed)


__all__ = [
    "NavigatorSettings",
    "SeedableNavigatorSettings",
]
