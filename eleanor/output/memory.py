"""In-memory :class:`OutputSink` implementation for programmatic and test use."""

from collections.abc import Sequence
from typing import override

from ..exceptions import EleanorException
from ..order import Order
from ..progress import ProgressHandle
from ..version import __version__
from .interface import ComputeResult, OutputSink, WriteOutcome


class MemorySink(OutputSink):
    _orders: dict[int, Order]

    def __init__(self) -> None:
        self._orders = {}

    @override
    def begin_run(self, order: Order) -> int:
        for order_id, existing in self._orders.items():
            if existing is order:
                return order_id

        order_id: int
        if order.id is None:
            order_id = max(self._orders.keys() or [-1]) + 1
        else:
            order_id = order.id

        if order.eleanor_version is None:
            order.eleanor_version = __version__

        order.id = order_id
        self._orders[order_id] = order

        return order_id

    @override
    def write_batch(
        self,
        order_id: int,
        results: Sequence[ComputeResult],
        progress: ProgressHandle | None = None,
    ) -> list[WriteOutcome]:
        if order_id not in self._orders:
            raise EleanorException("memory sink write_batch called before begin_run")
        order = self._orders[order_id]

        # Unlike CsvSink/PostgresSink, MemorySink treats every result —
        # including error results — as a committed write.  There is no
        # persistent store that could be left in an inconsistent state.
        outcomes: list[WriteOutcome] = []
        for result in results:
            result.point.order_id = order_id
            order.vs_points.append(result.point)
            outcomes.append(
                WriteOutcome(
                    exit_code=result.point.exit_code,
                    committed=True,
                )
            )
            if progress is not None:
                progress.tick()

        return outcomes

    @override
    def finalize_run(self) -> None:
        return None

    @override
    def supports_worker_writes(self) -> bool:
        return False

    @override
    def supports_progress(self) -> bool:
        return True
