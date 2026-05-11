"""Public surface of the ``eleanor.output`` extension point.

The registry API (:func:`available_outputs`, :func:`get_factory`,
:func:`register_output`) is re-exported eagerly.

The interface dataclasses (:class:`OutputSink`, :class:`ComputeResult`,
:class:`ErrorInfo`, :class:`WriteOutcome`, :class:`RunStats`) and the
built-in :class:`PostgresSink` are loaded on demand through :pep:`562`'s
``__getattr__`` hook so importing :mod:`eleanor.output` does not pull in
psycopg or the schema/converters/queries graph until a caller actually
touches one of those names. A matching ``TYPE_CHECKING`` block keeps
static type checkers seeing them as regular re-exports.

Built-in output factories live in :mod:`eleanor.output.factories` and are
discovered via entry points. Their heavy imports (for example
:mod:`eleanor.output.postgres`) stay deferred inside factory callables.
"""

from typing import TYPE_CHECKING

from ..exceptions import EleanorException
from ..plugin import is_abstract_instantiation_error, resolve_api_version
from .registry import (
    BUILTIN_OUTPUTS,
    ENTRY_POINT_GROUP,
    OVERRIDE_ENV_VAR,
    OutputFactory,
    available_outputs,
    get_factory,
    register_output,
)

if TYPE_CHECKING:
    from typing import Protocol

    class _OutputConfig(Protocol):
        @property
        def type(self) -> str | None: ...

        @property
        def args(self) -> dict[str, object]: ...

    class _LoaderConfig(Protocol):
        @property
        def output(self) -> _OutputConfig: ...

    from .csv import CsvSink as CsvSink
    from .interface import ComputeResult as ComputeResult
    from .interface import ErrorInfo as ErrorInfo
    from .interface import OutputSink as OutputSink
    from .interface import RunStats as RunStats
    from .interface import WriteOutcome as WriteOutcome
    from .memory import MemorySink as MemorySink
    from .null import NullSink as NullSink
    from .postgres import PostgresSink as PostgresSink


def __getattr__(name: str) -> object:
    if name == "ComputeResult":
        from .interface import ComputeResult

        return ComputeResult
    if name == "ErrorInfo":
        from .interface import ErrorInfo

        return ErrorInfo
    if name == "OutputSink":
        from .interface import OutputSink

        return OutputSink
    if name == "RunStats":
        from .interface import RunStats

        return RunStats
    if name == "WriteOutcome":
        from .interface import WriteOutcome

        return WriteOutcome
    if name == "PostgresSink":
        from .postgres import PostgresSink

        return PostgresSink
    if name == "CsvSink":
        from .csv import CsvSink

        return CsvSink
    if name == "MemorySink":
        from .memory import MemorySink

        return MemorySink
    if name == "NullSink":
        from .null import NullSink

        return NullSink
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def load_output_sink(config: "_LoaderConfig", verbose: bool = False) -> "OutputSink":
    if config.output.type is None:
        sinks = available_outputs()
        valid_sinks = ", ".join(f'"{t}"' for t in sorted(sinks))
        msg = f"no output sink type provided; choose one of {valid_sinks}"
        raise EleanorException(msg)

    factory = get_factory(config.output.type)
    version = resolve_api_version(factory)
    try:
        built = factory(config, verbose=verbose, **config.output.args)
    except TypeError as e:
        if not is_abstract_instantiation_error(e):
            raise
        version_suffix = "" if version is None else f" (API v{version})"
        raise EleanorException(
            f'output sink plugin "{config.output.type}" failed to instantiate{version_suffix}: {e}',
        ) from e

    from ..typing import cast
    from .interface import OutputSink

    # The protocol is strong, but we want to retain the runtime check because
    # protocols are discarded at runtime. The cast is necessary to satisfy
    # the typechecker (which will think the conditional is always true).
    built_obj = cast(object, built)
    if not isinstance(built_obj, OutputSink):
        raise EleanorException(
            f'output sink plugin "{config.output.type}" returned ' + f"{type(built).__name__}, expected an OutputSink",
        )
    return built


__all__ = [
    "BUILTIN_OUTPUTS",
    "CsvSink",
    "ComputeResult",
    "ENTRY_POINT_GROUP",
    "ErrorInfo",
    "MemorySink",
    "NullSink",
    "OVERRIDE_ENV_VAR",
    "OutputFactory",
    "OutputSink",
    "PostgresSink",
    "RunStats",
    "WriteOutcome",
    "available_outputs",
    "get_factory",
    "load_output_sink",
    "register_output",
]
