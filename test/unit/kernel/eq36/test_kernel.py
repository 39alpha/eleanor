import contextlib
import io
from types import SimpleNamespace
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.kernel.eq36.kernel import Kernel
from eleanor.kernel.eq36.settings import Eq3Config, Eq6Config, IOPT_1, IOPT_4, Settings
from eleanor.kernel.exceptions import EleanorKernelException
from eleanor.variable_space import (
    AqueousReactant,
    ElementReactant,
    FixedGasReactant,
    GasReactant,
    MineralReactant,
    SolidSolutionReactant,
    SolidSolutionReactantEndMembers,
    SpecialReactant,
    SpecialReactantComposition,
)

from ...common import TestCase


class _DummyPoint:
    def __init__(self,
                 settings,
                 suppressions=None,
                 has_reactants=False,
                 water_mass=1.0,
                 temperature=25.0,
                 pressure=10.0,
                 species=None,
                 elements=None,
                 mineral_reactants=None,
                 solid_solution_reactants=None,
                 special_reactants=None,
                 element_reactants=None,
                 aqueous_reactants=None,
                 gas_reactants=None,
                 fixed_gas_reactants=None,
                 glass_reactants=None):
        self.kernel = SimpleNamespace(settings=settings)
        self.suppressions = [] if suppressions is None else suppressions
        self._has_reactants = has_reactants
        self.water_mass = water_mass
        self.temperature = temperature
        self.pressure = pressure
        self.species = [] if species is None else species
        self.elements = [] if elements is None else elements
        self.mineral_reactants = [] if mineral_reactants is None else mineral_reactants
        self.solid_solution_reactants = [] if solid_solution_reactants is None else solid_solution_reactants
        self.special_reactants = [] if special_reactants is None else special_reactants
        self.element_reactants = [] if element_reactants is None else element_reactants
        self.aqueous_reactants = [] if aqueous_reactants is None else aqueous_reactants
        self.gas_reactants = [] if gas_reactants is None else gas_reactants
        self.fixed_gas_reactants = [] if fixed_gas_reactants is None else fixed_gas_reactants
        self.glass_reactants = [] if glass_reactants is None else glass_reactants

    def has_reactants(self):
        return self._has_reactants

    def has_species_constraint(self, name):
        return any(s.name == name for s in self.species)

    def get_species(self, name):
        for species in self.species:
            if species.name == name:
                return species
        return None

    def reactant_count(self):
        base = sum(
            map(len, [
                self.mineral_reactants,
                self.aqueous_reactants,
                self.gas_reactants,
                self.element_reactants,
                self.special_reactants,
                self.fixed_gas_reactants,
                self.solid_solution_reactants,
            ]))
        return base + sum(len(getattr(glass, "oxides", [])) for glass in self.glass_reactants)


class _DummyCurve:
    def __init__(self, in_domain=True, pressure=10.0):
        self._in_domain = in_domain
        self._pressure = pressure

    def temperature_in_domain(self, _T):
        return self._in_domain

    def __call__(self, _T):
        return self._pressure


class _NamedStringIO(io.StringIO):
    def __init__(self, name):
        super().__init__()
        self.name = name


