import io
from typing import cast
from unittest import mock

from eleanor.exceptions import EleanorFileException, EleanorParserException
from eleanor.kernel.eq36.codes import RunCode
from eleanor.kernel.eq36.util import determine_species, field_as_float, get_field, read_pickup_lines

from ...common import TestCase


class TestEq36Util(TestCase):
    """
    Tests of the eleanor.kernel.eq36.util module.
    """

    def test_get_field_and_field_as_float(self):
        """
        Ensure field extraction and float parsing support expected EQ36 formats.
        """
        self.assertEqual(get_field("a b c", 1), "b")
        self.assertEqual(field_as_float("1.23+04"), 1.23e04)
        self.assertEqual(field_as_float("-2.5E-02"), -2.5e-02)
        with self.assertRaises(EleanorParserException):
            field_as_float("not-a-number")

    def test_read_pickup_lines_variants(self):
        """
        Ensure pickup line reading supports handles/paths/default and errors on missing separators.
        """
        with mock.patch("eleanor.kernel.eq36.util.read_pickup_lines", return_value=["x"]) as rl:
            self.assertEqual(read_pickup_lines(None), ["x"])
            rl.assert_called_once_with("problem.3p")

        handle = io.StringIO("head\n*---\nline1\nline2\n")
        self.assertEqual(read_pickup_lines(cast(io.TextIOWrapper, cast(object, handle))), ["line1\n", "line2\n"])

        with mock.patch("builtins.open", return_value=io.StringIO("head\n*---\nline1\n")):
            self.assertEqual(read_pickup_lines("file.3p"), ["line1\n"])

        with self.assertRaises(EleanorFileException) as cm:
            read_pickup_lines(cast(io.TextIOWrapper, cast(object, io.StringIO("no separator\n"))))
        self.assertEqual(cm.exception.code, RunCode.FILE_ERROR_3P)

        with mock.patch("builtins.open", side_effect=FileNotFoundError("missing")):
            with self.assertRaises(EleanorFileException) as cm2:
                read_pickup_lines("missing.3p")
        self.assertEqual(cm2.exception.code, RunCode.FILE_ERROR_3P)

    def test_read_pickup_lines_handle_read_raises_filenotfound(self):
        """
        Ensure handle-based read failures are wrapped as EleanorFileException.
        """
        handle = mock.Mock()
        handle.readlines.side_effect = FileNotFoundError("missing")
        with self.assertRaises(EleanorFileException) as cm:
            read_pickup_lines(handle)
        self.assertEqual(cm.exception.code, RunCode.FILE_ERROR_3P)

    def _determine_species_text(self) -> str:
        return (
            "header\n"
            " * Alter/suppress options\n"
            "count 1\n"
            "            SUPSOL\n"
            " Done. Hybrid Newton-Raphson iteration converged in \n"
            "--- Saturation States of Solid Solutions ---\n"
            "line-a\n"
            "line-b\n"
            "line-c\n"
            "SUPSOL                    stuff\n"
            "KEEP                      stuff\n"
            "\n"
            "--- Fugacities ---\n"
            "line-a\n"
            "line-b\n"
            "line-c\n"
            "\n"
        )

    def test_determine_species_string_path_uses_opened_handle(self):
        """
        Ensure string path input is parsed via opened file content rather than recursive self-call.
        """
        with mock.patch("builtins.open", return_value=io.StringIO(self._determine_species_text())):
            elements, aqueous, solids, solid_solutions, _, gases = determine_species("fake.3o")
        self.assertEqual(elements, [])
        self.assertEqual(aqueous, [])
        self.assertEqual(solids, [])
        self.assertEqual(gases, [])
        self.assertEqual(solid_solutions, ["KEEP"])

    def test_determine_species_none_uses_default_path(self):
        """
        Ensure determine_species(None) falls back to reading problem.3o.
        """
        with mock.patch("builtins.open", return_value=io.StringIO(self._determine_species_text())) as open_mock:
            _, _, _, solid_solutions, _, _ = determine_species(None)
        open_mock.assert_called_once_with("problem.3o", "r")
        self.assertEqual(solid_solutions, ["KEEP"])

    def test_read_pickup_lines_separator_at_end_returns_empty_payload(self):
        """
        Ensure pickup parsing returns empty content when separator is the final line.
        """
        handle = io.StringIO("header\n*---\n")
        self.assertEqual(read_pickup_lines(cast(io.TextIOWrapper, cast(object, handle))), [])

    def test_determine_species_parses_all_sections_and_applies_suppression(self):
        """
        Ensure determine_species parses major report sections and filters suppressed entries.
        """
        elements, aqueous, solids, solid_solutions, _, gases = determine_species(
            cast(io.TextIOWrapper, cast(object, io.StringIO(self._determine_species_full_text())))
        )
        self.assertEqual(elements, ["K"])
        self.assertEqual(aqueous, ["HCO3-"])
        self.assertEqual(solids, ["CALCITE"])
        self.assertEqual(solid_solutions, ["KEEP"])
        self.assertEqual(gases, ["CO2(g)"])

    def test_determine_species_without_convergence_marker(self):
        """
        Ensure determine_species still parses trailing sections when convergence marker is absent.
        """
        text = (
            "header\n"
            "--- Saturation States of Solid Solutions ---\n"
            "h1\n"
            "h2\n"
            "h3\n"
            "KEEP                      x\n"
            "\n"
            "--- Fugacities ---\n"
            "h1\n"
            "h2\n"
            "h3\n"
            "CO2(g)                    x\n"
            "\n"
        )
        elements, aqueous, solids, solid_solutions, _, gases = determine_species(
            cast(io.TextIOWrapper, cast(object, io.StringIO(text)))
        )
        self.assertEqual(elements, [])
        self.assertEqual(aqueous, [])
        self.assertEqual(solids, [])
        self.assertEqual(solid_solutions, ["KEEP"])
        self.assertEqual(gases, ["CO2(g)"])

    def _determine_species_full_text(self) -> str:
        return (
            "header\n"
            " * Alter/suppress options\n"
            "count 2\n"
            "            SUPSOL\n"
            "ignored\n"
            "            SUPAQ\n"
            " Done. Hybrid Newton-Raphson iteration converged in \n"
            "           --- Elemental Composition of the Aqueous Solution ---\n"
            "h1\n"
            "h2\n"
            "h3\n"
            "O            1.0\n"
            "H            1.0\n"
            "Na           0.0\n"
            "K            1.0\n"
            "\n"
            "--- Distribution of Aqueous Solute Species ---\n"
            "h1\n"
            "h2\n"
            "h3\n"
            "O2(g)                     x\n"
            "SUPAQ                     x\n"
            "HCO3-                     x\n"
            "\n"
            "           --- Saturation States of Pure Solids ---\n"
            "h1\n"
            "h2\n"
            "h3\n"
            "None\n"
            "CALCITE                   x\n"
            "SUPSOL                    x\n"
            "\n"
            "--- Saturation States of Solid Solutions ---\n"
            "h1\n"
            "h2\n"
            "h3\n"
            "None\n"
            "SUPSOL                    x\n"
            "KEEP                      x\n"
            "\n"
            "--- Fugacities ---\n"
            "h1\n"
            "h2\n"
            "h3\n"
            "CO2(g)                    x\n"
            "SUPAQ                     x\n"
            "\n"
        )

    def test_determine_species_suppresses_solid_solution_entries(self):
        """
        Ensure suppressed solid solutions are removed from parsed solid solution list.
        """
        elements, aqueous, solids, solid_solutions, _, gases = determine_species(
            cast(io.TextIOWrapper, cast(object, io.StringIO(self._determine_species_text())))
        )
        self.assertEqual(elements, [])
        self.assertEqual(aqueous, [])
        self.assertEqual(solids, [])
        self.assertEqual(gases, [])
        self.assertEqual(solid_solutions, ["KEEP"])
