from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from itertools import cycle, islice
from typing import TypedDict, override

import numpy as np
import numpy.typing as npt
import scipy.special
import scipy.stats

from eleanor.exceptions import EleanorException
from eleanor.typing import Number, Self, cast
from eleanor.util import convert_to_number

type RawParameter = dict[str, object]

type ParameterScalar = Number | str | bool


class ParameterRaw(TypedDict, total=False):
    """Raw schema for a parameter dict accepted by :meth:`Parameter.from_dict`.

    All fields are optional because a raw parameter may take any of four
    shapes (``value``, ``values``, ``mean[/stddev/min/max]``, ``min+max``);
    the runtime validator below dispatches on which keys are present.
    """

    name: str | None
    type: object  # validated at runtime as ``str | None``
    value: ParameterScalar
    values: list[ParameterScalar]
    mean: ParameterScalar
    stddev: ParameterScalar
    min: ParameterScalar
    max: ParameterScalar


# ``ParameterSource`` captures every shape :meth:`Parameter.load` accepts.
type ParameterSource = ParameterRaw | list[ParameterScalar] | ParameterScalar


def _as_float(value: object) -> float:
    return float(convert_to_number(cast(Number | str, value)))


def _as_float_array(values: object) -> npt.NDArray[np.float64]:
    return np.atleast_1d(np.asarray(values, dtype=np.float64))


def _as_int_array(values: object) -> npt.NDArray[np.int_]:
    return np.atleast_1d(np.asarray(values, dtype=np.int_))


@dataclass
class Parameter(ABC):
    name: str
    type: str | None

    @abstractmethod
    def in_domain(self, parameter: "Parameter") -> bool:
        return False

    @abstractmethod
    def range(self) -> tuple[Number, Number]:
        return (0, 0)

    @abstractmethod
    def volume(self) -> float:
        return 1.0

    @abstractmethod
    def random(self, size: int = 1) -> list["ValueParameter"]:
        pass

    @abstractmethod
    def lattice(self, size: int = 2) -> list["ValueParameter"]:
        pass

    def restrict(self, cls: type["Parameter"], *args: object, **kwargs: object) -> "Parameter":
        new = cls(self.name, self.type, *args, **kwargs)
        return Parameter.refine(new)

    def fix(self, value: Number) -> "Parameter":
        return self.restrict(ValueParameter, value)

    @staticmethod
    def refine(parameter: "Parameter") -> "Parameter":
        if isinstance(parameter, RangeParameter) and parameter.min == parameter.max:
            return parameter.fix(parameter.min)
        elif isinstance(parameter, ListParameter):
            unique = set(parameter.values)
            if len(unique) == 1:
                return parameter.fix(unique.pop())

        return parameter

    @classmethod
    def from_dict(cls, raw: ParameterRaw, name: str | None = None) -> "Parameter":
        if name is None:
            name = raw.get("name")
        if not isinstance(name, str):
            raise EleanorException("parameter name must be a string")

        param_type = raw.get("type")
        if param_type is not None and not isinstance(param_type, str):
            raise EleanorException("parameter type must be a string or None")

        if "value" in raw:
            parameter: Parameter = ValueParameter(name, param_type, _as_float(raw["value"]))
        elif "values" in raw:
            parameter = ListParameter(name, param_type, [_as_float(v) for v in raw["values"]])
        elif "mean" in raw:
            mean = _as_float(raw["mean"])
            stddev = _as_float(raw["stddev"]) if "stddev" in raw else None
            a = _as_float(raw["min"]) if "min" in raw else -np.inf
            b = _as_float(raw["max"]) if "max" in raw else np.inf
            parameter = NormalParameter(name, param_type, mean, stddev=stddev, a=a, b=b)
        elif "min" in raw and "max" in raw:
            parameter = RangeParameter(name, param_type, _as_float(raw["min"]), _as_float(raw["max"]))
        else:
            raise EleanorException("parameter must have value, values or min and max")

        return cls.refine(parameter)

    @classmethod
    def load(cls, raw: object, name: str | None = None) -> "Parameter":
        if isinstance(raw, dict):
            return cls.from_dict(cast(ParameterRaw, cast(object, raw)), name=name)
        elif isinstance(raw, list):
            return cls.from_dict(
                ParameterRaw(values=cast(list[ParameterScalar], cast(object, raw))),
                name=name,
            )
        else:
            return cls.from_dict(ParameterRaw(value=cast(ParameterScalar, raw)), name=name)


@dataclass
class ValueParameter(Parameter):
    value: Number

    @override
    def in_domain(self, parameter: Parameter) -> bool:
        if not isinstance(parameter, ValueParameter):
            return False

        return parameter.value == self.value

    @override
    def range(self) -> tuple[Number, Number]:
        return self.value, self.value

    @override
    def volume(self) -> float:
        return 1.0

    @override
    def random(self, size: int = 1) -> list[Self]:
        return [deepcopy(self) for _ in range(size)]

    @override
    def lattice(self, size: int = 2) -> list[Self]:
        return [deepcopy(self) for _ in range(size)]


_ = Parameter.register(ValueParameter)


