from dataclasses import dataclass

from eleanor.settings import Settings


@dataclass(kw_only=True)
class KernelSettings(Settings):
    timeout: int | None = None


__all__ = ["KernelSettings"]
