import io
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from typing import cast
from unittest import TestCase, mock

from eleanor.config import Config
from eleanor.config.output import OutputSinkConfig
from eleanor.eleanor import Eleanor
from eleanor.exceptions import EleanorError, EleanorShutdown
from eleanor.executor import AbstractExecutor
from eleanor.executor.settings import ExecutorSettings
from eleanor.kernel import AbstractKernel
from eleanor.order import Order
from eleanor.output import AbstractOutputSink, ComputeResult, WriteOutcome
from eleanor.output.interface import ChunkResult, SinkBinding, SinkChunkResult
from eleanor.output.null import NullSinkSettings
import eleanor.timing as timing_mod
from eleanor.timing import DispatchTimings
from eleanor.variable_space import Point


class _Future:
    def __init__(self, value) -> None:
        self._value = value

    def result(self):
        return self._value

    def get(self):
        return self.result()

    def ready(self) -> bool:
        # Already-resolved, matching ``SerialFuture``.
        return True


class _StepClock:
    """Monotonic stand-in for ``time.perf_counter`` advanced by the test."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeExecutor:
    """Minimal ``AbstractExecutor`` stand-in with recording ``submit``/``shutdown``."""

    supports_worker_progress: bool = True

    def __init__(self, num_workers=2, submit_side_effect=None) -> None:
        self._num_workers = num_workers
        self.enter_count = 0
        if submit_side_effect is None or callable(submit_side_effect):
            effect = submit_side_effect or self._default_submit
        else:
            effect = self._adapting(list(submit_side_effect))
        self.submit = mock.Mock(side_effect=effect)
        self.pop_completed_future = mock.Mock(
            side_effect=lambda futures: futures.pop(0)
        )
        self.shutdown = mock.Mock()

    @staticmethod
    def _default_submit(_fn, *args, **kwargs):
        """Resolve to an empty ``ChunkResult`` shaped for the given bindings."""
        return _Future(_chunk_result(args[0], kwargs["bindings"], []))

    @staticmethod
    def _adapting(futures):
        """Serve queued futures, reshaping raw payloads into ``ChunkResult``s.

        A fixture says what a chunk produced; which half of the per-sink result
        that lands in follows from the binding's commit strategy, so the fake
        derives it rather than making every fixture spell it out. A fixture
        that already supplies a ``ChunkResult`` is passed through untouched.
        """
        queued = iter(futures)

        def submit(_fn, *args, **kwargs):
            future = next(queued)
            value = future.result()
            if isinstance(value, ChunkResult):
                return future
            return _Future(_chunk_result(args[0], kwargs["bindings"], value))

        return submit

    @property
    def num_workers(self):
        return self._num_workers

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, *_args):
        self.shutdown(wait=True)
        return None


def _make_eleanor():
    """Construct an ``Eleanor`` backed by a stubbed config."""
    return Eleanor(
        config=Config(
            output=[
                OutputSinkConfig(
                    kind="null",
                    settings=NullSinkSettings(support_worker_commit=False),
                ),
            ],
        )
    )


def _make_order(navigator_kind: str = "random") -> Order:
    """Produce a minimal order-like ``SimpleNamespace`` for ``Eleanor.run``."""
    return cast(
        Order,
        cast(
            object,
            SimpleNamespace(
                navigator=SimpleNamespace(kind=navigator_kind, args={}),
                id=None,
            ),
        ),
    )


def _point(*, exit_code: int = 0, **kwargs: object) -> Point:
    return cast(Point, cast(object, SimpleNamespace(exit_code=exit_code, **kwargs)))


def _as_executor(executor: _FakeExecutor) -> AbstractExecutor:
    return cast(AbstractExecutor, cast(object, executor))


def _navigator(num_systems: int = 1):
    navigator = mock.Mock()
    navigator.num_systems.return_value = num_systems
    navigator.navigate.return_value = iter([[]])
    return navigator


def _progress_factory(sim_handle, handles):
    """Build a ``Progress`` stand-in that honours its declared channel list.

    The gating on ``supports_progress`` now happens when the channel list is
    assembled, so a stub that hands out handles regardless would not show
    whether a declining sink was actually excluded.
    """

    def build(_manager, out_channels=()):
        return SimpleNamespace(
            sim=sim_handle,
            outs=lambda: {name: handles[name] for name in out_channels},
            join=mock.Mock(),
        )

    return build


@contextmanager
def _shutdown_with_state(state: SimpleNamespace):
    yield state


class TestEleanorConstruction(TestCase):
    """Tests covering ``Eleanor`` construction/session lifecycle."""

    def test_init_stashes_config_and_num_workers(self) -> None:
        """Ensure constructor stores config and num_workers."""
        fake_config = _make_eleanor().config
        eleanor = Eleanor(config=fake_config, num_workers=4)

        self.assertIs(eleanor.config, fake_config)
        self.assertEqual(eleanor.num_workers, 4)
        self.assertFalse(eleanor._entered)
        self.assertIsNone(eleanor._executor)
        self.assertIsNone(eleanor._manager)
        self.assertIsNone(eleanor._output_sinks)

    def test_init_raises_when_no_output_sink_configured(self) -> None:
        """Ensure constructor rejects a config with no output type and no sink override."""
        config = Config()
        with self.assertRaises(EleanorError):
            _ = Eleanor(config=config)

    def test_init_does_not_raise_when_output_sink_override_suppresses_guard(
        self,
    ) -> None:
        """Ensure constructor-level output_sink= bypasses the no-output-type guard."""
        config = Config()
        sink = mock.Mock(spec=AbstractOutputSink)
        eleanor = Eleanor(config=config, output_sink=sink)
        self.assertEqual(eleanor._output_sink_override, {"output": sink})

    def test_init_rejects_positional_config(self) -> None:
        """Ensure all constructor args are keyword-only after the * sentinel move."""
        with self.assertRaises(TypeError):
            _ = Eleanor(_make_eleanor().config)  # pyright: ignore[reportCallIssue]

    def test_enter_builds_executor_and_exit_tears_down_all(self) -> None:
        """Ensure __enter__/__exit__ set up and tear down session resources."""
        eleanor = _make_eleanor()
        executor = _FakeExecutor()
        manager = mock.Mock()
        sink = mock.Mock()

        with mock.patch(
            "eleanor.eleanor.load_executor", return_value=executor
        ) as load_executor:
            with eleanor:
                load_executor.assert_called_once_with(
                    "multiprocessing", ExecutorSettings()
                )
                self.assertIs(eleanor._executor, executor)
                eleanor._manager = manager
                eleanor._output_sinks = {"null": sink}

        sink.finalize.assert_called_once()
        manager.shutdown.assert_called_once()
        executor.shutdown.assert_called_once_with(wait=True)

    def test_run_failure_inside_with_still_tears_down_at_exit(self) -> None:
        """Ensure session resources are torn down when run() raises."""
        eleanor = _make_eleanor()
        order = _make_order()
        session_executor = _FakeExecutor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(side_effect=RuntimeError("dispatch failed"))

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=session_executor),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            with self.assertRaisesRegex(RuntimeError, "dispatch failed"):
                with eleanor:
                    _ = eleanor.run(order, 5, kernel=kernel, navigator=_navigator(1))

        sink.finalize.assert_called_once()
        session_executor.shutdown.assert_called_once_with(wait=True)

    def test_run_still_tears_down_executor_and_manager_when_sink_finalize_fails(
        self,
    ) -> None:
        """Ensure per-run teardown still closes manager/executor if sink.finalize() raises."""
        eleanor = _make_eleanor()
        order = _make_order()
        executor = _FakeExecutor()
        manager = mock.Mock()
        sim_handle = mock.Mock()
        progress = SimpleNamespace(
            sim=sim_handle, outs=lambda: {"null": mock.Mock()}, join=mock.Mock()
        )
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        sink.finalize.side_effect = RuntimeError("sink finalize failed")
        eleanor.process = mock.Mock(return_value={})

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=executor),
            mock.patch("eleanor.eleanor.Manager", return_value=manager),
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            self.assertRaisesRegex(RuntimeError, "sink finalize failed"),
        ):
            _ = eleanor.run(
                order, 5, kernel=kernel, navigator=_navigator(1), show_progress=True
            )

        manager.shutdown.assert_called_once()
        executor.shutdown.assert_called_once_with(wait=True)


class TestEleanorRun(TestCase):
    """Tests covering ``Eleanor.run`` single-order dispatch semantics."""

    def test_run_without_with_builds_and_tears_down_resources(self) -> None:
        """Ensure run() outside ``with`` builds/tears down executor and sink."""
        eleanor = _make_eleanor()
        order = _make_order()
        executor = _FakeExecutor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value={})

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch(
                "eleanor.eleanor.load_executor", return_value=executor
            ) as load_executor,
            mock.patch(
                "eleanor.eleanor.load_output_sink", return_value=sink
            ) as load_sink,
        ):
            out = eleanor.run(order, 5, kernel=kernel, navigator=_navigator(1))

        self.assertEqual(out, {"null": 7})
        load_executor.assert_called_once_with("multiprocessing", ExecutorSettings())
        assert len(eleanor.config.output) == 1
        load_sink.assert_called_once_with(
            eleanor.config.output[0].kind, eleanor.config.output[0].settings
        )
        sink.finalize.assert_called_once()
        executor.shutdown.assert_called_once_with(wait=True)

    def test_run_inside_with_reuses_session_executor_and_defers_finalize(self) -> None:
        """Ensure runs inside a session reuse executor and defer sink finalize."""
        eleanor = _make_eleanor()
        order1 = _make_order()
        order2 = _make_order()
        session_executor = _FakeExecutor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        seen_executors = []

        def process(*_args, **kwargs):
            seen_executors.append(kwargs["executor"])
            return {}

        eleanor.process = mock.Mock(side_effect=process)

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=session_executor),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            with eleanor:
                _ = eleanor.run(order1, 5, kernel=kernel, navigator=_navigator(1))
                _ = eleanor.run(order2, 5, kernel=kernel, navigator=_navigator(1))

        self.assertEqual(len(seen_executors), 2)
        self.assertIs(seen_executors[0], session_executor)
        self.assertIs(seen_executors[1], session_executor)
        sink.finalize.assert_called_once()

    def test_run_forwards_resume_id_to_begin_run_and_returns_the_sinks_id(self) -> None:
        """Ensure ``resume_id`` reaches the sink untouched and its id is returned.

        Eleanor does not interpret the token or the id: the sink owns that
        space, so the string goes down as given and whatever comes back is
        what ``run`` reports.
        """
        eleanor = _make_eleanor()
        order = _make_order()
        sink = mock.Mock()
        sink.begin_run.return_value = "sink-chosen-id"
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value={})

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            returned = eleanor.run(
                order, 4, kernel=kernel, navigator=_navigator(1), resume_id="99"
            )

        sink.begin_run.assert_called_once_with(order, requested_id="99")
        self.assertEqual(returned, {"null": "sink-chosen-id"})

    def test_run_passes_no_resume_id_when_none_is_given(self) -> None:
        """Ensure a plain run asks the sink for a fresh id rather than a resume."""
        eleanor = _make_eleanor()
        order = _make_order()
        sink = mock.Mock()
        sink.begin_run.return_value = 0
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value={})

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            _ = eleanor.run(order, 4, kernel=kernel, navigator=_navigator(1))

        sink.begin_run.assert_called_once_with(order, requested_id=None)

    def test_run_rejects_retired_executor_kwarg(self) -> None:
        """Ensure run() rejects the retired ``executor=`` kwarg."""
        eleanor = _make_eleanor()
        with self.assertRaisesRegex(
            TypeError, "unexpected keyword argument 'executor'"
        ):
            _ = eleanor.run(_make_order(), 1, executor=_FakeExecutor())  # pyright: ignore[reportCallIssue]

    def test_run_rejects_retired_parallel_kwarg(self) -> None:
        """Ensure run() rejects the retired ``parallel=`` kwarg."""
        eleanor = _make_eleanor()
        with self.assertRaisesRegex(
            TypeError, "unexpected keyword argument 'parallel'"
        ):
            _ = eleanor.run(_make_order(), 1, parallel="serial")  # pyright: ignore[reportCallIssue]

    def test_run_raises_when_num_systems_returns_zero(self) -> None:
        """Ensure run() validates navigator.num_systems >= 1."""
        eleanor = _make_eleanor()
        navigator = _navigator(0)
        sink = mock.Mock()
        sink.supports_progress.return_value = False

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            self.assertRaisesRegex(EleanorError, "num_systems.*must be >= 1"),
        ):
            _ = eleanor.run(_make_order(), 10, kernel=kernel, navigator=navigator)

    def test_run_raises_when_explicit_batch_size_is_zero(self) -> None:
        """Ensure run() validates explicit batch_size >= 1."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.supports_progress.return_value = False

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            self.assertRaisesRegex(EleanorError, "batch_size must be >= 1"),
        ):
            _ = eleanor.run(
                _make_order(), 10, kernel=kernel, navigator=_navigator(5), batch_size=0
            )

    def test_a_failing_begin_run_still_stops_the_progress_listener(self) -> None:
        """Ensure a sink refusing to start does not strand the listener process.

        ``Progress`` starts a subprocess as soon as it is constructed, and it
        was constructed before any sink's ``begin_run`` ran but torn down only
        by a ``finally`` that began after. A sink rejecting a resume token
        therefore left the listener alive holding a queue whose manager was
        about to be shut down, and it died printing its own traceback over
        the real error.
        """
        eleanor = _make_eleanor()
        sim_handle = mock.Mock(name="sim_handle")
        progress = _progress_factory(sim_handle, {"null": mock.Mock()})
        sink = mock.Mock()
        sink.supports_progress.return_value = True
        sink.begin_run.side_effect = EleanorError("no order 999 to extend")

        built: list[SimpleNamespace] = []

        def build(manager, out_channels=()):
            pump = progress(manager, out_channels)
            built.append(pump)
            return pump

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.Manager", return_value=mock.Mock()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            mock.patch("eleanor.eleanor.Progress", side_effect=build),
            self.assertRaisesRegex(EleanorError, "no order 999 to extend"),
        ):
            _ = eleanor.run(
                _make_order(),
                3,
                kernel=mock.MagicMock(AbstractKernel),
                navigator=_navigator(3),
                show_progress=True,
                resume_id="999",
            )

        self.assertEqual(len(built), 1, "the pump must have been constructed for this to be a real test")
        built[0].join.assert_called_once()

    def test_run_constructs_out_handle_only_when_sink_supports_progress(self) -> None:
        """Ensure process gets out_progress only for sinks that opt into progress."""
        eleanor = _make_eleanor()
        kernel = mock.MagicMock(AbstractKernel)
        navigator = _navigator(3)
        executor = _FakeExecutor()
        manager = mock.Mock()

        sim_handle_quiet = mock.Mock(name="sim_handle_quiet")
        out_handle_quiet = mock.Mock(name="out_handle_quiet")
        progress_quiet = _progress_factory(sim_handle_quiet, {"null": out_handle_quiet})
        quiet_sink = mock.Mock()
        quiet_sink.begin_run.return_value = 5
        quiet_sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value={})

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=executor),
            mock.patch("eleanor.eleanor.Manager", return_value=manager),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=quiet_sink),
            mock.patch("eleanor.eleanor.Progress", side_effect=progress_quiet),
        ):
            _ = eleanor.run(
                _make_order(), 3, kernel=kernel, navigator=navigator, show_progress=True
            )

        # A sink that declines progress is never declared as a channel, so no
        # bar is created for it and it gets no handle.
        kwargs = eleanor.process.call_args.kwargs
        self.assertIs(kwargs["sim_progress"], sim_handle_quiet)
        self.assertEqual(kwargs["out_progress"], {})

        sim_handle_loud = mock.Mock(name="sim_handle_loud")
        out_handle_loud = mock.Mock(name="out_handle_loud")
        progress_loud = _progress_factory(sim_handle_loud, {"null": out_handle_loud})
        loud_sink = mock.Mock()
        loud_sink.begin_run.return_value = 6
        loud_sink.supports_progress.return_value = True
        eleanor.process = mock.Mock(return_value={})

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=executor),
            mock.patch("eleanor.eleanor.Manager", return_value=manager),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=loud_sink),
            mock.patch("eleanor.eleanor.Progress", side_effect=progress_loud),
        ):
            _ = eleanor.run(
                _make_order(), 3, kernel=kernel, navigator=navigator, show_progress=True
            )

        kwargs = eleanor.process.call_args.kwargs
        self.assertIs(kwargs["sim_progress"], sim_handle_loud)
        self.assertEqual(kwargs["out_progress"], {"null": out_handle_loud})

    def test_run_closes_progress_handles_when_process_raises(self) -> None:
        """Ensure progress handles are closed/joined even if process raises."""
        eleanor = _make_eleanor()
        sim_handle = mock.Mock(name="sim_handle")
        out_handle = mock.Mock(name="out_handle")
        progress = SimpleNamespace(
            sim=sim_handle,
            outs=lambda: {"null": out_handle},
            join=mock.Mock(),
        )
        sink = mock.Mock()
        sink.begin_run.return_value = 8
        sink.supports_progress.return_value = True
        eleanor.process = mock.Mock(side_effect=RuntimeError("boom"))

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
            self.assertRaises(RuntimeError),
        ):
            _ = eleanor.run(
                _make_order(),
                1,
                kernel=kernel,
                navigator=_navigator(1),
                show_progress=True,
            )

        sim_handle.done.assert_called_once_with()
        out_handle.done.assert_called_once_with()
        progress.join.assert_called_once_with()

    def test_batch_size_threads_from_run_to_process(self) -> None:
        """Ensure run(..., batch_size=50) threads the value to process()."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value={})

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            _ = eleanor.run(
                _make_order(),
                10,
                batch_size=50,
                kernel=kernel,
                navigator=_navigator(50),
            )

        self.assertEqual(eleanor.process.call_args.kwargs["batch_size"], 50)

    def test_batch_size_defaults_to_num_systems(self) -> None:
        """Ensure run() defaults batch_size to navigator.num_systems(simulation_size)."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.begin_run.return_value = 9
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value={})

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            _ = eleanor.run(_make_order(), 3, kernel=kernel, navigator=_navigator(7))

        self.assertEqual(eleanor.process.call_args.kwargs["batch_size"], 7)

    def test_max_nav_attempts_threads_from_run_to_process(self) -> None:
        """Ensure run(..., max_nav_attempts=4) threads the value to process()."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.begin_run.return_value = 9
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value={})

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            _ = eleanor.run(
                _make_order(),
                3,
                max_nav_attempts=4,
                kernel=kernel,
                navigator=_navigator(7),
            )

        self.assertEqual(eleanor.process.call_args.kwargs["max_nav_attempts"], 4)

    def test_run_raises_when_explicit_max_nav_attempts_is_zero(self) -> None:
        """Ensure run() validates max_nav_attempts >= 1."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.supports_progress.return_value = False

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            self.assertRaisesRegex(EleanorError, "max_nav_attempts must be >= 1"),
        ):
            _ = eleanor.run(
                _make_order(),
                10,
                kernel=kernel,
                navigator=_navigator(5),
                max_nav_attempts=0,
            )

    def test_run_uses_explicit_output_sink_override(self) -> None:
        """Ensure output_sink= overrides config sink; caller retains lifecycle ownership."""
        eleanor = _make_eleanor()
        provided_sink = mock.Mock()
        provided_sink.begin_run.return_value = 7
        provided_sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value={})

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink") as load_sink,
        ):
            out = eleanor.run(
                _make_order(),
                1,
                output_sink=provided_sink,
                kernel=kernel,
                navigator=_navigator(1),
            )

        self.assertEqual(out, {"output": 7})
        load_sink.assert_not_called()
        provided_sink.initialize.assert_not_called()
        provided_sink.finalize.assert_not_called()
        provided_sink.finalize_run.assert_called_once()

    def test_run_finalizes_sink_on_shutdown(self) -> None:
        """Ensure run() finalizes sink state when process() raises EleanorShutdown."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(side_effect=EleanorShutdown("SIGTERM"))

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            self.assertRaises(EleanorShutdown),
        ):
            _ = eleanor.run(_make_order(), 5, kernel=kernel, navigator=_navigator(1))

        sink.finalize_run.assert_called_once_with()
        sink.finalize.assert_called_once_with()


class TestEleanorProcess(TestCase):
    """Tests covering ``Eleanor.process`` behavior."""

    def test_process_requires_executor(self) -> None:
        """Ensure process raises if no process executor is provided."""
        eleanor = _make_eleanor()
        order = _make_order()
        sink = mock.Mock()
        with self.assertRaises(EleanorError):
            _ = eleanor.process(
                order,
                mock.Mock(),
                mock.Mock(),
                1,
                1,
                batch_size=1,
                expected_total=1,
                executor=None,
            )

    def test_process_batches_for_serial_sinks(self) -> None:
        """Ensure process streams serial-sink writes per resolved worker batch."""
        eleanor = _make_eleanor()
        order = _make_order()
        kernel = mock.MagicMock(AbstractKernel)
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a", "b"]])
        compute_results_a = [ComputeResult(point=_point(exit_code=0))]
        compute_results_b = [ComputeResult(point=_point(exit_code=0))]
        executor = _FakeExecutor(
            submit_side_effect=[_Future(compute_results_a), _Future(compute_results_b)],
        )
        sim_progress = mock.Mock()
        out_progress = mock.Mock()
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = False
        # Explicit: a bare Mock returns a truthy attribute, which would
        # silently route these through the background writer.
        sink.supports_background_commit.return_value = False
        sink.commit_batch.side_effect = [
            [WriteOutcome(exit_code=0, committed=True)],
            [WriteOutcome(exit_code=0, committed=True)],
        ]

        _ = eleanor.process(
            order,
            kernel,
            navigator,
            2,
            [_bind(sink)],
            batch_size=2,
            max_nav_attempts=3,
            expected_total=2,
            executor=_as_executor(executor),
            sim_progress=sim_progress,
            out_progress={"output": out_progress},
        )
        navigator.navigate.assert_called_once_with(
            order, kernel, 2, 2, max_attempts=3
        )
        self.assertEqual(executor.submit.call_count, 2)
        self.assertEqual(
            sink.commit_batch.call_args_list,
            [
                mock.call(9, compute_results_a, progress=out_progress),
                mock.call(9, compute_results_b, progress=out_progress),
            ],
        )

    def test_process_respects_executor_completion_order_for_serial_sinks(self) -> None:
        """Ensure process drains futures in executor-selected completion order."""
        eleanor = _make_eleanor()
        order = _make_order()
        kernel = mock.MagicMock(AbstractKernel)
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a", "b"]])

        compute_results_a = [ComputeResult(point=_point(exit_code=0, label="a"))]
        compute_results_b = [ComputeResult(point=_point(exit_code=0, label="b"))]
        executor = _FakeExecutor(
            submit_side_effect=[_Future(compute_results_a), _Future(compute_results_b)],
        )

        def _pop_last(futures: list[object]) -> object:
            return futures.pop()

        executor.pop_completed_future = mock.Mock(side_effect=_pop_last)

        sink = mock.Mock()
        sink.supports_worker_commit.return_value = False
        # Explicit: a bare Mock returns a truthy attribute, which would
        # silently route these through the background writer.
        sink.supports_background_commit.return_value = False
        sink.commit_batch.side_effect = [
            [WriteOutcome(exit_code=0, committed=True)],
            [WriteOutcome(exit_code=0, committed=True)],
        ]
        out_progress = mock.Mock()

        _ = eleanor.process(
            order,
            kernel,
            navigator,
            2,
            [_bind(sink)],
            batch_size=2,
            expected_total=2,
            executor=_as_executor(executor),
            out_progress={"output": out_progress},
        )

        self.assertEqual(
            [call.args[1] for call in sink.commit_batch.call_args_list],
            [compute_results_b, compute_results_a],
        )

    def test_process_forwards_sink_to_workers_when_opted_in(self) -> None:
        """Ensure process routes writes through workers when sink opts in."""
        eleanor = _make_eleanor()
        order = _make_order()
        kernel = mock.MagicMock(AbstractKernel)
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a", "b"]])

        worker_outcomes = [
            WriteOutcome(exit_code=0, committed=True),
            WriteOutcome(exit_code=0, committed=True),
        ]
        executor = _FakeExecutor(
            submit_side_effect=[_Future(worker_outcomes), _Future([])],
        )
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = True
        sim_progress = mock.Mock()
        out_progress = mock.Mock()

        _ = eleanor.process(
            order,
            kernel,
            navigator,
            2,
            [_bind(sink)],
            batch_size=2,
            expected_total=2,
            executor=_as_executor(executor),
            sim_progress=sim_progress,
            out_progress={"output": out_progress},
        )

        submit_kwargs = executor.submit.call_args_list[0].kwargs
        binding = submit_kwargs["bindings"][0]
        self.assertIs(binding.sink, sink)
        self.assertEqual(binding.order_id, 9)
        self.assertTrue(binding.commit_in_worker)
        self.assertIs(submit_kwargs["sim_progress"], sim_progress)
        self.assertEqual(submit_kwargs["out_progress"], {"output": out_progress})

    def test_process_falls_back_to_batch_ticks_when_executor_cannot_carry_progress(
        self,
    ) -> None:
        """Ensure coarse batch ticks are emitted when worker progress is unavailable."""
        eleanor = _make_eleanor()
        order = _make_order()
        kernel = mock.MagicMock(AbstractKernel)
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a", "b"]])

        worker_outcomes = [
            WriteOutcome(exit_code=0, committed=True),
            WriteOutcome(exit_code=1, committed=True),
        ]
        executor = _FakeExecutor(
            num_workers=1,
            submit_side_effect=[_Future(worker_outcomes)],
        )
        executor.supports_worker_progress = False

        sink = mock.Mock()
        sink.supports_worker_commit.return_value = True
        sim_progress = mock.Mock()
        out_progress = mock.Mock()

        _ = eleanor.process(
            order,
            kernel,
            navigator,
            2,
            [_bind(sink)],
            batch_size=2,
            expected_total=2,
            executor=_as_executor(executor),
            sim_progress=sim_progress,
            out_progress={"output": out_progress},
        )

        submit_kwargs = executor.submit.call_args_list[0].kwargs
        self.assertIsNone(submit_kwargs["sim_progress"])
        self.assertIsNone(submit_kwargs["out_progress"])
        sim_progress.tick.assert_called_once_with(2)
        out_progress.tick.assert_called_once_with(1)

    def test_process_raises_on_navigator_underproduction(self) -> None:
        """Ensure process raises when navigator yields fewer points than expected."""
        eleanor = _make_eleanor()
        order = _make_order()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([])
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = False
        # Explicit: a bare Mock returns a truthy attribute, which would
        # silently route these through the background writer.
        sink.supports_background_commit.return_value = False

        with self.assertRaisesRegex(EleanorError, "expected 10"):
            _ = eleanor.process(
                order,
                mock.Mock(),
                navigator,
                10,
                [_bind(sink)],
                batch_size=5,
                expected_total=10,
                executor=_as_executor(_FakeExecutor()),
            )

    def test_process_raises_on_navigator_overproduction(self) -> None:
        """Ensure process raises when navigator yields more points than expected."""
        eleanor = _make_eleanor()
        order = _make_order()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a"] * 7])
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = False
        # Explicit: a bare Mock returns a truthy attribute, which would
        # silently route these through the background writer.
        sink.supports_background_commit.return_value = False
        executor = _FakeExecutor(num_workers=1, submit_side_effect=[_Future([])])

        with self.assertRaisesRegex(EleanorError, "expected 5"):
            _ = eleanor.process(
                order,
                mock.Mock(),
                navigator,
                5,
                [_bind(sink)],
                batch_size=7,
                expected_total=5,
                executor=_as_executor(executor),
            )

    def test_process_terminates_executor_on_interrupt(self) -> None:
        """Ensure process terminates the executor immediately when interrupted."""
        eleanor = _make_eleanor()
        order = _make_order()
        kernel = mock.MagicMock(AbstractKernel)
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a"]])
        executor = _FakeExecutor(submit_side_effect=[_Future([])])
        executor.pop_completed_future = mock.Mock(side_effect=KeyboardInterrupt)
        shutdown = SimpleNamespace(requested=False, signal_name=None)
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = False
        # Explicit: a bare Mock returns a truthy attribute, which would
        # silently route these through the background writer.
        sink.supports_background_commit.return_value = False

        with (
            mock.patch(
                "eleanor.eleanor.shutdown_on_signal",
                return_value=_shutdown_with_state(shutdown),
            ),
            self.assertRaises(EleanorShutdown),
        ):
            _ = eleanor.process(
                order,
                kernel,
                navigator,
                1,
                [_bind(sink)],
                batch_size=1,
                expected_total=1,
                executor=_as_executor(executor),
            )

        executor.shutdown.assert_called_once_with(wait=False)

    def test_process_shutdown_carries_signal_name(self) -> None:
        """Ensure EleanorShutdown preserves the recorded signal name."""
        eleanor = _make_eleanor()
        order = _make_order()
        kernel = mock.MagicMock(AbstractKernel)
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a"]])
        executor = _FakeExecutor(submit_side_effect=[_Future([])])
        executor.pop_completed_future = mock.Mock(side_effect=KeyboardInterrupt)
        shutdown = SimpleNamespace(requested=True, signal_name="SIGTERM")
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = False
        # Explicit: a bare Mock returns a truthy attribute, which would
        # silently route these through the background writer.
        sink.supports_background_commit.return_value = False

        with (
            mock.patch(
                "eleanor.eleanor.shutdown_on_signal",
                return_value=_shutdown_with_state(shutdown),
            ),
            self.assertRaises(EleanorShutdown) as raised,
        ):
            _ = eleanor.process(
                order,
                kernel,
                navigator,
                1,
                [_bind(sink)],
                batch_size=1,
                expected_total=1,
                executor=_as_executor(executor),
            )

        self.assertEqual(raised.exception.signal_name, "SIGTERM")

    def test_process_skips_total_check_on_shutdown(self) -> None:
        """Ensure interrupt-driven shutdown bypasses navigator total-mismatch validation."""
        eleanor = _make_eleanor()
        order = _make_order()
        navigator = mock.Mock()
        navigator.navigate.side_effect = KeyboardInterrupt
        shutdown = SimpleNamespace(requested=True, signal_name="SIGTERM")
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = False
        # Explicit: a bare Mock returns a truthy attribute, which would
        # silently route these through the background writer.
        sink.supports_background_commit.return_value = False

        with (
            mock.patch(
                "eleanor.eleanor.shutdown_on_signal",
                return_value=_shutdown_with_state(shutdown),
            ),
            self.assertRaises(EleanorShutdown) as raised,
        ):
            _ = eleanor.process(
                order,
                mock.Mock(),
                navigator,
                10,
                [_bind(sink)],
                batch_size=5,
                expected_total=10,
                executor=_as_executor(_FakeExecutor()),
            )

        self.assertEqual(raised.exception.signal_name, "SIGTERM")


class TestEleanorConstructorOverrides(TestCase):
    """Tests covering constructor-level executor/output sink overrides."""

    def test_constructor_executor_used_for_all_runs_in_session(self) -> None:
        """Ensure constructor executor override is reused across runs."""
        eleanor = _make_eleanor()
        ctor_executor = _FakeExecutor()
        eleanor._executor_override = ctor_executor

        seen_executors = []

        def process(*_args, **kwargs):
            seen_executors.append(kwargs["executor"])
            return {}

        eleanor.process = mock.Mock(side_effect=process)
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor") as load_executor,
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            with eleanor:
                _ = eleanor.run(
                    _make_order(), 5, kernel=kernel, navigator=_navigator(1)
                )
                _ = eleanor.run(
                    _make_order(), 5, kernel=kernel, navigator=_navigator(1)
                )

        load_executor.assert_not_called()
        self.assertEqual(len(seen_executors), 2)
        self.assertIs(seen_executors[0], ctor_executor)
        self.assertIs(seen_executors[1], ctor_executor)

    def test_unentered_executor_override_not_entered_or_shut_down_by_eleanor(
        self,
    ) -> None:
        """Ensure Eleanor does not manage lifecycle of caller-owned executor override."""
        eleanor = _make_eleanor()
        ctor_executor = _FakeExecutor()
        eleanor._executor_override = ctor_executor
        eleanor.process = mock.Mock(return_value={})
        sink = mock.Mock()
        sink.begin_run.return_value = 1
        sink.supports_progress.return_value = False

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor"),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            with eleanor:
                self.assertEqual(ctor_executor.enter_count, 0)
                _ = eleanor.run(
                    _make_order(), 1, kernel=kernel, navigator=_navigator(1)
                )
                self.assertEqual(ctor_executor.enter_count, 0)

        ctor_executor.shutdown.assert_not_called()

    def test_caller_entered_executor_not_shut_down_by_eleanor(self) -> None:
        """Ensure Eleanor does not shut down pre-entered executor overrides."""
        eleanor = _make_eleanor()
        ctor_executor = _FakeExecutor()
        _ = ctor_executor.__enter__()
        eleanor._executor_override = ctor_executor
        eleanor.process = mock.Mock(return_value={})
        sink = mock.Mock()
        sink.begin_run.return_value = 1
        sink.supports_progress.return_value = False

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor"),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            with eleanor:
                _ = eleanor.run(
                    _make_order(), 1, kernel=kernel, navigator=_navigator(1)
                )
                self.assertEqual(ctor_executor.enter_count, 1)

        ctor_executor.shutdown.assert_not_called()

    def test_constructor_output_sink_used_for_all_runs_in_session(self) -> None:
        """Ensure constructor output sink override is reused across runs."""
        eleanor = _make_eleanor()
        ctor_sink = mock.Mock()
        ctor_sink.begin_run.return_value = 7
        ctor_sink.supports_progress.return_value = False
        eleanor._output_sink_override = {"ctor": ctor_sink}
        eleanor.process = mock.Mock(return_value={})

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink") as load_sink,
        ):
            with eleanor:
                _ = eleanor.run(
                    _make_order(), 5, kernel=kernel, navigator=_navigator(1)
                )
                _ = eleanor.run(
                    _make_order(), 5, kernel=kernel, navigator=_navigator(1)
                )

        load_sink.assert_not_called()
        self.assertEqual(ctor_sink.begin_run.call_count, 2)

    def test_constructor_output_sink_not_finalized_at_exit(self) -> None:
        """Ensure constructor output sink is not finalize()-d by Eleanor."""
        eleanor = _make_eleanor()
        ctor_sink = mock.Mock()
        ctor_sink.begin_run.return_value = 3
        ctor_sink.supports_progress.return_value = False
        eleanor._output_sink_override = {"ctor": ctor_sink}
        eleanor.process = mock.Mock(return_value={})

        kernel = mock.MagicMock(AbstractKernel)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink"),
        ):
            with eleanor:
                _ = eleanor.run(
                    _make_order(), 1, kernel=kernel, navigator=_navigator(1)
                )

        ctor_sink.finalize.assert_not_called()

    def test_per_run_output_sink_overrides_constructor_output_sink(self) -> None:
        """Ensure per-run output_sink= wins over constructor override; caller retains lifecycle."""
        eleanor = _make_eleanor()
        ctor_sink = mock.Mock()
        per_run_sink = mock.Mock()
        per_run_sink.begin_run.return_value = 5
        per_run_sink.supports_progress.return_value = False
        eleanor._output_sink_override = {"ctor": ctor_sink}
        eleanor.process = mock.Mock(return_value={})

        kernel = mock.MagicMock(AbstractKernel)

        with mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()):
            _ = eleanor.run(
                _make_order(),
                1,
                output_sink=per_run_sink,
                kernel=kernel,
                navigator=_navigator(1),
            )

        per_run_sink.initialize.assert_not_called()
        per_run_sink.finalize.assert_not_called()
        per_run_sink.finalize_run.assert_called_once()
        ctor_sink.finalize.assert_not_called()


class TestEleanorProcessTimings(TestCase):
    """Tests covering the ``DispatchTimings`` wiring in ``Eleanor.process``."""

    @staticmethod
    def _serial_sink() -> mock.Mock:
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = False
        # Explicit: a bare Mock returns a truthy attribute, which would
        # silently route these through the background writer.
        sink.supports_background_commit.return_value = False
        sink.prepare_batch.side_effect = lambda _order_id, results: results
        sink.commit_batch.side_effect = lambda _order_id, prepared, **_kwargs: [
            WriteOutcome(exit_code=0, committed=True) for _ in prepared
        ]
        return sink

    def test_process_counts_chunks_and_points_for_serial_sinks(self) -> None:
        """Ensure every submitted chunk and point is counted."""
        eleanor = _make_eleanor()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a", "b", "c", "d"]])
        results = [ComputeResult(point=_point(exit_code=0))]
        executor = _FakeExecutor(
            submit_side_effect=[_Future(results) for _ in range(4)],
        )
        timings = DispatchTimings(enabled=True)

        _ = eleanor.process(
            _make_order(),
            mock.MagicMock(AbstractKernel),
            navigator,
            4,
            [_bind(self._serial_sink())],
            batch_size=4,
            expected_total=4,
            executor=_as_executor(executor),
            chunks_per_worker=2,
            timings=timings,
        )

        # 4 points split across num_workers(2) * chunks_per_worker(2) chunks.
        self.assertEqual(timings.chunks, 4)
        self.assertEqual(timings.points, 4)

    def test_process_counts_chunks_and_points_for_worker_write_sinks(self) -> None:
        """Ensure the worker-writes branch is instrumented too."""
        eleanor = _make_eleanor()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a", "b"]])
        outcomes = [WriteOutcome(exit_code=0, committed=True)]
        executor = _FakeExecutor(
            submit_side_effect=[_Future(outcomes), _Future(outcomes)],
        )
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = True
        timings = DispatchTimings(enabled=True)

        _ = eleanor.process(
            _make_order(),
            mock.MagicMock(AbstractKernel),
            navigator,
            2,
            [_bind(sink)],
            batch_size=2,
            expected_total=2,
            executor=_as_executor(executor),
            timings=timings,
        )

        self.assertEqual(timings.chunks, 2)
        self.assertEqual(timings.points, 2)

    def test_process_attributes_navigator_generation_time(self) -> None:
        """Ensure time spent pulling navigator batches lands in generate_s."""
        eleanor = _make_eleanor()
        clock = _StepClock()

        def _navigate(*_args: object, **_kwargs: object):
            clock.advance(5.0)
            yield ["a"]

        navigator = mock.Mock()
        navigator.navigate.side_effect = _navigate
        executor = _FakeExecutor(
            submit_side_effect=[_Future([ComputeResult(point=_point(exit_code=0))])],
        )
        timings = DispatchTimings(enabled=True)

        with mock.patch.object(timing_mod.time, "perf_counter", clock):
            _ = eleanor.process(
                _make_order(),
                mock.MagicMock(AbstractKernel),
                navigator,
                1,
                [_bind(self._serial_sink())],
                batch_size=1,
                expected_total=1,
                executor=_as_executor(executor),
                timings=timings,
            )

        self.assertEqual(timings.generate_s, 5.0)

    def test_process_attributes_sink_write_time(self) -> None:
        """Ensure serial-sink write time lands in write_s, not wait_s."""
        eleanor = _make_eleanor()
        clock = _StepClock()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a"]])
        executor = _FakeExecutor(
            submit_side_effect=[_Future([ComputeResult(point=_point(exit_code=0))])],
        )
        sink = self._serial_sink()

        def _slow_write(_order_id: object, results: list[object], **_kwargs: object):
            clock.advance(7.0)
            return [WriteOutcome(exit_code=0, committed=True) for _ in results]

        sink.commit_batch.side_effect = _slow_write
        timings = DispatchTimings(enabled=True)

        with mock.patch.object(timing_mod.time, "perf_counter", clock):
            _ = eleanor.process(
                _make_order(),
                mock.MagicMock(AbstractKernel),
                navigator,
                1,
                [_bind(sink)],
                batch_size=1,
                expected_total=1,
                executor=_as_executor(executor),
                timings=timings,
            )

        self.assertEqual(timings.write_s, 7.0)
        self.assertEqual(timings.wait_s, 0.0)
        # One chunk, two workers: the pool is provably short of work for the
        # whole write, so the stall is charged as starvation.
        self.assertEqual(timings.starved_s, 7.0)

    def test_process_charges_tail_of_drain_as_starved(self) -> None:
        """Ensure a drain with fewer chunks outstanding than workers is charged.

        With two workers and two chunks, the first ``pop`` is fully
        subscribed and the second is not, so only the second wait is charged.
        """
        eleanor = _make_eleanor()
        clock = _StepClock()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a", "b"]])
        results = [ComputeResult(point=_point(exit_code=0))]
        executor = _FakeExecutor(
            submit_side_effect=[_Future(results), _Future(results)],
        )

        def _slow_pop(futures: list[object]) -> object:
            clock.advance(1.0)
            return futures.pop(0)

        executor.pop_completed_future = mock.Mock(side_effect=_slow_pop)
        timings = DispatchTimings(enabled=True)

        with mock.patch.object(timing_mod.time, "perf_counter", clock):
            _ = eleanor.process(
                _make_order(),
                mock.MagicMock(AbstractKernel),
                navigator,
                2,
                [_bind(self._serial_sink())],
                batch_size=2,
                expected_total=2,
                executor=_as_executor(executor),
                chunks_per_worker=1,
                timings=timings,
            )

        self.assertEqual(executor.num_workers, 2)
        self.assertEqual(timings.wait_s, 2.0)
        self.assertEqual(timings.starved_s, 1.0)

    def test_process_builds_its_own_timings_when_none_supplied(self) -> None:
        """Ensure direct callers of process() do not have to pass timings."""
        eleanor = _make_eleanor()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a"]])
        executor = _FakeExecutor(
            submit_side_effect=[_Future([ComputeResult(point=_point(exit_code=0))])],
        )

        outcomes = eleanor.process(
            _make_order(),
            mock.MagicMock(AbstractKernel),
            navigator,
            1,
            [_bind(self._serial_sink())],
            batch_size=1,
            expected_total=1,
            executor=_as_executor(executor),
            timing=True,
        )

        self.assertEqual(len(outcomes), 1)


class TestEleanorRunTimingReport(TestCase):
    """Tests covering the ``--timing`` report emitted by ``Eleanor.run``."""

    def test_run_prints_the_summary_to_stderr_when_timing_is_enabled(self) -> None:
        """Ensure the report goes to stderr so stdout stays clean."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.begin_run.return_value = 3
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value={})
        captured = io.StringIO()

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            mock.patch("eleanor.eleanor.sys.stderr", captured),
        ):
            _ = eleanor.run(
                _make_order(),
                1,
                kernel=mock.MagicMock(AbstractKernel),
                navigator=_navigator(1),
                timing=True,
            )

        self.assertIn("dispatch timings", captured.getvalue())

    def test_run_stays_quiet_when_timing_is_disabled(self) -> None:
        """Ensure the report is opt-in."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.begin_run.return_value = 3
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value={})
        captured = io.StringIO()

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            mock.patch("eleanor.eleanor.sys.stderr", captured),
        ):
            _ = eleanor.run(
                _make_order(),
                1,
                kernel=mock.MagicMock(AbstractKernel),
                navigator=_navigator(1),
            )

        self.assertEqual(captured.getvalue(), "")

    def test_run_reports_timings_even_when_process_raises(self) -> None:
        """Ensure a failed run still reports where its time went."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.begin_run.return_value = 3
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(side_effect=EleanorShutdown("SIGTERM"))
        captured = io.StringIO()

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            mock.patch("eleanor.eleanor.sys.stderr", captured),
            self.assertRaises(EleanorShutdown),
        ):
            _ = eleanor.run(
                _make_order(),
                1,
                kernel=mock.MagicMock(AbstractKernel),
                navigator=_navigator(1),
                timing=True,
            )

        self.assertIn("dispatch timings", captured.getvalue())


