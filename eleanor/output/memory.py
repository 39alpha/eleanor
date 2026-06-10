from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self, override

from eleanor.exceptions import EleanorError
from eleanor.order import Order
from eleanor.output.interface import AbstractOutputSink, ComputeResult, WriteOutcome
from eleanor.output.settings import OutputSinkSettings
from eleanor.progress import ProgressHandle
from eleanor.util import guard_is_bool, require_bool


@dataclass(kw_only=True)
class MemorySinkSettings(OutputSinkSettings):
    support_worker_writes: bool

    def __post_init__(self) -> None:
        super().__post_init__()

        guard_is_bool(self.support_worker_writes, "support_worker_writes")

    @classmethod
    @override
    def from_dict(cls, raw: dict[str, object]) -> Self:
        base_settings = OutputSinkSettings.from_dict(raw)

        support_worker_writes = require_bool(
            raw.get("support_worker_writes", False),
            "support_worker_writes",
        )

        return cls(
            verbose=base_settings.verbose,
            support_worker_writes=support_worker_writes,
        )


class MemorySink(AbstractOutputSink):
    settings: MemorySinkSettings
    _orders: dict[int, Order]

    def __init__(self, settings: MemorySinkSettings | None = None) -> None:
        self.settings = settings if settings is not None else MemorySinkSettings(support_worker_writes=False)
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
    def write_batch(
        self,
        order_id: int,
        results: Sequence[ComputeResult],
        progress: ProgressHandle | None = None,
    ) -> list[WriteOutcome]:
        if order_id not in self._orders:
            msg = "memory sink write_batch called before begin_run"
            raise EleanorError(msg)
        order = self._orders[order_id]

        outcomes: list[WriteOutcome] = []
        for result in results:
            result.point.order_id = order_id
            order.vs_points.append(result.point)
            outcomes.append(
                WriteOutcome(
                    exit_code=result.point.exit_code,
                    committed=True,
                ),
            )
            if progress is not None:
                progress.tick()

        return outcomes

    @override
    def finalize_run(self) -> None:
        return None

    @override
    def supports_worker_writes(self) -> bool:
        return self.settings.support_worker_writes

    @override
    def supports_progress(self) -> bool:
        return True


__all__ = [
    "MemorySink",
    "MemorySinkSettings",
]
