from sqlalchemy import Column, ForeignKey, Integer, String, Table

from eleanor.config.parameter import Parameter
from eleanor.typing import Any, Optional
from eleanor.yeoman import yeoman_registry


@yeoman_registry.mapped_as_dataclass
class Config(object):
    __table__ = Table(
        'kernel',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('vs.id'), primary_key=True),
        Column('type', String, nullable=False),
    )

    __mapper_args__: dict[str, Any] = {
        'polymorphic_identity': 'kernel',
        'polymorphic_on': 'type',
    }

    id: Optional[int]
    type: str

    def parameters(self) -> list[Parameter]:
        return []
