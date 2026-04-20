from multiprocessing import Manager, Pool
from multiprocessing.pool import AsyncResult, Pool as ProcessPool
from queue import Queue

from sqlalchemy import and_, select

import eleanor.variable_space as vs
from eleanor.sailor import Sailor

from .config import Config, DatabaseConfig, load_config
from .exceptions import EleanorException
from .kernel.discover import import_kernel_module
from .kernel.interface import AbstractKernel
from .order import HufferResult, NavigatorProtocol, Order, load_order
from .transformers import transform
from .typing import Callable, EleanorKwargs, Self, Unpack, cast
from .util import Progress, chunks
from .version import __version__
from .yeoman import Yeoman, column_expr


class Eleanor(object):
    config: Config
    order: Order
    kernel_args: list[object]

    def __init__(self, config: str | Config, order: str | Order, kernel_args: list[object]):
        self.config = load_config(config)
        self.order = load_order(order)
        self.kernel_args = kernel_args

    def recur(self, config: str | Config, order: str | Order, kernel_args: list[object]) -> Self:
        return self.__class__(config, order, kernel_args)

    def run(
        self,
        simulation_size: int,
        *args: object,
        order_id: int | None = None,
        combined: bool = False,
        proportional_sampling: bool = False,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[int]:
        if len(self.order.transformers) != 0:
            kernel = self.load_kernel(**kwargs)
            self.order = transform(self.order, kernel)

        return self._run(
            simulation_size,
            *args,
            order_id=order_id,
            combined=combined,
            proportional_sampling=proportional_sampling,
            **kwargs,
        )

    def _run(
        self,
        simulation_size: int,
        *args: object,
        order_id: int | None = None,
        combined: bool = False,
        proportional_sampling: bool = False,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[int]:
        if self.order.suborders is not None and len(self.order.suborders.suborders) != 0:
            order_ids: set[int] = set()

            suborders = self.order.split_suborders()
            combined = combined or self.order.suborders.combined
            proportional_sampling = proportional_sampling or self.order.suborders.proportional_sampling

            if combined and order_id is None:
                order_id = self.ignite(*args, **kwargs)

            volume = self.order.volume()

            for suborder in suborders:
                suborder_samples = simulation_size
                if proportional_sampling:
                    suborder_samples = round(suborder_samples * suborder.volume() / volume)

                eleanor = self.recur(self.config, suborder, self.kernel_args)
                suborder_ids = eleanor._run(
                    suborder_samples,
                    *args,
                    order_id=order_id,
                    combined=combined,
                    proportional_sampling=proportional_sampling,
                    **kwargs,
                )
                order_ids.update(suborder_ids)

            return sorted(order_ids)

        return self.dispatch(simulation_size, *args, order_id=order_id, **kwargs)

    def dispatch(
        self,
        simulation_size: int,
        *args: object,
        order_id: int | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[int]:
        no_huffer = kwargs.get('no_huffer', False)
        num_procs = kwargs.get('num_procs', None)
        show_progress = kwargs.get('show_progress', False)
        success_sampling = kwargs.get('success_sampling', False)

        kernel = self.load_kernel(**kwargs)
        if self.order.navigator is None:
            raise EleanorException('order navigator is required')
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

        progress: Progress | None = None
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
                    progress=progress.queue if progress is not None else None,
                    **kwargs,
                )

        if progress is not None:
            progress.join()

        return [order_id]

    def process(
        self,
        kernel: AbstractKernel,
        navigator: NavigatorProtocol,
        simulation_size: int,
        order_id: int,
        *args: object,
        pool: ProcessPool | None = None,
        progress: Queue[bool | int] | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> None:
        if pool is None:
            raise EleanorException('no process pool created')

        success_sampling = kwargs.get('success_sampling', False)

        while True:
            vs_points = navigator.navigate(simulation_size, order_id=order_id, max_attempts=1)
            if progress is not None:
                progress.put(len(vs_points))

            vs_point_ids: list[int] = []

            futures: list[AsyncResult[list[int]]] = []
            process_count = cast(int, getattr(pool, '_processes', 1))
            sailor = Sailor(kernel, self.config.database)
            for batch in list(chunks(vs_points, process_count)):
                sailor_kwargs: EleanorKwargs = {**kwargs, 'success_sampling': success_sampling}
                future = pool.apply_async(
                    sailor.dispatch,
                    (batch, *args),
                    {**sailor_kwargs, 'progress': progress},
                )
                futures.append(future)

            while futures:
                future = futures.pop()
                vs_point_ids.extend(future.get())

            if navigator.is_complete(vs_point_ids):
                break

    def load_kernel(self, **kwargs: Unpack[EleanorKwargs]) -> AbstractKernel:
        if self.order.kernel is None:
            raise EleanorException('order kernel is required')
        kernel_module = import_kernel_module(self.order.kernel.type)
        kernel_ctor = cast(Callable[..., AbstractKernel], kernel_module.Kernel)
        kernel = kernel_ctor(self.order.kernel.settings, *self.kernel_args)
        kernel.setup(self.order, **kwargs)

        return kernel

    def ignite(
        self,
        *args: object,
        huffer_with: tuple[AbstractKernel, NavigatorProtocol] | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> int:
        kernel: AbstractKernel | None = None
        if huffer_with is not None:
            kernel, navigator = huffer_with
            huffer_problem = navigator.huffer_problem()
            # Force ``scratch=True`` via the kwargs bag so ``Sailor.work``
            # doesn't get two values for the same keyword argument when
            # ``kwargs`` already carries a user-supplied ``scratch`` from
            # the CLI flow.
            work_kwargs: EleanorKwargs = {**kwargs, 'scratch': True}
            huffer_point = Sailor(kernel).work(huffer_problem, *args, **work_kwargs)
            self.order.huffer_result = HufferResult.from_scratch(huffer_point.scratch, huffer_point.exit_code)
        else:
            huffer_point = None
            self.order.huffer_result = None

        with Yeoman(self.config.database) as yeoman:
            yeoman.setup()

            if yeoman.scalar(select(Order).where(column_expr(Order.eleanor_version != __version__))):
                raise EleanorException('cannot add order to a database created with a different version of Eleanor')

            result = yeoman.scalar(
                select(Order).where(
                    and_(
                        column_expr(Order.hash == self.order.hash),
                        column_expr(Order.eleanor_version == __version__),
                    )))

            if result is not None:
                order_id = self.order.id = result.id
                self.order.eleanor_version = result.eleanor_version

                if self.order.huffer_result is not None:
                    if result.huffer_result is None:
                        result.huffer_result = self.order.huffer_result
                    else:
                        result.huffer_result.exit_code = self.order.huffer_result.exit_code
                        result.huffer_result.zip = self.order.huffer_result.zip

                _ = yeoman.merge(result)
                yeoman.commit()
            else:
                self.order.eleanor_version = __version__
                yeoman.write(self.order, refresh=True)
                order_id = self.order.id

        if huffer_point is not None and kernel is not None and not kernel.is_soft_exit(huffer_point.exit_code):
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
                    column_expr(vs.Point.exit_code == 0),
                    column_expr(vs.Point.order_id == order_id),
                )).count()
            return successes
