import enum
from unittest import TestCase

import numpy as np
from eleanor.query.coercion import coerce_filter_value, parse_missing_policy
from eleanor.query.errors import InvalidFilterValue, ParseError


class _Kind(enum.Enum):
    """
    Enum used to verify enum coercion paths.
    """

    LOW = "low"
    HIGH = "high"


class TestCoercion(TestCase):
    """
    Tests for missing-policy and predicate-value coercion behavior.
    """

    def test_parse_missing_policy_accepts_all_supported_values(self) -> None:
        """
        Ensure all documented missing policies parse successfully.
        """
        self.assertEqual(parse_missing_policy("blank"), "blank")
        self.assertEqual(parse_missing_policy("null"), "null")
        self.assertEqual(parse_missing_policy("error"), "error")

    def test_parse_missing_policy_rejects_unknown_value(self) -> None:
        """
        Ensure unknown missing-policy strings raise ParseError.
        """
        with self.assertRaises(ParseError):
            parse_missing_policy("ignore")

    def test_coerce_filter_value_for_primitives(self) -> None:
        """
        Ensure primitive targets coerce valid literal values.
        """
        self.assertEqual(coerce_filter_value(int, "7", path="p", predicate="i=7"), 7)
        self.assertEqual(
            coerce_filter_value(float, "1.25", path="p", predicate="f=1.25"), 1.25
        )
        self.assertEqual(
            coerce_filter_value(np.float64, "1.25", path="p", predicate="f=1.25"),
            np.float64(1.25),
        )
        self.assertIs(
            coerce_filter_value(bool, "true", path="p", predicate="b=true"), True
        )
        self.assertIs(
            coerce_filter_value(bool, "FALSE", path="p", predicate="b=FALSE"), False
        )
        self.assertEqual(
            coerce_filter_value(str, "abc", path="p", predicate="s=abc"), "abc"
        )

    def test_coerce_filter_value_for_enum_by_name_and_value(self) -> None:
        """
        Ensure enum filters accept both member names and member values.
        """
        self.assertIs(
            coerce_filter_value(_Kind, "LOW", path="p", predicate="k=LOW"), _Kind.LOW
        )
        self.assertIs(
            coerce_filter_value(_Kind, "high", path="p", predicate="k=high"), _Kind.HIGH
        )

    def test_coerce_filter_value_rejects_invalid_values(self) -> None:
        """
        Ensure invalid literals raise InvalidFilterValue for target type.
        """
        with self.assertRaises(InvalidFilterValue):
            coerce_filter_value(int, "not_int", path="p", predicate="i=not_int")
        with self.assertRaises(InvalidFilterValue):
            coerce_filter_value(bool, "yes", path="p", predicate="b=yes")
        with self.assertRaises(InvalidFilterValue):
            coerce_filter_value(_Kind, "MEDIUM", path="p", predicate="k=MEDIUM")
