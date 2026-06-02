from dataclasses import dataclass

from eleanor.settings import Settings


@dataclass(kw_only=True)
class NavigatorSettings(Settings): ...


__all__ = ["NavigatorSettings"]
