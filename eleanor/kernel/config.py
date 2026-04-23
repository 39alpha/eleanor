from dataclasses import dataclass

from ..exceptions import EleanorException
from ..parameters import Parameter


@dataclass
class Settings(object):
    timeout: int | None

    def parameters(self) -> list[Parameter]:
        return []

@dataclass(kw_only=True)
class Config(object):
    type: str
    settings: Settings | dict[str, object]

    def resolved_settings(self) -> Settings:
        if not isinstance(self.settings, Settings):
            raise EleanorException(
                f'kernel.settings has unexpected type {type(self.settings).__name__}',
            )
        return self.settings

    def parameters(self) -> list[Parameter]:
        return self.resolved_settings().parameters()
