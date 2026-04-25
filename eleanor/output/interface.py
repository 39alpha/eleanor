from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from traceback import format_exception

import eleanor.variable_space as vs

from ..order import Order
from ..progress import ProgressHandle


@dataclass(slots=True, frozen=True)
class ErrorInfo(object):
    type_name: str
    message: str
    traceback_text: str

    @staticmethod
    def from_exception(error: Exception) -> "ErrorInfo":
        traceback_text = "".join(format_exception(type(error), error, error.__traceback__))
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
    def initialize(self) -> None:
        """Perform once-per-sink setup before any :meth:`begin_run` is called.

        Eleanor calls this method exactly once per sink instance, before
        the first :meth:`begin_run`. Sinks may use it to open persistent
        resources (connections, file handles), apply schema setup, or
        enter bulk-load mode. The default implementation is a no-op.

        :meth:`initialize` and :meth:`finalize` bracket the sink's lifetime;
        :meth:`begin_run` / :meth:`write_batch` / :meth:`finalize_run`
        bracket each individual run within that lifetime.
        """
        return None

    @abstractmethod
    def begin_run(self, order: Order) -> int:
        """Perform any setup required for a run and return the order id.

        This method is responsible for choosing an order id if the order does
        not already have one, and the sink may modify the provided order.

        This method must be called before :meth:`write_batch` or
        :meth:`finalize_run`. Repeated calls with the same order are expected
        to return the same id and leave the sink's backing store in the same
        observable state as a single call (e.g. no duplicate order rows),
        though they may still perform work -- opening a connection, reading
        back stored metadata, or populating fields on the in-memory order.

        Implementations are only expected to verify identifying metadata
        (such as the order id and the version of Eleanor that produced
        the order); they are not expected to validate that the full order
        contents match what is stored. Callers extending an existing order
        are responsible for supplying a consistent order.
        """
        ...

    @abstractmethod
    def write_batch(
        self,
        order_id: int,
        results: Sequence[ComputeResult],
        progress: ProgressHandle | None = None,
    ) -> list[WriteOutcome]:
        """Persist ``results`` for ``order_id`` and return per-point outcomes.

        When ``progress`` is supplied the sink is responsible for emitting
        ``tick`` messages whose values sum to the number of rows it durably
        wrote during this call. The sink chooses the cadence that best fits
        its storage model -- per row, per internal sub-batch, or a single
        call at the end. Sinks that cannot emit meaningful progress must
        return ``False`` from :meth:`supports_progress` so Eleanor never
        supplies a non-``None`` handle in the first place.

        Default implementations of :meth:`OutputSink` (and older third-party
        sinks that have not yet been updated) may ignore ``progress`` freely;
        they will never receive a non-``None`` handle because the default
        :meth:`supports_progress` returns ``False``.
        """
        ...

    @abstractmethod
    def finalize_run(self) -> None:
        """Perform per-run cleanup after a single :meth:`Eleanor.run` returns.

        Called once for every :meth:`Eleanor.run` invocation that uses this
        sink, after all :meth:`begin_run` / :meth:`write_batch` calls for
        that run have completed. Sinks may use it to flush per-run buffers,
        commit per-run state, or release per-run resources. Sink-lifetime
        resources (persistent connections, indexes dropped under bulk-load
        mode) belong to :meth:`initialize` / :meth:`finalize` instead.
        """
        ...

    def finalize(self) -> None:
        """Perform once-per-sink teardown after all :meth:`finalize_run` cycles.

        Eleanor calls this method exactly once per sink instance, after the
        final :meth:`finalize_run` (or immediately, if no run was started).
        Sinks may use it to close persistent resources, recreate indexes
        and constraints dropped during bulk-load mode, or run any
        post-write maintenance. The default implementation is a no-op.

        :meth:`finalize` and :meth:`initialize` bracket the sink's lifetime;
        :meth:`begin_run` / :meth:`write_batch` / :meth:`finalize_run`
        bracket each individual run within that lifetime.
        """
        return None

    def supports_worker_writes(self) -> bool:
        """Whether :meth:`write_batch` is safe to invoke from worker processes.

        Sinks that return ``True`` must be picklable and must tolerate being
        invoked concurrently from multiple workers against the same target.
        :meth:`initialize`, :meth:`begin_run`, :meth:`finalize_run`, and
        :meth:`finalize` still run only in the main process; any state they
        establish must either cross the pickle boundary with the sink or be
        re-discovered inside :meth:`write_batch`.

        Sinks that return ``False`` (the default) are driven by the main
        process after workers have returned their :class:`ComputeResult`
        payloads.
        """
        return False

    def supports_progress(self) -> bool:
        """Whether :meth:`write_batch` emits per-point output progress.

        Sinks that return ``True`` accept a :class:`ProgressHandle` on
        :meth:`write_batch` and emit ``tick`` messages that sum to the number
        of rows they durably wrote. Eleanor uses this signal to decide
        whether to render the output progress bar at all: when every active
        sink returns ``False``, the output bar is never created.

        The default is ``False`` so third-party sinks that pre-date the
        progress protocol continue to work unchanged.
        """
        return False
