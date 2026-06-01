from dataclasses import dataclass
from typing import Self, cast

from eleanor.config.plugin import PluginConfig
from eleanor.exceptions import EleanorException
from eleanor.kernel.registry import registry
from eleanor.kernel.settings import Settings
from eleanor.plugin import load_plugin_settings
from eleanor.util import require_str


@dataclass(kw_only=True)
class Config(PluginConfig[Settings]):
    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.settings), Settings):
            msg = f"kernel configuration requires Settings, got {type(self.settings).__name__}"
            raise EleanorException(msg)

        super().__post_init__()

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        kind = require_str(raw.get("kind"), "kind")
        settings_raw = {k: v for k, v in raw.items() if k != "kind"}
        settings = load_plugin_settings(registry, Settings, kind, settings_raw) or Settings()
        return cls(kind=kind, settings=settings)


__all__ = ["Config"]
