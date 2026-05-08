from contextlib import contextmanager
from types import SimpleNamespace
from typing import cast, override
from unittest import mock

from eleanor.config import Config
from eleanor.eleanor import Eleanor
from eleanor.exceptions import EleanorConfigurationException, EleanorException, EleanorShutdown
from eleanor.executor import AbstractExecutor
from eleanor.kernel import load_kernel
from eleanor.order import Order
from eleanor.output import ComputeResult, OutputSink, WriteOutcome, load_output_sink
from eleanor.variable_space import Point

from .common import TestCase


class _Future:
    def __init__(self, value):
        self._value = value

    def result(self):
        return self._value

    def get(self):
        return self.result()


class _FakeExecutor:
    """Minimal ``AbstractExecutor`` stand-in with recording ``submit``/``shutdown``."""

    supports_worker_progress: bool = True

    def __init__(self, num_workers=2, submit_side_effect=None):
        self._num_workers = num_workers
        self.enter_count = 0
        self.submit = mock.Mock(side_effect=submit_side_effect or [_Future([]), _Future([])])
        self.pop_completed_future = mock.Mock(side_effect=lambda futures: futures.pop(0))
        self.shutdown = mock.Mock()

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
    fake_config = cast(
        Config,
        cast(
            object,
            SimpleNamespace(
                database="db-config",
                output=SimpleNamespace(type="postgres", args={}),
                parallel=SimpleNamespace(backend="multiprocessing", chunks_per_worker=1),
            ),
        ),
    )
    kernel_args: list[object] = ["arg1"]
    return Eleanor(fake_config, kernel_args)


def _leaf_order(navigator_type="random") -> Order:
    """Produce a minimal order-like ``SimpleNamespace`` for ``Eleanor.run``."""
    return cast(
        Order,
        cast(
            object,
            SimpleNamespace(
                navigator=SimpleNamespace(type=navigator_type, args={}),
                id=None,
            ),
        ),
    )


def _point(*, exit_code: int = 0, **kwargs: object) -> Point:
    return cast(Point, cast(object, SimpleNamespace(exit_code=exit_code, **kwargs)))


def _as_executor(executor: _FakeExecutor) -> AbstractExecutor:
    return cast(AbstractExecutor, cast(object, executor))


class _LoaderOutputConfig:
    def __init__(self, *, sink_type: str | None, args: dict[str, object]):
        self.type = sink_type
        self.args = args


class _LoaderConfig:
    def __init__(self, output: _LoaderOutputConfig):
        self.output = output


def _navigator(num_systems: int = 1):
    navigator = mock.Mock()
    navigator.num_systems.return_value = num_systems
    navigator.navigate.return_value = iter([[]])
    return navigator


@contextmanager
def _shutdown_with_state(state: SimpleNamespace):
    yield state


