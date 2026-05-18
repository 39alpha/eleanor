from typing import cast
from unittest import mock

import numpy as np

from eleanor.exceptions import EleanorException
from eleanor.parameters import ValueParameter
from eleanor.reactants import (
    AbstractReactant,
    AqueousReactant,
    CombinedComponentRaw,
    CombinedReactant,
    CombinedReactantComponent,
    ElementReactant,
    FixedGasReactant,
    GasReactant,
    MineralReactant,
    ReactantRaw,
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
        raw = cast(ReactantRaw, cast(object, {"name": "r", "type": "mineral", "amount": 1.0}))
        with mock.patch("eleanor.reactants.MineralReactant.from_dict", return_value="mineral-reactant") as m:
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
            ("combined", "eleanor.reactants.CombinedReactant.from_dict"),
        ]
        for reactant_type, target in cases:
            raw: dict[str, object] = {"name": "r", "type": reactant_type, "amount": 1.0}
            if reactant_type == "special":
                raw["composition"] = {"Na": 1}
            if reactant_type == "fixed gas":
                raw["fugacity"] = 0.1
            if reactant_type == "solid solution":
                raw["end_members"] = {"em1": 0.5, "em2": 0.5}
            if reactant_type == "combined":
                raw["components"] = {
                    "SiO2": {"name": "SiO2", "type": "special", "composition": {"Si": 1, "O": 2}, "fraction": 0.5},
                    "fayalite": {"name": "fayalite", "type": "mineral", "fraction": 0.5},
                }
            with self.subTest(reactant_type=reactant_type):
                with mock.patch(target, return_value=f"{reactant_type}-reactant") as m:
                    out = AbstractReactant.from_dict(cast(ReactantRaw, cast(object, raw)))
                m.assert_called_once_with(raw, None)
                self.assertEqual(out, f"{reactant_type}-reactant")

    def test_abstract_reactant_parameters_placeholder(self):
        """
        Ensure the abstract placeholder body for :meth:`AbstractReactant.parameters` is executable.
        """
        self.assertEqual(AbstractReactant.parameters(cast(AbstractReactant, object())), [])

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
            COMBINED = "combined"

            def __new__(cls, *_args, **_kwargs):
                return "mystery"

        with mock.patch("eleanor.reactants.ReactantType", FakeReactantType):
            with self.assertRaises(EleanorException):
                AbstractReactant.from_dict({"name": "x", "type": "anything"})

    def test_titrated_reactant_from_dict_and_volume(self):
        """
        Ensure that :class:`TitratedReactant` parses defaults and computes volume multiplicatively.
        """
        raw = cast(ReactantRaw, cast(object, {"name": "calcite", "type": "mineral", "amount": 2.0}))
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
            SpecialReactant.from_dict({"name": "s", "type": "gas", "amount": 1.0, "composition": {"Na": 1}})
        with self.assertRaises(EleanorException):
            ElementReactant.from_dict({"name": "e", "type": "gas", "amount": 1.0})

    def test_fixed_gas_from_dict_and_volume(self):
        """
        Ensure that :class:`FixedGasReactant` parsing/volume logic works for valid configs.
        """
        reactant = FixedGasReactant.from_dict({"name": "co2", "type": "fixed gas", "amount": 1.0, "fugacity": 0.1})
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
                    "end_members": {"em1": [0.1, 0.2], "em2": 0.5},
                }
            )

        with self.assertRaises(EleanorException):
            SolidSolutionReactant.from_dict(
                {
                    "name": "ss",
                    "type": "solid solution",
                    "amount": 1.0,
                    "end_members": {"em1": {"values": [0.1, 0.2]}, "em2": 0.5},
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
                    "end_members": {"em1": [0.5, 0.25], "em2": 0.5},
                }
            )

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

    def test_combined_component_from_dict_validation(self):
        """
        Ensure CombinedReactantComponent.from_dict validates type-specific payloads and constraints.
        """
        mineral = CombinedReactantComponent.from_dict({"name": "fayalite", "type": "mineral", "fraction": 0.2})
        self.assertEqual(mineral.name, "fayalite")
        self.assertEqual(mineral.type, ReactantType.MINERAL)
        self.assertIsNone(mineral.relative_rate)
        self.assertIsNone(mineral.composition)
        self.assertIsNone(mineral.end_members)

        special = CombinedReactantComponent.from_dict(
            cast(
                CombinedComponentRaw,
                cast(
                    object,
                    {
                        "name": "SiO2",
                        "type": "special",
                        "composition": {"Si": 1, "O": 2},
                        "fraction": 0.5,
                        "relative_rate": 2.5,
                    },
                ),
            )
        )
        self.assertEqual(special.type, ReactantType.SPECIAL)
        self.assertEqual(special.composition, {"Si": 1, "O": 2})
        self.assertIsInstance(special.relative_rate, ValueParameter)
        self.assertEqual(cast(ValueParameter, special.relative_rate).value, 2.5)

        solid_solution = CombinedReactantComponent.from_dict(
            cast(
                CombinedComponentRaw,
                cast(
                    object,
                    {
                        "name": "olivine",
                        "type": "solid solution",
                        "fraction": 0.3,
                        "end_members": {"fayalite": 0.6, "forsterite": 0.4},
                    },
                ),
            )
        )
        self.assertEqual(solid_solution.type, ReactantType.SOLID_SOLUTION)
        self.assertIsNotNone(solid_solution.end_members)

        with self.assertRaises(EleanorException):
            CombinedReactantComponent.from_dict({"name": "fg", "type": "fixed gas", "fraction": 0.5})
        with self.assertRaises(EleanorException):
            CombinedReactantComponent.from_dict({"name": "nested", "type": "combined", "fraction": 0.5})
        with self.assertRaises(EleanorException):
            CombinedReactantComponent.from_dict({"name": "x", "type": "mineral", "fraction": 0.0})
        with self.assertRaises(EleanorException):
            CombinedReactantComponent.from_dict({"name": "x", "type": "mineral", "fraction": 1.0})
        with self.assertRaises(EleanorException):
            CombinedReactantComponent.from_dict({"name": "SiO2", "type": "special", "fraction": 0.5})

    def test_combined_component_parameters_handles_optional_relative_rate(self):
        """
        Ensure CombinedReactantComponent.parameters() includes relative_rate only when present and always includes end members.
        """
        proportional = CombinedReactantComponent.from_dict({"name": "fayalite", "type": "mineral", "fraction": 0.5})
        self.assertIsNone(proportional.relative_rate)
        self.assertEqual(proportional.parameters(), [])

        explicit = CombinedReactantComponent.from_dict(
            {"name": "forsterite", "type": "mineral", "fraction": 0.5, "relative_rate": 0.8}
        )
        self.assertIsNotNone(explicit.relative_rate)
        if explicit.relative_rate is None:
            raise AssertionError("expected explicit relative_rate parameter")
        self.assertEqual(explicit.parameters(), [explicit.relative_rate])

        solid_solution = CombinedReactantComponent.from_dict(
            {
                "name": "olivine",
                "type": "solid solution",
                "fraction": 0.5,
                "end_members": {"fayalite": 0.6, "forsterite": 0.4},
            }
        )
        if solid_solution.end_members is None:
            raise AssertionError("expected solid-solution component end_members")
        self.assertEqual(
            solid_solution.parameters(),
            [*solid_solution.end_members.values()],
        )

    def test_combined_reactant_from_dict_success(self):
        """
        Ensure CombinedReactant.from_dict parses valid configurations.
        """
        reactant = CombinedReactant.from_dict(
            {
                "name": "basalt-glass",
                "type": "combined",
                "amount": 1.0,
                "titration_rate": 2.0,
                "components": {
                    "SiO2": {"type": "special", "composition": {"Si": 1, "O": 2}, "fraction": 0.4},
                    "Na2O": {"type": "special", "composition": {"Na": 2, "O": 1}, "fraction": 0.6},
                },
            }
        )
        self.assertEqual(reactant.type, ReactantType.COMBINED)
        self.assertEqual(set(reactant.components.keys()), {"SiO2", "Na2O"})
        self.assertAlmostEqual(sum(c.fraction for c in reactant.components.values()), 1.0)

    def test_combined_reactant_from_dict_failures(self):
        """
        Ensure CombinedReactant.from_dict rejects invalid combined-reactant definitions.
        """
        with self.assertRaises(EleanorException):
            CombinedReactant.from_dict(
                {
                    "name": "bad",
                    "type": "mineral",
                    "amount": 1.0,
                    "components": {
                        "SiO2": {"type": "special", "composition": {"Si": 1, "O": 2}, "fraction": 0.5},
                        "Al2O3": {"type": "special", "composition": {"Al": 2, "O": 3}, "fraction": 0.5},
                    },
                }
            )
        with self.assertRaises(EleanorException):
            CombinedReactant.from_dict({"name": "empty", "type": "combined", "amount": 1.0, "components": {}})
        with self.assertRaises(EleanorException):
            CombinedReactant.from_dict(
                {
                    "name": "single",
                    "type": "combined",
                    "amount": 1.0,
                    "components": {"SiO2": {"type": "special", "composition": {"Si": 1, "O": 2}, "fraction": 1.0}},
                }
            )
        with self.assertRaises(EleanorException):
            CombinedReactant.from_dict(
                {
                    "name": "sum",
                    "type": "combined",
                    "amount": 1.0,
                    "components": {
                        "SiO2": {"type": "special", "composition": {"Si": 1, "O": 2}, "fraction": 0.5},
                        "Na2O": {"type": "special", "composition": {"Na": 2, "O": 1}, "fraction": 0.4},
                    },
                }
            )
        with self.assertRaises(EleanorException):
            CombinedReactant.from_dict(
                {
                    "name": "fixed-gas-component",
                    "type": "combined",
                    "amount": 1.0,
                    "components": {
                        "one": {"type": "special", "composition": {"Si": 1, "O": 2}, "fraction": 0.5},
                        "two": {"type": "fixed gas", "fraction": 0.5},
                    },
                }
            )

    def test_combined_reactant_from_dict_rejects_wrong_type_before_components(self):
        """
        Ensure CombinedReactant.from_dict raises the type-mismatch error before component parsing.
        """
        with self.assertRaisesRegex(
            EleanorException,
            'cannot create a combined reactant from config of type "mineral"',
        ):
            CombinedReactant.from_dict(
                {
                    "name": "bad",
                    "type": "mineral",
                    "amount": 1.0,
                    "components": {
                        "only-one": {"type": "special", "composition": {"Si": 1}, "fraction": 0.5},
                    },
                }
            )

    def test_combined_reactant_parameters(self):
        """
        Ensure CombinedReactant.parameters() includes base and all component parameters.
        """
        reactant = CombinedReactant.from_dict(
            {
                "name": "combo",
                "type": "combined",
                "amount": 1.0,
                "titration_rate": 2.0,
                "components": {
                    "fayalite": {"type": "mineral", "fraction": 0.6, "relative_rate": 1.5},
                    "olivine-ss": {
                        "type": "solid solution",
                        "fraction": 0.4,
                        "relative_rate": 0.5,
                        "end_members": {"fayalite": 0.7, "forsterite": 0.3},
                    },
                },
            }
        )
        params = reactant.parameters()
        self.assertEqual(len(params), 6)

    def test_combined_reactant_volume_folds_in_component_parameters(self):
        """
        Ensure CombinedReactant.volume() folds each component's parameter
        block (relative_rate plus any nested end_members) into the parent
        volume, mirroring the SolidSolutionReactant precedent. A component
        whose ``relative_rate`` is ``None`` contributes the identity volume
        (1.0), matching ``mapreduce(..., [], 1.0)`` in the implementation.
        """
        reactant = CombinedReactant.from_dict(
            {
                "name": "combo",
                "type": "combined",
                "amount": {"min": -3.0, "max": -1.0},
                "titration_rate": {"min": 0.5, "max": 2.0},
                "components": {
                    "fayalite": {
                        "type": "mineral",
                        "fraction": 0.5,
                        "relative_rate": {"min": 0.1, "max": 10.0},
                    },
                    "forsterite": {
                        "type": "mineral",
                        "fraction": 0.3,
                        "relative_rate": {"min": 0.5, "max": 5.0},
                    },
                    "proportional": {
                        "type": "mineral",
                        "fraction": 0.2,
                    },
                },
            }
        )
        base_volume = reactant.amount.volume() * reactant.titration_rate.volume()
        component_contribution = sum(
            (
                component.relative_rate.volume() if component.relative_rate is not None else np.float64(1.0)
                for component in reactant.components.values()
            ),
            start=np.float64(0.0),
        )
        expected = base_volume + component_contribution
        self.assertEqual(reactant.volume(), expected)

    def test_combined_reactant_volume_includes_solid_solution_end_members(self):
        """
        Ensure a solid-solution component contributes the product of its
        relative_rate and end_member parameter volumes to the combined volume.
        """
        reactant = CombinedReactant.from_dict(
            {
                "name": "combo",
                "type": "combined",
                "amount": 1.0,
                "components": {
                    "fayalite": {
                        "type": "mineral",
                        "fraction": 0.6,
                        "relative_rate": {"min": 0.0, "max": 4.0},
                    },
                    "olivine-ss": {
                        "type": "solid solution",
                        "fraction": 0.4,
                        "relative_rate": {"min": 0.0, "max": 2.0},
                        "end_members": {"fayalite": 0.7, "forsterite": 0.3},
                    },
                },
            }
        )
        # amount=1.0 (volume 1), titration_rate default 1.0 (volume 1) -> super 1.0
        # fayalite: relative_rate range [0, 4] -> 4.0
        # olivine-ss: relative_rate [0, 2] (= 2.0) * end_members (each volume 1) -> 2.0 * 1 * 1
        self.assertEqual(reactant.volume(), np.float64(1.0 + 4.0 + 2.0))
