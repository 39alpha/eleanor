"""Public surface of the ``eleanor.output`` extension point.

The registry API is re-exported eagerly: :mod:`eleanor.output.registry` has
no runtime dependency on :mod:`eleanor.config`, so it is safe to import it
from :mod:`eleanor.config` at module scope for sink-name validation.

The interface dataclasses (:class:`OutputSink`, :class:`ComputeResult`,
:class:`ErrorInfo`, :class:`WriteOutcome`, :class:`RunStats`) and the
built-in :class:`PostgresSink` transitively pull in
:mod:`eleanor.variable_space` -> :mod:`eleanor.equilibrium_space` ->
:mod:`eleanor.yeoman` -> :mod:`eleanor.config`; importing any of them
eagerly here would create a runtime ``ImportError`` at first use of the
``eleanor.config`` module. They are therefore loaded on demand through
:pep:`562`'s ``__getattr__`` hook, with a matching ``TYPE_CHECKING`` block
so static type checkers see them as regular re-exports.
"""
from typing import TYPE_CHECKING

from .registry import (
    BUILTIN_OUTPUT_SINKS,
    ENTRY_POINT_GROUP,
    OVERRIDE_ENV_VAR,
    OutputFactory,
    available_output_sinks,
    get_factory,
    register_output_sink,
)

if TYPE_CHECKING:
    from .interface import ComputeResult as ComputeResult
    from .interface import ErrorInfo as ErrorInfo
    from .interface import OutputSink as OutputSink
    from .interface import RunStats as RunStats
    from .interface import WriteOutcome as WriteOutcome
    from .postgres import PostgresSink as PostgresSink


def __getattr__(name: str) -> object:
    if name == 'ComputeResult':
        from .interface import ComputeResult

        return ComputeResult
    if name == 'ErrorInfo':
        from .interface import ErrorInfo

        return ErrorInfo
    if name == 'OutputSink':
        from .interface import OutputSink

        return OutputSink
    if name == 'RunStats':
        from .interface import RunStats

        return RunStats
    if name == 'WriteOutcome':
        from .interface import WriteOutcome

        return WriteOutcome
    if name == 'PostgresSink':
        from .postgres import PostgresSink

        return PostgresSink
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


__all__ = [
    'BUILTIN_OUTPUT_SINKS',
    'ComputeResult',
    'ENTRY_POINT_GROUP',
    'ErrorInfo',
    'OVERRIDE_ENV_VAR',
    'OutputFactory',
    'OutputSink',
    'PostgresSink',
    'RunStats',
    'WriteOutcome',
    'available_output_sinks',
    'get_factory',
    'register_output_sink',
]
