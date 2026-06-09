from collections import deque
from dataclasses import dataclass

from eleanor.query.aliases import SHORT_FORM_INVERSE, aliases_for, singularize
from eleanor.query.errors import (
    AliasCollision,
    AmbiguousRowScope,
    InvalidRowScope,
    ParseError,
    PresetScopeMissing,
    UnknownRowScope,
)
from eleanor.query.path import IterFilter, Path, Segment, parse_row_scope, path_to_string
from eleanor.query.reflection import (
    DataclassField,
    DictField,
    FieldKind,
    LeafField,
    ListField,
    StepInfo,
    dataclass_fields,
    walk_path,
)

# Default depth limit for ``enumerate_shortname_paths`` BFS. Sized to comfortably
# cover Eleanor's real ``Order`` dataclass field graph plus collection wrappers,
# while still bounding the walk against pathological/recursive type graphs.
# Increase only with a corresponding test exercising the new depth.
_DEFAULT_SHORTNAME_MAX_DEPTH: int = 8


@dataclass(frozen=True, slots=True)
class AmbientScope:
    alias: str
    path: Path
    type_kind: FieldKind
    terminal: bool
    # Container kind that an iter filter (``[*]``) was applied to in order
    # to bind this alias. ``None`` for non-iter-bound aliases (root,
    # match-bound, and intermediate dataclass aliases). ``ListField`` for
    # list-iter aliases, ``DictField`` for dict-iter aliases. Spec §7.1
    # meta-accessor validation reads this to decide whether ``@key`` is
    # legal.
    iter_source_kind: ListField | DictField | None = None


class AmbientScopeTable:
    _scopes: dict[str, AmbientScope]

    def __init__(self) -> None:
        self._scopes = {}

    def __contains__(self, alias: str) -> bool:
        return alias in self._scopes

    def __getitem__(self, alias: str) -> AmbientScope:
        return self._scopes[alias]

    def add(
        self,
        alias: str,
        path: Path,
        type_kind: FieldKind,
        *,
        terminal: bool,
        iter_source_kind: ListField | DictField | None = None,
    ) -> None:
        existing = self._scopes.get(alias)
        if existing is None:
            self._scopes[alias] = AmbientScope(
                alias=alias,
                path=path,
                type_kind=type_kind,
                terminal=terminal,
                iter_source_kind=iter_source_kind,
            )
            return

        if existing.path != path:
            raise AliasCollision(alias, [path_to_string(existing.path), path_to_string(path)])

        # Re-add at the same path: ``terminal=True`` upgrades, and an
        # ``iter_source_kind`` argument fills in a previously-None binding.
        # The first non-None ``iter_source_kind`` wins; once recorded, it is
        # never overwritten. ``resolve_row_scope`` may invoke ``add`` for
        # the same alias both inside the per-step loop and again via the
        # post-loop terminal block, so this merge keeps both calls coherent.
        new_terminal = existing.terminal or terminal
        new_iter = existing.iter_source_kind if existing.iter_source_kind is not None else iter_source_kind
        if new_terminal == existing.terminal and new_iter is existing.iter_source_kind:
            return
        self._scopes[alias] = AmbientScope(
            alias=alias,
            path=existing.path,
            type_kind=existing.type_kind,
            terminal=new_terminal,
            iter_source_kind=new_iter,
        )

    def items(self) -> list[tuple[str, AmbientScope]]:
        return list(self._scopes.items())

    def available_aliases(self) -> list[str]:
        return sorted(self._scopes.keys())

    def require(self, preset: str, alias: str) -> AmbientScope:
        scope = self._scopes.get(alias)
        if scope is None:
            raise PresetScopeMissing(preset, alias)
        return scope


def enumerate_shortname_paths(
    root_type: type[object], shortname: str, *, max_depth: int = _DEFAULT_SHORTNAME_MAX_DEPTH
) -> list[Path]:
    """Enumerate every dataclass-tree path whose terminal alias matches ``shortname``.

    The BFS walks dataclass fields under ``root_type`` and stops at the
    ``max_depth`` boundary; the default of ``_DEFAULT_SHORTNAME_MAX_DEPTH``
    is sized for the real ``Order`` tree. Use ``_enumerate_with_diagnostic``
    if the caller needs to know whether the cap was hit.
    """
    candidates, _ = _enumerate_with_diagnostic(root_type, shortname, max_depth=max_depth)
    return candidates


