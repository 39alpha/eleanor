from eleanor.output.interface import AbstractOutputSink, ComputeResult, ErrorInfo, RunStats, WriteOutcome
from eleanor.output.registry import registry
from eleanor.output.settings import OutputSinkSettings
from eleanor.plugin import load_plugin, load_plugin_settings


def load_output_sink_settings(kind: str, raw: dict[str, object]) -> OutputSinkSettings:
    return load_plugin_settings(registry, OutputSinkSettings, kind, raw) or OutputSinkSettings()


def load_output_sink(kind: str, settings: OutputSinkSettings) -> AbstractOutputSink:
    return load_plugin(registry, AbstractOutputSink, kind, settings)


__all__ = [
    "AbstractOutputSink",
    "ComputeResult",
    "ErrorInfo",
    "RunStats",
    "WriteOutcome",
    "load_output_sink",
    "load_output_sink_settings",
]
