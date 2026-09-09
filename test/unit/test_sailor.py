from typing import cast
from types import SimpleNamespace
from unittest import TestCase, mock

from eleanor.exceptions import EleanorError
from eleanor.kernel.exceptions import EleanorKernelError
from eleanor.output import ComputeResult, WriteOutcome
from eleanor.runner import Runner
from eleanor.variable_space import Point


def _vs_point(**kwargs: object) -> Point:
    return cast(Point, cast(object, SimpleNamespace({'exception': None, **kwargs})))


def _identity_sink(outcomes: object = None) -> mock.Mock:
    """Sink stand-in whose prepared payload is the ``ComputeResult`` list itself.

    ``dispatch`` now always routes through a sink, because ``prepare_batch``
    always runs in the worker. An identity prepare lets the compute-path tests
    keep asserting on ``ComputeResult``s directly.
    """
    sink = mock.Mock()
    sink.prepare_batch.side_effect = lambda _order_id, results: results
    sink.commit_batch.return_value = [] if outcomes is None else outcomes
    return sink


class TestRunner(TestCase):
    """
    Tests of the eleanor.runner module.
    """

    def test_dispatch_returns_one_compute_result_per_point(self) -> None:
        """
        Ensure that list dispatch returns one ComputeResult per input point.
        """
        runner = Runner(kernel=mock.Mock())
        points = [_vs_point(exit_code=0), _vs_point(exit_code=0)]

        with mock.patch.object(Runner, "work", side_effect=points) as work_mock:
            results = runner.dispatch(
                [_vs_point(), _vs_point()], sink=_identity_sink(), order_id=1
            )

        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(result, ComputeResult) for result in results))
        self.assertIs(cast(ComputeResult, results[0]).point, points[0])
        self.assertIs(cast(ComputeResult, results[1]).point, points[1])
        self.assertEqual(work_mock.call_count, 2)

    def test_dispatch_single_point_returns_compute_result(self) -> None:
        """
        Ensure single-point dispatch returns a single ComputeResult.
        """
        runner = Runner(kernel=mock.Mock())

        point = _vs_point(exit_code=0)
        with mock.patch.object(Runner, "work", return_value=point):
            results = runner.dispatch(_vs_point(), sink=_identity_sink(), order_id=1)

        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], ComputeResult)
        self.assertIs(cast(ComputeResult, results[0]).point, point)

    def test_dispatch_commits_through_the_sink_when_commit_is_set(self) -> None:
        """
        Ensure dispatch forwards compute results to sink.write_batch when a
        sink and order_id are supplied, and returns the WriteOutcome list.
        """
        runner = Runner(kernel=mock.Mock())
        points = [_vs_point(exit_code=0), _vs_point(exit_code=0)]
        outcomes = [
            WriteOutcome(exit_code=0, committed=True),
            WriteOutcome(exit_code=0, committed=True),
        ]
        sink = _identity_sink(outcomes)

        with mock.patch.object(Runner, "work", side_effect=points):
            results = runner.dispatch(
                [_vs_point(), _vs_point()], sink=sink, order_id=42, commit=True
            )

        self.assertEqual(results, outcomes)

        # prepare always runs, and sees the ComputeResults for this chunk.
        sink.prepare_batch.assert_called_once()
        prepare_order_id, called_compute_results = sink.prepare_batch.call_args.args
        self.assertEqual(prepare_order_id, 42)
        self.assertEqual(len(called_compute_results), 2)
        self.assertTrue(
            all(isinstance(r, ComputeResult) for r in called_compute_results)
        )
        self.assertIs(called_compute_results[0].point, points[0])
        self.assertIs(called_compute_results[1].point, points[1])

        # commit runs here only because commit=True was passed.
        sink.commit_batch.assert_called_once()
        commit_order_id, committed = sink.commit_batch.call_args.args
        self.assertEqual(commit_order_id, 42)
        self.assertIs(committed, called_compute_results)
        self.assertIsNone(sink.commit_batch.call_args.kwargs["progress"])

    def test_dispatch_emits_sim_progress_tick_per_point(self) -> None:
        """
        Ensure dispatch calls sim_progress.tick() once per point when a progress handle is supplied.
        """
        runner = Runner(kernel=mock.Mock())
        sim_progress = mock.Mock()

        with mock.patch.object(
            Runner,
            "work",
            side_effect=[
                _vs_point(exit_code=0),
                _vs_point(exit_code=0),
                _vs_point(exit_code=0),
            ],
        ):
            _ = runner.dispatch(
                [_vs_point(), _vs_point(), _vs_point()],
                sink=_identity_sink(),
                order_id=1,
                sim_progress=sim_progress,
            )

        self.assertEqual(sim_progress.tick.call_count, 3)

    def test_dispatch_forwards_out_progress_to_sink(self) -> None:
        """
        Ensure dispatch forwards the out_progress handle into sink.commit_batch.
        """
        runner = Runner(kernel=mock.Mock())
        sink = _identity_sink()
        out_progress = mock.Mock()

        with mock.patch.object(
            Runner, "work", return_value=_vs_point(exit_code=0)
        ):
            _ = runner.dispatch(
                [_vs_point()],
                sink=sink,
                order_id=1,
                commit=True,
                out_progress=out_progress,
            )

        sink.commit_batch.assert_called_once()
        self.assertIs(sink.commit_batch.call_args.kwargs["progress"], out_progress)

    def test_dispatch_without_progress_handles_never_ticks(self) -> None:
        """
        Ensure dispatch does not attempt any progress emission when handles are omitted.
        """
        runner = Runner(kernel=mock.Mock())

        with mock.patch.object(
            Runner, "work", return_value=_vs_point(exit_code=0)
        ):
            results = runner.dispatch(
                [_vs_point(), _vs_point()], sink=_identity_sink(), order_id=1
            )

        # No exception, no interaction with a progress handle; just the compute path.
        self.assertEqual(len(results), 2)

    def test_dispatch_requires_a_sink_and_an_order_id(self) -> None:
        """
        Ensure both are mandatory now that prepare_batch always runs.

        They used to be optional, with a runtime guard for the
        sink-without-order_id case. Since every dispatch prepares through a
        sink, the signature enforces it instead.
        """
        runner = Runner(kernel=mock.Mock())
        sink = _identity_sink()
        with mock.patch.object(
            Runner, "work", return_value=_vs_point(exit_code=0)
        ):
            with self.assertRaises(TypeError):
                _ = runner.dispatch([_vs_point()], sink=sink)  # type: ignore[call-arg]
            with self.assertRaises(TypeError):
                _ = runner.dispatch([_vs_point()], order_id=1)  # type: ignore[call-arg]
        sink.prepare_batch.assert_not_called()
        sink.commit_batch.assert_not_called()

    def test_dispatch_serializes_error_metadata_and_clears_exception(self) -> None:
        """
        Ensure dispatch converts exceptions into ErrorInfo and clears non-pickleable exception payloads.
        """
        runner = Runner(kernel=mock.Mock())

        point = _vs_point(exit_code=1, exception=RuntimeError("boom"))
        with mock.patch.object(Runner, "work", return_value=point):
            results = runner.dispatch(
                [_vs_point()], sink=_identity_sink(), order_id=1
            )

        self.assertEqual(len(results), 1)
        result = cast(ComputeResult, results[0])
        self.assertIsNotNone(result.error)
        assert result.error is not None
        self.assertEqual(result.error.type_name, "RuntimeError")
        self.assertEqual(result.error.message, "boom")
        self.assertIsNone(point.exception)

    def test_work_success_and_scratch(self) -> None:
        """
        Ensure that successful work sets timing, outputs, and optional scratch collection.
        """
        kernel = mock.Mock()
        kernel.run.return_value = ["eq"]
        runner = Runner(kernel=kernel)
        vs_point = _vs_point()
        out = runner.work(vs_point, scratch=False)
        self.assertIs(out, vs_point)
        self.assertEqual(vs_point.exit_code, 0)
        self.assertEqual(vs_point.es_points, ["eq"])
        self.assertTrue(hasattr(vs_point, "start_date"))
        self.assertTrue(hasattr(vs_point, "complete_date"))
        kernel.copy_data.assert_not_called()

        kernel.reset_mock()
        vs_point2 = _vs_point()
        out2 = runner.work(vs_point2, scratch=True)
        self.assertIs(out2, vs_point2)
        kernel.copy_data.assert_called_once_with(vs_point2)
        self.assertTrue(hasattr(vs_point2, "scratch"))
        self.assertIsNotNone(vs_point2.scratch)
        assert vs_point2.scratch is not None
        self.assertIsInstance(vs_point2.scratch.zip, bytes)

    def test_work_handles_eleanor_exception_and_generic_exception(self) -> None:
        """
        Ensure that work captures exceptions and sets exit codes for Eleanor and non-Eleanor errors.
        """
        kernel = mock.Mock()
        runner = Runner(kernel=kernel)

        kernel.run.side_effect = EleanorKernelError("boom", code=9)
        vs_point = _vs_point()
        out = runner.work(vs_point, verbose=False)
        self.assertIs(out, vs_point)
        self.assertEqual(vs_point.exit_code, 9)
        self.assertIsInstance(vs_point.exception, EleanorError)
        kernel.copy_data.assert_called_with(vs_point)

        kernel.reset_mock()
        kernel.run.side_effect = RuntimeError("oops")
        vs_point2 = _vs_point(exit_code=0)
        out2 = runner.work(vs_point2, verbose=False)
        self.assertIs(out2, vs_point2)
        self.assertEqual(vs_point2.exit_code, -1)
        self.assertIsInstance(vs_point2.exception, RuntimeError)

    def test_work_verbose_prints_traceback_to_stderr(self) -> None:
        """
        Ensure that verbose mode prints traceback information to stderr on work failures.
        """
        kernel = mock.Mock()
        kernel.run.side_effect = RuntimeError("oops")
        runner = Runner(kernel=kernel)
        vs_point = _vs_point(exit_code=0)

        with mock.patch("eleanor.runner.print_exception") as print_mock:
            _ = runner.work(vs_point, verbose=True)

        self.assertGreaterEqual(print_mock.call_count, 2)

    def test_collect_scratch_success_and_failure(self) -> None:
        """
        Ensure scratch collection returns zipped bytes and falls back to null-byte payload on errors.
        """
        from os.path import join
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            with open(join(tmp, "a.txt"), "w") as f:
                _ = f.write("abc")
            scratch = Runner.collect_scratch(tmp)
            self.assertIsNotNone(scratch)
            assert scratch is not None
            self.assertTrue(isinstance(scratch.zip, bytes) and len(scratch.zip) > 0)

        with mock.patch(
            "eleanor.runner.zipfile.ZipFile", side_effect=RuntimeError("zip error")
        ):
            scratch = Runner.collect_scratch(".")
        assert scratch is not None
        self.assertEqual(scratch.zip, bytes("\0", "ascii"))