class TestEleanorConstruction(TestCase):
    """Tests covering ``Eleanor`` construction/session lifecycle."""

    def test_init_stashes_config_and_kernel_args(self):
        """Ensure constructor stores config, kernel_args copy, and num_procs."""
        fake_config = _make_eleanor().config
        kernel_args: list[object] = ["k"]
        eleanor = Eleanor(fake_config, kernel_args, num_procs=4)

        self.assertIs(eleanor.config, fake_config)
        self.assertEqual(eleanor.kernel_args, ["k"])
        self.assertEqual(eleanor.num_procs, 4)
        self.assertFalse(eleanor._entered)
        self.assertIsNone(eleanor._executor)
        self.assertIsNone(eleanor._manager)
        self.assertIsNone(eleanor._output_sink)

    def test_init_defensively_copies_kernel_args(self):
        """Ensure constructor copies kernel_args so caller-side mutations do not leak in."""
        fake_config = _make_eleanor().config
        kernel_args: list[object] = ["k0"]
        eleanor = Eleanor(fake_config, kernel_args)

        kernel_args.append("k1")

        self.assertEqual(eleanor.kernel_args, ["k0"])

    def test_enter_builds_executor_and_exit_tears_down_all(self):
        """Ensure __enter__/__exit__ set up and tear down session resources."""
        eleanor = _make_eleanor()
        executor = _FakeExecutor()
        manager = mock.Mock()
        sink = mock.Mock()

        with mock.patch("eleanor.eleanor.load_executor", return_value=executor) as load_executor:
            with eleanor:
                load_executor.assert_called_once_with(kind="multiprocessing", num_workers=None)
                self.assertIs(eleanor._executor, executor)
                eleanor._manager = manager
                eleanor._output_sink = sink

        sink.finalize.assert_called_once()
        manager.shutdown.assert_called_once()
        executor.shutdown.assert_called_once_with(wait=True)

    def test_run_failure_inside_with_still_tears_down_at_exit(self):
        """Ensure session resources are torn down when run() raises."""
        eleanor = _make_eleanor()
        order = _leaf_order()
        session_executor = _FakeExecutor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(side_effect=RuntimeError("dispatch failed"))

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=session_executor),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            with self.assertRaisesRegex(RuntimeError, "dispatch failed"):
                with eleanor:
                    eleanor.run(order, 5, kernel=mock.Mock(), navigator=_navigator(1))

        sink.finalize.assert_called_once()
        session_executor.shutdown.assert_called_once_with(wait=True)

    def test_run_still_tears_down_executor_and_manager_when_sink_finalize_fails(self):
        """Ensure per-run teardown still closes manager/executor if sink.finalize() raises."""
        eleanor = _make_eleanor()
        order = _leaf_order()
        executor = _FakeExecutor()
        manager = mock.Mock()
        sim_handle = mock.Mock()
        progress = SimpleNamespace(sim=sim_handle, out=mock.Mock(), join=mock.Mock())
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        sink.finalize.side_effect = RuntimeError("sink finalize failed")
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=executor),
            mock.patch("eleanor.eleanor.Manager", return_value=manager),
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            self.assertRaisesRegex(RuntimeError, "sink finalize failed"),
        ):
            eleanor.run(order, 5, kernel=mock.Mock(), navigator=_navigator(1), show_progress=True)

        manager.shutdown.assert_called_once()
        executor.shutdown.assert_called_once_with(wait=True)


