"""Path parsing for EQL.

The parser is a single-pass recursive-descent parser with an integrated
tokenizer. It mirrors the grammar in spec §4:

Path      ::= Segment ( "." Segment )* [ "." Meta ]
Segment   ::= Identifier Filter*
Meta      ::= "@" Identifier
Filter    ::= "[" ("*" | Predicate ("," Predicate)*) "]"
Predicate ::= Identifier "=" Value
Value     ::= Unquoted | QuotedString
"""

from dataclasses import dataclass
from typing import NewType

from eleanor.query.errors import ParseError

Identifier = NewType("Identifier", str)


@dataclass(frozen=True, slots=True)
class Predicate:
    field: str
    value: str
    value_quoted: bool


@dataclass(frozen=True, slots=True)
class IterFilter:
    pass


@dataclass(frozen=True, slots=True)
class MatchFilter:
    predicates: tuple[Predicate, ...]


type Filter = IterFilter | MatchFilter


@dataclass(frozen=True, slots=True)
class Segment:
    name: str
    filters: tuple[Filter, ...]


@dataclass(frozen=True, slots=True)
class MetaSegment:
    """Spec §4/§7.1: terminal `@<name>` meta-accessor pseudo-segment.

    `name` is the bare identifier after the `@` (e.g. ``"index"``, ``"key"``).
    Validity of `name` against the closed set of canonical accessors and
    against the head alias's iter-binding is enforced at compile time, not
    here; the parser only checks the surface grammar.
    """

    name: str


@dataclass(frozen=True, slots=True)
class Path:
    segments: tuple[Segment, ...]
    meta: MetaSegment | None = None


class _Parser:
    text: str
    position: int

    def __init__(self, text: str):
        self.text = text
        self.position = 0

    def parse(self) -> Path:
        self._skip_ws()
        if self._at_end():
            raise ParseError("expected identifier", position=self.position)

        segments: list[Segment] = [self._parse_segment()]
        meta: MetaSegment | None = None
        while True:
            self._skip_ws()
            if self._peek() != ".":
                break
            dot_pos = self.position
            self.position += 1
            self._skip_ws()
            if self._at_end():
                raise ParseError("trailing '.'", position=dot_pos)
            if self._peek() == "@":
                # ``@<ident>`` is a terminal-only meta-accessor (spec §4).
                # Parse it and break; any further input is rejected as a
                # trailing-character error by the post-loop check.
                meta = self._parse_meta()
                break
            segments.append(self._parse_segment())

        self._skip_ws()
        if not self._at_end():
            current = self._peek()
            assert current is not None
            raise ParseError(f"unexpected character {current!r}", position=self.position)

        return Path(tuple(segments), meta=meta)

    def _parse_meta(self) -> MetaSegment:
        self._consume("@")
        name = self._parse_identifier()
        return MetaSegment(name=name)

    def _parse_segment(self) -> Segment:
        name = self._parse_identifier()
        filters: list[Filter] = []

        while True:
            self._skip_ws()
            if self._peek() != "[":
                break
            parsed = self._parse_filter()
            if isinstance(parsed, MatchFilter) and filters and isinstance(filters[-1], MatchFilter):
                merged = MatchFilter(predicates=filters[-1].predicates + parsed.predicates)
                filters[-1] = merged
            else:
                filters.append(parsed)

        return Segment(name=name, filters=tuple(filters))

    def _parse_filter(self) -> Filter:
        open_pos = self.position
        self._consume("[")
        self._skip_ws()

        current = self._peek()
        if current is None:
            raise ParseError("unterminated filter", position=open_pos)
        if current == "]":
            raise ParseError("empty filter is not allowed", position=self.position)
        if current == "*":
            self.position += 1
            self._skip_ws()
            self._consume("]")
            return IterFilter()

        predicates: list[Predicate] = [self._parse_predicate()]
        while True:
            self._skip_ws()
            current = self._peek()
            if current == ",":
                self.position += 1
                predicates.append(self._parse_predicate())
                continue
            if current == "]":
                self.position += 1
                break
            if current is None:
                raise ParseError("unterminated filter", position=open_pos)
            raise ParseError(f"unexpected character {current!r} in filter", position=self.position)

        return MatchFilter(predicates=tuple(predicates))

    def _parse_predicate(self) -> Predicate:
        field = self._parse_identifier()
        self._skip_ws()
        self._consume("=")
        value, quoted = self._parse_value()
        return Predicate(field=field, value=value, value_quoted=quoted)

    def _parse_value(self) -> tuple[str, bool]:
        self._skip_ws()
        current = self._peek()
        if current is None:
            raise ParseError("expected value", position=self.position)
        if current == '"':
            return self._parse_quoted_string()

        start = self.position
        while not self._at_end():
            current = self._peek()
            # _peek() can only be None when _at_end() is True, so the loop
            # guard above guarantees current is not None here.
            assert current is not None
            if current.isspace() or current in '=,]"':
                break
            self.position += 1

        if start == self.position:
            raise ParseError("expected value", position=self.position)

        return self.text[start : self.position], False

    def _parse_quoted_string(self) -> tuple[str, bool]:
        start = self.position
        self._consume('"')
        parts: list[str] = []
        while not self._at_end():
            current = self._peek()
            assert current is not None
            if current == '"':
                self.position += 1
                return "".join(parts), True
            if current == "\\":
                escape_pos = self.position
                self.position += 1
                escaped = self._peek()
                if escaped is None:
                    raise ParseError("unterminated escape sequence", position=escape_pos)
                if escaped in ('"', "\\"):
                    parts.append(escaped)
                    self.position += 1
                    continue
                raise ParseError(f"invalid escape sequence '\\{escaped}'", position=escape_pos)
            parts.append(current)
            self.position += 1

        raise ParseError("unterminated quoted string", position=start)

    def _parse_identifier(self) -> str:
        self._skip_ws()
        current = self._peek()
        if current is None:
            raise ParseError("expected identifier", position=self.position)
        if not (current.isalpha() or current == "_"):
            raise ParseError("expected identifier", position=self.position)

        start = self.position
        self.position += 1
        while not self._at_end():
            current = self._peek()
            # _peek() can only be None when _at_end() is True, so the loop
            # guard above guarantees current is not None here.
            assert current is not None
            if not (current.isalnum() or current == "_"):
                break
            self.position += 1
        return self.text[start : self.position]

    def _consume(self, expected: str) -> None:
        current = self._peek()
        if current != expected:
            if current is None:
                raise ParseError(f"expected {expected!r}", position=self.position)
            raise ParseError(f"expected {expected!r}, found {current!r}", position=self.position)
        self.position += 1

    def _skip_ws(self) -> None:
        while not self._at_end():
            current = self._peek()
            if current is None or not current.isspace():
                return
            self.position += 1

    def _peek(self) -> str | None:
        if self.position >= len(self.text):
            return None
        return self.text[self.position]

    def _at_end(self) -> bool:
        return self.position >= len(self.text)


