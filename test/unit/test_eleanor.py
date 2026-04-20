from types import SimpleNamespace
from unittest import mock

from eleanor.eleanor import Eleanor
from eleanor.exceptions import EleanorException
from eleanor.output import ComputeResult, WriteOutcome
from eleanor.order import HufferResult

from .common import TestCase


class _Future:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _Pool:
    def __init__(self, processes=None):
        self._processes = 2 if processes is None else processes
        self.apply_async = mock.Mock(side_effect=[_Future([10]), _Future([11])])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class _Query:
    def __init__(self, count_value):
        self._count_value = count_value

    def filter(self, *_args, **_kwargs):
        return self

    def count(self):
        return self._count_value


class _Yeoman:
    def __init__(self, scalar_values=None, count_value=0):
        self.scalar_values = [] if scalar_values is None else list(scalar_values)
        self.write = mock.Mock()
        self.merge = mock.Mock()
        self.commit = mock.Mock()
        self.setup = mock.Mock()
        self._count_value = count_value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def scalar(self, *_args, **_kwargs):
        return self.scalar_values.pop(0) if self.scalar_values else None

    def query(self, *_args, **_kwargs):
        return _Query(self._count_value)


class _Suborder:
    def __init__(self, volume):
        self._volume = volume

    def volume(self):
        return self._volume


