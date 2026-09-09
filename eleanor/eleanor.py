import sys
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping, MutableMapping, Sequence
from contextlib import ExitStack, contextmanager, suppress
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
from eleanor.output.interface import (
    AbstractOutputSink,
    ChunkResult,
    RunStats,
    SinkBinding,
    SinkChunkResult,
    WriteOutcome,
)
from eleanor.output.writer import BackgroundWriter
from eleanor.progress import SIM_CHANNEL, ManagedProgressHandle, Progress, ProgressHandle
from eleanor.runner import Runner
from eleanor.signals import shutdown_on_signal
from eleanor.timing import DispatchTimings
from eleanor.typing import EleanorKwargs

DEFAULT_SINK_NAME = "output"


def _sweep(
    sinks: Iterable[AbstractOutputSink[object]],
    teardown: Callable[[AbstractOutputSink[object]], None],
) -> None:
    """Apply ``teardown`` to every sink; re-raise the first failure afterwards."""
    first_error: BaseException | None = None
    for sink in sinks:
        try:
            teardown(sink)
        except BaseException as error:
            if first_error is None:
                first_error = error
    if first_error is not None:
        raise first_error


def _finalize_runs(sinks: Iterable[AbstractOutputSink[object]]) -> None:
    """End the current run on every sink."""
    _sweep(sinks, lambda sink: sink.finalize_run())


def _finalize_all(sinks: Iterable[AbstractOutputSink[object]]) -> None:
    """End every sink's lifetime."""
    _sweep(sinks, lambda sink: sink.finalize())


def _require_resume_tokens(
    resume_id: str | Mapping[str, str] | None,
    sinks: Mapping[str, AbstractOutputSink[object]],
) -> dict[str, str]:
    """Resolve ``resume_id``; every resumable sink needs a token, and only those."""
    tokens = _resume_tokens(resume_id, list(sinks))
    if not tokens:
        return tokens

    unresumable = sorted(name for name in tokens if not sinks[name].supports_resume())
    if unresumable:
        msg = (
            f"output sink(s) cannot resume: {', '.join(unresumable)}. "
            "Drop their --order-id token(s); they retain no run for one to name."
        )
        raise EleanorError(msg)

    missing = sorted(name for name, sink in sinks.items() if name not in tokens and sink.supports_resume())
    if missing:
        msg = (
            f"resuming requires an id for every resumable output sink; missing: {', '.join(missing)}. "
            "Pass one per sink, or drop --order-id to start a fresh run everywhere."
        )
        raise EleanorError(msg)
    return tokens


def _reject_target_clashes(sinks: Mapping[str, AbstractOutputSink[object]]) -> None:
    """Refuse a run in which two sinks write to the same store."""
    keyed = [(name, key) for name, sink in sinks.items() if (key := sink.target_key()) is not None]
    for index, (name, key) in enumerate(keyed):
        for other_name, other_key in keyed[index + 1 :]:
            if key == other_key:
                msg = (
                    f"output sinks {name!r} and {other_name!r} both write to {key}; "
                    "give each sink its own target, or configure only one of them."
                )
                raise EleanorError(msg)


def _as_sink_map[IdT](
    output_sink: AbstractOutputSink[IdT] | Mapping[str, AbstractOutputSink[IdT]] | None,
) -> dict[str, AbstractOutputSink[object]] | None:
    """Normalise a caller-supplied sink argument to a name -> sink mapping."""
    if output_sink is None:
        return None
    if isinstance(output_sink, Mapping):
        if not output_sink:
            msg = "output_sink mapping is empty; pass None to fall back to the configuration"
            raise EleanorError(msg)
        if SIM_CHANNEL in output_sink:
            msg = f"output sink name {SIM_CHANNEL!r} is reserved for the simulation progress bar"
            raise EleanorError(msg)
        return {name: cast("AbstractOutputSink[object]", sink) for name, sink in output_sink.items()}
    return {DEFAULT_SINK_NAME: cast("AbstractOutputSink[object]", output_sink)}