class TestEleanorRun(TestCase):
    """Tests covering ``Eleanor.run`` single-order dispatch semantics."""

    def test_run_without_with_builds_and_tears_down_resources(self):
        """Ensure run() outside ``with`` builds/tears down executor and sink."""
        eleanor = _make_eleanor()
        order = _leaf_order()
        executor = _FakeExecutor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=executor) as load_executor,
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink) as load_sink,
        ):
            out = eleanor.run(order, 5, kernel=mock.Mock(), navigator=_navigator(1))

        self.assertEqual(out, [7])
        load_executor.assert_called_once_with(kind="multiprocessing", num_workers=None)
        load_sink.assert_called_once_with(eleanor.config, verbose=False)
        sink.finalize.assert_called_once()
        executor.shutdown.assert_called_once_with(wait=True)

    def test_run_inside_with_reuses_session_executor_and_defers_finalize(self):
        """Ensure runs inside a session reuse executor and defer sink finalize."""
        eleanor = _make_eleanor()
        order1 = _leaf_order()
        order2 = _leaf_order()
        session_executor = _FakeExecutor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        seen_executors = []

        def process(*_args, **kwargs):
            seen_executors.append(kwargs["executor"])
            return []

        eleanor.process = mock.Mock(side_effect=process)

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=session_executor),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            with eleanor:
                _ = eleanor.run(order1, 5, kernel=mock.Mock(), navigator=_navigator(1))
                _ = eleanor.run(order2, 5, kernel=mock.Mock(), navigator=_navigator(1))

        self.assertEqual(len(seen_executors), 2)
        self.assertIs(seen_executors[0], session_executor)
        self.assertIs(seen_executors[1], session_executor)
        sink.finalize.assert_called_once()

    def test_run_single_leaf_passes_order_with_preset_id_to_begin_run(self):
        """Ensure begin_run is called with caller-supplied order ids intact."""
        eleanor = _make_eleanor()
        order = _leaf_order()
        order.id = 99
        sink = mock.Mock()
        sink.begin_run.return_value = 99
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            _ = eleanor.run(order, 4, kernel=mock.Mock(), navigator=_navigator(1))

        sink.begin_run.assert_called_once_with(order)
        self.assertEqual(order.id, 99)

    def test_run_rejects_retired_executor_kwarg(self):
        """Ensure run() rejects the retired ``executor=`` kwarg."""
        eleanor = _make_eleanor()
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'executor'"):
            eleanor.run(_leaf_order(), 1, executor=_FakeExecutor())  # pyright: ignore[reportCallIssue]

    def test_run_rejects_retired_parallel_kwarg(self):
        """Ensure run() rejects the retired ``parallel=`` kwarg."""
        eleanor = _make_eleanor()
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'parallel'"):
            eleanor.run(_leaf_order(), 1, parallel="serial")  # pyright: ignore[reportCallIssue]

    def test_run_raises_when_num_systems_returns_zero(self):
        """Ensure run() validates navigator.num_systems >= 1."""
        eleanor = _make_eleanor()
        navigator = _navigator(0)
        sink = mock.Mock()
        sink.supports_progress.return_value = False

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            self.assertRaisesRegex(EleanorException, "num_systems.*must be >= 1"),
        ):
            eleanor.run(_leaf_order(), 10, kernel=mock.Mock(), navigator=navigator)

    def test_run_raises_when_explicit_batch_size_is_zero(self):
        """Ensure run() validates explicit batch_size >= 1."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.supports_progress.return_value = False

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            self.assertRaisesRegex(EleanorException, "batch_size must be >= 1"),
        ):
            eleanor.run(_leaf_order(), 10, kernel=mock.Mock(), navigator=_navigator(5), batch_size=0)

    def test_run_constructs_out_handle_only_when_sink_supports_progress(self):
        """Ensure process gets out_progress only for sinks that opt into progress."""
        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = _navigator(3)
        executor = _FakeExecutor()
        manager = mock.Mock()

        sim_handle_quiet = mock.Mock(name="sim_handle_quiet")
        out_handle_quiet = mock.Mock(name="out_handle_quiet")
        progress_quiet = SimpleNamespace(sim=sim_handle_quiet, out=out_handle_quiet, join=mock.Mock())
        quiet_sink = mock.Mock()
        quiet_sink.begin_run.return_value = 5
        quiet_sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=executor),
            mock.patch("eleanor.eleanor.Manager", return_value=manager),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=quiet_sink),
            mock.patch("eleanor.eleanor.Progress", return_value=progress_quiet),
        ):
            eleanor.run(_leaf_order(), 3, kernel=kernel, navigator=navigator, show_progress=True)

        kwargs = eleanor.process.call_args.kwargs
        self.assertIs(kwargs["sim_progress"], sim_handle_quiet)
        self.assertIsNone(kwargs["out_progress"])

        sim_handle_loud = mock.Mock(name="sim_handle_loud")
        out_handle_loud = mock.Mock(name="out_handle_loud")
        progress_loud = SimpleNamespace(sim=sim_handle_loud, out=out_handle_loud, join=mock.Mock())
        loud_sink = mock.Mock()
        loud_sink.begin_run.return_value = 6
        loud_sink.supports_progress.return_value = True
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=executor),
            mock.patch("eleanor.eleanor.Manager", return_value=manager),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=loud_sink),
            mock.patch("eleanor.eleanor.Progress", return_value=progress_loud),
        ):
            eleanor.run(_leaf_order(), 3, kernel=kernel, navigator=navigator, show_progress=True)

        kwargs = eleanor.process.call_args.kwargs
        self.assertIs(kwargs["sim_progress"], sim_handle_loud)
        self.assertIs(kwargs["out_progress"], out_handle_loud)

    def test_run_closes_progress_handles_when_process_raises(self):
        """Ensure progress handles are closed/joined even if process raises."""
        eleanor = _make_eleanor()
        sim_handle = mock.Mock(name="sim_handle")
        out_handle = mock.Mock(name="out_handle")
        progress = SimpleNamespace(sim=sim_handle, out=out_handle, join=mock.Mock())
        sink = mock.Mock()
        sink.begin_run.return_value = 8
        sink.supports_progress.return_value = True
        eleanor.process = mock.Mock(side_effect=RuntimeError("boom"))

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
            self.assertRaises(RuntimeError),
        ):
            eleanor.run(_leaf_order(), 1, kernel=mock.Mock(), navigator=_navigator(1), show_progress=True)

        sim_handle.done.assert_called_once_with()
        out_handle.done.assert_called_once_with()
        progress.join.assert_called_once_with()

    def test_batch_size_threads_from_run_to_process(self):
        """Ensure run(..., batch_size=50) threads the value to process()."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            _ = eleanor.run(_leaf_order(), 10, batch_size=50, kernel=mock.Mock(), navigator=_navigator(50))

        self.assertEqual(eleanor.process.call_args.kwargs["batch_size"], 50)

    def test_batch_size_defaults_to_num_systems(self):
        """Ensure run() defaults batch_size to navigator.num_systems(simulation_size)."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.begin_run.return_value = 9
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            _ = eleanor.run(_leaf_order(), 3, kernel=mock.Mock(), navigator=_navigator(7))

        self.assertEqual(eleanor.process.call_args.kwargs["batch_size"], 7)

    def test_max_nav_attempts_threads_from_run_to_process(self):
        """Ensure run(..., max_nav_attempts=4) threads the value to process()."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.begin_run.return_value = 9
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            _ = eleanor.run(_leaf_order(), 3, max_nav_attempts=4, kernel=mock.Mock(), navigator=_navigator(7))

        self.assertEqual(eleanor.process.call_args.kwargs["max_nav_attempts"], 4)

    def test_run_raises_when_explicit_max_nav_attempts_is_zero(self):
        """Ensure run() validates max_nav_attempts >= 1."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.supports_progress.return_value = False

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            self.assertRaisesRegex(EleanorException, "max_nav_attempts must be >= 1"),
        ):
            eleanor.run(_leaf_order(), 10, kernel=mock.Mock(), navigator=_navigator(5), max_nav_attempts=0)

    def test_run_uses_explicit_output_sink_override(self):
        """Ensure output_sink= overrides config sink; caller retains lifecycle ownership."""
        eleanor = _make_eleanor()
        provided_sink = mock.Mock()
        provided_sink.begin_run.return_value = 7
        provided_sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value=[])
        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink") as load_sink,
        ):
            out = eleanor.run(_leaf_order(), 1, output_sink=provided_sink, kernel=mock.Mock(), navigator=_navigator(1))

        self.assertEqual(out, [7])
        load_sink.assert_not_called()
        provided_sink.initialize.assert_not_called()
        provided_sink.finalize.assert_not_called()
        provided_sink.finalize_run.assert_called_once()

    def test_run_finalizes_sink_on_shutdown(self):
        """Ensure run() finalizes sink state when process() raises EleanorShutdown."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(side_effect=EleanorShutdown("SIGTERM"))

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
            self.assertRaises(EleanorShutdown),
        ):
            eleanor.run(_leaf_order(), 5, kernel=mock.Mock(), navigator=_navigator(1))

        sink.finalize_run.assert_called_once_with()
        sink.finalize.assert_called_once_with()


