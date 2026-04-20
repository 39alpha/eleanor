from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Column, ForeignKey, Integer, String, Table

from ..parameters import Parameter
from ..typing import cast
from ..yeoman import JSONDict, reconstructor, yeoman_registry
from .discover import import_kernel_module


@dataclass
class Settings(object):
    timeout: int | None

    def parameters(self) -> list[Parameter]:
        return []
class SettingsClass(Protocol):
    @staticmethod
    def from_dict(raw: dict[str, object]) -> Settings:
        ...


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
            kernel_module = import_kernel_module(self.type)
            settings_cls = cast(SettingsClass, getattr(kernel_module, 'Settings'))
            self.settings = settings_cls.from_dict(cast(dict[str, object], self.settings))

    def parameters(self) -> list[Parameter]:
        return self.settings.parameters()
