from types import SimpleNamespace
from unittest import mock

from eleanor.eleanor import Eleanor
from eleanor.exceptions import EleanorException
from eleanor.order import LeafPlan
from eleanor.output import ComputeResult, OutputSink, WriteOutcome

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

    supports_worker_progress = True

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
    fake_config = SimpleNamespace(
        database="db-config",
        output=SimpleNamespace(type="postgres", args={}),
        parallel=SimpleNamespace(backend="multiprocessing", chunks_per_worker=1),
    )
    return Eleanor(fake_config, ["arg1"])


def _leaf_order(navigator_type="random", transformers=None):
    """Produce an order-like ``SimpleNamespace`` that looks like a leaf order.

    The returned namespace carries a minimal ``iter_leaves`` so
    ``Eleanor.run`` can walk it without crashing; it yields a single
    ``LeafPlan`` pointing back at the order itself.
    """
    ns = SimpleNamespace(
        suborders=None,
        transformers=transformers if transformers is not None else [],
        navigator=SimpleNamespace(type=navigator_type, args={}),
        id=None,
    )

    def iter_leaves(combined=False, proportional_sampling=False):
        _ = combined, proportional_sampling
        return iter([LeafPlan(order=ns, sample_fraction=1.0, umbrella=None)])

    ns.iter_leaves = iter_leaves
    return ns


class TestEleanorConstruction(TestCase):
    """
    Tests covering ``Eleanor.__init__`` and the session/per-run scopes.
    """

    def test_init_stashes_config_and_kernel_args(self):
        """
        Ensure the constructor stashes config, copies kernel_args, and stashes num_procs.
        """
        fake_config = SimpleNamespace(
            database="db-config",
            output=SimpleNamespace(type="postgres", args={}),
            parallel=SimpleNamespace(backend="multiprocessing", chunks_per_worker=1),
        )
        eleanor = Eleanor(fake_config, ["k"], num_procs=4)

        self.assertIs(eleanor.config, fake_config)
        self.assertEqual(eleanor.kernel_args, ["k"])
        self.assertEqual(eleanor.num_procs, 4)
        self.assertFalse(eleanor._entered)
        self.assertIsNone(eleanor._executor)
        self.assertIsNone(eleanor._manager)
        self.assertIsNone(eleanor._output_sink)

    def test_init_defaults_kernel_args_to_empty_list(self):
        """
        Ensure omitted ``kernel_args`` defaults to an empty list and is not shared with the caller.
        """
        fake_config = SimpleNamespace(
            database="db-config",
            output=SimpleNamespace(type="postgres", args={}),
            parallel=SimpleNamespace(backend="multiprocessing", chunks_per_worker=1),
        )
        eleanor = Eleanor(fake_config)
        self.assertEqual(eleanor.kernel_args, [])
        src = ["a"]
        e2 = Eleanor(fake_config, src)
        src.append("b")
        self.assertEqual(e2.kernel_args, ["a"])

    def test_enter_builds_executor_and_exit_tears_down_all(self):
        """
        Ensure __enter__ builds an executor and __exit__ finalizes sink,
        shuts down manager, and shuts down executor in that order.
        """
        eleanor = _make_eleanor()
        executor = _FakeExecutor()
        manager = mock.Mock()
        sink = mock.Mock()

        with mock.patch("eleanor.eleanor.build_executor", return_value=executor) as build_executor:
            with eleanor:
                build_executor.assert_called_once_with(kind="multiprocessing", num_workers=None)
                self.assertIs(eleanor._executor, executor)
                # Simulate lazy-initialization by run()
                eleanor._manager = manager
                eleanor._output_sink = sink

        sink.finalize.assert_called_once()
        manager.shutdown.assert_called_once()
        executor.shutdown.assert_called_once_with(wait=True)
        self.assertFalse(eleanor._entered)
        self.assertIsNone(eleanor._executor)
        self.assertIsNone(eleanor._manager)
        self.assertIsNone(eleanor._output_sink)

    def test_exit_still_tears_down_after_failure_in_one_resource(self):
        """
        Ensure __exit__ continues to shut down remaining resources even when
        an earlier resource's teardown raises.
        """
        eleanor = _make_eleanor()
        executor = _FakeExecutor()
        manager = mock.Mock()
        sink = mock.Mock()
        sink.finalize.side_effect = RuntimeError("boom")

        with mock.patch("eleanor.eleanor.build_executor", return_value=executor):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                with eleanor:
                    eleanor._manager = manager
                    eleanor._output_sink = sink

        manager.shutdown.assert_called_once()
        executor.shutdown.assert_called_once_with(wait=True)

    def test_run_failure_inside_with_still_tears_down_at_exit(self):
        """
        Ensure an exception raised during run() does not leak the session
        executor or sink: __exit__ is still entered and tears them down.
        """
        eleanor = _make_eleanor()
        order = _leaf_order()
        session_executor = _FakeExecutor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        eleanor._dispatch = mock.Mock(side_effect=RuntimeError("dispatch failed"))

        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=session_executor),
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink),
        ):
            with self.assertRaisesRegex(RuntimeError, "dispatch failed"):
                with eleanor:
                    eleanor.run(order, 5)

        # Session sink finalized at __exit__, executor shut down, state cleared.
        sink.finalize.assert_called_once()
        session_executor.shutdown.assert_called_once_with(wait=True)
        self.assertIsNone(eleanor._executor)
        self.assertIsNone(eleanor._output_sink)

    def test_progress_is_per_leaf_with_shared_manager(self):
        """
        Ensure a combined two-leaf run with show_progress=True builds a
        fresh Progress for each leaf while reusing the same SyncManager.
        """
        eleanor = _make_eleanor()
        umbrella = _leaf_order()
        leaf_a = _leaf_order()
        leaf_b = _leaf_order()
        root = SimpleNamespace(
            transformers=[],
            iter_leaves=mock.Mock(
                return_value=iter(
                    [
                        LeafPlan(order=leaf_a, sample_fraction=1.0, umbrella=umbrella),
                        LeafPlan(order=leaf_b, sample_fraction=1.0, umbrella=umbrella),
                    ]
                )
            ),
        )

        session_executor = _FakeExecutor()
        session_manager = mock.Mock()
        sink = mock.Mock()
        sink.begin_run.return_value = 77

        seen_managers = []

        def dispatch(order, samples, *a, manager, **kw):
            seen_managers.append(manager)
            return [77]

        eleanor._dispatch = mock.Mock(side_effect=dispatch)

        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=session_executor),
            mock.patch("eleanor.eleanor.Manager", return_value=session_manager),
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink),
        ):
            with eleanor:
                _ = eleanor.run(root, 10, combined=True, show_progress=True)

        # Both leaves observed the same SyncManager instance.
        self.assertEqual(len(seen_managers), 2)
        self.assertIs(seen_managers[0], session_manager)
        self.assertIs(seen_managers[1], session_manager)
        # The manager is shut down exactly once at __exit__.
        session_manager.shutdown.assert_called_once()


