from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict, override

from eleanor.exceptions import EleanorConfigurationException, EleanorException
from eleanor.order import Order
from eleanor.output.interface import ComputeResult, OutputSink, WriteOutcome
from eleanor.progress import ProgressHandle


class MemoryArgsRaw(TypedDict, total=False):
    support_worker_writes: bool


@dataclass(frozen=True, init=False)
class MemoryConfig(object):
    support_worker_writes: bool

    def __init__(self, support_worker_writes: object):
        if not isinstance(support_worker_writes, bool):
            msg = 'output.args.support_worker_writes must be a boolean for output type "memory"'
            raise EleanorConfigurationException(msg)
        object.__setattr__(self, "support_worker_writes", support_worker_writes)

    @staticmethod
    def from_raw(raw: MemoryArgsRaw) -> MemoryConfig:
        return MemoryConfig(
            support_worker_writes=raw.get("support_worker_writes", False),
        )


class MemorySink(OutputSink):
    config: MemoryConfig
    _orders: dict[int, Order]

    def __init__(self, config: MemoryConfig | None = None) -> None:
        self.config = config if config is not None else MemoryConfig(support_worker_writes=False)
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
            msg = "memory sink write_batch called before begin_run"
            raise EleanorException(msg)
        order = self._orders[order_id]

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
        return self.config.support_worker_writes

    @override
    def supports_progress(self) -> bool:
        return True


__all__ = [
    "MemoryArgsRaw",
    "MemoryConfig",
    "MemorySink",
]
