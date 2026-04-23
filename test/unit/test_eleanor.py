from types import SimpleNamespace
from unittest import mock

from eleanor.eleanor import Eleanor
from eleanor.exceptions import EleanorException
from eleanor.output import ComputeResult, OutputSink, WriteOutcome

from .common import TestCase


class _Future:
    def __init__(self, value):
        self._value = value
    def result(self):
        return self._value

    def get(self):
        return self.result()


class _Pool:
    def __init__(self, processes=None):
        workers = 2 if processes is None else processes
        if workers <= 0:
            workers = 1
        self.num_workers = workers
        self.submit = mock.Mock(side_effect=[_Future([10]), _Future([11])])
        self.shutdown = mock.Mock()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.shutdown()
        return None


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
        eleanor.config = SimpleNamespace(
            database="db-config",
            output=SimpleNamespace(type="postgres", args={}),
            parallel=SimpleNamespace(backend='multiprocessing', chunks_per_worker=1),
        )
        eleanor.order = SimpleNamespace(transformers=[])
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

    def test_init_applies_order_id_override(self):
        """
        Ensure the constructor assigns the supplied order_id onto the loaded order
        and leaves the existing id untouched when order_id is omitted.
        """
        loaded = SimpleNamespace(id=None)
        with (
            mock.patch("eleanor.eleanor.load_config", return_value="cfg"),
            mock.patch("eleanor.eleanor.load_order", return_value=loaded),
        ):
            eleanor = Eleanor("config.toml", "order.yaml", ["k"], order_id=55)
        self.assertIs(eleanor.order, loaded)
        self.assertEqual(eleanor.order.id, 55)

        untouched = SimpleNamespace(id=7)
        with (
            mock.patch("eleanor.eleanor.load_config", return_value="cfg"),
            mock.patch("eleanor.eleanor.load_order", return_value=untouched),
        ):
            eleanor = Eleanor("config.toml", "order.yaml", ["k"])
        self.assertEqual(eleanor.order.id, 7)

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
        executor = _Pool()
        with mock.patch("eleanor.eleanor.build_executor", return_value=executor) as build_executor:
            out = eleanor.run(5, order_id=3, verbose=True)
        self.assertEqual(out, [7])
        build_executor.assert_called_once_with(kind='multiprocessing', num_workers=None)
        eleanor.dispatch.assert_called_once_with(
            5,
            order_id=3,
            verbose=True,
            parallel='multiprocessing',
            chunks_per_worker=1,
            executor=executor,
            kernel=None,
            navigator=None,
            output_sink=None,
        )

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
        executor = _Pool()
        with (
            mock.patch("eleanor.eleanor.transform", return_value=transformed) as transform_fn,
            mock.patch("eleanor.eleanor.build_executor", return_value=executor) as build_executor,
        ):
            out = eleanor.run(4, order_id=2, verbose=True)

        self.assertEqual(out, [12])
        build_executor.assert_called_once_with(kind='multiprocessing', num_workers=None)
        eleanor.load_kernel.assert_called_once_with(verbose=True)
        transform_fn.assert_called_once_with(original_order, kernel, overrides=None)
        self.assertIs(eleanor.order, transformed)
        eleanor._run.assert_called_once_with(
            4,
            order_id=2,
            combined=False,
            proportional_sampling=False,
            verbose=True,
            parallel='multiprocessing',
            chunks_per_worker=1,
            executor=executor,
            kernel=None,
            navigator=None,
            output_sink=None,
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
        sink = mock.Mock()
        sink.begin_run.return_value = 99
        eleanor.load_output_sink = mock.Mock(return_value=sink)

        child1 = mock.Mock()
        child1._run.return_value = [4, 2]
        child2 = mock.Mock()
        child2._run.return_value = [2, 3]
        eleanor.recur = mock.Mock(side_effect=[child1, child2])
        executor = _Pool()
        with mock.patch("eleanor.eleanor.build_executor", return_value=executor) as build_executor:
            out = eleanor.run(8)

        self.assertEqual(out, [2, 3, 4])
        build_executor.assert_called_once_with(kind='multiprocessing', num_workers=None)
        eleanor.load_output_sink.assert_called_once()
        sink.begin_run.assert_called_once_with(eleanor.order)
        child1._run.assert_called_once()
        child2._run.assert_called_once()
        self.assertIs(child1._run.call_args.kwargs["executor"], executor)
        self.assertIs(child2._run.call_args.kwargs["executor"], executor)
        self.assertEqual(child1._run.call_args.kwargs["parallel"], 'multiprocessing')
        self.assertEqual(child2._run.call_args.kwargs["parallel"], 'multiprocessing')
        self.assertEqual(child1._run.call_args.kwargs["chunks_per_worker"], 1)
        self.assertEqual(child2._run.call_args.kwargs["chunks_per_worker"], 1)
        # order_id from begin_run is threaded into the child runs.
        self.assertEqual(child1._run.call_args.kwargs["order_id"], 99)
        self.assertEqual(child2._run.call_args.kwargs["order_id"], 99)

    def test_dispatch_rejects_unsupported_success_sampling(self):
        """
        Ensure dispatch raises if success_sampling is requested with unsupported navigator.
        """
        from eleanor.navigator import AbstractNavigator

        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock(spec=AbstractNavigator)
        navigator.supports_success_sampling.return_value = False
        eleanor.load_kernel = mock.Mock(return_value=kernel)
        eleanor.order.navigator = SimpleNamespace(type="random", args={})

        with (
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
            self.assertRaises(EleanorException),
        ):
            eleanor.dispatch(2, success_sampling=True)

    def test_dispatch_processes_without_success_sampling(self):
        """
        Ensure dispatch begins a run via the output sink and calls process once in standard mode.
        """
        from eleanor.navigator import AbstractNavigator

        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock(spec=AbstractNavigator)
        navigator.supports_success_sampling.return_value = True
        eleanor.load_kernel = mock.Mock(return_value=kernel)
        eleanor.order.navigator = SimpleNamespace(type="random", args={})
        eleanor.process = mock.Mock(return_value=[
            WriteOutcome(point_id=10, exit_code=0, committed=True)
        ])
        sink = mock.Mock()
        sink.begin_run.return_value = 5
        eleanor.load_output_sink = mock.Mock(return_value=sink)
        executor = _Pool()
        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=executor) as build_executor,
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
        ):
            out = eleanor.dispatch(6, num_procs=0, show_progress=False)

        self.assertEqual(out, [5])
        build_executor.assert_called_once_with(kind='multiprocessing', num_workers=0)
        eleanor.process.assert_called_once()
        sink.begin_run.assert_called_once_with(eleanor.order)
        sink.finalize.assert_called_once()
        self.assertIs(eleanor.process.call_args.kwargs["executor"], executor)

    def test_dispatch_success_sampling_with_progress(self):
        """
        Ensure dispatch loops in success-sampling mode and joins progress.
        Each call targets exactly simulation_size new successes; pre-existing
        DB successes are not counted toward the target.
        """
        from eleanor.navigator import AbstractNavigator

        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock(spec=AbstractNavigator)
        navigator.supports_success_sampling.return_value = True
        eleanor.load_kernel = mock.Mock(return_value=kernel)
        eleanor.order.navigator = SimpleNamespace(type="random", args={})
        eleanor.process = mock.Mock(return_value=[
            WriteOutcome(point_id=10, exit_code=0, committed=True),
            WriteOutcome(point_id=11, exit_code=0, committed=True),
        ])
        sink = mock.Mock()
        sink.begin_run.return_value = 11
        eleanor.load_output_sink = mock.Mock(return_value=sink)
        executor = _Pool()
        manager = mock.Mock()

        progress = SimpleNamespace(queue=mock.Mock(), join=mock.Mock())
        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=executor) as build_executor,
            mock.patch("eleanor.eleanor.Manager", return_value=manager),
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
        ):
            out = eleanor.dispatch(2, show_progress=True, success_sampling=True, order_id=11)

        self.assertEqual(out, [11])
        build_executor.assert_called_once_with(kind='multiprocessing', num_workers=None)
        eleanor.process.assert_called_once()
        sink.begin_run.assert_called_once_with(eleanor.order)
        sink.finalize.assert_called_once()
        progress.join.assert_called_once()
        manager.shutdown.assert_called_once()

    def test_process_requires_executor(self):
        """
        Ensure process raises if no process executor is provided.
        """
        eleanor = self._make_eleanor()
        sink = mock.Mock()
        with self.assertRaises(EleanorException):
            eleanor.process(mock.Mock(), mock.Mock(), 1, 1, executor=None, sink=sink)

    def test_process_batches_and_breaks_when_complete(self):
        """
        Ensure process navigates, dispatches sailor batches, and exits when navigator is complete.
        """
        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.navigate.return_value = ["a", "b"]
        navigator.is_complete.return_value = True
        executor = _Pool()
        progress = mock.Mock()
        compute_results = [
            ComputeResult(point=SimpleNamespace(exit_code=0)),
            ComputeResult(point=SimpleNamespace(exit_code=0)),
        ]
        executor.submit = mock.Mock(side_effect=[_Future(compute_results), _Future([])])
        sink = mock.Mock()
        sink.supports_worker_writes.return_value = False
        sink.write_batch.return_value = [
            WriteOutcome(point_id=10, exit_code=0, committed=True),
            WriteOutcome(point_id=11, exit_code=0, committed=True),
        ]

        eleanor.process(kernel, navigator, 2, 9, executor=executor, sink=sink, progress=progress, success_sampling=True)

        progress.put.assert_any_call(2)
        self.assertEqual(executor.submit.call_count, 2)
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

        executor = _Pool()
        executor.submit = mock.Mock(side_effect=[_Future(worker_results), _Future([])])
        sink = mock.Mock()
        sink.supports_worker_writes.return_value = False
        sink.write_batch.return_value = [
            WriteOutcome(point_id=101, exit_code=0, committed=True),
            WriteOutcome(point_id=102, exit_code=1, committed=True),
        ]

        eleanor.process(
            kernel,
            navigator,
            2,
            9,
            executor=executor,
            sink=sink,
            progress=None,
            success_sampling=True,
        )

        sink.write_batch.assert_called_once_with(9, worker_results)

    def test_process_forwards_sink_to_workers_when_opted_in(self):
        """
        Ensure process routes writes through workers when the sink opts in:
        the sink/order_id are threaded through executor.submit, futures already
        resolve to WriteOutcomes, and sink.write_batch is not called in the
        parent process.
        """
        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.navigate.return_value = ["a", "b"]
        navigator.is_complete.return_value = True

        worker_outcomes = [
            WriteOutcome(point_id=201, exit_code=0, committed=True),
            WriteOutcome(point_id=202, exit_code=0, committed=True),
        ]

        executor = _Pool()
        executor.submit = mock.Mock(side_effect=[_Future(worker_outcomes), _Future([])])

        sink = mock.Mock()
        sink.supports_worker_writes.return_value = True

        eleanor.process(
            kernel,
            navigator,
            2,
            9,
            executor=executor,
            sink=sink,
            progress=None,
            success_sampling=True,
        )

        sink.write_batch.assert_not_called()
        submit_kwargs = executor.submit.call_args_list[0].kwargs
        self.assertIs(submit_kwargs["sink"], sink)
        self.assertEqual(submit_kwargs["order_id"], 9)
        is_complete_args = navigator.is_complete.call_args[0][0]
        self.assertEqual(sorted(is_complete_args), [201, 202])

    def test_dispatch_uses_explicit_output_sink_override(self):
        """
        Ensure dispatch uses a caller-provided sink and skips load_output_sink.
        """
        from eleanor.navigator import AbstractNavigator

        eleanor = self._make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock(spec=AbstractNavigator)
        navigator.supports_success_sampling.return_value = True
        eleanor.load_kernel = mock.Mock(return_value=kernel)
        eleanor.order.navigator = SimpleNamespace(type="random", args={})
        eleanor.process = mock.Mock(return_value=[
            WriteOutcome(point_id=10, exit_code=0, committed=True)
        ])
        eleanor.load_output_sink = mock.Mock()
        provided_sink = mock.Mock()
        provided_sink.begin_run.return_value = 7
        executor = _Pool()
        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=executor) as build_executor,
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
        ):
            out = eleanor.dispatch(1, order_id=7, show_progress=False, output_sink=provided_sink)

        self.assertEqual(out, [7])
        build_executor.assert_called_once_with(kind='multiprocessing', num_workers=None)
        eleanor.load_output_sink.assert_not_called()
        provided_sink.begin_run.assert_called_once_with(eleanor.order)
        provided_sink.finalize.assert_called_once()
        self.assertIs(eleanor.process.call_args.kwargs["sink"], provided_sink)

    def test_load_output_sink_uses_registry_factory_and_args(self):
        """
        Ensure load_output_sink resolves the configured sink factory and forwards output.args.
        """
        eleanor = self._make_eleanor()
        eleanor.config.output = SimpleNamespace(type="plugin", args={"mode": "append"})

        class _Sink(OutputSink):
            def begin_run(self, order):
                _ = order

            def write_batch(self, order_id, results):
                _ = order_id
                _ = results
                return []

            def finalize(self):
                return None

        factory = mock.Mock(return_value=_Sink())
        with mock.patch("eleanor.eleanor.get_output_factory", return_value=factory) as get_factory_mock:
            sink = eleanor.load_output_sink(verbose=True)

        self.assertIsInstance(sink, OutputSink)
        get_factory_mock.assert_called_once_with("plugin")
        factory.assert_called_once_with(eleanor.config, verbose=True, mode="append")

    def test_load_output_sink_rejects_invalid_plugin_return(self):
        """
        Ensure load_output_sink enforces that factories return OutputSink instances.
        """
        eleanor = self._make_eleanor()
        eleanor.config.output = SimpleNamespace(type="plugin", args={})
        factory = mock.Mock(return_value=object())

        with (
            mock.patch("eleanor.eleanor.get_output_factory", return_value=factory),
            self.assertRaisesRegex(EleanorException, 'expected an OutputSink'),
        ):
            eleanor.load_output_sink()

    def test_load_kernel_constructs_and_sets_up_kernel(self):
        """
        Ensure load_kernel fetches the KernelSpec and delegates to spec.build/setup.
        """
        from eleanor.kernel.config import Settings as KernelSettings
        from eleanor.kernel.interface import AbstractKernel

        eleanor = self._make_eleanor()
        settings = KernelSettings(timeout=None)
        kernel_cfg = mock.Mock()
        kernel_cfg.type = "eq36"
        kernel_cfg.resolved_settings.return_value = settings
        eleanor.order.kernel = kernel_cfg

        kernel = mock.Mock(spec=AbstractKernel)
        spec = SimpleNamespace(
            settings_from_dict=mock.Mock(),
            build=mock.Mock(return_value=kernel),
        )
        with mock.patch("eleanor.eleanor.get_kernel_spec", return_value=spec) as get_spec_mock:
            out = eleanor.load_kernel(alpha=1)

        self.assertIs(out, kernel)
        get_spec_mock.assert_called_once_with("eq36")
        spec.build.assert_called_once_with(settings, "arg1")
        kernel.setup.assert_called_once_with(eleanor.order, alpha=1)

