import signal
from multiprocessing.managers import SyncManager
from queue import Queue
from typing import cast, override
from unittest import TestCase, mock

import eleanor.progress as progress_mod
from eleanor.progress import Progress, ProgressMessage, _ChannelHandle


class _FakeQueue:
    """Minimal queue stand-in capturing puts and handing ``get`` fixed items."""

    def __init__(self, messages=None) -> None:
        self.messages = list(messages) if messages is not None else []
        self.puts: list[object] = []
        self.task_done_count = 0
        self.join_called = False

    def put(self, item) -> None:
        self.puts.append(item)

    def get(self):
        return self.messages.pop(0)

    def task_done(self) -> None:
        self.task_done_count += 1

    def join(self) -> None:
        self.join_called = True


class _FakeTqdm:
    """Lightweight tqdm stand-in recording every interaction."""

    instances: list["_FakeTqdm"] = []
    # Value returned by every instance's ``_time()`` -- tests override this
    # before invoking the listener to assert what ``reset_timer_to_now``
    # writes back into ``start_t`` / ``last_print_t``. Mirrors the way real
    # tqdm exposes its clock as ``self._time``.
    time_value: float = 0.0

    def __init__(self, total, unit, colour, position, desc) -> None:
        self.total = total
        self.unit = unit
        self.colour = colour
        self.position = position
        self.desc = desc
        self.update_calls: list[int] = []
        self.refresh_calls = 0
        self.closed = False
        # Sentinel distinguishable from any value tests install via
        # ``_FakeTqdm.time_value``; the listener's ``reset_timer_to_now``
        # rewrites these via a Protocol cast on the first tick.
        self.start_t: float = -1.0
        self.last_print_t: float = -1.0
        _FakeTqdm.instances.append(self)

    def _time(self):
        return _FakeTqdm.time_value

    def update(self, n) -> None:
        self.update_calls.append(n)

    def refresh(self) -> None:
        self.refresh_calls += 1

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, target) -> None:
        self.target = target
        self.started = False
        self.join_calls: list[float | None] = []
        self.terminated = False
        self._alive_sequence: list[bool] = [True, False]

    def start(self) -> None:
        self.started = True

    def join(self, timeout=None) -> None:
        self.join_calls.append(timeout)

    def is_alive(self):
        if len(self._alive_sequence) > 1:
            return self._alive_sequence.pop(0)
        return self._alive_sequence[0]

    def terminate(self) -> None:
        self.terminated = True


class _FakeManager:
    def __init__(self, queue) -> None:
        self._queue = queue

    def Queue(self):
        return self._queue


def _typed_progress_queue(queue: _FakeQueue) -> "Queue[ProgressMessage | None]":
    return cast("Queue[ProgressMessage | None]", cast(object, queue))


def _typed_manager(manager: _FakeManager) -> SyncManager:
    return cast(SyncManager, cast(object, manager))


class TestChannelHandle(TestCase):
    """Tests of the picklable per-channel handle used by workers."""

    def test_total_tick_and_extend_emit_tagged_messages(self) -> None:
        """
        Ensure _ChannelHandle emits ProgressMessages tagged with the correct channel and kind.
        """
        queue = _FakeQueue()
        sim = _ChannelHandle(_typed_progress_queue(queue), "sim")
        out = _ChannelHandle(_typed_progress_queue(queue), "out")

        sim.total(10)
        sim.tick()
        sim.tick(3)
        sim.extend(4)
        sim.done()
        out.total(7)
        out.tick(2)
        out.done()

        self.assertEqual(
            queue.puts,
            [
                ProgressMessage(channel="sim", kind="total", value=10),
                ProgressMessage(channel="sim", kind="tick", value=1),
                ProgressMessage(channel="sim", kind="tick", value=3),
                ProgressMessage(channel="sim", kind="extend", value=4),
                ProgressMessage(channel="sim", kind="done", value=0),
                ProgressMessage(channel="out", kind="total", value=7),
                ProgressMessage(channel="out", kind="tick", value=2),
                ProgressMessage(channel="out", kind="done", value=0),
            ],
        )

    def test_channel_handle_is_picklable_for_worker_use(self) -> None:
        """
        Ensure _ChannelHandle round-trips through pickle so it can cross to workers.
        """
        import pickle

        queue = _FakeQueue()
        sim = _ChannelHandle(_typed_progress_queue(queue), "sim")
        copy = pickle.loads(pickle.dumps(sim))

        # The wrapper must survive pickling as a _ChannelHandle with the same channel.
        self.assertIsInstance(copy, _ChannelHandle)
        self.assertEqual(copy._channel, "sim")