class TestEleanor(TestCase):
    """
    Tests of the eleanor.eleanor module.
    """

    def _make_eleanor(self):
        eleanor = Eleanor.__new__(Eleanor)
        eleanor.kernel_args = ["arg1"]
        eleanor.config = SimpleNamespace(database="db-config", output=SimpleNamespace(type="postgres"))
        eleanor.order = SimpleNamespace(transformers=[], huffer_result=None)
        return eleanor

    def test_init_loads_config_and_order(self):
        """
        Ensure constructor delegates config/order loading helpers.
        """
        with (
            mock.patch("eleanor.eleanor.load_config", return_value="cfg") as load_cfg,
            mock.patch("eleanor.eleanor.load_order", return_value="ord") as load_order,
        ):
            eleanor = Eleanor("config.toml", "order.yaml", ["k"])
        load_cfg.assert_called_once_with("config.toml")
        load_order.assert_called_once_with("order.yaml")
        self.assertEqual(eleanor.config, "cfg")
        self.assertEqual(eleanor.order, "ord")
        self.assertEqual(eleanor.kernel_args, ["k"])

    def test_recur_uses_runtime_class(self):
        """
        Ensure recur re-instantiates via the dynamic class of self.
        """

        class Child(Eleanor):
            def __init__(self, config, order, kernel_args):
                self.config = config
                self.order = order
                self.kernel_args = kernel_args

        child = Child.__new__(Child)
        out = child.recur("cfg", "ord", ["k"])
        self.assertIsInstance(out, Child)
        self.assertEqual(out.config, "cfg")
        self.assertEqual(out.order, "ord")
        self.assertEqual(out.kernel_args, ["k"])

    def test_run_dispatches_without_suborders(self):
        """
        Ensure run delegates directly to dispatch when no suborders are present.
        """
        eleanor = self._make_eleanor()
        eleanor.order.suborders = None
        eleanor.dispatch = mock.Mock(return_value=[7])

        out = eleanor.run(5, order_id=3, verbose=True)
        self.assertEqual(out, [7])
        eleanor.dispatch.assert_called_once_with(5, order_id=3, verbose=True)

    def test_run_applies_transformers_before_recursing(self):
        """
        Ensure run loads the kernel and applies configured transformers before delegating to _run.
        """
        eleanor = self._make_eleanor()
        eleanor.order = SimpleNamespace(transformers=[SimpleNamespace(type="x")], suborders=None)
        original_order = eleanor.order
        transformed = SimpleNamespace(transformers=[], suborders=None)
        kernel = mock.Mock()
        eleanor.load_kernel = mock.Mock(return_value=kernel)
        eleanor._run = mock.Mock(return_value=[12])

        with mock.patch("eleanor.eleanor.transform", return_value=transformed) as transform_fn:
            out = eleanor.run(4, order_id=2, verbose=True)

        self.assertEqual(out, [12])
        eleanor.load_kernel.assert_called_once_with(verbose=True)
        transform_fn.assert_called_once_with(original_order, kernel)
        self.assertIs(eleanor.order, transformed)
        eleanor._run.assert_called_once_with(
            4,
            order_id=2,
            combined=False,
            proportional_sampling=False,
            verbose=True,
        )

    def test_run_recurse_with_suborders_and_proportional_sampling(self):
        """
        Ensure run recurses over suborders and aggregates sorted unique order ids.
        """
        eleanor = self._make_eleanor()
        suborders = [_Suborder(3.0), _Suborder(1.0)]
        eleanor.order.suborders = SimpleNamespace(suborders=suborders, combined=True, proportional_sampling=True)
        eleanor.order.split_suborders = mock.Mock(return_value=suborders)
        eleanor.order.volume = mock.Mock(return_value=4.0)
        eleanor.ignite = mock.Mock(return_value=99)

        child1 = mock.Mock()
        child1._run.return_value = [4, 2]
        child2 = mock.Mock()
        child2._run.return_value = [2, 3]
        eleanor.recur = mock.Mock(side_effect=[child1, child2])

        out = eleanor.run(8)

        self.assertEqual(out, [2, 3, 4])
        eleanor.ignite.assert_called_once()
        child1._run.assert_called_once()
        child2._run.assert_called_once()

    def test_dispatch_rejects_unsupported_success_sampling(self):
        """
        Ensure dispatch raises if success_sampling is requested with unsupported navigator.
        """
        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.supports_success_sampling.return_value = False
        eleanor.load_kernel = mock.Mock(return_value=kernel)
        eleanor.order.navigator = mock.Mock()
        eleanor.order.navigator.load.return_value = lambda *_args: navigator

        with self.assertRaises(EleanorException):
            eleanor.dispatch(2, success_sampling=True)

    def test_dispatch_processes_without_success_sampling(self):
        """
        Ensure dispatch ignites as needed and calls process once in standard mode.
        """
        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.supports_success_sampling.return_value = True
        eleanor.load_kernel = mock.Mock(return_value=kernel)
        eleanor.order.navigator = mock.Mock()
        eleanor.order.navigator.load.return_value = lambda *_args: navigator
        eleanor.ignite = mock.Mock(return_value=5)
        eleanor.process = mock.Mock(return_value=[
            WriteOutcome(point_id=10, exit_code=0, committed=True)
        ])
        sink = mock.Mock()
        eleanor.load_output_sink = mock.Mock(return_value=sink)

        with mock.patch("eleanor.eleanor.Pool", _Pool):
            out = eleanor.dispatch(6, num_procs=0, show_progress=False, no_huffer=True)

        self.assertEqual(out, [5])
        eleanor.ignite.assert_called_once()
        eleanor.process.assert_called_once()
        sink.begin_run.assert_called_once()
        sink.finalize.assert_called_once()
        self.assertEqual(eleanor.ignite.call_args.kwargs["huffer_with"], None)

    def test_dispatch_sets_huffer_with_when_enabled(self):
        """
        Ensure dispatch passes (kernel, navigator) to ignite when huffer is enabled.
        """
        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.supports_success_sampling.return_value = True
        eleanor.load_kernel = mock.Mock(return_value=kernel)
        eleanor.order.navigator = mock.Mock()
        eleanor.order.navigator.load.return_value = lambda *_args: navigator
        eleanor.ignite = mock.Mock(return_value=6)
        eleanor.process = mock.Mock(return_value=[
            WriteOutcome(point_id=10, exit_code=0, committed=True)
        ])
        sink = mock.Mock()
        eleanor.load_output_sink = mock.Mock(return_value=sink)

        with mock.patch("eleanor.eleanor.Pool", _Pool):
            out = eleanor.dispatch(3, no_huffer=False, show_progress=False)

        self.assertEqual(out, [6])
        sink.begin_run.assert_called_once()
        sink.finalize.assert_called_once()
        self.assertEqual(eleanor.ignite.call_args.kwargs["huffer_with"], (kernel, navigator))

    def test_dispatch_success_sampling_with_progress(self):
        """
        Ensure dispatch loops in success-sampling mode and joins progress.
        Each call targets exactly simulation_size new successes; pre-existing
        DB successes are not counted toward the target.
        """
        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.supports_success_sampling.return_value = True
        eleanor.load_kernel = mock.Mock(return_value=kernel)
        eleanor.order.navigator = mock.Mock()
        eleanor.order.navigator.load.return_value = lambda *_args: navigator
        eleanor.process = mock.Mock(return_value=[
            WriteOutcome(point_id=10, exit_code=0, committed=True),
            WriteOutcome(point_id=11, exit_code=0, committed=True),
        ])
        sink = mock.Mock()
        eleanor.load_output_sink = mock.Mock(return_value=sink)

        progress = SimpleNamespace(queue=mock.Mock(), join=mock.Mock())
        with (
            mock.patch("eleanor.eleanor.Pool", _Pool),
            mock.patch("eleanor.eleanor.Manager", return_value=object()),
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
        ):
            out = eleanor.dispatch(2, show_progress=True, success_sampling=True, order_id=11)

        self.assertEqual(out, [11])
        eleanor.process.assert_called_once()
        sink.begin_run.assert_called_once()
        sink.finalize.assert_called_once()
        progress.join.assert_called_once()

    def test_process_requires_pool(self):
        """
        Ensure process raises if no process pool is provided.
        """
        eleanor = self._make_eleanor()
        sink = mock.Mock()
        with self.assertRaises(EleanorException):
            eleanor.process(mock.Mock(), mock.Mock(), 1, 1, pool=None, sink=sink)

    def test_process_batches_and_breaks_when_complete(self):
        """
        Ensure process navigates, dispatches sailor batches, and exits when navigator is complete.
        """
        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.navigate.return_value = ["a", "b"]
        navigator.is_complete.return_value = True
        pool = _Pool()
        progress = mock.Mock()
        compute_results = [
            ComputeResult(point=SimpleNamespace(exit_code=0)),
            ComputeResult(point=SimpleNamespace(exit_code=0)),
        ]
        pool.apply_async = mock.Mock(side_effect=[_Future(compute_results), _Future([])])
        sink = mock.Mock()
        sink.write_batch.return_value = [
            WriteOutcome(point_id=10, exit_code=0, committed=True),
            WriteOutcome(point_id=11, exit_code=0, committed=True),
        ]

        eleanor.process(kernel, navigator, 2, 9, pool=pool, sink=sink, progress=progress, success_sampling=True)

        progress.put.assert_any_call(2)
        self.assertEqual(pool.apply_async.call_count, 2)
        sink.write_batch.assert_called_once_with(9, compute_results)
        is_complete_args = navigator.is_complete.call_args[0][0]
        self.assertEqual(sorted(is_complete_args), [10, 11])

    def test_process_routes_worker_results_through_sink(self):
        """
        Ensure process writes worker results through OutputSink in the parent process.
        """
        from eleanor.output import ComputeResult, WriteOutcome

        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.navigate.return_value = ["a", "b"]
        navigator.is_complete.return_value = True

        point_a = SimpleNamespace(exit_code=0, exception=None)
        point_b = SimpleNamespace(exit_code=1, exception=None)
        worker_results = [
            ComputeResult(point=point_a),
            ComputeResult(point=point_b),
        ]

        pool = _Pool()
        pool.apply_async = mock.Mock(side_effect=[_Future(worker_results), _Future([])])
        sink = mock.Mock()
        sink.write_batch.return_value = [
            WriteOutcome(point_id=101, exit_code=0, committed=True),
            WriteOutcome(point_id=102, exit_code=1, committed=True),
        ]

        eleanor.process(
            kernel,
            navigator,
            2,
            9,
            pool=pool,
            sink=sink,
            progress=None,
            success_sampling=True,
        )

        sink.write_batch.assert_called_once_with(9, worker_results)

    def test_load_kernel_constructs_and_sets_up_kernel(self):
        """
        Ensure load_kernel imports, constructs, and sets up the configured kernel.
        """
        eleanor = self._make_eleanor()
        eleanor.order.kernel = SimpleNamespace(type="eq36", settings="settings")

        kernel = mock.Mock()
        kernel_module = SimpleNamespace(Kernel=mock.Mock(return_value=kernel))
        with mock.patch("eleanor.eleanor.import_kernel_module", return_value=kernel_module):
            out = eleanor.load_kernel(alpha=1)

        self.assertIs(out, kernel)
        kernel.setup.assert_called_once_with(eleanor.order, alpha=1)

    def test_ignite_rejects_version_mismatch(self):
        """
        Ensure ignite raises when database contains orders with a different Eleanor version.
        """
        eleanor = self._make_eleanor()
        eleanor.order.hash = "abc"
        yeoman = _Yeoman(scalar_values=[object()])
        with mock.patch("eleanor.eleanor.Yeoman", return_value=yeoman):
            with self.assertRaises(EleanorException):
                eleanor.ignite()

    def test_ignite_merges_existing_order(self):
        """
        Ensure ignite reuses an existing order record and merges huffer updates.
        """
        eleanor = self._make_eleanor()
        eleanor.order.id = None
        eleanor.order.hash = "abc"
        eleanor.order.eleanor_version = None
        eleanor.order.huffer_result = None
        existing = SimpleNamespace(
            id=21,
            eleanor_version="v",
            huffer_result=SimpleNamespace(exit_code=0, zip=b"0"),
        )
        navigator = mock.Mock()
        navigator.huffer_problem.return_value = "problem"
        kernel = mock.Mock()
        kernel.is_soft_exit.return_value = True
        huffer_point = SimpleNamespace(exit_code=1, scratch=SimpleNamespace(zip=b"x"), exception=RuntimeError("x"))
        yeoman = _Yeoman(scalar_values=[None, existing])
        with (
            mock.patch("eleanor.eleanor.Sailor") as sailor_cls,
            mock.patch("eleanor.eleanor.Yeoman", return_value=yeoman),
        ):
            sailor_cls.return_value.work.return_value = huffer_point
            out = eleanor.ignite(huffer_with=(kernel, navigator))

        self.assertEqual(out, 21)
        yeoman.merge.assert_called_once_with(existing)
        yeoman.commit.assert_called_once()
        self.assertEqual(existing.huffer_result.exit_code, 1)
        self.assertEqual(existing.huffer_result.zip, b"x")

    def test_ignite_writes_new_order_and_requires_id(self):
        """
        Ensure ignite writes new orders and raises if no order id is assigned.
        """
        eleanor = self._make_eleanor()
        eleanor.order.id = 33
        eleanor.order.hash = "abc"
        eleanor.order.eleanor_version = None
        eleanor.order.huffer_result = None
        yeoman = _Yeoman(scalar_values=[None, None])
        with mock.patch("eleanor.eleanor.Yeoman", return_value=yeoman):
            out = eleanor.ignite()
        self.assertEqual(out, 33)
        yeoman.write.assert_called_once_with(eleanor.order, refresh=True)

        eleanor2 = self._make_eleanor()
        eleanor2.order.id = None
        eleanor2.order.hash = "abc"
        eleanor2.order.eleanor_version = None
        eleanor2.order.huffer_result = None
        yeoman2 = _Yeoman(scalar_values=[None, None])
        with mock.patch("eleanor.eleanor.Yeoman", return_value=yeoman2):
            with self.assertRaises(EleanorException):
                eleanor2.ignite()

    def test_ignite_huffer_soft_and_hard_exit_paths(self):
        """
        Ensure ignite handles huffer integration and raises on hard kernel exit.
        """
        eleanor = self._make_eleanor()
        eleanor.order.id = 8
        eleanor.order.hash = "abc"
        eleanor.order.eleanor_version = None
        eleanor.order.huffer_result = None
        navigator = mock.Mock()
        navigator.huffer_problem.return_value = "problem"
        kernel = mock.Mock()
        kernel.is_soft_exit.return_value = True
        huffer_point = SimpleNamespace(exit_code=3, scratch=SimpleNamespace(zip=b"z"), exception=RuntimeError("x"))
        yeoman = _Yeoman(scalar_values=[None, None])
        with (
            mock.patch("eleanor.eleanor.Sailor") as sailor_cls,
            mock.patch("eleanor.eleanor.Yeoman", return_value=yeoman),
        ):
            sailor_cls.return_value.work.return_value = huffer_point
            out = eleanor.ignite(huffer_with=(kernel, navigator))
        self.assertEqual(out, 8)
        self.assertIsNotNone(eleanor.order.huffer_result)

        eleanor2 = self._make_eleanor()
        eleanor2.order.id = 8
        eleanor2.order.hash = "abc"
        eleanor2.order.eleanor_version = None
        eleanor2.order.huffer_result = None
        kernel2 = mock.Mock()
        kernel2.is_soft_exit.return_value = False
        yeoman2 = _Yeoman(scalar_values=[None, None])
        with (
            mock.patch("eleanor.eleanor.Sailor") as sailor_cls2,
            mock.patch("eleanor.eleanor.Yeoman", return_value=yeoman2),
        ):
            sailor_cls2.return_value.work.return_value = huffer_point
            with self.assertRaises(EleanorException):
                eleanor2.ignite(huffer_with=(kernel2, navigator))

    def test_ignite_existing_order_adds_huffer_result_when_missing(self):
        """
        Ensure ignite assigns huffer_result when an existing order lacks one.
        """
        eleanor = self._make_eleanor()
        eleanor.order.id = None
        eleanor.order.hash = "abc"
        eleanor.order.eleanor_version = None
        eleanor.order.huffer_result = None
        existing = SimpleNamespace(id=17, eleanor_version="v", huffer_result=None)
        navigator = mock.Mock()
        navigator.huffer_problem.return_value = "problem"
        kernel = mock.Mock()
        kernel.is_soft_exit.return_value = True
        huffer_point = SimpleNamespace(exit_code=2, scratch=SimpleNamespace(zip=b"xyz"), exception=RuntimeError("x"))
        yeoman = _Yeoman(scalar_values=[None, existing])
        with (
            mock.patch("eleanor.eleanor.Sailor") as sailor_cls,
            mock.patch("eleanor.eleanor.Yeoman", return_value=yeoman),
        ):
            sailor_cls.return_value.work.return_value = huffer_point
            out = eleanor.ignite(huffer_with=(kernel, navigator))

        self.assertEqual(out, 17)
        self.assertIsNotNone(existing.huffer_result)
        self.assertEqual(existing.huffer_result.exit_code, 2)

