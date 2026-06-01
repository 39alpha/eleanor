from eleanor.output.interface import AbstractOutputSink, ComputeResult, ErrorInfo, RunStats, WriteOutcome
from eleanor.output.registry import registry
from eleanor.output.settings import Settings
from eleanor.plugin import load_plugin, load_plugin_settings


def load_output_sink_settings(kind: str, raw: dict[str, object]) -> Settings:
    return load_plugin_settings(registry, Settings, kind, raw) or Settings()


def load_output_sink(kind: str, settings: Settings) -> AbstractOutputSink:
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
