from types import SimpleNamespace
from unittest import mock

import pandas as pd

from eleanor.exceptions import EleanorException
from eleanor.reactants import ReactantType
from eleanor.transformers import AbstractTransformer, GlassReactantEmbedder, transform

from .common import TestCase


class _Kernel:
    def __init__(self, weights):
        self._weights = weights

    def get_atomic_weight(self, element: str):
        return self._weights.get(element)


class TestTransformers(TestCase):
    """
    Tests of the eleanor.transformers module.
    """

    def test_abstract_transformer_placeholder(self):
        """
        Ensure AbstractTransformer.transform placeholder returns the provided order.
        """
        order = object()
        self.assertIs(AbstractTransformer.transform(object(), order, object()), order)

    def test_glass_embedder_init_defaults_and_limit_clamp(self):
        """
        Ensure GlassReactantEmbedder constructor initializes defaults and clamps invalid limits.
        """
        embedder = GlassReactantEmbedder(
            filename="x.csv",
            reactant_name="glass",
            amount=1.0,
            limit=0,
        )
        self.assertEqual(embedder.filename, "x.csv")
        self.assertEqual(embedder.reactant_name, "glass")
        self.assertEqual(embedder.limit, 1)

        embedder_with_titration = GlassReactantEmbedder(
            filename="x.csv",
            reactant_name="glass",
            amount=1.0,
            titration_rate=2.0,
        )
        self.assertIsNotNone(embedder_with_titration.titration_rate)
        self.assertEqual(embedder_with_titration.titration_rate.value, 2.0)

    def test_glass_embedder_init_wraps_parameter_errors(self):
        """
        Ensure GlassReactantEmbedder wraps parameter-construction failures in EleanorException.
        """
        with self.assertRaises(EleanorException):
            GlassReactantEmbedder(filename="x.csv", reactant_name="glass", amount="not-a-number")

    def test_glass_embedder_init_reraises_eleanor_exception(self):
        """
        Ensure GlassReactantEmbedder re-raises EleanorException directly without wrapping.
        """
        with self.assertRaisesRegex(EleanorException, 'cannot create the empty ListParameter'):
            GlassReactantEmbedder(filename="x.csv", reactant_name="glass", amount=[])

    def test_read_oxide_composition(self):
        """
        Ensure oxide composition parser returns parsed stoichiometry or None for invalid names.
        """
        embedder = GlassReactantEmbedder(filename="x.csv", reactant_name="glass", amount=1.0)
        self.assertEqual(embedder.read_oxide_composition("SiO2"), {"Si": 1, "O": 2})
        self.assertEqual(embedder.read_oxide_composition("Na2O"), {"Na": 2, "O": 1})
        self.assertIsNone(embedder.read_oxide_composition("2SiO"))

    def test_read_oxide_composition_rejects_non_string_regex_groups(self):
        """
        Ensure read_oxide_composition handles defensive non-string regex group values.
        """
        embedder = GlassReactantEmbedder(filename="x.csv", reactant_name="glass", amount=1.0)

        class _Pattern:
            def match(self, _name):
                return True

            def findall(self, _name):
                return [(1, 2)]

        with mock.patch("re.compile", return_value=_Pattern()):
            self.assertIsNone(embedder.read_oxide_composition("SiO2"))

    def test_read_csv_success_and_failure(self):
        """
        Ensure read_csv returns a DataFrame on success and wraps reader failures.
        """
        embedder = GlassReactantEmbedder(filename="x.csv", reactant_name="glass", amount=1.0)
        with mock.patch("pandas.read_csv", return_value=pd.DataFrame({"SiO2": [0.6], "Na2O": [0.4]})):
            data = embedder.read_csv()
        self.assertIsInstance(data, pd.DataFrame)

        with mock.patch("pandas.read_csv", side_effect=RuntimeError("boom")):
            with self.assertRaises(EleanorException):
                embedder.read_csv()

    def test_glass_embedder_transform_builds_suborders(self):
        """
        Ensure transform creates glass-reactant suborders with normalized oxide fractions.
        """
        embedder = GlassReactantEmbedder(filename="x.csv", reactant_name="glass", amount=1.0)
        order = SimpleNamespace(transformers=[], suborders=None)
        kernel = _Kernel({"Si": 28.0, "O": 16.0, "Na": 23.0})
        data = pd.DataFrame(
            [
                {"SiO2": 0.6, "Na2O": 0.4},
                {"SiO2": 0.5, "Na2O": 0.5},
            ]
        )

        with mock.patch.object(embedder, "read_csv", return_value=data):
            out = embedder.transform(order, kernel)

        self.assertIs(out, order)
        self.assertIsNotNone(order.suborders)
        self.assertEqual(len(order.suborders.suborders), 2)
        reactant = order.suborders.suborders[0].reactants[0]
        self.assertEqual(reactant.type, ReactantType.GLASS)
        self.assertAlmostEqual(sum(oxide.fraction for oxide in reactant.oxides.values()), 1.0)

    def test_glass_embedder_transform_mass_fraction_and_limit(self):
        """
        Ensure transform converts mass fractions when requested and respects row limits.
        """
        embedder = GlassReactantEmbedder(
            filename="x.csv",
            reactant_name="glass",
            amount=1.0,
            assume_mass_fraction=True,
            limit=1,
        )
        order = SimpleNamespace(transformers=[], suborders=None)
        kernel = _Kernel({"Si": 28.0, "O": 16.0, "Na": 23.0})
        data = pd.DataFrame(
            [
                {"SiO2": 60.0, "Na2O": 40.0},
                {"SiO2": 50.0, "Na2O": 50.0},
            ]
        )

        with mock.patch.object(embedder, "read_csv", return_value=data):
            _ = embedder.transform(order, kernel)

        self.assertEqual(len(order.suborders.suborders), 1)
        reactant = order.suborders.suborders[0].reactants[0]
        self.assertNotEqual(reactant.oxides["SiO2"].fraction, 60.0 / (60.0 + 40.0))

    def test_glass_embedder_transform_rejects_unknown_atomic_weights(self):
        """
        Ensure transform raises when kernel cannot provide an atomic weight for oxide elements.
        """
        embedder = GlassReactantEmbedder(filename="x.csv", reactant_name="glass", amount=1.0)
        order = SimpleNamespace(transformers=[], suborders=None)
        kernel = _Kernel({"Si": 28.0, "O": 16.0})
        data = pd.DataFrame([{"SiO2": 0.5, "Na2O": 0.5}])

        with mock.patch.object(embedder, "read_csv", return_value=data):
            with self.assertRaises(EleanorException):
                embedder.transform(order, kernel)

    def test_glass_embedder_transform_ignores_positive_non_oxide_columns(self):
        """
        Ensure transform ignores positive numeric columns that are not recognized oxide names.
        """
        embedder = GlassReactantEmbedder(filename="x.csv", reactant_name="glass", amount=1.0)
        order = SimpleNamespace(transformers=[], suborders=None)
        kernel = _Kernel({"Si": 28.0, "O": 16.0, "Na": 23.0})
        data = pd.DataFrame([{"SiO2": 0.5, "Na2O": 0.5, "sample_id": 123.0}])

        with mock.patch.object(embedder, "read_csv", return_value=data):
            out = embedder.transform(order, kernel)

        self.assertIs(out, order)
        reactant = order.suborders.suborders[0].reactants[0]
        self.assertEqual(set(reactant.oxides.keys()), {"SiO2", "Na2O"})

    def test_glass_embedder_init_base_rate_with_oxide_rates(self):
        """
        Ensure GlassReactantEmbedder parses dict-form titration_rate with base_rate and oxide_rates.
        """
        embedder = GlassReactantEmbedder(
            filename="x.csv",
            reactant_name="glass",
            amount=1.0,
            titration_rate={
                "base_rate": 2.0,
                "oxide_rates": {"SiO2": 1.5, "Na2O": {"min": 0.5, "max": 2.0}},
            },
        )
        self.assertEqual(embedder.titration_rate.value, 2.0)
        self.assertEqual(len(embedder.oxide_rates), 2)
        self.assertEqual(embedder.oxide_rates["SiO2"].value, 1.5)

    def test_glass_embedder_init_base_rate_only(self):
        """
        Ensure GlassReactantEmbedder parses dict-form titration_rate with base_rate but no oxide_rates.
        """
        embedder = GlassReactantEmbedder(
            filename="x.csv",
            reactant_name="glass",
            amount=1.0,
            titration_rate={"base_rate": 3.0},
        )
        self.assertEqual(embedder.titration_rate.value, 3.0)
        self.assertEqual(embedder.oxide_rates, {})

    def test_glass_embedder_transform_validates_oxide_rate_names(self):
        """
        Ensure transform raises when oxide_rates reference oxides not in the CSV.
        """
        embedder = GlassReactantEmbedder(
            filename="x.csv",
            reactant_name="glass",
            amount=1.0,
            titration_rate={
                "base_rate": 1.0,
                "oxide_rates": {"SiO2": 1.5, "FeO": 2.0},
            },
        )
        order = SimpleNamespace(transformers=[], suborders=None)
        kernel = _Kernel({"Si": 28.0, "O": 16.0, "Na": 23.0})
        data = pd.DataFrame([{"SiO2": 0.6, "Na2O": 0.4}])

        with mock.patch.object(embedder, "read_csv", return_value=data):
            with self.assertRaises(EleanorException):
                embedder.transform(order, kernel)

    def test_glass_embedder_transform_validates_missing_oxide_rate(self):
        """
        Ensure transform raises when a positive-quantity oxide has no relative rate specified.
        """
        embedder = GlassReactantEmbedder(
            filename="x.csv",
            reactant_name="glass",
            amount=1.0,
            titration_rate={
                "base_rate": 1.0,
                "oxide_rates": {"SiO2": 1.5},
            },
        )
        order = SimpleNamespace(transformers=[], suborders=None)
        kernel = _Kernel({"Si": 28.0, "O": 16.0, "Na": 23.0})
        data = pd.DataFrame([{"SiO2": 0.6, "Na2O": 0.4}])

        with mock.patch.object(embedder, "read_csv", return_value=data):
            with self.assertRaises(EleanorException):
                embedder.transform(order, kernel)

    def test_glass_embedder_transform_applies_oxide_rates(self):
        """
        Ensure transform assigns per-oxide relative rates to the created GlassReactantOxide objects.
        """
        embedder = GlassReactantEmbedder(
            filename="x.csv",
            reactant_name="glass",
            amount=1.0,
            titration_rate={
                "base_rate": 2.0,
                "oxide_rates": {"SiO2": 1.5, "Na2O": 0.8},
            },
        )
        order = SimpleNamespace(transformers=[], suborders=None)
        kernel = _Kernel({"Si": 28.0, "O": 16.0, "Na": 23.0})
        data = pd.DataFrame([{"SiO2": 0.6, "Na2O": 0.4}])

        with mock.patch.object(embedder, "read_csv", return_value=data):
            embedder.transform(order, kernel)

        reactant = order.suborders.suborders[0].reactants[0]
        self.assertEqual(reactant.oxides["SiO2"].relative_rate.value, 1.5)
        self.assertEqual(reactant.oxides["Na2O"].relative_rate.value, 0.8)

    def test_glass_embedder_transform_default_oxide_rates(self):
        """
        Ensure transform assigns default relative_rate of 1.0 when no oxide_rates are specified.
        """
        embedder = GlassReactantEmbedder(
            filename="x.csv",
            reactant_name="glass",
            amount=1.0,
            titration_rate=2.0,
        )
        order = SimpleNamespace(transformers=[], suborders=None)
        kernel = _Kernel({"Si": 28.0, "O": 16.0, "Na": 23.0})
        data = pd.DataFrame([{"SiO2": 0.6, "Na2O": 0.4}])

        with mock.patch.object(embedder, "read_csv", return_value=data):
            embedder.transform(order, kernel)

        reactant = order.suborders.suborders[0].reactants[0]
        self.assertEqual(reactant.oxides["SiO2"].relative_rate.value, 1.0)
        self.assertEqual(reactant.oxides["Na2O"].relative_rate.value, 1.0)

    def test_module_transform_applies_and_clears_transformers(self):
        """
        Ensure module-level transform applies configured transformers and clears transformer configs.
        """
        from eleanor.transformers import AbstractTransformer

        kernel = object()
        order = SimpleNamespace(transformers=[], marker=0)

        class _Transformer(AbstractTransformer):
            observed_args: dict[str, object] | None = None

            def __init__(self, **args):
                # Write to the class so the assertion below can read it
                # without a reference to the specific instance.  Safe here
                # because _Transformer is defined fresh per test invocation.
                type(self).observed_args = args

            def transform(self, in_order, _kernel):
                in_order.marker += 1
                return in_order

        transformer_cfg = SimpleNamespace(type="mine", args={"filename": "x.csv"})
        order.transformers = [transformer_cfg]

        with mock.patch(
            "eleanor.transformers.get_factory",
            return_value=_Transformer,
        ) as get_factory:
            out = transform(order, kernel)

        self.assertIs(out, order)
        get_factory.assert_called_once_with("mine")
        self.assertEqual(_Transformer.observed_args, {"filename": "x.csv"})
        self.assertEqual(order.marker, 1)
        self.assertEqual(order.transformers, [])

    def test_module_transform_noop_when_no_transformers(self):
        """
        Ensure module-level transform is a no-op when no transformers are configured.
        """
        order = SimpleNamespace(transformers=[])
        self.assertIs(transform(order, object()), order)