class TestEq36Kernel(TestCase):
    """
    Tests of selected branch behavior in eleanor.kernel.eq36.kernel.
    """

    def _settings(self, with_eq6=True):
        return Settings(
            timeout=None,
            model="b-dot",
            charge_balance="Cl-",
            eq3_config=Eq3Config(),
            eq6_config=Eq6Config() if with_eq6 else None,
        )

    def _kernel(self):
        return Kernel(settings=self._settings(), data1_dir=".")

    def test_is_soft_exit_accepts_code_60_and_rejects_other_nonzero(self):
        """
        Ensure soft-exit detection accepts code 60 and rejects unrelated nonzero codes.
        """
        kernel = self._kernel()
        self.assertTrue(kernel.is_soft_exit(60))
        self.assertFalse(kernel.is_soft_exit(2))

    def test_get_atomic_weight_requires_setup_and_reads_first_data1(self):
        """
        Ensure get_atomic_weight fails before setup and then reads from the first loaded data1 element map.
        """
        kernel = self._kernel()
        with self.assertRaises(EleanorException):
            kernel.get_atomic_weight("Na")

        kernel._setup = True
        kernel._data1s = [SimpleNamespace(elements={"Na": 22.99})]
        self.assertEqual(kernel.get_atomic_weight("Na"), 22.99)
        self.assertIsNone(kernel.get_atomic_weight("Cl"))

    def test_resolve_kernel_settings_permits_solids_and_sets_titration_when_reactants_present(self):
        """
        Ensure unsuppressed solid-solution runs permit solids and switch EQ6 to titration mode when reactants exist.
        """
        kernel = self._kernel()
        point = _DummyPoint(self._settings(with_eq6=True), has_reactants=True)

        resolved = kernel.resolve_kernel_settings(point)

        self.assertEqual(resolved.eq3_config.iopt_4, IOPT_4.PERMIT_SOLID_SOLUTIONS)
        self.assertEqual(resolved.eq6_config.iopt_4, IOPT_4.PERMIT_SOLID_SOLUTIONS)
        self.assertEqual(resolved.eq6_config.iopt_1, IOPT_1.TITRATION_SYS)

    def test_resolve_kernel_settings_with_all_and_named_suppressions_warns_and_keeps_defaults(self):
        """
        Ensure mixed all/named solid-solution suppressions emit warning and keep solid-solution suppression enabled.
        """
        kernel = self._kernel()
        suppressions = [
            SimpleNamespace(type="solid solution", name=None, exceptions=[]),
            SimpleNamespace(type="solid solutions", name="SS1", exceptions=[]),
        ]
        point = _DummyPoint(self._settings(with_eq6=True), suppressions=suppressions, has_reactants=False)

        with mock.patch("sys.stderr", new=io.StringIO()) as stderr:
            resolved = kernel.resolve_kernel_settings(point)

        self.assertEqual(resolved.eq3_config.iopt_4, IOPT_4.IGNORE_SOLID_SOLUTIONS)
        self.assertEqual(resolved.eq6_config.iopt_4, IOPT_4.IGNORE_SOLID_SOLUTIONS)
        self.assertIn("all solid solutions are suppressed", stderr.getvalue())

    def test_resolve_kernel_settings_rejects_solid_solution_exemptions(self):
        """
        Ensure solid-solution suppression exceptions are rejected as unsupported.
        """
        kernel = self._kernel()
        suppressions = [SimpleNamespace(type="solid solution", name=None, exceptions=[object()])]
        point = _DummyPoint(self._settings(with_eq6=True), suppressions=suppressions)

        with self.assertRaises(NotImplementedError):
            kernel.resolve_kernel_settings(point)

    def test_resolve_kernel_settings_without_eq6_only_updates_eq3(self):
        """
        Ensure unsuppressed solid-solution mode still updates EQ3 when EQ6 config is disabled.
        """
        kernel = self._kernel()
        point = _DummyPoint(self._settings(with_eq6=False), has_reactants=True)

        resolved = kernel.resolve_kernel_settings(point)

        self.assertEqual(resolved.eq3_config.iopt_4, IOPT_4.PERMIT_SOLID_SOLUTIONS)
        self.assertIsNone(resolved.eq6_config)

    def test_resolve_kernel_settings_rejects_unexpected_settings_type(self):
        """
        Ensure resolve_kernel_settings rejects points whose kernel settings are not eq36 Settings instances.
        """
        kernel = self._kernel()
        point = _DummyPoint(self._settings())
        point.kernel.settings = object()

        with self.assertRaises(TypeError):
            kernel.resolve_kernel_settings(point)

    def test_find_data1_filters_candidates_and_returns_exact_pressure_match(self):
        """
        Ensure find_data1 ignores curves outside domain/non-matching pressure and returns the matching data1.
        """
        kernel = self._kernel()
        kernel._data1s = [
            SimpleNamespace(filename="none", tp_curve=None),
            SimpleNamespace(filename="outside", tp_curve=_DummyCurve(in_domain=False, pressure=10.0)),
            SimpleNamespace(filename="wrong", tp_curve=_DummyCurve(in_domain=True, pressure=7.5)),
            SimpleNamespace(filename="right", tp_curve=_DummyCurve(in_domain=True, pressure=10.0)),
        ]
        point = _DummyPoint(self._settings(), temperature=25.0, pressure=10.0)

        data1 = kernel.find_data1(point)

        self.assertEqual(data1.filename, "right")

    def test_find_data1_raises_when_no_curve_matches_temperature_pressure(self):
        """
        Ensure find_data1 raises when no data1 curve satisfies both temperature-domain and pressure equality checks.
        """
        kernel = self._kernel()
        kernel._data1s = [SimpleNamespace(filename="wrong", tp_curve=_DummyCurve(in_domain=True, pressure=9.0))]
        point = _DummyPoint(self._settings(), temperature=25.0, pressure=10.0)

        with self.assertRaises(EleanorKernelException):
            kernel.find_data1(point)

    def test_find_data1_multiple_matches_verbose_warns_and_returns_first(self):
        """
        Ensure find_data1 emits verbose warning for multiple matches and returns the first match.
        """
        kernel = self._kernel()
        first = SimpleNamespace(filename="first", tp_curve=_DummyCurve(in_domain=True, pressure=10.0))
        second = SimpleNamespace(filename="second", tp_curve=_DummyCurve(in_domain=True, pressure=10.0))
        kernel._data1s = [first, second]
        point = _DummyPoint(self._settings(), temperature=25.0, pressure=10.0)

        with mock.patch("builtins.print") as print_mock:
            data1 = kernel.find_data1(point, verbose=True)

        self.assertIs(data1, first)
        print_mock.assert_called_once_with(
            "warning: multiple data1 files pass through temperature 25.0 and pressure 10.0; choosing first")

    def test_run_eq3_only_finds_data1_and_sets_eq3_timestamps(self):
        """
        Ensure run executes eq3-only flow, resolves missing data1 via find_data1, and stamps eq3 result timing.
        """
        kernel = self._kernel()
        settings = self._settings(with_eq6=False)
        point = _DummyPoint(settings)
        found_data1 = SimpleNamespace(filename="/tmp/found/run.d1")
        eq3_result = SimpleNamespace(stage="eq3")

        with (
            mock.patch.object(kernel, "resolve_kernel_settings", return_value=settings) as resolve,
            mock.patch.object(kernel, "find_data1", return_value=found_data1) as find_data1,
            mock.patch.object(kernel, "write_eq3_input", return_value="problem.3i") as write_eq3_input,
            mock.patch("eleanor.kernel.eq36.kernel.eq3") as eq3_mock,
            mock.patch("eleanor.kernel.eq36.kernel.Kernel.read_eq3_output", return_value=eq3_result) as read_eq3_output,
            mock.patch("eleanor.kernel.eq36.kernel.eq6") as eq6_mock,
            mock.patch("eleanor.kernel.eq36.kernel.read_pickup_lines") as read_pickup_lines,
            mock.patch("eleanor.kernel.eq36.kernel.Kernel.read_eq6_output") as read_eq6_output,
            mock.patch("eleanor.kernel.eq36.kernel.Data1.from_file") as from_file,
        ):
            output = kernel.run(point, verbose=True)

        resolve.assert_called_once_with(point)
        find_data1.assert_called_once_with(point, verbose=True)
        self.assertEqual(settings.data1_file, "/tmp/found/run.d1")
        write_eq3_input.assert_called_once_with(point, found_data1, verbose=True)
        eq3_mock.assert_called_once_with("/tmp/found/run.d1", "problem.3i", timeout=settings.timeout)
        read_eq3_output.assert_called_once_with()
        eq6_mock.assert_not_called()
        read_pickup_lines.assert_not_called()
        read_eq6_output.assert_not_called()
        from_file.assert_not_called()
        self.assertEqual(output, [eq3_result])
        self.assertLessEqual(eq3_result.start_date, eq3_result.complete_date)

    def test_run_eq3_eq6_uses_preconfigured_data1_and_stamps_eq6_points(self):
        """
        Ensure run loads preconfigured data1, executes eq3+eq6 flow, and stamps timing on each eq6 result point.
        """
        kernel = self._kernel()
        settings = self._settings(with_eq6=True)
        settings.data1_file = "/tmp/configured/run.d1"
        point = _DummyPoint(settings)
        loaded_data1 = SimpleNamespace(filename="/tmp/configured/run.d1")
        eq3_result = SimpleNamespace(stage="eq3")
        eq6_results = [SimpleNamespace(stage="eq6-a"), SimpleNamespace(stage="eq6-b")]
        pickup_lines = ["pickup-a\n", "pickup-b\n"]

        with (
            mock.patch.object(kernel, "resolve_kernel_settings", return_value=settings) as resolve,
            mock.patch.object(kernel, "find_data1") as find_data1,
            mock.patch("eleanor.kernel.eq36.kernel.Data1.from_file", return_value=loaded_data1) as from_file,
            mock.patch.object(kernel, "write_eq3_input", return_value="problem.3i") as write_eq3_input,
            mock.patch("eleanor.kernel.eq36.kernel.eq3") as eq3_mock,
            mock.patch("eleanor.kernel.eq36.kernel.Kernel.read_eq3_output", return_value=eq3_result) as read_eq3_output,
            mock.patch("eleanor.kernel.eq36.kernel.read_pickup_lines", return_value=pickup_lines) as read_pickup_lines,
            mock.patch.object(kernel, "write_eq6_input", return_value="problem.6i") as write_eq6_input,
            mock.patch("eleanor.kernel.eq36.kernel.eq6") as eq6_mock,
            mock.patch("eleanor.kernel.eq36.kernel.Kernel.read_eq6_output", return_value=eq6_results) as read_eq6_output,
        ):
            output = kernel.run(point, verbose=True)

        resolve.assert_called_once_with(point)
        find_data1.assert_not_called()
        from_file.assert_called_once_with("/tmp/configured/run.d1")
        write_eq3_input.assert_called_once_with(point, loaded_data1, verbose=True)
        eq3_mock.assert_called_once_with("/tmp/configured/run.d1", "problem.3i", timeout=settings.timeout)
        read_eq3_output.assert_called_once_with()
        read_pickup_lines.assert_called_once_with()
        write_eq6_input.assert_called_once_with(point, pickup_lines=pickup_lines, verbose=True)
        eq6_mock.assert_called_once_with("/tmp/configured/run.d1", "problem.6i", timeout=settings.timeout)
        read_eq6_output.assert_called_once_with(track_path=settings.track_path)
        self.assertEqual(output, [eq3_result, *eq6_results])
        self.assertLessEqual(eq3_result.start_date, eq3_result.complete_date)
        for result in eq6_results:
            self.assertLessEqual(result.start_date, result.complete_date)

    def test_run_reraises_eleanor_exception_without_wrapping(self):
        """
        Ensure run re-raises EleanorException subclasses directly.
        """
        kernel = self._kernel()
        point = _DummyPoint(self._settings())
        error = EleanorKernelException("known kernel failure")

        with mock.patch.object(kernel, "resolve_kernel_settings", side_effect=error):
            with self.assertRaises(EleanorKernelException) as context:
                kernel.run(point)

        self.assertIs(context.exception, error)

    def test_run_wraps_unexpected_exceptions_with_generic_eleanor_exception(self):
        """
        Ensure run wraps unexpected exceptions with a generic EleanorException while preserving the original cause.
        """
        kernel = self._kernel()
        point = _DummyPoint(self._settings())
        cause = RuntimeError("unexpected failure")

        with mock.patch.object(kernel, "resolve_kernel_settings", side_effect=cause):
            with self.assertRaises(EleanorException) as context:
                kernel.run(point)

        self.assertIn("an unexpected error occured", str(context.exception))
        self.assertIs(context.exception.__cause__, cause)

    def test_write_switch_grid_eq3_includes_iopg_rows(self):
        """
        Ensure write_switch_grid prints the Eq3 IOPG rows.
        """
        kernel = self._kernel()
        handle = io.StringIO()

        kernel.write_switch_grid(handle, Eq3Config())

        output = handle.getvalue()
        self.assertIn("iopg1-10=", output)
        self.assertIn("iopg11-20=", output)

    def test_write_switch_grid_eq6_omits_iopg_rows(self):
        """
        Ensure write_switch_grid omits Eq3-only IOPG rows for Eq6Config.
        """
        kernel = self._kernel()
        handle = io.StringIO()

        kernel.write_switch_grid(handle, Eq6Config())

        output = handle.getvalue()
        self.assertNotIn("iopg1-10=", output)
        self.assertNotIn("iopg11-20=", output)

    def test_write_switch_grid_eq3_verbose_uses_make_verbose(self):
        """
        Ensure write_switch_grid calls Eq3 make_verbose in verbose mode and prints rows from the returned config.
        """
        kernel = self._kernel()
        base_cfg = Eq3Config()
        verbose_cfg = Eq3Config(iopt_1=IOPT_1.FLOW_THROUGH_SYS)
        expected_line = "  iopt1-10= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}".format(
            *verbose_cfg.iopt[:10])
        handle = io.StringIO()

        with mock.patch.object(base_cfg, "make_verbose", return_value=verbose_cfg) as make_verbose:
            kernel.write_switch_grid(handle, base_cfg, verbose=True)

        make_verbose.assert_called_once_with()
        self.assertIn(expected_line, handle.getvalue())

    def test_copy_data_uses_existing_data1_file_without_find_data1(self):
        """
        Ensure copy_data uses preconfigured data1 path directly and skips find_data1 lookup.
        """
        kernel = self._kernel()
        settings = self._settings()
        settings.data1_file = "/tmp/source/testdata.d1"
        point = _DummyPoint(settings)

        with (
            mock.patch.object(kernel, "resolve_kernel_settings", return_value=settings) as resolve,
            mock.patch.object(kernel, "find_data1") as find_data1,
            mock.patch("eleanor.kernel.eq36.kernel.copyfile") as copyfile_mock,
        ):
            kernel.copy_data(point, dir="target")

        resolve.assert_called_once_with(point)
        find_data1.assert_not_called()
        copyfile_mock.assert_called_once_with("/tmp/source/testdata.d1", "target/testdata.d1")

    def test_copy_data_finds_data1_when_missing_and_updates_settings(self):
        """
        Ensure copy_data resolves missing data1 path via find_data1 and forwards verbose flag.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(settings)
        found = SimpleNamespace(filename="/tmp/found/fresh.d1")

        with (
            mock.patch.object(kernel, "resolve_kernel_settings", return_value=settings) as resolve,
            mock.patch.object(kernel, "find_data1", return_value=found) as find_data1,
            mock.patch("eleanor.kernel.eq36.kernel.copyfile") as copyfile_mock,
        ):
            kernel.copy_data(point, dir="target", verbose=True)

        resolve.assert_called_once_with(point)
        find_data1.assert_called_once_with(point, verbose=True)
        self.assertEqual(settings.data1_file, "/tmp/found/fresh.d1")
        copyfile_mock.assert_called_once_with("/tmp/found/fresh.d1", "target/fresh.d1")

    def test_setup_filters_data1_files_by_tp_curve_domain_and_sets_setup_flag(self):
        """
        Ensure setup only retains data1 files whose tp-curves intersect the requested T/P domain.
        """
        kernel = self._kernel()
        order = SimpleNamespace(
            temperature=SimpleNamespace(range=lambda: (1.0, 2.0)),
            pressure=SimpleNamespace(range=lambda: (3.0, 4.0)),
        )
        rejected = SimpleNamespace(tp_curve=SimpleNamespace(set_domain=mock.Mock(return_value=False)))
        accepted = SimpleNamespace(tp_curve=SimpleNamespace(set_domain=mock.Mock(return_value=True)))

        with (
            mock.patch("eleanor.kernel.eq36.kernel.tool_room.WorkingDirectory",
                       return_value=contextlib.nullcontext()) as wd_mock,
            mock.patch("eleanor.kernel.eq36.kernel.tool_room.find_files",
                       return_value=([], ["first.d1", "second.d1"])) as find_files_mock,
            mock.patch("eleanor.kernel.eq36.kernel.os.path.realpath",
                       side_effect=lambda path: f"/abs/{path}") as realpath_mock,
            mock.patch("eleanor.kernel.eq36.kernel.Data1.from_file",
                       side_effect=[rejected, accepted]) as from_file_mock,
        ):
            kernel.setup(order)

        wd_mock.assert_called_once_with(".")
        find_files_mock.assert_called_once_with(".d1")
        self.assertEqual(realpath_mock.call_count, 2)
        from_file_mock.assert_has_calls([mock.call("/abs/first.d1"), mock.call("/abs/second.d1")])
        rejected.tp_curve.set_domain.assert_called_once_with((1.0, 2.0), (3.0, 4.0))
        accepted.tp_curve.set_domain.assert_called_once_with((1.0, 2.0), (3.0, 4.0))
        self.assertTrue(kernel._setup)
        self.assertEqual(kernel._data1s, [accepted])

    def test_validate_order_raises_kernel_has_not_been_setup(self):
        """
        Ensure validate_order raises when the kernel has not been setup.
        """
        kernel = self._kernel()
        order = SimpleNamespace(
            temperature=SimpleNamespace(range=lambda: (10.0, 20.0)),
            pressure=SimpleNamespace(range=lambda: (30.0, 40.0)),
        )
        rejected = SimpleNamespace(tp_curve=SimpleNamespace(set_domain=mock.Mock(return_value=False)))

        with (
            mock.patch("eleanor.kernel.eq36.kernel.tool_room.WorkingDirectory",
                       return_value=contextlib.nullcontext()),
            mock.patch("eleanor.kernel.eq36.kernel.tool_room.find_files", return_value=([], ["only.d1"])),
            mock.patch("eleanor.kernel.eq36.kernel.os.path.realpath", side_effect=lambda path: path),
            mock.patch("eleanor.kernel.eq36.kernel.Data1.from_file", return_value=rejected),
        ):
            with self.assertRaises(EleanorException):
                kernel.validate_order(order)

        self.assertFalse(kernel._setup)
        self.assertEqual(kernel._data1s, [])

    def test_validate_order_raises_when_no_data1_curves_intersect_target_domain(self):
        """
        Ensure validate_order raises when no discovered data1 file supports the requested temperature/pressure domain.
        """
        kernel = self._kernel()
        order = SimpleNamespace(
            temperature=SimpleNamespace(range=lambda: (10.0, 20.0)),
            pressure=SimpleNamespace(range=lambda: (30.0, 40.0)),
        )
        rejected = SimpleNamespace(tp_curve=SimpleNamespace(set_domain=mock.Mock(return_value=False)))

        with (
            mock.patch("eleanor.kernel.eq36.kernel.tool_room.WorkingDirectory",
                       return_value=contextlib.nullcontext()),
            mock.patch("eleanor.kernel.eq36.kernel.tool_room.find_files", return_value=([], ["only.d1"])),
            mock.patch("eleanor.kernel.eq36.kernel.os.path.realpath", side_effect=lambda path: path),
            mock.patch("eleanor.kernel.eq36.kernel.Data1.from_file", return_value=rejected),
        ):
            kernel.setup(order)
            with self.assertRaises(EleanorException):
                kernel.validate_order(order)

        self.assertTrue(kernel._setup)
        self.assertEqual(kernel._data1s, [])

    def test_constrain_appends_temperature_and_tp_constraints_in_order(self):
        """
        Ensure constrain appends temperature-range and T/P-curve constraints and returns the same boatswain.
        """
        kernel = self._kernel()
        kernel._data1s = [SimpleNamespace(name="d1")]
        boatswain = SimpleNamespace(
            order=SimpleNamespace(temperature="TEMP", pressure="PRESS"),
            constraints=[],
        )

        with (
            mock.patch("eleanor.kernel.eq36.kernel.TemperatureRangeConstraint", return_value="TRANGE") as trange_mock,
            mock.patch("eleanor.kernel.eq36.kernel.TPCurveConstraint", return_value="TPCURVE") as tpcurve_mock,
        ):
            out = kernel.constrain(boatswain)

        self.assertIs(out, boatswain)
        self.assertEqual(boatswain.constraints, ["TRANGE", "TPCURVE"])
        trange_mock.assert_called_once_with("TEMP", kernel._data1s)
        tpcurve_mock.assert_called_once_with("TEMP", "PRESS", kernel._data1s)

    def test_write_eq3_input_requires_setup_before_writing(self):
        """
        Ensure write_eq3_input fails fast when kernel setup has not been completed.
        """
        kernel = self._kernel()
        point = _DummyPoint(self._settings())

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq3_input(point, data1=SimpleNamespace())

    def test_write_eq3_input_rejects_unconstrained_non_fO2_redox_species(self):
        """
        Ensure write_eq3_input raises when configured redox species is not constrained on the variable-space point.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "pe"
        point = _DummyPoint(settings, species=[SimpleNamespace(name="H+", value=-7.0)])

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq3_input(point, data1=SimpleNamespace())

    def test_write_eq3_input_fO2_redox_requires_O2_species_lookup(self):
        """
        Ensure write_eq3_input raises when redox_species=fO2 but O2(g) lookup is missing at write time.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "fO2"
        point = _DummyPoint(settings, species=[SimpleNamespace(name="fO2", value=-60.0)])
        handle = _NamedStringIO("problem.3i")

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq3_input(point, data1=SimpleNamespace(get_basis_species=lambda _x: None), file=handle)

    def test_write_eq3_input_uses_fO2_fallback_via_O2_species_and_writes_expected_general_fields(self):
        """
        Ensure write_eq3_input accepts O2(g) as fallback for fO2 and emits expected general redox fields.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "fO2"
        point = _DummyPoint(settings,
                            species=[
                                SimpleNamespace(name="O2(g)", value=-60.0),
                                SimpleNamespace(name="H+", value=-7.0),
                            ])
        handle = _NamedStringIO("problem.3i")

        path = kernel.write_eq3_input(point, data1=SimpleNamespace(get_basis_species=lambda _x: None), file=handle)
        output = handle.getvalue()

        self.assertEqual(path, "problem.3i")
        self.assertIn("irdxc3=   0", output)
        self.assertIn("uredox= None", output)
        self.assertIn("species= H+", output)

    def test_write_eq3_input_emits_custom_water_mass_in_scamas_field(self):
        """
        Ensure write_eq3_input writes the correct scamas line when water_mass is not the default 1kg.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "fO2"
        point = _DummyPoint(settings,
                            water_mass=0.5,
                            species=[SimpleNamespace(name="O2(g)", value=-60.0)])
        handle = _NamedStringIO("problem.3i")

        kernel.write_eq3_input(point, data1=SimpleNamespace(get_basis_species=lambda _x: None), file=handle)
        output = handle.getvalue()

        self.assertIn("scamas=  5.00000E-01", output)
        self.assertNotIn("scamas=  1.00000E+00", output)

    def test_write_eq3_input_raises_when_element_has_no_basis_species(self):
        """
        Ensure write_eq3_input raises when an element in the point has no matching basis species in data1.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "fO2"
        point = _DummyPoint(settings,
                            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
                            elements=[SimpleNamespace(name="Na", log_molality=-3.0)])
        handle = _NamedStringIO("problem.3i")
        data1 = SimpleNamespace(get_basis_species=lambda _name: None)

        with self.assertRaises(Exception):
            kernel.write_eq3_input(point, data1=data1, file=handle)

    def test_write_eq6_input_requires_eq6_config(self):
        """
        Ensure write_eq6_input fails fast when eq6 configuration is disabled.
        """
        kernel = self._kernel()
        point = _DummyPoint(self._settings(with_eq6=False))

        with self.assertRaises(ValueError):
            kernel.write_eq6_input(point)

    def test_write_eq6_input_rejects_unconstrained_non_fO2_redox_species(self):
        """
        Ensure write_eq6_input raises when a non-fO2 redox species is unconstrained.
        """
        kernel = self._kernel()
        settings = self._settings()
        settings.redox_species = "pe"
        point = _DummyPoint(settings, species=[SimpleNamespace(name="H+", value=-7.0)])

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq6_input(point)

    def test_write_eq6_input_rejects_invalid_mineral_reactant_type(self):
        """
        Ensure write_eq6_input surfaces attribute errors for invalid mineral reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            mineral_reactants=[object()],
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_unsupported_suppression_type(self):
        """
        Ensure write_eq6_input rejects suppression types outside supported categories.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            suppressions=[SimpleNamespace(type="unexpected", name=None, exceptions=[])],
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_fixed_gas_reactant_type(self):
        """
        Ensure write_eq6_input surfaces attribute errors for invalid fixed gas reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            fixed_gas_reactants=[object()],
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_solid_solution_reactant_type(self):
        """
        Ensure write_eq6_input surfaces attribute errors for invalid solid solution reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            solid_solution_reactants=[object()],
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_special_reactant_type(self):
        """
        Ensure write_eq6_input surfaces attribute errors for invalid special reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            special_reactants=[object()],
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_element_reactant_type(self):
        """
        Ensure write_eq6_input surfaces attribute errors for invalid element reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            element_reactants=[object()],
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_aqueous_reactant_type(self):
        """
        Ensure write_eq6_input surfaces attribute errors for invalid aqueous reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            aqueous_reactants=[object()],
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_gas_reactant_type(self):
        """
        Ensure write_eq6_input surfaces attribute errors for invalid gas reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            gas_reactants=[object()],
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_writes_all_reactant_blocks_for_valid_typed_reactants(self):
        """
        Ensure write_eq6_input emits blocks for all supported reactant categories with valid typed reactants.
        """
        kernel = self._kernel()
        settings = self._settings()

        mineral = MineralReactant(name="Calcite", log_moles=0.0, titration_rate=1.0, id=None)
        solid_solution = SolidSolutionReactant(
            name="Albite_ss",
            log_moles=0.0,
            titration_rate=1.0,
            end_members=[SolidSolutionReactantEndMembers(name="EM1", fraction=1.0)],
            id=None,
        )
        special = SpecialReactant(
            name="SR",
            log_moles=0.0,
            titration_rate=1.0,
            composition=[SpecialReactantComposition(element="Na", count=1)],
            id=None,
        )
        element = ElementReactant(name="Na", log_moles=0.0, titration_rate=1.0, id=None)
        aqueous = AqueousReactant(name="Na+", log_moles=0.0, titration_rate=1.0, id=None)
        gas = GasReactant(name="CO2(g)", log_moles=0.0, titration_rate=1.0, id=None)
        fixed_gas = FixedGasReactant(name="O2(g)", log_moles=0.0, log_fugacity=-50.0, id=None)
        glass = SimpleNamespace(
            oxides=[
                SimpleNamespace(
                    name="SiO2",
                    log_moles=0.0,
                    titration_rate=1.0,
                    composition=[
                        SimpleNamespace(element="Si", count=1),
                        SimpleNamespace(element="O", count=2),
                    ],
                )
            ])

        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            suppressions=[SimpleNamespace(type="minerals", name=None, exceptions=[SimpleNamespace(name="Quartz")])],
            mineral_reactants=[mineral],
            solid_solution_reactants=[solid_solution],
            special_reactants=[special],
            element_reactants=[element],
            aqueous_reactants=[aqueous],
            gas_reactants=[gas],
            fixed_gas_reactants=[fixed_gas],
            glass_reactants=[glass],
        )
        handle = _NamedStringIO("problem.6i")

        path = kernel.write_eq6_input(point, file=handle)
        output = handle.getvalue()

        self.assertEqual(path, "problem.6i")
        self.assertIn("reactant= Calcite", output)
        self.assertIn("reactant= Albite_ss", output)
        self.assertIn("EM1", output)
        self.assertIn("reactant=  SR", output)
        self.assertIn("reactant=  Na", output)
        self.assertIn("reactant= Na+", output)
        self.assertIn("reactant= CO2(g)", output)
        self.assertIn("reactant=  SiO2", output)
        self.assertIn("species= O2(g)", output)
        self.assertIn("nxopt=  1", output)
        self.assertIn("nxopex=  1", output)
        self.assertIn("species= Quartz", output)

    def test_write_eq6_input_writes_header_and_appends_pickup_lines(self):
        """
        Ensure write_eq6_input emits basic header data and appends pickup lines verbatim.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(settings, species=[SimpleNamespace(name="O2(g)", value=-60.0)])
        handle = _NamedStringIO("problem.6i")
        pickup_lines = ["pickup-a\n", "pickup-b\n"]

        path = kernel.write_eq6_input(point, file=handle, pickup_lines=pickup_lines)
        output = handle.getvalue()

        self.assertEqual(path, "problem.6i")
        self.assertIn("EQ3NR input file name= problem.6i", output)
        self.assertIn("nffg=", output)
        self.assertTrue(output.endswith("pickup-a\npickup-b\n"))

    def test_write_eq6_input_string_path_uses_open_wrapper_branch(self):
        """
        Ensure write_eq6_input follows the string-path wrapper branch and writes using opened handle.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(settings, species=[SimpleNamespace(name="O2(g)", value=-60.0)])
        handle = _NamedStringIO("wrapped.6i")

        with mock.patch("builtins.open", return_value=handle) as open_mock:
            path = kernel.write_eq6_input(point, file="wrapped.6i")

        open_mock.assert_called_once_with("wrapped.6i", "w")
        self.assertEqual(path, "wrapped.6i")

    def test_write_eq6_input_none_file_defaults_to_problem_6i(self):
        """
        Ensure write_eq6_input default file=None branch opens problem.6i.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(settings, species=[SimpleNamespace(name="O2(g)", value=-60.0)])
        handle = _NamedStringIO("problem.6i")

        with mock.patch("builtins.open", return_value=handle) as open_mock:
            path = kernel.write_eq6_input(point, file=None)

        self.assertEqual(path, "problem.6i")
        open_mock.assert_called_once_with("problem.6i", "w")

    def test_write_eq3_input_string_path_wrapper_and_positive_h_branch(self):
        """
        Ensure write_eq3_input string-path wrapper branch executes and positive H+ uses the alternate covali formatting path.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "pe"
        settings.basis_map = {"Na+": "NaOH(aq)"}
        point = _DummyPoint(
            settings,
            species=[
                SimpleNamespace(name="pe", value=4.0),
                SimpleNamespace(name="H+", value=7.0),
            ],
            elements=[SimpleNamespace(name="Na", log_molality=-3.0)],
            suppressions=[SimpleNamespace(name="Quartz", type=None, exceptions=[])],
        )
        data1 = SimpleNamespace(get_basis_species=lambda _name: SimpleNamespace(name="Na+"))
        handle = _NamedStringIO("wrapped.3i")

        with mock.patch("builtins.open", return_value=contextlib.nullcontext(handle)) as open_mock:
            path = kernel.write_eq3_input(point, data1=data1, file="wrapped.3i")

        output = handle.getvalue()
        self.assertEqual(path, "wrapped.3i")
        open_mock.assert_called_once_with("wrapped.3i", "w")
        self.assertIn("irdxc3=   1", output)
        self.assertIn("uredox= pe", output)
        self.assertIn("switch with= NaOH(aq)", output)
        self.assertIn("species= Quartz", output)
        self.assertIn("species= Na+", output)

    def test_write_eq3_input_none_file_defaults_to_problem_3i(self):
        """
        Ensure write_eq3_input default file=None branch opens problem.3i.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "fO2"
        point = _DummyPoint(settings, species=[SimpleNamespace(name="O2(g)", value=-60.0)])
        data1 = SimpleNamespace(get_basis_species=lambda _name: None)
        handle = _NamedStringIO("problem.3i")

        with mock.patch("builtins.open", return_value=handle) as open_mock:
            path = kernel.write_eq3_input(point, data1=data1, file=None)

        self.assertEqual(path, "problem.3i")
        open_mock.assert_called_once_with("problem.3i", "w")

    def test_write_eq6_input_suppression_branches_for_none_named_and_solid_solution_types(self):
        """
        Ensure write_eq6_input executes suppression.type None, named mineral suppression, and solid-solution pass branches.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            suppressions=[
                SimpleNamespace(type=None, name="Calcite", exceptions=[]),
                SimpleNamespace(type="minerals", name="Hematite", exceptions=[]),
                SimpleNamespace(type="solid solutions", name=None, exceptions=[]),
            ],
        )
        handle = _NamedStringIO("problem.6i")

        path = kernel.write_eq6_input(point, file=handle)
        output = handle.getvalue()

        self.assertEqual(path, "problem.6i")
        self.assertIn("nxopt=  0", output)
    def test_write_eq6_input_rejects_suppression_without_name_and_type(self):
        """
        Ensure write_eq6_input rejects suppressions that provide neither a type nor a name.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            suppressions=[SimpleNamespace(type=None, name=None, exceptions=[])],
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_all_named_suppressions_with_exceptions(self):
        """
        Ensure write_eq6_input rejects named suppressions when exceptions are provided, regardless of suppression type.
        """
        kernel = self._kernel()
        settings = self._settings()
        cases = [
            SimpleNamespace(type=None, name="Calcite", exceptions=[SimpleNamespace(name="Quartz")]),
            SimpleNamespace(type="minerals", name="Hematite", exceptions=[SimpleNamespace(name="Quartz")]),
            SimpleNamespace(type="solid solutions", name="Feldspar_ss", exceptions=[SimpleNamespace(name="Albite")]),
        ]

        for suppression in cases:
            with self.subTest(type=suppression.type, name=suppression.name):
                point = _DummyPoint(
                    settings,
                    species=[SimpleNamespace(name="O2(g)", value=-60.0)],
                    suppressions=[suppression],
                )
                handle = _NamedStringIO("problem.6i")
                with self.assertRaises(EleanorKernelException):
                    kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_named_mineral_without_exceptions_does_not_enable_all_mineral_suppression(self):
        """
        Ensure named mineral suppressions without exceptions do not trigger suppress-all-minerals mode.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            suppressions=[SimpleNamespace(type="minerals", name="Hematite", exceptions=[])],
        )
        handle = _NamedStringIO("problem.6i")

        path = kernel.write_eq6_input(point, file=handle)
        output = handle.getvalue()

        self.assertEqual(path, "problem.6i")
        self.assertIn("nxopt=  0", output)
        self.assertNotIn("option= All", output)
        self.assertNotIn("nxopex=  0", output)

    def test_write_eq6_input_suppress_all_minerals_without_exceptions_prints_empty_nxopex(self):
        """
        Ensure write_eq6_input hits suppress_minerals + no-exceptions branch and prints nxopex with zero.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _DummyPoint(
            settings,
            species=[SimpleNamespace(name="O2(g)", value=-60.0)],
            suppressions=[SimpleNamespace(type="minerals", name=None, exceptions=[])],
        )
        handle = _NamedStringIO("problem.6i")

        path = kernel.write_eq6_input(point, file=handle)
        output = handle.getvalue()

        self.assertEqual(path, "problem.6i")
        self.assertIn("nxopt=  1", output)
        self.assertIn("nxopex=  0", output)

    def test_read_eq3_output_maps_parser_data_and_applies_sentinel_conversions(self):
        """
        Ensure read_eq3_output maps parser payload fields and converts sentinel values to -inf as expected.
        """
        eq3_data = {
            "temperature": 25.0,
            "pressure": 10.0,
            "log_fO2": -60.0,
            "log_activity_water": -0.01,
            "mole_fraction_water": 0.98,
            "log_activity_coefficient_water": 0.02,
            "osmotic_coefficient": 0.8,
            "stoichiometric_osmotic_coefficient": 0.81,
            "log_sum_molalities": -1.0,
            "log_sum_stoichiometric_molalities": -0.9,
            "log_ionic_strength": -2.0,
            "log_stoichiometric_ionic_strength": -1.8,
            "log_ionic_asymmetry": -2.2,
            "log_stoichiometric_ionic_asymmetry": -2.1,
            "solvent_mass": 1.0,
            "solute_mass": 0.1,
            "solution_mass": 1.1,
            "solution_volume": 1.2,
            "solvent_fraction": 0.9,
            "solute_fraction": 0.1,
            "tds": 100.0,
            "pH": {"NBS pH scale": {"pH": 7.0, "Eh": 0.1, "pe-": 4.0, "Ah": 1.2}},
            "pcH": None,
            "pHCl": None,
            "cations": 1.0,
            "anions": 1.0,
            "total_charge": 0.0,
            "mean_charge": 0.0,
            "charge_imbalance": 0.0,
            "alkalinity": {"Extended": {"Total": 2.5}},
            "elements": {"Na": {"log_molality": -3.0, "mass_fraction": 0.2}},
            "aqueous": {
                "H2O": {"molality": 0.0, "log_molality": -9.0, "log_activity": -99999, "log_gamma": 0.0},
                "Na+": {"molality": 0.1, "log_molality": -1.0, "log_activity": -1.1, "log_gamma": 0.2},
            },
            "solids": {
                "pure_solids": {
                    "Calcite": {
                        "log_qk": 0.2,
                        "affinity": 1.0,
                        "moles": -99999,
                        "log_moles": -5.0,
                        "mass": -99999,
                        "log_mass": -4.0,
                        "volume": -99999,
                        "log_volume": -3.0,
                    }
                },
                "solid_solutions": {
                    "SS1": {
                        "log_qk": 0.1,
                        "affinity": 0.2,
                        "log_moles": -2.0,
                        "log_mass": -1.5,
                        "log_volume": -1.2,
                        "end_members": {
                            "EM1": {
                                "log_qk": 0.3,
                                "affinity": 0.4,
                                "log_moles": -6.0,
                                "log_mass": -5.0,
                                "log_volume": -4.0,
                            }
                        },
                    }
                },
            },
            "gases": {"CO2(g)": {"log_fugacity": -3.0}},
            "redox": {"O2/H2O": {"Eh": 0.1, "pe-": 4.0, "log_fO2": -60.0, "Ah": 1.2}},
        }

        parser = SimpleNamespace(data=eq3_data)
        parser_instance = mock.Mock()
        parser_instance.parse.return_value = parser

        with mock.patch("eleanor.kernel.eq36.kernel.OutputParser3", return_value=parser_instance):
            point = Kernel.read_eq3_output()

        self.assertEqual(point.stage, "eq3")
        self.assertEqual(point.temperature, 25.0)
        self.assertEqual(point.extended_alkalinity, 2.5)
        self.assertEqual(len(point.elements), 1)
        self.assertEqual(len(point.aqueous_species), 2)
        self.assertEqual(point.aqueous_species[0].log_molality, -float("inf"))
        self.assertEqual(point.aqueous_species[0].log_activity, -float("inf"))
        self.assertEqual(point.pure_solids[0].log_moles, -float("inf"))
        self.assertEqual(point.pure_solids[0].log_mass, -float("inf"))
        self.assertEqual(point.pure_solids[0].log_volume, -float("inf"))

    def test_read_eq6_output_track_path_false_keeps_last_step_only(self):
        """
        Ensure read_eq6_output with track_path=False returns only the last parsed step.
        """
        def _step(log_xi):
            return {
                "log_xi": log_xi,
                "temperature": 25.0,
                "pressure": 10.0,
                "pH": {"NBS pH scale": {"pH": 7.0, "Eh": 0.1, "pe-": 4.0, "Ah": 1.2}},
                "pHCl": None,
                "log_fO2": -60.0,
                "log_activity_water": -0.01,
                "mole_fraction_water": 0.98,
                "log_activity_coefficient_water": 0.02,
                "osmotic_coefficient": 0.8,
                "stoichiometric_osmotic_coefficient": 0.81,
                "log_sum_molalities": -1.0,
                "log_sum_stoichiometric_molalities": -0.9,
                "log_ionic_strength": -2.0,
                "log_stoichiometric_ionic_strength": -1.8,
                "log_ionic_asymmetry": -2.2,
                "log_stoichiometric_ionic_asymmetry": -2.1,
                "solvent_mass": 1.0,
                "solute_mass": 0.1,
                "solution_mass": 1.1,
                "solvent_fraction": 0.9,
                "solute_fraction": 0.1,
                "tds": 100.0,
                "charge_imbalance": 0.0,
                "expected_charge_imbalance": 0.0,
                "charge_discrepancy": 0.0,
                "sigma": 0.0,
                "elements": {"Na": {"log_molality": -3.0, "mass_fraction": 0.2}},
                "aqueous": {
                    "O2(g)": {"molality": 1.0, "log_molality": 0.0, "log_activity": 0.0, "log_gamma": 0.0},
                    "Na+": {"molality": 0.1, "log_molality": -1.0, "log_activity": -1.1, "log_gamma": 0.2},
                },
                "solids": {
                    "pure_solids": {"Calcite": {"log_qk": 0.2, "affinity": 1.0, "moles": 1.0, "log_moles": -1.0}},
                    "solid_solutions": {},
                },
                "gases": {"CO2(g)": {"log_fugacity": -3.0}},
                "redox": {"O2/H2O": {"Eh": 0.1, "pe-": 4.0, "log_fO2": -60.0, "Ah": 1.2}},
            }

        parser_instance = mock.Mock()
        parser_instance.parse.return_value = SimpleNamespace(path=[_step(-2.0), _step(-1.0)])

        with mock.patch("eleanor.kernel.eq36.kernel.OutputParser6", return_value=parser_instance):
            points = Kernel.read_eq6_output(track_path=False)

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].log_xi, -1.0)
        self.assertEqual(len(points[0].aqueous_species), 1)
        self.assertEqual(points[0].aqueous_species[0].name, "Na+")
        self.assertEqual(points[0].reactants, [])

    def test_read_eq6_output_track_path_true_maps_reactants_and_sentinel_branches(self):
        """
        Ensure read_eq6_output with track_path=True keeps all steps and applies sentinel conversions in mapped objects.
        """
        step = {
            "log_xi": -1.5,
            "temperature": 25.0,
            "pressure": 10.0,
            "pH": {"NBS pH scale": {"pH": 7.0, "Eh": 0.1, "pe-": 4.0, "Ah": 1.2}},
            "pHCl": None,
            "log_fO2": -60.0,
            "log_activity_water": -0.01,
            "mole_fraction_water": 0.98,
            "log_activity_coefficient_water": 0.02,
            "osmotic_coefficient": 0.8,
            "stoichiometric_osmotic_coefficient": 0.81,
            "log_sum_molalities": -1.0,
            "log_sum_stoichiometric_molalities": -0.9,
            "log_ionic_strength": -2.0,
            "log_stoichiometric_ionic_strength": -1.8,
            "log_ionic_asymmetry": -2.2,
            "log_stoichiometric_ionic_asymmetry": -2.1,
            "solvent_mass": 1.0,
            "solute_mass": 0.1,
            "solution_mass": 1.1,
            "solvent_fraction": 0.9,
            "solute_fraction": 0.1,
            "tds": 100.0,
            "charge_imbalance": 0.0,
            "expected_charge_imbalance": 0.0,
            "charge_discrepancy": 0.0,
            "sigma": 0.0,
            "reactants": {
                "overall_affinity": 12.0,
                "mass_reacted": 3.0,
                "mass_remaining": 7.0,
                "reactants": {
                    "Calcite": {
                        "log_moles_reacted": -1.0,
                        "log_moles_remaining": -2.0,
                        "log_mass_reacted": -3.0,
                        "log_mass_remaining": -4.0,
                        "affinity": 1.2,
                        "relative_rate": 0.5,
                    }
                },
            },
            "solids": {
                "created": {"mass": 1.0, "volume": 2.0},
                "destroyed": {"mass": 0.4, "volume": 0.5},
                "net": {"mass": 0.6, "volume": 1.5},
                "pure_solids": {
                    "Calcite": {"log_qk": 0.2, "affinity": 1.0, "moles": 0.0, "log_moles": -9.0, "log_mass": -4.0}
                },
                "solid_solutions": {
                    "SS1": {
                        "log_qk": 0.1,
                        "affinity": 0.2,
                        "log_moles": -2.0,
                        "log_mass": -1.5,
                        "log_volume": -1.2,
                        "end_members": {
                            "EM1": {
                                "log_qk": 0.3,
                                "affinity": 0.4,
                                "log_moles": -6.0,
                                "log_mass": -5.0,
                                "log_volume": -4.0,
                            }
                        },
                    }
                },
            },
            "elements": {"Na": {"log_molality": -3.0, "mass_fraction": 0.2}},
            "aqueous": {
                "O2(g)": {"molality": 1.0, "log_molality": 0.0, "log_activity": 0.0, "log_gamma": 0.0},
                "H2O": {"molality": 0.0, "log_molality": -9.0, "log_activity": -99999, "log_gamma": 0.0},
            },
            "gases": {"CO2(g)": {"log_fugacity": -3.0}},
            "redox": {"O2/H2O": {"Eh": 0.1, "pe-": 4.0, "log_fO2": -60.0, "Ah": 1.2}},
        }

        parser_instance = mock.Mock()
        parser_instance.parse.return_value = SimpleNamespace(path=[step, step])

        with mock.patch("eleanor.kernel.eq36.kernel.OutputParser6", return_value=parser_instance):
            points = Kernel.read_eq6_output(track_path=True)

        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].overall_affinity, 12.0)
        self.assertEqual(points[0].reactant_mass_reacted, 3.0)
        self.assertEqual(len(points[0].reactants), 1)
        self.assertEqual(points[0].reactants[0].name, "Calcite")
        self.assertEqual(len(points[0].aqueous_species), 1)
        self.assertEqual(points[0].aqueous_species[0].log_molality, -float("inf"))
        self.assertEqual(points[0].aqueous_species[0].log_activity, -float("inf"))
        self.assertEqual(points[0].pure_solids[0].log_moles, -float("inf"))
