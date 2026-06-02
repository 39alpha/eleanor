import enum
from typing import Literal

import numpy as np

from eleanor.query.errors import InvalidFilterValue, ParseError

type MissingPolicy = Literal["blank", "null", "error"]


def parse_missing_policy(value: object) -> MissingPolicy:
    if value == "blank":
        return "blank"
    if value == "null":
        return "null"
    if value == "error":
        return "error"
    raise ParseError(f"invalid missing policy: {value!r}", position=None)


def coerce_filter_value(target: type[object], raw: str, *, path: str, predicate: str) -> object:
    if target is str:
        return raw

    if target is int:
        try:
            return int(raw, base=10)
        except ValueError as exc:
            raise InvalidFilterValue(path, predicate, raw, target) from exc

    if target is float or target is np.float64:
        try:
            return np.float64(raw)
        except ValueError as exc:
            raise InvalidFilterValue(path, predicate, raw, target) from exc

    if target is bool:
        lowered = raw.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        raise InvalidFilterValue(path, predicate, raw, target)

    # ``isinstance(target, type)`` is defensive: the live pipeline narrows
    # ``target`` via ``reflection.coercion_target`` before calling here, so
    # ``target`` is always a ``type``. Without this guard, ``issubclass`` would
    # raise ``TypeError`` if a future caller ever passed a non-type (e.g., a
    # generic alias). basedpyright sees the typed signature and flags the
    # check as redundant; suppressing keeps the runtime contract explicit.
    if isinstance(target, type) and issubclass(target, enum.Enum):  # pyright: ignore[reportUnnecessaryIsInstance]
        enum_target: type[enum.Enum] = target
        try:
            return enum_target[raw]
        except KeyError:
            pass

        for member in enum_target:
            value: object = member.value  # pyright: ignore[reportAny]
            if value == raw or str(value) == raw:
                return member

        raise InvalidFilterValue(path, predicate, raw, target)

    raise InvalidFilterValue(path, predicate, raw, target)
