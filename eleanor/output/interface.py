from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from traceback import format_exception
from types import TracebackType
from typing import TYPE_CHECKING, Self

import eleanor.variable_space as vs
from eleanor.exceptions import EleanorError

if TYPE_CHECKING:
    from eleanor.order import Order
    from eleanor.progress import ProgressHandle


def require_int_order_id(requested_id: str, sink_name: str) -> int:
    """Parse ``requested_id`` as an integer, for sinks whose ids are integers.

    ``begin_run`` receives the resume token as the raw string the caller
    supplied, because only the sink knows its own id space. The sinks backed by
    an integer sequence share this parser so they also share one error message.
    """
    try:
        return int(requested_id)
    except ValueError as error:
        msg = f"{sink_name} order id must be an integer, got {requested_id!r}"
        raise EleanorError(msg) from error


@dataclass(slots=True, frozen=True)
class ErrorInfo:
    type_name: str
    message: str
    traceback_text: str

    @staticmethod
    def from_exception(error: Exception) -> ErrorInfo:
        traceback_text = "".join(format_exception(type(error), error, error.__traceback__))
        return ErrorInfo(type_name=error.__class__.__name__, message=str(error), traceback_text=traceback_text)


@dataclass(slots=True)
class ComputeResult:
    point: vs.Point
    error: ErrorInfo | None = None


@dataclass(slots=True, frozen=True)
class WriteOutcome:
    exit_code: int
    committed: bool
    error_message: str | None = None


@dataclass(slots=True, frozen=True)
class SinkChunkResult:
    """What one sink did with one chunk, as handed back from the worker.

    Exactly one of :attr:`outcomes` / :attr:`prepared` is set, and which one
    is decided before the chunk is submitted by
    :attr:`SinkBinding.commit_in_worker`:

    * :attr:`outcomes` -- the sink committed in the worker. Only the small
      per-point verdicts travel back.
    * :attr:`prepared` -- the sink commits in the parent, so its prepared
      payload has to make the trip.

    The sink is identified by name rather than by position so that a chunk's
    results cannot be silently mismatched against the binding list.
    """

    name: str
    outcomes: list[WriteOutcome] | None = None
    prepared: Sequence[object] | None = None


@dataclass(slots=True, frozen=True)
class ChunkResult:
    """Everything one chunk produced, across every active sink.

    :param point_count: How many VS points the chunk held. Carried explicitly
        because it is no longer recoverable from the payload: with several
        sinks active, ``len(sinks)`` counts sinks, not points, and the parent
        needs the point count to emit fallback simulation-progress ticks for
        executors that cannot forward a progress handle into workers.
    :param sinks: One :class:`SinkChunkResult` per active sink, in binding
        order.
    """

    point_count: int
    sinks: list[SinkChunkResult]


@dataclass(slots=True)
class RunStats:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0

    def update(self, outcomes: Sequence[WriteOutcome]) -> None:
        self.attempted += len(outcomes)
        n = sum(1 for o in outcomes if o.committed and o.exit_code == 0)
        self.succeeded += n
        self.failed += len(outcomes) - n


