from abc import ABC, abstractmethod
from dataclasses import dataclass

from eleanor.exceptions import EleanorException
from eleanor.typing import Any, Number, Optional
from eleanor.util import convert_to_number


@dataclass
class Parameter(ABC):
    name: str
    type: Optional[str]
    unit: Optional[str]

    @abstractmethod
    def in_domain(self, parameter) -> bool:
        return False

    @abstractmethod
    def range(self) -> tuple[Number, Number]:
        return (0, 0)

    def restrict(self, cls, *args, **kwargs):
        new = cls(self.name, self.type, self.unit, *args, **kwargs)
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

        unit = raw.get('unit')
        if not isinstance(param_type, (str, type(None))):
            raise EleanorException('parameter unit must be a string or None')

        match raw:
            case {'value': value}:
                parameter: Parameter = ValueParameter(name, param_type, unit, convert_to_number(value))
            case {'min': min, 'max': max}:
                parameter = RangeParameter(name, param_type, unit, convert_to_number(min), convert_to_number(max))
            case {'values': values}:
                parameter = ListParameter(name, param_type, unit, [convert_to_number(v) for v in values])
            case _:
                raise EleanorException('parameter must have value, values or min and max')

        return cls.refine(parameter)


@dataclass
class ValueParameter(Parameter):
    value: Number

    def in_domain(self, parameter: Parameter) -> bool:
        if not isinstance(parameter, ValueParameter):
            return False

        return parameter.value == self.value

    def range(self) -> tuple[Number, Number]:
        return self.value, self.value


Parameter.register(ValueParameter)


@dataclass(init=False)
class RangeParameter(Parameter):
    min: Number
    max: Number

    def __init__(self, name: str, type: Optional[str], unit: Optional[str], a: Number, b: Number):
        a, b = min(a, b), max(a, b)
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'type', type)
        object.__setattr__(self, 'unit', unit)
        object.__setattr__(self, 'min', a)
        object.__setattr__(self, 'max', b)

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


Parameter.register(RangeParameter)


@dataclass
class ListParameter(Parameter):
    values: list[Number]

    def __init__(self, name: str, type: Optional[str], unit: Optional[str], values: list[Number]):
        if not values:
            raise EleanorException(f'cannot create the empty ListParameter "{name}"')
        object.__setattr__(self, 'name', name)
        object.__setattr__(self, 'type', type)
        object.__setattr__(self, 'unit', unit)
        object.__setattr__(self, 'values', sorted(values))

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


Parameter.register(ListParameter)

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
