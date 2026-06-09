import contextlib
import io
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest import TestCase, mock

import eleanor.variable_space as vs
import numpy as np
from eleanor.config.kernel import KernelConfig
from eleanor.constraints.point_builder import PointBuilder
from eleanor.exceptions import EleanorException
from eleanor.kernel.eq36.codes import RunCode
from eleanor.kernel.eq36.data1 import BasisSpecies, Data1
from eleanor.kernel.eq36.kernel import Eq36Kernel
from eleanor.kernel.eq36.settings import (
    IOPG_1,
    IOPT_1,
    IOPT_4,
    Eq3Settings,
    Eq6Settings,
    Eq36Settings,
)
from eleanor.kernel.exceptions import EleanorKernelException
from eleanor.kernel.settings import KernelSettings
from eleanor.order import Order
from eleanor.parameters import Parameter
from eleanor.variable_space import (
    AqueousReactant,
    Element,
    ElementReactant,
    FixedGasReactant,
    GasReactant,
    MineralReactant,
    SolidSolutionReactant,
    SolidSolutionReactantEndMembers,
    SpecialReactant,
    SpecialReactantComposition,
    Species,
    Suppression,
    SuppressionException,
)


def _make_point(
    settings: Eq36Settings,
    *,
    suppressions: list[vs.Suppression] | None = None,
    water_mass: float = 1.0,
    temperature: float = 25.0,
    pressure: float = 10.0,
    species: list[vs.Species] | None = None,
    elements: list[vs.Element] | None = None,
    mineral_reactants: list[MineralReactant] | None = None,
    solid_solution_reactants: list[SolidSolutionReactant] | None = None,
    special_reactants: list[SpecialReactant] | None = None,
    element_reactants: list[ElementReactant] | None = None,
    aqueous_reactants: list[AqueousReactant] | None = None,
    gas_reactants: list[GasReactant] | None = None,
    fixed_gas_reactants: list[FixedGasReactant] | None = None,
) -> vs.Point:
    return vs.Point(
        kernel=KernelConfig(kind="eq36", settings=settings),
        water_mass=np.float64(water_mass),
        temperature=np.float64(temperature),
        pressure=np.float64(pressure),
        suppressions=suppressions or [],
        species=species or [],
        elements=elements or [],
        mineral_reactants=mineral_reactants or [],
        solid_solution_reactants=solid_solution_reactants or [],
        special_reactants=special_reactants or [],
        element_reactants=element_reactants or [],
        aqueous_reactants=aqueous_reactants or [],
        gas_reactants=gas_reactants or [],
        fixed_gas_reactants=fixed_gas_reactants or [],
    )


class _DummyCurve:
    def __init__(self, in_domain=True, pressure=10.0) -> None:
        self._in_domain = in_domain
        self._pressure = pressure

    def temperature_in_domain(self, _T):
        return self._in_domain

    def __call__(self, _T):
        return self._pressure


class _NamedStringIO(io.StringIO):
    name: str

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


