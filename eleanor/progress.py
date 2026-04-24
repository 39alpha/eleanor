"""Dual-channel progress pump shared between the parent process and workers.

The :class:`Progress` pump drives up to two stacked :mod:`tqdm` bars:

``sim``
    Advances as variable-space points complete their kernel compute step. Ticks
    are typically emitted from worker processes via :class:`Sailor.dispatch`.

``out``
    Advances as points are durably written by the active :class:`OutputSink`.
    Ticks are typically emitted from inside the sink's ``write_batch`` (either
    from workers, for ``supports_worker_writes`` sinks, or from the parent for
    serial sinks). The bar is created lazily and only if at least one ``out``
    channel message is ever delivered -- sinks that do not opt in to progress
    reporting (see :meth:`OutputSink.supports_progress`) never cause an output
    bar to render.

A single :class:`multiprocessing.Manager`-backed queue carries tagged
:class:`ProgressMessage` objects so there is still one consumer process behind
the scenes. Per-channel :class:`_ChannelHandle` wrappers hide the tagging and
are picklable, so they can cross the worker boundary alongside the underlying
queue proxy.
"""
from dataclasses import dataclass
from multiprocessing import Process
from multiprocessing.managers import SyncManager
from queue import Queue
from typing import Literal, NoReturn, Protocol, runtime_checkable

from tqdm import tqdm

from .typing import cast

Channel = Literal['sim', 'out']
MessageKind = Literal['total', 'extend', 'tick']


@dataclass(slots=True, frozen=True)
class ProgressMessage(object):
    """A single tagged progress update.

    :param channel: The bar the message targets -- ``'sim'`` or ``'out'``.
    :param kind: The operation to perform on the bar:

        * ``'total'``  -- set the bar's absolute total to ``value``.
        * ``'extend'`` -- add ``value`` to the bar's running total (ignored
          when the bar has ``no_total_update=True``).
        * ``'tick'``   -- advance the bar by ``value`` completed units.
    :param value: The argument to the operation. For ``'tick'`` the value is
        the number of units to advance; for ``'total'`` / ``'extend'`` it is
        an absolute / delta count respectively.
    """
    channel: Channel
    kind: MessageKind
    value: int


@runtime_checkable
class ProgressHandle(Protocol):
    """Worker-facing façade over a single progress channel.

    The handle exposes only the operations the producer is expected to use and
    hides the underlying tagged-message format. Handles are cheap, picklable
    wrappers over the shared :class:`multiprocessing.Manager`-backed queue.
    """

    def total(self, n: int) -> None:
        """Set the bar's absolute total to ``n``."""
        ...

    def extend(self, n: int) -> None:
        """Add ``n`` units to the bar's running total."""
        ...

    def tick(self, n: int = 1) -> None:
        """Advance the bar by ``n`` completed units."""
        ...


class _ChannelHandle(object):
    """Concrete :class:`ProgressHandle` that tags each message with a channel.

    Placed at module scope so it remains picklable for workers: the only
    state is a queue proxy and a string literal.
    """

    __slots__: tuple[str, ...] = ('_queue', '_channel')

    _queue: 'Queue[ProgressMessage | None]'
    _channel: Channel

    def __init__(self, queue: 'Queue[ProgressMessage | None]', channel: Channel):
        self._queue = queue
        self._channel = channel

    def total(self, n: int) -> None:
        self._queue.put(ProgressMessage(channel=self._channel, kind='total', value=int(n)))

    def extend(self, n: int) -> None:
        self._queue.put(ProgressMessage(channel=self._channel, kind='extend', value=int(n)))

    def tick(self, n: int = 1) -> None:
        self._queue.put(ProgressMessage(channel=self._channel, kind='tick', value=int(n)))


