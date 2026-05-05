import io
import warnings
from typing import cast, override
from unittest import mock

import numpy as np

from eleanor.exceptions import EleanorException, EleanorFileException, EleanorParserException
from eleanor.kernel.eq36.codes import RunCode
from eleanor.kernel.eq36.parsers import OutputParser
from eleanor.kernel.eq36.parsers import OutputParser3 as _OutputParser3
from eleanor.kernel.eq36.parsers import OutputParser6 as _OutputParser6

from ...common import AnyDict, TestCase, as_any_dict


class OutputParser3(_OutputParser3):
    data: AnyDict


class OutputParser6(_OutputParser6):
    data: AnyDict


class DummyOutputParser(OutputParser):
    data: AnyDict

    @override
    def read_elemental_composition(self):
        pass

    @override
    def read_numerical_composition(self):
        pass

    @override
    def read_sensible_composition(self):
        pass

    @override
    def read_bulk_properties(self):
        pass

    @override
    def read_charge_balance(self):
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

    def test_navigation_helpers_consume_and_unconsume_patterns(self):
        """
        Ensure consume/unconsume helpers move line cursor to expected matching lines.
        """
        parser = self._parser("first\nsecond\nthird\n")
        parser.consume_to_pattern(r"^third$")
        self.assertEqual(parser.line_num, 2)
        self.assertEqual(parser.line().strip(), "third")

        parser.unconsume_to_pattern(r"^second$")
        self.assertEqual(parser.line_num, 1)
        self.assertEqual(parser.line().strip(), "second")

    def test_read_key_value_helpers_and_basic_property(self):
        """
        Ensure primitive key/value parsing and basic-property storage behave as expected.
        """
        parser = self._parser("tempc=25.0\npress=2.0 bars\n")
        key, value = parser.read_key_value()
        self.assertEqual(key, "tempc")
        self.assertEqual(value, 25.0)

        parser.advance()
        key, value, unit = parser.read_key_value_unit()
        self.assertEqual(key, "press")
        self.assertEqual(value, 2.0)
        self.assertEqual(unit, "bars")

        parser = self._parser("pressure=1.0 bars\n")
        custom_data = {}
        parser.read_basic_property("pressure", key="p", units=["bars", "bar"], data=custom_data, advance=False)
        self.assertEqual(custom_data["p"], 1.0)
        self.assertEqual(parser.line_num, 0)

    def test_read_basic_property_unit_validation_error(self):
        """
        Ensure read_basic_property rejects unexpected units.
        """
        parser = self._parser("pressure=1.0 pascal\n")
        with self.assertRaises(EleanorParserException):
            parser.read_basic_property("pressure", key="p", units=["bars", "bar"])

    def test_read_basic_table_row_names_exact_cardinality_succeeds(self):
        """
        Ensure read_basic_table accepts exactly matching row_names cardinality.
        """
        parser = self._parser("unused1 1.0\nunused2 2.0\n\n")
        table = parser.read_basic_table("value", row_names=["row1", "row2"])
        self.assertEqual(table["row1"]["value"], 1.0)
        self.assertEqual(table["row2"]["value"], 2.0)

    def test_read_reactants_none_builds_empty_structure(self):
        """
        Ensure a None reactant summary yields an explicit empty structure.
        """
        parser = self._parser("--- Reactant Summary ---\n Reactant Moles Delta moles Mass, g Delta mass, g\n\nNone\n")

        parser.read_reactants()

        self.assertIn("reactants", parser.data)
        self.assertEqual(parser.data["reactants"], {})

    def test_read_basic_table_row_names_too_many_rows_raises_parser_error(self):
        """
        Ensure row_names length is enforced when more table rows are present.
        """
        parser = self._parser("a 1.0\nb 2.0\n")

        with self.assertRaises(EleanorParserException):
            parser.read_basic_table("x", row_names=["only_one"])

    def test_read_basic_table_row_names_too_few_rows_raises_parser_error(self):
        """
        Ensure row_names length is enforced when fewer table rows are present.
        """
        parser = self._parser("a 1.0\n\n")

        with self.assertRaises(EleanorParserException):
            parser.read_basic_table("x", row_names=["row1", "row2"])

    def test_read_log_property_requires_string_key(self):
        """
        Ensure read_log_property requires key to be a string.
        """
        parser_missing = self._parser("Oxygen fugacity=1.0 bars\nLog oxygen fugacity=0.0\n")
        with self.assertRaises(EleanorParserException):
            parser_missing.read_log_property("Oxygen fugacity", units=["bars", "bar"])

        parser_nonstring = self._parser("Oxygen fugacity=1.0 bars\nLog oxygen fugacity=0.0\n")
        with self.assertRaises(EleanorParserException):
            parser_nonstring.read_log_property("Oxygen fugacity", key=cast(str, cast(object, 1)), units=["bars", "bar"])

    def test_read_reactants_nonpositive_values_emit_no_warnings_and_keep_ideals(self):
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
        reactant = as_any_dict(as_any_dict(as_any_dict(parser.data)["reactants"])["reactants"])["R1"]
        self.assertTrue(np.isneginf(reactant["log_moles_remaining"]))
        self.assertTrue(np.isnan(reactant["log_moles_reacted"]))
        self.assertTrue(np.isneginf(reactant["log_mass_remaining"]))
        self.assertTrue(np.isnan(reactant["log_mass_reacted"]))

    def test_outputparser3_file_not_found_wrapped(self):
        """
        Ensure OutputParser3 wraps missing file errors in EleanorFileException with code.
        """
        with mock.patch("builtins.open", side_effect=FileNotFoundError("missing")):
            with self.assertRaises(EleanorFileException) as cm:
                OutputParser3("missing.3o")
        self.assertEqual(cm.exception.code, RunCode.NO_3O_FILE)

    def test_outputparser6_check_path_termination_normal_and_early(self):
        """
        Ensure OutputParser6 termination checker accepts normal and rejects early termination.
        """
        normal = OutputParser6(io.StringIO("header\n --- The reaction path has terminated normally ---\n"))
        normal.line_num = len(normal.lines)
        normal.check_path_termination()

        early = OutputParser6(io.StringIO("header\n --- The reaction path has terminated early ---\n"))
        early.line_num = len(early.lines)
        with self.assertRaises(EleanorException) as cm:
            early.check_path_termination()
        self.assertEqual(cm.exception.code, RunCode.EQ6_EARLY_TERMINATION)

    def test_outputparser6_check_path_termination_missing_status_raises(self):
        """
        Ensure OutputParser6 termination checker raises when no status marker is present.
        """
        parser = OutputParser6(io.StringIO("header\nno status here\n"))
        parser.line_num = len(parser.lines)
        with self.assertRaises(EleanorException) as cm:
            parser.check_path_termination()
        self.assertEqual(cm.exception.code, RunCode.EQ6_ERROR)

    def test_advance_to_xi_step_missing_separator_raises_parser_error(self):
        """
        Ensure advance_to_xi_step rejects Xi markers not followed by a path separator.
        """
        parser = self._parser("Stepping to Xi\nXi=0\n")
        with self.assertRaisesRegex(EleanorParserException, "expected path separator after Stepping to Xi"):
            parser.advance_to_xi_step()

    def test_outputparser6_parse_raises_for_missing_xi_separator(self):
        """
        Ensure OutputParser6.parse surfaces a strict error when Xi step separators are missing.
        """
        parser = OutputParser6(
            io.StringIO("Stepping to Xi\nXi=0\n --- The reaction path has terminated normally ---\n")
        )
        with self.assertRaisesRegex(EleanorParserException, "expected path separator after Stepping to Xi"):
            parser.parse()

    def test_read_saturation_states_updates_existing_adds_new_and_skips_starred(self):
        """
        Ensure saturation-state parsing updates existing phases, adds new phases, and skips starred rows.
        """
        parser = self._parser(
            " --- Saturation States of Pure Solids ---\n"
            " Phase Log Q/K Affinity, kcal\n"
            " hdr\n"
            "CALCITE -1.0 2.0\n"
            "ARAGONITE -2.0 4.0 SATD\n"
            "DOLOMITE * *\n"
            "\n"
        )
        phases: dict[str, dict[str, object]] = {"CALCITE": {"existing": 9.0}}

        parser.read_saturation_states("Saturation States of Pure Solids", phases)

        self.assertEqual(phases["CALCITE"]["existing"], 9.0)
        self.assertEqual(phases["CALCITE"]["log_qk"], -1.0)
        self.assertEqual(phases["CALCITE"]["affinity"], 2.0)
        self.assertEqual(phases["ARAGONITE"]["log_qk"], -2.0)
        self.assertEqual(phases["ARAGONITE"]["affinity"], 4.0)
        self.assertNotIn("DOLOMITE", phases)

    def test_read_saturation_states_rejects_too_many_columns(self):
        """
        Ensure saturation-state parsing rejects rows with extra columns.
        """
        parser = self._parser(
            " --- Saturation States of Pure Solids ---\n"
            " Phase Log Q/K Affinity, kcal\n"
            " hdr\n"
            "CALCITE -1.0 2.0 SATD EXTRA\n"
            "\n"
        )
        with self.assertRaises(EleanorParserException):
            parser.read_saturation_states("Saturation States of Pure Solids", {})

    def test_read_saturation_states_rejects_invalid_state_token(self):
        """
        Ensure saturation-state parsing rejects unrecognized state tokens.
        """
        parser = self._parser(
            " --- Saturation States of Pure Solids ---\n"
            " Phase Log Q/K Affinity, kcal\n"
            " hdr\n"
            "CALCITE -1.0 2.0 INVALID\n"
            "\n"
        )
        with self.assertRaises(EleanorParserException):
            parser.read_saturation_states("Saturation States of Pure Solids", {})

    def test_read_liquid_saturation_states_parses_and_skips_starred_rows(self):
        """
        Ensure liquid saturation-state parsing stores normal rows and skips starred rows.
        """
        parser = self._parser(
            " --- Saturation States of Pure Liquids ---\n Phase Log Q/K Affinity, kcal\n hdr\nH2O -0.1 1.2\nOIL * *\n\n"
        )

        parser.read_liquid_saturation_states()

        self.assertIn("liquids", parser.data)
        liquids = as_any_dict(as_any_dict(parser.data)["liquids"])
        self.assertEqual(liquids["H2O"]["log_qk"], -0.1)
        self.assertEqual(liquids["H2O"]["affinity"], 1.2)
        self.assertNotIn("OIL", liquids)

    def test_read_pure_solid_saturation_states_initializes_and_parses(self):
        """
        Ensure pure-solid saturation-state wrapper initializes containers and parses values.
        """
        parser = self._parser(
            " --- Saturation States of Pure Solids ---\n Phase Log Q/K Affinity, kcal\n hdr\nCALCITE -1.5 3.0\n\n"
        )

        parser.read_pure_solid_saturation_states()

        self.assertIn("solids", parser.data)
        solids = as_any_dict(as_any_dict(parser.data)["solids"])
        self.assertIn("pure_solids", solids)
        self.assertEqual(solids["pure_solids"]["CALCITE"]["log_qk"], -1.5)
        self.assertEqual(solids["pure_solids"]["CALCITE"]["affinity"], 3.0)

    def test_read_solid_solution_saturation_states_backfills_end_member_fields(self):
        """
        Ensure solid-solution saturation wrapper backfills missing end-member fields from pure solids.
        """
        parser = self._parser(
            " --- Saturation States of Solid Solutions ---\n Phase Log Q/K Affinity, kcal\n hdr\nNone\n\n"
        )
        parser.data = {
            "solids": {
                "pure_solids": {
                    "EM1": {"log_qk": -9.0, "affinity": 5.0},
                },
                "solid_solutions": {
                    "SS1": {
                        "end_members": {
                            "EM1": {"log_qk": None, "affinity": None},
                        }
                    }
                },
            }
        }

        parser.read_solid_solution_saturation_states()

        em_props = as_any_dict(as_any_dict(as_any_dict(as_any_dict(parser.data)["solids"])["solid_solutions"])["SS1"])[
            "end_members"
        ]["EM1"]
        self.assertEqual(em_props["log_qk"], -9.0)
        self.assertEqual(em_props["affinity"], 5.0)

    def test_read_end_members_updates_duplicates_and_skips_starred_rows(self):
        """
        Ensure end-member parsing updates duplicate entries and skips starred rows.
        """
        parser = self._parser(
            " Component x Log x  Log lambda Log activity\n"
            "h1\n"
            "EM1 0.1 -1.0 -2.0 -3.0\n"
            "EM1 0.2 -0.7 -1.5 -2.2\n"
            "EM2 * * * *\n"
            "\n"
        )
        end_members = {"EM1": {"preexisting": 9.0}}

        parser.read_end_members(end_members)

        self.assertEqual(end_members["EM1"]["preexisting"], 9.0)
        self.assertEqual(end_members["EM1"]["x"], 0.2)
        self.assertEqual(end_members["EM1"]["log_x"], -0.7)
        self.assertEqual(end_members["EM1"]["log_lambda"], -1.5)
        self.assertEqual(end_members["EM1"]["log_activity"], -2.2)
        self.assertNotIn("EM2", end_members)

    def test_read_mineral_parses_valid_row_and_preserves_existing_fields(self):
        """
        Ensure mineral parsing updates the expected phase while preserving other fields.
        """
        parser = self._parser(" Mineral Log Q/K Aff, kcal State\nh1\nSS1 -1.2 3.4 SATD\n")
        phases: dict[str, dict[str, object]] = {"SS1": {"existing": 1.0}}

        parser.read_mineral("Solid Solution Product Phases", phases, expected_phase="SS1")

        self.assertEqual(phases["SS1"]["existing"], 1.0)
        self.assertEqual(phases["SS1"]["log_qk"], -1.2)
        self.assertEqual(phases["SS1"]["affinity"], 3.4)

    def test_read_mineral_skips_starred_values(self):
        """
        Ensure mineral parsing skips rows where thermodynamic values are starred.
        """
        parser = self._parser(" Mineral Log Q/K Aff, kcal State\nh1\nSS1 * *\n")
        phases: dict[str, dict[str, object]] = {"SS1": {"existing": 1.0}}

        parser.read_mineral("Solid Solution Product Phases", phases, expected_phase="SS1")

        self.assertEqual(phases["SS1"], {"existing": 1.0})

    def test_read_mineral_rejects_invalid_state_column(self):
        """
        Ensure mineral parsing rejects unrecognized state tokens.
        """
        parser = self._parser(" Mineral Log Q/K Aff, kcal State\nh1\nSS1 -1.2 3.4 INVALID\n")
        phases = {"SS1": {}}

        with self.assertRaises(EleanorParserException):
            parser.read_mineral("Solid Solution Product Phases", phases, expected_phase="SS1")

    def test_read_mineral_expected_phase_mismatch_raises_parser_error(self):
        """
        Ensure mineral parsing raises a parser error when expected_phase does not match the parsed mineral name.
        """
        parser = self._parser(" Mineral Log Q/K Aff, kcal State\nh1\nSS1 -1.2 3.4 SATD\n")
        phases = {"SS1": {}}

        with self.assertRaises(EleanorParserException):
            parser.read_mineral("Solid Solution Product Phases", phases, expected_phase="DIFFERENT_PHASE")

    def test_read_end_member_saturations_updates_known_and_skips_starred(self):
        """
        Ensure end-member saturation parsing updates known entries and skips starred rows.
        """
        parser = self._parser("EM1 -2.0 1.0\nEM2 * *\n\n")
        end_members = {"EM1": {"x": 0.5}, "EM2": {"x": 0.4}}

        parser.read_end_member_saturations("Solid Solution Product Phases", end_members)

        self.assertEqual(end_members["EM1"]["x"], 0.5)
        self.assertEqual(end_members["EM1"]["log_qk"], -2.0)
        self.assertEqual(end_members["EM1"]["affinity"], 1.0)
        self.assertEqual(end_members["EM2"], {"x": 0.4})

    def test_read_end_member_saturations_unknown_end_member_raises_parser_error(self):
        """
        Ensure end-member saturation parsing raises a parser error for unknown end members.
        """
        parser = self._parser("UNKNOWN -2.0 1.0\n\n")
        with self.assertRaises(EleanorParserException):
            parser.read_end_member_saturations("Solid Solution Product Phases", {"EM1": {"x": 0.5}})

    def test_read_product_phases_parses_block_and_hands_off_to_fugacities(self):
        """
        Ensure product-phase parsing captures one phase block and leaves cursor for Fugacities parsing.
        """
        parser = self._parser(
            " --- Solid Solution Product Phases ---\n"
            "h1\n"
            "h2\n"
            " --- SS1 ---\n"
            " Component x Log x  Log lambda Log activity\n"
            "h1\n"
            "EM1 0.5 -0.3 -0.1 -0.4\n"
            "\n"
            " Mineral Log Q/K Aff, kcal State\n"
            "h1\n"
            "SS1 -1.0 2.0 SATD\n"
            "EM1 -2.0 3.0\n"
            "\n"
            " --- Fugacities ---\n"
        )

        parser.read_product_phases("Solid Solution Product Phases")

        ss1 = parser.data["solids"]["solid_solutions"]["SS1"]
        self.assertEqual(ss1["log_qk"], -1.0)
        self.assertEqual(ss1["affinity"], 2.0)
        self.assertEqual(ss1["end_members"]["EM1"]["x"], 0.5)
        self.assertEqual(ss1["end_members"]["EM1"]["log_qk"], -2.0)
        self.assertEqual(ss1["end_members"]["EM1"]["affinity"], 3.0)
        self.assertNotIn("gases", parser.data)
        self.assertNotIn("Fugacities", parser.line())
        self.assertIn("Fugacities", parser.peek())

    def test_read_product_phases_then_read_fugacities_parses_gases(self):
        """
        Ensure read_fugacities can immediately follow read_product_phases and parse gas rows.
        """
        parser = self._parser(
            " --- Solid Solution Product Phases ---\n"
            "h1\n"
            "h2\n"
            " --- SS1 ---\n"
            " Component x Log x  Log lambda Log activity\n"
            "h1\n"
            "EM1 0.5 -0.3 -0.1 -0.4\n"
            "\n"
            " Mineral Log Q/K Aff, kcal State\n"
            "h1\n"
            "SS1 -1.0 2.0 SATD\n"
            "EM1 -2.0 3.0\n"
            "\n"
            " --- Fugacities ---\n"
            " Gas Log Fugacity Fugacity\n"
            "h1\n"
            "CO2(g) -1.0 0.1\n"
            "N2(g) * *\n"
            "\n"
        )

        parser.read_product_phases("Solid Solution Product Phases")
        self.assertNotIn("gases", parser.data)
        self.assertIn("Fugacities", parser.peek())

        parser.read_fugacities()

        self.assertIn("gases", parser.data)
        self.assertEqual(parser.data["gases"]["CO2(g)"]["log_fugacity"], -1.0)
        self.assertEqual(parser.data["gases"]["CO2(g)"]["fugacity"], 0.1)
        self.assertNotIn("N2(g)", parser.data["gases"])

    def test_read_product_phases_missing_header_raises_parser_error(self):
        """
        Ensure read_product_phases raises when the requested section header is absent.
        """
        parser = self._parser(" --- Some Other Section ---\nbody\n")
        with self.assertRaises(EleanorParserException):
            parser.read_product_phases("Solid Solution Product Phases")

    def test_read_product_phases_missing_header_does_not_mutate_data(self):
        """
        Ensure missing-header failures do not mutate parser.data.
        """
        parser = self._parser(" --- Some Other Section ---\nbody\n")
        parser.data = {"preexisting": {"x": 1}}
        with self.assertRaises(EleanorParserException):
            parser.read_product_phases("Solid Solution Product Phases")
        self.assertEqual(parser.data, {"preexisting": {"x": 1}})

    def test_outputparser6_read_elemental_composition_mgkg_table(self):
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

        na = parser.data["elements"]["Na"]
        self.assertEqual(na["mass_fraction"], 1e-3)
        self.assertEqual(na["molality"], 1e-2)
        self.assertEqual(na["log_molality"], -2.0)
        self.assertNotIn("mass_per_volume", na)
        self.assertNotIn("molarity", na)

    def test_outputparser6_read_elemental_composition_mgl_table(self):
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

        na = parser.data["elements"]["Na"]
        self.assertEqual(na["mass_per_volume"], 1e-3)
        self.assertEqual(na["mass_fraction"], 2e-3)
        self.assertEqual(na["molarity"], 3e-2)
        self.assertAlmostEqual(na["log_molarity"], np.log10(3e-2))
        self.assertEqual(na["molality"], 4e-2)
        self.assertAlmostEqual(na["log_molality"], np.log10(4e-2))

    def test_outputparser6_read_elemental_composition_invalid_header_raises(self):
        """
        Ensure OutputParser6 elemental-composition parsing rejects unknown table headers.
        """
        parser = OutputParser6(
            io.StringIO(" --- Elemental Composition of the Aqueous Solution ---\nh1\n Element unexpected columns\nh2\n")
        )

        with self.assertRaises(EleanorParserException):
            parser.read_elemental_composition()

    def test_outputparser6_read_numerical_composition_mgl_table(self):
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

        hco3 = parser.data["numerical_composition"]["HCO3-"]
        self.assertEqual(hco3["mass_per_volume"], 5e-4)
        self.assertEqual(hco3["mass_fraction"], 6e-4)
        self.assertEqual(hco3["molarity"], 1e-2)
        self.assertAlmostEqual(hco3["log_molarity"], -2.0)
        self.assertEqual(hco3["molality"], 2e-2)
        self.assertAlmostEqual(hco3["log_molality"], np.log10(2e-2))

    def test_outputparser6_read_sensible_composition_invalid_header_raises(self):
        """
        Ensure OutputParser6 sensible-composition parsing rejects unknown table headers.
        """
        parser = OutputParser6(
            io.StringIO(" --- Sensible Composition of the Aqueous Solution ---\nh1\n Species unexpected columns\nh2\n")
        )

        with self.assertRaises(EleanorParserException):
            parser.read_sensible_composition()

    def test_outputparser6_read_bulk_properties_parses_scalars_and_log_relations(self):
        """
        Ensure OutputParser6 bulk-properties parser reads fields and computes log values from stored scalars.
        """
        parser = OutputParser6(
            io.StringIO(
                "Oxygen fugacity=1.0 bars\n"
                "Log oxygen fugacity=0.0\n"
                "Activity of water=0.9\n"
                "Log activity of water=-0.045757\n"
                "Mole fraction of water=0.95\n"
                "Log mole fraction of water=-0.022276\n"
                "Activity coefficient of water=1.1\n"
                "Log activity coefficient of water=0.041393\n"
                "Osmotic coefficient=0.8\n"
                "Stoichiometric osmotic coefficient=0.81\n"
                "Sum of molalities=0.1\n"
                "Sum of stoichiometric molalities=0.2\n"
                "Ionic strength (I)=0.3 molal\n"
                "Stoichiometric ionic strength=0.4 molal\n"
                "Ionic asymmetry (J)=0.5 molal\n"
                "Stoichiometric ionic asymmetry=0.6 molal\n"
                "Solvent mass=100 grams\n"
                "Solutes (TDS) mass=10 grams\n"
                "Aqueous solution mass=110 grams\n"
                "Solvent fraction=0.9 kg.h2o/kg.sol\n"
                "Solute fraction=0.1 kg.tds/kg.sol\n"
                "Total dissolved solutes (TDS)=500 mg/kg.sol\n"
                " --- More Precise Aqueous Phase Masses ---\n"
                "h1\n"
                "Solvent mass=120 grams\n"
                "Solutes (TDS) mass=12 grams\n"
                "Aqueous solution mass=132 grams\n"
            )
        )

        with mock.patch.object(parser, "read_alkalinity") as read_alkalinity:
            parser.read_bulk_properties()

        read_alkalinity.assert_called_once()
        self.assertEqual(parser.data["fO2"], 1.0)
        self.assertEqual(parser.data["log_fO2"], 0.0)
        self.assertEqual(parser.data["activity_water"], 0.9)
        self.assertEqual(parser.data["mole_fraction_water"], 0.95)
        self.assertEqual(parser.data["activity_coefficient_water"], 1.1)
        self.assertEqual(parser.data["osmotic_coefficient"], 0.8)
        self.assertEqual(parser.data["stoichiometric_osmotic_coefficient"], 0.81)
        self.assertEqual(parser.data["sum_molalities"], 0.1)
        self.assertEqual(parser.data["sum_stoichiometric_molalities"], 0.2)
        self.assertEqual(parser.data["ionic_strength"], 0.3)
        self.assertEqual(parser.data["stoichiometric_ionic_strength"], 0.4)
        self.assertEqual(parser.data["ionic_asymmetry"], 0.5)
        self.assertEqual(parser.data["stoichiometric_ionic_asymmetry"], 0.6)
        self.assertEqual(parser.data["solvent_fraction"], 0.9)
        self.assertEqual(parser.data["solute_fraction"], 0.1)
        self.assertEqual(parser.data["tds"], 500.0)
        self.assertAlmostEqual(parser.data["log_ionic_strength"], np.log10(parser.data["ionic_strength"]))
        self.assertAlmostEqual(
            parser.data["log_stoichiometric_ionic_strength"],
            np.log10(parser.data["stoichiometric_ionic_strength"]),
        )
        self.assertAlmostEqual(parser.data["log_ionic_asymmetry"], np.log10(parser.data["ionic_asymmetry"]))
        self.assertAlmostEqual(
            parser.data["log_stoichiometric_ionic_asymmetry"],
            np.log10(parser.data["stoichiometric_ionic_asymmetry"]),
        )
        self.assertAlmostEqual(parser.data["log_sum_molalities"], np.log10(parser.data["sum_molalities"]))
        self.assertAlmostEqual(
            parser.data["log_sum_stoichiometric_molalities"],
            np.log10(parser.data["sum_stoichiometric_molalities"]),
        )
        self.assertAlmostEqual(parser.data["log_solvent_mass"], np.log10(parser.data["solvent_mass"]))
        self.assertAlmostEqual(parser.data["log_solute_mass"], np.log10(parser.data["solute_mass"]))
        self.assertAlmostEqual(parser.data["log_solution_mass"], np.log10(parser.data["solution_mass"]))

    def test_outputparser6_read_charge_balance_parses_and_scales_per_unit_values(self):
        """
        Ensure OutputParser6 charge-balance parser reads totals and scales per-unit values by 1e-3.
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

        self.assertEqual(parser.data["charge_imbalance"], 1.0)
        self.assertEqual(parser.data["expected_charge_imbalance"], 2.0)
        self.assertEqual(parser.data["charge_discrepancy"], 3.0)
        self.assertEqual(parser.data["sigma"], 4.0)
        self.assertEqual(parser.data["charge_imbalance_per_unit_solution"], 0.005)
        self.assertEqual(parser.data["expected_charge_imbalance_per_unit_solution"], 0.006)
        self.assertEqual(parser.data["charge_discrepancy_per_unit_solution"], 0.007)
        self.assertEqual(parser.data["sigma_per_unit_solution"], 0.008)
        self.assertEqual(parser.data["relative_charge_discrepancy"], 9.0)

    def test_outputparser6_init_without_file_uses_default_path(self):
        """
        Ensure OutputParser6 defaults to opening problem.6o when no file argument is provided.
        """
        with mock.patch("builtins.open", mock.mock_open(read_data="")) as mocked_open:
            parser = OutputParser6()
        mocked_open.assert_called_once_with("problem.6o", "r")
        self.assertIsInstance(parser, OutputParser6)

    def test_outputparser6_file_not_found_wrapped(self):
        """
        Ensure OutputParser6 wraps missing-file errors in EleanorFileException with NO_6O_FILE code.
        """
        with mock.patch("builtins.open", side_effect=FileNotFoundError("missing")):
            with self.assertRaises(EleanorFileException) as cm:
                OutputParser6("missing.6o")
        self.assertEqual(cm.exception.code, RunCode.NO_6O_FILE)

    def test_outputparser6_parse_with_no_steps_checks_termination(self):
        """
        Ensure OutputParser6.parse checks termination even when no Xi step is found.
        """
        parser = OutputParser6(io.StringIO(""))

        with (
            mock.patch.object(parser, "advance_to_xi_step", return_value=False),
            mock.patch.object(parser, "parse_step") as parse_step,
            mock.patch.object(parser, "check_path_termination") as check_path_termination,
        ):
            result = parser.parse()

        self.assertIs(result, parser)
        parse_step.assert_not_called()
        check_path_termination.assert_called_once()

    def test_outputparser6_parse_step_appends_snapshot_and_resets_data(self):
        """
        Ensure parse_step appends parsed step data to path and resets transient data.
        """
        parser = OutputParser6(io.StringIO(""))

        def fake_read_basic_property(name, key=None, **kwargs):
            if key is not None:
                parser.data[key] = 1.0

        with (
            mock.patch.object(parser, "consume_blank_lines"),
            mock.patch.object(parser, "advance"),
            mock.patch.object(parser, "read_basic_property", side_effect=fake_read_basic_property),
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
        self.assertEqual(step["xi"], 1.0)
        self.assertEqual(step["temperature"], 1.0)
        self.assertEqual(step["pressure"], 1.0)
        self.assertEqual(step["log_xi"], 0.0)
        self.assertEqual(parser.data, {})

    def test_outputparser6_parse_step_wraps_internal_errors(self):
        """
        Ensure parse_step wraps internal failures in EleanorParserException.
        """
        parser = OutputParser6(io.StringIO(""))

        def fake_read_basic_property(name, key=None, **kwargs):
            if key is not None:
                parser.data[key] = 1.0

        with (
            mock.patch.object(parser, "consume_blank_lines"),
            mock.patch.object(parser, "advance"),
            mock.patch.object(parser, "read_basic_property", side_effect=fake_read_basic_property),
            mock.patch.object(parser, "read_reactants", side_effect=RuntimeError("boom")),
        ):
            with self.assertRaisesRegex(EleanorParserException, "failed to parse EQ6 output"):
                parser.parse_step()

    def test_outputparser6_parse_iterates_steps_and_checks_termination(self):
        """
        Ensure OutputParser6.parse loops over Xi steps and checks final path termination.
        """
        parser = OutputParser6(io.StringIO(""))

        with (
            mock.patch.object(parser, "advance_to_xi_step", side_effect=[True, True, False]),
            mock.patch.object(parser, "parse_step") as parse_step,
            mock.patch.object(parser, "check_path_termination") as check_path_termination,
        ):
            result = parser.parse()

        self.assertIs(result, parser)
        self.assertEqual(parse_step.call_count, 2)
        check_path_termination.assert_called_once()

    def test_outputparser3_parse_wraps_internal_errors(self):
        """
        Ensure OutputParser3.parse wraps internal parsing failures in EleanorParserException.
        """
        parser = OutputParser3(io.StringIO("Normal exit\n"))

        with (
            mock.patch.object(parser, "consume_to_pattern"),
            mock.patch.object(parser, "advance"),
            mock.patch.object(parser, "read_basic_property"),
            mock.patch.object(parser, "read_elemental_composition", side_effect=RuntimeError("boom")),
        ):
            with self.assertRaisesRegex(EleanorParserException, "failed to parse EQ3 output"):
                parser.parse()

    def test_outputparser3_parse_raises_on_early_termination_marker_absence(self):
        """
        Ensure OutputParser3.parse raises EQ3_EARLY_TERMINATION when final normal-exit marker is absent.
        """
        parser = OutputParser3(io.StringIO("not normal exit\n"))

        with (
            mock.patch.object(parser, "consume_to_pattern"),
            mock.patch.object(parser, "advance"),
            mock.patch.object(parser, "read_basic_property"),
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
            with self.assertRaises(EleanorException) as cm:
                parser.parse()

        self.assertEqual(cm.exception.code, RunCode.EQ3_EARLY_TERMINATION)

    def test_read_ph_like_parses_scales_skips_starred_and_reads_optional_fields(self):
        """
        Ensure read_pH_like stores valid scale rows, skips starred rows, and reads optional pcH/pHCl entries.
        """
        parser = self._parser(
            " --- The pH, Eh, pe-, and Ah on various pH scales ---\n"
            "h1\n"
            "h2\n"
            "h3\n"
            "NBS 7.10 0.20 3.10 4.10\n"
            "Alt Scale * * * *\n"
            "\n"
            "pcH=6.50\n"
            "pHCl=6.40\n"
        )

        parser.read_pH_like()

        self.assertIn("pH", parser.data)
        self.assertEqual(parser.data["pH"]["NBS"]["pH"], 7.10)
        self.assertEqual(parser.data["pH"]["NBS"]["Eh"], 0.20)
        self.assertEqual(parser.data["pH"]["NBS"]["pe-"], 3.10)
        self.assertEqual(parser.data["pH"]["NBS"]["Ah"], 4.10)
        self.assertNotIn("Alt Scale", parser.data["pH"])
        self.assertEqual(parser.data["pcH"], 6.50)
        self.assertEqual(parser.data["pHCl"], 6.40)

    def test_read_ph_like_tolerates_missing_optional_pch_and_phcl(self):
        """
        Ensure read_pH_like succeeds when optional pcH/pHCl lines are absent.
        """
        parser = self._parser(
            " --- The pH, Eh, pe-, and Ah on various pH scales ---\n"
            "h1\n"
            "h2\n"
            "h3\n"
            "NBS 7.10 0.20 3.10 4.10\n"
            "\n"
            "next section marker\n"
        )

        parser.read_pH_like()

        self.assertIn("pH", parser.data)
        self.assertNotIn("pcH", parser.data)
        self.assertNotIn("pHCl", parser.data)

    def test_read_alkalinity_returns_when_not_defined(self):
        """
        Ensure read_alkalinity exits without creating data when alkalinity is explicitly not defined.
        """
        parser = self._parser("prefix\nAlkalinity is not defined in this run\n")

        parser.read_alkalinity()

        self.assertNotIn("alkalinity", parser.data)

    def test_read_alkalinity_parses_until_extended_and_skips_l_units(self):
        """
        Ensure read_alkalinity parses repeated alkalinity blocks through Extended and skips per-liter species rows.
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

        self.assertIn("alkalinity", parser.data)
        carbonate = parser.data["alkalinity"]["Carbonate"]
        extended = parser.data["alkalinity"]["Extended"]
        self.assertEqual(carbonate["Total"], 1.20)
        self.assertEqual(carbonate["CO3--"], 0.30)
        self.assertNotIn("HCO3-", carbonate)
        self.assertEqual(extended["Total"], 2.20)
        self.assertEqual(extended["OH-"], 0.90)

    def test_read_aqueous_solute_parses_rows_and_skips_starred(self):
        """
        Ensure read_aqueous_solute stores normal rows and skips starred rows.
        """
        parser = self._parser(
            " --- Distribution of Aqueous Solute Species ---\n"
            " Species Molality Log Molality Log Gamma Log Activity\n"
            "h1\n"
            "Na+ 1e-2 -2.0 -0.1 -2.1\n"
            "Cl- * * * *\n"
            "\n"
        )

        parser.read_aqueous_solute()

        self.assertIn("aqueous", parser.data)
        self.assertEqual(parser.data["aqueous"]["Na+"]["molality"], 1e-2)
        self.assertEqual(parser.data["aqueous"]["Na+"]["log_molality"], -2.0)
        self.assertEqual(parser.data["aqueous"]["Na+"]["log_gamma"], -0.1)
        self.assertEqual(parser.data["aqueous"]["Na+"]["log_activity"], -2.1)
        self.assertNotIn("Cl-", parser.data["aqueous"])

    def test_read_redox_reactions_parses_rows_and_skips_starred(self):
        """
        Ensure read_redox_reactions stores normal rows and skips starred rows.
        """
        parser = self._parser(
            " --- Aqueous Redox Reactions ---\n"
            " Couple Eh, volts pe- log fO2 Ah, kcal\n"
            "h1\n"
            "O2/H2O 0.80 13.5 -70.0 -10.0\n"
            "Fe+++/Fe++ * * * *\n"
            "\n"
        )

        parser.read_redox_reactions()

        self.assertIn("redox", parser.data)
        self.assertEqual(parser.data["redox"]["O2/H2O"]["Eh"], 0.80)
        self.assertEqual(parser.data["redox"]["O2/H2O"]["pe-"], 13.5)
        self.assertEqual(parser.data["redox"]["O2/H2O"]["log_fO2"], -70.0)
        self.assertEqual(parser.data["redox"]["O2/H2O"]["Ah"], -10.0)
        self.assertNotIn("Fe+++/Fe++", parser.data["redox"])

    def test_read_solid_blocks_parses_solution_end_member_and_pure_phase(self):
        """
        Ensure read_solid_blocks parses solid solutions, their end members, and pure solids.
        """
        parser = self._parser("SS1 -1.0 1.0 10.0 100.0\n   EM1 -2.0 0.5 5.0 50.0\nCALCITE -3.0 2.0 20.0 200.0\n\n")
        pure_solids = {}
        solid_solutions = {}

        parser.read_solid_blocks(pure_solids, solid_solutions)

        self.assertIn("SS1", solid_solutions)
        self.assertEqual(solid_solutions["SS1"]["moles"], 1.0)
        self.assertEqual(solid_solutions["SS1"]["log_moles"], -1.0)
        self.assertEqual(solid_solutions["SS1"]["mass"], 10.0)
        self.assertEqual(solid_solutions["SS1"]["volume"], 100.0)
        self.assertAlmostEqual(solid_solutions["SS1"]["log_mass"], np.log10(10.0))
        self.assertAlmostEqual(solid_solutions["SS1"]["log_volume"], np.log10(100.0))
        self.assertIn("EM1", solid_solutions["SS1"]["end_members"])
        self.assertEqual(solid_solutions["SS1"]["end_members"]["EM1"]["moles"], 0.5)
        self.assertEqual(solid_solutions["SS1"]["end_members"]["EM1"]["log_moles"], -2.0)
        self.assertEqual(solid_solutions["SS1"]["end_members"]["EM1"]["mass"], 5.0)
        self.assertEqual(solid_solutions["SS1"]["end_members"]["EM1"]["volume"], 50.0)
        self.assertIn("CALCITE", pure_solids)
        self.assertEqual(pure_solids["CALCITE"]["moles"], 2.0)
        self.assertEqual(pure_solids["CALCITE"]["log_moles"], -3.0)

    def test_read_solid_blocks_raises_on_orphan_end_member(self):
        """
        Ensure read_solid_blocks raises when an end-member appears without a parent solid solution.
        """
        parser = self._parser("   EM1 -2.0 0.5 5.0 50.0\n\n")

        with self.assertRaisesRegex(EleanorParserException, "unexpected end member"):
            parser.read_solid_blocks({}, {})

    def test_read_solid_blocks_skips_starred_and_sets_fix_f_defaults(self):
        """
        Ensure read_solid_blocks skips starred rows and assigns default saturation values for fix_f phases.
        """
        parser = self._parser("STAR * * * *\nfix_fCO2 -1.0 1.0 10.0 100.0\n\n")
        pure_solids = {}
        solid_solutions = {}

        parser.read_solid_blocks(pure_solids, solid_solutions)

        self.assertNotIn("STAR", pure_solids)
        self.assertNotIn("STAR", solid_solutions)
        self.assertIn("fix_fCO2", pure_solids)
        self.assertEqual(pure_solids["fix_fCO2"]["log_qk"], 0.0)
        self.assertEqual(pure_solids["fix_fCO2"]["affinity"], 0.0)

    def test_read_solid_phases_none_path_populates_mass_balance_rows(self):
        """
        Ensure read_solid_phases handles the 'None' path and still parses created/destroyed/net totals.
        """
        parser = self._parser(
            " --- Summary of Solid Phases (ES) ---\n"
            " Phase/End-member Log moles Moles Grams Volume, cm3\n"
            "h1\n"
            "None\n"
            "skip1\n"
            "skip2\n"
            "not grand summary\n"
            "mass summary\n"
            "created 1.0 2.0\n"
            "destroyed 3.0 4.0\n"
            "net 5.0 6.0\n"
            "\n"
        )

        parser.read_solid_phases()

        self.assertIn("solids", parser.data)
        solids = parser.data["solids"]
        self.assertEqual(solids["created"]["mass"], 1.0)
        self.assertEqual(solids["created"]["volume"], 2.0)
        self.assertEqual(solids["destroyed"]["mass"], 3.0)
        self.assertEqual(solids["destroyed"]["volume"], 4.0)
        self.assertEqual(solids["net"]["mass"], 5.0)
        self.assertEqual(solids["net"]["volume"], 6.0)
        self.assertEqual(solids["pure_solids"], {})
        self.assertEqual(solids["solid_solutions"], {})

    def test_read_solid_phases_grand_summary_parses_solids(self):
        """
        Ensure read_solid_phases parses solids from the grand-summary branch.
        """
        parser = self._parser(
            " --- Summary of Solid Phases (ES) ---\n"
            " Phase/End-member Log moles Moles Grams Volume, cm3\n"
            "h1\n"
            "None\n"
            "skip1\n"
            "skip2\n"
            " --- Grand Summary of Solid Phases (ES + PRS + Reactants) ---\n"
            " Phase/End-member Log moles Moles Grams Volume, cm3\n"
            "h1\n"
            "CALCITE -3.0 2.0 20.0 200.0\n"
            "\n"
            "\n"
            "tail1\n"
            "tail2\n"
            "created 1.0 2.0\n"
            "destroyed 3.0 4.0\n"
            "net 5.0 6.0\n"
            "\n"
        )

        parser.read_solid_phases()

        solids = parser.data["solids"]
        self.assertIn("CALCITE", solids["pure_solids"])
        self.assertEqual(solids["pure_solids"]["CALCITE"]["moles"], 2.0)
        self.assertEqual(solids["pure_solids"]["CALCITE"]["log_moles"], -3.0)
        self.assertEqual(solids["created"]["mass"], 1.0)
        self.assertEqual(solids["net"]["volume"], 6.0)

    def test_read_solid_blocks_wraps_row_unpack_error_as_parser_exception(self):
        """
        Ensure malformed/non-data rows in read_solid_blocks are surfaced as EleanorParserException.
        """
        parser = self._parser("None\n\n")

        with self.assertRaises(EleanorParserException):
            parser.read_solid_blocks({}, {})

    def test_outputparser3_read_elemental_composition_scales_and_logs(self):
        """
        Ensure OutputParser3 elemental composition scales concentrations and computes log fields.
        """
        parser = OutputParser3(
            io.StringIO(
                " --- Elemental Composition of the Aqueous Solution ---\n"
                " Element mg/L mg/kg.sol Molarity Molality\n"
                "h1\n"
                "Na 1000 2000 1e-2 2e-2\n"
                "\n"
            )
        )

        parser.read_elemental_composition()

        na = parser.data["elements"]["Na"]
        self.assertEqual(na["concentration"], 1.0)
        self.assertEqual(na["mass_fraction"], 2e-3)
        self.assertEqual(na["molarity"], 1e-2)
        self.assertEqual(na["molality"], 2e-2)
        self.assertAlmostEqual(na["log_molarity"], np.log10(1e-2))
        self.assertAlmostEqual(na["log_molality"], np.log10(2e-2))

    def test_outputparser3_read_numerical_composition_scales_and_logs(self):
        """
        Ensure OutputParser3 numerical composition scales concentrations and computes log fields.
        """
        parser = OutputParser3(
            io.StringIO(
                " --- Numerical Composition of the Aqueous Solution ---\n"
                " Species mg/L mg/kg.sol Molarity Molality\n"
                "h1\n"
                "HCO3- 500 600 1e-2 2e-2\n"
                "\n"
            )
        )

        parser.read_numerical_composition()

        hco3 = parser.data["numerical_composition"]["HCO3-"]
        self.assertEqual(hco3["concentration"], 0.5)
        self.assertEqual(hco3["mass_fraction"], 6e-4)
        self.assertEqual(hco3["molarity"], 1e-2)
        self.assertEqual(hco3["molality"], 2e-2)
        self.assertAlmostEqual(hco3["log_molarity"], np.log10(1e-2))
        self.assertAlmostEqual(hco3["log_molality"], np.log10(2e-2))

    def test_outputparser3_read_sensible_composition_scales_and_logs(self):
        """
        Ensure OutputParser3 sensible composition scales concentrations and computes log fields.
        """
        parser = OutputParser3(
            io.StringIO(
                " --- Sensible Composition of the Aqueous Solution ---\n"
                " Species mg/L mg/kg.sol Molarity Molality\n"
                "h1\n"
                "CO2(aq) 200 300 1e-3 2e-3\n"
                "\n"
            )
        )

        parser.read_sensible_composition()

        co2 = parser.data["sensible_composition"]["CO2(aq)"]
        self.assertEqual(co2["concentration"], 0.2)
        self.assertEqual(co2["mass_fraction"], 3e-4)
        self.assertEqual(co2["molarity"], 1e-3)
        self.assertEqual(co2["molality"], 2e-3)
        self.assertAlmostEqual(co2["log_molarity"], np.log10(1e-3))
        self.assertAlmostEqual(co2["log_molality"], np.log10(2e-3))

    def test_outputparser3_read_charge_balance_parses_concentration_table(self):
        """
        Ensure OutputParser3 charge-balance parser reads the concentration/mass_fraction/molality table path.
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

        self.assertEqual(parser.data["cations"], 1.0)
        self.assertEqual(parser.data["anions"], 0.9)
        self.assertEqual(parser.data["total_charge"], 0.1)
        self.assertEqual(parser.data["mean_charge"], 0.05)
        self.assertEqual(parser.data["charge_imbalance"], 0.01)
        self.assertEqual(parser.data["charge_imbalance_percent_total"], 7.5)
        self.assertEqual(parser.data["charge_imbalance_percent_mean"], 8.5)

        charge_balance = parser.data["charge_balance"]
        self.assertEqual(charge_balance["species"], "Cl-")
        self.assertEqual(charge_balance["PHASE1"]["concentration"], 1.0)
        self.assertEqual(charge_balance["PHASE1"]["mass_fraction"], 2e-3)
        self.assertEqual(charge_balance["PHASE1"]["molality"], 0.3)

    def test_outputparser3_read_charge_balance_falls_back_to_log_activity_table(self):
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

        charge_balance = parser.data["charge_balance"]
        self.assertEqual(charge_balance["species"], "H+")
        self.assertEqual(charge_balance["PHASE1"]["log_activity"], -1.2)
        self.assertNotIn("concentration", charge_balance["PHASE1"])

    def test_outputparser3_read_charge_balance_missing_balancing_header_raises(self):
        """
        Ensure OutputParser3 charge-balance parser raises on missing Electrical Balancing header.
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
                "not an electrical balancing header\n"
            )
        )

        with self.assertRaises(EleanorParserException):
            parser.read_charge_balance()

    def test_read_liquid_saturation_states_rejects_too_many_columns(self):
        """
        Ensure liquid saturation-state parser rejects rows with extra state columns.
        """
        parser = self._parser(
            " --- Saturation States of Pure Liquids ---\n"
            " Phase Log Q/K Affinity, kcal\n"
            " hdr\n"
            "H2O -1.0 2.0 SATD EXTRA\n"
            "\n"
        )

        with self.assertRaises(EleanorParserException):
            parser.read_liquid_saturation_states()

    def test_advance_to_xi_step_returns_false_when_no_xi_marker(self):
        """
        Ensure advance_to_xi_step returns False at EOF when no Xi marker is present.
        """
        parser = self._parser("header\nfooter\n")
        self.assertFalse(parser.advance_to_xi_step())

    def test_advance_to_xi_step_returns_true_and_advances_past_separator(self):
        """
        Ensure advance_to_xi_step returns True and positions cursor after the path separator.
        """
        parser = self._parser("preface\nStepping to Xi\n - - -\nXi=1\n")
        self.assertTrue(parser.advance_to_xi_step())
        self.assertEqual(parser.line().strip(), "Xi=1")

    def test_read_reactants_raises_for_unexpected_affinity_reactant(self):
        """
        Ensure read_reactants raises when affinity table references a reactant not in summary rows.
        """
        parser = self._parser(
            "--- Reactant Summary ---\n"
            " Reactant Moles Delta moles Mass, g Delta mass, g\n"
            "\n"
            "R1 1.0 0.1 2.0 0.2\n"
            "\n"
            "Mass remaining=2 grams\n"
            "Mass destroyed=0.2 grams\n"
            " Reactant Affinity Rel. Rate\n"
            "h1\n"
            "h2\n"
            "R2 1.0 1.0\n"
            "\n"
            "Affinity of the overall irreversible reaction=0.0 kcal\n"
            "\n"
        )

        with self.assertRaises(EleanorParserException):
            parser.read_reactants()

    def test_read_reactants_skips_starred_affinity_values(self):
        """
        Ensure read_reactants keeps reactant entries and skips starred affinity/relative-rate rows.
        """
        parser = self._parser(
            "--- Reactant Summary ---\n"
            " Reactant Moles Delta moles Mass, g Delta mass, g\n"
            "\n"
            "R1 1.0 0.1 2.0 0.2\n"
            "\n"
            "Mass remaining=2 grams\n"
            "Mass destroyed=0.2 grams\n"
            " Reactant Affinity Rel. Rate\n"
            "h1\n"
            "h2\n"
            "R1 * *\n"
            "\n"
            "Affinity of the overall irreversible reaction=0.0 kcal\n"
            "\n"
        )

        parser.read_reactants()

        reactant = parser.data["reactants"]["reactants"]["R1"]
        self.assertNotIn("affinity", reactant)
        self.assertNotIn("relative_rate", reactant)

    def test_read_aqueous_saturation_states_consumes_rows(self):
        """
        Ensure read_aqueous_saturation_states consumes its table rows through the next blank line.
        """
        parser = self._parser(
            " --- Saturation States of Aqueous Reactions Not Fixed at Equilibrium ---\n"
            " Reaction Log Q/K Affinity, kcal\n"
            "h1\n"
            "RXN1 -1.0 2.0\n"
            "RXN2 -2.0 4.0\n"
            "\n"
            "next\n"
        )

        parser.read_aqueous_saturation_states()

        self.assertEqual(parser.line().strip(), "")

    def test_read_product_phases_initializes_missing_end_members_on_existing_phase(self):
        """
        Ensure read_product_phases adds an end_members map when phase exists but lacks that key.
        """
        parser = self._parser(
            " --- Solid Solution Product Phases ---\n"
            "h1\n"
            "h2\n"
            " --- SS1 ---\n"
            " Component x Log x  Log lambda Log activity\n"
            "h1\n"
            "EM1 0.5 -0.3 -0.1 -0.4\n"
            "\n"
            " Mineral Log Q/K Aff, kcal State\n"
            "h1\n"
            "SS1 -1.0 2.0 SATD\n"
            "EM1 -2.0 3.0\n"
            "\n"
            " --- Fugacities ---\n"
        )
        parser.data = {"solids": {"solid_solutions": {"SS1": {}}}}

        parser.read_product_phases("Solid Solution Product Phases")

        ss1 = parser.data["solids"]["solid_solutions"]["SS1"]
        self.assertIn("end_members", ss1)
        self.assertEqual(ss1["end_members"]["EM1"]["x"], 0.5)
        self.assertEqual(ss1["log_qk"], -1.0)
        self.assertEqual(ss1["affinity"], 2.0)

    def test_outputparser6_read_numerical_composition_mgkg_table(self):
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

        na = parser.data["numerical_composition"]["Na+"]
        self.assertEqual(na["mass_fraction"], 1e-3)
        self.assertEqual(na["molality"], 1e-2)
        self.assertAlmostEqual(na["log_molality"], np.log10(1e-2))
        self.assertNotIn("mass_per_volume", na)
        self.assertNotIn("molarity", na)

    def test_outputparser6_read_numerical_composition_invalid_header_raises(self):
        """
        Ensure OutputParser6 numerical-composition parsing rejects unknown table headers.
        """
        parser = OutputParser6(
            io.StringIO(" --- Numerical Composition of the Aqueous Solution ---\nh1\n Species unknown columns\nh2\n")
        )

        with self.assertRaises(EleanorParserException):
            parser.read_numerical_composition()

    def test_outputparser6_read_sensible_composition_mgkg_table(self):
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

        co2 = parser.data["sensible_composition"]["CO2(aq)"]
        self.assertEqual(co2["mass_fraction"], 3e-4)
        self.assertEqual(co2["molality"], 2e-3)
        self.assertAlmostEqual(co2["log_molality"], np.log10(2e-3))
        self.assertNotIn("mass_per_volume", co2)
        self.assertNotIn("molarity", co2)

    def test_outputparser6_read_sensible_composition_mgl_table(self):
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

        co2 = parser.data["sensible_composition"]["CO2(aq)"]
        self.assertAlmostEqual(co2["mass_per_volume"], 2e-4)
        self.assertEqual(co2["mass_fraction"], 3e-4)
        self.assertEqual(co2["molarity"], 1e-3)
        self.assertEqual(co2["molality"], 2e-3)
        self.assertAlmostEqual(co2["log_molarity"], np.log10(1e-3))
        self.assertAlmostEqual(co2["log_molality"], np.log10(2e-3))

    def test_outputparser_pretty_print_prints_nested_dict_key_at_nonzero_indent(self):
        """
        Ensure pretty_print prints nested dictionary keys with indented-key formatting branch.
        """
        parser = self._parser("")

        with mock.patch("builtins.print") as mocked_print:
            parser.pretty_print({"root": {"child": {"leaf": 1.0}}})

        mocked_print.assert_any_call("root")
        mocked_print.assert_any_call("   ", "child")
        mocked_print.assert_any_call("       ", "leaf", 1.0)

    def test_consume_while_pattern_advances_across_matching_lines(self):
        """
        Ensure consume_while_pattern advances while pattern matches current lines.
        """
        parser = self._parser("A\nA\nB\n")
        parser.consume_while_pattern(r"^A$")
        self.assertEqual(parser.line().strip(), "B")

    def test_outputparser_abstract_method_bodies_return_none_on_direct_call(self):
        """
        Ensure abstract method placeholder bodies can be directly invoked and return None.
        """
        parser = self._parser("")
        self.assertIsNone(OutputParser.read_elemental_composition(parser))
        self.assertIsNone(OutputParser.read_numerical_composition(parser))
        self.assertIsNone(OutputParser.read_sensible_composition(parser))
        self.assertIsNone(OutputParser.read_bulk_properties(parser))
        self.assertIsNone(OutputParser.read_charge_balance(parser))
        self.assertIsNone(OutputParser.parse(parser))

    def test_read_alkalinity_unexpected_state_branch_raises_parser_exception(self):
        """
        Ensure read_alkalinity surfaces parser-state errors when expected alkalinity header matching fails.
        """
        parser = self._parser("Alkalinity report\nnot a header\n")
        with mock.patch.object(parser, "consume_to_pattern"):
            with self.assertRaises(EleanorParserException):
                parser.read_alkalinity()

    def test_read_solid_blocks_starred_row_with_blank_next_line_advances_two(self):
        """
        Ensure read_solid_blocks uses two-line advance for starred rows followed by a blank line.
        """
        parser = self._parser("PHASE * * * *\n\n\n")
        parser.read_solid_blocks({}, {})
        self.assertEqual(parser.line_num, 2)

    def test_read_mineral_rejects_too_many_state_columns(self):
        """
        Ensure read_mineral rejects rows with more than one state column.
        """
        parser = self._parser(" Mineral Log Q/K Aff, kcal State\nh1\nSS1 -1.2 3.4 SATD EXTRA\n")
        phases = {"SS1": {}}
        with self.assertRaises(EleanorParserException):
            parser.read_mineral("Solid Solution Product Phases", phases, expected_phase="SS1")

    def test_read_end_member_saturations_rejects_too_many_columns(self):
        """
        Ensure read_end_member_saturations rejects rows with extra state columns.
        """
        parser = self._parser("EM1 -2.0 1.0 SATD EXTRA\n\n")
        with self.assertRaises(EleanorParserException):
            parser.read_end_member_saturations("Solid Solution Product Phases", {"EM1": {}})

    def test_read_end_member_saturations_rejects_invalid_state_token(self):
        """
        Ensure read_end_member_saturations rejects unknown state tokens.
        """
        parser = self._parser("EM1 -2.0 1.0 INVALID\n\n")
        with self.assertRaises(EleanorParserException):
            parser.read_end_member_saturations("Solid Solution Product Phases", {"EM1": {}})

    def test_check_path_termination_match_none_branch_raises_eq6_error(self):
        """
        Ensure check_path_termination raises EQ6_ERROR when current line does not match termination regex.
        """
        parser = OutputParser6(io.StringIO("not a termination status\n"))
        with mock.patch.object(parser, "unconsume_to_pattern"):
            with self.assertRaises(EleanorException) as cm:
                parser.check_path_termination()
        self.assertEqual(cm.exception.code, RunCode.EQ6_ERROR)

    def test_read_solid_phases_non_none_es_path_parses_blocks_then_advances(self):
        """
        Ensure read_solid_phases executes the non-None ES branch and advances past the trailing None sentinel.
        """
        parser = self._parser(
            " --- Summary of Solid Phases (ES) ---\n"
            " Phase/End-member Log moles Moles Grams Volume, cm3\n"
            "h1\n"
            "CALCITE -3.0 2.0 20.0 200.0\n"
            "\n"
            "\n"
            "None\n"
            "after-none\n"
            "created 1.0 2.0\n"
            "destroyed 3.0 4.0\n"
            "net 5.0 6.0\n"
            "\n"
        )

        parser.read_solid_phases()

        solids = parser.data["solids"]
        self.assertIn("CALCITE", solids["pure_solids"])
        self.assertEqual(solids["created"]["mass"], 1.0)
        self.assertEqual(solids["net"]["volume"], 6.0)

    def test_read_solid_solution_saturation_states_initializes_missing_containers_then_requires_pure_solids(self):
        """
        Ensure read_solid_solution_saturation_states initializes missing containers, then currently raises if pure_solids is absent.
        """
        parser = self._parser(
            " --- Saturation States of Solid Solutions ---\n Phase Log Q/K Affinity, kcal\n hdr\nNone\n\n"
        )
        parser.data = {}
        with self.assertRaises(KeyError):
            parser.read_solid_solution_saturation_states()

        self.assertIn("solids", parser.data)
        self.assertIn("solid_solutions", parser.data["solids"])
        self.assertEqual(parser.data["solids"]["solid_solutions"], {})

    def test_check_path_termination_unexpected_status_branch_raises_early_termination(self):
        """
        Ensure check_path_termination hits fallback branch for unexpected status token and raises early-termination code.
        """
        parser = OutputParser6(io.StringIO("status line\n"))

        class _FakeMatch:
            def __getitem__(self, index):
                if index == 1:
                    return "unexpected"
                raise IndexError(index)

        class _FakePattern:
            def match(self, _line):
                return _FakeMatch()

        with (
            mock.patch("eleanor.kernel.eq36.parsers.re.compile", return_value=_FakePattern()),
            mock.patch.object(parser, "unconsume_to_pattern"),
        ):
            with self.assertRaises(EleanorException) as cm:
                parser.check_path_termination()

        self.assertEqual(cm.exception.code, RunCode.EQ6_EARLY_TERMINATION)

    def test_outputparser3_read_bulk_properties_parses_and_computes_logs(self):
        """
        Ensure OutputParser3 bulk-property parser reads scalar fields and computes expected log fields.
        """
        parser = OutputParser3(
            io.StringIO(
                "Oxygen fugacity=1.0 bars\n"
                "Log oxygen fugacity=0.0\n"
                "Activity of water=0.9\n"
                "Log activity of water=-0.045757\n"
                "Mole fraction of water=0.95\n"
                "Log mole fraction of water=-0.022276\n"
                "Activity coefficient of water=1.1\n"
                "Log activity coefficient of water=0.041393\n"
                "Osmotic coefficient=0.8\n"
                "Stoichiometric osmotic coefficient=0.81\n"
                "Sum of molalities=0.1\n"
                "Sum of stoichiometric molalities=0.2\n"
                "Ionic strength (I)=0.3 molal\n"
                "Stoichiometric ionic strength=0.4 molal\n"
                "Ionic asymmetry (J)=0.5 molal\n"
                "Stoichiometric ionic asymmetry=0.6 molal\n"
                "Solvent mass=100 grams\n"
                "Solutes (TDS) mass=10 grams\n"
                "Aqueous solution mass=110 grams\n"
                "Aqueous solution volume=1.2 liters\n"
                "Solvent fraction=0.9 kg.h2o/kg.sol\n"
                "Solute fraction=0.1 kg.tds/kg.sol\n"
                "Total dissolved solutes (TDS)=500 mg/kg.sol\n"
                "Solution density=1.01 g/ml\n"
            )
        )

        parser.read_bulk_properties()

        self.assertEqual(parser.data["fO2"], 1.0)
        self.assertEqual(parser.data["log_fO2"], 0.0)
        self.assertEqual(parser.data["activity_water"], 0.9)
        self.assertEqual(parser.data["mole_fraction_water"], 0.95)
        self.assertEqual(parser.data["activity_coefficient_water"], 1.1)
        self.assertEqual(parser.data["osmotic_coefficient"], 0.8)
        self.assertEqual(parser.data["stoichiometric_osmotic_coefficient"], 0.81)
        self.assertEqual(parser.data["ionic_strength"], 0.3)
        self.assertEqual(parser.data["stoichiometric_ionic_strength"], 0.4)
        self.assertEqual(parser.data["ionic_asymmetry"], 0.5)
        self.assertEqual(parser.data["stoichiometric_ionic_asymmetry"], 0.6)
        self.assertEqual(parser.data["solvent_mass"], 100.0)
        self.assertEqual(parser.data["solute_mass"], 10.0)
        self.assertEqual(parser.data["solution_mass"], 110.0)
        self.assertEqual(parser.data["solution_volume"], 1.2)
        self.assertEqual(parser.data["solvent_fraction"], 0.9)
        self.assertEqual(parser.data["solute_fraction"], 0.1)
        self.assertEqual(parser.data["tds"], 500.0)
        self.assertEqual(parser.data["solution_density"], 1.01)
        self.assertAlmostEqual(parser.data["log_ionic_strength"], np.log10(0.3))
        self.assertAlmostEqual(parser.data["log_stoichiometric_ionic_strength"], np.log10(0.4))
        self.assertAlmostEqual(parser.data["log_ionic_asymmetry"], np.log10(0.5))
        self.assertAlmostEqual(parser.data["log_stoichiometric_ionic_asymmetry"], np.log10(0.6))
        self.assertAlmostEqual(parser.data["log_sum_molalities"], np.log10(0.1))
        self.assertAlmostEqual(parser.data["log_sum_stoichiometric_molalities"], np.log10(0.2))
        self.assertAlmostEqual(parser.data["log_solvent_mass"], np.log10(100.0))
        self.assertAlmostEqual(parser.data["log_solute_mass"], np.log10(10.0))
        self.assertAlmostEqual(parser.data["log_solution_mass"], np.log10(110.0))

    def test_outputparser3_init_without_file_uses_default_path(self):
        """
        Ensure OutputParser3 defaults to opening problem.3o when no file argument is provided.
        """
        with mock.patch("builtins.open", mock.mock_open(read_data="")) as mocked_open:
            parser = OutputParser3()
        mocked_open.assert_called_once_with("problem.3o", "r")
        self.assertIsInstance(parser, OutputParser3)

    def test_outputparser3_parse_success_path_returns_self(self):
        """
        Ensure OutputParser3.parse returns self on successful parse with normal-exit marker.
        """
        parser = OutputParser3(io.StringIO("Normal exit\n"))

        with (
            mock.patch.object(parser, "consume_to_pattern"),
            mock.patch.object(parser, "advance"),
            mock.patch.object(parser, "read_basic_property"),
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
            result = parser.parse()

        self.assertIs(result, parser)

    def test_outputparser_pretty_print_prints_nested_dict_and_scalar(self):
        """
        Ensure pretty_print prints both nested dictionaries and top-level scalars.
        """
        parser = self._parser("")

        with mock.patch("builtins.print") as mocked_print:
            parser.pretty_print({"root": {"leaf": 1.0}, "scalar": 2.0})

        mocked_print.assert_any_call("root")
        mocked_print.assert_any_call("   ", "leaf", 1.0)
        mocked_print.assert_any_call("scalar", 2.0)

    def test_read_liquid_saturation_states_rejects_invalid_state_token(self):
        """
        Ensure liquid saturation-state parser rejects unknown state tokens.
        """
        parser = self._parser(
            " --- Saturation States of Pure Liquids ---\n Phase Log Q/K Affinity, kcal\n hdr\nH2O -1.0 2.0 INVALID\n\n"
        )

        with self.assertRaises(EleanorParserException):
            parser.read_liquid_saturation_states()
