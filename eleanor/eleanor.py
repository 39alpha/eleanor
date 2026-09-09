import sys
from collections.abc import Callable, Generator, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from itertools import batched, chain
from multiprocessing import Manager
from multiprocessing.managers import SyncManager
from types import TracebackType
from typing import Self, Unpack, cast

import eleanor.variable_space as vs
from eleanor.config import Config
from eleanor.exceptions import EleanorError, EleanorShutdown
from eleanor.executor import AbstractExecutor, AbstractFuture, load_executor
from eleanor.executor.settings import ExecutorSettings
from eleanor.kernel import load_kernel
from eleanor.kernel.interface import AbstractKernel
from eleanor.navigator import AbstractNavigator, load_navigator
from eleanor.order import Order
from eleanor.output import load_output_sink
from eleanor.output.interface import AbstractOutputSink, RunStats, WriteOutcome
from eleanor.progress import ManagedProgressHandle, Progress, ProgressHandle
from eleanor.runner import Runner
from eleanor.signals import shutdown_on_signal
from eleanor.timing import DispatchTimings
from eleanor.typing import EleanorKwargs


class Eleanor:
    """An engine for dispatching :class:`Order` runs.

    An :class:`Eleanor` instance owns its long-lived resources (executor
    worker pool, progress :class:`~multiprocessing.managers.SyncManager`,
    output sink) for the duration of a ``with`` block, and reuses them
    across any number of :meth:`run` calls made inside that block::

        with Eleanor(config=cfg) as eleanor:
            eleanor.run(order1, 1000)
            eleanor.run(order2, 2000)

    Outside of a ``with`` block, each :meth:`run` call builds the
    resources it needs and tears them down on exit, so one-shot usage
    remains a single method call::

        Eleanor(config=cfg).run(order, 1000)

    Constructor-level ``executor`` and ``output_sink`` keyword arguments
    override the Config-derived defaults for every :meth:`run` call on
    this instance.  Caller retains ownership — Eleanor never shuts down
    or finalizes them.

    Per-run ``output_sink=`` on :meth:`run` overrides the constructor-level
    sink for that call, but the caller still owns its lifetime
    (``initialize`` / ``finalize``).  The recommended pattern is::

        with MySink(...) as sink:
            eleanor.run(order, n, output_sink=sink)
    """

    config: Config
    num_workers: int | None

    # Caller-supplied session-level overrides. Caller retains ownership:
    # Eleanor never enters/shuts down the executor override and never
    # finalizes the output-sink override.
    _executor_override: AbstractExecutor | None
    _output_sink_override: AbstractOutputSink | None

    # Resources owned by the engine when used as a context manager.
    # ``_entered`` controls the "session vs. per-run" resource lifetime.
    _entered: bool
    _executor: AbstractExecutor | None
    _manager: SyncManager | None
    _output_sink: AbstractOutputSink | None

    def __init__(
        self,
        *,
        config: Config | None = None,
        num_workers: int | None = None,
        executor: AbstractExecutor | None = None,
        output_sink: AbstractOutputSink | None = None,
    ) -> None:
        self.config = config if config is not None else Config()
        self.num_workers = num_workers

        self._executor_override = executor
        self._output_sink_override = output_sink
        if self.config.output is None and self._output_sink_override is None:
            msg = "no output sink provided via config or keyword option"
            raise EleanorError(msg)

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

        The progress :class:`SyncManager` and :class:`AbstractOutputSink` are left
        unbuilt until the first :meth:`run` that needs them.
        """
        if self._executor_override is None:
            settings = self.config.executor.settings
            if self.num_workers is not None:
                settings = replace(settings, num_workers=self.num_workers)

            self._executor = load_executor(self.config.executor.kind, settings)

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
                wait = _exc_type is None or not issubclass(_exc_type, KeyboardInterrupt)
                self._executor.shutdown(wait=wait)
            except BaseException as error:
                if first_error is None:
                    first_error = error
            finally:
                self._executor = None

        self._entered = False

        if first_error is not None:
            raise first_error

    @contextmanager
    def _executor_scope(
        self,
        *,
        kind: str,
        settings: ExecutorSettings | None,
    ) -> Generator[AbstractExecutor]:
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

        if settings is None:
            settings = ExecutorSettings()

        if self.num_workers is not None:
            settings = replace(settings, num_workers=self.num_workers)

        with load_executor(kind, settings) as executor:
            yield executor

    @contextmanager
    def _manager_scope(self) -> Generator[SyncManager]:
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
        override: AbstractOutputSink | None,
        *,
        verbose: bool,
    ) -> Generator[AbstractOutputSink]:
        """Yield an :class:`AbstractOutputSink` for the duration of one :meth:`run` call.

        Preference order:

        * **Caller-supplied** — ``override`` (per-run) or
          ``self._output_sink_override`` (constructor-level).  Returned
          as-is; the caller owns :meth:`~AbstractOutputSink.initialize` /
          :meth:`~AbstractOutputSink.finalize`.  Eleanor only calls
          :meth:`~AbstractOutputSink.finalize_run` on scope exit.
        * ``self._output_sink`` (session-scoped, lazily built from
          :attr:`config`) — :meth:`~AbstractOutputSink.initialize`-d at construction
          time, :meth:`~AbstractOutputSink.finalize_run`-d on every run scope exit,
          and :meth:`~AbstractOutputSink.finalize`-d once at :meth:`__exit__`.
        * A fresh per-run sink built from :attr:`config` — full lifecycle
          (:meth:`~AbstractOutputSink.initialize`, :meth:`~AbstractOutputSink.finalize_run`,
          :meth:`~AbstractOutputSink.finalize`) collapsed into the single
          :meth:`run` call.

        .. note::
            When session-scoped (third branch), the ``verbose`` setting of
            the **first** :meth:`run` call that creates the sink is used
            for the entire session. Subsequent calls with a different
            ``verbose`` value will not affect the existing sink.
        """
        caller_sink = override if override is not None else self._output_sink_override
        if caller_sink is not None:
            try:
                yield caller_sink
            finally:
                caller_sink.finalize_run()
            return

        if self._entered:
            if self._output_sink is None:
                if self.config.output is None:
                    msg = "no output sink provided via config or keyword option"
                    raise EleanorError(msg)

                settings = replace(self.config.output.settings, verbose=verbose)
                self._output_sink = load_output_sink(self.config.output.kind, settings)
                self._output_sink.initialize()
            try:
                yield self._output_sink
            finally:
                self._output_sink.finalize_run()
            return

        if self.config.output is None:
            msg = "no output sink provided via config or keyword option"
            raise EleanorError(msg)

        settings = replace(self.config.output.settings, verbose=verbose)
        sink = load_output_sink(self.config.output.kind, settings)

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
        chunks_per_worker: int | None = None,
        batch_size: int | None = None,
        max_nav_attempts: int = 1,
        kernel: AbstractKernel | None = None,
        kernel_args: list[object] | None = None,
        navigator: AbstractNavigator | None = None,
        output_sink: AbstractOutputSink | None = None,
        timings: DispatchTimings | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> int:
        """Dispatch ``order`` against ``simulation_size`` VS points.
        See the class docstring for the session-vs-per-run resource model.

        If an explicit ``output_sink`` is supplied, Eleanor treats it as
        caller-owned: the caller is responsible for
        :meth:`~AbstractOutputSink.initialize` / :meth:`~AbstractOutputSink.finalize`.
        Eleanor only calls :meth:`~AbstractOutputSink.finalize_run` on scope exit.

        Supplying ``timings`` lets a caller read the dispatch loop's
        wall-clock attribution after the run instead of only seeing it
        printed.  The two controls are independent: ``timings`` decides
        what collects the measurements, while the ``timing`` keyword
        decides whether Eleanor prints a summary.
        """
        # Check for arguments that have been retired. The double cast lets
        # basedpyright accept a membership test for a key outside EleanorKwargs.
        for retired_arg in ["executor", "parallel"]:
            if retired_arg in cast(dict[str, object], cast(object, kwargs)):
                msg = f"Eleanor.run() got an unexpected keyword argument '{retired_arg}'"
                raise TypeError(msg)

        verbose = kwargs.get("verbose", False)
        show_progress = kwargs.get("show_progress", False)
        timing = kwargs.get("timing", False)
        if timings is None:
            timings = DispatchTimings(enabled=timing)

        if chunks_per_worker is None:
            chunks_per_worker = self.config.executor.settings.chunks_per_worker

        executor_settings = replace(self.config.executor.settings, chunks_per_worker=chunks_per_worker)

        with ExitStack() as stack:
            run_executor = stack.enter_context(
                self._executor_scope(kind=self.config.executor.kind, settings=executor_settings),
            )
            run_sink = stack.enter_context(
                self._sink_scope(output_sink, verbose=verbose),
            )
            run_manager: SyncManager | None = None
            if show_progress:
                run_manager = stack.enter_context(self._manager_scope())
            if run_executor.num_workers <= 0:
                msg = "executor num_workers must be >= 1"
                raise EleanorError(msg)
            if chunks_per_worker <= 0:
                msg = "chunks_per_worker must be >= 1"
                raise EleanorError(msg)
            if max_nav_attempts <= 0:
                msg = "max_nav_attempts must be >= 1"
                raise EleanorError(msg)

            if kernel is None:
                kernel = load_kernel(order.kernel.kind, order.kernel.settings)

            kernel_kwargs = kernel.prepare_setup_args(*(kernel_args or []))
            kernel.setup(order, **kernel_kwargs)
            kernel.validate_order(order)

            if navigator is None:
                navigator = load_navigator(order.navigator.kind, settings=order.navigator.settings)
            expected_total = navigator.num_systems(order, simulation_size)
            if expected_total <= 0:
                msg = f"navigator.num_systems({simulation_size}) returned {expected_total}; must be >= 1"
                raise EleanorError(msg)
            effective_batch_size = batch_size if batch_size is not None else expected_total
            if batch_size is not None and batch_size <= 0:
                msg = "batch_size must be >= 1"
                raise EleanorError(msg)

            progress: Progress | None = None
            # Local handles use ``ManagedProgressHandle`` rather than the worker-
            # facing ``ProgressHandle`` so the dispatch context can call ``done()``
            # at teardown.  Anywhere these are forwarded to a producer
            # (``process()`` / ``Runner.dispatch`` / ``AbstractOutputSink.commit_batch``)
            # they implicitly narrow to ``ProgressHandle``, which omits ``done()``.
            sim_handle: ManagedProgressHandle | None = None
            out_handle: ManagedProgressHandle | None = None
            if show_progress:
                if run_manager is None:
                    msg = "show_progress requires an active SyncManager"
                    raise EleanorError(msg)
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
                with timings.measure():
                    outcomes = self.process(
                        order,
                        kernel,
                        navigator,
                        simulation_size,
                        order.id,
                        *args,
                        batch_size=effective_batch_size,
                        max_nav_attempts=max_nav_attempts,
                        expected_total=expected_total,
                        executor=run_executor,
                        chunks_per_worker=chunks_per_worker,
                        sink=run_sink,
                        sim_progress=sim_handle,
                        out_progress=out_handle,
                        timings=timings,
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
                if timing:
                    print(timings.summary(), file=sys.stderr)

            return order.id

    @staticmethod
    def _dispatch_window[T](
        chunk_stream: Iterator[tuple[vs.Point, ...]],
        *,
        submit_chunk: Callable[[list[vs.Point]], AbstractFuture[T]],
        consume: Callable[[AbstractFuture[T], int], None],
        executor: AbstractExecutor,
        max_in_flight: int,
        timings: DispatchTimings,
    ) -> int:
        """Feed ``chunk_stream`` through a bounded window of in-flight chunks.

        Keeps up to ``max_in_flight`` chunks outstanding, topping the window
        back up as each one completes rather than draining it to empty between
        navigator batches. Point generation, worker compute and consumption
        therefore overlap continuously, and parent memory stays bounded by the
        window rather than by the batch.

        Generic over the future's payload so that one loop serves both the
        worker-write and serial-sink modes. ``AbstractFuture`` is invariant
        over its type parameter, so without the type variable the in-flight
        list could not be typed without a cast on every access.

        :param chunk_stream: Lazy stream of point chunks. Pulled from only as
            window space becomes available, which is what supplies
            backpressure to the navigator.
        :param submit_chunk: Hands one chunk to the executor and returns its
            future. Owns its own ``timings.submitting()`` accounting.
        :param consume: Called with a completed future and the number of
            chunks still outstanding. Owns any write-side accounting.
        :return: The number of points submitted.
        """
        in_flight: list[AbstractFuture[T]] = []
        submitted = 0
        exhausted = False

        while True:
            while not exhausted and len(in_flight) < max_in_flight:
                # Timed here rather than around ``navigator.navigate`` itself:
                # the stream is lazy, so pulling a chunk is what actually
                # drives generation.
                with timings.generating():
                    chunk = next(chunk_stream, None)
                if chunk is None:
                    exhausted = True
                    break

                # ``batched`` yields tuples, but ``Runner.dispatch`` treats any
                # non-``list`` as a single point, so the chunk has to be
                # materialised as a list before it crosses that boundary.
                points = list(chunk)
                submitted += len(points)
                in_flight.append(submit_chunk(points))
                timings.count_chunk(len(points))

            if not in_flight:
                return submitted

            with timings.waiting(in_flight=len(in_flight), num_workers=executor.num_workers):
                future = executor.pop_completed_future(in_flight)
            # The post-pop count is what ``consume`` needs: it is how much work
            # the pool still has while the parent is busy consuming this one.
            consume(future, len(in_flight))

    def process(
        self,
        order: Order,
        kernel: AbstractKernel,
        navigator: AbstractNavigator,
        simulation_size: int,
        order_id: int,
        *args: object,
        batch_size: int,
        max_nav_attempts: int = 1,
        expected_total: int,
        executor: AbstractExecutor | None = None,
        chunks_per_worker: int = 1,
        sink: AbstractOutputSink,
        sim_progress: ProgressHandle | None = None,
        out_progress: ProgressHandle | None = None,
        timings: DispatchTimings | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[WriteOutcome]:
        """Drive the navigator/executor/sink loop for a single leaf order.
        :param sim_progress: Handle for the simulation bar. Forwarded to
            :meth:`Runner.dispatch` so workers can emit per-point ticks;
            when the executor does not support worker-side progress, ticks
            are emitted in the parent after each future resolves.
        :param out_progress: Handle for the output bar. Passed to
            :meth:`AbstractOutputSink.commit_batch`; the sink decides its own
            tick cadence. For worker-commit sinks on executors without
            worker-progress support, a single chunk-level tick per future is
            emitted in the parent as a fallback.
        :param timings: Accumulator for the dispatch loop's wall-clock
            attribution. When omitted one is built from the ``timing``
            keyword so direct callers of :meth:`process` still get a
            working (if unreported) accumulator.
        """
        if timings is None:
            timings = DispatchTimings(enabled=kwargs.get("timing", False))

        if executor is None:
            msg = "no process executor created"
            raise EleanorError(msg)
        if executor.num_workers <= 0:
            msg = "executor num_workers must be >= 1"
            raise EleanorError(msg)
        if chunks_per_worker <= 0:
            msg = "chunks_per_worker must be >= 1"
            raise EleanorError(msg)
        if max_nav_attempts <= 0:
            msg = "max_nav_attempts must be >= 1"
            raise EleanorError(msg)

        outcomes: list[WriteOutcome] = []

        worker_commit = sink.supports_worker_commit()

        # When the executor cannot forward a ``Manager``-backed queue into
        # its workers, we must not hand the handles to ``Runner.dispatch``;
        # the parent will emit coarser chunk-granularity ticks instead.
        worker_sim_progress = sim_progress if executor.supports_worker_progress else None
        worker_out_progress = out_progress if executor.supports_worker_progress else None
        runner_kwargs: EleanorKwargs = {**kwargs}

        # ``chunks_per_worker`` keeps its meaning as the in-flight window depth
        # per worker. ``chunk_size`` is derived from ``batch_size`` so existing
        # configurations produce the same chunk sizes they did when each
        # navigator batch was split into exactly ``num_workers *
        # chunks_per_worker`` pieces -- only the barrier between batches goes
        # away, not the granularity of the work.
        max_in_flight = executor.num_workers * chunks_per_worker
        chunk_size = max(1, -(-batch_size // max_in_flight))

        def submit_worker_commit(points: list[vs.Point]) -> AbstractFuture[list[WriteOutcome]]:
            """Dispatch a chunk whose sink also commits inside the worker.

            Sinks that opt in to worker commits have both halves of the write
            run in the worker, so the future resolves to a small
            ``list[WriteOutcome]`` and the prepared payload never crosses the
            process boundary at all.

            ``Runner.dispatch`` has a ``Sequence[object] | list[WriteOutcome]``
            union return type, but with ``commit=True`` it always returns
            ``list[WriteOutcome]``; ``AbstractFuture`` is invariant, so narrow
            the future here.
            """
            with timings.submitting():
                return cast(
                    AbstractFuture[list[WriteOutcome]],
                    executor.submit(
                        Runner(kernel).dispatch,
                        points,
                        *args,
                        sink=sink,
                        order_id=order_id,
                        commit=True,
                        sim_progress=worker_sim_progress,
                        out_progress=worker_out_progress,
                        **runner_kwargs,
                    ),
                )

        def consume_worker_commit(
            future: AbstractFuture[list[WriteOutcome]],
            _in_flight: int,
        ) -> None:
            result = future.result()
            outcomes.extend(result)
            # Fallback chunk-level ticks for executors that cannot forward the
            # ProgressHandle into workers. Empty futures are skipped so the bar
            # never gets a spurious tick(0).
            if worker_sim_progress is None and sim_progress is not None and result:
                sim_progress.tick(len(result))
            if worker_out_progress is None and out_progress is not None:
                committed = sum(1 for o in result if o.committed and o.exit_code == 0)
                if committed:
                    out_progress.tick(committed)

        def submit_prepare(points: list[vs.Point]) -> AbstractFuture[Sequence[object]]:
            """Dispatch a chunk whose sink is committed by the main process.

            The worker still reduces the compute graph via
            ``sink.prepare_batch``; only the durable commit waits for the
            parent. See ``submit_worker_commit`` on the narrowing cast: without
            ``commit=True``, ``Runner.dispatch`` always resolves to the
            prepared sequence.
            """
            with timings.submitting():
                return cast(
                    AbstractFuture[Sequence[object]],
                    executor.submit(
                        Runner(kernel).dispatch,
                        points,
                        *args,
                        sink=sink,
                        order_id=order_id,
                        sim_progress=worker_sim_progress,
                        **runner_kwargs,
                    ),
                )

        def consume_prepared(future: AbstractFuture[Sequence[object]], in_flight: int) -> None:
            prepared = future.result()
            if worker_sim_progress is None and sim_progress is not None and prepared:
                sim_progress.tick(len(prepared))
            # Commit each resolved chunk as it arrives instead of accumulating
            # prepared payloads in-memory. This reduces parent memory pressure
            # and cuts time-to-first-write.
            if len(prepared) == 0:
                return
            # The sink owns the output bar's cadence: per-row, per-chunk, or
            # anything in between. Eleanor only hands over the handle.
            #
            # The outstanding count is handed to the timer so a commit that
            # stalls the dispatch thread while the pool runs dry is charged as
            # starvation, not just as write time.
            with timings.writing(in_flight=in_flight, num_workers=executor.num_workers):
                outcomes.extend(
                    sink.commit_batch(
                        order_id,
                        prepared,
                        progress=out_progress,
                    ),
                )

        total_produced = 0
        # Signal handlers are intentionally installed *after* the executor pool
        # is constructed so worker processes inherit only the default SIGTERM
        # disposition.
        with shutdown_on_signal() as shutdown:
            try:
                # One flat, lazy stream of chunks. Flattening across navigator
                # batches is what removes the drain-all barrier: the window can
                # be topped up from the next batch while the previous one is
                # still in flight. ``batch_size`` survives as the navigator's
                # own generation granularity.
                chunk_stream = batched(
                    chain.from_iterable(
                        navigator.navigate(
                            order,
                            kernel,
                            simulation_size,
                            batch_size,
                            order_id=order_id,
                            max_attempts=max_nav_attempts,
                        ),
                    ),
                    chunk_size,
                    # A short final chunk is the normal case: the point count
                    # is rarely a multiple of ``chunk_size``.
                    strict=False,
                )

                if worker_commit:
                    total_produced = self._dispatch_window(
                        chunk_stream,
                        submit_chunk=submit_worker_commit,
                        consume=consume_worker_commit,
                        executor=executor,
                        max_in_flight=max_in_flight,
                        timings=timings,
                    )
                else:
                    total_produced = self._dispatch_window(
                        chunk_stream,
                        submit_chunk=submit_prepare,
                        consume=consume_prepared,
                        executor=executor,
                        max_in_flight=max_in_flight,
                        timings=timings,
                    )
            except KeyboardInterrupt:
                executor.shutdown(wait=False)
                raise EleanorShutdown(shutdown.signal_name) from None

        if total_produced != expected_total:
            msg = f"navigator produced {total_produced} points, expected {expected_total}"
            raise EleanorError(msg)

        return outcomes