def parse_path(text: str) -> Path:
    parser = _Parser(text)
    return parser.parse()


def parse_row_scope(text: str) -> Identifier | Path:
    parsed = parse_path(text)
    if parsed.meta is not None:
        raise ParseError(
            "meta-accessors (@index, @key) are not valid in row_scope position",
            position=None,
        )
    if len(parsed.segments) == 1 and len(parsed.segments[0].filters) == 0:
        return Identifier(parsed.segments[0].name)
    return parsed


def path_to_string(path: Path) -> str:
    parts: list[str] = []
    for segment in path.segments:
        filter_text = "".join(_filter_to_string(item) for item in segment.filters)
        parts.append(f"{segment.name}{filter_text}")
    base = ".".join(parts)
    if path.meta is None:
        return base
    if not base:
        # Defensive: a meta with zero segments shouldn't reach here via the
        # parser, but render reasonably if a caller constructs one directly.
        return f"@{path.meta.name}"
    return f"{base}.@{path.meta.name}"


def predicate_text(predicate: Predicate) -> str:
    """Render a predicate as ``field=value`` (or ``field="quoted"``) text.

    Used both by ``path_to_string`` for canonical path stringification and by
    error messages in ``reflection`` and ``compiler``. The two callers want
    the predicate text without surrounding ``[...]`` brackets.
    """
    if predicate.value_quoted:
        escaped = predicate.value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{predicate.field}="{escaped}"'
    return f"{predicate.field}={predicate.value}"


def quote_predicate_value(value: str) -> str:
    """Return ``value`` in the form a path predicate can safely embed it in.

    Returns the value verbatim when every character is legal under the
    ``Unquoted`` production (spec §4: any character except whitespace, ``=``,
    ``,``, ``]``, or ``"``). Otherwise returns a quoted-string literal with
    ``\\`` and ``"`` escaped, so the result always round-trips through
    ``parse_path``. The empty string is always quoted, since ``field=`` is
    not a valid bare predicate.
    """
    if value and all(not (c.isspace() or c in '=,]"') for c in value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def match_filter_text(filter_expr: MatchFilter) -> str:
    """Render a match filter's predicates as comma-joined text without brackets.

    Used by ``InvalidFilter`` error messages in ``reflection`` and ``compiler``.
    Note that this is intentionally bracketless; ``_filter_to_string`` is the
    canonical bracketed form used by ``path_to_string``.
    """
    return ",".join(predicate_text(predicate) for predicate in filter_expr.predicates)


def _filter_to_string(filter_expr: Filter) -> str:
    if isinstance(filter_expr, IterFilter):
        return "[*]"
    return f"[{match_filter_text(filter_expr)}]"
