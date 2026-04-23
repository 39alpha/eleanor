from typing import Protocol, TextIO

from sqlalchemy import create_mock_engine

from ....connection import DatabaseConfig
from ..persistence import models
from ..persistence.registry import postgres_registry


class _Compilable(Protocol):
    def compile(self) -> object:
        ...


def dump_schema(config: DatabaseConfig, stream: TextIO) -> None:
    def dump(sql: _Compilable, *_multiparams: object, **_params: object) -> None:
        print(sql.compile(), file=stream)

    engine = create_mock_engine(str(config), dump)
    _ = models
    postgres_registry.metadata.create_all(engine)
