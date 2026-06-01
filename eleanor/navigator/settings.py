from dataclasses import dataclass

from eleanor.settings import Settings as DefaultSettings


@dataclass(kw_only=True)
class Settings(DefaultSettings): ...


__all__ = ["Settings"]
