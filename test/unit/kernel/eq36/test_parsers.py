import io
import warnings
from pathlib import Path
from typing import cast, override
from unittest import TestCase, mock

import eleanor.equilibrium_space as es
import numpy as np
from eleanor.kernel.eq36.codes import RunCode
from eleanor.kernel.eq36.parsers import OutputParser, OutputParser3, OutputParser6
from eleanor.kernel.exceptions import EleanorKernelException


class DummyOutputParser(OutputParser):
    @override
    def read_elemental_composition(self) -> None:
        pass

    @override
    def read_numerical_composition(self) -> None:
        pass

    @override
    def read_sensible_composition(self) -> None:
        pass

    @override
    def read_bulk_properties(self) -> None:
        pass

    @override
    def read_charge_balance(self) -> None:
        pass

    @override
    def parse(self):
        return self


class TestEq36Parsers(TestCase):
    """
    Tests of selected base-parser behavior in eleanor.kernel.eq36.parsers.
    """

    @staticmethod
    def _parser(text: str) -> DummyOutputParser:
        return DummyOutputParser(io.StringIO(text))

    def test_read_reactants_nonpositive_values_emit_no_warnings_and_keep_ideals(
        self,
    ) -> None:
        """
        Ensure reactant log fields keep expected -inf/nan ideals without surfacing warnings.
        """
        parser = self._parser(
            "--- Reactant Summary ---\n"
            " Reactant Moles Delta moles Mass, g Delta mass, g\n"
            "\n"
            "R1 0.0 -1.0 0.0 -2.0\n"
            "\n"
            "Mass remaining=0 grams\n"
            "Mass destroyed=1 grams\n"
            " Reactant Affinity Rel. Rate\n"
            "h1\n"
            "h2\n"
            "R1 1.0 1.0\n"
            "\n"
            "Affinity of the overall irreversible reaction=0.0 kcal\n"
            "\n"
        )

        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            parser.read_reactants()

        self.assertEqual(len(captured), 0)
        self.assertEqual(len(parser._reactants), 1)
        reactant = parser._reactants[0]
        self.assertTrue(np.isneginf(reactant.log_moles_remaining))
        self.assertTrue(np.isnan(reactant.log_moles_reacted))
        self.assertTrue(np.isneginf(reactant.log_mass_remaining))
        self.assertTrue(np.isnan(reactant.log_mass_reacted))

    def test_outputparser3_file_not_found_wrapped(self) -> None:
        """
        Ensure OutputParser3 wraps missing file errors in EleanorKernelException with code.
        """
        with mock.patch.object(Path, "open", side_effect=FileNotFoundError("missing")):
            with self.assertRaises(EleanorKernelException) as cm:
                OutputParser3("missing.3o")
        self.assertEqual(cm.exception.code, RunCode.NO_3O_FILE)

    def test_outputparser6_check_path_termination_normal_and_early(self) -> None:
        """
        Ensure OutputParser6 termination checker accepts normal and rejects early termination.
        """
        normal = OutputParser6(
            io.StringIO("header\n --- The reaction path has terminated normally ---\n")
        )
        normal.line_num = len(normal.lines)
        normal.check_path_termination()

        early = OutputParser6(
            io.StringIO("header\n --- The reaction path has terminated early ---\n")
        )
        early.line_num = len(early.lines)
        with self.assertRaises(EleanorKernelException) as cm:
            early.check_path_termination()
        self.assertEqual(cm.exception.code, RunCode.EQ6_EARLY_TERMINATION)

    def test_outputparser6_check_path_termination_missing_status_raises(self) -> None:
        """
        Ensure OutputParser6 termination checker raises when no status marker is present.
        """
        parser = OutputParser6(io.StringIO("header\nno status here\n"))
        parser.line_num = len(parser.lines)
        with self.assertRaises(EleanorKernelException) as cm:
            parser.check_path_termination()
        self.assertEqual(cm.exception.code, RunCode.EQ6_ERROR)

    def test_outputparser6_parse_raises_for_missing_xi_separator(self) -> None:
        """
        Ensure OutputParser6.parse surfaces a strict error when Xi step separators are missing.
        """
        parser = OutputParser6(
            io.StringIO(
                "Stepping to Xi\nXi=0\n --- The reaction path has terminated normally ---\n"
            )
        )
        with self.assertRaisesRegex(
            EleanorKernelException, "expected path separator after Stepping to Xi"
        ):
            parser.parse()

    def test_read_pure_solid_saturation_states_rejects_invalid_state_token(
        self,
    ) -> None:
        """
        Ensure pure-solid saturation parsing rejects unrecognized state tokens.
        """
        parser = self._parser(
            " --- Saturation States of Pure Solids ---\n"
            " Phase Log Q/K Affinity, kcal\n"
            " hdr\n"
            "CALCITE -1.0 2.0 INVALID\n"
            "\n"
        )
        with self.assertRaises(EleanorKernelException):
            parser.read_pure_solid_saturation_states()

    def test_read_log_property_rejects_empty_name(self) -> None:
        """
        Ensure read_log_property rejects empty property names.
        """
        parser = self._parser("value=1\n")
        with self.assertRaises(EleanorKernelException):
            parser.read_log_property("")

    def test_read_end_member_saturations_unknown_end_member_raises_parser_error(
        self,
    ) -> None:
        """
        Ensure end-member saturation parsing raises a parser error for unknown end members.
        """
        parser = self._parser("UNKNOWN -2.0 1.0\n\n")
        with self.assertRaises(EleanorKernelException):
            parser.read_end_member_saturations("Solid Solution Product Phases", {})

    def test_outputparser6_read_elemental_composition_mgkg_table(self) -> None:
        """
        Ensure OutputParser6 elemental-composition parsing supports mg/kg.sol + Molality tables.
        """
        parser = OutputParser6(
            io.StringIO(
                " --- Elemental Composition of the Aqueous Solution ---\n"
                "h1\n"
                " Element mg/kg.sol Molality\n"
                "h2\n"
                "Na 1000 1e-2\n"
                "\n"
            )
        )

        parser.read_elemental_composition()

        self.assertEqual(len(parser._elements), 1)
        na = parser._elements[0]
        self.assertEqual(na.name, "Na")
        self.assertEqual(na.mass_fraction, 1e-3)
        self.assertEqual(na.log_molality, -2.0)

    def test_outputparser6_read_elemental_composition_mgl_table(self) -> None:
        """
        Ensure OutputParser6 elemental-composition parsing supports mg/L + mg/kg.sol + Molarity + Molality tables.
        """
        parser = OutputParser6(
            io.StringIO(
                " --- Elemental Composition of the Aqueous Solution ---\n"
                "h1\n"
                " Element mg/L mg/kg.sol Molarity Molality\n"
                "h2\n"
                "Na 1000 2000 3e-2 4e-2\n"
                "\n"
            )
        )

        parser.read_elemental_composition()

        self.assertEqual(len(parser._elements), 1)
        na = parser._elements[0]
        self.assertEqual(na.name, "Na")
        self.assertEqual(na.mass_fraction, 2e-3)
        self.assertAlmostEqual(na.log_molality, np.log10(4e-2))

    def test_outputparser6_read_numerical_composition_mgl_table(self) -> None:
        """
        Ensure OutputParser6 numerical-composition parsing supports the 4-column Species table.
        """
        parser = OutputParser6(
            io.StringIO(
                " --- Numerical Composition of the Aqueous Solution ---\n"
                "h1\n"
                " Species mg/L mg/kg.sol Molarity Molality\n"
                "h2\n"
                "HCO3- 500 600 1e-2 2e-2\n"
                "\n"
            )
        )

        parser.read_numerical_composition()

        self.assertEqual(parser.line().strip(), "")

    def test_outputparser6_read_charge_balance_parses_and_scales_per_unit_values(
        self,
    ) -> None:
        """
        Ensure OutputParser6 charge-balance parser reads expected aggregate values.
        """
        parser = OutputParser6(
            io.StringIO(
                " --- Aqueous Solution Charge Balance ---\n"
                "h1\n"
                "Actual Charge imbalance=1 eq\n"
                "Expected Charge imbalance=2 eq\n"
                "Charge discrepancy=3 eq\n"
                "Sigma |equivalents|=4 eq\n"
                "gap\n"
                "Actual Charge imbalance=5 eq/kg.solu\n"
                "Expected Charge imbalance=6 eq/kg.solu\n"
                "Charge discrepancy=7 eq/kg.solu\n"
                "Sigma |equivalents|=8 eq/kg.solu\n"
                "gap2\n"
                "Relative charge discrepancy=9\n"
            )
        )

        parser.read_charge_balance()

        self.assertEqual(parser._charge_imbalance, 1.0)
        self.assertEqual(parser._expected_charge_imbalance, 2.0)
        self.assertEqual(parser._charge_discrepancy, 3.0)
        self.assertEqual(parser._sigma, 4.0)

    def test_outputparser6_file_not_found_wrapped(self) -> None:
        """
        Ensure OutputParser6 wraps missing-file errors in EleanorKernelException with NO_6O_FILE code.
        """
        with mock.patch.object(Path, "open", side_effect=FileNotFoundError("missing")):
            with self.assertRaises(EleanorKernelException) as cm:
                OutputParser6("missing.6o")
        self.assertEqual(cm.exception.code, RunCode.NO_6O_FILE)

    def test_outputparser6_parse_with_no_steps_checks_termination(self) -> None:
        """
        Ensure OutputParser6.parse checks termination even when no Xi step is found.
        """
        parser = OutputParser6(io.StringIO(""))

        with (
            mock.patch.object(parser, "advance_to_xi_step", return_value=False),
            mock.patch.object(parser, "parse_step") as parse_step,
            mock.patch.object(
                parser, "check_path_termination"
            ) as check_path_termination,
        ):
            result = parser.parse()

        self.assertIs(result, parser)
        parse_step.assert_not_called()
        check_path_termination.assert_called_once()

    def test_outputparser6_parse_step_appends_snapshot_and_resets_data(self) -> None:
        """
        Ensure parse_step appends parsed step data to path and resets transient state.
        """
        parser = OutputParser6(io.StringIO(""))

        def fake_read_basic_property(name: str, units=None, advance=True):  # noqa: ARG001
            values = {"Xi": 1.0, "Temperature": 1.0, "Pressure": 1.0}
            return np.float64(values.get(name, 0.0))

        with (
            mock.patch.object(parser, "consume_blank_lines"),
            mock.patch.object(parser, "advance"),
            mock.patch.object(
                parser, "read_basic_property", side_effect=fake_read_basic_property
            ),
            mock.patch.object(parser, "read_reactants"),
            mock.patch.object(parser, "read_elemental_composition"),
            mock.patch.object(parser, "read_numerical_composition"),
            mock.patch.object(parser, "read_sensible_composition"),
            mock.patch.object(parser, "read_pH_like"),
            mock.patch.object(parser, "read_bulk_properties"),
            mock.patch.object(parser, "read_charge_balance"),
            mock.patch.object(parser, "read_aqueous_solute"),
            mock.patch.object(parser, "read_redox_reactions"),
            mock.patch.object(parser, "read_solid_phases"),
            mock.patch.object(parser, "read_aqueous_saturation_states"),
            mock.patch.object(parser, "read_pure_solid_saturation_states"),
            mock.patch.object(parser, "read_liquid_saturation_states"),
            mock.patch.object(parser, "read_solid_solution_saturation_states"),
            mock.patch.object(parser, "read_product_phases"),
            mock.patch.object(parser, "read_fugacities"),
        ):
            result = parser.parse_step()

        self.assertIs(result, parser)
        self.assertEqual(len(parser.path), 1)
        step = parser.path[0]
        self.assertEqual(step.stage, "eq6")
        self.assertEqual(step.temperature, 1.0)
        self.assertEqual(step.pressure, 1.0)
        self.assertEqual(step.log_xi, 0.0)
        self.assertEqual(parser._xi, 0.0)
        self.assertEqual(parser._log_xi, 0.0)
        self.assertEqual(parser._elements, [])

    def test_outputparser6_parse_step_wraps_internal_errors(self) -> None:
        """
        Ensure parse_step wraps internal failures in EleanorKernelException.
        """
        parser = OutputParser6(io.StringIO(""))

        def fake_read_basic_property(name: str, units=None, advance=True):  # noqa: ARG001
            values = {"Xi": 1.0, "Temperature": 1.0, "Pressure": 1.0}
            return np.float64(values.get(name, 0.0))

        with (
            mock.patch.object(parser, "consume_blank_lines"),
            mock.patch.object(parser, "advance"),
            mock.patch.object(
                parser, "read_basic_property", side_effect=fake_read_basic_property
            ),
            mock.patch.object(
                parser, "read_reactants", side_effect=RuntimeError("boom")
            ),
        ):
            with self.assertRaisesRegex(
                EleanorKernelException, "failed to parse EQ6 output"
            ):
                parser.parse_step()

    def test_outputparser3_parse_raises_on_early_termination_marker_absence(
        self,
    ) -> None:
        """
        Ensure OutputParser3.parse raises EQ3_EARLY_TERMINATION when final normal-exit marker is absent.
        """
        parser = OutputParser3(io.StringIO("not normal exit\n"))

        with (
            mock.patch.object(parser, "consume_to_pattern"),
            mock.patch.object(parser, "advance"),
            mock.patch.object(
                parser, "read_basic_property", return_value=np.float64(1.0)
            ),
            mock.patch.object(parser, "read_elemental_composition"),
            mock.patch.object(parser, "read_numerical_composition"),
            mock.patch.object(parser, "read_sensible_composition"),
            mock.patch.object(parser, "read_bulk_properties"),
            mock.patch.object(parser, "read_pH_like"),
            mock.patch.object(parser, "read_alkalinity"),
            mock.patch.object(parser, "read_charge_balance"),
            mock.patch.object(parser, "read_aqueous_solute"),
            mock.patch.object(parser, "read_redox_reactions"),
            mock.patch.object(parser, "read_aqueous_saturation_states"),
            mock.patch.object(parser, "read_pure_solid_saturation_states"),
            mock.patch.object(parser, "read_liquid_saturation_states"),
            mock.patch.object(parser, "read_solid_solution_saturation_states"),
            mock.patch.object(parser, "read_product_phases"),
            mock.patch.object(parser, "read_fugacities"),
        ):
            with self.assertRaises(EleanorKernelException) as cm:
                parser.parse()

        self.assertEqual(cm.exception.code, RunCode.EQ3_EARLY_TERMINATION)

    def test_outputparser3_read_charge_balance_falls_back_to_log_activity_table(
        self,
    ) -> None:
        """
        Ensure OutputParser3 charge-balance parser falls back to log-activity table parsing when needed.
        """
        parser = OutputParser3(
            io.StringIO(
                " --- Electrical Balance Totals ---\n"
                "h1\n"
                "h2\n"
                "h3\n"
                "Sigma(mz) cations=1.0\n"
                "Sigma(mz) anions=0.9\n"
                "Total charge=0.1\n"
                "Mean charge=0.05\n"
                "Charge imbalance=0.01\n"
                "skip1\n"
                "skip2\n"
                "skip3\n"
                "skip4\n"
                "7.5 %\n"
                "8.5 %\n"
                "skip5\n"
                "skip6\n"
                " --- Electrical Balancing on H+ ---\n"
                "b1\n"
                "b2\n"
                "b3\n"
                "PHASE1 -1.2\n"
                "\n"
            )
        )

        parser.read_charge_balance()

        self.assertEqual(parser._cations, 1.0)
        self.assertEqual(parser._anions, 0.9)
        self.assertEqual(parser._total_charge, 0.1)
        self.assertEqual(parser._mean_charge, 0.05)
        self.assertEqual(parser._charge_imbalance, 0.01)

    def test_outputparser6_read_numerical_composition_mgkg_table(self) -> None:
        """
        Ensure OutputParser6 numerical-composition parsing supports mg/kg.sol + Molality tables.
        """
        parser = OutputParser6(
            io.StringIO(
                " --- Numerical Composition of the Aqueous Solution ---\n"
                "h1\n"
                " Species mg/kg.sol Molality\n"
                "h2\n"
                "Na+ 1000 1e-2\n"
                "\n"
            )
        )

        parser.read_numerical_composition()

        self.assertEqual(parser.line().strip(), "")

    def test_outputparser6_read_sensible_composition_mgkg_table(self) -> None:
        """
        Ensure OutputParser6 sensible-composition parsing supports mg/kg.sol + Molality tables.
        """
        parser = OutputParser6(
            io.StringIO(
                " --- Sensible Composition of the Aqueous Solution ---\n"
                "h1\n"
                " Species mg/kg.sol Molality\n"
                "h2\n"
                "CO2(aq) 300 2e-3\n"
                "\n"
            )
        )

        parser.read_sensible_composition()

        self.assertEqual(parser.line().strip(), "")

    def test_outputparser6_read_sensible_composition_mgl_table(self) -> None:
        """
        Ensure OutputParser6 sensible-composition parsing supports mg/L + mg/kg.sol + Molarity + Molality tables.
        """
        parser = OutputParser6(
            io.StringIO(
                " --- Sensible Composition of the Aqueous Solution ---\n"
                "h1\n"
                " Species mg/L mg/kg.sol Molarity Molality\n"
                "h2\n"
                "CO2(aq) 200 300 1e-3 2e-3\n"
                "\n"
            )
        )

        parser.read_sensible_composition()

        self.assertEqual(parser.line().strip(), "")

    def test_read_alkalinity_parses_multiple_sections_and_filters_units(self) -> None:
        """
        Ensure read_alkalinity captures the Extended total and ignores unsupported detail rows.
        """
        parser = self._parser(
            "prefix\n"
            "Alkalinity report\n"
            " --- Carbonate Total Alkalinity --\n"
            "header\n"
            "1.20 eq/kg\n"
            "0.30 eq CO3--\n"
            "0.40 mmol/L HCO3-\n"
            "malformed\n"
            "\n"
            " --- Extended Total Alkalinity --\n"
            "header\n"
            "2.20 eq/kg\n"
            "0.90 eq OH-\n"
            "\n"
        )

        parser.read_alkalinity()

        self.assertEqual(parser._extended_alkalinity, 2.20)

    def test_outputparser3_read_charge_balance_concentration_table_path(self) -> None:
        """
        Ensure OutputParser3 charge-balance parser accepts concentration-table layout.
        """
        parser = OutputParser3(
            io.StringIO(
                " --- Electrical Balance Totals ---\n"
                "h1\n"
                "h2\n"
                "h3\n"
                "Sigma(mz) cations=1.0\n"
                "Sigma(mz) anions=0.9\n"
                "Total charge=0.1\n"
                "Mean charge=0.05\n"
                "Charge imbalance=0.01\n"
                "skip1\n"
                "skip2\n"
                "skip3\n"
                "skip4\n"
                "7.5 %\n"
                "8.5 %\n"
                "skip5\n"
                "skip6\n"
                " --- Electrical Balancing on Cl- ---\n"
                "b1\n"
                "b2\n"
                "b3\n"
                "PHASE1 1000 2000 0.3\n"
                "\n"
            )
        )

        parser.read_charge_balance()

        self.assertEqual(parser._cations, 1.0)
        self.assertEqual(parser._anions, 0.9)
        self.assertEqual(parser._total_charge, 0.1)
        self.assertEqual(parser._mean_charge, 0.05)
        self.assertEqual(parser._charge_imbalance, 0.01)

    def test_outputparser6_composition_readers_reject_unknown_headers(self) -> None:
        """
        Ensure EQ6 composition readers reject unknown table headers across elemental, numerical, and sensible blocks.
        """
        cases = [
            (
                "read_elemental_composition",
                "Elemental Composition of the Aqueous Solution",
                " Element unexpected columns",
            ),
            (
                "read_numerical_composition",
                "Numerical Composition of the Aqueous Solution",
                " Species unknown columns",
            ),
            (
                "read_sensible_composition",
                "Sensible Composition of the Aqueous Solution",
                " Species unexpected columns",
            ),
        ]

        for method_name, section_header, bad_header in cases:
            with self.subTest(method=method_name):
                parser = OutputParser6(
                    io.StringIO(f" --- {section_header} ---\nh1\n{bad_header}\nh2\n")
                )
                with self.assertRaises(EleanorKernelException):
                    getattr(parser, method_name)()

    def test_read_solid_blocks_handles_starred_and_malformed_rows(self) -> None:
        """
        Ensure read_solid_blocks skips starred rows and raises a parser error for malformed solid rows.
        """
        with self.subTest("starred rows"):
            parser = self._parser("STAR1 * * * *\nSTAR2 * * * *\n\n")
            parser.read_solid_blocks()
            self.assertEqual(parser._pure_solids, {})
            self.assertEqual(parser._solid_solutions, {})
            self.assertEqual(parser.line_num, 3)

        with self.subTest("malformed row"):
            parser = self._parser("None\n\n")
            with self.assertRaises(EleanorKernelException):
                parser.read_solid_blocks()

    def test_read_product_phases_missing_header_raises_and_does_not_mutate_data(
        self,
    ) -> None:
        """
        Ensure missing product-phases headers raise and leave existing parser solids state untouched.
        """
        parser = self._parser(" --- Some Other Section ---\nbody\n")
        snapshot = dict(parser._solid_solutions)

        with self.assertRaises(EleanorKernelException):
            parser.read_product_phases("Solid Solution Product Phases")

        self.assertEqual(parser._solid_solutions, snapshot)