def _resume_tokens(
    resume_id: str | Mapping[str, str] | None,
    names: Sequence[str],
) -> dict[str, str]:
    """Resolve ``resume_id`` against the active sink names."""
    if resume_id is None:
        return {}

    if isinstance(resume_id, str):
        if len(names) != 1:
            joined = ", ".join(names)
            msg = (
                f"a bare resume id is ambiguous with {len(names)} output sinks ({joined}); "
                "map each sink to its own id instead"
            )
            raise EleanorError(msg)
        return {names[0]: resume_id}

    unknown = sorted(set(resume_id) - set(names))
    if unknown:
        joined = ", ".join(names)
        msg = f"no output sink named {', '.join(repr(name) for name in unknown)}; active sinks: {joined}"
        raise EleanorError(msg)
    return dict(resume_id)


class Eleanor:
    """An engine for dispatching :class:`Order` runs.

    An :class:`Eleanor` instance owns its long-lived resources (executor
    worker pool, progress :class:`~multiprocessing.managers.SyncManager`,
    output sinks) for the duration of a ``with`` block, and reuses them
    across any number of :meth:`run` calls made inside that block::

        with Eleanor(config=cfg) as eleanor:
            eleanor.run(order1, 1000)
            eleanor.run(order2, 2000)

    Outside of a ``with`` block, each :meth:`run` call builds the
    resources it needs and tears them down on exit, so one-shot usage
    remains a single method call::

        Eleanor(config=cfg).run(order, 1000)

    A run may drive **several sinks at once**. The kernel runs once per
    point regardless; the compute graph is fanned out to every sink inside
    the worker, which is what makes N sinks far cheaper than N runs. Each
    sink keeps its own id space, its own progress bar and its own resume
    token, and :meth:`run` returns every id it allocated, keyed by sink name.

    Constructor-level ``executor`` and ``output_sink`` keyword arguments
    override the Config-derived defaults for every :meth:`run` call on
    this instance.  Caller retains ownership — Eleanor never shuts down
    or finalizes them.

    Per-run ``output_sink=`` on :meth:`run` overrides the constructor-level
    sinks for that call, but the caller still owns their lifetime
    (``initialize`` / ``finalize``).  The recommended pattern is::

        with MySink(...) as sink:
            eleanor.run(order, n, output_sink=sink)

    ``output_sink=`` accepts a single sink (named ``"output"``) or a mapping
    of name to sink.
    """

    config: Config
    num_workers: int | None

    # Caller-supplied session-level overrides. Caller retains ownership:
    # Eleanor never enters/shuts down the executor override and never
    # finalizes the output-sink overrides.
    _executor_override: AbstractExecutor | None
    _output_sink_override: dict[str, AbstractOutputSink[object]] | None

    # Resources owned by the engine when used as a context manager.
    # ``_entered`` controls the "session vs. per-run" resource lifetime.
    _entered: bool
    _executor: AbstractExecutor | None
    _manager: SyncManager | None
    _output_sinks: dict[str, AbstractOutputSink[object]] | None

    def __init__[IdT](
        self,
        *,
        config: Config | None = None,
        num_workers: int | None = None,
        executor: AbstractExecutor | None = None,
        output_sink: AbstractOutputSink[IdT] | Mapping[str, AbstractOutputSink[IdT]] | None = None,
    ) -> None:
        self.config = config if config is not None else Config()
        self.num_workers = num_workers

        self._executor_override = executor
        self._output_sink_override = _as_sink_map(output_sink)
        if not self.config.output and self._output_sink_override is None:
            msg = "no output sink provided via config or keyword option"
            raise EleanorError(msg)

        self._entered = False
        self._executor = None
        self._manager = None
        self._output_sinks = None

    def __enter__(self) -> Self:
        """Activate session-scoped resources.

        When no constructor-level ``executor`` was supplied, one is built from
        :attr:`config` and entered eagerly so workers are warm for the first
        :meth:`run` call. When a constructor-level executor override is
        supplied, Eleanor reuses it as-is and never enters or shuts it down;
        caller-owned lifecycle may be context-managed or manual.

        The progress :class:`SyncManager` and the output sinks are left
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
        """Tear down session-scoped resources."""
        first_error: BaseException | None = None

        if self._output_sinks is not None:
            for sink in self._output_sinks.values():
                try:
                    sink.finalize()
                except BaseException as error:
                    if first_error is None:
                        first_error = error
            self._output_sinks = None

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

    def _build_config_sinks(self, *, verbose: bool) -> dict[str, AbstractOutputSink[object]]:
        """Construct and initialize every sink named in :attr:`config`.

        Built through an :class:`ExitStack` so that a sink failing to
        initialize does not strand the ones already built -- the stack unwinds
        them through ``finalize`` before the error propagates. On success the
        stack is defused and the caller owns the sinks' lifetime.
        """
        if not self.config.output:
            msg = "no output sink provided via config or keyword option"
            raise EleanorError(msg)

        sinks: dict[str, AbstractOutputSink[object]] = {}
        with ExitStack() as stack:
            for entry in self.config.output:
                settings = replace(entry.settings, verbose=verbose)
                sink = load_output_sink(entry.kind, settings)
                sink.initialize()
                _ = stack.callback(sink.finalize)
                sinks[entry.name] = sink
            _ = stack.pop_all()
        return sinks

    @contextmanager
    def _sinks_scope(
        self,
        override: Mapping[str, AbstractOutputSink[object]] | None,
        *,
        verbose: bool,
    ) -> Generator[dict[str, AbstractOutputSink[object]]]:
        """Yield the active sinks for the duration of one :meth:`run` call.

        Preference order:

        * **Caller-supplied** — ``override`` (per-run) or
          ``self._output_sink_override`` (constructor-level).  Returned
          as-is; the caller owns :meth:`~AbstractOutputSink.initialize` /
          :meth:`~AbstractOutputSink.finalize`.  Eleanor only calls
          :meth:`~AbstractOutputSink.finalize_run` on scope exit.
        * ``self._output_sinks`` (session-scoped, lazily built from
          :attr:`config`) — :meth:`~AbstractOutputSink.initialize`-d at construction
          time, :meth:`~AbstractOutputSink.finalize_run`-d on every run scope exit,
          and :meth:`~AbstractOutputSink.finalize`-d once at :meth:`__exit__`.
        * Fresh per-run sinks built from :attr:`config` — full lifecycle
          (:meth:`~AbstractOutputSink.initialize`, :meth:`~AbstractOutputSink.finalize_run`,
          :meth:`~AbstractOutputSink.finalize`) collapsed into the single
          :meth:`run` call.

        ``finalize_run`` is called on every sink even if an earlier one
        raises, for the same reason :meth:`__exit__` finalizes them all.

        .. note::
            When session-scoped (second branch), the ``verbose`` setting of
            the **first** :meth:`run` call that creates the sinks is used
            for the entire session. Subsequent calls with a different
            ``verbose`` value will not affect the existing sinks.
        """
        caller_sinks = override if override is not None else self._output_sink_override
        if caller_sinks is not None:
            owned = dict(caller_sinks)
            try:
                yield owned
            finally:
                _finalize_runs(owned.values())
            return

        if self._entered:
            if self._output_sinks is None:
                self._output_sinks = self._build_config_sinks(verbose=verbose)
            try:
                yield self._output_sinks
            finally:
                _finalize_runs(self._output_sinks.values())
            return

        sinks = self._build_config_sinks(verbose=verbose)
        try:
            yield sinks
        finally:
            try:
                _finalize_runs(sinks.values())
            finally:
                _finalize_all(sinks.values())

    def run[IdT](
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
        output_sink: AbstractOutputSink[IdT] | Mapping[str, AbstractOutputSink[IdT]] | None = None,
        resume_id: str | Mapping[str, str] | None = None,
        timings: DispatchTimings | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> dict[str, object]:
        """Dispatch ``order`` against ``simulation_size`` VS points.
        See the class docstring for the session-vs-per-run resource model.

        If an explicit ``output_sink`` is supplied — a single sink, or a
        mapping of name to sink — Eleanor treats it as caller-owned: the
        caller is responsible for :meth:`~AbstractOutputSink.initialize` /
        :meth:`~AbstractOutputSink.finalize`.  Eleanor only calls
        :meth:`~AbstractOutputSink.finalize_run` on scope exit.

        ``resume_id`` extends an existing run instead of starting a new one.
        Tokens are passed through to :meth:`~AbstractOutputSink.begin_run`
        untouched, as strings: the sink owns the id space, so only it can say
        what a valid id looks like. A token the named sink does not recognise
        is an error rather than a silent new run.

        With one sink, ``resume_id`` may be that bare token. With several it
        must be a mapping of sink name to token, and **every** sink that
        reports :meth:`~AbstractOutputSink.supports_resume` needs an entry:
        resuming some sinks while silently starting others fresh would split
        one run's output across two ids with nothing recording that they
        differ. Sinks that decline ``supports_resume`` are skipped.

        The return value maps each sink's name to whatever id it allocated,
        typed ``object`` because Eleanor never inspects one.

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
            run_sinks = stack.enter_context(
                self._sinks_scope(_as_sink_map(output_sink), verbose=verbose),
            )
            _reject_target_clashes(run_sinks)
            run_manager: SyncManager | None = None
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

            tokens = _require_resume_tokens(resume_id, run_sinks)

            progress: Progress | None = None
            sim_handle: ManagedProgressHandle | None = None
            out_handles: dict[str, ManagedProgressHandle] = {}

            try:
                if show_progress:
                    run_manager = stack.enter_context(self._manager_scope())
                    bar_names = [name for name, sink in run_sinks.items() if sink.supports_progress()]
                    progress = Progress(run_manager, bar_names)
                    sim_handle = progress.sim
                    out_handles = progress.outs()
                    sim_handle.total(expected_total)
                    for handle in out_handles.values():
                        handle.total(expected_total)

                bindings = [
                    SinkBinding.bind(name, sink, sink.begin_run(order, requested_id=tokens.get(name)))
                    for name, sink in run_sinks.items()
                ]
                order_ids = {binding.name: binding.order_id for binding in bindings}

                stats = {name: RunStats() for name in run_sinks}

                with timings.measure():
                    outcomes = self.process(
                        order,
                        kernel,
                        navigator,
                        simulation_size,
                        bindings,
                        *args,
                        batch_size=effective_batch_size,
                        max_nav_attempts=max_nav_attempts,
                        expected_total=expected_total,
                        executor=run_executor,
                        chunks_per_worker=chunks_per_worker,
                        sim_progress=sim_handle,
                        out_progress=out_handles,
                        timings=timings,
                        **kwargs,
                    )
                for name, sink_outcomes in outcomes.items():
                    stats[name].update(sink_outcomes)
            finally:
                if progress is not None:
                    progress.sim.done()
                    for handle in out_handles.values():
                        handle.done()
                    progress.join()
                if timing:
                    print(timings.summary(), file=sys.stderr)

            return order_ids

    @staticmethod
    def _dispatch_window(
        chunk_stream: Iterator[tuple[vs.Point, ...]],
        *,
        submit_chunk: Callable[[list[vs.Point]], AbstractFuture[ChunkResult]],
        consume: Callable[[AbstractFuture[ChunkResult], int], None],
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

        :param chunk_stream: Lazy stream of point chunks. Pulled from only as
            window space becomes available, which is what supplies
            backpressure to the navigator.
        :param submit_chunk: Hands one chunk to the executor and returns its
            future. Owns its own ``timings.submitting()`` accounting.
        :param consume: Called with a completed future and the number of
            chunks still outstanding. Owns any write-side accounting.
        :return: The number of points submitted.
        """
        in_flight: list[AbstractFuture[ChunkResult]] = []
        submitted = 0
        exhausted = False

        while True:
            while not exhausted and len(in_flight) < max_in_flight:
                with timings.generating():
                    chunk = next(chunk_stream, None)
                if chunk is None:
                    exhausted = True
                    break

                points = list(chunk)
                submitted += len(points)
                in_flight.append(submit_chunk(points))
                timings.count_chunk(len(points))

            if not in_flight:
                return submitted

            with timings.waiting(in_flight=len(in_flight), num_workers=executor.num_workers):
                future = executor.pop_completed_future(in_flight)
            consume(future, len(in_flight))

    def process(
        self,
        order: Order,
        kernel: AbstractKernel,
        navigator: AbstractNavigator,
        simulation_size: int,
        bindings: Sequence[SinkBinding],
        *args: object,
        batch_size: int,
        max_nav_attempts: int = 1,
        expected_total: int,
        executor: AbstractExecutor | None = None,
        chunks_per_worker: int = 1,
        sim_progress: ProgressHandle | None = None,
        out_progress: Mapping[str, ProgressHandle] | None = None,
        timings: DispatchTimings | None = None,
        **kwargs: Unpack[EleanorKwargs],
    ) -> dict[str, list[WriteOutcome]]:
        """Drive the navigator/executor/sink loop for a single leaf order.

        Every bound sink sees every point: the kernel runs once per point and
        the resulting compute graph is fanned out inside the worker, which is
        what makes N sinks cheaper than N runs.

        :param bindings: The active sinks, each already paired with the order
            id it issued. Their order is the order sinks prepare in.
        :param sim_progress: Handle for the simulation bar. Forwarded to
            :meth:`Runner.dispatch` so workers can emit per-point ticks;
            when the executor does not support worker-side progress, ticks
            are emitted in the parent after each future resolves.
        :param out_progress: Per-sink handles for the output bars, keyed by
            sink name. Passed to :meth:`AbstractOutputSink.commit_batch`; each
            sink decides its own tick cadence. For worker-commit sinks on
            executors without worker-progress support, a single chunk-level
            tick per future is emitted in the parent as a fallback.
        :param timings: Accumulator for the dispatch loop's wall-clock
            attribution. When omitted one is built from the ``timing``
            keyword so direct callers of :meth:`process` still get a
            working (if unreported) accumulator.
        :return: Each sink's :class:`WriteOutcome` list, keyed by sink name.
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
        if not bindings:
            msg = "no output sink provided via config or keyword option"
            raise EleanorError(msg)

        by_name = {binding.name: binding for binding in bindings}
        outcomes: dict[str, list[WriteOutcome]] = {binding.name: [] for binding in bindings}

        worker_sim_progress = sim_progress if executor.supports_worker_progress else None
        worker_out_progress = out_progress if executor.supports_worker_progress else None
        runner_kwargs: EleanorKwargs = {**kwargs}

        max_in_flight = executor.num_workers * chunks_per_worker
        chunk_size = max(1, -(-batch_size // max_in_flight))

        writers: dict[str, BackgroundWriter[object]] = {
            binding.name: BackgroundWriter(
                binding.sink,
                binding.order_id,
                depth=executor.num_workers,
                progress=None if out_progress is None else out_progress.get(binding.name),
                name=binding.name,
            )
            for binding in bindings
            if not binding.commit_in_worker and binding.sink.supports_background_commit()
        }

        def submit_chunk(points: list[vs.Point]) -> AbstractFuture[ChunkResult]:
            """Dispatch one chunk to a worker for compute, prepare and fan-out.

            ``Runner.dispatch`` reduces the compute graph through every bound
            sink and commits the ones that opted into worker commits, so what
            comes back is per-sink: small outcome lists for those, prepared
            payloads for the sinks the parent commits.
            """
            with timings.submitting():
                return executor.submit(
                    Runner(kernel).dispatch,
                    points,
                    *args,
                    bindings=bindings,
                    sim_progress=worker_sim_progress,
                    out_progress=worker_out_progress,
                    **runner_kwargs,
                )

        def collect_worker_committed(sink_result: SinkChunkResult) -> None:
            """Bank outcomes for a sink that already committed in the worker.

            Costs the dispatch loop nothing beyond a list extend, so this
            deliberately runs outside the write timer.
            """
            committed = sink_result.outcomes
            if committed is None:
                return

            outcomes[sink_result.name].extend(committed)
            if worker_out_progress is None and out_progress is not None:
                handle = out_progress.get(sink_result.name)
                written = sum(1 for o in committed if o.committed and o.exit_code == 0)
                if handle is not None and written:
                    handle.tick(written)

        def commit_in_parent(sink_result: SinkChunkResult) -> None:
            """Commit one sink's prepared payload here, or hand it to its writer."""
            name = sink_result.name
            prepared = sink_result.prepared
            if not prepared:
                return

            writer = writers.get(name)
            if writer is not None:
                writer.submit(prepared)
                return

            binding = by_name[name]
            outcomes[name].extend(
                binding.sink.commit_batch(
                    binding.order_id,
                    prepared,
                    progress=None if out_progress is None else out_progress.get(name),
                ),
            )

        def consume(future: AbstractFuture[ChunkResult], in_flight: int) -> None:
            result = future.result()

            if worker_sim_progress is None and sim_progress is not None and result.point_count:
                sim_progress.tick(result.point_count)

            pending: list[SinkChunkResult] = []
            for sink_result in result.sinks:
                if sink_result.outcomes is None:
                    pending.append(sink_result)
                else:
                    collect_worker_committed(sink_result)

            if pending:
                with timings.writing(in_flight=in_flight, num_workers=executor.num_workers):
                    for sink_result in pending:
                        commit_in_parent(sink_result)

        total_produced = 0
        with shutdown_on_signal() as shutdown:
            for writer in writers.values():
                writer.start()
            try:
                chunk_stream = batched(
                    chain.from_iterable(
                        navigator.navigate(
                            order,
                            kernel,
                            simulation_size,
                            batch_size,
                            max_attempts=max_nav_attempts,
                        ),
                    ),
                    chunk_size,
                    strict=False,
                )

                total_produced = self._dispatch_window(
                    chunk_stream,
                    submit_chunk=submit_chunk,
                    consume=consume,
                    executor=executor,
                    max_in_flight=max_in_flight,
                    timings=timings,
                )
            except KeyboardInterrupt:
                _abort_writers(writers)
                executor.shutdown(wait=False)
                raise EleanorShutdown(shutdown.signal_name) from None
            except BaseException:
                _abort_writers(writers)
                raise
            else:
                if writers:
                    with timings.writing(in_flight=0, num_workers=executor.num_workers):
                        _join_writers(writers, outcomes)

        if total_produced != expected_total:
            msg = f"navigator produced {total_produced} points, expected {expected_total}"
            raise EleanorError(msg)

        return outcomes


def _abort_writers(writers: Mapping[str, BackgroundWriter[object]]) -> None:
    """Abort every writer, never raising."""
    for writer in writers.values():
        with suppress(BaseException):
            writer.abort()


def _join_writers(
    writers: Mapping[str, BackgroundWriter[object]],
    outcomes: MutableMapping[str, list[WriteOutcome]],
) -> None:
    """Join every writer, collecting outcomes; re-raise the first failure."""
    first_error: BaseException | None = None
    for name, writer in writers.items():
        try:
            outcomes[name].extend(writer.join())
        except BaseException as error:
            if first_error is None:
                first_error = error

    if first_error is not None:
        raise first_error
