from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from itertools import cycle, islice
from typing import Self, cast, override

import numpy as np
import numpy.typing as npt

from eleanor.exceptions import EleanorError
from eleanor.util import convert_to_number

type ParameterScalar = int | float | np.float64 | str | bool

type ParameterSource = dict[str, object] | list[ParameterScalar] | ParameterScalar
NEG_INF = np.float64(-np.inf)
POS_INF = np.float64(np.inf)

type ParameterOrSource = Parameter | ParameterSource


def load_parameter(param: ParameterOrSource) -> Parameter:
    if isinstance(param, Parameter):
        return param

    return Parameter.load(param)


def _as_float(value: object) -> np.float64:
    return np.float64(convert_to_number(cast(int | float | np.floating | str, value)))


def _as_float_array(values: object) -> npt.NDArray[np.float64]:
    return np.atleast_1d(np.asarray(values, dtype=np.float64))


def _as_int_array(values: object) -> npt.NDArray[np.int_]:
    return np.atleast_1d(np.asarray(values, dtype=np.int_))


@dataclass
class Parameter(ABC):
    @abstractmethod
    def in_domain(self, parameter: Parameter) -> bool:
        return False

    @abstractmethod
    def range(self) -> tuple[np.float64, np.float64]:
        return (np.float64(0), np.float64(0))

    @abstractmethod
    def volume(self) -> np.float64:
        return np.float64(1.0)

    @abstractmethod
    def random(self, size: int = 1) -> list[ValueParameter]:
        pass

    @abstractmethod
    def lattice(self, size: int = 2) -> list[ValueParameter]:
        pass

    def restrict(self, cls: type[Parameter], *args: object, **kwargs: object) -> Parameter:
        new = cls(*args, **kwargs)
        return Parameter.refine(new)

    def fix(self, value: np.float64) -> Parameter:
        return self.restrict(ValueParameter, value)

    @staticmethod
    def refine(parameter: Parameter) -> Parameter:
        if isinstance(parameter, RangeParameter) and parameter.min == parameter.max:
            return parameter.fix(parameter.min)
        if isinstance(parameter, ListParameter):
            unique = set(parameter.values)
            if len(unique) == 1:
                return parameter.fix(unique.pop())

        return parameter

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> Parameter:
        if "value" in raw:
            parameter: Parameter = ValueParameter(_as_float(raw["value"]))
        elif "values" in raw:
            parameter = ListParameter([_as_float(v) for v in cast(list[object], raw["values"])])
        elif "mean" in raw:
            mean = _as_float(raw["mean"])
            stddev = _as_float(raw["stddev"]) if "stddev" in raw else None
            a = _as_float(raw["min"]) if "min" in raw else np.float64(-np.inf)
            b = _as_float(raw["max"]) if "max" in raw else np.float64(np.inf)
            parameter = NormalParameter(mean, stddev=stddev, a=a, b=b)
        elif "min" in raw and "max" in raw:
            parameter = RangeParameter(_as_float(raw["min"]), _as_float(raw["max"]))
        else:
            msg = "parameter must have value, values or min and max"
            raise EleanorError(msg)

        return cls.refine(parameter)

    @classmethod
    def load(cls, raw: object) -> Parameter:
        if isinstance(raw, dict):
            return cls.from_dict(cast(dict[str, object], raw))
        if isinstance(raw, list):
            return cls.from_dict({"values": cast(list[ParameterScalar], raw)})
        return cls.from_dict({"value": cast(ParameterScalar, raw)})


@dataclass
class ValueParameter(Parameter):
    value: np.float64

    @override
    def in_domain(self, parameter: Parameter) -> bool:
        if not isinstance(parameter, ValueParameter):
            return False
        return bool(parameter.value == self.value)  # pyright: ignore[reportAny]

    @override
    def range(self) -> tuple[np.float64, np.float64]:
        return self.value, self.value

    @override
    def volume(self) -> np.float64:
        return np.float64(1.0)

    @override
    def random(self, size: int = 1) -> list[Self]:
        return [deepcopy(self) for _ in range(size)]

    @override
    def lattice(self, size: int = 2) -> list[Self]:
        return [deepcopy(self) for _ in range(size)]


_ = Parameter.register(ValueParameter)


@dataclass(init=False)
class RangeParameter(Parameter):
    min: np.float64
    max: np.float64

    def __init__(self, a: np.float64, b: np.float64) -> None:
        super().__init__()
        self.min = np.float64(min(a, b))
        self.max = np.float64(max(a, b))

    @property
    def bounds(self) -> tuple[ValueParameter, ValueParameter]:
        return ValueParameter(self.min), ValueParameter(self.max)

    @override
    def in_domain(self, parameter: Parameter) -> bool:
        if isinstance(parameter, ValueParameter):
            return bool(self.min <= parameter.value and parameter.value <= self.max)
        if isinstance(parameter, RangeParameter):
            return all(self.in_domain(b) for b in parameter.bounds)
        if isinstance(parameter, ListParameter):
            return all(self.in_domain(x) for x in parameter.elements)

        return False

    @override
    def range(self) -> tuple[np.float64, np.float64]:
        return self.min, self.max

    @override
    def volume(self) -> np.float64:
        return self.max - self.min

    @override
    def random(self, size: int = 1) -> list[ValueParameter]:
        from scipy.stats import uniform

        values = _as_float_array(cast(object, uniform.rvs(loc=self.min, scale=self.volume(), size=size)))
        return [ValueParameter(cast(np.float64, values[i])) for i in range(values.size)]

    @override
    def lattice(self, size: int = 2) -> list[ValueParameter]:
        values = _as_float_array(np.linspace(self.min, self.max, num=size))
        return [ValueParameter(cast(np.float64, values[i])) for i in range(values.size)]


