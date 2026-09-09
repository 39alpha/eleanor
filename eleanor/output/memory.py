from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self, cast, override

import eleanor.variable_space as vs
from eleanor.exceptions import EleanorError
from eleanor.order import Order
from eleanor.output.interface import AbstractOutputSink, ComputeResult, WriteOutcome
from eleanor.output.settings import OutputSinkSettings
from eleanor.progress import ProgressHandle
from eleanor.util import guard_is_bool, require_bool


@dataclass(kw_only=True)
class MemorySinkSettings(OutputSinkSettings):
    support_worker_commit: bool

    def __post_init__(self) -> None:
        super().__post_init__()

        guard_is_bool(self.support_worker_commit, "support_worker_commit")

    @classmethod
    @override
    def from_dict(cls, raw: dict[str, object]) -> Self:
        base_settings = OutputSinkSettings.from_dict(raw)

        support_worker_commit = require_bool(
            raw.get("support_worker_commit", False),
            "support_worker_commit",
        )

        return cls(
            verbose=base_settings.verbose,
            support_worker_commit=support_worker_commit,
        )


class MemorySink(AbstractOutputSink):
    """In-memory sink that retains the whole compute graph.

    Its prepared payload is the :class:`~eleanor.variable_space.Point` itself,
    because retaining the graph *is* the point of this sink -- there is nothing
    to reduce. That makes it the reference case for what an unreduced payload
    costs when compared against sinks that do reduce.
    """

    settings: MemorySinkSettings
    _orders: dict[int, Order]

    def __init__(self, settings: MemorySinkSettings | None = None) -> None:
        self.settings = settings if settings is not None else MemorySinkSettings(support_worker_commit=False)
        self._orders = {}

    @override
    def begin_run(self, order: Order) -> int:
        for order_id, existing in self._orders.items():
            if existing is order:
                return order_id

        order_id = order.id if order.id is not None else max(self._orders.keys() or [-1]) + 1
        order.id = order_id
        self._orders[order_id] = order

        return order_id

    @override
    def prepare_batch(self, order_id: int, results: Sequence[ComputeResult]) -> Sequence[vs.Point]:
        for result in results:
            result.point.order_id = order_id
        return [result.point for result in results]

    @override
    def commit_batch(
        self,
        order_id: int,
        prepared: Sequence[object],
        progress: ProgressHandle | None = None,
    ) -> list[WriteOutcome]:
        if order_id not in self._orders:
            msg = "memory sink commit_batch called before begin_run"
            raise EleanorError(msg)
        order = self._orders[order_id]

        outcomes: list[WriteOutcome] = []
        for point in cast("Sequence[vs.Point]", prepared):
            order.vs_points.append(point)
            outcomes.append(WriteOutcome(exit_code=point.exit_code, committed=True))
            if progress is not None:
                progress.tick()

        return outcomes

    @override
    def finalize_run(self) -> None:
        return None

    @override
    def supports_worker_commit(self) -> bool:
        return self.settings.support_worker_commit

    @override
    def supports_progress(self) -> bool:
        return True


__all__ = [
    "MemorySink",
    "MemorySinkSettings",
]