class TestEleanorProcess(TestCase):
    """Tests covering ``Eleanor.process`` behavior."""

    def test_process_requires_executor(self):
        """Ensure process raises if no process executor is provided."""
        eleanor = _make_eleanor()
        sink = mock.Mock()
        with self.assertRaises(EleanorException):
            eleanor.process(
                mock.Mock(),
                mock.Mock(),
                1,
                1,
                batch_size=1,
                expected_total=1,
                executor=None,
                sink=sink,
            )

    def test_process_batches_for_serial_sinks(self):
        """Ensure process streams serial-sink writes per resolved worker batch."""
        eleanor = _make_eleanor()
        kernel = mock.Mock()
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
        sink.supports_worker_writes.return_value = False
        sink.write_batch.side_effect = [
            [WriteOutcome(exit_code=0, committed=True)],
            [WriteOutcome(exit_code=0, committed=True)],
        ]

        eleanor.process(
            kernel,
            navigator,
            2,
            9,
            batch_size=2,
            max_nav_attempts=3,
            expected_total=2,
            executor=_as_executor(executor),
            sink=sink,
            sim_progress=sim_progress,
            out_progress=out_progress,
        )
        navigator.navigate.assert_called_once_with(2, 2, order_id=9, max_attempts=3)
        self.assertEqual(executor.submit.call_count, 2)
        self.assertEqual(
            sink.write_batch.call_args_list,
            [
                mock.call(9, compute_results_a, progress=out_progress),
                mock.call(9, compute_results_b, progress=out_progress),
            ],
        )

    def test_process_respects_executor_completion_order_for_serial_sinks(self):
        """Ensure process drains futures in executor-selected completion order."""
        eleanor = _make_eleanor()
        kernel = mock.Mock()
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
        sink.supports_worker_writes.return_value = False
        sink.write_batch.side_effect = [
            [WriteOutcome(exit_code=0, committed=True)],
            [WriteOutcome(exit_code=0, committed=True)],
        ]
        out_progress = mock.Mock()

        eleanor.process(
            kernel,
            navigator,
            2,
            9,
            batch_size=2,
            expected_total=2,
            executor=_as_executor(executor),
            sink=sink,
            out_progress=out_progress,
        )

        self.assertEqual(
            [call.args[1] for call in sink.write_batch.call_args_list],
            [compute_results_b, compute_results_a],
        )

    def test_process_forwards_sink_to_workers_when_opted_in(self):
        """Ensure process routes writes through workers when sink opts in."""
        eleanor = _make_eleanor()
        kernel = mock.Mock()
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
        sink.supports_worker_writes.return_value = True
        sim_progress = mock.Mock()
        out_progress = mock.Mock()

        eleanor.process(
            kernel,
            navigator,
            2,
            9,
            batch_size=2,
            expected_total=2,
            executor=_as_executor(executor),
            sink=sink,
            sim_progress=sim_progress,
            out_progress=out_progress,
        )

        submit_kwargs = executor.submit.call_args_list[0].kwargs
        self.assertIs(submit_kwargs["sink"], sink)
        self.assertEqual(submit_kwargs["order_id"], 9)
        self.assertIs(submit_kwargs["sim_progress"], sim_progress)
        self.assertIs(submit_kwargs["out_progress"], out_progress)

    def test_process_falls_back_to_batch_ticks_when_executor_cannot_carry_progress(self):
        """Ensure coarse batch ticks are emitted when worker progress is unavailable."""
        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a", "b"]])

        worker_outcomes = [
            WriteOutcome(exit_code=0, committed=True),
            WriteOutcome(exit_code=1, committed=True),
        ]
        executor = _FakeExecutor(
            submit_side_effect=[_Future(worker_outcomes), _Future([])],
        )
        executor.supports_worker_progress = False

        sink = mock.Mock()
        sink.supports_worker_writes.return_value = True
        sim_progress = mock.Mock()
        out_progress = mock.Mock()

        eleanor.process(
            kernel,
            navigator,
            2,
            9,
            batch_size=2,
            expected_total=2,
            executor=_as_executor(executor),
            sink=sink,
            sim_progress=sim_progress,
            out_progress=out_progress,
        )

        submit_kwargs = executor.submit.call_args_list[0].kwargs
        self.assertIsNone(submit_kwargs["sim_progress"])
        self.assertIsNone(submit_kwargs["out_progress"])
        sim_progress.tick.assert_called_once_with(2)
        out_progress.tick.assert_called_once_with(1)

    def test_process_raises_on_navigator_underproduction(self):
        """Ensure process raises when navigator yields fewer points than expected."""
        eleanor = _make_eleanor()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([])
        sink = mock.Mock()
        sink.supports_worker_writes.return_value = False

        with self.assertRaisesRegex(EleanorException, "expected 10"):
            eleanor.process(
                mock.Mock(),
                navigator,
                10,
                1,
                batch_size=5,
                expected_total=10,
                executor=_as_executor(_FakeExecutor()),
                sink=sink,
            )

    def test_process_raises_on_navigator_overproduction(self):
        """Ensure process raises when navigator yields more points than expected."""
        eleanor = _make_eleanor()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a"] * 7])
        sink = mock.Mock()
        sink.supports_worker_writes.return_value = False
        executor = _FakeExecutor(num_workers=1, submit_side_effect=[_Future([])])

        with self.assertRaisesRegex(EleanorException, "expected 5"):
            eleanor.process(
                mock.Mock(),
                navigator,
                5,
                1,
                batch_size=7,
                expected_total=5,
                executor=_as_executor(executor),
                sink=sink,
            )

    def test_process_terminates_executor_on_interrupt(self):
        """Ensure process terminates the executor immediately when interrupted."""
        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a"]])
        executor = _FakeExecutor(submit_side_effect=[_Future([])])
        executor.pop_completed_future = mock.Mock(side_effect=KeyboardInterrupt)
        shutdown = SimpleNamespace(requested=False, signal_name=None)
        sink = mock.Mock()
        sink.supports_worker_writes.return_value = False

        with (
            mock.patch("eleanor.eleanor.shutdown_on_signal", return_value=_shutdown_with_state(shutdown)),
            self.assertRaises(EleanorShutdown),
        ):
            eleanor.process(
                kernel,
                navigator,
                1,
                9,
                batch_size=1,
                expected_total=1,
                executor=_as_executor(executor),
                sink=sink,
            )

        executor.shutdown.assert_called_once_with(wait=False)

    def test_process_shutdown_carries_signal_name(self):
        """Ensure EleanorShutdown preserves the recorded signal name."""
        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.navigate.return_value = iter([["a"]])
        executor = _FakeExecutor(submit_side_effect=[_Future([])])
        executor.pop_completed_future = mock.Mock(side_effect=KeyboardInterrupt)
        shutdown = SimpleNamespace(requested=True, signal_name="SIGTERM")
        sink = mock.Mock()
        sink.supports_worker_writes.return_value = False

        with (
            mock.patch("eleanor.eleanor.shutdown_on_signal", return_value=_shutdown_with_state(shutdown)),
            self.assertRaises(EleanorShutdown) as raised,
        ):
            eleanor.process(
                kernel,
                navigator,
                1,
                9,
                batch_size=1,
                expected_total=1,
                executor=_as_executor(executor),
                sink=sink,
            )

        self.assertEqual(raised.exception.signal_name, "SIGTERM")

    def test_process_skips_total_check_on_shutdown(self):
        """Ensure interrupt-driven shutdown bypasses navigator total-mismatch validation."""
        eleanor = _make_eleanor()
        navigator = mock.Mock()
        navigator.navigate.side_effect = KeyboardInterrupt
        shutdown = SimpleNamespace(requested=True, signal_name="SIGTERM")
        sink = mock.Mock()
        sink.supports_worker_writes.return_value = False

        with (
            mock.patch("eleanor.eleanor.shutdown_on_signal", return_value=_shutdown_with_state(shutdown)),
            self.assertRaises(EleanorShutdown) as raised,
        ):
            eleanor.process(
                mock.Mock(),
                navigator,
                10,
                1,
                batch_size=5,
                expected_total=10,
                executor=_as_executor(_FakeExecutor()),
                sink=sink,
            )

        self.assertEqual(raised.exception.signal_name, "SIGTERM")