class Progress(object):
    """Two-bar progress pump.

    The pump starts a dedicated listener :class:`~multiprocessing.Process` that
    drains tagged messages from a shared queue and renders up to two stacked
    :mod:`tqdm` bars. The output bar is created lazily: if no ``out`` channel
    message is ever received, only the simulation bar is displayed.

    :param manager: The shared :class:`~multiprocessing.managers.SyncManager`
        used to allocate the cross-process queue.
    :param out_no_total_update: When ``True``, the output bar ignores
        ``extend`` messages after its initial total is set. Used under
        ``success_sampling`` where the output bar tracks progress toward a
        fixed target (N successes) rather than the growing attempt count.
    """

    queue: 'Queue[ProgressMessage | None]'
    process: Process
    out_no_total_update: bool

    def __init__(self, manager: SyncManager, out_no_total_update: bool = False):
        self.out_no_total_update = out_no_total_update
        # SyncManager.Queue() is typed as Any by the stubs; narrow it here so
        # downstream users see the ProgressMessage shape we expect.
        self.queue = cast('Queue[ProgressMessage | None]', manager.Queue())
        self.process = Process(target=self.listen)
        self.process.start()

    @property
    def sim(self) -> ProgressHandle:
        """Handle for the simulation channel. Picklable for worker use."""
        return _ChannelHandle(self.queue, 'sim')

    @property
    def out(self) -> ProgressHandle:
        """Handle for the output channel. Picklable for worker use."""
        return _ChannelHandle(self.queue, 'out')

    def listen(self) -> None:
        """Drain the queue until a shutdown sentinel (``None``) arrives.

        Runs in the listener subprocess. Per-channel state (bars, totals,
        total-update policy) is kept locally; the parent's copy of ``self`` is
        read-only here except for resources that live in the queue itself.
        """
        bars: dict[Channel, tqdm[NoReturn] | None] = {'sim': None, 'out': None}
        totals: dict[Channel, int] = {'sim': 0, 'out': 0}
        positions: dict[Channel, int] = {'sim': 0, 'out': 1}
        colours: dict[Channel, str] = {'sim': '#ec5c29', 'out': '#2993ec'}
        descriptions: dict[Channel, str] = {'sim': 'sims', 'out': 'output'}
        description_width = max(len(description) for description in descriptions.values())
        no_total_update: dict[Channel, bool] = {'sim': False, 'out': self.out_no_total_update}
        first_total: dict[Channel, bool] = {'sim': True, 'out': True}

        def ensure_bar(channel: Channel) -> tqdm[NoReturn]:
            bar = bars[channel]
            if bar is None:
                bar = tqdm(
                    total=totals[channel] if totals[channel] > 0 else None,
                    unit=' systems',
                    colour=colours[channel],
                    position=positions[channel],
                    desc=descriptions[channel].ljust(description_width),
                )
                bars[channel] = bar
            return bar

        while True:
            msg = self.queue.get()
            if msg is None:
                _ = self.queue.task_done()
                break

            channel = msg.channel
            if msg.kind == 'total':
                totals[channel] = msg.value
                first_total[channel] = False
                bar = ensure_bar(channel)
                bar.total = msg.value
                bar.refresh()
            elif msg.kind == 'extend':
                if first_total[channel]:
                    # Treat the first extend as the bar's initial total so a
                    # producer that only ever sends extends still gets a bar.
                    totals[channel] = msg.value
                    first_total[channel] = False
                    bar = ensure_bar(channel)
                    bar.total = totals[channel]
                    bar.refresh()
                elif not no_total_update[channel]:
                    totals[channel] += msg.value
                    bar = ensure_bar(channel)
                    bar.total = totals[channel]
                    bar.refresh()
            elif msg.kind == 'tick':
                bar = ensure_bar(channel)
                _ = bar.update(msg.value)

            _ = self.queue.task_done()

        for bar in bars.values():
            if bar is not None:
                bar.close()

    def join(self) -> None:
        """Signal the listener to shut down and wait for it to exit."""
        self.queue.put(None)
        self.queue.join()
        self.process.join()
