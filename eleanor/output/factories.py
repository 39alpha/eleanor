from typing import TYPE_CHECKING

from eleanor.exceptions import EleanorException
from eleanor.plugin import ConfigurablePluginSpec

if TYPE_CHECKING:
    from eleanor.output.csv import CsvSink
    from eleanor.output.memory import MemorySink
    from eleanor.output.null import NullSink
    from eleanor.output.postgres import PostgresSink


def parse_csv_settings(raw: dict[str, object]) -> object:
    from eleanor.output.csv import Settings

    return Settings.from_dict(raw)


def build_csv_sink(settings: object) -> CsvSink:
    from eleanor.output.csv import CsvSink, Settings

    if not isinstance(settings, Settings):
        msg = f"csv output sink requires csv Settings, got {type(settings).__name__}"
        raise EleanorException(msg)

    return CsvSink(settings)


csv_spec = ConfigurablePluginSpec(
    parse_settings=parse_csv_settings,
    build=build_csv_sink,
    plugin_api_version=1,
)


def parse_memory_settings(raw: dict[str, object]) -> object:
    from eleanor.output.memory import Settings

    return Settings.from_dict(raw)


def build_memory_sink(settings: object) -> MemorySink:
    from eleanor.output.memory import MemorySink, Settings

    if not isinstance(settings, Settings):
        msg = f"memory output sink requires memory Settings, got {type(settings).__name__}"
        raise EleanorException(msg)

    return MemorySink(settings)


memory_spec = ConfigurablePluginSpec(
    parse_settings=parse_memory_settings,
    build=build_memory_sink,
    plugin_api_version=1,
)


def parse_null_settings(raw: dict[str, object]) -> object:
    from eleanor.output.null import Settings

    return Settings.from_dict(raw)


def build_null_sink(settings: object) -> NullSink:
    from eleanor.output.null import NullSink, Settings

    if not isinstance(settings, Settings):
        msg = f"null output sink requires null Settings, got {type(settings).__name__}"
        raise EleanorException(msg)

    return NullSink(settings)


null_spec = ConfigurablePluginSpec(
    parse_settings=parse_null_settings,
    build=build_null_sink,
    plugin_api_version=1,
)


def parse_postgres_settings(raw: dict[str, object]) -> object:
    from eleanor.output.postgres.settings import Settings

    return Settings.from_dict(raw)


def build_postgres_sink(settings: object) -> PostgresSink:
    from eleanor.output.postgres import PostgresSink
    from eleanor.output.postgres.settings import Settings

    if not isinstance(settings, Settings):
        msg = f"postgres output sink requires postgres Settings, got {type(settings).__name__}"
        raise EleanorException(msg)

    return PostgresSink(settings)


postgres_spec = ConfigurablePluginSpec(
    parse_settings=parse_postgres_settings,
    build=build_postgres_sink,
    plugin_api_version=1,
)

__all__ = [
    "csv_spec",
    "memory_spec",
    "null_spec",
    "postgres_spec",
]
