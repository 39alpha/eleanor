from typing import Unpack, cast, override
from unittest import TestCase

import eleanor.equilibrium_space as es
import eleanor.variable_space as vs
from eleanor.constraints.point_builder import PointBuilder
from eleanor.kernel.interface import AbstractKernel
from eleanor.order import Order
from eleanor.typing import EleanorKwargs


class DummyKernel(AbstractKernel):
    @override
    def setup(
        self,
        order: Order | None = None,
        **kwargs: object,
    ) -> None:
        _ = order
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

    def test_default_helpers(self) -> None:
        """
        Ensure that :class:`AbstractKernel` default helper methods return expected values.
        """
        kernel = DummyKernel()
        self.assertTrue(kernel.is_soft_exit(0))
        self.assertFalse(kernel.is_soft_exit(1))
        point_builder = cast(PointBuilder, object())
        self.assertIs(kernel.constrain(point_builder), point_builder)

    def test_abstract_placeholder_methods(self) -> None:
        """
        Ensure that abstract placeholder method bodies are executable when called directly.
        """
        abstract_kernel = cast(AbstractKernel, object())
        vs_point = cast(vs.Point, object())
        order = cast(Order, object())
        self.assertIsNone(AbstractKernel.setup(abstract_kernel, order))
        self.assertIsNone(AbstractKernel.run(abstract_kernel, vs_point))
        self.assertIsNone(AbstractKernel.copy_data(abstract_kernel, vs_point))
        self.assertIsNone(AbstractKernel.get_atomic_weight(abstract_kernel, "Na"))
        AbstractKernel.validate_order(abstract_kernel, order)
        self.assertIsNone(AbstractKernel.get_molar_mass(abstract_kernel, "H2O"))
