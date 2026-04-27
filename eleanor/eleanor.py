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
from .progress import Progress, ProgressHandle
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
    or finalizes them.  Per-run ``executor=`` / ``output_sink=`` kwargs
    on individual :meth:`run` calls still take precedence.
    """

    config: Config
    kernel_args: list[object]
    num_procs: int | None

    # Caller-supplied session-level overrides.  Eleanor enters and exits the
    # executor override only when the caller has not already entered it
    # (detected via ``has_entered()``); the output-sink override is never
    # finalized by Eleanor.
    _executor_override: AbstractExecutor | None
    _entered_executor_override: bool  # True when Eleanor called __enter__ on it
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
        self._entered_executor_override = False
        self._output_sink_override = output_sink

        self._entered = False
        self._executor = None
        self._manager = None
        self._output_sink = None

    def __enter__(self) -> Self:
        """Activate session-scoped resources.

        When no constructor-level ``executor`` was supplied, one is built from
        :attr:`config` and entered eagerly so workers are warm for the first
        :meth:`run` call.  When one was supplied, Eleanor checks
        :meth:`~AbstractExecutor.has_entered`:

        * If the executor has **not** been entered (Pattern 1 — Eleanor owns
          lifecycle), Eleanor calls :meth:`~AbstractExecutor.__enter__` on it
          and will call :meth:`~AbstractExecutor.shutdown` at :meth:`__exit__`.
        * If it **has** already been entered (Pattern 2 — caller owns
          lifecycle), Eleanor uses it as-is and will not touch its lifecycle.

        The progress :class:`SyncManager` and :class:`OutputSink` are left
        unbuilt until the first :meth:`run` that needs them.
        """
        if self._executor_override is None:
            parallel, _ = self._parallel_defaults()
            self._executor = build_executor(kind=parallel, num_workers=self.num_procs)
            _ = self._executor.__enter__()
        elif not self._executor_override.has_entered():
            _ = self._executor_override.__enter__()
            self._entered_executor_override = True
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

        if self._executor_override is not None and self._entered_executor_override:
            try:
                self._executor_override.shutdown(wait=True)
            except BaseException as error:
                if first_error is None:
                    first_error = error
            finally:
                self._entered_executor_override = False

        self._entered = False

        if first_error is not None:
            raise first_error

    def _parallel_defaults(self) -> tuple[str, int]:
        return self.config.parallel.backend, self.config.parallel.chunks_per_worker

    @contextmanager
    def _executor_scope(
        self,
        override: AbstractExecutor | None,
        *,
        parallel: str,
    ) -> "Generator[AbstractExecutor, None, None]":
        """Yield an executor for the duration of one :meth:`run` call.

        Preference order:

        * ``override`` (per-run, externally-owned) — returned as-is,
          caller keeps ownership.
        * ``self._executor_override`` (constructor-level) — returned
          as-is, caller keeps ownership.
        * ``self._executor`` (session-scoped, built in :meth:`__enter__`)
          — returned as-is.
        * a freshly-built executor torn down when this scope exits.
        """
        if override is not None:
            yield override
            return
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
        """Yield an :class:`OutputSink` for the duration of one :meth:`run`.

        Preference order:

        * Per-run ``override`` wins and is ``finalize()``-d at scope exit.
        * ``self._output_sink_override`` (constructor-level) — returned
          as-is, caller keeps ownership, never finalized by Eleanor.
        * ``self._output_sink`` (session-scoped, lazily built from
          :attr:`config`) — finalized once at :meth:`__exit__`.
        * A fresh per-run sink built from :attr:`config` and
          ``finalize()``-d at scope exit.

        .. note::
            When session-scoped (third branch), the ``verbose`` setting of
            the **first** :meth:`run` call that creates the sink is used
            for the entire session. Subsequent calls with a different
            ``verbose`` value will not affect the existing sink.
        """
        if override is not None:
            try:
                yield override
            finally:
                override.finalize()
            return

        if self._output_sink_override is not None:
            yield self._output_sink_override
            return

        if self._entered:
            if self._output_sink is None:
                self._output_sink = self.load_output_sink(verbose=verbose)
            yield self._output_sink
            return

        sink = self.load_output_sink(verbose=verbose)
        try:
            yield sink
        finally:
            sink.finalize()

    def run(
        self,
        order: Order,
        simulation_size: int,
        *args: object,
        combined: bool = False,
        proportional_sampling: bool = False,
        parallel: str | None = None,
        chunks_per_worker: int | None = None,
        executor: AbstractExecutor | None = None,
        kernel: AbstractKernel | None = None,
        navigator: NavigatorProtocol | None = None,
        output_sink: OutputSink | None = None,
        transformers: "list[AbstractTransformer] | None" = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[int]:
        """Dispatch ``order`` against ``simulation_size`` VS points.

        The order's suborder tree (if any) is flattened into a stream of
        leaves via :meth:`Order.iter_leaves`; each leaf is dispatched in
        turn against a shared executor / sink / manager. See the class
        docstring for the session-vs-per-run resource model.

        If an explicit ``output_sink`` is supplied, Eleanor calls
        ``finalize()`` on it when :meth:`run` returns — ownership of the
        sink transfers to Eleanor for the duration of the call.
        """
        verbose = kwargs.get("verbose", False)
        show_progress = kwargs.get("show_progress", False)

        default_parallel, default_chunks_per_worker = self._parallel_defaults()
        if parallel is None:
            parallel = default_parallel
        if chunks_per_worker is None:
            chunks_per_worker = default_chunks_per_worker

        # Apply transformers before walking the tree: they can rewrite
        # suborders and other order-scoped state, so the walk must see
        # the transformed order.
        # ``effective_kernel`` captures the kernel used for this run: when
        # transformers are applied it is loaded once here and reused for
        # every leaf, so kernel construction happens at most once per
        # ``run()`` call.
        effective_kernel = kernel
        if transformers is not None or len(order.transformers) != 0:
            if effective_kernel is None:
                effective_kernel = self.load_kernel(order, **kwargs)
            order = transform(order, effective_kernel, overrides=transformers)

        with ExitStack() as stack:
            run_executor = stack.enter_context(
                self._executor_scope(executor, parallel=parallel),
            )
            run_sink = stack.enter_context(
                self._sink_scope(output_sink, verbose=verbose),
            )
            run_manager: SyncManager | None = None
            if show_progress:
                run_manager = stack.enter_context(self._manager_scope())

            leaves = list(
                order.iter_leaves(
                    combined=combined,
                    proportional_sampling=proportional_sampling,
                )
            )
            if not leaves:
                raise EleanorException("order produced no dispatchable leaves")

            # Resolve umbrella order ids up front so ``begin_run`` runs
            # once per distinct umbrella regardless of how many leaves
            # share it.
            #
            # Using ``id()`` as the key is safe: ``iter_leaves`` stores
            # the exact same ``Order`` object on every leaf in a combined
            # subtree (the pre-split ancestor node), so Python object
            # identity is the correct equality check here.
            umbrella_ids: dict[int, int] = {}
            for leaf in leaves:
                if leaf.umbrella is None:
                    continue
                key = id(leaf.umbrella)
                if key not in umbrella_ids:
                    umbrella_ids[key] = run_sink.begin_run(leaf.umbrella)

            order_ids: set[int] = set()
            for leaf in leaves:
                samples = round(simulation_size * leaf.sample_fraction)
                if leaf.umbrella is not None:
                    leaf.order.id = umbrella_ids[id(leaf.umbrella)]

                dispatched = self._dispatch(
                    leaf.order,
                    samples,
                    *args,
                    chunks_per_worker=chunks_per_worker,
                    executor=run_executor,
                    kernel=effective_kernel,
                    navigator=navigator,
                    sink=run_sink,
                    manager=run_manager,
                    **kwargs,
                )
                order_ids.update(dispatched)

            return sorted(order_ids)

    def _dispatch(
        self,
        order: Order,
        simulation_size: int,
        *args: object,
        chunks_per_worker: int,
        executor: AbstractExecutor,
        kernel: AbstractKernel | None,
        navigator: NavigatorProtocol | None,
        sink: OutputSink,
        manager: SyncManager | None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[int]:
        """Dispatch a single leaf order against the given executor/sink.

        The caller is responsible for resolving the executor, sink and
        (if progress is requested) manager scopes; this method neither
        builds nor tears them down. It does, however, construct a fresh
        :class:`~eleanor.progress.Progress` for each leaf when progress is
        enabled, so every leaf gets its own ``tqdm`` bar(s) even when the
        underlying :class:`SyncManager` is session-scoped.

        ``show_progress`` and ``success_sampling`` are read from
        :paramref:`kwargs` (the :class:`EleanorKwargs` bag) so that they
        still flow through to :meth:`process` and the sailor chain.

        The output progress bar is only rendered when the active
        :class:`OutputSink` opts in via
        :meth:`~OutputSink.supports_progress`; otherwise only the simulation
        bar is shown.
        """
        show_progress = kwargs.get("show_progress", False)
        success_sampling = kwargs.get("success_sampling", False)

        if executor.num_workers <= 0:
            raise EleanorException("executor num_workers must be >= 1")
        if chunks_per_worker <= 0:
            raise EleanorException("chunks_per_worker must be >= 1")

        if kernel is None:
            kernel = self.load_kernel(order, **kwargs)

        if navigator is None:
            if order.navigator is None:
                raise EleanorException("order navigator is required")
            from .navigator.registry import get_factory as get_navigator_factory

            navigator_factory = get_navigator_factory(order.navigator.type)
            version = resolve_api_version(navigator_factory)
            try:
                built = navigator_factory(order, kernel, **order.navigator.args)
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

        if success_sampling and not navigator.supports_success_sampling():
            msg = f"{navigator.__class__.__module__}.{navigator.__class__.__name__} does not support success sampling"
            raise EleanorException(msg)

        progress: Progress | None = None
        sim_handle: ProgressHandle | None = None
        out_handle: ProgressHandle | None = None
        if show_progress:
            if manager is None:
                raise EleanorException("show_progress requires an active SyncManager")
            # Under ``success_sampling`` the output bar tracks progress toward
            # a fixed target (N successes) and should therefore ignore
            # ``extend`` messages after its initial total is set.
            progress = Progress(manager, out_no_total_update=success_sampling)
            sim_handle = progress.sim
            if sink.supports_progress():
                out_handle = progress.out
                if success_sampling:
                    # Seed the output bar's target immediately so it renders
                    # with the right denominator before any sink tick arrives.
                    out_handle.total(simulation_size)

        order.id = sink.begin_run(order)

        stats = RunStats()

        try:
            if success_sampling:
                # Each call targets exactly ``simulation_size`` new
                # successes; pre-existing successes already in the
                # sink's backing store are not counted.
                while stats.succeeded < simulation_size:
                    outcomes = self.process(
                        kernel,
                        navigator,
                        simulation_size - stats.succeeded,
                        order.id,
                        *args,
                        executor=executor,
                        chunks_per_worker=chunks_per_worker,
                        sink=sink,
                        sim_progress=sim_handle,
                        out_progress=out_handle,
                        **kwargs,
                    )
                    stats.update(outcomes)
            else:
                outcomes = self.process(
                    kernel,
                    navigator,
                    simulation_size,
                    order.id,
                    *args,
                    executor=executor,
                    chunks_per_worker=chunks_per_worker,
                    sink=sink,
                    sim_progress=sim_handle,
                    out_progress=out_handle,
                    **kwargs,
                )
                stats.update(outcomes)
        finally:
            if progress is not None:
                progress.join()

        return [order.id]

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
        sim_progress: ProgressHandle | None = None,
        out_progress: ProgressHandle | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[WriteOutcome]:
        """Drive the navigator/executor/sink loop for a single leaf order.

        :param sim_progress: Handle for the simulation bar. Extended by the
            navigator batch size at the start of each iteration. Forwarded to
            :meth:`Sailor.dispatch` so workers can emit per-point ticks;
            when the executor does not support worker-side progress, ticks
            are emitted in the parent after each future resolves.
        :param out_progress: Handle for the output bar. Extended by the
            navigator batch size at the start of each iteration (a no-op
            when the underlying bar has ``out_no_total_update=True``).
            Passed to :meth:`OutputSink.write_batch`; the sink decides its
            own tick cadence. For worker-write sinks on executors without
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

        while True:
            vs_points = navigator.navigate(simulation_size, order_id=order_id, max_attempts=1)
            if sim_progress is not None:
                sim_progress.extend(len(vs_points))
            if out_progress is not None:
                out_progress.extend(len(vs_points))

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
                            sim_progress=worker_sim_progress,
                            out_progress=worker_out_progress,
                            **sailor_kwargs,
                        ),
                    )
                    outcome_futures.append(outcome_future)

                batch_outcomes: list[WriteOutcome] = []
                while outcome_futures:
                    outcome_future = outcome_futures.pop()
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

                compute_results: list[ComputeResult] = []
                while compute_futures:
                    compute_future = compute_futures.pop()
                    result = compute_future.result()
                    compute_results.extend(result)
                    if worker_sim_progress is None and sim_progress is not None and result:
                        sim_progress.tick(len(result))

                # The sink owns the output bar's cadence: per-row, per-batch,
                # or anything in between. Eleanor only hands over the handle.
                batch_outcomes = sink.write_batch(
                    order_id,
                    compute_results,
                    progress=out_progress,
                )

            outcomes.extend(batch_outcomes)

            for outcome in batch_outcomes:
                if outcome.point_id is not None:
                    vs_point_ids.append(outcome.point_id)

            if navigator.is_complete(vs_point_ids):
                break

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
        if order.kernel is None:
            raise EleanorException("order kernel is required")
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
