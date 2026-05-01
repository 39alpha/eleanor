"""A minimal sink that discards the data for testing and benchmarking use"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict, override

from eleanor.exceptions import EleanorConfigurationException, EleanorException

from ..order import Order
from ..progress import ProgressHandle
from ..version import __version__
from .interface import ComputeResult, OutputSink, WriteOutcome


class NullArgsRaw(TypedDict, total=False):
    support_worker_writes: bool


@dataclass(frozen=True, init=False)
class NullConfig(object):
    support_worker_writes: bool

    def __init__(self, support_worker_writes: object):
        if not isinstance(support_worker_writes, bool):
            raise EleanorConfigurationException(
                'output.args.support_worker_writes must be a boolean for output type "null"'
            )
        object.__setattr__(self, "support_worker_writes", support_worker_writes)

    @staticmethod
    def from_raw(raw: NullArgsRaw) -> "NullConfig":
        return NullConfig(
            support_worker_writes=raw.get("support_worker_writes", False),
        )


class NullSink(OutputSink):
    config: NullConfig
    _next_order_id: int
    _order_id: int | None

    def __init__(self, config: NullConfig):
        self.config = config
        self._next_order_id = 0
        self._order_id = None

    @override
    def begin_run(self, order: Order) -> int:
        if order.eleanor_version is None:
            order.eleanor_version = __version__

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
            raise EleanorException("null sink write_batch called before begin_run")

        outcomes: list[WriteOutcome] = []
        for result in results:
            result.point.order_id = order_id
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
        self._order_id = None

    @override
    def supports_worker_writes(self) -> bool:
        return self.config.support_worker_writes

    @override
    def supports_progress(self) -> bool:
        return True