class TestEleanorLoaders(TestCase):
    """Tests covering module-level plugin loader helpers."""

    def test_load_output_sink_uses_registry_factory_and_args(self):
        """Ensure load_output_sink resolves configured factory and output args."""
        config = _LoaderConfig(_LoaderOutputConfig(sink_type="plugin", args={"mode": "append"}))

        class _Sink(OutputSink):
            @override
            def begin_run(self, order):
                _ = order
                return 1

            @override
            def write_batch(self, order_id, results, progress=None):
                _ = order_id
                _ = results
                _ = progress
                return []

            @override
            def finalize_run(self):
                return None

        factory = mock.Mock(return_value=_Sink())
        with (
            mock.patch("eleanor.output.available_outputs", return_value=frozenset({"plugin"})),
            mock.patch("eleanor.output.get_factory", return_value=factory) as get_factory_mock,
        ):
            sink = load_output_sink(config, verbose=True)

        self.assertIsInstance(sink, OutputSink)
        get_factory_mock.assert_called_once_with("plugin")
        factory.assert_called_once_with(config, verbose=True, mode="append")

    def test_load_output_sink_rejects_invalid_plugin_return(self):
        """Ensure load_output_sink enforces OutputSink return type."""
        config = _LoaderConfig(_LoaderOutputConfig(sink_type="plugin", args={}))
        factory = mock.Mock(return_value=object())

        with (
            mock.patch("eleanor.output.available_outputs", return_value=frozenset({"plugin"})),
            mock.patch("eleanor.output.get_factory", return_value=factory),
            self.assertRaisesRegex(EleanorException, "expected an OutputSink"),
        ):
            _ = load_output_sink(config)

    def test_load_output_sink_rejects_none_type(self):
        """Ensure load_output_sink raises when no output type is configured."""
        config = _LoaderConfig(_LoaderOutputConfig(sink_type=None, args={}))
        with self.assertRaisesRegex(EleanorConfigurationException, "no output sink type provided"):
            _ = load_output_sink(config)

    def test_load_output_sink_rejects_unknown_type(self):
        """Ensure load_output_sink raises for unregistered sink types with a helpful message."""
        config = _LoaderConfig(_LoaderOutputConfig(sink_type="definitely-not-a-sink", args={}))
        with self.assertRaisesRegex(EleanorConfigurationException, "definitely-not-a-sink") as ctx:
            _ = load_output_sink(config)
        self.assertIn("postgres", str(ctx.exception))

    def test_load_kernel_constructs_and_sets_up_kernel(self):
        """Ensure load_kernel delegates to spec.build/setup with order context."""
        from eleanor.kernel.config import Settings as KernelSettings
        from eleanor.kernel.interface import AbstractKernel

        _ = _make_eleanor()
        settings = KernelSettings(timeout=None)
        kernel_cfg = mock.Mock()
        kernel_cfg.type = "eq36"
        kernel_cfg.resolved_settings.return_value = settings
        order = cast(Order, cast(object, SimpleNamespace(kernel=kernel_cfg)))

        kernel = mock.Mock(spec=AbstractKernel)
        spec = SimpleNamespace(
            settings_from_dict=mock.Mock(),
            build=mock.Mock(return_value=kernel),
        )
        kernel_args: list[object] = ["arg1"]
        with mock.patch("eleanor.kernel.get_factory", return_value=spec) as get_spec_mock:
            out = load_kernel(order, kernel_args, alpha=1)  # pyright: ignore[reportCallIssue]

        self.assertIs(out, kernel)
        get_spec_mock.assert_called_once_with("eq36")
        spec.build.assert_called_once_with(settings, "arg1")
        kernel.setup.assert_called_once_with(order, alpha=1)
        kernel.validate_order.assert_called_once_with(order)

    def test_load_kernel_raises_on_malformed_order_without_kernel(self):
        """Ensure malformed order-like objects without kernel config fail immediately."""
        order = cast(Order, cast(object, SimpleNamespace(kernel=None)))
        with self.assertRaisesRegex(AttributeError, "'NoneType' object has no attribute 'type'"):
            _ = load_kernel(order, ["arg1"])


