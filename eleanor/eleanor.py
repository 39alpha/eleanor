from contextlib import AbstractContextManager, nullcontext
from multiprocessing import Manager
from queue import Queue
from typing import TYPE_CHECKING

from eleanor.sailor import Sailor

from .config import Config, load_config
from .executor import AbstractExecutor, AbstractFuture, build_executor
from .exceptions import EleanorException
from .kernel.interface import AbstractKernel
from .kernel.registry import get_factory as get_kernel_spec
from .order import NavigatorProtocol, Order, load_order
from .output.interface import ComputeResult, OutputSink, RunStats, WriteOutcome
from .output.registry import get_factory as get_output_factory
from .transformer import transform
from .typing import EleanorKwargs, Self, Unpack, cast
from .util import Progress, chunks
from .version import __version__

if TYPE_CHECKING:
    from .transformer import AbstractTransformer


class Eleanor(object):
    config: Config
    order: Order
    kernel_args: list[object]

    def __init__(
        self,
        config: str | Config,
        order: str | Order,
        kernel_args: list[object],
        order_id: int | None = None,
        tag: str | None = None
    ):
        self.config = load_config(config)
        self.order = load_order(order, order_id=order_id, tag=tag)
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
        kernel: AbstractKernel | None = None,
        navigator: NavigatorProtocol | None = None,
        output_sink: OutputSink | None = None,
        transformers: 'list[AbstractTransformer] | None' = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[int]:
        if transformers is not None or len(self.order.transformers) != 0:
            run_kernel = kernel if kernel is not None else self.load_kernel(**kwargs)
            self.order = transform(self.order, run_kernel, overrides=transformers)

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
                kernel=kernel,
                navigator=navigator,
                output_sink=output_sink,
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
        kernel: AbstractKernel | None = None,
        navigator: NavigatorProtocol | None = None,
        output_sink: OutputSink | None = None,
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
                verbose = kwargs.get('verbose', False)
                output_sink = output_sink if output_sink is not None else self.load_output_sink(verbose=verbose)
                order_id = output_sink.begin_run(self.order)

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
                    kernel=kernel,
                    navigator=navigator,
                    output_sink=output_sink,
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
            kernel=kernel,
            navigator=navigator,
            output_sink=output_sink,
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
        kernel: AbstractKernel | None = None,
        navigator: NavigatorProtocol | None = None,
        output_sink: OutputSink | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[int]:
        num_procs = kwargs.get('num_procs', None)
        show_progress = kwargs.get('show_progress', False)
        success_sampling = kwargs.get('success_sampling', False)
        verbose = kwargs.get('verbose', False)

        default_parallel, default_chunks_per_worker = self._parallel_defaults()
        if parallel is None:
            parallel = default_parallel
        if chunks_per_worker is None:
            chunks_per_worker = default_chunks_per_worker

        if kernel is None:
            kernel = self.load_kernel(**kwargs)

        if navigator is None:
            if self.order.navigator is None:
                raise EleanorException('order navigator is required')
            from .navigator.registry import get_factory as get_navigator_factory
            navigator_factory = get_navigator_factory(self.order.navigator.type)
            built = navigator_factory(self.order, kernel, **self.order.navigator.args)
            if not isinstance(built, NavigatorProtocol):
                raise EleanorException(
                    f'navigator plugin "{self.order.navigator.type}" returned '
                    + f'{type(built).__name__}, expected an AbstractNavigator',
                )
            navigator = built

        if success_sampling and not navigator.supports_success_sampling():
            msg = f"{navigator.__class__.__module__}.{navigator.__class__.__name__} does not support success sampling"
            raise EleanorException(msg)

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

        output_sink = output_sink if output_sink is not None else self.load_output_sink(verbose=verbose)
        if order_id is not None:
            self.order.id = order_id
        order_id = output_sink.begin_run(self.order)

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

        worker_writes = sink.supports_worker_writes()

        while True:
            vs_points = navigator.navigate(simulation_size, order_id=order_id, max_attempts=1)
            if progress is not None:
                progress.put(len(vs_points))

            vs_point_ids: list[int] = []

            # Cap chunk count at the number of points so we never produce
            # empty batches when num_workers * chunks_per_worker exceeds
            # len(vs_points).
            chunk_count = min(len(vs_points), executor.num_workers * chunks_per_worker)

            sailor_kwargs: EleanorKwargs = {**kwargs}

            if worker_writes:
                # Sinks that opt in to worker writes receive the sink and
                # ``order_id`` through to ``Sailor.dispatch``, which invokes
                # ``sink.write_batch`` inside the worker. The future therefore
                # resolves directly to a small ``list[WriteOutcome]`` payload,
                # avoiding the IPC cost of shipping full ``ComputeResult``s
                # (and their mapped ``vs.Point`` graph) back to the parent.
                outcome_futures: list[AbstractFuture[list[WriteOutcome]]] = []
                for batch in chunks(vs_points, chunk_count):
                    # ``Sailor.dispatch`` has a ``list[ComputeResult] |
                    # list[WriteOutcome]`` union return type, but with a sink
                    # and ``order_id`` supplied it always returns
                    # ``list[WriteOutcome]``. ``AbstractFuture`` is invariant
                    # over its type parameter, so narrow the future here.
                    outcome_future = cast(
                        AbstractFuture[list[WriteOutcome]],
                        executor.submit(
                            Sailor(kernel).dispatch,
                            batch,
                            *args,
                            sink=sink,
                            order_id=order_id,
                            **sailor_kwargs,
                        ),
                    )
                    outcome_futures.append(outcome_future)

                batch_outcomes: list[WriteOutcome] = []
                while outcome_futures:
                    outcome_future = outcome_futures.pop()
                    batch_outcomes.extend(outcome_future.result())
            else:
                # Serial sinks are driven by the main process: workers return
                # full ``ComputeResult`` payloads, which are then written here.
                compute_futures: list[AbstractFuture[list[ComputeResult]]] = []
                for batch in chunks(vs_points, chunk_count):
                    # See the ``worker_writes`` branch above: without a sink,
                    # ``Sailor.dispatch`` always resolves to
                    # ``list[ComputeResult]``, so narrow the invariant future.
                    compute_future = cast(
                        AbstractFuture[list[ComputeResult]],
                        executor.submit(
                            Sailor(kernel).dispatch,
                            batch,
                            *args,
                            **sailor_kwargs,
                        ),
                    )
                    compute_futures.append(compute_future)

                compute_results: list[ComputeResult] = []
                while compute_futures:
                    compute_future = compute_futures.pop()
                    compute_results.extend(compute_future.result())

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
        factory = get_output_factory(self.config.output.type)
        built = factory(self.config, verbose=verbose, **self.config.output.args)
        if not isinstance(built, OutputSink):
            raise EleanorException(
                f'output sink plugin "{self.config.output.type}" returned '
                + f'{type(built).__name__}, expected an OutputSink',
            )
        return built

    def load_kernel(self, **kwargs: Unpack[EleanorKwargs]) -> AbstractKernel:
        if self.order.kernel is None:
            raise EleanorException('order kernel is required')
        spec = get_kernel_spec(self.order.kernel.type)
        settings = self.order.kernel.resolved_settings()
        kernel = spec.build(settings, *self.kernel_args)
        if not isinstance(kernel, AbstractKernel):
            raise EleanorException(
                f'kernel plugin "{self.order.kernel.type}" returned '
                + f'{type(kernel).__name__}, expected an AbstractKernel',
            )
        kernel.setup(self.order, **kwargs)
        kernel.validate_order(self.order)

        return kernel
