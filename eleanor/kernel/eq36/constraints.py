import math
from dataclasses import dataclass

from eleanor.constraints import AbstractConstraint
from eleanor.exceptions import EleanorException
from eleanor.order import Order
from eleanor.parameters import ListParameter, Parameter, ParameterRegistry, RangeParameter, Valuation, ValueParameter
from eleanor.typing import Number

from .data1 import Data1


@dataclass
class TemperatureRangeConstraint(AbstractConstraint):
    temperature: Parameter
    min_t: float
    max_t: float

    def __init__(self, temperature: Parameter, data1s: list[Data1]):
        self.temperature = temperature

        if len(data1s) == 0:
            raise EleanorException('at least one data1 file must be provided')

        self.min_t = math.inf
        self.max_t = -math.inf

        for data1 in data1s:
            if data1.tp_curve is not None:
                self.min_t = min(data1.tp_curve.T['min'], self.min_t)
                self.max_t = max(data1.tp_curve.T['max'], self.max_t)

    @property
    def independent_parameters(self) -> list[Parameter]:
        return []

    @property
    def dependent_parameters(self) -> list[Parameter]:
        return [self.temperature]

    def apply(self, registry: ParameterRegistry, valuation: Valuation) -> Valuation:
        temperature_id = registry.id(self.temperature)

        refined = valuation[temperature_id]
        try:
            if isinstance(refined, ValueParameter):
                if self.min_t > refined.value or refined.value > self.max_t:
                    raise EleanorException('fixed temperature value is outside of the data1 temperature range')
                return {temperature_id: refined}
            elif isinstance(refined, RangeParameter):
                min_t = max(refined.min, self.min_t)
                max_t = min(refined.max, self.max_t)

                return {temperature_id: refined.restrict(RangeParameter, min_t, max_t)}
            elif isinstance(refined, ListParameter):
                values = [t for t in refined.values if self.min_t <= t and t <= self.max_t]
                return {temperature_id: refined.restrict(ListParameter, values)}
        except EleanorException as e:
            raise EleanorException('temperature is incompatible with the data1 temperature range') from e

        raise EleanorException('unexpected parameter type')


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

        try:
            values: list[Number] = []
            for data1 in self.data1s:
                if data1.tp_curve is not None and data1.tp_curve.temperature_in_domain(T):
                    P = data1.tp_curve(T)
                    if P is None:
                        continue

                    if refined.in_domain(refined.fix(P)):
                        values.append(P)

            return {
                pressure_id: Parameter.refine(refined.restrict(ListParameter, values)),
            }
        except EleanorException as e:
            raise EleanorException('cannot select a pressure consistent with the data1 files') from e


AbstractConstraint.register(TPCurveConstraint)
