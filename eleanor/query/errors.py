# Each subclass below overrides ``__str__`` to drop the ``(code: None) `` prefix
# that ``EleanorError.__str__`` would otherwise add. EQL errors are
# user-facing diagnostics for query authors and don't carry an integer ``code``;
# the cleaner messages are intentional, even though they render differently
# from the rest of the ``EleanorError`` hierarchy.
from typing import override

from eleanor.exceptions import EleanorError


class ParseError(EleanorError):
    message: str
    position: int | None

    def __init__(self, message: str, *, position: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.position = position

    @override
    def __str__(self) -> str:
        if self.position is None:
            return self.message
        return f"{self.message} (position {self.position})"


class UnknownRowScopeError(EleanorError):
    shortname: str
    hint: str | None

    def __init__(self, shortname: str, *, hint: str | None = None) -> None:
        super().__init__(shortname)
        self.shortname = shortname
        self.hint = hint

    @override
    def __str__(self) -> str:
        if self.hint is None:
            return f'unknown row_scope "{self.shortname}"'
        return f'unknown row_scope "{self.shortname}" ({self.hint})'


class AmbiguousRowScopeError(EleanorError):
    shortname: str
    candidates: list[str]

    def __init__(self, shortname: str, candidates: list[str]) -> None:
        super().__init__(shortname, *candidates)
        self.shortname = shortname
        self.candidates = candidates

    @override
    def __str__(self) -> str:
        joined = ", ".join(self.candidates)
        return f'ambiguous row_scope "{self.shortname}" (candidates: {joined})'


class InvalidRowScopeError(EleanorError):
    path: str
    reason: str

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(path, reason)
        self.path = path
        self.reason = reason

    @override
    def __str__(self) -> str:
        return f'invalid row_scope "{self.path}": {self.reason}'


class InvalidPathError(EleanorError):
    path: str
    segment: str
    owner_type: type[object]

    def __init__(self, path: str, segment: str, owner_type: type[object]) -> None:
        super().__init__(path, segment, owner_type.__name__)
        self.path = path
        self.segment = segment
        self.owner_type = owner_type

    @override
    def __str__(self) -> str:
        return f'invalid path "{self.path}": segment "{self.segment}" is not valid on {self.owner_type.__name__}'


class InvalidFilterError(EleanorError):
    path: str
    segment: str
    predicate: str

    def __init__(self, path: str, segment: str, predicate: str) -> None:
        super().__init__(path, segment, predicate)
        self.path = path
        self.segment = segment
        self.predicate = predicate

    @override
    def __str__(self) -> str:
        return f'invalid filter "{self.predicate}" on segment "{self.segment}" in "{self.path}"'


class InvalidFilterValueError(EleanorError):
    path: str
    predicate: str
    value: str
    target_type: type[object]

    def __init__(self, path: str, predicate: str, value: str, target_type: type[object]) -> None:
        super().__init__(path, predicate, value, target_type.__name__)
        self.path = path
        self.predicate = predicate
        self.value = value
        self.target_type = target_type

    @override
    def __str__(self) -> str:
        return (
            f'invalid filter value "{self.value}" for predicate "{self.predicate}" '
            + f'in "{self.path}" (expected {self.target_type.__name__})'
        )


class UnknownScopeError(EleanorError):
    alias: str
    available: list[str]

    def __init__(self, alias: str, available: list[str]) -> None:
        super().__init__(alias, *available)
        self.alias = alias
        self.available = available

    @override
    def __str__(self) -> str:
        joined = ", ".join(self.available)
        return f'unknown scope alias "{self.alias}" (available: {joined})'


class AliasCollisionError(EleanorError):
    alias: str
    paths: list[str]

    def __init__(self, alias: str, paths: list[str]) -> None:
        super().__init__(alias, *paths)
        self.alias = alias
        self.paths = paths

    @override
    def __str__(self) -> str:
        joined = ", ".join(self.paths)
        return f'alias collision for "{self.alias}" at paths: {joined}'


class ColumnNameCollisionError(EleanorError):
    name: str
    paths: list[str]

    def __init__(self, name: str, paths: list[str]) -> None:
        super().__init__(name, *paths)
        self.name = name
        self.paths = paths

    @override
    def __str__(self) -> str:
        joined = ", ".join(self.paths)
        return f'column name collision for "{self.name}" at paths: {joined}'


class SplatUnknownFieldError(EleanorError):
    alias: str
    field: str
    available: list[str]

    def __init__(self, alias: str, field: str, available: list[str]) -> None:
        super().__init__(alias, field, *available)
        self.alias = alias
        self.field = field
        self.available = available

    @override
    def __str__(self) -> str:
        joined = ", ".join(self.available)
        return f'splat on "{self.alias}" requested unknown field "{self.field}" (available: {joined})'


class PresetScopeMissingError(EleanorError):
    preset: str
    missing_alias: str

    def __init__(self, preset: str, missing_alias: str) -> None:
        super().__init__(preset, missing_alias)
        self.preset = preset
        self.missing_alias = missing_alias

    @override
    def __str__(self) -> str:
        return f'preset "{self.preset}" requires missing alias "{self.missing_alias}"'


class UnknownPresetError(EleanorError):
    name: str

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    @override
    def __str__(self) -> str:
        return f'unknown preset "{self.name}"'


class InvalidMetaAccessorError(EleanorError):
    path: str
    accessor: str
    reason: str

    def __init__(self, path: str, accessor: str, reason: str) -> None:
        super().__init__(path, accessor, reason)
        self.path = path
        self.accessor = accessor
        self.reason = reason

    @override
    def __str__(self) -> str:
        return f'invalid meta-accessor "@{self.accessor}" in "{self.path}": {self.reason}'


class PathMissError(EleanorError):
    row_index: int
    column: str
    segment: str

    def __init__(self, row_index: int, column: str, segment: str) -> None:
        super().__init__(row_index, column, segment)
        self.row_index = row_index
        self.column = column
        self.segment = segment

    @override
    def __str__(self) -> str:
        return f'path miss at row {self.row_index}, column "{self.column}", segment "{self.segment}"'


class MultipleMatchError(EleanorError):
    path: str
    predicate: str
    match_count: int

    def __init__(self, path: str, predicate: str, match_count: int) -> None:
        super().__init__(path, predicate, match_count)
        self.path = path
        self.predicate = predicate
        self.match_count = match_count

    @override
    def __str__(self) -> str:
        return (
            f'multiple matches for predicate "{self.predicate}" in "{self.path}" ' + f"(match_count={self.match_count})"
        )
