from dataclasses import dataclass
from typing import Self, cast

from eleanor.config.plugin import PluginConfig
from eleanor.exceptions import EleanorError
from eleanor.navigator.registry import registry
from eleanor.navigator.settings import NavigatorSettings
from eleanor.plugin import load_plugin_settings
from eleanor.util import require_dict, require_opt_str


@dataclass(init=False)
class NavigatorConfig(PluginConfig[NavigatorSettings]):
    def __init__(self, *, kind: str = "random", settings: NavigatorSettings | None = None) -> None:
        loaded_settings = (
            settings
            if settings is not None
            else load_plugin_settings(registry, NavigatorSettings, kind, {}) or NavigatorSettings()
        )

        super().__init__(kind=kind, settings=loaded_settings)

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.settings), NavigatorSettings):
            msg = f"navigator configuration requires NavigatorSettings, got {type(self.settings).__name__}"
            raise EleanorError(msg)

        super().__post_init__()

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        kind = require_opt_str(raw.get("kind"), "navigator.kind") or "random"
        if "settings" in raw:
            if set(raw) - {"kind", "settings"}:
                msg = "navigator configuration cannot mix flat and nested settings"
                raise EleanorError(msg)
            settings_raw: dict[str, object] = require_dict(raw["settings"], "settings")
        else:
            settings_raw = {k: v for k, v in raw.items() if k != "kind"}

        settings = load_plugin_settings(registry, NavigatorSettings, kind, settings_raw) or NavigatorSettings()
        return cls(kind=kind, settings=settings)


__all__ = ["NavigatorConfig"]
