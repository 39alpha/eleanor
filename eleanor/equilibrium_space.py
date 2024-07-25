from sqlalchemy import Column, ForeignKey, Integer, String, Table

from .typing import Any, Optional
from .yeoman import yeoman_registry


@yeoman_registry.mapped_as_dataclass
class Point(object):
    __table__ = Table(
        'equilibrium_space',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('variable_space_id', Integer, ForeignKey('variable_space.id')),
        Column('kernel', String, nullable=False),
    )

    __mapper_args__: dict[str, Any] = {
        'polymorphic_identity': 'equilibrium_space',
        'polymorphic_on': 'kernel',
    }

    id: Optional[int]
    variable_space_id: Optional[int]
    kernel: str
