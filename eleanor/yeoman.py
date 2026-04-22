import json
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from typing import final, override, cast

import sqlalchemy.orm
from sqlalchemy import BLOB, JSON, ColumnElement, Engine, create_engine
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Session, registry
from sqlalchemy.types import TypeDecorator, TypeEngine

from .connection import DatabaseConfig
from .exceptions import EleanorException

yeoman_registry = registry()


def column_expr(expr: object) -> ColumnElement[bool]:
    """Cast a SQLAlchemy comparison expression to ``ColumnElement[bool]``.

    The bundled SQLAlchemy stubs type ``Column.__eq__``/``__ne__`` as returning
    ``bool`` even though at runtime they return ``ColumnElement``. This helper
    re-types the result so it can be passed to ``select().where(...)`` and
    ``and_(...)`` without triggering type-checker errors at every call site.
    """
    return cast(ColumnElement[bool], expr)

# SQLAlchemy's ``reconstructor`` decorator is untyped in the bundled stubs,
# which causes static type checkers to treat decorated methods as partially
# unknown. Pin the name once here via ``getattr`` + ``cast`` so the rest of the
# codebase can use a fully-typed ``reconstructor``.
_sa_reconstructor = cast(
    Callable[[Callable[..., object]], Callable[..., object]],
    getattr(sqlalchemy.orm, 'reconstructor'),
)


def reconstructor[F: Callable[..., object]](fn: F) -> F:
    """Typed wrapper around :func:`sqlalchemy.orm.reconstructor`.

    SQLAlchemy's :func:`reconstructor` is untyped, which causes static type
    checkers to report the decorated method's type as partially unknown. This
    thin wrapper preserves the decorated function's signature.
    """
    return cast(F, _sa_reconstructor(fn))


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
        elif is_dataclass(value) and not isinstance(value, type):
            value = asdict(value)
        elif not isinstance(value, dict):
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


class Yeoman(Session):
    engine: Engine

    def __init__(self, config: DatabaseConfig, *args: object, verbose: bool = False, **kwargs: object):
        if config.sslmode is not None:
            self.engine = create_engine(str(config), connect_args={'sslmode': config.sslmode}, echo=verbose)
        else:
            self.engine = create_engine(str(config), echo=verbose)
        super().__init__(self.engine, *args, **kwargs)

    @override
    def __exit__(self, *args: object, **kwargs: object) -> None:
        super().__exit__(*args, **kwargs)
        self.engine.dispose()

    def setup(self) -> None:
        yeoman_registry.metadata.create_all(self.engine)

    def write(self, entity: object, refresh: bool = False) -> None:
        with self as session:
            session.add(entity)
            session.commit()
            if refresh:
                session.refresh(entity)
