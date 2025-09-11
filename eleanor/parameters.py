import itertools
import random
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass

import numpy as np
import scipy.stats

from eleanor.exceptions import EleanorException
from eleanor.typing import Any, Number, Optional, Self
from eleanor.util import convert_to_number


@dataclass
class Parameter(ABC):
    name: str
    type: Optional[str]

    @abstractmethod
    def in_domain(self, parameter) -> bool:
        return False

    @abstractmethod
    def range(self) -> tuple[Number, Number]:
        return (0, 0)

    @abstractmethod
    def volume(self) -> float:
        return 1.0

    @abstractmethod
    def random(self, size: Optional[int] = None):
        pass

    def restrict(self, cls, *args, **kwargs):
        new = cls(self.name, self.type, *args, **kwargs)
        return Parameter.refine(new)

    def fix(self, value: Number):
        return self.restrict(ValueParameter, value)

    @staticmethod
    def refine(parameter):
        if isinstance(parameter, RangeParameter) and parameter.min == parameter.max:
            return parameter.fix(parameter.min)
        elif isinstance(parameter, ListParameter):
            unique = set(parameter.values)
            if len(unique) == 1:
                return parameter.fix(unique.pop())

        return parameter

    @classmethod
    def from_dict(cls, raw: dict[str, Any], name: Optional[str] = None):
        if name is None:
            name = raw['name']
        if not isinstance(name, str):
            raise EleanorException('parameter name must be a string')

        param_type = raw.get('type')
        if not isinstance(param_type, (str, type(None))):
            raise EleanorException('parameter type must be a string or None')

        match raw:
            case {'value': value}:
                parameter: Parameter = ValueParameter(name, param_type, convert_to_number(value))
            case {'values': values}:
                parameter = ListParameter(name, param_type, [convert_to_number(v) for v in values])
            case {'mean': mean}:
                stddev = convert_to_number(raw['stddev']) if 'stddev' in raw else None
                a = convert_to_number(raw['min']) if 'min' in raw else float('-inf')
                b = convert_to_number(raw['max']) if 'max' in raw else float('inf')
                parameter = NormalParameter(name, param_type, convert_to_number(mean), stddev=stddev, a=a, b=b)
            case {'min': min, 'max': max}:
                parameter = RangeParameter(name, param_type, convert_to_number(min), convert_to_number(max))
            case _:
                raise EleanorException('parameter must have value, values or min and max')

        return cls.refine(parameter)

    @classmethod
    def load(cls, raw: Any, name: Optional[str] = None):
        if isinstance(raw, dict):
            return cls.from_dict(raw, name=name)
        elif isinstance(raw, list):
            return cls.from_dict({'values': raw}, name=name)
        else:
            return cls.from_dict({'value': raw}, name=name)


@dataclass
class ValueParameter(Parameter):
    value: Number

    def in_domain(self, parameter: Parameter) -> bool:
        if not isinstance(parameter, ValueParameter):
            return False

        return parameter.value == self.value

    def range(self) -> tuple[Number, Number]:
        return self.value, self.value

    def volume(self) -> float:
        return 1.0

    def random(self, size: Optional[int] = None) -> Self | list[Self]:
        if size is None:
            return deepcopy(self)
        else:
            return [deepcopy(self) for _ in range(size)]


Parameter.register(ValueParameter)


@dataclass(init=False)
class RangeParameter(Parameter):
    min: Number
    max: Number

    def __init__(self, name: str, type: Optional[str], a: Number, b: Number):
        self.name = name
        self.type = type
        self.min, self.max = min(a, b), max(a, b)

    @property
    def bounds(self) -> tuple[ValueParameter, ValueParameter]:
        return self.fix(self.min), self.fix(self.max)

    def in_domain(self, parameter: Parameter) -> bool:
        if isinstance(parameter, ValueParameter):
            return self.min <= parameter.value and parameter.value <= self.max
        elif isinstance(parameter, RangeParameter):
            return all(self.in_domain(b) for b in parameter.bounds)
        elif isinstance(parameter, ListParameter):
            return all(self.in_domain(x) for x in parameter.elements)

        return False

    def range(self) -> tuple[Number, Number]:
        return self.min, self.max

    def volume(self) -> float:
        return self.max - self.min

    def random(self, size: Optional[int] = None) -> ValueParameter | list[ValueParameter]:
        if size is None:
            return self.fix(float(scipy.stats.uniform.rvs(loc=self.min, scale=self.volume())))
        else:
            return [
                self.fix(float(value))
                for value in scipy.stats.uniform.rvs(loc=self.min, scale=self.volume(), size=size)  # type: ignore
            ]


