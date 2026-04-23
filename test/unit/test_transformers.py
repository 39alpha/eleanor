from types import SimpleNamespace
from unittest import mock

from eleanor.exceptions import EleanorException
from eleanor.transformer import AbstractTransformer, transform

from .common import TestCase


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

    def test_module_transform_applies_and_clears_transformers(self):
        """
        Ensure module-level transform applies configured transformers and clears transformer configs.
        """
        kernel = object()
        order = SimpleNamespace(transformers=[], marker=0)

        class _Transformer(AbstractTransformer):
            observed_args: dict[str, object] | None = None

            def __init__(self, **args):
                type(self).observed_args = args

            def transform(self, in_order, _kernel):
                in_order.marker += 1
                return in_order

        transformer_cfg = SimpleNamespace(type="mine", args={"filename": "x.csv"})
        order.transformers = [transformer_cfg]

        with mock.patch(
            "eleanor.transformer.get_factory",
            return_value=_Transformer,
        ) as get_factory:
            out = transform(order, kernel)

        self.assertIs(out, order)
        get_factory.assert_called_once_with("mine")
        self.assertEqual(_Transformer.observed_args, {"filename": "x.csv"})
        self.assertEqual(order.marker, 1)
        self.assertEqual(order.transformers, [])

    def test_module_transform_applies_override_instances(self):
        """
        Ensure module-level transform applies explicit override instances in sequence.
        """
        kernel = object()
        order = SimpleNamespace(transformers=[SimpleNamespace(type="unused", args={})], marker=0)

        class _Transformer(AbstractTransformer):
            def transform(self, in_order, _kernel):
                in_order.marker += 1
                return in_order

        out = transform(order, kernel, overrides=[_Transformer(), _Transformer()])
        self.assertIs(out, order)
        self.assertEqual(order.marker, 2)
        self.assertEqual(order.transformers, [])

    def test_module_transform_rejects_non_transformer_plugin_returns(self):
        """
        Ensure module-level transform raises when a plugin factory returns a non-transformer object.
        """
        order = SimpleNamespace(transformers=[SimpleNamespace(type="mine", args={})])
        with (
            mock.patch("eleanor.transformer.get_factory", return_value=lambda **_args: object()),
            self.assertRaisesRegex(EleanorException, 'expected an AbstractTransformer'),
        ):
            _ = transform(order, object())

    def test_module_transform_noop_when_no_transformers(self):
        """
        Ensure module-level transform is a no-op when no transformers are configured.
        """
        order = SimpleNamespace(transformers=[])
        self.assertIs(transform(order, object()), order)
