import os
import time
from datetime import datetime
from multiprocessing import Manager, Pool, Process
from queue import Queue
from sys import exit, stderr
from traceback import print_exception

from sqlalchemy import and_, select

import eleanor.variable_space as vs
from eleanor.sailor import Sailor

from .config import Config, DatabaseConfig, load_config
from .exceptions import EleanorException
from .kernel.discover import import_kernel_module
from .kernel.interface import AbstractKernel
from .navigator import AbstractNavigator
from .order import HufferResult, Order, load_order
from .typing import Any, Optional, Self, cast
from .util import Progress, chunks
from .version import __version__
from .yeoman import Yeoman


class Eleanor(object):
    config: Config
    order: Order
    kernel_args: list[Any]

    def __init__(self, config: str | Config, order: str | Order, kernel_args: list[Any], *args, **kwargs):
        self.config = load_config(config)
        self.order = load_order(order)
        self.kernel_args = kernel_args

    def recur(self, *args, **kwargs) -> Self:
        return self.__class__(*args, **kwargs)

    def run(
        self,
        simulation_size: int,
        *args,
        order_id: Optional[int] = None,
        combined: bool = False,
        proportional_sampling: bool = False,
        verbose: bool = False,
        **kwargs,
    ) -> list[int]:
        if self.order.suborders is not None and len(self.order.suborders.suborders) != 0:
            order_ids: set[int] = set()

            suborders = self.order.split_suborders()
            combined = combined or self.order.suborders.combined
            proportional_sampling = proportional_sampling or self.order.suborders.proportional_sampling

            if combined and order_id is None:
                order_id = self.ignite(*args, verbose=verbose, **kwargs)

            volume = self.order.volume()

            for suborder in suborders:
                suborder_samples = simulation_size
                if proportional_sampling:
                    suborder_samples = round(suborder_samples * suborder.volume() / volume)

                eleanor = self.recur(self.config, suborder, self.kernel_args)
                suborder_ids = eleanor.run(
                    suborder_samples,
                    *args,
                    order_id=order_id,
                    combined=combined,
                    proportional_sampling=proportional_sampling,
                    verbose=verbose,
                    **kwargs,
                )
                order_ids.update(suborder_ids)

            return sorted(order_ids)

        return self.dispatch(simulation_size, *args, order_id=order_id, verbose=verbose, **kwargs)

    def dispatch(
        self,
        simulation_size: int,
        *args,
        no_huffer: bool = False,
        num_procs: int | None = None,
        show_progress: bool = False,
        success_sampling: bool = False,
        order_id: Optional[int] = None,
        **kwargs,
    ):
        kernel = self.load_kernel(**kwargs)
        navigator = self.order.navigator.load()(self.order, kernel)

        if success_sampling and not navigator.supports_success_sampling():
            msg = f"{navigator.__class__.__module__}.{navigator.__class__.__name__} does not support success sampling"
            raise EleanorException(msg)

        if order_id is None:
            huffer_with = None
            if not no_huffer:
                huffer_with = (kernel, navigator)
            order_id = self.ignite(*args, huffer_with=huffer_with, **kwargs)

        manager = Manager()

        progress: Optional[Progress] = None
        if show_progress:
            progress = Progress(manager, no_total_update=success_sampling)

        if num_procs is not None and num_procs <= 0:
            num_procs = 1

        with Pool(processes=num_procs) as pool:
            if success_sampling:
                successes = Eleanor.count_successes(self.config.database, order_id)
                target_samples = successes + simulation_size

                while successes < target_samples:
                    self.process(
                        kernel,
                        navigator,
                        target_samples - successes,
                        order_id,
                        *args,
                        pool=pool,
                        success_sampling=success_sampling,
                        progress=progress.queue if progress is not None else None,
                        **kwargs,
                    )

                    successes = Eleanor.count_successes(self.config.database, order_id)
            else:
                self.process(
                    kernel,
                    navigator,
                    simulation_size,
                    order_id,
                    *args,
                    pool=pool,
                    success_sampling=success_sampling,
                    progress=progress.queue if progress is not None else None,
                    **kwargs,
                )

        if progress is not None:
            progress.join()

        return [order_id]

    def process(
        self,
        kernel: AbstractKernel,
        navigator: AbstractNavigator,
        simulation_size: int,
        order_id: int,
        *args,
        pool=None,
        success_sampling: bool = False,
        progress: Optional[Queue[bool | int]] = None,
        **kwargs,
    ):
        if pool is None:
            raise EleanorException('no process pool created')

        while True:
            vs_points = navigator.navigate(simulation_size, order_id=order_id, max_attempts=1)
            if progress is not None:
                progress.put(len(vs_points))

            vs_point_ids: list[int] = []

            futures = []
            for batch_num, batch in enumerate(chunks(vs_points, pool._processes)):  # type: ignore
                future = pool.apply_async(
                    Sailor(kernel, self.config.database).dispatch,
                    (batch, *args),
                    {
                        **kwargs,
                        'progress': progress,
                        'success_sampling': success_sampling,
                    },
                )
                futures.append(future)

            while futures:
                future = futures.pop()
                vs_point_ids.extend(future.get())

            if navigator.is_complete(vs_point_ids):
                break

    def load_kernel(self, **kwargs) -> AbstractKernel:
        kernel_module = import_kernel_module(self.order.kernel.type)
        kernel = kernel_module.Kernel(self.order.kernel.settings, *self.kernel_args)
        kernel.setup(self.order, **kwargs)

        return kernel

    def ignite(
        self,
        *args,
        huffer_with: Optional[tuple[AbstractKernel, AbstractNavigator]] = None,
        verbose: bool = False,
        scratch: bool = False,
        **kwargs,
    ) -> int:
        if huffer_with is not None:
            kernel, navigator = huffer_with
            huffer_problem = navigator.huffer_problem()
            huffer_point = Sailor(kernel).work(huffer_problem, *args, scratch=True, **kwargs)
            self.order.huffer_result = HufferResult.from_scratch(huffer_point.scratch, huffer_point.exit_code)
        else:
            huffer_point = None
            self.order.huffer_result = None

        with Yeoman(self.config.database) as yeoman:
            yeoman.setup()

            if yeoman.scalar(select(Order).where(Order.eleanor_version != __version__)):  # type: ignore
                raise EleanorException('cannot add order to a database created with a different version of Eleanor')

            result = yeoman.scalar(
                select(Order).where(
                    and_(
                        Order.hash == self.order.hash,  # type: ignore
                        Order.eleanor_version == __version__,  # type: ignore
                    )))

            if result is not None:
                order_id = self.order.id = result.id
                self.order.eleanor_version = result.eleanor_version

                if self.order.huffer_result is not None:
                    if result.huffer_result is None:
                        result.huffer_result = self.order.huffer_result
                    else:
                        result.huffer_result.exit_code = self.order.huffer_result.exit_code  # type: ignore
                        result.huffer_result.zip = self.order.huffer_result.zip  # type: ignore

                yeoman.merge(result)
                yeoman.commit()
            else:
                self.order.eleanor_version = __version__
                yeoman.write(self.order, refresh=True)
                order_id = self.order.id

        if huffer_point is not None and not kernel.is_soft_exit(huffer_point.exit_code):
            raise EleanorException(
                f'Error: the huffer failed',
                code=huffer_point.exit_code,
            ) from huffer_point.exception
        elif order_id is None:
            raise EleanorException(f'Error: failed to create the order')

        return order_id

    @staticmethod
    def count_successes(config: DatabaseConfig, order_id: int) -> int:
        with Yeoman(config) as yeoman:
            successes = yeoman.query(vs.Point).filter(
                and_(
                    vs.Point.exit_code == 0,  # type: ignore
                    vs.Point.order_id == order_id,  # type: ignore
                )).count()
            return successes
