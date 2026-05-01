from contextlib import ExitStack, contextmanager
from multiprocessing import Manager
from multiprocessing.managers import SyncManager
from types import TracebackType
from typing import TYPE_CHECKING

from eleanor.sailor import Sailor

from .config import Config
from .exceptions import EleanorException
from .executor import AbstractExecutor, AbstractFuture, build_executor
from .kernel.interface import AbstractKernel
from .kernel.registry import get_factory as get_kernel_spec
from .order import NavigatorProtocol, Order
from .output.interface import ComputeResult, OutputSink, RunStats, WriteOutcome
from .output.registry import get_factory as get_output_factory
from .plugin import is_abstract_instantiation_error, resolve_api_version
from .progress import ManagedProgressHandle, Progress, ProgressHandle
from .transformer import transform
from .typing import EleanorKwargs, Self, Unpack, cast
from .util import chunks

if TYPE_CHECKING:
    from collections.abc import Generator

    from .transformer import AbstractTransformer


class Eleanor(object):
    """An engine for dispatching :class:`Order` runs.

    An :class:`Eleanor` instance owns its long-lived resources (executor
    worker pool, progress :class:`~multiprocessing.managers.SyncManager`,
    output sink) for the duration of a ``with`` block, and reuses them
    across any number of :meth:`run` calls made inside that block::

        with Eleanor(config, kernel_args) as eleanor:
            eleanor.run(order1, 1000)
            eleanor.run(order2, 2000)

    Outside of a ``with`` block, each :meth:`run` call builds the
    resources it needs and tears them down on exit, so one-shot usage
    remains a single method call::

        Eleanor(config, kernel_args).run(order, 1000)

    Constructor-level ``executor`` and ``output_sink`` keyword arguments
    override the Config-derived defaults for every :meth:`run` call on
    this instance.  Caller retains ownership — Eleanor never shuts down
    or finalizes them.  Per-run ``output_sink=`` kwargs on individual
    :meth:`run` calls still take precedence.
    """

    config: Config
    kernel_args: list[object]
    num_procs: int | None

    # Caller-supplied session-level overrides. Caller retains ownership:
    # Eleanor never enters/shuts down the executor override and never
    # finalizes the output-sink override.
    _executor_override: AbstractExecutor | None
    _output_sink_override: OutputSink | None

    # Resources owned by the engine when used as a context manager.
    # ``_entered`` controls the "session vs. per-run" resource lifetime.
    _entered: bool
    _executor: AbstractExecutor | None
    _manager: SyncManager | None
    _output_sink: OutputSink | None

    def __init__(
        self,
        config: Config,
        kernel_args: list[object] | None = None,
        num_procs: int | None = None,
        *,
        executor: AbstractExecutor | None = None,
        output_sink: OutputSink | None = None,
    ):
        self.config = config
        self.kernel_args = list(kernel_args) if kernel_args is not None else []
        self.num_procs = num_procs

        self._executor_override = executor
        self._output_sink_override = output_sink

        self._entered = False
        self._executor = None
        self._manager = None
        self._output_sink = None

    def __enter__(self) -> Self:
        """Activate session-scoped resources.

        When no constructor-level ``executor`` was supplied, one is built from
        :attr:`config` and entered eagerly so workers are warm for the first
        :meth:`run` call. When a constructor-level executor override is
        supplied, Eleanor reuses it as-is and never enters or shuts it down;
        caller-owned lifecycle may be context-managed or manual.

        The progress :class:`SyncManager` and :class:`OutputSink` are left
        unbuilt until the first :meth:`run` that needs them.
        """
        if self._executor_override is None:
            parallel, _ = self._parallel_defaults()
            self._executor = build_executor(kind=parallel, num_workers=self.num_procs)
            _ = self._executor.__enter__()
        self._entered = True
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Tear down session-scoped resources.

        The three resources shut down independently so a failure in one
        does not mask failures in the others; the first exception is
        re-raised after the rest have been attempted.
        """
        first_error: BaseException | None = None

        if self._output_sink is not None:
            try:
                self._output_sink.finalize()
            except BaseException as error:
                first_error = error
            finally:
                self._output_sink = None

        if self._manager is not None:
            try:
                self._manager.shutdown()
            except BaseException as error:
                if first_error is None:
                    first_error = error
            finally:
                self._manager = None

        if self._executor is not None:
            try:
                self._executor.shutdown(wait=True)
            except BaseException as error:
                if first_error is None:
                    first_error = error
            finally:
                self._executor = None

        self._entered = False

        if first_error is not None:
            raise first_error

    def _parallel_defaults(self) -> tuple[str, int]:
        return self.config.parallel.backend, self.config.parallel.chunks_per_worker

    @contextmanager
    def _executor_scope(
        self,
        *,
        parallel: str,
    ) -> "Generator[AbstractExecutor, None, None]":
        """Yield an executor for the duration of one :meth:`run` call.

        Preference order:
        * ``self._executor_override`` (constructor-level) — returned
          as-is, caller keeps ownership.
        * ``self._executor`` (session-scoped, built in :meth:`__enter__`)
          — returned as-is.
        * a freshly-built executor torn down when this scope exits
          (one-shot usage: Eleanor not used as a context manager).
        """
        if self._executor_override is not None:
            yield self._executor_override
            return
        if self._entered and self._executor is not None:
            yield self._executor
            return
        with build_executor(kind=parallel, num_workers=self.num_procs) as executor:
            yield executor

    @contextmanager
    def _manager_scope(self) -> "Generator[SyncManager, None, None]":
        """Yield a :class:`SyncManager` for the duration of one :meth:`run`.

        Session-scoped when inside a ``with`` block, lazily initialised
        on first use; per-run and torn down on scope exit otherwise.
        """
        if self._entered:
            if self._manager is None:
                self._manager = Manager()
            yield self._manager
            return

        manager = Manager()
        try:
            yield manager
        finally:
            manager.shutdown()

    @contextmanager
    def _sink_scope(
        self,
        override: OutputSink | None,
        *,
        verbose: bool,
    ) -> "Generator[OutputSink, None, None]":
        """Yield an :class:`OutputSink` for the duration of one :meth:`run` call.

        Preference order:

        * Per-run ``override`` wins. Eleanor takes the full lifecycle for the
          single :meth:`run` call: :meth:`~OutputSink.initialize` on entry,
          :meth:`~OutputSink.finalize_run` on exit, then
          :meth:`~OutputSink.finalize` on exit (in that order).
        * ``self._output_sink_override`` (constructor-level) — returned
          as-is, caller keeps ownership of
          :meth:`~OutputSink.initialize` / :meth:`~OutputSink.finalize`.
          Eleanor still calls :meth:`~OutputSink.finalize_run` per run.
        * ``self._output_sink`` (session-scoped, lazily built from
          :attr:`config`) — :meth:`~OutputSink.initialize`-d at construction
          time, :meth:`~OutputSink.finalize_run`-d on every run scope exit,
          and :meth:`~OutputSink.finalize`-d once at :meth:`__exit__`.
        * A fresh per-run sink built from :attr:`config` — full lifecycle
          (:meth:`~OutputSink.initialize`, :meth:`~OutputSink.finalize_run`,
          :meth:`~OutputSink.finalize`) collapsed into the single
          :meth:`run` call.

        .. note::
            When session-scoped (third branch), the ``verbose`` setting of
            the **first** :meth:`run` call that creates the sink is used
            for the entire session. Subsequent calls with a different
            ``verbose`` value will not affect the existing sink.
        """
        if override is not None:
            override.initialize()
            try:
                yield override
            finally:
                try:
                    override.finalize_run()
                finally:
                    override.finalize()
            return

        if self._output_sink_override is not None:
            try:
                yield self._output_sink_override
            finally:
                self._output_sink_override.finalize_run()
            return

        if self._entered:
            if self._output_sink is None:
                self._output_sink = self.load_output_sink(verbose=verbose)
                self._output_sink.initialize()
            try:
                yield self._output_sink
            finally:
                self._output_sink.finalize_run()
            return

        sink = self.load_output_sink(verbose=verbose)
        sink.initialize()
        try:
            yield sink
        finally:
            try:
                sink.finalize_run()
            finally:
                sink.finalize()

    def run(
        self,
        order: Order,
        simulation_size: int,
        *args: object,
        parallel: str | None = None,
        chunks_per_worker: int | None = None,
        batch_size: int | None = None,
        kernel: AbstractKernel | None = None,
        navigator: NavigatorProtocol | None = None,
        output_sink: OutputSink | None = None,
        transformers: "list[AbstractTransformer] | None" = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[int]:
        """Dispatch ``order`` against ``simulation_size`` VS points.
        See the class docstring for the session-vs-per-run resource model.

        If an explicit ``output_sink`` is supplied, Eleanor takes the full
        sink lifecycle for the duration of this :meth:`run` call:
        :meth:`~OutputSink.initialize` on entry, then
        :meth:`~OutputSink.finalize_run` and :meth:`~OutputSink.finalize`
        on exit.
        """
        # ``executor`` was a named parameter prior to this branch; the double cast
        # lets basedpyright accept a membership test for a key outside EleanorKwargs.
        if "executor" in cast(dict[str, object], cast(object, kwargs)):
            raise TypeError("Eleanor.run() got an unexpected keyword argument 'executor'")
        verbose = kwargs.get("verbose", False)
        show_progress = kwargs.get("show_progress", False)

        default_parallel, default_chunks_per_worker = self._parallel_defaults()
        if parallel is None:
            parallel = default_parallel
        if chunks_per_worker is None:
            chunks_per_worker = default_chunks_per_worker
        # Apply transformers before dispatch: they can rewrite order-scoped
        # state, so dispatch must see the transformed order.
        # ``effective_kernel`` captures the kernel used for this run: when
        # transformers are applied it is loaded once here and reused for
        # dispatch, so kernel construction happens at most once per
        # ``run()`` call.
        effective_kernel = kernel
        if transformers is not None or len(order.transformers) != 0:
            if effective_kernel is None:
                effective_kernel = self.load_kernel(order, **kwargs)
            order = transform(order, effective_kernel, overrides=transformers)

        with ExitStack() as stack:
            run_executor = stack.enter_context(
                self._executor_scope(parallel=parallel),
            )
            run_sink = stack.enter_context(
                self._sink_scope(output_sink, verbose=verbose),
            )
            run_manager: SyncManager | None = None
            if show_progress:
                run_manager = stack.enter_context(self._manager_scope())
            if run_executor.num_workers <= 0:
                raise EleanorException("executor num_workers must be >= 1")
            if chunks_per_worker <= 0:
                raise EleanorException("chunks_per_worker must be >= 1")

            if effective_kernel is None:
                effective_kernel = self.load_kernel(order, **kwargs)

            if navigator is None:
                from .navigator.registry import get_factory as get_navigator_factory

                navigator_factory = get_navigator_factory(order.navigator.type)
                version = resolve_api_version(navigator_factory)
                try:
                    built = navigator_factory(order, effective_kernel, **order.navigator.args)
                except TypeError as e:
                    if not is_abstract_instantiation_error(e):
                        raise
                    version_suffix = "" if version is None else f" (API v{version})"
                    raise EleanorException(
                        f'navigator plugin "{order.navigator.type}" failed to instantiate{version_suffix}: {e}',
                    ) from e
                if not isinstance(built, NavigatorProtocol):
                    raise EleanorException(
                        f'navigator plugin "{order.navigator.type}" returned '
                        + f"{type(built).__name__}, expected an AbstractNavigator",
                    )
                navigator = built

            assert navigator is not None
            expected_total = navigator.num_systems(simulation_size)
            if expected_total <= 0:
                raise EleanorException(
                    f"navigator.num_systems({simulation_size}) returned {expected_total}; must be >= 1",
                )
            effective_batch_size = batch_size if batch_size is not None else expected_total
            if batch_size is not None and batch_size <= 0:
                raise EleanorException("batch_size must be >= 1")

            progress: Progress | None = None
            # Local handles use ``ManagedProgressHandle`` rather than the worker-
            # facing ``ProgressHandle`` so the dispatch context can call ``done()``
            # at teardown.  Anywhere these are forwarded to a producer
            # (``process()`` / ``Sailor.dispatch`` / ``OutputSink.write_batch``)
            # they implicitly narrow to ``ProgressHandle``, which omits ``done()``.
            sim_handle: ManagedProgressHandle | None = None
            out_handle: ManagedProgressHandle | None = None
            if show_progress:
                if run_manager is None:
                    raise EleanorException("show_progress requires an active SyncManager")
                progress = Progress(run_manager)
                sim_handle = progress.sim
                if run_sink.supports_progress():
                    out_handle = progress.out
                sim_handle.total(expected_total)
                if out_handle is not None:
                    out_handle.total(expected_total)

            order.id = run_sink.begin_run(order)

            stats = RunStats()

            try:
                outcomes = self.process(
                    effective_kernel,
                    navigator,
                    simulation_size,
                    order.id,
                    *args,
                    batch_size=effective_batch_size,
                    expected_total=expected_total,
                    executor=run_executor,
                    chunks_per_worker=chunks_per_worker,
                    sink=run_sink,
                    sim_progress=sim_handle,
                    out_progress=out_handle,
                    **kwargs,
                )
                stats.update(outcomes)
            finally:
                if progress is not None:
                    # ``sim_handle`` is co-assigned with ``progress`` above, but
                    # the type checker can't infer that link from the
                    # ``progress is not None`` narrowing alone.  Closing the sim
                    # bar via ``progress.sim.done()`` keeps the live invariant
                    # — "progress drives sim" — as the single discriminant.
                    # ``out_handle`` legitimately may be ``None`` here when the
                    # active sink does not opt in to progress reporting.
                    progress.sim.done()
                    if out_handle is not None:
                        out_handle.done()
                    progress.join()

            return [order.id]

    def process(
        self,
        kernel: AbstractKernel,
        navigator: NavigatorProtocol,
        simulation_size: int,
        order_id: int,
        *args: object,
        batch_size: int,
        expected_total: int,
        executor: AbstractExecutor | None = None,
        chunks_per_worker: int = 1,
        sink: OutputSink,
        sim_progress: ProgressHandle | None = None,
        out_progress: ProgressHandle | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[WriteOutcome]:
        """Drive the navigator/executor/sink loop for a single leaf order.
        :param sim_progress: Handle for the simulation bar. Forwarded to
            :meth:`Sailor.dispatch` so workers can emit per-point ticks;
            when the executor does not support worker-side progress, ticks
            are emitted in the parent after each future resolves.
        :param out_progress: Handle for the output bar. Passed to
            :meth:`OutputSink.write_batch`; the sink decides its own tick
            cadence. For worker-write sinks on executors without
            worker-progress support, a single batch-level tick per future is
            emitted in the parent as a fallback.
        """
        if executor is None:
            raise EleanorException("no process executor created")
        if executor.num_workers <= 0:
            raise EleanorException("executor num_workers must be >= 1")
        if chunks_per_worker <= 0:
            raise EleanorException("chunks_per_worker must be >= 1")

        outcomes: list[WriteOutcome] = []

        worker_writes = sink.supports_worker_writes()

        # When the executor cannot forward a ``Manager``-backed queue into
        # its workers, we must not hand the handles to ``Sailor.dispatch``;
        # the parent will emit coarser batch-granularity ticks instead.
        worker_sim_progress = sim_progress if executor.supports_worker_progress else None
        worker_out_progress = out_progress if executor.supports_worker_progress else None
        total_produced = 0
        for vs_points in navigator.navigate(
            simulation_size,
            batch_size,
            order_id=order_id,
            max_attempts=1,
        ):
            total_produced += len(vs_points)
            if len(vs_points) == 0:
                continue

            # Cap chunk count at the number of points so we never produce
            # empty batches when num_workers * chunks_per_worker exceeds
            # len(vs_points).
            chunk_count = min(len(vs_points), executor.num_workers * chunks_per_worker)

            sailor_kwargs: EleanorKwargs = {**kwargs}
            batch_outcomes: list[WriteOutcome] = []

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
                            sim_progress=worker_sim_progress,
                            out_progress=worker_out_progress,
                            **sailor_kwargs,
                        ),
                    )
                    outcome_futures.append(outcome_future)

                while outcome_futures:
                    outcome_future = executor.pop_completed_future(outcome_futures)
                    result = outcome_future.result()
                    batch_outcomes.extend(result)
                    # Fallback batch-level ticks for executors that cannot
                    # forward the ProgressHandle into workers. Empty futures
                    # are skipped so the bar never gets a spurious tick(0).
                    if worker_sim_progress is None and sim_progress is not None and result:
                        sim_progress.tick(len(result))
                    if worker_out_progress is None and out_progress is not None:
                        committed = sum(1 for o in result if o.committed and o.exit_code == 0)
                        if committed:
                            out_progress.tick(committed)
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
                            sim_progress=worker_sim_progress,
                            **sailor_kwargs,
                        ),
                    )
                    compute_futures.append(compute_future)

                while compute_futures:
                    compute_future = executor.pop_completed_future(compute_futures)
                    result = compute_future.result()
                    if worker_sim_progress is None and sim_progress is not None and result:
                        sim_progress.tick(len(result))
                    # Stream each resolved worker batch straight into the sink
                    # instead of accumulating all compute payloads in-memory.
                    # This reduces parent memory pressure and cuts time-to-
                    # first-write for large runs.
                    if len(result) == 0:
                        continue
                    # The sink owns the output bar's cadence: per-row,
                    # per-batch, or anything in between. Eleanor only hands
                    # over the handle.
                    batch_outcomes.extend(
                        sink.write_batch(
                            order_id,
                            result,
                            progress=out_progress,
                        )
                    )

            outcomes.extend(batch_outcomes)

        if total_produced != expected_total:
            raise EleanorException(
                f"navigator produced {total_produced} points, expected {expected_total}",
            )

        return outcomes

    def load_output_sink(self, verbose: bool = False) -> OutputSink:
        factory = get_output_factory(self.config.output.type)
        version = resolve_api_version(factory)
        try:
            built = factory(self.config, verbose=verbose, **self.config.output.args)
        except TypeError as e:
            if not is_abstract_instantiation_error(e):
                raise
            version_suffix = "" if version is None else f" (API v{version})"
            raise EleanorException(
                f'output sink plugin "{self.config.output.type}" failed to instantiate{version_suffix}: {e}',
            ) from e
        if not isinstance(built, OutputSink):
            raise EleanorException(
                f'output sink plugin "{self.config.output.type}" returned '
                + f"{type(built).__name__}, expected an OutputSink",
            )
        return built

    def load_kernel(self, order: Order, **kwargs: Unpack[EleanorKwargs]) -> AbstractKernel:
        spec = get_kernel_spec(order.kernel.type)
        settings = order.kernel.resolved_settings()
        try:
            kernel = spec.build(settings, *self.kernel_args)
        except TypeError as e:
            if not is_abstract_instantiation_error(e):
                raise
            raise EleanorException(
                f'kernel plugin "{order.kernel.type}" failed to instantiate '
                + f"(API v{spec.plugin_api_version}): {e}",
            ) from e
        if not isinstance(kernel, AbstractKernel):
            raise EleanorException(
                f'kernel plugin "{order.kernel.type}" returned '
                + f"{type(kernel).__name__}, expected an AbstractKernel",
            )
        kernel.setup(order, **kwargs)
        kernel.validate_order(order)

        return kernel
