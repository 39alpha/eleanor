from collections.abc import Sequence
from typing import override

from ..connection import DatabaseConfig
from ..exceptions import EleanorException
from ..order import HufferResult, Order
from ..yeoman import Yeoman
from .interface import ComputeResult, OutputSink, WriteOutcome


class PostgresSink(OutputSink):
    config: DatabaseConfig
    verbose: bool

    def __init__(self, config: DatabaseConfig, verbose: bool = False):
        self.config = config
        self.verbose = verbose

    @override
    def begin_run(self, order: Order, huffer_result: HufferResult | None) -> None:
        if order.id is None:
            raise EleanorException('order must have an id before writing output')

    @override
    def write_batch(self, order_id: int, results: Sequence[ComputeResult]) -> list[WriteOutcome]:
        outcomes: list[WriteOutcome] = []

        with Yeoman(self.config, verbose=self.verbose) as yeoman:
            for result in results:
                try:
                    # point.order_id must be set before the ORM write as a required side-effect
                    point = result.point
                    point.order_id = order_id
                    yeoman.write(point, refresh=True)

                    if point.id is None:
                        raise EleanorException('variable space point does not have an id after insert')

                    outcomes.append(
                        WriteOutcome(
                            point_id=point.id,
                            exit_code=point.exit_code,
                            committed=True,
                        ))
                except Exception as e:
                    outcomes.append(
                        WriteOutcome(
                            point_id=None,
                            exit_code=-1,
                            committed=False,
                            error_message=str(e),
                        ))

        return outcomes

    @override
    def finalize(self) -> None:
        pass