class TestEleanorRun(TestCase):
    """
    Tests covering ``Eleanor.run`` in leaf and multi-leaf shapes.
    """

    def test_run_without_with_builds_and_tears_down_resources(self):
        """
        Ensure run() outside of ``with`` builds a per-run executor and
        sink, finalizes the sink at the end of run, and tears the executor down.
        """
        eleanor = _make_eleanor()
        order = _leaf_order()
        executor = _FakeExecutor()
        sink = mock.Mock()
        sink.begin_run.return_value = 7
        eleanor._dispatch = mock.Mock(return_value=[7])

        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=executor) as build_executor,
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink) as load_sink,
        ):
            out = eleanor.run(order, 5)

        self.assertEqual(out, [7])
        build_executor.assert_called_once_with(kind="multiprocessing", num_workers=None)
        load_sink.assert_called_once_with(verbose=False)
        sink.finalize.assert_called_once()
        executor.shutdown.assert_called_once_with(wait=True)

    def test_run_inside_with_reuses_session_executor_and_defers_finalize(self):
        """
        Ensure two consecutive run() calls inside ``with`` see the same executor
        and the sink's finalize is deferred until __exit__.
        """
        eleanor = _make_eleanor()
        order1 = _leaf_order()
        order2 = _leaf_order()
        session_executor = _FakeExecutor()
        sink = mock.Mock()
        seen_executors = []

        def dispatch(order, samples, *a, executor, **kw):
            seen_executors.append(executor)
            return [sink.begin_run.return_value]

        eleanor._dispatch = mock.Mock(side_effect=dispatch)

        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=session_executor),
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink),
        ):
            with eleanor:
                _ = eleanor.run(order1, 5)
                _ = eleanor.run(order2, 5)

        self.assertEqual(len(seen_executors), 2)
        self.assertIs(seen_executors[0], session_executor)
        self.assertIs(seen_executors[1], session_executor)
        # finalize once at __exit__, not per-run
        sink.finalize.assert_called_once()
        session_executor.shutdown.assert_called_once_with(wait=True)

    def test_run_applies_transformers_before_walking_leaves(self):
        """
        Ensure run() loads the kernel and rewrites the order before walking the suborder tree.
        """
        eleanor = _make_eleanor()
        original = _leaf_order(transformers=[SimpleNamespace(type="t")])
        transformed = _leaf_order()
        kernel = mock.Mock()
        eleanor.load_kernel = mock.Mock(return_value=kernel)
        eleanor._dispatch = mock.Mock(return_value=[42])

        executor = _FakeExecutor()
        sink = mock.Mock()
        sink.begin_run.return_value = 42
        seen_orders = []

        def dispatch(order, *a, **kw):
            seen_orders.append(order)
            return [42]

        eleanor._dispatch.side_effect = dispatch

        with (
            mock.patch("eleanor.eleanor.transform", return_value=transformed) as transform_fn,
            mock.patch("eleanor.eleanor.build_executor", return_value=executor),
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink),
        ):
            out = eleanor.run(original, 3, verbose=True)

        self.assertEqual(out, [42])
        eleanor.load_kernel.assert_called_once_with(original, verbose=True)
        transform_fn.assert_called_once_with(original, kernel, overrides=None)
        # the dispatched order is the post-transform one
        self.assertEqual(len(seen_orders), 1)
        self.assertIs(seen_orders[0], transformed)
        # and the same kernel is forwarded to _dispatch (not re-loaded per leaf)
        self.assertIs(eleanor._dispatch.call_args.kwargs["kernel"], kernel)

    def test_run_combined_calls_begin_run_once_per_umbrella(self):
        """
        Ensure combined runs call sink.begin_run(umbrella) exactly once regardless
        of how many leaves share the umbrella, and each leaf's order.id is set to
        the umbrella's id before dispatch.
        """
        eleanor = _make_eleanor()
        umbrella = _leaf_order()
        leaf_a = _leaf_order()
        leaf_b = _leaf_order()
        # Skip iter_leaves by patching the order's method.
        root = SimpleNamespace(
            transformers=[],
            iter_leaves=mock.Mock(
                return_value=iter(
                    [
                        LeafPlan(order=leaf_a, sample_fraction=1.0, umbrella=umbrella),
                        LeafPlan(order=leaf_b, sample_fraction=1.0, umbrella=umbrella),
                    ]
                )
            ),
        )

        executor = _FakeExecutor()
        sink = mock.Mock()
        sink.begin_run.return_value = 77
        dispatched_calls = []

        def dispatch(order, samples, *a, **kw):
            dispatched_calls.append((order, order.id))
            return [order.id]

        eleanor._dispatch = mock.Mock(side_effect=dispatch)

        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=executor),
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink),
        ):
            out = eleanor.run(root, 10, combined=True)

        self.assertEqual(out, [77])
        sink.begin_run.assert_called_once_with(umbrella)
        self.assertEqual(len(dispatched_calls), 2)
        self.assertEqual(dispatched_calls[0], (leaf_a, 77))
        self.assertEqual(dispatched_calls[1], (leaf_b, 77))

    def test_run_proportional_scales_samples_per_leaf(self):
        """
        Ensure proportional sampling multiplies simulation_size by leaf.sample_fraction.
        """
        eleanor = _make_eleanor()
        leaf_a = _leaf_order()
        leaf_b = _leaf_order()
        root = SimpleNamespace(
            transformers=[],
            iter_leaves=mock.Mock(
                return_value=iter(
                    [
                        LeafPlan(order=leaf_a, sample_fraction=0.25, umbrella=None),
                        LeafPlan(order=leaf_b, sample_fraction=0.75, umbrella=None),
                    ]
                )
            ),
        )

        executor = _FakeExecutor()
        sink = mock.Mock()
        sink.begin_run.return_value = 5
        sizes = []

        def dispatch(order, samples, *a, **kw):
            sizes.append(samples)
            return [sink.begin_run.return_value]

        eleanor._dispatch = mock.Mock(side_effect=dispatch)

        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=executor),
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink),
        ):
            _ = eleanor.run(root, 100, proportional_sampling=True)

        self.assertEqual(sizes, [25, 75])

    def test_run_single_leaf_passes_order_with_preset_id_to_dispatch(self):
        """
        Ensure a caller-supplied order.id on a non-split order is forwarded to _dispatch
        unchanged: the caller is responsible for pre-setting the id before calling run().
        """
        eleanor = _make_eleanor()
        order = _leaf_order()
        order.id = 99

        executor = _FakeExecutor()
        sink = mock.Mock()
        seen = {}

        def dispatch(order, samples, *a, **kw):
            seen["order_id"] = order.id
            return [99]

        eleanor._dispatch = mock.Mock(side_effect=dispatch)

        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=executor),
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink),
        ):
            _ = eleanor.run(order, 4)

        self.assertEqual(seen["order_id"], 99)

    def test_run_raises_when_order_yields_no_leaves(self):
        """
        Ensure run() raises EleanorException when iter_leaves produces no leaves.
        """
        eleanor = _make_eleanor()
        empty_order = SimpleNamespace(
            transformers=[],
            iter_leaves=mock.Mock(return_value=iter([])),
        )
        executor = _FakeExecutor()
        sink = mock.Mock()

        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=executor),
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink),
            self.assertRaisesRegex(EleanorException, "no dispatchable leaves"),
        ):
            eleanor.run(empty_order, 10)


