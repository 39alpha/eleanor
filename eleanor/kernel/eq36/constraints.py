from dataclasses import dataclass
from typing import cast, override

import numpy as np

from eleanor.constraints.interface import AbstractConstraint
from eleanor.exceptions import EleanorError
from eleanor.kernel.eq36.data1 import Data1
from eleanor.parameters import (
    ListParameter,
    NormalParameter,
    Parameter,
    ParameterRegistry,
    RangeParameter,
    Valuation,
    ValueParameter,
)


@dataclass
class TemperatureRangeConstraint(AbstractConstraint):
    temperature: Parameter
    min_temp: np.float64
    max_temp: np.float64

    def __init__(self, temperature: Parameter, data1s: list[Data1]) -> None:
        self.temperature = temperature

        if len(data1s) == 0:
            msg = "at least one data1 file must be provided"
            raise EleanorError(msg)

        self.min_temp = np.float64(np.inf)
        self.max_temp = np.float64(-np.inf)

        for data1 in data1s:
            if data1.tp_curve is not None:
                self.min_temp = min(data1.tp_curve.temperature["min"], self.min_temp)
                self.max_temp = max(data1.tp_curve.temperature["max"], self.max_temp)

    @property
    @override
    def independent_parameters(self) -> list[Parameter]:
        return []

    @property
    @override
    def dependent_parameters(self) -> list[Parameter]:
        return [self.temperature]

    @override
    def apply(self, registry: ParameterRegistry, valuation: Valuation) -> Valuation:
        temperature_id = registry.id(self.temperature)

        refined = valuation[temperature_id]
        try:
            if isinstance(refined, ValueParameter):
                if self.min_temp > refined.value or refined.value > self.max_temp:
                    msg = "fixed temperature value is outside of the data1 temperature range"
                    raise EleanorError(msg)
                return {temperature_id: refined}
            if isinstance(refined, RangeParameter):
                min_temp = max(refined.min, self.min_temp)
                max_temp = min(refined.max, self.max_temp)

                return {temperature_id: refined.restrict(RangeParameter, min_temp, max_temp)}
            if isinstance(refined, ListParameter):
                values = [t for t in refined.values if self.min_temp <= t <= self.max_temp]
                return {temperature_id: refined.restrict(ListParameter, values)}
            if isinstance(refined, NormalParameter):
                min_temp = max(refined.min, self.min_temp)
                max_temp = min(refined.max, self.max_temp)

                return {
                    temperature_id: refined.restrict(
                        NormalParameter,
                        refined.mean,
                        stddev=refined.stddev,
                        a=min_temp,
                        b=max_temp,
                    ),
                }
        except EleanorError as e:
            msg = "temperature is incompatible with the data1 temperature range"
            raise EleanorError(msg) from e

        msg = "unexpected parameter type"
        raise EleanorError(msg)


@dataclass
class TPCurveConstraint(AbstractConstraint):
    temperature: Parameter
    pressure: Parameter
    data1s: list[Data1]

    @property
    @override
    def independent_parameters(self) -> list[Parameter]:
        return [self.temperature]

    @property
    @override
    def dependent_parameters(self) -> list[Parameter]:
        return [self.pressure]

    @override
    def apply(self, registry: ParameterRegistry, valuation: Valuation) -> Valuation:
        temperature_id = registry.id(self.temperature)
        pressure_id = registry.id(self.pressure)

        input = valuation[temperature_id]
        if not isinstance(input, ValueParameter):
            msg = "temperature has not been fixed to a single value"
            raise EleanorError(msg)

        refined = valuation[pressure_id]

        temp = input.value

        try:
            values: list[np.float64] = []
            for data1 in self.data1s:
                if data1.tp_curve is not None and data1.tp_curve.temperature_in_domain(temp):
                    press = cast(np.float64 | None, data1.tp_curve(temp))
                    if press is None:
                        continue
                    if refined.in_domain(refined.fix(press)):
                        values.append(press)

            return {
                pressure_id: Parameter.refine(refined.restrict(ListParameter, values)),
            }
        except EleanorError as e:
            msg = "cannot select a pressure consistent with the data1 files"
            raise EleanorError(msg) from e


_ = AbstractConstraint.register(TPCurveConstraint)
