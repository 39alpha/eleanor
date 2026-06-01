from dataclasses import dataclass
from typing import Self

from eleanor.settings import Settings as DefaultSettings
from eleanor.util import guard_is_bool, require_bool


@dataclass(kw_only=True)
class Settings(DefaultSettings):
    verbose: bool = False

    def __post_init__(self) -> None:
        guard_is_bool(self.verbose, "verbose")

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        verbose = require_bool(raw.get("verbose", False), "verbose")
        return cls(verbose=verbose)


__all__ = ["Settings"]