class TestEq36ParsersRealOutputs(TestCase):
    """
    End-to-end parser checks against real EQ3/6 fixture outputs.
    """

    fixture_root = Path(__file__).resolve().parents[3] / "data" / "eq36_parsers"

    def _fixture_path(self, case: str, filename: str) -> str:
        return str(self.fixture_root / case / filename)

    def _parse_eq3(self, case: str) -> es.Point:
        parser = OutputParser3(self._fixture_path(case, "problem.3o")).parse()
        if parser.point is None:
            raise AssertionError("expected eq3 parser to populate point")
        return parser.point

    def _parse_eq6_path(self, case: str) -> list[es.Point]:
        return OutputParser6(self._fixture_path(case, "problem.6o")).parse().path

    @staticmethod
    def _find_aqueous(point: es.Point, name: str) -> es.AqueousSpecies:
        for species in point.aqueous_species:
            if species.name == name:
                return species
        raise AssertionError(f"expected aqueous species {name}")

    @staticmethod
    def _find_pure_solid(point: es.Point, name: str) -> es.PureSolid:
        for solid in point.pure_solids:
            if solid.name == name:
                return solid
        raise AssertionError(f"expected pure solid {name}")

    def test_outputparser3_real_outputs_have_expected_core_fields(self) -> None:
        """
        Ensure EQ3 parser produces expected scalar values and section sizes for real fixture outputs.
        """
        expected_by_case = {
            "200": {
                "temperature": 200.0,
                "pressure": 300.0,
                "nbs_pH": 2.5459,
                "pcH": 5.4936,
                "pHCl": 11.6085,
                "h_log_activity": -2.5459,
                "barite_log_qk": -4.38511,
                "barite_affinity": -9.49402,
            },
            "250": {
                "temperature": 250.0,
                "pressure": 300.0,
                "nbs_pH": 2.5549,
                "pcH": 5.4936,
                "pHCl": 11.6373,
                "h_log_activity": -2.5549,
                "barite_log_qk": -4.51197,
                "barite_affinity": -10.80097,
            },
        }

        for case, expected in expected_by_case.items():
            with self.subTest(case=case):
                point = self._parse_eq3(case)
                hydrogen = self._find_aqueous(point, "H+")
                barite = self._find_pure_solid(point, "barite")

                self.assertEqual(point.stage, "eq3")
                self.assertAlmostEqual(
                    float(point.temperature), expected["temperature"]
                )
                self.assertAlmostEqual(float(point.pressure), expected["pressure"])
                self.assertAlmostEqual(float(point.log_fO2), -3.0)
                self.assertAlmostEqual(float(point.pH), expected["nbs_pH"])
                assert point.custom_properties.get("pcH") is not None
                assert point.custom_properties.get("pHCl") is not None
                self.assertAlmostEqual(
                    cast(np.float64, point.custom_properties["pcH"]), expected["pcH"]
                )
                self.assertAlmostEqual(
                    cast(np.float64, point.custom_properties["pHCl"]), expected["pHCl"]
                )
                self.assertAlmostEqual(
                    float(hydrogen.log_activity), expected["h_log_activity"]
                )
                self.assertEqual(len(point.elements), 16)
                self.assertEqual(len(point.aqueous_species), 132)
                self.assertEqual(len(point.pure_solids), 143)
                self.assertEqual(len(point.solid_solutions), 27)
                self.assertEqual(len(point.gases), 0)
                self.assertEqual(len(point.redox_reactions), 1)
                self.assertAlmostEqual(float(barite.log_qk), expected["barite_log_qk"])
                self.assertAlmostEqual(
                    float(barite.affinity), expected["barite_affinity"]
                )

    def test_outputparser6_real_outputs_have_expected_path_shape_and_endpoints(
        self,
    ) -> None:
        """
        Ensure EQ6 parser produces expected path length, endpoint values, and count invariants.
        """
        expected_by_case = {
            "200": {
                "steps": 424,
                "temperature": 200.0,
                "nbs_pH_first": 2.5459,
                "nbs_pH_last": 6.7168,
                "log_fO2_last": -51.259,
                "aqueous_first_count": 123,
                "aqueous_last_count": 127,
                "overall_affinity_first": 65.594,
                "overall_affinity_last": 1.762,
                "solids_created_mass_last": 22.6757,
                "solids_net_mass_last": 2.6757,
            },
            "250": {
                "steps": 375,
                "temperature": 250.0,
                "nbs_pH_first": 2.5549,
                "nbs_pH_last": 6.3215,
                "log_fO2_last": -44.962,
                "aqueous_first_count": 124,
                "aqueous_last_count": 128,
                "overall_affinity_first": 66.648,
                "overall_affinity_last": 1.1145,
                "solids_created_mass_last": 22.6796,
                "solids_net_mass_last": 2.67958,
            },
        }

        for case, expected in expected_by_case.items():
            with self.subTest(case=case):
                path = self._parse_eq6_path(case)
                self.assertEqual(len(path), expected["steps"])

                first = path[0]
                last = path[-1]

                self.assertEqual(first.stage, "eq6")
                self.assertEqual(last.stage, "eq6")
                assert first.log_xi is not None
                assert last.log_xi is not None
                self.assertTrue(np.isneginf(float(first.log_xi)))
                self.assertAlmostEqual(float(last.log_xi), -0.9188868277797307)

                self.assertAlmostEqual(
                    float(first.temperature), expected["temperature"]
                )
                self.assertAlmostEqual(float(first.pressure), 300.0)
                self.assertAlmostEqual(float(last.temperature), expected["temperature"])
                self.assertAlmostEqual(float(last.pressure), 300.0)
                self.assertAlmostEqual(float(first.log_fO2), -3.0)
                self.assertAlmostEqual(float(last.log_fO2), expected["log_fO2_last"])
                self.assertAlmostEqual(float(first.pH), expected["nbs_pH_first"])
                self.assertAlmostEqual(float(last.pH), expected["nbs_pH_last"])

                self.assertEqual(len(first.elements), 16)
                self.assertEqual(len(last.elements), 16)
                self.assertEqual(
                    len(first.aqueous_species), expected["aqueous_first_count"]
                )
                self.assertEqual(
                    len(last.aqueous_species), expected["aqueous_last_count"]
                )
                self.assertEqual(len(first.gases), 11)
                self.assertEqual(len(last.gases), 11)
                self.assertEqual(len(first.pure_solids), 143)
                self.assertEqual(len(last.pure_solids), 144)
                self.assertEqual(len(first.solid_solutions), 27)
                self.assertEqual(len(last.solid_solutions), 27)
                self.assertFalse(
                    any(species.name == "O2(g)" for species in first.aqueous_species)
                )

                first_reactant_names = sorted(
                    reactant.name for reactant in first.reactants
                )
                self.assertEqual(first_reactant_names, ["olivine-ss"])
                assert first.custom_properties.get("overall_affinity") is not None
                assert last.custom_properties.get("overall_affinity") is not None
                assert last.custom_properties.get("solid_mass_created") is not None
                assert last.custom_properties.get("solid_mass_change") is not None
                self.assertAlmostEqual(
                    cast(np.float64, first.custom_properties["overall_affinity"]),
                    expected["overall_affinity_first"],
                )
                self.assertAlmostEqual(
                    cast(np.float64, last.custom_properties["overall_affinity"]),
                    expected["overall_affinity_last"],
                )
                self.assertAlmostEqual(
                    cast(np.float64, last.custom_properties["solid_mass_created"]),
                    expected["solids_created_mass_last"],
                )
                self.assertAlmostEqual(
                    cast(np.float64, last.custom_properties["solid_mass_change"]),
                    expected["solids_net_mass_last"],
                )

                log_xis: list[float] = []
                for step in path:
                    assert step.log_xi is not None
                    log_xis.append(float(step.log_xi))
                for left, right in zip(log_xis, log_xis[1:], strict=False):
                    self.assertLessEqual(left, right)

    def test_outputparser6_first_step_matches_outputparser3_initial_state(self) -> None:
        """
        Ensure EQ6 first-step state matches EQ3 output for shared initial-state quantities.
        """
        for case in ("200", "250"):
            with self.subTest(case=case):
                eq3 = self._parse_eq3(case)
                eq6_first = self._parse_eq6_path(case)[0]

                eq3_hydrogen = self._find_aqueous(eq3, "H+")
                eq6_hydrogen = self._find_aqueous(eq6_first, "H+")

                self.assertAlmostEqual(
                    float(eq3.temperature), float(eq6_first.temperature)
                )
                self.assertAlmostEqual(float(eq3.pressure), float(eq6_first.pressure))
                self.assertAlmostEqual(float(eq3.log_fO2), float(eq6_first.log_fO2))
                self.assertAlmostEqual(float(eq3.pH), float(eq6_first.pH))
                assert eq3.custom_properties.get("pHCl") is not None
                assert eq6_first.custom_properties.get("pHCl") is not None
                self.assertAlmostEqual(
                    cast(np.float64, eq3.custom_properties["pHCl"]),
                    cast(np.float64, eq6_first.custom_properties["pHCl"]),
                )
                self.assertAlmostEqual(
                    eq3_hydrogen.log_activity, eq6_hydrogen.log_activity
                )
