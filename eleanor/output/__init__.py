from typing import TYPE_CHECKING, cast

from eleanor.exceptions import EleanorException
from eleanor.output.interface import ComputeResult, ErrorInfo, OutputSink, RunStats, WriteOutcome
from eleanor.output.registry import available_output_sinks, get_factory
from eleanor.plugin import is_abstract_instantiation_error, resolve_api_version

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


def load_output_sink(config: _LoaderConfig, verbose: bool = False) -> OutputSink:
    kind = config.output.type
    if kind is None:
        sinks = available_output_sinks()
        valid_sinks = ", ".join(f"{t!r}" for t in sorted(sinks))
        msg = f"no output sink type provided; choose one of {valid_sinks}"
        raise EleanorException(msg)

    kwargs = config.output.args

    factory = get_factory(kind)
    version = resolve_api_version(factory)
    try:
        built = factory(config, verbose=verbose, **kwargs)
    except TypeError as e:
        if not is_abstract_instantiation_error(e):
            raise
        version_suffix = "" if version is None else f" (API v{version})"
        msg = f"output sink plugin {kind!r} failed to instantiate{version_suffix}: {e}"
        raise EleanorException(msg) from e

    if not isinstance(cast(object, built), OutputSink):
        msg = f"output sink plugin {kind!r} returned {type(built).__name__}, expected an OutputSink"
        raise EleanorException(msg)

    return built


__all__ = [
    "ComputeResult",
    "ErrorInfo",
    "OutputSink",
    "RunStats",
    "WriteOutcome",
    "load_output_sink",
]
