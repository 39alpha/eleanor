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
class NullSinkSettings(OutputSinkSettings):
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


class NullSink(AbstractOutputSink):
    settings: NullSinkSettings
    _next_order_id: int
    _order_id: int | None

    def __init__(self, settings: NullSinkSettings | None = None) -> None:
        self.settings = settings if settings is not None else NullSinkSettings(support_worker_writes=False)
        self._next_order_id = 0
        self._order_id = None

    @override
    def begin_run(self, order: Order) -> int:
        if order.id is not None:
            if order.id >= self._next_order_id:
                self._next_order_id = order.id + 1
            self._order_id = order.id
            return order.id

        order.id = self._next_order_id
        self._next_order_id += 1
        self._order_id = order.id

        return order.id

    @override
    def write_batch(
        self,
        order_id: int,
        results: Sequence[ComputeResult],
        progress: ProgressHandle | None = None,
    ) -> list[WriteOutcome]:
        if self._order_id != order_id:
            msg = "null sink write_batch called before begin_run"
            raise EleanorError(msg)

        outcomes: list[WriteOutcome] = []
        for result in results:
            result.point.order_id = order_id
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
        self._order_id = None

    @override
    def supports_worker_writes(self) -> bool:
        return self.settings.support_worker_writes

    @override
    def supports_progress(self) -> bool:
        return True


__all__ = [
    "NullSink",
    "NullSinkSettings",
]
