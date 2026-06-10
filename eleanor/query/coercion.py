import enum
from collections.abc import Callable
from typing import Literal, cast

import numpy as np

from eleanor.query.errors import InvalidFilterValueError, ParseError

type MissingPolicy = Literal["blank", "null", "error"]


def parse_missing_policy(value: object) -> MissingPolicy:
    if value == "blank":
        return "blank"
    if value == "null":
        return "null"
    if value == "error":
        return "error"
    msg = f"invalid missing policy: {value!r}"
    raise ParseError(msg, position=None)


def _coerce_bool(raw: str) -> bool:
    match raw.lower():
        case "true":
            return True
        case "false":
            return False
        case _:
            raise ValueError(raw)


def _coerce_enum(enum_target: type[enum.Enum], raw: str) -> enum.Enum:
    try:
        return enum_target[raw]
    except KeyError:
        pass

    for member in enum_target:
        value: object = cast(object, member.value)
        if value == raw or str(value) == raw:
            return member
    raise ValueError(raw)


_COERCERS: dict[type[object], Callable[[str], object]] = {
    str: lambda r: r,
    int: lambda r: int(r, base=10),
    float: np.float64,
    np.float64: np.float64,
    bool: _coerce_bool,
}


def coerce_filter_value(target: type[object], raw: str, *, path: str, predicate: str) -> object:
    coercer = _COERCERS.get(target)

    # ``isinstance(target, type)`` is defensive: the live pipeline narrows
    # ``target`` via ``reflection.coercion_target`` before calling here, so
    # ``target`` is always a ``type``. Without this guard, ``issubclass`` would
    # raise ``TypeError`` if a future caller ever passed a non-type (e.g., a
    # generic alias). basedpyright sees the typed signature and flags the
    # check as redundant; casting suppresses the diagnostic.
    if coercer is None and isinstance(cast(object, target), type) and issubclass(target, enum.Enum):

        def enum_coercer(r: str) -> enum.Enum:
            return _coerce_enum(target, r)

        coercer = enum_coercer

    if coercer is not None:
        try:
            return coercer(raw)
        except ValueError:
            pass

    raise InvalidFilterValueError(path, predicate, raw, target)