class TestEleanorConstructorOverrides(TestCase):
    """Tests covering constructor-level executor/output sink overrides."""

    def test_constructor_executor_used_for_all_runs_in_session(self):
        """Ensure constructor executor override is reused across runs."""
        eleanor = _make_eleanor()
        ctor_executor = _FakeExecutor()
        setattr(eleanor, "_executor_override", ctor_executor)

        seen_executors = []

        def process(*_args, **kwargs):
            seen_executors.append(kwargs["executor"])
            return []

        eleanor.process = mock.Mock(side_effect=process)
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        sink.supports_progress.return_value = False

        with (
            mock.patch("eleanor.eleanor.load_executor") as load_executor,
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            with eleanor:
                _ = eleanor.run(_leaf_order(), 5, kernel=mock.Mock(), navigator=_navigator(1))
                _ = eleanor.run(_leaf_order(), 5, kernel=mock.Mock(), navigator=_navigator(1))

        load_executor.assert_not_called()
        self.assertEqual(len(seen_executors), 2)
        self.assertIs(seen_executors[0], ctor_executor)
        self.assertIs(seen_executors[1], ctor_executor)

    def test_unentered_executor_override_not_entered_or_shut_down_by_eleanor(self):
        """Ensure Eleanor does not manage lifecycle of caller-owned executor override."""
        eleanor = _make_eleanor()
        ctor_executor = _FakeExecutor()
        setattr(eleanor, "_executor_override", ctor_executor)
        eleanor.process = mock.Mock(return_value=[])
        sink = mock.Mock()
        sink.begin_run.return_value = 1
        sink.supports_progress.return_value = False

        with (
            mock.patch("eleanor.eleanor.load_executor"),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            with eleanor:
                self.assertEqual(ctor_executor.enter_count, 0)
                _ = eleanor.run(_leaf_order(), 1, kernel=mock.Mock(), navigator=_navigator(1))
                self.assertEqual(ctor_executor.enter_count, 0)

        ctor_executor.shutdown.assert_not_called()

    def test_caller_entered_executor_not_shut_down_by_eleanor(self):
        """Ensure Eleanor does not shut down pre-entered executor overrides."""
        eleanor = _make_eleanor()
        ctor_executor = _FakeExecutor()
        ctor_executor.__enter__()
        setattr(eleanor, "_executor_override", ctor_executor)
        eleanor.process = mock.Mock(return_value=[])
        sink = mock.Mock()
        sink.begin_run.return_value = 1
        sink.supports_progress.return_value = False

        with (
            mock.patch("eleanor.eleanor.load_executor"),
            mock.patch("eleanor.eleanor.load_output_sink", return_value=sink),
        ):
            with eleanor:
                _ = eleanor.run(_leaf_order(), 1, kernel=mock.Mock(), navigator=_navigator(1))
                self.assertEqual(ctor_executor.enter_count, 1)

        ctor_executor.shutdown.assert_not_called()

    def test_constructor_output_sink_used_for_all_runs_in_session(self):
        """Ensure constructor output sink override is reused across runs."""
        eleanor = _make_eleanor()
        ctor_sink = mock.Mock()
        ctor_sink.begin_run.return_value = 7
        ctor_sink.supports_progress.return_value = False
        eleanor._output_sink_override = ctor_sink
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink") as load_sink,
        ):
            with eleanor:
                _ = eleanor.run(_leaf_order(), 5, kernel=mock.Mock(), navigator=_navigator(1))
                _ = eleanor.run(_leaf_order(), 5, kernel=mock.Mock(), navigator=_navigator(1))

        load_sink.assert_not_called()
        self.assertEqual(ctor_sink.begin_run.call_count, 2)

    def test_constructor_output_sink_not_finalized_at_exit(self):
        """Ensure constructor output sink is not finalize()-d by Eleanor."""
        eleanor = _make_eleanor()
        ctor_sink = mock.Mock()
        ctor_sink.begin_run.return_value = 3
        ctor_sink.supports_progress.return_value = False
        eleanor._output_sink_override = ctor_sink
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()),
            mock.patch("eleanor.eleanor.load_output_sink"),
        ):
            with eleanor:
                _ = eleanor.run(_leaf_order(), 1, kernel=mock.Mock(), navigator=_navigator(1))

        ctor_sink.finalize.assert_not_called()

    def test_per_run_output_sink_overrides_constructor_output_sink(self):
        """Ensure per-run output_sink= wins over constructor override; caller retains lifecycle."""
        eleanor = _make_eleanor()
        ctor_sink = mock.Mock()
        per_run_sink = mock.Mock()
        per_run_sink.begin_run.return_value = 5
        per_run_sink.supports_progress.return_value = False
        eleanor._output_sink_override = ctor_sink
        eleanor.process = mock.Mock(return_value=[])

        with mock.patch("eleanor.eleanor.load_executor", return_value=_FakeExecutor()):
            eleanor.run(
                _leaf_order(),
                1,
                output_sink=per_run_sink,
                kernel=mock.Mock(),
                navigator=_navigator(1),
            )

        per_run_sink.initialize.assert_not_called()
        per_run_sink.finalize.assert_not_called()
        per_run_sink.finalize_run.assert_called_once()
        ctor_sink.finalize.assert_not_called()
