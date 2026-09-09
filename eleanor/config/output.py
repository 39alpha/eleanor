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
    name: str = ""
    settings: OutputSinkSettings = field(default_factory=OutputSinkSettings)

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.settings), OutputSinkSettings):
            msg = f"output configuration requires {OutputSinkSettings.__name__}, got {type(self.settings).__name__}"
            raise EleanorError(msg)

        if not self.name:
            self.name = self.kind

        super().__post_init__()

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        kind = require_str(raw.get("kind"), "kind")
        name = require_str(raw.get("name", kind), "name")
        settings_raw = {k: v for k, v in raw.items() if k not in {"kind", "name"}}
        settings = load_plugin_settings(registry, OutputSinkSettings, kind, settings_raw) or OutputSinkSettings()
        return cls(kind=kind, name=name, settings=settings)


__all__ = ["OutputSinkConfig"]
