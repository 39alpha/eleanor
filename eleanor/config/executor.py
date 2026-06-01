from dataclasses import dataclass, field
from typing import Self, cast

from eleanor.config.plugin import PluginConfig
from eleanor.exceptions import EleanorException
from eleanor.executor.registry import registry
from eleanor.executor.settings import Settings
from eleanor.plugin import load_plugin_settings
from eleanor.util import require_opt_str


@dataclass(kw_only=True)
class Config(PluginConfig[Settings]):
    kind: str = "multiprocessing"
    settings: Settings = field(default_factory=Settings)

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.settings), Settings):
            msg = f"executor configuration requires Settings, got {type(self.settings).__name__}"
            raise EleanorException(msg)

        super().__post_init__()

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Self:
        kind = require_opt_str(raw.get("kind"), "executor.kind") or "multiprocessing"
        settings_raw = {k: v for k, v in raw.items() if k != "kind"}
        settings = load_plugin_settings(registry, Settings, kind, settings_raw) or Settings()
        return cls(kind=kind, settings=settings)


__all__ = ["Config"]