def _bind(sink: object, name: str = "output", order_id: object = 9) -> SinkBinding:
    """Bind a stand-in sink, honouring its stated commit strategy."""
    return SinkBinding(
        name=name,
        sink=cast("AbstractOutputSink[object]", sink),
        order_id=order_id,
        commit_in_worker=bool(sink.supports_worker_commit()),  # pyright: ignore[reportAttributeAccessIssue]
    )


def _chunk_result(points: object, bindings: object, payload: object) -> ChunkResult:
    """Synthesize what ``Runner.dispatch`` would have returned for a chunk.

    Worker-commit sinks come back with outcomes and no payload; the rest come
    back with the prepared payload for the parent to commit.
    """
    items = cast("list[object]", payload)
    sinks: list[SinkChunkResult] = []
    for binding in cast("list[SinkBinding]", bindings):
        if binding.commit_in_worker:
            # A fixture that already speaks in outcomes keeps them verbatim;
            # anything else stands in as one clean write per item.
            if items and all(isinstance(item, WriteOutcome) for item in items):
                outcomes = cast("list[WriteOutcome]", list(items))
            else:
                outcomes = [WriteOutcome(exit_code=0, committed=True) for _ in items]
            sinks.append(SinkChunkResult(name=binding.name, outcomes=outcomes))
        else:
            sinks.append(SinkChunkResult(name=binding.name, prepared=list(items)))
    return ChunkResult(point_count=len(cast("list[object]", points)), sinks=sinks)


