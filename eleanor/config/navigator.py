from dataclasses import dataclass, field
from typing import Self, cast

from eleanor.config.plugin import PluginConfig
from eleanor.exceptions import EleanorException
from eleanor.navigator.registry import registry
from eleanor.navigator.settings import NavigatorSettings
from eleanor.plugin import load_plugin_settings
from eleanor.util import require_opt_str


@dataclass(kw_only=True)
class NavigatorConfig(PluginConfig[NavigatorSettings]):
    kind: str = "random"
    settings: NavigatorSettings = field(default_factory=NavigatorSettings)

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.settings), NavigatorSettings):
            msg = f"navigator configuration requires NavigatorSettings, got {type(self.settings).__name__}"
            raise EleanorException(msg)

        super().__post_init__()

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        kind = require_opt_str(raw.get("kind"), "navigator.kind") or "random"
        settings_raw = {k: v for k, v in raw.items() if k != "kind"}
        settings = load_plugin_settings(registry, NavigatorSettings, kind, settings_raw) or NavigatorSettings()
        return cls(kind=kind, settings=settings)


__all__ = ["NavigatorConfig"]
