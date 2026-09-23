from dataclasses import dataclass
from typing import Self, cast

from eleanor.config.plugin import PluginConfig
from eleanor.exceptions import EleanorError
from eleanor.kernel.registry import registry
from eleanor.kernel.settings import KernelSettings
from eleanor.plugin import load_plugin_settings
from eleanor.util import require_dict, require_str


@dataclass(kw_only=True)
class KernelConfig(PluginConfig[KernelSettings]):
    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.settings), KernelSettings):
            msg = f"kernel configuration requires {KernelSettings.__name__}, got {type(self.settings).__name__}"
            raise EleanorError(msg)

        super().__post_init__()

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        kind = require_str(raw.get("kind"), "kind")
        if "settings" in raw:
            if set(raw) - {"kind", "settings"}:
                msg = "kernel configuration cannot mix flat and nested settings"
                raise EleanorError(msg)
            settings_raw: dict[str, object] = require_dict(raw["settings"], "settings")
        else:
            settings_raw = {k: v for k, v in raw.items() if k != "kind"}
        settings = load_plugin_settings(registry, KernelSettings, kind, settings_raw) or KernelSettings()
        return cls(kind=kind, settings=settings)


__all__ = ["KernelConfig"]
