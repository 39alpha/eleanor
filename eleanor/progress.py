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

import signal
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing import Process
from multiprocessing.managers import SyncManager
from queue import Queue
from typing import Literal, NoReturn, Protocol, runtime_checkable

from tqdm import tqdm

from .typing import cast

Channel = Literal["sim", "out"]
MessageKind = Literal["total", "extend", "tick", "done"]


class _TimedBar(Protocol):
    """Internal view of the ``tqdm`` timer fields the listener resets.

    ``tqdm`` starts timing at construction, but the listener may instantiate
    a bar on a ``total`` / ``extend`` message before any work has actually
    started; this Protocol lets the listener narrow a ``tqdm`` instance to
    just the timer attributes it needs to rewrite.

    ``_time`` is the bar's own clock callable -- tqdm seeds ``start_t`` from
    it and computes ``elapsed = self._time() - self.start_t``. Reading
    through ``_time`` rather than calling :mod:`time` directly keeps the
    reset in the same clock domain as the displayed elapsed; calling a
    different clock (e.g. ``time.monotonic`` while tqdm uses ``time.time``)
    produces nonsense elapsed values on the order of decades.
    """

    start_t: float
    last_print_t: float
    _time: Callable[[], float]


@dataclass(slots=True, frozen=True)
class ProgressMessage(object):
    """A single tagged progress update.

    :param channel: The bar the message targets -- ``'sim'`` or ``'out'``.
    :param kind: The operation to perform on the bar:

        * ``'total'``  -- set the bar's absolute total to ``value``.
        * ``'extend'`` -- add ``value`` to the bar's running total.
        * ``'tick'``   -- advance the bar by ``value`` completed units.
        * ``'done'``   -- freeze and close the bar at its current state.
    :param value: The argument to the operation. For ``'tick'`` the value is
        the number of units to advance; for ``'total'`` / ``'extend'`` it is
        an absolute / delta count respectively. ``'done'`` ignores ``value``.
    """

    channel: Channel
    kind: MessageKind
    value: int


