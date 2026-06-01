from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from eleanor.parameters import Parameter


@runtime_checkable
class SettingsLike(Protocol):
    def parameters(self) -> list[Parameter]: ...


@dataclass(kw_only=True)
class Settings:
    def parameters(self) -> list[Parameter]:
        return []