class _RecordingExecutor:
    """Executor stand-in that logs the order of ``submit`` / ``pop`` calls.

    The log is what distinguishes a sliding window from a drain-all barrier:
    a barrier empties the in-flight set at every navigator batch boundary,
    whereas a window only lets it empty once the point stream is exhausted.
    """

    supports_worker_progress: bool = True

    def __init__(self, num_workers: int = 2, payload: object = None) -> None:
        self._num_workers = num_workers
        self._payload = payload if payload is not None else []
        self.log: list[str] = []
        self.chunks: list[object] = []

    @property
    def num_workers(self) -> int:
        return self._num_workers

    def submit(self, _fn, *args, **kwargs):
        self.log.append("submit")
        self.chunks.append(args[0])
        return _Future(_chunk_result(args[0], kwargs["bindings"], self._payload))

    def pop_completed_future(self, futures):
        self.log.append("pop")
        return futures.pop(0)

    def shutdown(self, wait: bool = True) -> None:
        _ = wait

    def outstanding_history(self) -> list[tuple[str, int]]:
        """Replay the log into ``(event, futures outstanding after it)`` pairs."""
        outstanding = 0
        history: list[tuple[str, int]] = []
        for event in self.log:
            outstanding += 1 if event == "submit" else -1
            history.append((event, outstanding))
        return history


