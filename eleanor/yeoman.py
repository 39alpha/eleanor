import json

from sqlalchemy import BLOB, JSON, Engine, TypeDecorator, create_engine
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.orm import Session, registry

from .config import DatabaseConfig
from .exceptions import EleanorException
from .typing import Optional

engine: Engine | None = None
yeoman_registry = registry()


class JSONDict(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        match dialect.name:
            case 'postgresql':
                return dialect.type_descriptor(JSONB)
            case _:
                return dialect.type_descriptor(JSON)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        elif not isinstance(value, dict):
            raise EleanorException('cannot serialize non-dict to JSON')
        return json.loads(json.dumps(value, sort_keys=True, default=str))


class Binary(TypeDecorator):
    impl = BLOB
    cache_ok = True

    def load_dialect_impl(self, dialect):
        match dialect.name:
            case 'postgresql':
                return dialect.type_descriptor(BYTEA)
            case _:
                return dialect.type_descriptor(BLOB)


class Yeoman(Session):

    def __init__(self, *args, **kwargs):
        global engine

        if engine is None:
            raise EleanorException('cannot create Yeoman session without first setting up')

        super().__init__(engine, *args, **kwargs)

    @staticmethod
    def setup(config: DatabaseConfig, verbose: bool = False, **kwargs) -> None:
        global engine, yeoman_registry

        if engine is not None:
            raise EleanorException('cannot resetup Yeoman')

        engine = create_engine(str(config), echo=verbose)
        yeoman_registry.metadata.create_all(engine)

    @staticmethod
    def is_setup() -> bool:
        global engine
        return engine is not None

    @staticmethod
    def unsafe_engine() -> Optional[Engine]:
        global engine
        return engine

    @staticmethod
    def dispose(close: bool = False) -> None:
        global engine

        if engine is None:
            raise EleanorException('cannot dispose Yeoman before it is setup')

        engine.dispose(close=close)