Parameter.register(RangeParameter)


@dataclass
class ListParameter(Parameter):
    values: list[Number]

    def __init__(self, name: str, type: Optional[str], values: list[Number]):
        if not values:
            raise EleanorException(f'cannot create the empty ListParameter "{name}"')
        self.name = name
        self.type = type
        self.values = sorted(values)

    @property
    def elements(self) -> list[ValueParameter]:
        return [self.fix(v) for v in self.values]

    def in_domain(self, parameter: Parameter) -> bool:
        if isinstance(parameter, ValueParameter):
            return parameter.value in self.values
        elif isinstance(parameter, RangeParameter):
            a, b = parameter.bounds
            return a == b and self.in_domain(a)
        elif isinstance(parameter, ListParameter):
            return all(self.in_domain(x) for x in parameter.elements)

        return False

    def range(self) -> tuple[Number, Number]:
        return min(self.values), max(self.values)

    def volume(self) -> float:
        return len(self.values)

    def random(self, size: Optional[int] = None) -> ValueParameter | list[ValueParameter]:
        if size is None:
            return self.fix(self.values[scipy.stats.randint.rvs(0, len(self.values))])
        else:
            return [self.fix(self.values[i])
                    for i in scipy.stats.randint.rvs(0, len(self.values), size=size)]  # type: ignore


Parameter.register(ListParameter)


@dataclass
class NormalParameter(Parameter):
    mean: Number
    stddev: Number
    min: Number
    max: Number

    def __init__(
            self,
            name: str,
            type: Optional[str],
            mean: Number,
            stddev: Optional[Number] = None,
            a: Number = float('-inf'),
            b: Number = float('inf'),
    ):
        self.name = name
        self.type = type
        self.mean = mean
        self.min, self.max = min(a, b), max(a, b)

        if stddev is None:
            if np.isinf(self.min) or np.isinf(self.max):
                self.stddev = 1.0
            else:
                self.stddev = (self.max - self.min) / 6
        else:
            self.stddev = stddev

    def in_domain(self, parameter: Parameter) -> bool:
        return True

    def range(self) -> tuple[Number, Number]:
        return -float('inf'), float('inf')

    def volume(self) -> float:
        return 1.0

    def random(self, size: Optional[int] = None) -> ValueParameter:
        if np.isinf(self.min) and np.isinf(self.max):
            if size is None:
                return self.fix(float(scipy.stats.norm.rvs(loc=self.mean, scale=self.stddev)))
            else:
                return [self.fix(value)
                        for value in scipy.stats.norm.rvs(loc=self.mean, scale=self.stddev, size=size)]  # type: ignore
        else:
            a = (self.min - self.mean) / self.stddev
            b = (self.max - self.mean) / self.stddev

            if size is None:
                return self.fix(float(scipy.stats.truncnorm.rvs(a, b, loc=self.mean, scale=self.stddev)))
            else:
                return [
                    self.fix(value) for value in scipy.stats.truncnorm.rvs(
                        a,
                        b,
                        loc=self.mean,
                        scale=self.stddev,
                        size=size,
                    )  # type: ignore
                ]


Parameter.register(NormalParameter)

Valuation = dict[int, Parameter]


class ParameterRegistry(object):
    parameters: list[Parameter]

    def __init__(self):
        self.parameters = []

    def add_parameter(self, parameter: Parameter) -> None:
        if any(parameter is p for p in self.parameters):
            raise EleanorException()
        self.parameters.append(parameter)

    def add_parameters(self, parameters: list[Parameter]) -> None:
        for parameter in parameters:
            self.add_parameter(parameter)

    def valuation(self) -> Valuation:
        return {i: p for i, p in enumerate(self.parameters)}

    def id(self, parameter: Parameter) -> int:
        for i, p in enumerate(self.parameters):
            if p is parameter:
                return i
        raise IndexError('parameter not in registry')

    def parameter(self, id: int) -> Parameter:
        if id < 0 or id >= len(self.parameters):
            raise IndexError('parameter id not in registry')
        return self.parameters[id]
