from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self, cast, override

from eleanor.exceptions import EleanorError
from eleanor.order import Order
from eleanor.output.interface import AbstractOutputSink, ComputeResult, WriteOutcome
from eleanor.output.settings import OutputSinkSettings
from eleanor.progress import ProgressHandle
from eleanor.util import guard_is_bool, require_bool


@dataclass(kw_only=True)
class NullSinkSettings(OutputSinkSettings):
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


@dataclass(slots=True, frozen=True)
class NullPrepared:
    """Everything :class:`NullSink` needs at commit time, and nothing more.

    Discarding output makes this the one sink whose prepared payload can be
    genuinely tiny: only the exit code survives the trip, so the compute graph
    never crosses the process boundary at all. That makes the null sink a
    clean measurement of dispatch-loop overhead in isolation.
    """

    exit_code: int


class NullSink(AbstractOutputSink):
    settings: NullSinkSettings
    _next_order_id: int
    _order_id: int | None

    def __init__(self, settings: NullSinkSettings | None = None) -> None:
        self.settings = settings if settings is not None else NullSinkSettings(support_worker_commit=False)
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
    def prepare_batch(self, order_id: int, results: Sequence[ComputeResult]) -> Sequence[NullPrepared]:
        for result in results:
            result.point.order_id = order_id
        return [NullPrepared(exit_code=result.point.exit_code) for result in results]

    @override
    def commit_batch(
        self,
        order_id: int,
        prepared: Sequence[object],
        progress: ProgressHandle | None = None,
    ) -> list[WriteOutcome]:
        if self._order_id != order_id:
            msg = "null sink commit_batch called before begin_run"
            raise EleanorError(msg)

        outcomes: list[WriteOutcome] = []
        for item in cast("Sequence[NullPrepared]", prepared):
            outcomes.append(WriteOutcome(exit_code=item.exit_code, committed=True))
            if progress is not None:
                progress.tick()

        return outcomes

    @override
    def finalize_run(self) -> None:
        self._order_id = None

    @override
    def supports_worker_commit(self) -> bool:
        return self.settings.support_worker_commit

    @override
    def supports_background_commit(self) -> bool:
        return True

    @override
    def supports_progress(self) -> bool:
        return True


__all__ = [
    "NullPrepared",
    "NullSink",
    "NullSinkSettings",
]
