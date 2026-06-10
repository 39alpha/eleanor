from typing import TYPE_CHECKING

from eleanor.exceptions import EleanorError
from eleanor.executor.settings import ExecutorSettings
from eleanor.plugin import ConfigurablePluginSpec

if TYPE_CHECKING:
    from eleanor.executor.multiprocessing import MultiprocessingExecutor
    from eleanor.executor.serial import SerialExecutor


def parse_standard_settings(raw: dict[str, object]) -> ExecutorSettings:
    return ExecutorSettings.from_dict(raw)


def build_serial(settings: object) -> SerialExecutor:
    if not isinstance(settings, ExecutorSettings):
        msg = f"serial executor requires {ExecutorSettings.__name__}, got {type(settings).__name__}"
        raise EleanorError(msg)

    from eleanor.executor.serial import SerialExecutor

    return SerialExecutor(settings)


serial_spec = ConfigurablePluginSpec(
    parse_settings=parse_standard_settings,
    build=build_serial,
    plugin_api_version=1,
)


def build_multiprocessing(settings: object) -> MultiprocessingExecutor:
    if not isinstance(settings, ExecutorSettings):
        msg = f"multiprocessing executor requires {ExecutorSettings.__name__}, got {type(settings).__name__}"
        raise EleanorError(msg)

    from eleanor.executor.multiprocessing import MultiprocessingExecutor

    return MultiprocessingExecutor(settings)


multiprocessing_spec = ConfigurablePluginSpec(
    parse_settings=parse_standard_settings,
    build=build_multiprocessing,
    plugin_api_version=1,
)


__all__ = [
    "multiprocessing_spec",
    "serial_spec",
]
