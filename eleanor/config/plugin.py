from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from eleanor.exceptions import EleanorException
from eleanor.settings import SettingsLike
from eleanor.util import guard_is_str

if TYPE_CHECKING:
    from eleanor.parameters import Parameter


@dataclass(kw_only=True)
class PluginConfig[T: SettingsLike]:
    kind: str
    settings: T

    def __post_init__(self) -> None:
        guard_is_str(self.kind, "kind")

        if not isinstance(cast(object, self.settings), SettingsLike):
            got = type(self.settings).__name__
            msg = f"plugin settings must implement SettingsLike, got {got}"
            raise EleanorException(msg)

    def parameters(self) -> list[Parameter]:
        return self.settings.parameters()


__all__ = [
    "PluginConfig",
]