class TestEleanorDispatch(TestCase):
    """
    Tests covering ``Eleanor._dispatch`` and the process loop.
    """

    def test_dispatch_rejects_unsupported_success_sampling(self):
        """
        Ensure _dispatch raises if success_sampling is requested with unsupported navigator.
        """
        from eleanor.navigator import AbstractNavigator

        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock(spec=AbstractNavigator)
        navigator.supports_success_sampling.return_value = False
        order = _leaf_order()
        sink = mock.Mock()
        sink.begin_run.return_value = 5

        with (
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
            self.assertRaises(EleanorException),
        ):
            eleanor._dispatch(
                order,
                2,
                chunks_per_worker=1,
                executor=_FakeExecutor(),
                kernel=kernel,
                navigator=None,
                sink=sink,
                manager=None,
                success_sampling=True,
            )

    def test_dispatch_calls_process_once_in_standard_mode(self):
        """
        Ensure _dispatch begins a run via the sink and calls process once when not
        in success-sampling mode.
        """
        from eleanor.navigator import AbstractNavigator

        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock(spec=AbstractNavigator)
        navigator.supports_success_sampling.return_value = True
        order = _leaf_order()
        sink = mock.Mock()
        sink.begin_run.return_value = 5
        eleanor.process = mock.Mock(
            return_value=[
                WriteOutcome(point_id=10, exit_code=0, committed=True),
            ]
        )
        executor = _FakeExecutor()

        with mock.patch(
            "eleanor.navigator.registry.get_factory",
            return_value=lambda *_args, **_kw: navigator,
        ):
            out = eleanor._dispatch(
                order,
                6,
                chunks_per_worker=1,
                executor=executor,
                kernel=kernel,
                navigator=None,
                sink=sink,
                manager=None,
            )

        self.assertEqual(out, [5])
        eleanor.process.assert_called_once()
        sink.begin_run.assert_called_once_with(order)
        self.assertIs(eleanor.process.call_args.kwargs["executor"], executor)

    def test_dispatch_success_sampling_loops_until_target_met(self):
        """
        Ensure _dispatch loops in success-sampling mode until at least
        simulation_size new successes have been recorded.
        """
        from eleanor.navigator import AbstractNavigator

        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock(spec=AbstractNavigator)
        navigator.supports_success_sampling.return_value = True
        order = _leaf_order()
        sink = mock.Mock()
        sink.begin_run.return_value = 11
        sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(
            return_value=[
                WriteOutcome(point_id=10, exit_code=0, committed=True),
                WriteOutcome(point_id=11, exit_code=0, committed=True),
            ]
        )
        executor = _FakeExecutor()
        manager = mock.Mock()

        progress = SimpleNamespace(
            sim=mock.Mock(),
            out=mock.Mock(),
            join=mock.Mock(),
        )
        with (
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
        ):
            out = eleanor._dispatch(
                order,
                2,
                chunks_per_worker=1,
                executor=executor,
                kernel=kernel,
                navigator=None,
                sink=sink,
                manager=manager,
                show_progress=True,
                success_sampling=True,
            )  # show_progress/success_sampling flow through kwargs

        self.assertEqual(out, [11])
        eleanor.process.assert_called_once()
        sink.begin_run.assert_called_once_with(order)
        progress.join.assert_called_once()

    def test_dispatch_constructs_out_handle_only_when_sink_supports_progress(self):
        """
        Ensure _dispatch hands the output handle to process() only when the
        sink advertises supports_progress=True; otherwise only the sim handle
        travels down, keeping the output bar from rendering.
        """
        from eleanor.navigator import AbstractNavigator

        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock(spec=AbstractNavigator)
        navigator.supports_success_sampling.return_value = True
        order = _leaf_order()
        executor = _FakeExecutor()
        manager = mock.Mock()

        sim_handle = mock.Mock(name="sim_handle")
        out_handle = mock.Mock(name="out_handle")
        progress = SimpleNamespace(sim=sim_handle, out=out_handle, join=mock.Mock())

        # Sink opts out of progress: out_handle must never be forwarded.
        quiet_sink = mock.Mock()
        quiet_sink.begin_run.return_value = 5
        quiet_sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
        ):
            eleanor._dispatch(
                order,
                1,
                chunks_per_worker=1,
                executor=executor,
                kernel=kernel,
                navigator=None,
                sink=quiet_sink,
                manager=manager,
                show_progress=True,
            )

        kwargs = eleanor.process.call_args.kwargs
        self.assertIs(kwargs["sim_progress"], sim_handle)
        self.assertIsNone(kwargs["out_progress"])

        # Sink opts in: the out handle is forwarded and, under
        # success_sampling, the output bar total is seeded up front.
        loud_sink = mock.Mock()
        loud_sink.begin_run.return_value = 6
        loud_sink.supports_progress.return_value = True
        eleanor.process = mock.Mock(
            return_value=[
                WriteOutcome(point_id=10, exit_code=0, committed=True),
            ]
        )

        with (
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
        ):
            eleanor._dispatch(
                order,
                3,
                chunks_per_worker=1,
                executor=executor,
                kernel=kernel,
                navigator=None,
                sink=loud_sink,
                manager=manager,
                show_progress=True,
                success_sampling=True,
            )

        kwargs = eleanor.process.call_args.kwargs
        self.assertIs(kwargs["sim_progress"], sim_handle)
        self.assertIs(kwargs["out_progress"], out_handle)
        # Under success_sampling, the output bar's target was seeded to 3.
        out_handle.total.assert_called_with(3)

    def test_dispatch_signals_done_on_both_handles_in_finally(self):
        """
        Ensure _dispatch closes the sim bar (always) and the out bar (only when
        the sink opted in) by calling ``done()`` on each handle in the finally
        block, even when ``process()`` raises.
        """
        from eleanor.navigator import AbstractNavigator

        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock(spec=AbstractNavigator)
        navigator.supports_success_sampling.return_value = True
        executor = _FakeExecutor()
        manager = mock.Mock()

        # --- Loud sink: both handles are live, both must be closed. ---
        sim_handle = mock.Mock(name="sim_handle")
        out_handle = mock.Mock(name="out_handle")
        progress = SimpleNamespace(sim=sim_handle, out=out_handle, join=mock.Mock())

        loud_sink = mock.Mock()
        loud_sink.begin_run.return_value = 6
        loud_sink.supports_progress.return_value = True
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
        ):
            eleanor._dispatch(
                _leaf_order(),
                1,
                chunks_per_worker=1,
                executor=executor,
                kernel=kernel,
                navigator=None,
                sink=loud_sink,
                manager=manager,
                show_progress=True,
            )

        sim_handle.done.assert_called_once_with()
        out_handle.done.assert_called_once_with()
        progress.join.assert_called_once_with()

        # --- Quiet sink: out_handle was never built, so done() must not be sent on it. ---
        sim_handle = mock.Mock(name="sim_handle")
        out_handle = mock.Mock(name="out_handle")
        progress = SimpleNamespace(sim=sim_handle, out=out_handle, join=mock.Mock())

        quiet_sink = mock.Mock()
        quiet_sink.begin_run.return_value = 7
        quiet_sink.supports_progress.return_value = False
        eleanor.process = mock.Mock(return_value=[])

        with (
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
        ):
            eleanor._dispatch(
                _leaf_order(),
                1,
                chunks_per_worker=1,
                executor=executor,
                kernel=kernel,
                navigator=None,
                sink=quiet_sink,
                manager=manager,
                show_progress=True,
            )

        sim_handle.done.assert_called_once_with()
        out_handle.done.assert_not_called()
        progress.join.assert_called_once_with()

        # --- Exception path: done()/join() must still fire from the finally. ---
        sim_handle = mock.Mock(name="sim_handle")
        out_handle = mock.Mock(name="out_handle")
        progress = SimpleNamespace(sim=sim_handle, out=out_handle, join=mock.Mock())

        boom_sink = mock.Mock()
        boom_sink.begin_run.return_value = 8
        boom_sink.supports_progress.return_value = True
        eleanor.process = mock.Mock(side_effect=RuntimeError("boom"))

        with (
            mock.patch("eleanor.eleanor.Progress", return_value=progress),
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
            self.assertRaises(RuntimeError),
        ):
            eleanor._dispatch(
                _leaf_order(),
                1,
                chunks_per_worker=1,
                executor=executor,
                kernel=kernel,
                navigator=None,
                sink=boom_sink,
                manager=manager,
                show_progress=True,
            )

        sim_handle.done.assert_called_once_with()
        out_handle.done.assert_called_once_with()
        progress.join.assert_called_once_with()

    def test_dispatch_requires_manager_when_progress_enabled(self):
        """
        Ensure _dispatch refuses to build a Progress object without a SyncManager.
        """
        from eleanor.navigator import AbstractNavigator

        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock(spec=AbstractNavigator)
        navigator.supports_success_sampling.return_value = True
        order = _leaf_order()
        sink = mock.Mock()
        sink.begin_run.return_value = 1

        with (
            mock.patch(
                "eleanor.navigator.registry.get_factory",
                return_value=lambda *_args, **_kw: navigator,
            ),
            self.assertRaisesRegex(EleanorException, "SyncManager"),
        ):
            eleanor._dispatch(
                order,
                2,
                chunks_per_worker=1,
                executor=_FakeExecutor(),
                kernel=kernel,
                navigator=None,
                sink=sink,
                manager=None,
                show_progress=True,
            )

    def test_process_requires_executor(self):
        """
        Ensure process raises if no process executor is provided.
        """
        eleanor = _make_eleanor()
        sink = mock.Mock()
        with self.assertRaises(EleanorException):
            eleanor.process(mock.Mock(), mock.Mock(), 1, 1, executor=None, sink=sink)

    def test_process_batches_and_breaks_when_complete(self):
        """
        Ensure process navigates, streams serial-sink writes per resolved worker
        batch, and exits when navigator is complete.
        """
        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.navigate.return_value = ["a", "b"]
        navigator.is_complete.return_value = True
        compute_results_a = [ComputeResult(point=SimpleNamespace(exit_code=0))]
        compute_results_b = [ComputeResult(point=SimpleNamespace(exit_code=0))]
        executor = _FakeExecutor(
            submit_side_effect=[_Future(compute_results_a), _Future(compute_results_b)],
        )
        sim_progress = mock.Mock()
        out_progress = mock.Mock()
        sink = mock.Mock()
        sink.supports_worker_writes.return_value = False
        sink.write_batch.side_effect = [
            [WriteOutcome(point_id=10, exit_code=0, committed=True)],
            [WriteOutcome(point_id=11, exit_code=0, committed=True)],
        ]

        eleanor.process(
            kernel,
            navigator,
            2,
            9,
            executor=executor,
            sink=sink,
            sim_progress=sim_progress,
            out_progress=out_progress,
            success_sampling=True,
        )

        # Both bars extend by the batch size at the start of each navigator
        # iteration; output bar has out_no_total_update in Progress, so the
        # extend() call is safe even under success_sampling.
        sim_progress.extend.assert_any_call(2)
        out_progress.extend.assert_any_call(2)
        self.assertEqual(executor.submit.call_count, 2)
        self.assertEqual(
            sink.write_batch.call_args_list,
            [
                mock.call(9, compute_results_a, progress=out_progress),
                mock.call(9, compute_results_b, progress=out_progress),
            ],
        )
        self.assertEqual(executor.pop_completed_future.call_count, 2)
        is_complete_args = navigator.is_complete.call_args[0][0]
        self.assertEqual(sorted(is_complete_args), [10, 11])

    def test_process_respects_executor_completion_order_for_serial_sinks(self):
        """
        Ensure process drains futures in the order selected by
        executor.pop_completed_future rather than strict submission order.
        """
        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.navigate.return_value = ["a", "b"]
        navigator.is_complete.return_value = True

        compute_results_a = [ComputeResult(point=SimpleNamespace(exit_code=0, label="a"))]
        compute_results_b = [ComputeResult(point=SimpleNamespace(exit_code=0, label="b"))]
        executor = _FakeExecutor(
            submit_side_effect=[_Future(compute_results_a), _Future(compute_results_b)],
        )
        # Simulate "second future completed first".
        executor.pop_completed_future = mock.Mock(side_effect=lambda futures: futures.pop())

        sink = mock.Mock()
        sink.supports_worker_writes.return_value = False
        sink.write_batch.side_effect = [
            [WriteOutcome(point_id=20, exit_code=0, committed=True)],
            [WriteOutcome(point_id=10, exit_code=0, committed=True)],
        ]
        out_progress = mock.Mock()

        eleanor.process(
            kernel,
            navigator,
            2,
            9,
            executor=executor,
            sink=sink,
            out_progress=out_progress,
        )

        self.assertEqual(
            [call.args[1] for call in sink.write_batch.call_args_list],
            [compute_results_b, compute_results_a],
        )
        self.assertEqual(navigator.is_complete.call_args[0][0], [20, 10])

    def test_process_forwards_sink_to_workers_when_opted_in(self):
        """
        Ensure process routes writes through workers when the sink opts in:
        the sink/order_id/progress handles are threaded through executor.submit,
        futures already resolve to WriteOutcomes, and sink.write_batch is not
        called in the parent process.
        """
        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.navigate.return_value = ["a", "b"]
        navigator.is_complete.return_value = True

        worker_outcomes = [
            WriteOutcome(point_id=201, exit_code=0, committed=True),
            WriteOutcome(point_id=202, exit_code=0, committed=True),
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
            executor=executor,
            sink=sink,
            sim_progress=sim_progress,
            out_progress=out_progress,
            success_sampling=True,
        )

        sink.write_batch.assert_not_called()
        submit_kwargs = executor.submit.call_args_list[0].kwargs
        self.assertIs(submit_kwargs["sink"], sink)
        self.assertEqual(submit_kwargs["order_id"], 9)
        # Progress handles flow through to workers when the executor
        # advertises supports_worker_progress=True.
        self.assertIs(submit_kwargs["sim_progress"], sim_progress)
        self.assertIs(submit_kwargs["out_progress"], out_progress)
        is_complete_args = navigator.is_complete.call_args[0][0]
        self.assertEqual(sorted(is_complete_args), [201, 202])

    def test_process_falls_back_to_batch_ticks_when_executor_cannot_carry_progress(self):
        """
        Ensure process emits coarse batch-level ticks in the parent when the
        executor cannot forward a ProgressHandle into its workers.
        """
        eleanor = _make_eleanor()
        kernel = mock.Mock()
        navigator = mock.Mock()
        navigator.navigate.return_value = ["a", "b"]
        navigator.is_complete.return_value = True

        worker_outcomes = [
            WriteOutcome(point_id=1, exit_code=0, committed=True),
            WriteOutcome(point_id=2, exit_code=1, committed=True),  # not counted as success
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
            executor=executor,
            sink=sink,
            sim_progress=sim_progress,
            out_progress=out_progress,
        )

        # Handles are NOT threaded into the worker when the executor cannot
        # carry them.
        submit_kwargs = executor.submit.call_args_list[0].kwargs
        self.assertIsNone(submit_kwargs["sim_progress"])
        self.assertIsNone(submit_kwargs["out_progress"])
        # Instead, the parent ticks once per batch: 2 results total, 1 of
        # which is a committed success.
        sim_progress.tick.assert_called_once_with(2)
        out_progress.tick.assert_called_once_with(1)

    def test_run_uses_explicit_output_sink_override(self):
        """
        Ensure an explicit output_sink= override is used and finalize()-d at the
        end of run, and load_output_sink is not called.
        """
        eleanor = _make_eleanor()
        order = _leaf_order()
        provided_sink = mock.Mock()
        provided_sink.begin_run.return_value = 7
        eleanor._dispatch = mock.Mock(return_value=[7])
        eleanor.load_output_sink = mock.Mock()
        executor = _FakeExecutor()

        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=executor),
        ):
            out = eleanor.run(order, 1, output_sink=provided_sink)

        self.assertEqual(out, [7])
        eleanor.load_output_sink.assert_not_called()
        provided_sink.finalize.assert_called_once()