_ = Parameter.register(RangeParameter)


@dataclass
class ListParameter(Parameter):
    values: list[np.float64]

    def __init__(self, values: list[np.float64]) -> None:
        if not values:
            msg = "cannot create the empty ListParameter"
            raise EleanorError(msg)
        super().__init__()
        self.values = sorted(values)

    @property
    def elements(self) -> list[ValueParameter]:
        return [ValueParameter(v) for v in self.values]

    @override
    def in_domain(self, parameter: Parameter) -> bool:
        if isinstance(parameter, ValueParameter):
            return parameter.value in self.values
        if isinstance(parameter, RangeParameter):
            a, b = parameter.bounds
            return a == b and self.in_domain(a)
        if isinstance(parameter, ListParameter):
            return all(self.in_domain(x) for x in parameter.elements)

        return False

    @override
    def range(self) -> tuple[np.float64, np.float64]:
        return min(self.values), max(self.values)

    @override
    def volume(self) -> np.float64:
        return np.float64(len(self.values))

    @override
    def random(self, size: int = 1) -> list[ValueParameter]:
        from scipy.stats import randint

        indices = _as_int_array(cast(object, randint.rvs(0, len(self.values), size=size)))
        return [ValueParameter(self.values[int(indices.item(i))]) for i in range(indices.size)]

    @override
    def lattice(self, size: int = 2) -> list[ValueParameter]:
        return [ValueParameter(value) for value in islice(cycle(self.values), size)]


_ = Parameter.register(ListParameter)


@dataclass
class NormalParameter(Parameter):
    mean: np.float64
    stddev: np.float64
    min: np.float64
    max: np.float64

    def __init__(
        self,
        mean: np.float64,
        stddev: np.float64 | None = None,
        a: np.float64 = NEG_INF,
        b: np.float64 = POS_INF,
    ) -> None:
        super().__init__()
        self.mean = mean
        self.min = np.float64(min(a, b))
        self.max = np.float64(max(a, b))

        if stddev is None:
            if np.isinf(self.min) or np.isinf(self.max):
                self.stddev = np.float64(1.0)
            else:
                self.stddev = (self.max - self.min) / 6
        else:
            self.stddev = stddev

    @override
    def in_domain(self, parameter: Parameter) -> bool:
        return True

    @override
    def range(self) -> tuple[np.float64, np.float64]:
        return (np.float64(-np.inf), np.float64(np.inf))

    @override
    def volume(self) -> np.float64:
        return np.float64(1.0)

    @override
    def random(self, size: int = 1) -> list[ValueParameter]:
        from scipy.stats import norm, truncnorm

        if np.isinf(self.min) and np.isinf(self.max):
            draws = cast(object, norm.rvs(loc=self.mean, scale=self.stddev, size=size))
        else:
            a = (self.min - self.mean) / self.stddev
            b = (self.max - self.mean) / self.stddev
            draws = cast(object, truncnorm.rvs(a, b, loc=self.mean, scale=self.stddev, size=size))

        samples = _as_float_array(draws)
        return [ValueParameter(cast(np.float64, samples[i])) for i in range(samples.size)]

    @override
    def lattice(self, size: int = 2) -> list[ValueParameter]:
        from scipy.special import erfinv

        u = _as_float_array(np.linspace(0, 1, num=size + 2)[1:-1])

        if not np.isinf(self.min) or not np.isinf(self.max):
            from scipy.stats import norm

            a = (self.min - self.mean) / self.stddev
            b = (self.max - self.mean) / self.stddev

            phi_alpha = _as_float(cast(object, norm.cdf(a)))
            Z = _as_float(cast(object, norm.cdf(b))) - phi_alpha

            u = Z * u + phi_alpha

        values = _as_float_array(cast(object, self.stddev * np.sqrt(2) * erfinv(2 * u - 1) + self.mean))
        return [ValueParameter(cast(np.float64, values[i])) for i in range(values.size)]


_ = Parameter.register(NormalParameter)

Valuation = dict[int, Parameter]


class ParameterRegistry:
    parameters: list[Parameter]

    def __init__(self) -> None:
        self.parameters = []

    def add_parameter(self, parameter: Parameter) -> None:
        if any(parameter is p for p in self.parameters):
            msg = "parameter already in registry"
            raise EleanorError(msg)
        self.parameters.append(parameter)

    def add_parameters(self, parameters: list[Parameter]) -> None:
        for parameter in parameters:
            self.add_parameter(parameter)

    def valuation(self) -> Valuation:
        return dict(enumerate(self.parameters))

    def id(self, parameter: Parameter) -> int:
        for i, p in enumerate(self.parameters):
            if p is parameter:
                return i
        msg = "parameter not in registry"
        raise IndexError(msg)

    def parameter(self, id: int) -> Parameter:
        if id < 0 or id >= len(self.parameters):
            msg = "parameter id not in registry"
            raise IndexError(msg)
        return self.parameters[id]
