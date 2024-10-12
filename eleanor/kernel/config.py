from sqlalchemy import Column, ForeignKey, Integer, String, Table

from ..parameters import Parameter
from ..typing import Any, Optional
from ..yeoman import yeoman_registry


@yeoman_registry.mapped_as_dataclass
class Config(object):
    __table__ = Table(
        'kernel',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('variable_space.id'), primary_key=True),
        Column('type', String, nullable=False),
        Column('timeout', Integer, nullable=True),
    )

    __mapper_args__: dict[str, Any] = {
        'polymorphic_identity': 'kernel',
        'polymorphic_on': 'type',
    }

    id: Optional[int]
    type: str
    timeout: Optional[int]

    def parameters(self) -> list[Parameter]:
        return []