class TestEleanorLoaders(TestCase):
    """
    Tests covering ``Eleanor.load_output_sink`` and ``Eleanor.load_kernel``.
    """

    def test_load_output_sink_uses_registry_factory_and_args(self):
        """
        Ensure load_output_sink resolves the configured sink factory and forwards output.args.
        """
        eleanor = _make_eleanor()
        eleanor.config.output = SimpleNamespace(type="plugin", args={"mode": "append"})

        class _Sink(OutputSink):
            def begin_run(self, order):
                _ = order

            def write_batch(self, order_id, results):
                _ = order_id
                _ = results
                return []

            def finalize_run(self):
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
        eleanor = _make_eleanor()
        eleanor.config.output = SimpleNamespace(type="plugin", args={})
        factory = mock.Mock(return_value=object())

        with (
            mock.patch("eleanor.eleanor.get_output_factory", return_value=factory),
            self.assertRaisesRegex(EleanorException, "expected an OutputSink"),
        ):
            eleanor.load_output_sink()

    def test_load_kernel_constructs_and_sets_up_kernel(self):
        """
        Ensure load_kernel takes the order as a parameter and delegates to spec.build/setup on it.
        """
        from eleanor.kernel.config import Settings as KernelSettings
        from eleanor.kernel.interface import AbstractKernel

        eleanor = _make_eleanor()
        settings = KernelSettings(timeout=None)
        kernel_cfg = mock.Mock()
        kernel_cfg.type = "eq36"
        kernel_cfg.resolved_settings.return_value = settings
        order = SimpleNamespace(kernel=kernel_cfg)

        kernel = mock.Mock(spec=AbstractKernel)
        spec = SimpleNamespace(
            settings_from_dict=mock.Mock(),
            build=mock.Mock(return_value=kernel),
        )
        with mock.patch("eleanor.eleanor.get_kernel_spec", return_value=spec) as get_spec_mock:
            out = eleanor.load_kernel(order, alpha=1)

        self.assertIs(out, kernel)
        get_spec_mock.assert_called_once_with("eq36")
        spec.build.assert_called_once_with(settings, "arg1")
        kernel.setup.assert_called_once_with(order, alpha=1)

    def test_load_kernel_rejects_missing_order_kernel(self):
        """
        Ensure load_kernel raises EleanorException when the order has no kernel config.
        """
        eleanor = _make_eleanor()
        order = SimpleNamespace(kernel=None)
        with self.assertRaisesRegex(EleanorException, "order kernel is required"):
            eleanor.load_kernel(order)


