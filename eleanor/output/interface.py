from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from traceback import format_exception

import eleanor.variable_space as vs

from ..order import HufferResult, Order


@dataclass(slots=True, frozen=True)
class ErrorInfo(object):
    type_name: str
    message: str
    traceback_text: str

    @staticmethod
    def from_exception(error: Exception) -> 'ErrorInfo':
        traceback_text = ''.join(format_exception(type(error), error, error.__traceback__))
        return ErrorInfo(type_name=error.__class__.__name__, message=str(error), traceback_text=traceback_text)


@dataclass(slots=True)
class ComputeResult(object):
    point: vs.Point
    error: ErrorInfo | None = None


@dataclass(slots=True, frozen=True)
class WriteOutcome(object):
    point_id: int | None
    exit_code: int
    committed: bool
    error_message: str | None = None


@dataclass(slots=True)
class RunStats(object):
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0

    def update(self, outcomes: Sequence[WriteOutcome]) -> None:
        self.attempted += len(outcomes)
        n = sum(1 for o in outcomes if o.committed and o.exit_code == 0)
        self.succeeded += n
        self.failed += len(outcomes) - n


class OutputSink(ABC):
    @abstractmethod
    def begin_run(self, order: Order, huffer_result: HufferResult | None) -> None:
        ...

    @abstractmethod
    def write_batch(self, order_id: int, results: Sequence[ComputeResult]) -> list[WriteOutcome]:
        ...

    @abstractmethod
    def finalize(self) -> None:
        ...

    def supports_worker_writes(self) -> bool:
        """Whether :meth:`write_batch` is safe to invoke from worker processes.

        Sinks that return ``True`` must be picklable and must tolerate being
        invoked concurrently from multiple workers against the same target.
        :meth:`begin_run` and :meth:`finalize` still run only in the main
        process; any state they establish must either cross the pickle
        boundary with the sink or be re-discovered inside :meth:`write_batch`.

        Sinks that return ``False`` (the default) are driven by the main
        process after workers have returned their :class:`ComputeResult`
        payloads.
        """
        return False