def _batched_navigator(batches: list[list[str]]):
    """Navigator stand-in yielding ``batches`` and reporting their total size."""
    navigator = mock.Mock()
    navigator.num_systems.return_value = sum(len(batch) for batch in batches)
    navigator.navigate.return_value = iter(batches)
    return navigator


class TestEleanorDispatchWindow(TestCase):
    """Tests covering the sliding in-flight window in ``Eleanor.process``."""

    @staticmethod
    def _serial_sink() -> mock.Mock:
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = False
        # Explicit: a bare Mock returns a truthy attribute, which would
        # silently route these through the background writer.
        sink.supports_background_commit.return_value = False
        sink.prepare_batch.side_effect = lambda _order_id, results: results
        sink.commit_batch.side_effect = lambda _order_id, prepared, **_kwargs: [
            WriteOutcome(exit_code=0, committed=True) for _ in prepared
        ]
        return sink

    def _process(
        self,
        executor: _RecordingExecutor,
        batches: list[list[str]],
        *,
        batch_size: int,
        chunks_per_worker: int = 1,
        sink: mock.Mock | None = None,
    ) -> None:
        eleanor = _make_eleanor()
        total = sum(len(batch) for batch in batches)
        _ = eleanor.process(
            _make_order(),
            mock.MagicMock(AbstractKernel),
            _batched_navigator(batches),
            total,
            [_bind(sink if sink is not None else self._serial_sink())],
            batch_size=batch_size,
            expected_total=total,
            executor=_as_executor(executor),
            chunks_per_worker=chunks_per_worker,
        )

    def test_window_is_never_drained_to_empty_before_the_stream_ends(self) -> None:
        """Ensure work is topped up as it completes, not refilled from empty.

        This is the barrier regression test. Two navigator batches of four
        points each, a window of two chunks: under a drain-all barrier the
        outstanding count returns to zero at the batch boundary, before the
        remaining chunks are submitted.
        """
        executor = _RecordingExecutor(num_workers=2)

        self._process(
            executor,
            [["a", "b", "c", "d"], ["e", "f", "g", "h"]],
            batch_size=4,
        )

        history = executor.outstanding_history()
        last_submit = max(i for i, (event, _) in enumerate(history) if event == "submit")
        self.assertTrue(
            all(outstanding > 0 for _event, outstanding in history[:last_submit]),
            f"window emptied before the stream was exhausted: {history}",
        )

    def test_window_never_exceeds_num_workers_times_chunks_per_worker(self) -> None:
        """Ensure the window bound is respected, so memory stays bounded."""
        executor = _RecordingExecutor(num_workers=3)

        self._process(
            executor,
            [[chr(ord("a") + i) for i in range(12)]],
            batch_size=12,
            chunks_per_worker=2,
        )

        peak = max(outstanding for _event, outstanding in executor.outstanding_history())
        self.assertLessEqual(peak, 3 * 2)

    def test_chunks_cross_the_worker_boundary_as_lists(self) -> None:
        """Ensure chunks are materialised as lists, not left as tuples.

        ``itertools.batched`` yields tuples and ``Runner.dispatch`` treats any
        non-``list`` as a single point, so a tuple here would silently be
        dispatched as one point instead of several.
        """
        executor = _RecordingExecutor(num_workers=2)

        self._process(executor, [["a", "b", "c", "d"]], batch_size=4)

        self.assertTrue(executor.chunks)
        for chunk in executor.chunks:
            self.assertIsInstance(chunk, list)

    def test_chunk_sizing_matches_the_pre_window_derivation(self) -> None:
        """Ensure existing configurations keep the chunk sizes they had.

        Before the window, each navigator batch was split into exactly
        ``num_workers * chunks_per_worker`` pieces. ``chunk_size`` is derived
        to reproduce that, so tuning does not silently change meaning.
        """
        executor = _RecordingExecutor(num_workers=4)

        self._process(
            executor,
            [[chr(ord("a") + i) for i in range(16)]],
            batch_size=16,
            chunks_per_worker=2,
        )

        # 16 points / (4 workers * 2 chunks) = 2 points per chunk, 8 chunks.
        self.assertEqual([len(chunk) for chunk in executor.chunks], [2] * 8)

    def test_a_short_final_chunk_is_allowed(self) -> None:
        """Ensure a point count that is not a multiple of chunk_size is fine."""
        executor = _RecordingExecutor(num_workers=2)

        self._process(executor, [["a", "b", "c", "d", "e"]], batch_size=5)

        # ceil(5 / 2) = 3 points per chunk -> chunks of 3 and 2.
        self.assertEqual([len(chunk) for chunk in executor.chunks], [3, 2])

    def test_window_spans_navigator_batches(self) -> None:
        """Ensure chunks are cut from a flattened stream, not per batch.

        A batch smaller than one chunk used to produce an undersized chunk of
        its own; flattening lets a chunk draw points from two batches.
        """
        executor = _RecordingExecutor(num_workers=1)

        self._process(executor, [["a", "b"], ["c", "d"]], batch_size=4)

        # ceil(4 / 1) = 4 points per chunk, so all four points -- drawn from
        # both navigator batches -- land in a single chunk.
        self.assertEqual([len(chunk) for chunk in executor.chunks], [4])

    def test_worker_write_sinks_use_the_same_window(self) -> None:
        """Ensure the window serves the worker-write mode too."""
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = True
        executor = _RecordingExecutor(
            num_workers=2,
            payload=[WriteOutcome(exit_code=0, committed=True)],
        )

        self._process(
            executor,
            [["a", "b", "c", "d"], ["e", "f", "g", "h"]],
            batch_size=4,
        )

        sink.commit_batch.assert_not_called()
        history = executor.outstanding_history()
        last_submit = max(i for i, (event, _) in enumerate(history) if event == "submit")
        self.assertTrue(
            all(outstanding > 0 for _event, outstanding in history[:last_submit]),
            f"window emptied before the stream was exhausted: {history}",
        )

    def test_navigator_shortfall_is_still_detected(self) -> None:
        """Ensure the expected_total guard survives the per-chunk accounting."""
        eleanor = _make_eleanor()
        executor = _RecordingExecutor(num_workers=2)

        with self.assertRaisesRegex(EleanorError, "produced 2 points, expected 4"):
            _ = eleanor.process(
                _make_order(),
                mock.MagicMock(AbstractKernel),
                _batched_navigator([["a", "b"]]),
                4,
                [_bind(self._serial_sink())],
                batch_size=4,
                expected_total=4,
                executor=_as_executor(executor),
            )