class AbstractOutputSink[IdT](ABC):
    """A destination for computed :class:`ComputeResult` payloads.

    Persisting a batch is split into two halves so that the expensive,
    pure part can run in a worker process while the durable part runs
    wherever the storage model requires:

    :meth:`prepare_batch`
        Always runs in the worker, with the full :class:`ComputeResult`
        graph available. Reduces that graph to the sink's own compact
        representation.
    :meth:`commit_batch`
        Runs in the worker or in the parent, per :meth:`supports_worker_commit`.
        Durably persists what :meth:`prepare_batch` produced.

    A prepared payload's type is private to the sink. Eleanor never inspects
    one, it only carries it from the worker to whichever process commits it,
    so the plumbing types it as ``object``. The only requirements are that it
    pickles and that it is cheaper to unpickle than the graph it came from --
    the whole point of the split is to keep the ~100k-object compute graph
    from crossing the process boundary. Columnar payloads (one array per
    column) do far better here than row-oriented ones, which preserve the
    object count.

    Because ``commit_batch`` receives its parameter as ``Sequence[object]``,
    a sink narrows it back to its own payload type there -- Python has no way
    to express "some type the sink chose and I will hand back faithfully"
    without resorting to ``Any``, so the narrowing is explicit and local. The
    pairing of ``prepare_batch``'s output with ``commit_batch``'s input is
    therefore the sink's own responsibility.
    """

    def initialize(self) -> None:
        """Perform once-per-sink setup before any :meth:`begin_run` is called.

        Called exactly once per sink instance, before the first
        :meth:`begin_run`. Sinks may use it to open persistent resources
        (connections, file handles), apply schema setup, or enter
        bulk-load mode. The default implementation is a no-op.

        For **config-derived** sinks (built from Eleanor's configuration),
        Eleanor calls this method automatically. For **caller-supplied**
        sinks — whether passed at construction
        (``Eleanor(output_sink=...)``) or per-run
        (``Eleanor.run(output_sink=...)``) — the caller is responsible
        for calling :meth:`initialize` and :meth:`finalize`. The
        recommended pattern is to use the sink as a context manager::

            with MySink(...) as sink:
                eleanor.run(..., output_sink=sink)

        :meth:`initialize` and :meth:`finalize` bracket the sink's
        lifetime; :meth:`begin_run` / :meth:`prepare_batch` /
        :meth:`commit_batch` / :meth:`finalize_run` bracket each individual
        run within that lifetime.
        """
        return

    @abstractmethod
    def begin_run(self, order: Order, *, requested_id: str | None = None) -> IdT:
        """Perform any setup required for a run and return its order id.

        The sink owns the id space. Nothing upstream knows what an id looks
        like, so ``requested_id`` arrives as the raw token the caller supplied
        (``--order-id`` on the command line) and it is the sink's job to
        interpret it. The contract is the same for every sink:

        * ``requested_id`` is ``None`` -- allocate a fresh id and start a new
          run.
        * ``requested_id`` names a run this sink already holds -- return that
          id, so the new points extend the existing run.
        * ``requested_id`` is malformed for this sink's id space, or names a
          run it does not hold -- raise :class:`~eleanor.exceptions.EleanorError`.
          Resuming is an explicit request, so quietly starting a new run
          instead would discard the caller's intent.

        This method must be called before :meth:`prepare_batch`,
        :meth:`commit_batch` or :meth:`finalize_run`. Repeated calls with the same order are expected
        to return the same id and leave the sink's backing store in the same
        observable state as a single call (e.g. no duplicate order rows),
        though they may still perform work -- opening a connection, reading
        back stored metadata, or populating fields on the in-memory order.

        Implementations are only expected to verify identifying metadata
        (such as the version of Eleanor that produced the order); they are
        not expected to validate that the full order contents match what is
        stored. Callers extending an existing run are responsible for
        supplying a consistent order.
        """
        ...

    @abstractmethod
    def prepare_batch(self, order_id: IdT, results: Sequence[ComputeResult]) -> Sequence[object]:
        """Reduce ``results`` to this sink's compact representation.

        **Always runs in a worker process**, where the full compute graph is
        available, so this is where any expensive projection, conversion or
        filtering belongs. Whatever is returned is what crosses the process
        boundary, so prefer a representation that collapses the graph's object
        count rather than merely reshaping it.

        Returns exactly one prepared item per element of ``results``, in the
        same order. That correspondence is what lets :meth:`commit_batch`
        report ``outcomes[i]`` for ``results[i]``, and what keeps per-point
        error isolation possible; a sink that needs to pool work across the
        whole batch should do so in :meth:`commit_batch` instead.

        The sink instance is a per-chunk copy sent into the worker, so this
        method **must not rely on mutating sink state**: any mutation is
        discarded when the worker's copy is dropped. Parent-side state that
        this method needs must either cross the pickle boundary with the sink
        or be re-derived here.

        The converse deserves as much attention, because it is the one that
        costs. *Anything a sink accumulates in* :meth:`commit_batch` *is
        re-pickled into every chunk submitted after it*, so a sink that
        retains per-point state makes the run pay for its own output
        quadratically -- exactly the cost this split exists to avoid. That
        state is also pickled on the dispatch thread while the writer thread
        may be midway through mutating it (see
        :meth:`supports_background_commit`), so the worker's view of it is a
        snapshot taken at no particular moment. Keep it out of the worker
        entirely: give the sink a ``__getstate__`` that drops whatever
        :meth:`prepare_batch` does not read.
        :class:`~eleanor.output.memory.MemorySink` and
        :class:`~eleanor.output.csv.CsvSink` both do this.

        A failure that affects a single point should be recorded in that
        point's prepared item rather than raised, so the remaining points in
        the chunk can still commit. Raising aborts the whole chunk.

        **This method must not mutate ``results``, nor anything reachable
        from them.** When several sinks are active they are each handed the
        *same* ``results`` -- computing once and fanning out is the entire
        point -- and they prepare in the order the configuration lists them.
        A sink that writes to the compute graph is therefore visible to every
        sink after it, and to any sink whose prepared payload aliases the
        graph rather than copying out of it (:class:`PostgresPrepared` holds
        the point objects themselves).
        """
        ...

    @abstractmethod
    def commit_batch(
        self,
        order_id: IdT,
        prepared: Sequence[object],
        progress: ProgressHandle | None = None,
    ) -> list[WriteOutcome]:
        """Durably persist ``prepared`` for ``order_id``; one outcome per item.

        Runs in the worker when :meth:`supports_worker_commit` is ``True``, and
        in the parent process otherwise. Returns one :class:`WriteOutcome` per
        element of ``prepared``, in the same order, so that ``outcomes[i]``
        describes ``results[i]`` from the corresponding
        :meth:`prepare_batch` call.

        Whether to persist per point (isolating failures) or to pool the whole
        batch into one statement (faster, but a single bad row fails all of
        them) is the sink's choice; Eleanor has no opinion.

        When ``progress`` is supplied the sink is responsible for emitting
        ``tick`` messages whose values sum to the number of rows it durably
        wrote during this call. The sink chooses the cadence that best fits
        its storage model -- per row, per internal sub-batch, or a single
        call at the end. Sinks that cannot emit meaningful progress must
        return ``False`` from :meth:`supports_progress` so Eleanor never
        supplies a non-``None`` handle in the first place.
        """
        ...

    @abstractmethod
    def finalize_run(self) -> None:
        """Perform per-run cleanup after a single :meth:`Eleanor.run` returns.

        Called once for every :meth:`Eleanor.run` invocation that uses this
        sink, after all :meth:`begin_run` / :meth:`commit_batch` calls for
        that run have completed. Sinks may use it to flush per-run buffers,
        commit per-run state, or release per-run resources. Sink-lifetime
        resources (persistent connections, indexes dropped under bulk-load
        mode) belong to :meth:`initialize` / :meth:`finalize` instead.
        """
        ...

    def finalize(self) -> None:
        """Perform once-per-sink teardown after all :meth:`finalize_run` cycles.

        Called exactly once per sink instance, after the final
        :meth:`finalize_run` (or immediately, if no run was started).
        Sinks may use it to close persistent resources, recreate indexes
        and constraints dropped during bulk-load mode, or run any
        post-write maintenance. The default implementation is a no-op.

        For **caller-supplied** sinks, the caller is responsible for
        calling this method (see :meth:`initialize` for the recommended
        context-manager pattern).

        :meth:`finalize` and :meth:`initialize` bracket the sink's
        lifetime; :meth:`begin_run` / :meth:`prepare_batch` /
        :meth:`commit_batch` / :meth:`finalize_run` bracket each individual
        run within that lifetime.
        """
        return

    def __enter__(self) -> Self:
        """Enter the sink's lifetime: calls :meth:`initialize`."""
        self.initialize()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Exit the sink's lifetime: calls :meth:`finalize`."""
        self.finalize()

    def supports_resume(self) -> bool:
        """Whether this sink can extend a run it already holds.

        A sink that returns ``False`` is always given ``requested_id=None``
        and is never required to supply a resume token, because there is
        nothing for a token to name: a live-plotting sink draws to a window,
        a streaming sink writes to a socket, neither retains a run to go back
        to. Eleanor still starts such a sink normally; only the resume half of
        :meth:`begin_run`'s contract is waived.

        This matters once several sinks are active at once. Resume is
        per-sink -- the id space belongs to the sink, so only the sink can
        interpret a token -- and Eleanor requires a token for every sink that
        claims to support resuming, rather than silently starting some of them
        fresh and leaving the outputs of one run split across two ids. This
        method is how a sink opts out of that requirement.

        The default is ``True`` so third-party sinks that pre-date the
        capability keep their existing resume behaviour.
        """
        return True

    def supports_worker_commit(self) -> bool:
        """Whether :meth:`commit_batch` is safe to invoke from worker processes.

        Sinks that return ``True`` must tolerate being invoked concurrently
        from multiple workers against the same target, and skip the prepared
        payload's trip back to the parent entirely -- the future resolves
        straight to a small :class:`WriteOutcome` list.

        Sinks that return ``False`` (the default) have their
        :meth:`commit_batch` driven by the parent, once the worker's prepared
        payload arrives. Single-writer stores belong here.

        Note this says nothing about :meth:`prepare_batch`, which always runs
        in a worker, so **every** sink must be picklable regardless of what
        this returns. :meth:`initialize`, :meth:`begin_run`,
        :meth:`finalize_run` and :meth:`finalize` still run only in the main
        process; any state they establish that :meth:`prepare_batch` needs
        must either cross the pickle boundary with the sink or be re-derived
        there.
        """
        return False

    def supports_background_commit(self) -> bool:
        """Whether :meth:`commit_batch` may run on a dedicated writer thread.

        Eleanor's guarantee to a sink that returns ``True`` is narrow but
        firm: a *single* thread owns the sink for the duration of a run and is
        joined before :meth:`finalize_run`, so the sink never sees concurrent
        commits and never needs its own locking. What changes is only *which*
        thread -- :meth:`commit_batch` no longer runs on the same thread as
        :meth:`initialize`, :meth:`begin_run`, :meth:`finalize_run` or
        :meth:`finalize`.

        Return ``False`` (the default) if the sink holds anything thread-affine
        between those calls: a sqlite3 connection opened with
        ``check_same_thread``, thread-local storage, a C library with a
        per-thread context. Unlike the prepare/commit split, which every sink
        must implement, this one is opt-in precisely because only the sink
        knows whether its resources travel between threads.

        Has no effect when :meth:`supports_worker_commit` is ``True``: that
        commits in the worker, so there is no dispatch thread to get off.
        """
        return False

    def supports_progress(self) -> bool:
        """Whether :meth:`commit_batch` emits per-point output progress.

        Sinks that return ``True`` accept a :class:`ProgressHandle` on
        :meth:`commit_batch` and emit ``tick`` messages that sum to the number
        of rows they durably wrote. Eleanor uses this signal to decide
        whether to render the output progress bar at all: when every active
        sink returns ``False``, the output bar is never created.

        The default is ``False`` so third-party sinks that pre-date the
        progress protocol continue to work unchanged.
        """
        return False