class TestEq36Kernel(TestCase):
    """
    Tests of selected branch behavior in eleanor.kernel.eq36.kernel.
    """

    def _data1(self) -> Data1:
        return Data1(Path("fake"), {}, {}, {}, {}, {}, {}, {}, None)

    def _settings(self, with_eq6=True) -> Eq36Settings:
        return Eq36Settings(
            model=IOPG_1.B_DOT,
            charge_balance="Cl-",
            eq3_config=Eq3Settings(),
            eq6_config=Eq6Settings() if with_eq6 else None,
        )

    def _config(self) -> KernelConfig:
        return KernelConfig(kind="eq6", settings=self._settings())

    def _kernel(self) -> Eq36Kernel:
        return Eq36Kernel()

    def test_is_soft_exit_accepts_code_60_and_rejects_other_nonzero(self) -> None:
        """
        Ensure soft-exit detection accepts code 60 and rejects unrelated nonzero codes.
        """
        kernel = self._kernel()
        self.assertTrue(kernel.is_soft_exit(60))
        self.assertFalse(kernel.is_soft_exit(2))

    def test_get_atomic_weight_requires_setup_and_reads_first_data1(self) -> None:
        """
        Ensure get_atomic_weight fails before setup and then reads from the first loaded data1 element map.
        """
        kernel = self._kernel()
        with self.assertRaises(EleanorException):
            kernel.get_atomic_weight("Na")

        kernel._setup = True
        kernel._data1s = cast(list[Data1], [SimpleNamespace(elements={"Na": 22.99})])
        self.assertEqual(kernel.get_atomic_weight("Na"), 22.99)
        self.assertIsNone(kernel.get_atomic_weight("Cl"))

    def test_get_molar_mass_requires_setup_returns_computed_value_and_returns_none_for_unknown(
        self,
    ) -> None:
        """
        Ensure get_molar_mass fails before setup, returns the data1 result for a known species,
        and returns None when the species is not found.
        """
        kernel = self._kernel()
        with self.assertRaises(EleanorException):
            kernel.get_molar_mass("H2O")

        sentinel = object()
        data1 = SimpleNamespace(molar_mass=mock.Mock(return_value=sentinel))
        kernel._setup = True
        kernel._data1s = cast(list[Data1], [data1])

        self.assertIs(kernel.get_molar_mass("H2O"), sentinel)
        data1.molar_mass.assert_called_once_with("H2O", None)

        data1.molar_mass.side_effect = KeyError("unknown")
        self.assertIsNone(kernel.get_molar_mass("Unknown"))

    def test_get_molar_mass_forwards_mole_fractions_and_propagates_value_error(
        self,
    ) -> None:
        """
        Ensure get_molar_mass forwards mole_fractions to data1 and lets ValueError propagate
        (e.g. when a solid solution is queried without supplying mole_fractions).
        """
        fractions = mock.sentinel.fractions
        sentinel = object()
        data1 = SimpleNamespace(molar_mass=mock.Mock(return_value=sentinel))
        kernel = self._kernel()
        kernel._setup = True
        kernel._data1s = cast(list[Data1], [data1])

        self.assertIs(kernel.get_molar_mass("SOLID1", fractions), sentinel)
        data1.molar_mass.assert_called_once_with("SOLID1", fractions)

        data1.molar_mass.side_effect = ValueError(
            "mole_fractions is required to get the molar_mass of a solid solution"
        )
        with self.assertRaises(ValueError):
            kernel.get_molar_mass("SOLID1", None)

    def test_resolve_kernel_settings_permits_solids_and_sets_titration_when_reactants_present(
        self,
    ) -> None:
        """
        Ensure unsuppressed solid-solution runs permit solids and switch EQ6 to titration mode when reactants exist.
        """
        kernel = self._kernel()
        point = _make_point(
            self._settings(with_eq6=True),
            mineral_reactants=[
                MineralReactant(
                    name="stub",
                    log_moles=np.float64(0.0),
                    titration_rate=np.float64(1.0),
                )
            ],
        )

        resolved = kernel.resolve_kernel_settings(point)

        self.assertEqual(resolved.eq3_config.iopt_4, IOPT_4.PERMIT_SOLID_SOLUTIONS)
        assert resolved.eq6_config is not None
        self.assertEqual(resolved.eq6_config.iopt_4, IOPT_4.PERMIT_SOLID_SOLUTIONS)
        self.assertEqual(resolved.eq6_config.iopt_1, IOPT_1.TITRATION_SYS)

    def test_resolve_kernel_settings_with_all_and_named_suppressions_warns_and_keeps_defaults(
        self,
    ) -> None:
        """
        Ensure mixed all/named solid-solution suppressions emit warning and keep solid-solution suppression enabled.
        """
        kernel = self._kernel()
        suppressions = [
            Suppression(type="solid solution", name=None, exceptions=[]),
            Suppression(type="solid solutions", name="SS1", exceptions=[]),
        ]
        point = _make_point(self._settings(with_eq6=True), suppressions=suppressions)

        with mock.patch("sys.stderr", new=io.StringIO()) as stderr:
            resolved = kernel.resolve_kernel_settings(point)

        self.assertEqual(resolved.eq3_config.iopt_4, IOPT_4.IGNORE_SOLID_SOLUTIONS)
        assert resolved.eq6_config is not None
        self.assertEqual(resolved.eq6_config.iopt_4, IOPT_4.IGNORE_SOLID_SOLUTIONS)
        self.assertIn("all solid solutions are suppressed", stderr.getvalue())

    def test_resolve_kernel_settings_rejects_solid_solution_exemptions(self) -> None:
        """
        Ensure solid-solution suppression exceptions are rejected as unsupported.
        """
        kernel = self._kernel()
        suppressions = [
            Suppression(
                type="solid solution",
                name=None,
                exceptions=[SuppressionException(name="stub")],
            )
        ]
        point = _make_point(self._settings(with_eq6=True), suppressions=suppressions)

        with self.assertRaises(NotImplementedError):
            kernel.resolve_kernel_settings(point)

    def test_resolve_kernel_settings_without_eq6_only_updates_eq3(self) -> None:
        """
        Ensure unsuppressed solid-solution mode still updates EQ3 when EQ6 config is disabled.
        """
        kernel = self._kernel()
        point = _make_point(
            self._settings(with_eq6=False),
            mineral_reactants=[
                MineralReactant(
                    name="stub",
                    log_moles=np.float64(0.0),
                    titration_rate=np.float64(1.0),
                )
            ],
        )

        resolved = kernel.resolve_kernel_settings(point)

        self.assertEqual(resolved.eq3_config.iopt_4, IOPT_4.PERMIT_SOLID_SOLUTIONS)
        self.assertIsNone(resolved.eq6_config)

    def test_resolve_kernel_settings_rejects_unexpected_settings_type(self) -> None:
        """
        Ensure resolve_kernel_settings rejects points whose kernel settings are not eq36 Settings instances.
        """
        kernel = self._kernel()
        point = _make_point(self._settings())
        point.kernel.settings = KernelSettings()

        with self.assertRaises(TypeError):
            kernel.resolve_kernel_settings(point)

    def test_find_data1_filters_candidates_and_returns_exact_pressure_match(
        self,
    ) -> None:
        """
        Ensure find_data1 ignores curves outside domain/non-matching pressure and returns the matching data1.
        """
        kernel = self._kernel()
        kernel._data1s = cast(
            list[Data1],
            [
                SimpleNamespace(filename="none", tp_curve=None),
                SimpleNamespace(
                    filename="outside",
                    tp_curve=_DummyCurve(in_domain=False, pressure=10.0),
                ),
                SimpleNamespace(
                    filename="wrong", tp_curve=_DummyCurve(in_domain=True, pressure=7.5)
                ),
                SimpleNamespace(
                    filename="right",
                    tp_curve=_DummyCurve(in_domain=True, pressure=10.0),
                ),
            ],
        )
        point = _make_point(self._settings(), temperature=25.0, pressure=10.0)

        data1 = kernel.find_data1(point)

        self.assertEqual(data1.filename, "right")

    def test_find_data1_raises_when_no_curve_matches_temperature_pressure(self) -> None:
        """
        Ensure find_data1 raises when no data1 curve satisfies both temperature-domain and pressure equality checks.
        """
        kernel = self._kernel()
        kernel._data1s = cast(
            list[Data1],
            [
                SimpleNamespace(
                    filename="wrong", tp_curve=_DummyCurve(in_domain=True, pressure=9.0)
                )
            ],
        )
        point = _make_point(self._settings(), temperature=25.0, pressure=10.0)

        with self.assertRaises(EleanorKernelException):
            kernel.find_data1(point)

    def test_find_data1_multiple_matches_verbose_warns_and_returns_first(self) -> None:
        """
        Ensure find_data1 emits verbose warning for multiple matches and returns the first match.
        """
        kernel = self._kernel()
        first = SimpleNamespace(
            filename="first", tp_curve=_DummyCurve(in_domain=True, pressure=10.0)
        )
        second = SimpleNamespace(
            filename="second", tp_curve=_DummyCurve(in_domain=True, pressure=10.0)
        )
        kernel._data1s = cast(list[Data1], [first, second])
        point = _make_point(self._settings(), temperature=25.0, pressure=10.0)

        with mock.patch("builtins.print") as print_mock:
            data1 = kernel.find_data1(point, verbose=True)

        self.assertIs(data1, first)
        print_mock.assert_called_once_with(
            "warning: multiple data1 files pass through temperature 25.0 and pressure 10.0; choosing first"
        )

    def test_run_eq3_only_finds_data1_and_sets_eq3_timestamps(self) -> None:
        """
        Ensure run executes eq3-only flow, resolves missing data1 via find_data1, and stamps eq3 result timing.
        """
        kernel = self._kernel()
        settings = self._settings(with_eq6=False)
        point = _make_point(settings)
        found_data1 = SimpleNamespace(filename="/tmp/found/run.d1")
        eq3_result = SimpleNamespace(stage="eq3")

        with (
            mock.patch.object(
                kernel, "resolve_kernel_settings", return_value=settings
            ) as resolve,
            mock.patch.object(
                kernel, "find_data1", return_value=found_data1
            ) as find_data1,
            mock.patch.object(
                kernel, "write_eq3_input", return_value="problem.3i"
            ) as write_eq3_input,
            mock.patch("eleanor.kernel.eq36.kernel.eq3") as eq3_mock,
            mock.patch(
                "eleanor.kernel.eq36.kernel.Eq36Kernel.read_eq3_output",
                return_value=eq3_result,
            ) as read_eq3_output,
            mock.patch("eleanor.kernel.eq36.kernel.eq6") as eq6_mock,
            mock.patch(
                "eleanor.kernel.eq36.kernel.read_pickup_lines"
            ) as read_pickup_lines,
            mock.patch(
                "eleanor.kernel.eq36.kernel.Eq36Kernel.read_eq6_output"
            ) as read_eq6_output,
            mock.patch("eleanor.kernel.eq36.kernel.Data1.from_file") as from_file,
        ):
            output = kernel.run(point, verbose=True)

        resolve.assert_called_once_with(point)
        find_data1.assert_called_once_with(point, verbose=True)
        self.assertEqual(settings.data1_file, "/tmp/found/run.d1")
        write_eq3_input.assert_called_once_with(point, found_data1, verbose=True)
        eq3_mock.assert_called_once_with(
            "/tmp/found/run.d1", "problem.3i", timeout=settings.timeout
        )
        read_eq3_output.assert_called_once_with()
        eq6_mock.assert_not_called()
        read_pickup_lines.assert_not_called()
        read_eq6_output.assert_not_called()
        from_file.assert_not_called()
        self.assertEqual(output, [eq3_result])
        self.assertLessEqual(eq3_result.start_date, eq3_result.complete_date)

    def test_run_eq3_eq6_uses_preconfigured_data1_and_stamps_eq6_points(self) -> None:
        """
        Ensure run loads preconfigured data1, executes eq3+eq6 flow, and stamps timing on each eq6 result point.
        """
        kernel = self._kernel()
        settings = self._settings(with_eq6=True)
        settings.data1_file = Path("/tmp").joinpath("configured", "run.d1")
        point = _make_point(settings)
        loaded_data1 = SimpleNamespace(filename=Path("/tmp/configured/run.d1"))
        eq3_result = SimpleNamespace(stage="eq3")
        eq6_results = [SimpleNamespace(stage="eq6-a"), SimpleNamespace(stage="eq6-b")]
        pickup_lines = ["pickup-a\n", "pickup-b\n"]

        with (
            mock.patch.object(
                kernel, "resolve_kernel_settings", return_value=settings
            ) as resolve,
            mock.patch.object(kernel, "find_data1") as find_data1,
            mock.patch(
                "eleanor.kernel.eq36.kernel.Data1.from_file", return_value=loaded_data1
            ) as from_file,
            mock.patch.object(
                kernel, "write_eq3_input", return_value="problem.3i"
            ) as write_eq3_input,
            mock.patch("eleanor.kernel.eq36.kernel.eq3") as eq3_mock,
            mock.patch(
                "eleanor.kernel.eq36.kernel.Eq36Kernel.read_eq3_output",
                return_value=eq3_result,
            ) as read_eq3_output,
            mock.patch(
                "eleanor.kernel.eq36.kernel.read_pickup_lines",
                return_value=pickup_lines,
            ) as read_pickup_lines,
            mock.patch.object(
                kernel, "write_eq6_input", return_value="problem.6i"
            ) as write_eq6_input,
            mock.patch("eleanor.kernel.eq36.kernel.eq6") as eq6_mock,
            mock.patch(
                "eleanor.kernel.eq36.kernel.Eq36Kernel.read_eq6_output",
                return_value=eq6_results,
            ) as read_eq6_output,
        ):
            output = kernel.run(point, verbose=True)

        resolve.assert_called_once_with(point)
        find_data1.assert_not_called()
        from_file.assert_called_once_with(Path("/tmp/configured/run.d1"))
        write_eq3_input.assert_called_once_with(point, loaded_data1, verbose=True)
        eq3_mock.assert_called_once_with(
            Path("/tmp/configured/run.d1"), "problem.3i", timeout=settings.timeout
        )
        read_eq3_output.assert_called_once_with()
        read_pickup_lines.assert_called_once_with()
        write_eq6_input.assert_called_once_with(
            point, pickup_lines=pickup_lines, verbose=True
        )
        eq6_mock.assert_called_once_with(
            Path("/tmp/configured/run.d1"), "problem.6i", timeout=settings.timeout
        )
        read_eq6_output.assert_called_once_with(track_path=settings.track_path)
        self.assertEqual(output, [eq3_result, *eq6_results])
        self.assertLessEqual(eq3_result.start_date, eq3_result.complete_date)
        for result in eq6_results:
            self.assertLessEqual(result.start_date, result.complete_date)

    def test_run_reraises_eleanor_exception_without_wrapping(self) -> None:
        """
        Ensure run re-raises EleanorException subclasses directly.
        """
        kernel = self._kernel()
        point = _make_point(self._settings())
        error = EleanorKernelException("known kernel failure", code=RunCode.EQ3_ERROR)

        with mock.patch.object(kernel, "resolve_kernel_settings", side_effect=error):
            with self.assertRaises(EleanorKernelException) as context:
                kernel.run(point)

        self.assertIs(context.exception, error)

    def test_run_wraps_unexpected_exceptions_with_generic_eleanor_exception(
        self,
    ) -> None:
        """
        Ensure run wraps unexpected exceptions with a generic EleanorException while preserving the original cause.
        """
        kernel = self._kernel()
        point = _make_point(self._settings())
        cause = RuntimeError("unexpected failure")

        with mock.patch.object(kernel, "resolve_kernel_settings", side_effect=cause):
            with self.assertRaises(EleanorException) as context:
                kernel.run(point)

        self.assertIn("an unexpected error occurred", str(context.exception))
        self.assertIs(context.exception.__cause__, cause)

    def test_write_switch_grid_eq3_includes_iopg_rows(self) -> None:
        """
        Ensure write_switch_grid prints the Eq3 IOPG rows.
        """
        kernel = self._kernel()
        handle = io.StringIO()

        kernel.write_switch_grid(handle, Eq3Settings())

        output = handle.getvalue()
        self.assertIn("iopg1-10=", output)
        self.assertIn("iopg11-20=", output)

    def test_write_switch_grid_eq6_omits_iopg_rows(self) -> None:
        """
        Ensure write_switch_grid omits Eq3-only IOPG rows for Eq6Config.
        """
        kernel = self._kernel()
        handle = io.StringIO()

        kernel.write_switch_grid(handle, Eq6Settings())

        output = handle.getvalue()
        self.assertNotIn("iopg1-10=", output)
        self.assertNotIn("iopg11-20=", output)

    def test_write_switch_grid_eq3_verbose_uses_make_verbose(self) -> None:
        """
        Ensure write_switch_grid calls Eq3 make_verbose in verbose mode and prints rows from the returned config.
        """
        kernel = self._kernel()
        base_cfg = Eq3Settings()
        verbose_cfg = Eq3Settings(iopt_1=IOPT_1.FLOW_THROUGH_SYS)
        expected_line = "  iopt1-10= {0: >5}{1: >5}{2: >5}{3: >5}{4: >5}{5: >5}{6: >5}{7: >5}{8: >5}{9: >5}".format(
            *verbose_cfg.iopt[:10]
        )
        handle = io.StringIO()

        with mock.patch.object(
            base_cfg, "make_verbose", return_value=verbose_cfg
        ) as make_verbose:
            kernel.write_switch_grid(handle, base_cfg, verbose=True)

        make_verbose.assert_called_once_with()
        self.assertIn(expected_line, handle.getvalue())

    def test_copy_data_uses_existing_data1_file_without_find_data1(self) -> None:
        """
        Ensure copy_data uses preconfigured data1 path directly and skips find_data1 lookup.
        """
        kernel = self._kernel()
        settings = self._settings()
        settings.data1_file = Path("/tmp").joinpath("source", "testdata.d1")
        point = _make_point(settings)

        with (
            mock.patch.object(
                kernel, "resolve_kernel_settings", return_value=settings
            ) as resolve,
            mock.patch.object(kernel, "find_data1") as find_data1,
            mock.patch("eleanor.kernel.eq36.kernel.copyfile") as copyfile_mock,
        ):
            kernel.copy_data(point, dir="target")

        resolve.assert_called_once_with(point)
        find_data1.assert_not_called()
        copyfile_mock.assert_called_once_with(
            Path("/tmp/source/testdata.d1"), Path("target/testdata.d1")
        )

    def test_copy_data_finds_data1_when_missing_and_updates_settings(self) -> None:
        """
        Ensure copy_data resolves missing data1 path via find_data1 and forwards verbose flag.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(settings)
        found = SimpleNamespace(filename=Path("/tmp/found/fresh.d1"))

        with (
            mock.patch.object(
                kernel, "resolve_kernel_settings", return_value=settings
            ) as resolve,
            mock.patch.object(kernel, "find_data1", return_value=found) as find_data1,
            mock.patch("eleanor.kernel.eq36.kernel.copyfile") as copyfile_mock,
        ):
            kernel.copy_data(point, dir="target", verbose=True)

        resolve.assert_called_once_with(point)
        find_data1.assert_called_once_with(point, verbose=True)
        self.assertEqual(settings.data1_file, Path("/tmp/found/fresh.d1"))
        copyfile_mock.assert_called_once_with(
            Path("/tmp/found/fresh.d1"), Path("target/fresh.d1")
        )

    def test_setup_filters_data1_files_that_intersect_target_domain(self) -> None:
        """
        Ensure setup only retains data1 files whose tp-curves intersect the requested T/P domain.
        """
        kernel = self._kernel()
        order = mock.create_autospec(Order, instance=True)
        order.kernel = self._config()
        order.temperature = Parameter.load({"min": 1.0, "max": 2.0})
        order.pressure = Parameter.load({"min": 3.0, "max": 4.0})
        rejected = SimpleNamespace(
            tp_curve=SimpleNamespace(set_domain=mock.Mock(return_value=False))
        )
        accepted = SimpleNamespace(
            tp_curve=SimpleNamespace(set_domain=mock.Mock(return_value=True))
        )

        with (
            mock.patch(
                "eleanor.kernel.eq36.kernel.tool_room.WorkingDirectory",
                return_value=contextlib.nullcontext(),
            ) as wd_mock,
            mock.patch(
                "eleanor.kernel.eq36.kernel.tool_room.find_files",
                return_value=([], [Path("first.d1"), Path("second.d1")]),
            ) as find_files_mock,
            mock.patch(
                "eleanor.kernel.eq36.kernel.Data1.from_file",
                side_effect=[rejected, accepted],
            ),
        ):
            kernel.setup(cast(Order, order), data1_dir=("."))

        wd_mock.assert_called_once_with(Path("."))
        find_files_mock.assert_called_once_with(".d1")
        rejected.tp_curve.set_domain.assert_called_once_with((1.0, 2.0), (3.0, 4.0))
        accepted.tp_curve.set_domain.assert_called_once_with((1.0, 2.0), (3.0, 4.0))
        self.assertTrue(kernel._setup)
        self.assertEqual(kernel._data1s, [accepted])

    def test_setup_raises_when_order_is_none(self) -> None:
        """
        Ensure setup raises EleanorException when called with an invalid order.
        """
        kernel = self._kernel()

        with self.assertRaisesRegex(
            EleanorException, "order provided to Eq36Kernel.setup"
        ):
            kernel.setup(cast(Order, cast(object, None)), data1_dir=".")

    def test_validate_order_raises_kernel_has_not_been_setup(self) -> None:
        """
        Ensure validate_order raises when the kernel has not been setup.
        """
        kernel = self._kernel()
        order = mock.create_autospec(Order, instance=True)
        order.kernel = KernelSettings()
        order.temperature = Parameter.load(100.0)
        order.pressure = Parameter.load(20.0)
        rejected = SimpleNamespace(
            tp_curve=SimpleNamespace(set_domain=mock.Mock(return_value=False))
        )

        with (
            mock.patch(
                "eleanor.kernel.eq36.kernel.tool_room.WorkingDirectory",
                return_value=contextlib.nullcontext(),
            ),
            mock.patch(
                "eleanor.kernel.eq36.kernel.tool_room.find_files",
                return_value=([], ["only.d1"]),
            ),
            mock.patch(
                "eleanor.kernel.eq36.kernel.os.path.realpath",
                side_effect=lambda path: path,
            ),
            mock.patch(
                "eleanor.kernel.eq36.kernel.Data1.from_file", return_value=rejected
            ),
        ):
            with self.assertRaises(EleanorException):
                kernel.validate_order(order)

        self.assertFalse(kernel._setup)
        self.assertEqual(kernel._data1s, [])

    def test_validate_order_raises_when_no_data1_curves_intersect_target_domain(
        self,
    ) -> None:
        """
        Ensure validate_order raises when no discovered data1 file supports the requested temperature/pressure domain.
        """
        kernel = self._kernel()
        order = mock.create_autospec(Order, instance=True)
        order.kernel = self._config()
        order.temperature = Parameter.load(10.0)
        order.pressure = Parameter.load(30.0)
        rejected = SimpleNamespace(
            tp_curve=SimpleNamespace(set_domain=mock.Mock(return_value=False))
        )

        with (
            mock.patch(
                "eleanor.kernel.eq36.kernel.tool_room.WorkingDirectory",
                return_value=contextlib.nullcontext(),
            ),
            mock.patch(
                "eleanor.kernel.eq36.kernel.tool_room.find_files",
                return_value=([], [Path("only.d1")]),
            ),
            mock.patch(
                "eleanor.kernel.eq36.kernel.Data1.from_file", return_value=rejected
            ),
        ):
            kernel.setup(order, data1_dir=".")
            with self.assertRaises(EleanorException):
                kernel.validate_order(order)

        self.assertTrue(kernel._setup)
        self.assertEqual(kernel._data1s, [])

    def test_constrain_appends_temperature_and_tp_constraints_in_order(self) -> None:
        """
        Ensure constrain appends temperature-range and T/P-curve constraints and returns the same point_builder.
        """
        order = mock.create_autospec(Order, instance=True)
        order.kernel = self._config()
        order.temperature = Parameter.load({"min": 100, "max": 200})
        order.pressure = Parameter.load({"min": 1, "max": 800})

        kernel = self._kernel()
        kernel._setup = True
        kernel._data1s = cast(list[Data1], [SimpleNamespace(name="d1")])

        point_builder = mock.create_autospec(PointBuilder, instance=True)
        point_builder.order = order
        point_builder.constraints = []

        with (
            mock.patch(
                "eleanor.kernel.eq36.kernel.TemperatureRangeConstraint",
                return_value="TRANGE",
            ) as trange_mock,
            mock.patch(
                "eleanor.kernel.eq36.kernel.TPCurveConstraint", return_value="TPCURVE"
            ) as tpcurve_mock,
        ):
            out = kernel.constrain(point_builder)

        self.assertIs(out, point_builder)
        self.assertEqual(point_builder.constraints, ["TRANGE", "TPCURVE"])
        trange_mock.assert_called_once_with(order.temperature, kernel._data1s)
        tpcurve_mock.assert_called_once_with(
            order.temperature, order.pressure, kernel._data1s
        )

    def test_write_eq3_input_requires_setup_before_writing(self) -> None:
        """
        Ensure write_eq3_input fails fast when kernel setup has not been completed.
        """
        kernel = self._kernel()
        point = _make_point(self._settings())

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq3_input(point, data1=self._data1())

    def test_write_eq3_input_rejects_unconstrained_non_fO2_redox_species(self) -> None:
        """
        Ensure write_eq3_input raises when configured redox species is not constrained on the variable-space point.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "pe"
        point = _make_point(
            settings, species=[Species(name="H+", value=np.float64(-7.0))]
        )

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq3_input(point, data1=self._data1())

    def test_write_eq3_input_fO2_redox_requires_O2_species_lookup(self) -> None:
        """
        Ensure write_eq3_input raises when redox_species=fO2 but O2(g) lookup is missing at write time.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "fO2"
        point = _make_point(
            settings, species=[Species(name="fO2", value=np.float64(-60.0))]
        )
        handle = _NamedStringIO("problem.3i")

        data1 = mock.create_autospec(Data1, instance=True)
        data1.get_basis_species.return_value = None

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq3_input(point, data1=data1, file=handle)

    def test_write_eq3_input_uses_fO2_fallback_via_O2_species_and_writes_expected_general_fields(
        self,
    ) -> None:
        """
        Ensure write_eq3_input accepts O2(g) as fallback for fO2 and emits expected general redox fields.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "fO2"
        point = _make_point(
            settings,
            species=[
                Species(name="O2(g)", value=np.float64(-60.0)),
                Species(name="H+", value=np.float64(-7.0)),
            ],
        )
        handle = _NamedStringIO("problem.3i")

        data1 = mock.create_autospec(Data1, instance=True)
        data1.get_basis_species.return_value = None

        path = kernel.write_eq3_input(point, data1=data1, file=handle)
        output = handle.getvalue()

        self.assertEqual(path, "problem.3i")
        self.assertIn("irdxc3=   0", output)
        self.assertIn("uredox= None", output)
        self.assertIn("species= H+", output)

    def test_write_eq3_input_emits_custom_water_mass_in_scamas_field(self) -> None:
        """
        Ensure write_eq3_input writes the correct scamas line when water_mass is not the default 1kg.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "fO2"
        point = _make_point(
            settings,
            water_mass=0.5,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
        )
        handle = _NamedStringIO("problem.3i")

        data1 = mock.create_autospec(Data1, instance=True)
        data1.get_basis_species.return_value = None

        kernel.write_eq3_input(point, data1=data1, file=handle)
        output = handle.getvalue()

        self.assertIn("scamas=  5.00000E-01", output)
        self.assertNotIn("scamas=  1.00000E+00", output)

    def test_write_eq3_input_raises_when_element_has_no_basis_species(self) -> None:
        """
        Ensure write_eq3_input raises when an element in the point has no matching basis species in data1.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "fO2"
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            elements=[Element(name="Na", log_molality=np.float64(-3.0))],
        )
        handle = _NamedStringIO("problem.3i")
        data1 = mock.create_autospec(Data1, instance=True)
        data1.get_basis_species.return_value = None

        with self.assertRaises(Exception):
            kernel.write_eq3_input(point, data1=data1, file=handle)

    def test_write_eq6_input_requires_eq6_config(self) -> None:
        """
        Ensure write_eq6_input fails fast when eq6 configuration is disabled.
        """
        kernel = self._kernel()
        point = _make_point(self._settings(with_eq6=False))

        with self.assertRaises(ValueError):
            kernel.write_eq6_input(point)

    def test_write_eq6_input_rejects_unconstrained_non_fO2_redox_species(self) -> None:
        """
        Ensure write_eq6_input raises when a non-fO2 redox species is unconstrained.
        """
        kernel = self._kernel()
        settings = self._settings()
        settings.redox_species = "pe"
        point = _make_point(
            settings, species=[Species(name="H+", value=np.float64(-7.0))]
        )

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq6_input(point)

    def test_write_eq6_input_rejects_invalid_mineral_reactant_type(self) -> None:
        """
        Ensure write_eq6_input surfaces attribute errors for invalid mineral reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            mineral_reactants=cast(list[MineralReactant], [object()]),
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_unsupported_suppression_type(self) -> None:
        """
        Ensure write_eq6_input rejects suppression types outside supported categories.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            suppressions=[Suppression(type="unexpected", name=None, exceptions=[])],
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_fixed_gas_reactant_type(self) -> None:
        """
        Ensure write_eq6_input surfaces attribute errors for invalid fixed gas reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            fixed_gas_reactants=cast(list[FixedGasReactant], [object()]),
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_solid_solution_reactant_type(self) -> None:
        """
        Ensure write_eq6_input surfaces attribute errors for invalid solid solution reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            solid_solution_reactants=cast(list[SolidSolutionReactant], [object()]),
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_special_reactant_type(self) -> None:
        """
        Ensure write_eq6_input surfaces attribute errors for invalid special reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            special_reactants=cast(list[SpecialReactant], [object()]),
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_element_reactant_type(self) -> None:
        """
        Ensure write_eq6_input surfaces attribute errors for invalid element reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            element_reactants=cast(list[ElementReactant], [object()]),
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_aqueous_reactant_type(self) -> None:
        """
        Ensure write_eq6_input surfaces attribute errors for invalid aqueous reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            aqueous_reactants=cast(list[AqueousReactant], [object()]),
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_invalid_gas_reactant_type(self) -> None:
        """
        Ensure write_eq6_input surfaces attribute errors for invalid gas reactants.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            gas_reactants=cast(list[GasReactant], [object()]),
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(AttributeError):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_writes_all_reactant_blocks_for_valid_typed_reactants(
        self,
    ) -> None:
        """
        Ensure write_eq6_input emits blocks for all supported reactant categories with valid typed reactants.
        """
        kernel = self._kernel()
        settings = self._settings()

        mineral = MineralReactant(
            name="Calcite", log_moles=np.float64(0.0), titration_rate=np.float64(1.0)
        )
        solid_solution = SolidSolutionReactant(
            name="Albite_ss",
            log_moles=np.float64(0.0),
            titration_rate=np.float64(1.0),
            end_members=[
                SolidSolutionReactantEndMembers(name="EM1", fraction=np.float64(1.0))
            ],
        )
        special = SpecialReactant(
            name="SR",
            log_moles=np.float64(0.0),
            titration_rate=np.float64(1.0),
            composition=[SpecialReactantComposition(element="Na", count=1)],
        )
        element = ElementReactant(
            name="Na", log_moles=np.float64(0.0), titration_rate=np.float64(1.0)
        )
        aqueous = AqueousReactant(
            name="Na+", log_moles=np.float64(0.0), titration_rate=np.float64(1.0)
        )
        gas = GasReactant(
            name="CO2(g)", log_moles=np.float64(0.0), titration_rate=np.float64(1.0)
        )
        fixed_gas = FixedGasReactant(
            name="O2(g)", log_moles=np.float64(0.0), log_fugacity=np.float64(-50.0)
        )

        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            suppressions=[
                Suppression(
                    type="minerals",
                    name=None,
                    exceptions=[SuppressionException(name="Quartz")],
                )
            ],
            mineral_reactants=[mineral],
            solid_solution_reactants=[solid_solution],
            special_reactants=[special],
            element_reactants=[element],
            aqueous_reactants=[aqueous],
            gas_reactants=[gas],
            fixed_gas_reactants=[fixed_gas],
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
        self.assertIn("species= O2(g)", output)
        self.assertIn("nxopt=  1", output)
        self.assertIn("nxopex=  1", output)
        self.assertIn("species= Quartz", output)

    def test_write_eq6_input_writes_header_and_appends_pickup_lines(self) -> None:
        """
        Ensure write_eq6_input emits basic header data and appends pickup lines verbatim.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings, species=[Species(name="O2(g)", value=np.float64(-60.0))]
        )
        handle = _NamedStringIO("problem.6i")
        pickup_lines = ["pickup-a\n", "pickup-b\n"]

        path = kernel.write_eq6_input(point, file=handle, pickup_lines=pickup_lines)
        output = handle.getvalue()

        self.assertEqual(path, "problem.6i")
        self.assertIn("EQ3NR input file name= problem.6i", output)
        self.assertIn("nffg=", output)
        self.assertTrue(output.endswith("pickup-a\npickup-b\n"))

    def test_write_eq6_input_string_path_uses_open_wrapper_branch(self) -> None:
        """
        Ensure write_eq6_input follows the string-path wrapper branch and writes using opened handle.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings, species=[Species(name="O2(g)", value=np.float64(-60.0))]
        )
        handle = _NamedStringIO("wrapped.6i")

        with mock.patch("builtins.open", return_value=handle) as open_mock:
            path = kernel.write_eq6_input(point, file="wrapped.6i")

        open_mock.assert_called_once_with("wrapped.6i", "w")
        self.assertEqual(path, "wrapped.6i")

    def test_write_eq6_input_none_file_defaults_to_problem_6i(self) -> None:
        """
        Ensure write_eq6_input default file=None branch opens problem.6i.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings, species=[Species(name="O2(g)", value=np.float64(-60.0))]
        )
        handle = _NamedStringIO("problem.6i")

        with mock.patch("builtins.open", return_value=handle) as open_mock:
            path = kernel.write_eq6_input(point, file=None)

        self.assertEqual(path, "problem.6i")
        open_mock.assert_called_once_with(Path("problem.6i"), "w")

    def test_write_eq3_input_string_path_wrapper_and_positive_h_branch(self) -> None:
        """
        Ensure write_eq3_input string-path wrapper branch executes and positive H+ uses the alternate covali formatting path.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "pe"
        settings.basis_map = {"Na+": "NaOH(aq)"}
        point = _make_point(
            settings,
            species=[
                Species(name="pe", value=np.float64(4.0)),
                Species(name="H+", value=np.float64(7.0)),
            ],
            elements=[Element(name="Na", log_molality=np.float64(-3.0))],
            suppressions=[Suppression(name="Quartz", type=None, exceptions=[])],
        )
        data1 = mock.create_autospec(Data1, instance=True)
        data1.get_basis_species.return_value = BasisSpecies(
            name="Na+",
            molar_mass=np.float64(22.98977),
            composition={"Na": 1},
            charge=1,
            volume=None,
        )

        handle = _NamedStringIO("wrapped.3i")

        with mock.patch(
            "builtins.open", return_value=contextlib.nullcontext(handle)
        ) as open_mock:
            path = kernel.write_eq3_input(point, data1=data1, file="wrapped.3i")

        output = handle.getvalue()
        self.assertEqual(path, "wrapped.3i")
        open_mock.assert_called_once_with("wrapped.3i", "w")
        self.assertIn("irdxc3=   1", output)
        self.assertIn("uredox= pe", output)
        self.assertIn("switch with= NaOH(aq)", output)
        self.assertIn("species= Quartz", output)
        self.assertIn("species= Na+", output)

    def test_write_eq3_input_none_file_defaults_to_problem_3i(self) -> None:
        """
        Ensure write_eq3_input default file=None branch opens problem.3i.
        """
        kernel = self._kernel()
        kernel._setup = True
        settings = self._settings()
        settings.redox_species = "fO2"
        point = _make_point(
            settings, species=[Species(name="O2(g)", value=np.float64(-60.0))]
        )
        data1 = mock.create_autospec(Data1, instance=True)
        data1.get_basis_species.return_value = None
        handle = _NamedStringIO("problem.3i")

        with mock.patch("builtins.open", return_value=handle) as open_mock:
            path = kernel.write_eq3_input(point, data1=data1, file=None)

        self.assertEqual(path, "problem.3i")
        open_mock.assert_called_once_with(Path("problem.3i"), "w")

    def test_write_eq6_input_suppression_branches_for_none_named_and_solid_solution_types(
        self,
    ) -> None:
        """
        Ensure write_eq6_input executes suppression.type None, named mineral suppression, and solid-solution pass branches.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            suppressions=[
                Suppression(type=None, name="Calcite", exceptions=[]),
                Suppression(type="minerals", name="Hematite", exceptions=[]),
                Suppression(type="solid solutions", name=None, exceptions=[]),
            ],
        )
        handle = _NamedStringIO("problem.6i")

        path = kernel.write_eq6_input(point, file=handle)
        output = handle.getvalue()

        self.assertEqual(path, "problem.6i")
        self.assertIn("nxopt=  0", output)

    def test_write_eq6_input_rejects_suppression_without_name_and_type(self) -> None:
        """
        Ensure write_eq6_input rejects suppressions that provide neither a type nor a name.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            suppressions=[Suppression(type=None, name=None, exceptions=[])],
        )
        handle = _NamedStringIO("problem.6i")

        with self.assertRaises(EleanorKernelException):
            kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_rejects_all_named_suppressions_with_exceptions(
        self,
    ) -> None:
        """
        Ensure write_eq6_input rejects named suppressions when exceptions are provided, regardless of suppression type.
        """
        kernel = self._kernel()
        settings = self._settings()
        cases = [
            Suppression(
                type=None,
                name="Calcite",
                exceptions=[SuppressionException(name="Quartz")],
            ),
            Suppression(
                type="minerals",
                name="Hematite",
                exceptions=[SuppressionException(name="Quartz")],
            ),
            Suppression(
                type="solid solutions",
                name="Feldspar_ss",
                exceptions=[SuppressionException(name="Albite")],
            ),
        ]

        for suppression in cases:
            with self.subTest(type=suppression.type, name=suppression.name):
                point = _make_point(
                    settings,
                    species=[Species(name="O2(g)", value=np.float64(-60.0))],
                    suppressions=[suppression],
                )
                handle = _NamedStringIO("problem.6i")
                with self.assertRaises(EleanorKernelException):
                    kernel.write_eq6_input(point, file=handle)

    def test_write_eq6_input_named_mineral_without_exceptions_does_not_enable_all_mineral_suppression(
        self,
    ) -> None:
        """
        Ensure named mineral suppressions without exceptions do not trigger suppress-all-minerals mode.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            suppressions=[Suppression(type="minerals", name="Hematite", exceptions=[])],
        )
        handle = _NamedStringIO("problem.6i")

        path = kernel.write_eq6_input(point, file=handle)
        output = handle.getvalue()

        self.assertEqual(path, "problem.6i")
        self.assertIn("nxopt=  0", output)
        self.assertNotIn("option= All", output)
        self.assertNotIn("nxopex=  0", output)

    def test_write_eq6_input_suppress_all_minerals_without_exceptions_prints_empty_nxopex(
        self,
    ) -> None:
        """
        Ensure write_eq6_input hits suppress_minerals + no-exceptions branch and prints nxopex with zero.
        """
        kernel = self._kernel()
        settings = self._settings()
        point = _make_point(
            settings,
            species=[Species(name="O2(g)", value=np.float64(-60.0))],
            suppressions=[Suppression(type="minerals", name=None, exceptions=[])],
        )
        handle = _NamedStringIO("problem.6i")

        path = kernel.write_eq6_input(point, file=handle)
        output = handle.getvalue()

        self.assertEqual(path, "problem.6i")
        self.assertIn("nxopt=  1", output)
        self.assertIn("nxopex=  0", output)

    def test_read_eq3_output_returns_parser_point_passthrough(self) -> None:
        """
        Ensure read_eq3_output returns parser.point directly.
        """
        expected_point = SimpleNamespace(stage="eq3")
        parser_instance = mock.Mock()
        parser_instance.parse.return_value = SimpleNamespace(point=expected_point)

        with mock.patch(
            "eleanor.kernel.eq36.kernel.OutputParser3", return_value=parser_instance
        ) as parser_cls:
            point = Eq36Kernel.read_eq3_output(file="custom.3o")

        parser_cls.assert_called_once_with(file="custom.3o")
        self.assertIs(point, expected_point)

    def test_read_eq3_output_asserts_when_parser_point_is_missing(self) -> None:
        """
        Ensure read_eq3_output asserts when parser.point is None.
        """
        parser_instance = mock.Mock()
        parser_instance.parse.return_value = SimpleNamespace(point=None)

        with mock.patch(
            "eleanor.kernel.eq36.kernel.OutputParser3", return_value=parser_instance
        ):
            with self.assertRaises(AssertionError):
                Eq36Kernel.read_eq3_output()

    def test_read_eq6_output_track_path_false_keeps_last_step_only(self) -> None:
        """
        Ensure read_eq6_output with track_path=False returns only the final parsed point.
        """
        first = SimpleNamespace(log_xi=-2.0)
        last = SimpleNamespace(log_xi=-1.0)
        parser_instance = mock.Mock()
        parser_instance.parse.return_value = SimpleNamespace(path=[first, last])

        with mock.patch(
            "eleanor.kernel.eq36.kernel.OutputParser6", return_value=parser_instance
        ) as parser_cls:
            points = Eq36Kernel.read_eq6_output(file="custom.6o", track_path=False)

        parser_cls.assert_called_once_with(file="custom.6o")
        self.assertEqual(points, [last])
        self.assertIs(points[0], last)

    def test_read_eq6_output_track_path_true_returns_full_path(self) -> None:
        """
        Ensure read_eq6_output with track_path=True returns the full parser path object.
        """
        first = SimpleNamespace(log_xi=-2.0)
        last = SimpleNamespace(log_xi=-1.0)
        path = [first, last]
        parser_instance = mock.Mock()
        parser_instance.parse.return_value = SimpleNamespace(path=path)

        with mock.patch(
            "eleanor.kernel.eq36.kernel.OutputParser6", return_value=parser_instance
        ):
            points = Eq36Kernel.read_eq6_output(track_path=True)

        self.assertIs(points, path)

    def test_read_eq6_output_track_path_false_handles_empty_paths(self) -> None:
        """
        Ensure read_eq6_output with track_path=False returns an empty list when no points were parsed.
        """
        parser_instance = mock.Mock()
        parser_instance.parse.return_value = SimpleNamespace(path=[])

        with mock.patch(
            "eleanor.kernel.eq36.kernel.OutputParser6", return_value=parser_instance
        ):
            points = Eq36Kernel.read_eq6_output(track_path=False)

        self.assertEqual(points, [])
