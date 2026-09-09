from typing import cast

from eleanor.output.interface import AbstractOutputSink, ComputeResult, ErrorInfo, RunStats, WriteOutcome
from eleanor.output.registry import registry
from eleanor.output.settings import OutputSinkSettings
from eleanor.plugin import load_plugin, load_plugin_settings


def load_output_sink_settings(kind: str, raw: dict[str, object]) -> OutputSinkSettings:
    return load_plugin_settings(registry, OutputSinkSettings, kind, raw) or OutputSinkSettings()


def load_output_sink(kind: str, settings: OutputSinkSettings) -> AbstractOutputSink[object]:
    """Build the configured sink, with its id type erased to ``object``.

    Which sink the config names -- and therefore which id type it chose -- is
    not knowable here, and ``AbstractOutputSink`` is invariant in that
    parameter, so no single parameterization accepts every sink. Erasing to
    ``object`` is sound for Eleanor's own use: it never constructs or inspects
    an id, it only carries the value ``begin_run`` returned back into
    ``prepare_batch`` / ``commit_batch``. This is the same trade the prepared
    payload already makes, and the cast is deliberately confined to this one
    plugin boundary.
    """
    return cast("AbstractOutputSink[object]", load_plugin(registry, AbstractOutputSink, kind, settings))


__all__ = [
    "AbstractOutputSink",
    "ComputeResult",
    "ErrorInfo",
    "RunStats",
    "WriteOutcome",
    "load_output_sink",
    "load_output_sink_settings",
]