class TestEleanorBackgroundCommit(TestCase):
    """Tests covering the background commit thread in ``Eleanor.process``."""

    @staticmethod
    def _sink(*, background: bool = True) -> mock.Mock:
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = False
        sink.supports_background_commit.return_value = background
        sink.prepare_batch.side_effect = lambda _order_id, results: results
        sink.commit_batch.side_effect = lambda _order_id, prepared, **_kwargs: [
            WriteOutcome(exit_code=0, committed=True) for _ in prepared
        ]
        return sink

    def _process(self, sink: mock.Mock, executor: _RecordingExecutor) -> list[WriteOutcome]:
        """Run one sink through ``process`` and return just its outcomes."""
        eleanor = _make_eleanor()
        outcomes = eleanor.process(
            _make_order(),
            mock.MagicMock(AbstractKernel),
            _batched_navigator([["a", "b", "c", "d"]]),
            4,
            [_bind(sink)],
            batch_size=4,
            expected_total=4,
            executor=_as_executor(executor),
        )
        return outcomes["output"]

    def test_commits_happen_off_the_dispatch_thread(self) -> None:
        """Ensure an opted-in sink is committed from the writer thread."""
        sink = self._sink()
        dispatch_thread = threading.current_thread().name
        commit_threads: list[str] = []

        def _record(_order_id, prepared, **_kwargs):
            commit_threads.append(threading.current_thread().name)
            return [WriteOutcome(exit_code=0, committed=True) for _ in prepared]

        sink.commit_batch.side_effect = _record
        executor = _RecordingExecutor(num_workers=2, payload=["x"])

        _ = self._process(sink, executor)

        self.assertTrue(commit_threads)
        for name in commit_threads:
            self.assertNotEqual(name, dispatch_thread)

    def test_a_sink_that_opts_out_is_committed_inline(self) -> None:
        """Ensure the capability is honoured, not assumed."""
        sink = self._sink(background=False)
        dispatch_thread = threading.current_thread().name
        commit_threads: list[str] = []

        def _record(_order_id, prepared, **_kwargs):
            commit_threads.append(threading.current_thread().name)
            return [WriteOutcome(exit_code=0, committed=True) for _ in prepared]

        sink.commit_batch.side_effect = _record
        executor = _RecordingExecutor(num_workers=2, payload=["x"])

        _ = self._process(sink, executor)

        self.assertTrue(commit_threads)
        for name in commit_threads:
            self.assertEqual(name, dispatch_thread)

    def test_every_outcome_is_collected_before_process_returns(self) -> None:
        """Ensure the join barrier holds, so RunStats sees the full picture.

        Without it, outcomes committed after the last chunk was popped would
        be missing from the return value.
        """
        sink = self._sink()
        executor = _RecordingExecutor(num_workers=2, payload=["x", "y"])

        outcomes = self._process(sink, executor)

        # 4 points / (2 workers * 1 chunk each) = 2 chunks, and this fake
        # executor resolves each future to a two-item prepared payload.
        self.assertEqual(len(outcomes), 4)
        self.assertTrue(all(o.committed for o in outcomes))

    def test_the_writer_is_joined_before_process_returns(self) -> None:
        """Ensure no commit is still in flight once process has returned."""
        sink = self._sink()
        in_flight = threading.Event()
        released = threading.Event()

        def _slow(_order_id, prepared, **_kwargs):
            in_flight.set()
            released.wait(timeout=5.0)
            return [WriteOutcome(exit_code=0, committed=True) for _ in prepared]

        sink.commit_batch.side_effect = _slow
        executor = _RecordingExecutor(num_workers=2, payload=["x"])
        released.set()

        _ = self._process(sink, executor)

        # A live writer thread here would mean finalize_run could race a commit.
        self.assertFalse(
            any(t.name.startswith("eleanor-writer") and t.is_alive() for t in threading.enumerate()),
            "writer thread outlived process()",
        )

    def test_a_commit_failure_propagates_out_of_process(self) -> None:
        """Ensure a threaded failure is not swallowed."""
        sink = self._sink()
        sink.commit_batch.side_effect = RuntimeError("commit exploded")
        executor = _RecordingExecutor(num_workers=2, payload=["x"])

        with self.assertRaisesRegex(RuntimeError, "commit exploded"):
            _ = self._process(sink, executor)

        self.assertFalse(
            any(t.name.startswith("eleanor-writer") and t.is_alive() for t in threading.enumerate()),
            "writer thread outlived a failed process()",
        )

    def test_a_dispatch_failure_does_not_leave_the_writer_running(self) -> None:
        """Ensure the writer is torn down when the loop fails elsewhere.

        The original exception must also survive: aborting rather than joining
        is what keeps a stashed commit error from displacing it.
        """
        sink = self._sink()
        eleanor = _make_eleanor()
        navigator = mock.Mock()
        navigator.num_systems.return_value = 4

        def _explode(*_args: object, **_kwargs: object):
            yield ["a"]
            msg = "navigator exploded"
            raise RuntimeError(msg)

        navigator.navigate.side_effect = _explode
        executor = _RecordingExecutor(num_workers=2, payload=["x"])

        with self.assertRaisesRegex(RuntimeError, "navigator exploded"):
            _ = eleanor.process(
                _make_order(),
                mock.MagicMock(AbstractKernel),
                navigator,
                4,
                [_bind(sink)],
                batch_size=4,
                expected_total=4,
                executor=_as_executor(executor),
            )

        self.assertFalse(
            any(t.name.startswith("eleanor-writer") and t.is_alive() for t in threading.enumerate()),
            "writer thread outlived a failed process()",
        )

    def test_worker_commit_sinks_get_no_writer(self) -> None:
        """Ensure the writer is not built when there is no inline commit."""
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = True
        sink.supports_background_commit.return_value = True
        executor = _RecordingExecutor(
            num_workers=2,
            payload=[WriteOutcome(exit_code=0, committed=True)],
        )

        _ = self._process(sink, executor)

        sink.commit_batch.assert_not_called()
        self.assertFalse(
            any(t.name.startswith("eleanor-writer") for t in threading.enumerate()),
            "a worker-commit sink should not get a writer thread",
        )