class TestProgressLifecycle(TestCase):
    """Tests for :class:`Progress` construction and shutdown bookkeeping."""

    def test_init_starts_listener_process_and_exposes_handles(self) -> None:
        """
        Ensure :class:`Progress` starts its listener and yields picklable channel handles.
        """
        queue = _FakeQueue()
        manager = _FakeManager(queue)

        with mock.patch.object(progress_mod, "Process", _FakeProcess):
            p = Progress(_typed_manager(manager))
        fake_process = cast(_FakeProcess, cast(object, p.process))
        self.assertTrue(fake_process.started)
        self.assertIs(p.queue, queue)

        sim_handle = p.sim
        out_handle = p.out
        self.assertIsInstance(sim_handle, _ChannelHandle)
        self.assertIsInstance(out_handle, _ChannelHandle)
        self.assertEqual(cast(_ChannelHandle, sim_handle)._channel, "sim")
        self.assertEqual(cast(_ChannelHandle, out_handle)._channel, "out")

    def test_join_puts_sentinel_and_waits_for_listener(self) -> None:
        """
        Ensure :meth:`Progress.join` enqueues a shutdown sentinel and waits for the listener.
        """
        queue = _FakeQueue()
        manager = _FakeManager(queue)

        with mock.patch.object(progress_mod, "Process", _FakeProcess):
            p = Progress(_typed_manager(manager))
            fake_process = cast(_FakeProcess, cast(object, p.process))
            fake_process._alive_sequence = [True, False]
            p.join()

        self.assertEqual(queue.puts, [None])
        self.assertTrue(queue.join_called)
        self.assertEqual(fake_process.join_calls, [5.0])
        self.assertFalse(fake_process.terminated)

    def test_join_skips_queue_join_when_listener_is_dead(self) -> None:
        """
        Ensure :meth:`Progress.join` skips queue.join() when the listener is already dead.
        """
        queue = _FakeQueue()
        manager = _FakeManager(queue)

        with mock.patch.object(progress_mod, "Process", _FakeProcess):
            p = Progress(_typed_manager(manager))
            fake_process = cast(_FakeProcess, cast(object, p.process))
            fake_process._alive_sequence = [False, False]
            p.join()

        self.assertEqual(queue.puts, [None])
        self.assertFalse(queue.join_called)
        self.assertEqual(fake_process.join_calls, [5.0])
        self.assertFalse(fake_process.terminated)

    def test_join_terminates_listener_when_join_times_out(self) -> None:
        """
        Ensure :meth:`Progress.join` terminates a listener process that remains alive after timeout.
        """
        queue = _FakeQueue()
        manager = _FakeManager(queue)

        with mock.patch.object(progress_mod, "Process", _FakeProcess):
            p = Progress(_typed_manager(manager))
            fake_process = cast(_FakeProcess, cast(object, p.process))
            fake_process._alive_sequence = [True, True]
            p.join()

        self.assertEqual(queue.puts, [None])
        self.assertTrue(queue.join_called)
        self.assertTrue(fake_process.terminated)
        self.assertEqual(fake_process.join_calls, [5.0, None])


