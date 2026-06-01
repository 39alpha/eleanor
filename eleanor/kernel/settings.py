from dataclasses import dataclass

from eleanor.settings import Settings as DefaultSettings


@dataclass(kw_only=True)
class Settings(DefaultSettings):
    timeout: int | None = None


__all__ = ["Settings"]