@runtime_checkable
class ProgressHandle(Protocol):
    """Worker-facing façade over a single progress channel.

    The handle exposes only the operations a producer (worker or sink) is
    expected to use and hides the underlying tagged-message format. Handles
    are cheap, picklable wrappers over the shared
    :class:`multiprocessing.Manager`-backed queue.

    Note that this Protocol intentionally does *not* expose ``done()``;
    closing a channel's bar is a parent-only operation. Workers and sinks
    are typed against this narrower view at every boundary
    (:meth:`Sailor.dispatch`, :meth:`OutputSink.write_batch`,
    :meth:`Eleanor.process`) so an accidental ``done()`` from a producer is
    rejected by the type checker rather than silently dropping ticks from
    other workers.
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


@runtime_checkable
class ManagedProgressHandle(ProgressHandle, Protocol):
    """Parent-facing :class:`ProgressHandle` with the privileged ``done()`` op.

    :class:`Progress` returns this wider view from :attr:`Progress.sim` /
    :attr:`Progress.out` so the parent dispatch context can close a channel's
    bar. Producers (workers, sinks) only ever see the narrower
    :class:`ProgressHandle`, which keeps ``done()`` out of reach for any
    code path that would race against other producers on the same channel.
    """

    def done(self) -> None:
        """Freeze and close this channel's bar.

        Must be called only from the parent dispatch context, not from
        workers. Calling it from a worker would immediately close the bar
        and cause all subsequent ticks from other workers on this channel
        to be silently discarded.
        """
        ...


class _ChannelHandle(object):
    """Concrete :class:`ManagedProgressHandle` that tags each message with a channel.

    Placed at module scope so it remains picklable for workers: the only
    state is a queue proxy and a string literal.
    """

    __slots__: tuple[str, ...] = ("_queue", "_channel")

    _queue: "Queue[ProgressMessage | None]"
    _channel: Channel

    def __init__(self, queue: "Queue[ProgressMessage | None]", channel: Channel):
        self._queue = queue
        self._channel = channel

    def total(self, n: int) -> None:
        self._queue.put(ProgressMessage(channel=self._channel, kind="total", value=int(n)))

    def extend(self, n: int) -> None:
        self._queue.put(ProgressMessage(channel=self._channel, kind="extend", value=int(n)))

    def tick(self, n: int = 1) -> None:
        self._queue.put(ProgressMessage(channel=self._channel, kind="tick", value=int(n)))

    def done(self) -> None:
        self._queue.put(ProgressMessage(channel=self._channel, kind="done", value=0))


class Progress(object):
    """Two-bar progress pump.

    The pump starts a dedicated listener :class:`~multiprocessing.Process` that
    drains tagged messages from a shared queue and renders up to two stacked
    :mod:`tqdm` bars. The output bar is created lazily: if no ``out`` channel
    message is ever received, only the simulation bar is displayed.

    :param manager: The shared :class:`~multiprocessing.managers.SyncManager`
        used to allocate the cross-process queue.
    """

    queue: "Queue[ProgressMessage | None]"
    process: Process

    def __init__(self, manager: SyncManager):
        # SyncManager.Queue() is typed as Any by the stubs; narrow it here so
        # downstream users see the ProgressMessage shape we expect.
        self.queue = cast("Queue[ProgressMessage | None]", manager.Queue())
        self.process = Process(target=self.listen)
        self.process.start()

    @property
    def sim(self) -> ManagedProgressHandle:
        """Handle for the simulation channel. Picklable for worker use.

        Returns the parent-facing :class:`ManagedProgressHandle` so the
        dispatch context can call ``done()``; producers downstream are still
        typed against :class:`ProgressHandle`, which omits ``done()``.
        """
        return _ChannelHandle(self.queue, "sim")

    @property
    def out(self) -> ManagedProgressHandle:
        """Handle for the output channel. Picklable for worker use.

        See :attr:`sim` for the rationale behind the parent-vs-worker
        Protocol split.
        """
        return _ChannelHandle(self.queue, "out")

    def listen(self) -> None:
        """Drain the queue until a shutdown sentinel (``None``) arrives.

        Individual channel bars may be closed early by sending a ``"done"``
        message; any subsequent messages for that channel are discarded.
        Runs in the listener subprocess. Per-channel state (bars, totals) is
        kept locally; the parent's copy of ``self`` is
        read-only here except for resources that live in the queue itself.
        """
        _ = signal.signal(signal.SIGINT, signal.SIG_IGN)
        bars: dict[Channel, tqdm[NoReturn] | None] = {"sim": None, "out": None}
        totals: dict[Channel, int] = {"sim": 0, "out": 0}
        positions: dict[Channel, int] = {"sim": 0, "out": 1}
        colours: dict[Channel, str] = {"sim": "#ec5c29", "out": "#2993ec"}
        descriptions: dict[Channel, str] = {"sim": "  sims", "out": "output"}
        description_width = max(len(description) for description in descriptions.values())
        first_total: dict[Channel, bool] = {"sim": True, "out": True}
        first_tick: dict[Channel, bool] = {"sim": True, "out": True}
        channel_done: dict[Channel, bool] = {"sim": False, "out": False}

        def ensure_bar(channel: Channel) -> tqdm[NoReturn]:
            bar = bars[channel]
            if bar is None:
                bar = tqdm(
                    total=totals[channel] if totals[channel] > 0 else None,
                    unit=" systems",
                    colour=colours[channel],
                    position=positions[channel],
                    desc=descriptions[channel].ljust(description_width),
                )
                bars[channel] = bar
            return bar

        def reset_timer_to_now(bar: tqdm[NoReturn]) -> None:
            # tqdm starts timing when the bar is instantiated, but this pump
            # may instantiate a bar on ``total``/``extend`` before the first
            # completed unit arrives. Reset to the first tick so elapsed time
            # reflects active work duration for that channel.
            #
            # ``bar._time`` is tqdm's own clock callable (``time.time`` by
            # default in tqdm 4.x); reading through it keeps ``start_t`` in
            # the same clock domain as the elapsed display, which uses
            # ``self._time() - self.start_t``. Calling a different clock
            # (e.g. ``time.monotonic``, which returns system uptime) here
            # would make tqdm display ``time.time() - small_uptime`` as
            # elapsed -- a number on the order of decades.
            #
            # Cast through ``object`` because ``tqdm[NoReturn]`` does not
            # structurally overlap with ``_TimedBar`` from pyright's point
            # of view: tqdm sets ``start_t`` / ``last_print_t`` / ``_time``
            # as instance attributes inside ``__init__``, not declared class
            # attributes the type checker can see. The Protocol is
            # specifically a typed window into those instance attributes.
            timed_bar = cast("_TimedBar", cast(object, bar))
            # ``_time`` is private to tqdm by name only; this whole reset is
            # an intentional reach into tqdm's internals, gated by the
            # ``_TimedBar`` Protocol and the tqdm version pin in pyproject.
            now = timed_bar._time()  # pyright: ignore[reportPrivateUsage]
            timed_bar.start_t = now
            timed_bar.last_print_t = now

        while True:
            msg = self.queue.get()
            if msg is None:
                _ = self.queue.task_done()
                break

            channel = msg.channel
            if channel_done[channel]:
                _ = self.queue.task_done()
                continue

            if msg.kind == "total":
                totals[channel] = msg.value
                first_total[channel] = False
                bar = ensure_bar(channel)
                bar.total = msg.value
                bar.refresh()
            elif msg.kind == "extend":
                if first_total[channel]:
                    # Treat the first extend as the bar's initial total so a
                    # producer that only ever sends extends still gets a bar.
                    totals[channel] = msg.value
                    first_total[channel] = False
                    bar = ensure_bar(channel)
                    bar.total = totals[channel]
                    bar.refresh()
                else:
                    totals[channel] += msg.value
                    bar = ensure_bar(channel)
                    bar.total = totals[channel]
                    bar.refresh()
            elif msg.kind == "tick":
                bar = ensure_bar(channel)
                if first_tick[channel]:
                    reset_timer_to_now(bar)
                    first_tick[channel] = False
                _ = bar.update(msg.value)
            elif msg.kind == "done":
                # The early-continue at the top of the loop already filtered
                # out a duplicate ``done`` for this channel, so by the time we
                # land here ``channel_done[channel]`` is necessarily ``False``.
                channel_done[channel] = True
                bar = bars[channel]
                if bar is not None:
                    # ``tqdm.close()`` defaults to ``leave=True`` and runs its
                    # own final ``display(pos=0)`` that re-renders the bar at
                    # the cursor's current line and writes ``\n``. Calling
                    # ``bar.refresh()`` first is *not* a no-op here: by the
                    # time we process the second channel's ``done``, the
                    # first channel's ``close()`` has already advanced the
                    # cursor by one line, so the second channel's
                    # ``refresh()`` -- which moves to relative ``pos=1`` --
                    # ends up rendering an extra copy of the bar one line
                    # below its actual on-screen position. The subsequent
                    # ``close()`` then overwrites the original final-tick
                    # render at the correct line, leaving the stray copy
                    # below it as a visible duplicate until the next prompt
                    # paint. Letting ``close()`` do the only render keeps
                    # tqdm's cursor accounting consistent across both bars.
                    #
                    # When no tick was ever observed, ``reset_timer_to_now``
                    # has not run, so ``start_t`` / ``last_print_t`` are
                    # whatever tqdm seeded at construction. ``close()`` will
                    # then display elapsed = ``_time() - start_t`` -- the
                    # actual wall-clock duration the bar was visible -- which
                    # is the most defensible thing to show when no progress
                    # was made.
                    bar.close()
                    bars[channel] = None

            _ = self.queue.task_done()

        for bar in bars.values():
            if bar is not None:
                bar.close()

    def join(self) -> None:
        """Signal the listener to shut down and wait for it to exit."""
        self.queue.put(None)
        if self.process.is_alive():
            self.queue.join()
        self.process.join(timeout=5.0)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join()