class TestEleanorMultipleSinks(TestCase):
    """Tests covering a run driving more than one output sink at once."""

    @staticmethod
    def _sink(*, worker_commit: bool, background: bool = False) -> mock.Mock:
        sink = mock.Mock()
        sink.supports_worker_commit.return_value = worker_commit
        sink.supports_background_commit.return_value = background
        sink.supports_progress.return_value = True
        sink.supports_resume.return_value = True
        sink.prepare_batch.side_effect = lambda _order_id, results: results
        sink.commit_batch.side_effect = lambda _order_id, prepared, **_kwargs: [
            WriteOutcome(exit_code=0, committed=True) for _ in prepared
        ]
        return sink

    def _process(self, bindings: list[SinkBinding], payload: object = None):
        eleanor = _make_eleanor()
        executor = _RecordingExecutor(num_workers=2, payload=payload or ["x", "y"])
        return eleanor.process(
            _make_order(),
            mock.MagicMock(AbstractKernel),
            _batched_navigator([["a", "b", "c", "d"]]),
            4,
            bindings,
            batch_size=4,
            expected_total=4,
            executor=_as_executor(executor),
        )

    def test_outcomes_are_keyed_per_sink(self) -> None:
        """Ensure each sink's outcomes are reported separately.

        Summing them would inflate ``RunStats.attempted`` by the sink count,
        making a healthy two-sink run look like twice the work.
        """
        outcomes = self._process(
            [
                _bind(self._sink(worker_commit=True), name="pg"),
                _bind(self._sink(worker_commit=False), name="csv"),
            ],
        )

        self.assertEqual(sorted(outcomes), ["csv", "pg"])
        self.assertEqual(len(outcomes["pg"]), 4)
        self.assertEqual(len(outcomes["csv"]), 4)

    def test_mixed_commit_strategies_are_honoured_in_one_chunk(self) -> None:
        """Ensure a worker-commit sink and a serial sink can share a run.

        The dispatch loop used to pick one strategy for the whole run from a
        single sink's answer; a chunk now has to carry both.
        """
        worker_sink = self._sink(worker_commit=True)
        serial_sink = self._sink(worker_commit=False)

        outcomes = self._process(
            [_bind(worker_sink, name="pg"), _bind(serial_sink, name="csv")],
        )

        # The worker-commit sink was committed in the worker, so the parent
        # never called it; the serial one was committed by the parent.
        worker_sink.commit_batch.assert_not_called()
        self.assertTrue(serial_sink.commit_batch.called)
        self.assertEqual(len(outcomes["pg"]), 4)
        self.assertEqual(len(outcomes["csv"]), 4)

    def test_each_sink_keeps_its_own_order_id(self) -> None:
        """Ensure ids are not shared across sinks, whatever their id space."""
        first = self._sink(worker_commit=False)
        second = self._sink(worker_commit=False)

        _ = self._process(
            [
                _bind(first, name="a", order_id=42),
                _bind(second, name="b", order_id="8f14e45f"),
            ],
        )

        self.assertEqual(first.commit_batch.call_args.args[0], 42)
        self.assertEqual(second.commit_batch.call_args.args[0], "8f14e45f")

    def test_each_background_sink_gets_its_own_writer(self) -> None:
        """Ensure serial sinks commit on separate threads.

        ``BackgroundWriter`` guarantees one thread owns its sink for the run,
        which is what lets sinks skip internal locking. Sharing a thread
        between two sinks would keep that guarantee but serialise sinks that
        have no reason to wait on each other.
        """
        threads: dict[str, set[str]] = {"a": set(), "b": set()}

        def _recorder(name: str):
            def commit(_order_id, prepared, **_kwargs):
                threads[name].add(threading.current_thread().name)
                return [WriteOutcome(exit_code=0, committed=True) for _ in prepared]

            return commit

        first = self._sink(worker_commit=False, background=True)
        second = self._sink(worker_commit=False, background=True)
        first.commit_batch.side_effect = _recorder("a")
        second.commit_batch.side_effect = _recorder("b")

        _ = self._process([_bind(first, name="a"), _bind(second, name="b")])

        self.assertEqual(len(threads["a"]), 1)
        self.assertEqual(len(threads["b"]), 1)
        self.assertNotEqual(threads["a"], threads["b"])
        dispatch_thread = threading.current_thread().name
        self.assertNotIn(dispatch_thread, threads["a"] | threads["b"])

    def test_a_failing_sink_aborts_the_run_and_stops_every_writer(self) -> None:
        """Ensure one sink's commit failure takes the whole run down cleanly.

        Continuing with the survivors would produce a run that reports success
        while one of its outputs is missing rows.
        """
        healthy = self._sink(worker_commit=False, background=True)
        broken = self._sink(worker_commit=False, background=True)
        broken.commit_batch.side_effect = RuntimeError("disk full")

        with self.assertRaisesRegex(RuntimeError, "disk full"):
            _ = self._process(
                [_bind(healthy, name="ok"), _bind(broken, name="bad")],
            )

        self.assertFalse(
            any(t.name.startswith("eleanor-writer") for t in threading.enumerate()),
            "a failed run must not leave a writer thread behind",
        )

    def test_progress_handles_are_routed_per_sink(self) -> None:
        """Ensure each sink ticks its own bar, not a shared one."""
        first = self._sink(worker_commit=False)
        second = self._sink(worker_commit=False)
        handle_a = mock.Mock()
        handle_b = mock.Mock()

        eleanor = _make_eleanor()
        executor = _RecordingExecutor(num_workers=2, payload=["x"])
        _ = eleanor.process(
            _make_order(),
            mock.MagicMock(AbstractKernel),
            _batched_navigator([["a", "b"]]),
            2,
            [_bind(first, name="a"), _bind(second, name="b")],
            batch_size=2,
            expected_total=2,
            executor=_as_executor(executor),
            out_progress={"a": handle_a, "b": handle_b},
        )

        self.assertIs(first.commit_batch.call_args.kwargs["progress"], handle_a)
        self.assertIs(second.commit_batch.call_args.kwargs["progress"], handle_b)

    def test_process_rejects_an_empty_binding_list(self) -> None:
        """Ensure a run with nothing to write to is an error, not a silent no-op."""
        eleanor = _make_eleanor()
        with self.assertRaisesRegex(EleanorError, "no output sink"):
            _ = eleanor.process(
                _make_order(),
                mock.MagicMock(AbstractKernel),
                _batched_navigator([["a"]]),
                1,
                [],
                batch_size=1,
                expected_total=1,
                executor=_as_executor(_FakeExecutor()),
            )


