import json

from sqlalchemy import BLOB, JSON, Engine, TypeDecorator, create_engine
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.orm import Session, registry

from .config import DatabaseConfig
from .exceptions import EleanorException
from .typing import Optional

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
    engine: Engine

    def __init__(self, config: DatabaseConfig, *args, verbose: bool = False, **kwargs):
        self.engine = create_engine(str(config), echo=verbose)
        super().__init__(self.engine, *args, **kwargs)

    def setup(self) -> None:
        yeoman_registry.metadata.create_all(self.engine)

    def write(self, entity):
        with self as session:
            session.add(entity)
            session.commit()
