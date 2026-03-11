from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.parameters import ValueParameter
from eleanor.reactants import (
    AbstractReactant,
    AqueousReactant,
    ElementReactant,
    FixedGasReactant,
    GasReactant,
    GlassReactant,
    GlassReactantOxide,
    MineralReactant,
    ReactantType,
    SolidSolutionReactant,
    SpecialReactant,
    TitratedReactant,
)

from .common import TestCase


class TestReactants(TestCase):
    """
    Tests of the eleanor.reactants module.
    """

    def test_abstract_reactant_dispatch(self):
        """
        Ensure that :meth:`AbstractReactant.from_dict` dispatches to the matching subclass.
        """
        raw = {"name": "r", "type": "mineral", "amount": 1.0}
        with mock.patch(
            "eleanor.reactants.MineralReactant.from_dict", return_value="mineral-reactant"
        ) as m:
            out = AbstractReactant.from_dict(raw)
        m.assert_called_once_with(raw, None)
        self.assertEqual(out, "mineral-reactant")

    def test_abstract_reactant_dispatch_all_types(self):
        """
        Ensure that :meth:`AbstractReactant.from_dict` dispatches all supported reactant types.
        """
        cases = [
            ("aqueous", "eleanor.reactants.AqueousReactant.from_dict"),
            ("gas", "eleanor.reactants.GasReactant.from_dict"),
            ("fixed gas", "eleanor.reactants.FixedGasReactant.from_dict"),
            ("special", "eleanor.reactants.SpecialReactant.from_dict"),
            ("element", "eleanor.reactants.ElementReactant.from_dict"),
            ("solid solution", "eleanor.reactants.SolidSolutionReactant.from_dict"),
            ("glass", "eleanor.reactants.GlassReactant.from_dict"),
        ]
        for reactant_type, target in cases:
            raw = {"name": "r", "type": reactant_type, "amount": 1.0}
            if reactant_type == "special":
                raw["composition"] = {"Na": 1}
            if reactant_type == "fixed gas":
                raw["fugacity"] = 0.1
            if reactant_type == "solid solution":
                raw["end_members"] = {"em1": 0.5, "em2": 0.5}
            if reactant_type == "glass":
                raw["oxides"] = {
                    "SiO2": {"name": "SiO2", "composition": {"Si": 1, "O": 2}, "fraction": 0.5},
                    "Al2O3": {"name": "Al2O3", "composition": {"Al": 2, "O": 3}, "fraction": 0.5},
                }
            with self.subTest(reactant_type=reactant_type):
                with mock.patch(target, return_value=f"{reactant_type}-reactant") as m:
                    out = AbstractReactant.from_dict(raw)
                m.assert_called_once_with(raw, None)
                self.assertEqual(out, f"{reactant_type}-reactant")

    def test_abstract_reactant_parameters_placeholder(self):
        """
        Ensure the abstract placeholder body for :meth:`AbstractReactant.parameters` is executable.
        """
        self.assertEqual(AbstractReactant.parameters(object()), [])

    def test_abstract_reactant_unexpected_type_branch(self):
        """
        Ensure that the explicit unexpected-type fallback in dispatch raises :class:`EleanorException`.
        """
        class FakeReactantType:
            MINERAL = "mineral"
            AQUEOUS = "aqueous"
            GAS = "gas"
            FIXED_GAS = "fixed gas"
            SPECIAL = "special"
            ELEMENT = "element"
            SOLID_SOLUTION = "solid solution"
            GLASS = "glass"

            def __new__(cls, *_args, **_kwargs):
                return "mystery"

        with mock.patch("eleanor.reactants.ReactantType", FakeReactantType):
            with self.assertRaises(EleanorException):
                AbstractReactant.from_dict({"name": "x", "type": "anything"})

    def test_titrated_reactant_from_dict_and_volume(self):
        """
        Ensure that :class:`TitratedReactant` parses defaults and computes volume multiplicatively.
        """
        raw = {"name": "calcite", "type": "mineral", "amount": 2.0}
        reactant = TitratedReactant.from_dict(raw)
        self.assertEqual(reactant.name, "calcite")
        self.assertEqual(reactant.type, ReactantType.MINERAL)
        self.assertIsInstance(reactant.amount, ValueParameter)
        self.assertIsInstance(reactant.titration_rate, ValueParameter)
        self.assertEqual(reactant.parameters(), [reactant.amount, reactant.titration_rate])
        self.assertEqual(reactant.volume(), 1.0)

    def test_specific_titrated_subclasses_from_dict(self):
        """
        Ensure that typed titrated reactants parse successfully for their matching type.
        """
        mineral = MineralReactant.from_dict({"name": "m", "type": "mineral", "amount": 1.0})
        aqueous = AqueousReactant.from_dict({"name": "a", "type": "aqueous", "amount": 1.0})
        gas = GasReactant.from_dict({"name": "g", "type": "gas", "amount": 1.0})
        element = ElementReactant.from_dict({"name": "e", "type": "element", "amount": 1.0})
        special = SpecialReactant.from_dict(
            {
                "name": "s",
                "type": "special",
                "amount": 1.0,
                "composition": {"Na": 1},
            }
        )
        self.assertEqual(mineral.type, ReactantType.MINERAL)
        self.assertEqual(aqueous.type, ReactantType.AQUEOUS)
        self.assertEqual(gas.type, ReactantType.GAS)
        self.assertEqual(element.type, ReactantType.ELEMENT)
        self.assertEqual(special.composition, {"Na": 1})

    def test_specific_titrated_subclasses_reject_wrong_type(self):
        """
        Ensure specialized titrated reactants reject mismatched types.
        """
        with self.assertRaises(EleanorException):
            MineralReactant.from_dict({"name": "m", "type": "gas", "amount": 1.0})
        with self.assertRaises(EleanorException):
            AqueousReactant.from_dict({"name": "a", "type": "gas", "amount": 1.0})
        with self.assertRaises(EleanorException):
            GasReactant.from_dict({"name": "g", "type": "aqueous", "amount": 1.0})
        with self.assertRaises(EleanorException):
            SpecialReactant.from_dict(
                {"name": "s", "type": "gas", "amount": 1.0, "composition": {"Na": 1}}
            )
        with self.assertRaises(EleanorException):
            ElementReactant.from_dict({"name": "e", "type": "gas", "amount": 1.0})

    def test_fixed_gas_from_dict_and_volume(self):
        """
        Ensure that :class:`FixedGasReactant` parsing/volume logic works for valid configs.
        """
        reactant = FixedGasReactant.from_dict(
            {"name": "co2", "type": "fixed gas", "amount": 1.0, "fugacity": 0.1}
        )
        self.assertEqual(reactant.type, ReactantType.FIXED_GAS)
        self.assertIsInstance(reactant.amount, ValueParameter)
        self.assertIsInstance(reactant.fugacity, ValueParameter)
        self.assertEqual(reactant.parameters(), [reactant.amount, reactant.fugacity])
        self.assertEqual(reactant.volume(), 1.0)

    def test_fixed_gas_from_dict_rejects_wrong_type(self):
        """
        Ensure that :class:`FixedGasReactant` rejects non-fixed-gas configs.
        """
        with self.assertRaises(EleanorException):
            FixedGasReactant.from_dict({"name": "bad", "type": "gas", "amount": 1.0, "fugacity": 0.1})

    def test_solid_solution_from_dict_success(self):
        """
        Ensure that :class:`SolidSolutionReactant` parses valid end-member fractions.
        """
        reactant = SolidSolutionReactant.from_dict(
            {
                "name": "ss",
                "type": "solid solution",
                "amount": 1.0,
                "end_members": {"em1": 0.25, "em2": 0.75},
            }
        )
        self.assertEqual(reactant.type, ReactantType.SOLID_SOLUTION)
        self.assertEqual(set(reactant.end_members.keys()), {"em1", "em2"})
        self.assertEqual(len(reactant.parameters()), 4)
        self.assertEqual(reactant.volume(), 2.0)

    def test_solid_solution_rejects_non_value_parameter(self):
        """
        Ensure that solid-solution end members reject list/range parameters.
        """
        with self.assertRaises(EleanorException):
            SolidSolutionReactant.from_dict(
                {
                    "name": "ss",
                    "type": "solid solution",
                    "amount": 1.0,
                    "end_members": {"em1": [0.5, 0.5], "em2": 0.5},
                }
            )

        with self.assertRaises(EleanorException):
            SolidSolutionReactant.from_dict(
                {
                    "name": "ss",
                    "type": "solid solution",
                    "amount": 1.0,
                    "end_members": {"em1": {"values": [0.5, 0.5]}, "em2": 0.5},
                }
            )

        with self.assertRaises(EleanorException):
            SolidSolutionReactant.from_dict(
                {
                    "name": "ss",
                    "type": "solid solution",
                    "amount": 1.0,
                    "end_members": {"em1": {"mean": 0.5, "stddev": 0.1}, "em2": 0.5},
                }
            )

    def test_solid_solution_rejects_loaded_non_value_parameter(self):
        """
        Ensure that loaded non-value end-member parameters trigger the explicit runtime type check.
        """
        with mock.patch("eleanor.reactants.Parameter.load", return_value=object()):
            with self.assertRaises(EleanorException):
                SolidSolutionReactant.from_dict(
                    {
                        "name": "ss",
                        "type": "solid solution",
                        "amount": 1.0,
                        "end_members": {"em1": 0.5, "em2": 0.5},
                    }
                )

    def test_solid_solution_rejects_wrong_type(self):
        """
        Ensure that :class:`SolidSolutionReactant` rejects configs with non-solid-solution types.
        """
        with self.assertRaises(EleanorException):
            SolidSolutionReactant.from_dict(
                {
                    "name": "ss",
                    "type": "mineral",
                    "amount": 1.0,
                    "end_members": {"em1": 0.5, "em2": 0.5},
                }
            )

    def test_solid_solution_rejects_out_of_range_and_bad_sum(self):
        """
        Ensure that solid-solution fractions must be in [0, 1] and sum to 1.0.
        """
        with self.assertRaises(EleanorException):
            SolidSolutionReactant.from_dict(
                {
                    "name": "ss",
                    "type": "solid solution",
                    "amount": 1.0,
                    "end_members": {"em1": 1.2, "em2": -0.2},
                }
            )

        with self.assertRaises(EleanorException):
            SolidSolutionReactant.from_dict(
                {
                    "name": "ss",
                    "type": "solid solution",
                    "amount": 1.0,
                    "end_members": {"em1": 0.4, "em2": 0.5},
                }
            )

    def test_abstract_reactant_from_dict_unexpected_type_raises(self):
        """
        Ensure unexpected reactant types surface as value/enum errors.
        """
        with self.assertRaises(ValueError):
            AbstractReactant.from_dict({"name": "x", "type": "not-a-type"})

    def test_titrated_reactant_parameters_are_parameter_objects(self):
        """
        Ensure parsed titrated reactant fields are parameter instances.
        """
        reactant = TitratedReactant.from_dict({"name": "x", "type": "gas", "amount": 1.0})
        self.assertIsInstance(reactant.amount, ValueParameter)
        self.assertIsInstance(reactant.titration_rate, ValueParameter)

    def test_glass_oxide_from_dict_validation(self):
        """
        Ensure GlassReactantOxide.from_dict validates composition and fraction requirements.
        """
        oxide = GlassReactantOxide.from_dict(
            {"name": "SiO2", "composition": {"Si": 1, "O": 2}, "fraction": 0.5}
        )
        self.assertEqual(oxide.name, "SiO2")
        self.assertEqual(oxide.composition, {"Si": 1, "O": 2})
        self.assertEqual(oxide.fraction, 0.5)

        with self.assertRaises(EleanorException):
            GlassReactantOxide.from_dict({"name": "x", "composition": "invalid", "fraction": 0.5})
        with self.assertRaises(EleanorException):
            GlassReactantOxide.from_dict({"name": "x", "composition": {"Si": 1}, "fraction": 1})
        with self.assertRaises(EleanorException):
            GlassReactantOxide.from_dict({"name": "x", "composition": {"Si": 1}, "fraction": 1.0})

    def test_glass_reactant_from_dict_success_and_failures(self):
        """
        Ensure GlassReactant.from_dict parses valid configs and rejects invalid glass definitions.
        """
        reactant = GlassReactant.from_dict(
            {
                "name": "glass",
                "type": "glass",
                "amount": 1.0,
                "titration_rate": 2.0,
                "oxides": {
                    "SiO2": {"name": "SiO2", "composition": {"Si": 1, "O": 2}, "fraction": 0.4},
                    "Na2O": {"name": "Na2O", "composition": {"Na": 2, "O": 1}, "fraction": 0.6},
                },
            }
        )
        self.assertEqual(reactant.type, ReactantType.GLASS)
        self.assertEqual(set(reactant.oxides.keys()), {"SiO2", "Na2O"})

        with self.assertRaises(EleanorException):
            GlassReactant.from_dict(
                {
                    "name": "bad",
                    "type": "mineral",
                    "amount": 1.0,
                    "oxides": {
                        "SiO2": {"name": "SiO2", "composition": {"Si": 1, "O": 2}, "fraction": 0.5},
                        "Al2O3": {"name": "Al2O3", "composition": {"Al": 2, "O": 3}, "fraction": 0.5},
                    },
                }
            )

        with self.assertRaises(EleanorException):
            GlassReactant.from_dict({"name": "empty", "type": "glass", "amount": 1.0, "oxides": {}})

        with self.assertRaises(EleanorException):
            GlassReactant.from_dict(
                {
                    "name": "single",
                    "type": "glass",
                    "amount": 1.0,
                    "oxides": {
                        "SiO2": {"name": "SiO2", "composition": {"Si": 1, "O": 2}, "fraction": 0.5}
                    },
                }
            )

        with self.assertRaises(EleanorException):
            GlassReactant.from_dict(
                {
                    "name": "sum",
                    "type": "glass",
                    "amount": 1.0,
                    "oxides": {
                        "SiO2": {"name": "SiO2", "composition": {"Si": 1, "O": 2}, "fraction": 0.5},
                        "Na2O": {"name": "Na2O", "composition": {"Na": 2, "O": 1}, "fraction": 0.4},
                    },
                }
            )
