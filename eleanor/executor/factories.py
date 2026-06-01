from typing import TYPE_CHECKING

from eleanor.exceptions import EleanorException
from eleanor.executor.settings import Settings
from eleanor.plugin import ConfigurablePluginSpec

if TYPE_CHECKING:
    from eleanor.executor.interface import AbstractExecutor


def parse_standard_settings(raw: dict[str, object]) -> Settings:
    return Settings.from_dict(raw)


def build_serial(settings: object) -> AbstractExecutor:
    if not isinstance(settings, Settings):
        msg = f"serial executor requires executor Settings, got {type(settings).__name__}"
        raise EleanorException(msg)

    from eleanor.executor.serial import Executor

    return Executor(settings)


serial_spec = ConfigurablePluginSpec(
    parse_settings=parse_standard_settings,
    build=build_serial,
    plugin_api_version=1,
)


def build_multiprocessing(settings: object) -> AbstractExecutor:
    if not isinstance(settings, Settings):
        msg = f"multiprocessing executor requires executor Settings, got {type(settings).__name__}"
        raise EleanorException(msg)

    from eleanor.executor.multiprocessing import Executor

    return Executor(settings)


multiprocessing_spec = ConfigurablePluginSpec(
    parse_settings=parse_standard_settings,
    build=build_multiprocessing,
    plugin_api_version=1,
)


__all__ = [
    "multiprocessing_spec",
    "serial_spec",
]