class TestEleanorTargetClashes(TestCase):
    """A run must refuse two sinks pointed at one store.

    Distinct names are not enough: nothing correlates two sinks' counters or
    buffers, so both writing to one file or one database corrupts it.
    """

    @staticmethod
    def _sinks(**targets: object) -> dict[str, mock.Mock]:
        sinks: dict[str, mock.Mock] = {}
        for name, key in targets.items():
            sink = mock.Mock()
            sink.begin_run.return_value = f"{name}-id"
            sink.supports_progress.return_value = False
            sink.supports_worker_commit.return_value = True
            sink.supports_resume.return_value = True
            sink.target_key.return_value = key
            sinks[name] = sink
        return sinks

    def _run(self, sinks: dict[str, mock.Mock]):
        eleanor = Eleanor(
            config=Config(),
            output_sink=cast("dict[str, AbstractOutputSink[object]]", sinks),
        )
        eleanor.process = mock.Mock(return_value={name: [] for name in sinks})
        with mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()):
            return eleanor.run(
                _make_order(),
                1,
                kernel=mock.MagicMock(AbstractKernel),
                navigator=_navigator(1),
            )

    def test_two_sinks_on_one_target_are_refused(self) -> None:
        """Ensure the clash is caught before either sink begins a run."""
        sinks = self._sinks(first="/tmp/rows.csv", second="/tmp/rows.csv")

        with self.assertRaisesRegex(EleanorError, "'first' and 'second' both write to /tmp/rows.csv"):
            _ = self._run(sinks)

        for sink in sinks.values():
            sink.begin_run.assert_not_called()

    def test_distinct_targets_are_allowed(self) -> None:
        """Ensure the check does not fire on the configuration it exists to enable."""
        ids = self._run(self._sinks(first="/tmp/a.csv", second="/tmp/b.csv"))

        self.assertEqual(sorted(ids), ["first", "second"])

    def test_sinks_that_opt_out_never_collide(self) -> None:
        """Ensure ``None`` means "no exclusive target" rather than one shared one.

        Every sink predating this method returns ``None``, so treating that as
        a target would reject every multi-sink run there is.
        """
        ids = self._run(self._sinks(first=None, second=None))

        self.assertEqual(sorted(ids), ["first", "second"])


