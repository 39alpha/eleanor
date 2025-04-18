from dataclasses import dataclass

from eleanor.constraints import AbstractConstraint
from eleanor.exceptions import EleanorException
from eleanor.order import Order
from eleanor.parameters import ListParameter, Parameter, ParameterRegistry, Valuation, ValueParameter
from eleanor.typing import Number

from .data1 import Data1


@dataclass
class TPCurveConstraint(AbstractConstraint):
    temperature: Parameter
    pressure: Parameter
    data1s: list[Data1]

    @property
    def independent_parameters(self) -> list[Parameter]:
        return [self.temperature]

    @property
    def dependent_parameters(self) -> list[Parameter]:
        return [self.pressure]

    def apply(self, registry: ParameterRegistry, valuation: Valuation) -> Valuation:
        temperature_id = registry.id(self.temperature)
        pressure_id = registry.id(self.pressure)

        input = valuation[temperature_id]
        if not isinstance(input, ValueParameter):
            raise EleanorException('temperature has not been fixed to a single value')

        refined = valuation[pressure_id]
        name = refined.name
        type = refined.type

        T = input.value

        values: list[Number] = []
        for data1 in self.data1s:
            if data1.tp_curve.temperature_in_domain(T):
                P = data1.tp_curve(T)
                if P is None:
                    continue

                if refined.in_domain(refined.fix(P)):
                    values.append(P)

        return {
            pressure_id: Parameter.refine(refined.restrict(ListParameter, values)),
        }


AbstractConstraint.register(TPCurveConstraint)
