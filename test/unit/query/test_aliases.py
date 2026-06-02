from unittest import TestCase

from eleanor.query.aliases import _validate_short_forms_static, aliases_for, singularize, validate_short_forms


class TestAliases(TestCase):
    """
    Tests for query alias generation and validation.
    """

    def test_singularize_handles_common_plural_forms(self):
        """
        Ensure plural segment names normalize to stable singular aliases.
        """
        self.assertEqual(singularize("points"), "point")
        self.assertEqual(singularize("species"), "species")
        self.assertEqual(singularize("axes"), "axis")
        self.assertEqual(singularize("bodies"), "body")

    def test_singularize_irregular_forms_match_compound_suffixes(self):
        """
        Ensure spec §5.4 irregular suffixes match compound names and preserve prefix case.
        """
        self.assertEqual(singularize("aqueous_species"), "aqueous_species")
        self.assertEqual(singularize("coordinate_axes"), "coordinate_axis")
        self.assertEqual(singularize("Coordinate_Axes"), "Coordinate_axis")
        self.assertEqual(singularize("AQUEOUS_species"), "AQUEOUS_species")

    def test_aliases_for_returns_short_form_when_defined(self):
        """
        Ensure aliases include configured short forms for known defaults.
        """
        self.assertEqual(aliases_for("vs_points"), ("vs_point", "vs"))
        self.assertEqual(aliases_for("es_points"), ("es_point", "es"))

    def test_validate_short_forms_current_table_is_consistent(self):
        """
        Ensure short-form alias registry passes its internal consistency checks.
        """
        validate_short_forms()

    def test_validate_short_forms_static_rejects_duplicate_values(self):
        """
        Ensure two short-form keys mapping to the same value are rejected.
        """
        with self.assertRaises(AssertionError):
            _validate_short_forms_static(
                {"a": "x", "b": "x"},
                {"x": "a"},
                ("points",),
            )

    def test_validate_short_forms_static_rejects_short_form_default_collision(self):
        """
        Ensure a short form that matches a default alias derived from known_names is rejected.
        """
        with self.assertRaises(AssertionError):
            _validate_short_forms_static(
                {"something": "point"},
                {"point": "something"},
                ("points",),
            )