@dataclass(init=False)
class RangeParameter(Parameter):
    min: Number
    max: Number

    def __init__(self, name: str, type: str | None, a: Number, b: Number):
        super().__init__(name, type)
        self.min, self.max = min(a, b), max(a, b)

    @property
    def bounds(self) -> tuple[ValueParameter, ValueParameter]:
        return ValueParameter(self.name, self.type, self.min), ValueParameter(self.name, self.type, self.max)

    @override
    def in_domain(self, parameter: Parameter) -> bool:
        if isinstance(parameter, ValueParameter):
            return self.min <= parameter.value and parameter.value <= self.max
        elif isinstance(parameter, RangeParameter):
            return all(self.in_domain(b) for b in parameter.bounds)
        elif isinstance(parameter, ListParameter):
            return all(self.in_domain(x) for x in parameter.elements)

        return False

    @override
    def range(self) -> tuple[Number, Number]:
        return self.min, self.max

    @override
    def volume(self) -> float:
        return self.max - self.min

    @override
    def random(self, size: int = 1) -> list[ValueParameter]:
        values = _as_float_array(cast(object, scipy.stats.uniform.rvs(loc=self.min, scale=self.volume(), size=size)))
        return [ValueParameter(self.name, self.type, float(cast(Number, values.item(i)))) for i in range(values.size)]

    @override
    def lattice(self, size: int = 2) -> list[ValueParameter]:
        values = _as_float_array(np.linspace(self.min, self.max, num=size))
        return [ValueParameter(self.name, self.type, float(cast(Number, values.item(i)))) for i in range(values.size)]


_ = Parameter.register(RangeParameter)


@dataclass
class ListParameter(Parameter):
    values: list[Number]

    def __init__(self, name: str, type: str | None, values: list[Number]):
        if not values:
            raise EleanorException(f'cannot create the empty ListParameter "{name}"')
        super().__init__(name, type)
        self.values = sorted(values)

    @property
    def elements(self) -> list[ValueParameter]:
        return [ValueParameter(self.name, self.type, v) for v in self.values]

    @override
    def in_domain(self, parameter: Parameter) -> bool:
        if isinstance(parameter, ValueParameter):
            return parameter.value in self.values
        elif isinstance(parameter, RangeParameter):
            a, b = parameter.bounds
            return a == b and self.in_domain(a)
        elif isinstance(parameter, ListParameter):
            return all(self.in_domain(x) for x in parameter.elements)

        return False

    @override
    def range(self) -> tuple[Number, Number]:
        return min(self.values), max(self.values)

    @override
    def volume(self) -> float:
        return len(self.values)

    @override
    def random(self, size: int = 1) -> list[ValueParameter]:
        indices = _as_int_array(cast(object, scipy.stats.randint.rvs(0, len(self.values), size=size)))
        return [
            ValueParameter(self.name, self.type, self.values[int(cast(Number, indices.item(i)))])
            for i in range(indices.size)
        ]

    @override
    def lattice(self, size: int = 2) -> list[ValueParameter]:
        return [ValueParameter(self.name, self.type, value) for value in islice(cycle(self.values), size)]


_ = Parameter.register(ListParameter)


@dataclass
class NormalParameter(Parameter):
    mean: Number
    stddev: Number
    min: Number
    max: Number

    def __init__(
        self,
        name: str,
        type: str | None,
        mean: Number,
        stddev: Number | None = None,
        a: Number = -np.inf,
        b: Number = np.inf,
    ):
        super().__init__(name, type)
        self.mean = mean
        self.min, self.max = min(a, b), max(a, b)

        if stddev is None:
            if np.isinf(self.min) or np.isinf(self.max):
                self.stddev = 1.0
            else:
                self.stddev = (self.max - self.min) / 6
        else:
            self.stddev = stddev

    @override
    def in_domain(self, parameter: Parameter) -> bool:
        return True

    @override
    def range(self) -> tuple[Number, Number]:
        return -float("inf"), float("inf")

    @override
    def volume(self) -> float:
        return 1.0

    @override
    def random(self, size: int = 1) -> list[ValueParameter]:
        if np.isinf(self.min) and np.isinf(self.max):
            draws = cast(object, scipy.stats.norm.rvs(loc=self.mean, scale=self.stddev, size=size))
        else:
            a = (self.min - self.mean) / self.stddev
            b = (self.max - self.mean) / self.stddev
            draws = cast(object, scipy.stats.truncnorm.rvs(a, b, loc=self.mean, scale=self.stddev, size=size))

        samples = _as_float_array(draws)
        return [ValueParameter(self.name, self.type, float(cast(Number, samples.item(i)))) for i in range(samples.size)]

    @override
    def lattice(self, size: int = 2) -> list[ValueParameter]:
        u = _as_float_array(np.linspace(0, 1, num=size + 2)[1:-1])

        if not np.isinf(self.min) or not np.isinf(self.max):
            a = (self.min - self.mean) / self.stddev
            b = (self.max - self.mean) / self.stddev

            phi_alpha = _as_float(cast(object, scipy.stats.norm.cdf(a)))
            Z = _as_float(cast(object, scipy.stats.norm.cdf(b))) - phi_alpha

            u = Z * u + phi_alpha

        values = _as_float_array(cast(object, self.stddev * np.sqrt(2) * scipy.special.erfinv(2 * u - 1) + self.mean))
        return [ValueParameter(self.name, self.type, float(cast(Number, values.item(i)))) for i in range(values.size)]


_ = Parameter.register(NormalParameter)

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
        raise IndexError("parameter not in registry")

    def parameter(self, id: int) -> Parameter:
        if id < 0 or id >= len(self.parameters):
            raise IndexError("parameter id not in registry")
        return self.parameters[id]
