from typing import cast, override

import eleanor.equilibrium_space as es
import eleanor.variable_space as vs
from eleanor.constraints import Boatswain
from eleanor.kernel.interface import AbstractKernel
from eleanor.order import Order
from eleanor.typing import EleanorKwargs, Unpack

from ..common import TestCase


class DummyKernel(AbstractKernel):
    @override
    def setup(
        self,
        order: Order | None = None,
        *args: object,
        **kwargs: Unpack[EleanorKwargs],
    ) -> None:
        _ = order
        _ = args
        _ = kwargs

    @override
    def run(
        self,
        vs_point: vs.Point,
        *args: object,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[es.Point]:
        _ = vs_point
        _ = args
        _ = kwargs
        return []


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
        boatswain = cast(Boatswain, object())
        self.assertIs(kernel.constrain(boatswain), boatswain)

    def test_abstract_placeholder_methods(self):
        """
        Ensure that abstract placeholder method bodies are executable when called directly.
        """
        abstract_kernel = cast(AbstractKernel, object())
        vs_point = cast(vs.Point, object())
        self.assertIsNone(AbstractKernel.setup(abstract_kernel))
        self.assertIsNone(AbstractKernel.run(abstract_kernel, vs_point))
        self.assertIsNone(AbstractKernel.copy_data(abstract_kernel, vs_point))
        self.assertIsNone(AbstractKernel.get_atomic_weight(abstract_kernel, "Na"))