def _enumerate_with_diagnostic(root_type: type[object], shortname: str, *, max_depth: int) -> tuple[list[Path], bool]:
    """BFS implementation of ``enumerate_shortname_paths`` plus a cap-hit flag.

    Returns ``(candidates, cap_hit)`` where ``cap_hit`` is ``True`` if any
    queued state was discarded for exceeding ``max_depth``. Callers can use
    this to surface a diagnostic when a shortname produces no candidates and
    the depth cap was the reason.
    """
    candidates: list[Path] = []
    cap_hit = False
    queue: deque[tuple[type[object], Path, tuple[str, ...], int]] = deque()
    queue.append((root_type, Path(segments=()), (), 0))
    visited: set[tuple[type[object], tuple[str, ...]]] = {(root_type, ())}
    seen_paths: set[str] = set()

    while queue:
        current_type, current_path, alias_chain, depth = queue.popleft()
        if depth >= max_depth:
            cap_hit = True
            continue

        for field in dataclass_fields(current_type):
            if isinstance(field, LeafField):
                continue
            if isinstance(field, DataclassField):
                segment = Segment(name=field.name, filters=())
                next_kind = field
            elif isinstance(field, ListField):
                segment = Segment(name=field.name, filters=(IterFilter(),))
                next_kind = field.element_kind
            else:
                segment = Segment(name=field.name, filters=(IterFilter(),))
                next_kind = field.value_kind

            next_path = Path(segments=current_path.segments + (segment,))
            default_alias = aliases_for(field.name)[0]
            if shortname in aliases_for(field.name):
                serialized = path_to_string(next_path)
                if serialized not in seen_paths:
                    seen_paths.add(serialized)
                    candidates.append(next_path)
            if not isinstance(next_kind, DataclassField):
                continue

            next_alias_chain = alias_chain + (default_alias,)
            state = (next_kind.dataclass_type, next_alias_chain)
            if state in visited:
                continue
            visited.add(state)
            queue.append((next_kind.dataclass_type, next_path, next_alias_chain, depth + 1))

    return candidates, cap_hit


def validate_short_forms_for_root(root_type: type[object]) -> None:
    """Verify ``root_type``'s dataclass tree has no field whose default alias
    collides with a registered short-form value.

    Walks every reachable dataclass field under ``root_type`` and computes its
    default alias via ``singularize``. If any default alias matches a value in
    ``aliases.SHORT_FORM_INVERSE`` (e.g., ``vs``, ``es``), raises
    ``AliasCollision`` listing the offending paths. The walk uses a
    ``visited`` set keyed on ``type`` so recursive type graphs terminate.

    This is the runtime/live-reflection counterpart to
    ``aliases.validate_short_forms`` (which only checks the curated
    ``_KNOWN_SEGMENT_NAMES`` table).
    """
    short_form_values = set(SHORT_FORM_INVERSE)
    if not short_form_values:
        return

    collisions: dict[str, list[str]] = {}
    queue: deque[tuple[type[object], Path]] = deque()
    queue.append((root_type, Path(segments=())))
    visited: set[type[object]] = {root_type}

    while queue:
        current_type, current_path = queue.popleft()
        for field in dataclass_fields(current_type):
            segment, next_type = _short_form_walk_step(field)

            default_alias = singularize(field.name)
            if default_alias in short_form_values:
                next_path = Path(segments=current_path.segments + (segment,))
                collisions.setdefault(default_alias, []).append(path_to_string(next_path))

            if next_type is None or next_type in visited:
                continue
            visited.add(next_type)
            queue.append((next_type, Path(segments=current_path.segments + (segment,))))

    if collisions:
        # Report the first collision deterministically (sorted by alias).
        alias = sorted(collisions)[0]
        raise AliasCollision(alias, collisions[alias])


def _short_form_walk_step(field: FieldKind) -> tuple[Segment, type[object] | None]:
    """Compute the canonical (segment, next_type) pair for ``field``.

    Returns ``next_type=None`` for fields that don't produce a dataclass to
    descend into (leaves, or containers whose element/value is not a
    dataclass). The returned ``Segment`` mirrors what ``aliases_for(name)``
    would expect: collections get a trailing iter filter so the path renders
    as ``foo[*]``, dataclasses get a bare segment.
    """
    if isinstance(field, ListField):
        next_type = field.element_kind.dataclass_type if isinstance(field.element_kind, DataclassField) else None
        return Segment(name=field.name, filters=(IterFilter(),)), next_type
    if isinstance(field, DictField):
        next_type = field.value_kind.dataclass_type if isinstance(field.value_kind, DataclassField) else None
        return Segment(name=field.name, filters=(IterFilter(),)), next_type
    if isinstance(field, DataclassField):
        return Segment(name=field.name, filters=()), field.dataclass_type
    return Segment(name=field.name, filters=()), None


