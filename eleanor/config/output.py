from dataclasses import dataclass, field
from typing import Self, cast

from eleanor.config.plugin import PluginConfig
from eleanor.exceptions import EleanorError
from eleanor.output.registry import registry
from eleanor.output.settings import OutputSinkSettings
from eleanor.plugin import load_plugin_settings
from eleanor.util import require_str


@dataclass(kw_only=True)
class OutputSinkConfig(PluginConfig[OutputSinkSettings]):
    kind: str
    settings: OutputSinkSettings = field(default_factory=OutputSinkSettings)

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.settings), OutputSinkSettings):
            msg = f"output configuration requires {OutputSinkSettings.__name__}, got {type(self.settings).__name__}"
            raise EleanorError(msg)

        super().__post_init__()

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        kind = require_str(raw.get("kind"), "kind")
        settings_raw = {k: v for k, v in raw.items() if k != "kind"}
        settings = load_plugin_settings(registry, OutputSinkSettings, kind, settings_raw) or OutputSinkSettings()
        return cls(kind=kind, settings=settings)


__all__ = ["OutputSinkConfig"]