class TestEleanorConstructorOverrides(TestCase):
    """
    Tests covering the constructor-level ``executor=`` and ``output_sink=``
    override parameters.
    """

    def test_constructor_executor_used_for_all_runs_in_session(self):
        """
        Ensure a constructor-supplied executor is used for every run() in the
        session and that build_executor is never called.
        """
        eleanor = _make_eleanor()
        ctor_executor = _FakeExecutor()
        eleanor._executor_override = ctor_executor

        order = _leaf_order()
        sink = mock.Mock()
        seen_executors = []

        def dispatch(order, samples, *a, executor, **kw):
            seen_executors.append(executor)
            return [sink.begin_run.return_value]

        eleanor._dispatch = mock.Mock(side_effect=dispatch)

        with (
            mock.patch("eleanor.eleanor.build_executor") as build_executor,
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink),
        ):
            with eleanor:
                _ = eleanor.run(order, 5)
                _ = eleanor.run(order, 5)

        build_executor.assert_not_called()
        self.assertEqual(len(seen_executors), 2)
        self.assertIs(seen_executors[0], ctor_executor)
        self.assertIs(seen_executors[1], ctor_executor)

    def test_unentered_executor_override_not_entered_or_shut_down_by_eleanor(self):
        """
        Ensure Eleanor reuses an unentered constructor-supplied executor
        as-is and does not manage its lifecycle.
        """
        eleanor = _make_eleanor()
        ctor_executor = _FakeExecutor()  # not entered by caller
        eleanor._executor_override = ctor_executor
        order = _leaf_order()
        sink = mock.Mock()
        eleanor._dispatch = mock.Mock(return_value=[1])

        with (
            mock.patch("eleanor.eleanor.build_executor"),
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink),
        ):
            with eleanor:
                self.assertEqual(ctor_executor.enter_count, 0)
                _ = eleanor.run(order, 1)
                self.assertEqual(ctor_executor.enter_count, 0)

        ctor_executor.shutdown.assert_not_called()

    def test_caller_entered_executor_not_shut_down_by_eleanor(self):
        """
        Ensure Eleanor does not shut down a constructor-supplied executor that
        the caller already entered.
        """
        eleanor = _make_eleanor()
        ctor_executor = _FakeExecutor()
        ctor_executor.__enter__()  # caller enters it first
        eleanor._executor_override = ctor_executor
        order = _leaf_order()
        sink = mock.Mock()
        eleanor._dispatch = mock.Mock(return_value=[1])

        with (
            mock.patch("eleanor.eleanor.build_executor"),
            mock.patch.object(Eleanor, "load_output_sink", return_value=sink),
        ):
            with eleanor:
                _ = eleanor.run(order, 1)
                self.assertEqual(ctor_executor.enter_count, 1)

        ctor_executor.shutdown.assert_not_called()

    def test_run_rejects_per_run_executor_kwarg(self):
        """
        Ensure run() no longer accepts per-run executor overrides.
        """
        eleanor = _make_eleanor()
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'executor'"):
            eleanor.run(_leaf_order(), 1, executor=_FakeExecutor())

    def test_constructor_output_sink_used_for_all_runs_in_session(self):
        """
        Ensure a constructor-supplied output_sink is used for every run() in
        the session and that load_output_sink is never called.
        """
        eleanor = _make_eleanor()
        ctor_sink = mock.Mock()
        ctor_sink.begin_run.return_value = 7
        eleanor._output_sink_override = ctor_sink

        order = _leaf_order()
        eleanor._dispatch = mock.Mock(return_value=[7])

        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=_FakeExecutor()),
            mock.patch.object(Eleanor, "load_output_sink") as load_sink,
        ):
            with eleanor:
                _ = eleanor.run(order, 5)
                _ = eleanor.run(order, 5)

        load_sink.assert_not_called()
        # Both runs reached _dispatch, meaning the sink was supplied without error.
        self.assertEqual(eleanor._dispatch.call_count, 2)
        self.assertIs(eleanor._dispatch.call_args_list[0].kwargs["sink"], ctor_sink)
        self.assertIs(eleanor._dispatch.call_args_list[1].kwargs["sink"], ctor_sink)

    def test_constructor_output_sink_not_finalized_at_exit(self):
        """
        Ensure the constructor-supplied output_sink is not finalized when the
        context manager exits — the caller retains ownership.
        """
        eleanor = _make_eleanor()
        ctor_sink = mock.Mock()
        ctor_sink.begin_run.return_value = 3
        eleanor._output_sink_override = ctor_sink

        order = _leaf_order()
        eleanor._dispatch = mock.Mock(return_value=[3])

        with (
            mock.patch("eleanor.eleanor.build_executor", return_value=_FakeExecutor()),
            mock.patch.object(Eleanor, "load_output_sink"),
        ):
            with eleanor:
                _ = eleanor.run(order, 1)

        ctor_sink.finalize.assert_not_called()

    def test_per_run_output_sink_overrides_constructor_output_sink(self):
        """
        Ensure a per-run output_sink= kwarg takes precedence over the
        constructor-supplied sink, and is finalized at run end.
        """
        eleanor = _make_eleanor()
        ctor_sink = mock.Mock()
        per_run_sink = mock.Mock()
        per_run_sink.begin_run.return_value = 5
        eleanor._output_sink_override = ctor_sink
        eleanor._dispatch = mock.Mock(return_value=[5])

        with mock.patch("eleanor.eleanor.build_executor", return_value=_FakeExecutor()):
            eleanor.run(_leaf_order(), 1, output_sink=per_run_sink)

        self.assertIs(eleanor._dispatch.call_args.kwargs["sink"], per_run_sink)
        per_run_sink.finalize.assert_called_once()
        ctor_sink.finalize.assert_not_called()