def resolve_row_scope(root_type: type[object], raw: object) -> tuple[Path, AmbientScopeTable]:
    if raw is None:
        raise ParseError("row_scope is required", position=None)

    text = raw if isinstance(raw, str) else str(raw)
    parsed = parse_row_scope(text)
    resolved: Path
    walk_steps: list[StepInfo]

    if not isinstance(parsed, Path):
        shortname = str(parsed)
        if shortname == "order":
            # ``order`` is the canonical root alias (spec §5.2) and is reserved:
            # it always short-circuits to the empty path. A downstream field
            # also named ``order`` is intentionally shadowed at row_scope
            # resolution; if such a field is reachable from a non-root scope,
            # ``AmbientScopeTable.add`` will surface the conflict via
            # ``AliasCollision`` when the scope table is built.
            resolved = Path(segments=())
            walk_steps = []
        else:
            matches, cap_hit = _enumerate_with_diagnostic(root_type, shortname, max_depth=_DEFAULT_SHORTNAME_MAX_DEPTH)
            if len(matches) == 0:
                hint: str | None = None
                if cap_hit:
                    hint = (
                        f"shortname enumeration hit the depth limit ({_DEFAULT_SHORTNAME_MAX_DEPTH});"
                        f" deeper matches were skipped"
                    )
                raise UnknownRowScope(shortname, hint=hint)
            if len(matches) > 1:
                raise AmbiguousRowScope(shortname, [path_to_string(path) for path in matches])
            resolved = matches[0]
            walk_steps = walk_path(root_type, resolved)
            # The shortname enumerator only emits paths terminating in a
            # ``DataclassField`` or an iter-filtered container, so this
            # validation is currently a no-op. Run it unconditionally to keep
            # the invariant defended rather than implicit.
            if not _valid_row_scope_terminal(resolved, walk_steps):
                reason = "row_scope must end at a dataclass node or an iterative [*] segment"
                raise InvalidRowScope(path_to_string(resolved), reason)
    else:
        resolved = parsed
        walk_steps = walk_path(root_type, resolved)
        if not _valid_row_scope_terminal(resolved, walk_steps):
            reason = "row_scope must end at a dataclass node or an iterative [*] segment"
            raise InvalidRowScope(path_to_string(resolved), reason)

    table = AmbientScopeTable()
    root_kind: FieldKind = DataclassField(name="order", dataclass_type=root_type, optional=False)
    table.add("order", Path(segments=()), root_kind, terminal=len(resolved.segments) == 0)

    if len(resolved.segments) == 0:
        table.add("self", Path(segments=()), root_kind, terminal=True)
        return resolved, table

    for index, step in enumerate(walk_steps):
        prefix = Path(segments=resolved.segments[: index + 1])
        is_terminal = index == len(walk_steps) - 1
        if _contains_iter_filter(step.segment):
            iter_source = step.segment_kind if isinstance(step.segment_kind, (ListField, DictField)) else None
            for alias in aliases_for(step.segment.name):
                table.add(alias, prefix, step.kind_after, terminal=is_terminal, iter_source_kind=iter_source)
            continue
        if len(step.segment.filters) == 0:
            for alias in aliases_for(step.segment.name):
                table.add(alias, prefix, step.kind_after, terminal=is_terminal)

    terminal = walk_steps[-1]
    terminal_iter_source: ListField | DictField | None = None
    if _contains_iter_filter(terminal.segment) and isinstance(terminal.segment_kind, (ListField, DictField)):
        terminal_iter_source = terminal.segment_kind
    for alias in aliases_for(terminal.segment.name):
        table.add(alias, resolved, terminal.kind_after, terminal=True, iter_source_kind=terminal_iter_source)
    table.add("self", resolved, terminal.kind_after, terminal=True, iter_source_kind=terminal_iter_source)
    return resolved, table


def _contains_iter_filter(segment: Segment) -> bool:
    return any(isinstance(filter_expr, IterFilter) for filter_expr in segment.filters)


def _valid_row_scope_terminal(path: Path, steps: list[StepInfo]) -> bool:
    if len(path.segments) == 0:
        return True
    if len(steps) == 0:
        return False
    terminal = steps[-1]
    if isinstance(terminal.kind_after, DataclassField):
        return True
    return _contains_iter_filter(terminal.segment)