@dataclass(slots=True, frozen=True)
class SinkBinding:
    """One active sink, together with everything a chunk needs to write to it.

    A run may drive several sinks at once, each with its own id space and its
    own commit strategy. Keeping the three together in one object -- rather
    than in parallel lists indexed in lockstep -- is deliberate: pairing a
    sink with the wrong order id, or crediting one sink's outcomes to another,
    is the failure mode this whole layer is most exposed to.

    Bindings cross into worker processes, so every field must pickle. The
    sink already must (:meth:`AbstractOutputSink.prepare_batch` always runs in
    a worker), and the order id must because the sink chose it.

    :param name: The sink's configured name. Identifies it in resume tokens,
        progress bars, per-sink statistics and error messages.
    :param commit_in_worker: A snapshot of
        :meth:`AbstractOutputSink.supports_worker_commit`, taken once when the
        binding is built. Snapshotting keeps the parent and the worker
        agreeing on where a given chunk gets committed even if a sink's answer
        were to vary.
    """

    name: str
    sink: AbstractOutputSink[object]
    order_id: object
    commit_in_worker: bool

    @staticmethod
    def bind(name: str, sink: AbstractOutputSink[object], order_id: object) -> SinkBinding:
        """Build a binding, snapshotting the sink's commit strategy."""
        return SinkBinding(
            name=name,
            sink=sink,
            order_id=order_id,
            commit_in_worker=sink.supports_worker_commit(),
        )


__all__ = [
    "AbstractOutputSink",
    "ChunkResult",
    "ComputeResult",
    "ErrorInfo",
    "RunStats",
    "SinkBinding",
    "SinkChunkResult",
    "WriteOutcome",
    "require_int_order_id",
]
