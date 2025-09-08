from dataclasses import dataclass

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import reconstructor

from ..parameters import Parameter
from ..typing import Any, Optional
from ..yeoman import JSONDict, yeoman_registry
from .discover import import_kernel_module


@dataclass
class Settings(object):
    timeout: Optional[int]

    def parameters(self) -> list[Parameter]:
        return []


@yeoman_registry.mapped_as_dataclass(kw_only=True)
class Config(object):
    __table__ = Table(
        'kernel',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('variable_space.id', ondelete="CASCADE"), primary_key=True),
        Column('type', String, nullable=False),
        Column('settings', JSONDict, nullable=False),
    )

    type: str
    settings: Settings
    id: Optional[int] = None

    @reconstructor
    def reconstruct(self):
        if isinstance(self.settings, dict):
            kernel_module = import_kernel_module(self.type)
            self.settings = kernel_module.Settings.from_dict(self.settings)

    def parameters(self) -> list[Parameter]:
        return self.settings.parameters()
