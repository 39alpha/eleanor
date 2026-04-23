import json
from dataclasses import asdict, is_dataclass
from typing import final, override, cast

from sqlalchemy import BLOB, JSON
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine

from ....exceptions import EleanorException


@final
class JSONDict(TypeDecorator[dict[str, object] | None]):
    impl = JSON
    cache_ok = True

    @override
    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[object]:
        match dialect.name:
            case 'postgresql':
                return dialect.type_descriptor(cast(TypeEngine[object], JSONB))
            case _:
                return dialect.type_descriptor(cast(TypeEngine[object], JSON))

    @override
    def process_bind_param(self, value: object | None, dialect: Dialect) -> dict[str, object] | None:
        _ = dialect
        if value is None:
            return None
        if is_dataclass(value) and not isinstance(value, type):
            value = asdict(value)
        if not isinstance(value, dict):
            raise EleanorException('cannot serialize non-dict to JSON')
        return cast(dict[str, object], json.loads(json.dumps(value, sort_keys=True, default=str)))


@final
class Binary(TypeDecorator[bytes]):
    impl = BLOB
    cache_ok = True

    @override
    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[object]:
        match dialect.name:
            case 'postgresql':
                return dialect.type_descriptor(cast(TypeEngine[object], BYTEA))
            case _:
                return dialect.type_descriptor(cast(TypeEngine[object], BLOB))
