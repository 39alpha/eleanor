from contextlib import AbstractContextManager, nullcontext
from multiprocessing import Manager
from queue import Queue

from sqlalchemy import and_, select

from eleanor.sailor import Sailor

from .config import Config, load_config
from .executor import AbstractExecutor, build_executor
from .exceptions import EleanorException
from .kernel.discover import import_kernel_module
from .kernel.interface import AbstractKernel
from .order import HufferResult, NavigatorProtocol, Order, load_order
from .output import ComputeResult, OutputSink, PostgresSink, RunStats, WriteOutcome
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

    def _parallel_defaults(self) -> tuple[str, int]:
        return self.config.parallel.backend, self.config.parallel.chunks_per_worker

    @staticmethod
    def _executor_context(
        executor: AbstractExecutor | None,
        *,
        parallel: str,
        num_workers: int | None,
    ) -> AbstractContextManager[AbstractExecutor]:
        """Return a context manager yielding an :class:`AbstractExecutor`.

        When an externally-owned ``executor`` is supplied, wrap it in a
        :func:`contextlib.nullcontext` so the caller retains ownership of its
        lifetime. Otherwise, build a fresh executor via :func:`build_executor`.
        """
        if executor is not None:
            return nullcontext(executor)
        return build_executor(kind=parallel, num_workers=num_workers)

    def run(
        self,
        simulation_size: int,
        *args: object,
        order_id: int | None = None,
        combined: bool = False,
        proportional_sampling: bool = False,
        parallel: str | None = None,
        chunks_per_worker: int | None = None,
        executor: AbstractExecutor | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[int]:
        if len(self.order.transformers) != 0:
            kernel = self.load_kernel(**kwargs)
            self.order = transform(self.order, kernel)

        default_parallel, default_chunks_per_worker = self._parallel_defaults()
        if parallel is None:
            parallel = default_parallel
        if chunks_per_worker is None:
            chunks_per_worker = default_chunks_per_worker

        executor_context = self._executor_context(
            executor,
            parallel=parallel,
            num_workers=kwargs.get('num_procs'),
        )

        with executor_context as run_executor:
            return self._run(
                simulation_size,
                *args,
                order_id=order_id,
                combined=combined,
                proportional_sampling=proportional_sampling,
                parallel=parallel,
                chunks_per_worker=chunks_per_worker,
                executor=run_executor,
                **kwargs,
            )

    def _run(
        self,
        simulation_size: int,
        *args: object,
        order_id: int | None = None,
        combined: bool = False,
        proportional_sampling: bool = False,
        parallel: str | None = None,
        chunks_per_worker: int | None = None,
        executor: AbstractExecutor | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[int]:
        default_parallel, default_chunks_per_worker = self._parallel_defaults()
        if parallel is None:
            parallel = default_parallel
        if chunks_per_worker is None:
            chunks_per_worker = default_chunks_per_worker

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
                    parallel=parallel,
                    chunks_per_worker=chunks_per_worker,
                    executor=executor,
                    **kwargs,
                )
                order_ids.update(suborder_ids)

            return sorted(order_ids)

        return self.dispatch(
            simulation_size,
            *args,
            order_id=order_id,
            parallel=parallel,
            chunks_per_worker=chunks_per_worker,
            executor=executor,
            **kwargs,
        )

    def dispatch(
        self,
        simulation_size: int,
        *args: object,
        order_id: int | None = None,
        parallel: str | None = None,
        chunks_per_worker: int | None = None,
        executor: AbstractExecutor | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[int]:
        no_huffer = kwargs.get('no_huffer', False)
        num_procs = kwargs.get('num_procs', None)
        show_progress = kwargs.get('show_progress', False)
        success_sampling = kwargs.get('success_sampling', False)
        verbose = kwargs.get('verbose', False)

        default_parallel, default_chunks_per_worker = self._parallel_defaults()
        if parallel is None:
            parallel = default_parallel
        if chunks_per_worker is None:
            chunks_per_worker = default_chunks_per_worker

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
        self.order.id = order_id

        progress: Progress | None = None
        manager = None
        if show_progress:
            manager = Manager()
            progress = Progress(manager, no_total_update=success_sampling)

        executor_context = self._executor_context(
            executor,
            parallel=parallel,
            num_workers=num_procs,
        )

        output_sink = self.load_output_sink(verbose=bool(verbose))
        output_sink.begin_run(self.order, self.order.huffer_result)

        stats = RunStats()

        try:
            with executor_context as dispatch_executor:
                if success_sampling:
                    # Each call to dispatch targets exactly simulation_size new successful
                    # points. Pre-existing successes already in the database are not counted.
                    while stats.succeeded < simulation_size:
                        outcomes = self.process(
                            kernel,
                            navigator,
                            simulation_size - stats.succeeded,
                            order_id,
                            *args,
                            executor=dispatch_executor,
                            chunks_per_worker=chunks_per_worker,
                            sink=output_sink,
                            progress=progress.queue if progress is not None else None,
                            **kwargs,
                        )
                        stats.update(outcomes)
                else:
                    outcomes = self.process(
                        kernel,
                        navigator,
                        simulation_size,
                        order_id,
                        *args,
                        executor=dispatch_executor,
                        chunks_per_worker=chunks_per_worker,
                        sink=output_sink,
                        progress=progress.queue if progress is not None else None,
                        **kwargs,
                    )
                    stats.update(outcomes)

            output_sink.finalize()
        finally:
            if progress is not None:
                progress.join()
            if manager is not None:
                manager.shutdown()

        return [order_id]

    def process(
        self,
        kernel: AbstractKernel,
        navigator: NavigatorProtocol,
        simulation_size: int,
        order_id: int,
        *args: object,
        executor: AbstractExecutor | None = None,
        chunks_per_worker: int = 1,
        sink: OutputSink,
        progress: Queue[bool | int] | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[WriteOutcome]:
        if executor is None:
            raise EleanorException('no process executor created')
        if executor.num_workers <= 0:
            raise EleanorException('executor num_workers must be >= 1')
        if chunks_per_worker <= 0:
            raise EleanorException('chunks_per_worker must be >= 1')

        success_sampling = kwargs.get('success_sampling', False)
        outcomes: list[WriteOutcome] = []

        while True:
            vs_points = navigator.navigate(simulation_size, order_id=order_id, max_attempts=1)
            if progress is not None:
                progress.put(len(vs_points))

            vs_point_ids: list[int] = []

            futures = []
            # Cap chunk count at the number of points so we never produce
            # empty batches when num_workers * chunks_per_worker exceeds
            # len(vs_points).
            chunk_count = min(len(vs_points), executor.num_workers * chunks_per_worker)
            for batch in chunks(vs_points, chunk_count):
                sailor_kwargs: EleanorKwargs = {**kwargs}
                future = executor.submit(
                    Sailor(kernel).dispatch,
                    batch,
                    *args,
                    **sailor_kwargs,
                )
                futures.append(future)

            compute_results: list[ComputeResult] = []
            while futures:
                future = futures.pop()
                compute_results.extend(future.result())

            batch_outcomes = sink.write_batch(order_id, compute_results)
            outcomes.extend(batch_outcomes)

            for outcome in batch_outcomes:
                if outcome.point_id is not None:
                    vs_point_ids.append(outcome.point_id)
                if progress is not None and (not success_sampling or outcome.exit_code == 0):
                    progress.put(True)

            if navigator.is_complete(vs_point_ids):
                break

        return outcomes

    def load_output_sink(self, verbose: bool = False) -> OutputSink:
        match self.config.output.type:
            case 'postgres':
                return PostgresSink(self.config.database, verbose=verbose)
            case _:
                raise EleanorException(f'unsupported output sink type "{self.config.output.type}"')

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