class TestEleanorResumeRouting(TestCase):
    """Tests covering how ``resume_id`` is resolved against the active sinks."""

    @staticmethod
    def _sinks(**resumable: bool) -> dict[str, mock.Mock]:
        sinks: dict[str, mock.Mock] = {}
        for name, can_resume in resumable.items():
            sink = mock.Mock()
            sink.begin_run.return_value = f"{name}-id"
            sink.supports_progress.return_value = False
            sink.supports_worker_commit.return_value = True
            sink.supports_resume.return_value = can_resume
            sinks[name] = sink
        return sinks

    def _run(self, sinks: dict[str, mock.Mock], resume_id: object = None):
        eleanor = Eleanor(
            config=Config(),
            output_sink=cast("dict[str, AbstractOutputSink[object]]", sinks),
        )
        eleanor.process = mock.Mock(return_value={name: [] for name in sinks})
        with mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()):
            return eleanor.run(
                _make_order(),
                1,
                kernel=mock.MagicMock(AbstractKernel),
                navigator=_navigator(1),
                resume_id=cast("str | None", resume_id),
            )

    def test_tokens_are_routed_to_their_named_sink(self) -> None:
        """Ensure each sink is handed only its own token, verbatim."""
        sinks = self._sinks(pg=True, csv=True)

        _ = self._run(sinks, {"pg": "42", "csv": "8f14e45f"})

        self.assertEqual(sinks["pg"].begin_run.call_args.kwargs["requested_id"], "42")
        self.assertEqual(
            sinks["csv"].begin_run.call_args.kwargs["requested_id"], "8f14e45f"
        )

    def test_a_bare_token_is_accepted_for_a_lone_sink(self) -> None:
        """Ensure the pre-existing single-sink invocation keeps working."""
        sinks = self._sinks(pg=True)

        _ = self._run(sinks, "42")

        self.assertEqual(sinks["pg"].begin_run.call_args.kwargs["requested_id"], "42")

    def test_a_bare_token_is_ambiguous_with_several_sinks(self) -> None:
        """Ensure a bare token is refused rather than guessed at.

        The id spaces differ per sink, so there is nothing to infer from.
        """
        with self.assertRaisesRegex(EleanorError, "bare resume id is ambiguous"):
            _ = self._run(self._sinks(pg=True, csv=True), "42")

    def test_a_missing_token_for_a_resumable_sink_is_an_error(self) -> None:
        """Ensure a partial resume is refused, naming what is missing.

        Silently starting the unnamed sink fresh would split one run's output
        across two ids with nothing recording that they differ.
        """
        with self.assertRaisesRegex(EleanorError, "missing: csv"):
            _ = self._run(self._sinks(pg=True, csv=True), {"pg": "42"})

    def test_a_sink_that_cannot_resume_needs_no_token(self) -> None:
        """Ensure ``supports_resume() is False`` exempts a sink.

        A live-plot sink retains nothing for a token to name; demanding one
        would make resume unusable alongside it.
        """
        sinks = self._sinks(pg=True, plot=False)

        _ = self._run(sinks, {"pg": "42"})

        self.assertEqual(sinks["pg"].begin_run.call_args.kwargs["requested_id"], "42")
        self.assertIsNone(sinks["plot"].begin_run.call_args.kwargs["requested_id"])

    def test_a_token_aimed_at_a_sink_that_cannot_resume_is_an_error(self) -> None:
        """Ensure a token is refused rather than handed to a sink that declined.

        ``supports_resume() is False`` promises the sink never sees a
        ``requested_id``; forwarding one anyway would make every such sink
        handle a token it already said it cannot interpret.
        """
        sinks = self._sinks(pg=True, plot=False)

        with self.assertRaisesRegex(EleanorError, "cannot resume: plot"):
            _ = self._run(sinks, {"pg": "42", "plot": "7"})

        sinks["pg"].begin_run.assert_not_called()

    def test_a_bare_token_for_a_lone_sink_that_cannot_resume_is_an_error(self) -> None:
        """Ensure the single-sink shorthand is checked too, not just the mapping."""
        with self.assertRaisesRegex(EleanorError, "cannot resume: plot"):
            _ = self._run(self._sinks(plot=False), "42")

    def test_a_token_for_an_unknown_sink_is_an_error(self) -> None:
        """Ensure a typo'd sink name fails loudly instead of being dropped."""
        with self.assertRaisesRegex(EleanorError, "no output sink named 'typo'"):
            _ = self._run(self._sinks(pg=True), {"typo": "42"})

    def test_no_resume_id_starts_every_sink_fresh(self) -> None:
        """Ensure the default path asks no sink to resume."""
        sinks = self._sinks(pg=True, csv=True)

        _ = self._run(sinks)

        for sink in sinks.values():
            self.assertIsNone(sink.begin_run.call_args.kwargs["requested_id"])

    def test_run_returns_every_allocated_id_keyed_by_sink(self) -> None:
        """Ensure the caller can tell which id belongs to which sink."""
        ids = self._run(self._sinks(pg=True, csv=True))

        self.assertEqual(ids, {"pg": "pg-id", "csv": "csv-id"})