class TestProgressListener(TestCase):
    """Tests of :meth:`Progress.listen` message handling."""

    @override
    def setUp(self) -> None:
        _FakeTqdm.instances = []
        _FakeTqdm.time_value = 0.0

    def _run_listener(self, messages):
        queue = _FakeQueue(messages=messages)
        p = object.__new__(Progress)
        setattr(p, "queue", queue)
        with (
            mock.patch.object(progress_mod, "tqdm", _FakeTqdm),
            mock.patch("eleanor.progress.signal.signal") as signal_mock,
        ):
            p.listen()
        signal_mock.assert_called_once_with(signal.SIGINT, signal.SIG_IGN)
        return queue

    def _bars_by_channel(self):
        """Partition the ordered FakeTqdm instances by their position."""
        bars: dict[str, _FakeTqdm] = {}
        for bar in _FakeTqdm.instances:
            if bar.position == 0:
                bars["sim"] = bar
            elif bar.position == 1:
                bars["out"] = bar
        return bars

    def test_sim_total_tick_and_extend(self) -> None:
        """
        Ensure sim-channel messages drive a single bar with total/extend/tick semantics.
        """
        queue = self._run_listener(
            [
                ProgressMessage(channel="sim", kind="total", value=5),
                ProgressMessage(channel="sim", kind="tick", value=1),
                ProgressMessage(channel="sim", kind="extend", value=3),
                ProgressMessage(channel="sim", kind="tick", value=2),
                None,
            ]
        )
        bars = self._bars_by_channel()

        # Only the sim bar is created -- the output bar is lazy.
        self.assertIn("sim", bars)
        self.assertNotIn("out", bars)

        sim = bars["sim"]
        self.assertEqual(sim.unit, " systems")
        self.assertEqual(sim.total, 8)  # 5 then extended by 3
        self.assertEqual(sim.update_calls, [1, 2])
        self.assertTrue(sim.closed)
        # The bar should carry a human-readable label so the user can tell
        # it apart from the output bar.
        self.assertEqual(sim.desc.strip(), "sims")
        self.assertEqual(queue.task_done_count, 5)

    def test_output_bar_materialises_only_after_first_out_message(self) -> None:
        """
        Ensure the output bar is created only when an out-channel message arrives.
        """
        # Sim-only traffic: no output bar should ever be built.
        self._run_listener(
            [
                ProgressMessage(channel="sim", kind="total", value=2),
                ProgressMessage(channel="sim", kind="tick", value=1),
                None,
            ]
        )
        self.assertNotIn("out", self._bars_by_channel())

        _FakeTqdm.instances = []

        # Now send both channels; both bars should be rendered and in the
        # correct positions.
        self._run_listener(
            [
                ProgressMessage(channel="sim", kind="total", value=2),
                ProgressMessage(channel="sim", kind="tick", value=1),
                ProgressMessage(channel="out", kind="total", value=2),
                ProgressMessage(channel="out", kind="tick", value=1),
                None,
            ]
        )
        bars = self._bars_by_channel()
        self.assertIn("sim", bars)
        self.assertIn("out", bars)
        self.assertEqual(bars["sim"].total, 2)
        self.assertEqual(bars["out"].total, 2)
        self.assertEqual(bars["out"].update_calls, [1])
        # Sim and out bars should have distinct, human-readable labels and
        # be padded to a common width so they line up vertically.
        self.assertEqual(bars["sim"].desc.strip(), "sims")
        self.assertEqual(bars["out"].desc.strip(), "output")
        self.assertEqual(len(bars["sim"].desc), len(bars["out"].desc))

    def test_sim_extend_without_prior_total_seeds_initial_total(self) -> None:
        """
        Ensure an extend as the first message for a channel sets the initial total.
        """
        self._run_listener(
            [
                ProgressMessage(channel="sim", kind="extend", value=3),
                ProgressMessage(channel="sim", kind="tick", value=1),
                None,
            ]
        )
        bars = self._bars_by_channel()
        self.assertEqual(bars["sim"].total, 3)
        self.assertEqual(bars["sim"].update_calls, [1])

    def test_listener_closes_both_bars_on_shutdown(self) -> None:
        """
        Ensure both bars receive close() when the shutdown sentinel is processed.
        """
        self._run_listener(
            [
                ProgressMessage(channel="sim", kind="total", value=2),
                ProgressMessage(channel="out", kind="total", value=2),
                None,
            ]
        )
        bars = self._bars_by_channel()
        self.assertTrue(bars["sim"].closed)
        self.assertTrue(bars["out"].closed)

    def test_done_closes_channel_and_ignores_late_messages(self) -> None:
        """
        Ensure a done message freezes/closes one channel and late messages on that channel are ignored.
        """
        self._run_listener(
            [
                ProgressMessage(channel="sim", kind="total", value=2),
                ProgressMessage(channel="sim", kind="tick", value=1),
                ProgressMessage(channel="sim", kind="done", value=0),
                ProgressMessage(
                    channel="sim", kind="tick", value=1
                ),  # ignored after done
                ProgressMessage(channel="out", kind="total", value=1),
                ProgressMessage(channel="out", kind="tick", value=1),
                None,
            ]
        )
        bars = self._bars_by_channel()
        self.assertEqual(bars["sim"].update_calls, [1])
        self.assertTrue(bars["sim"].closed)
        self.assertEqual(bars["out"].update_calls, [1])

    def test_done_on_unmaterialized_channel_is_a_noop(self) -> None:
        """
        Ensure done for a channel with no prior messages does not crash and does not materialize a bar.
        """
        self._run_listener(
            [
                ProgressMessage(channel="sim", kind="total", value=3),
                ProgressMessage(channel="sim", kind="tick", value=1),
                ProgressMessage(channel="out", kind="done", value=0),
                ProgressMessage(channel="sim", kind="tick", value=1),
                None,
            ]
        )
        bars = self._bars_by_channel()
        self.assertIn("sim", bars)
        self.assertNotIn("out", bars)
        self.assertEqual(bars["sim"].update_calls, [1, 1])

    def test_first_tick_resets_elapsed_timer_baseline(self) -> None:
        """
        Ensure the first tick resets tqdm's internal timer so elapsed starts at first completed unit.
        """
        queue = _FakeQueue(
            messages=[
                ProgressMessage(channel="sim", kind="total", value=2),
                ProgressMessage(channel="sim", kind="tick", value=1),
                None,
            ]
        )
        p = object.__new__(Progress)
        setattr(p, "queue", queue)

        # ``reset_timer_to_now`` reads ``bar._time()`` so it stays in the same
        # clock domain as tqdm's elapsed display; route the fake bar's clock
        # through ``_FakeTqdm.time_value`` so the test owns the value the
        # listener installs into ``start_t`` / ``last_print_t``.
        _FakeTqdm.time_value = 123.0
        with (
            mock.patch.object(progress_mod, "tqdm", _FakeTqdm),
            mock.patch("eleanor.progress.signal.signal"),
        ):
            p.listen()

        bars = self._bars_by_channel()
        self.assertEqual(bars["sim"].start_t, 123.0)
        self.assertEqual(bars["sim"].last_print_t, 123.0)

    def test_done_before_any_tick_does_not_reset_timer(self) -> None:
        """
        Ensure done arriving before any tick leaves tqdm's elapsed timer untouched.
        """
        queue = _FakeQueue(
            messages=[
                ProgressMessage(channel="sim", kind="total", value=2),
                ProgressMessage(channel="sim", kind="done", value=0),
                None,
            ]
        )
        p = object.__new__(Progress)
        setattr(p, "queue", queue)

        # If ``reset_timer_to_now`` were (incorrectly) called here, both
        # fields would be 999.0 instead of the _FakeTqdm -1.0 sentinel.
        _FakeTqdm.time_value = 999.0
        with (
            mock.patch.object(progress_mod, "tqdm", _FakeTqdm),
            mock.patch("eleanor.progress.signal.signal"),
        ):
            p.listen()

        bars = self._bars_by_channel()
        self.assertTrue(bars["sim"].closed)
        self.assertEqual(bars["sim"].start_t, -1.0)
        self.assertEqual(bars["sim"].last_print_t, -1.0)
