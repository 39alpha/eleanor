from dataclasses import dataclass

from sqlalchemy import Column, ForeignKey, Integer, String, Table

from ..parameters import Parameter
from ..typing import Any, cast
from ..yeoman import JSONDict, reconstructor, yeoman_registry
from .registry import get_spec


@dataclass
class Settings(object):
    timeout: int | None

    def parameters(self) -> list[Parameter]:
        return []


@yeoman_registry.mapped_as_dataclass(kw_only=True)
class Config(object):
    __table__: Table = Table(
        'kernel',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), primary_key=True),
        Column('type', String, nullable=False),
        Column('settings', JSONDict, nullable=False),
    )

    type: str
    settings: Settings
    id: int | None = None

    @reconstructor
    def reconstruct(self) -> None:
        if isinstance(self.settings, dict):
            spec = get_spec(self.type)
            settings_dict = cast(dict[str, Any], self.settings)  # pyright: ignore[reportExplicitAny]
            self.settings = cast(Settings, spec.settings_from_dict(settings_dict))

    def parameters(self) -> list[Parameter]:
        return self.settings.parameters()
