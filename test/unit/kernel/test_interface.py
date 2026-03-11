from eleanor.kernel.interface import AbstractKernel

from ..common import TestCase


class DummyKernel(AbstractKernel):
    def setup(self, *args, **kwargs):
        return "ok"

    def run(self, vs_point, *args, **kwargs):
        return [vs_point]


class TestKernelInterface(TestCase):
    """
    Tests of the eleanor.kernel.interface module.
    """

    def test_default_helpers(self):
        """
        Ensure that :class:`AbstractKernel` default helper methods return expected values.
        """
        kernel = DummyKernel()
        self.assertTrue(kernel.is_soft_exit(0))
        self.assertFalse(kernel.is_soft_exit(1))

        boatswain = object()
        self.assertIs(kernel.constrain(boatswain), boatswain)

    def test_abstract_placeholder_methods(self):
        """
        Ensure that abstract placeholder method bodies are executable when called directly.
        """
        self.assertIsNone(AbstractKernel.setup(object()))
        self.assertIsNone(AbstractKernel.run(object(), object()))
        self.assertIsNone(AbstractKernel.copy_data(object(), object()))
