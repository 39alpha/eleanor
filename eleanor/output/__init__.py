from typing import cast

from eleanor.exceptions import EleanorException
from eleanor.output.interface import ComputeResult, ErrorInfo, OutputSink, RunStats, WriteOutcome
from eleanor.output.registry import get_factory
from eleanor.plugin import is_abstract_instantiation_error, resolve_api_version


def load_output_sink(kind: str, *, verbose: bool = False, **kwargs: object) -> OutputSink:
    factory = get_factory(kind)
    version = resolve_api_version(factory)
    try:
        built = factory(verbose=verbose, **kwargs)
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
