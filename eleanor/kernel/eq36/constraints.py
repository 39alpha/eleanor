from dataclasses import dataclass

from eleanor.constraints import AbstractConstraint, Valuation
from eleanor.exceptions import EleanorException
from eleanor.order import Order
from eleanor.parameters import ListParameter, Parameter, ValueParameter
from eleanor.typing import Number

from .data0_tools import TPCurve


@dataclass
class TPCurveConstraint(AbstractConstraint):
    temperature: Parameter
    pressure: Parameter
    curves: list[TPCurve]

    @property
    def independent_parameters(self) -> list[Parameter]:
        return [self.temperature]

    @property
    def dependent_parameters(self) -> list[Parameter]:
        return [self.pressure]

    def apply(self, valuation: Valuation) -> dict[Parameter, Parameter]:
        input = valuation[self.temperature]
        if not isinstance(input, ValueParameter):
            raise EleanorException()

        refined = valuation[self.pressure]
        name = refined.name
        type = refined.type

        T = input.value

        values: list[Number] = []
        for curve in self.curves:
            if curve.temperature_in_domain(T):
                P = curve(T)
                if P is None:
                    continue

                if refined.in_domain(refined.fix(P)):
                    values.append(P)

        return {
            self.pressure: Parameter.refine(refined.restrict(ListParameter, values)),
        }


AbstractConstraint.register(TPCurveConstraint)
