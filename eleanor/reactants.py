import operator
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict, override

import numpy as np

from .exceptions import EleanorException
from .parameters import Parameter, ParameterSource, ValueParameter
from .typing import cast
from .util import mapreduce

type RawMap = dict[str, object]


class GlassOxideRaw(TypedDict, total=False):
    """Raw schema for a single oxide block inside a glass reactant."""

    name: str | None
    composition: dict[str, int]
    fraction: float | np.float64
    relative_rate: ParameterSource


class ReactantRaw(TypedDict, total=False):
    """Raw schema shared by every reactant variant.

    Variant-specific keys (``fugacity`` for fixed gas, ``composition`` for
    special, ``end_members`` for solid solution, ``oxides`` for glass) are
    declared here so that the ``TypedDict`` covers the full surface area;
    each concrete ``from_dict`` only reads the subset it needs.
    """

    type: str
    name: str | None
    amount: ParameterSource
    titration_rate: ParameterSource
    fugacity: ParameterSource
    composition: dict[str, int]
    end_members: dict[str, ParameterSource]
    oxides: dict[str, GlassOxideRaw]


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise EleanorException(f"{field_name} must be a string")
    return value


def _require_dict[T](value: object, field_name: str) -> dict[str, T]:
    """Validate that ``value`` is a ``dict`` at runtime and return it typed.

    The incoming TypedDict declarations are aspirational over untrusted
    YAML/JSON/TOML input, so an ``isinstance`` check is genuinely useful.
    Accepting ``object`` widens the declared type enough that pyright treats
    the check as meaningful.
    """
    if not isinstance(value, dict):
        raise EleanorException(f"{field_name} must be a dictionary")
    return cast(dict[str, T], cast(object, value))


def _require_float(value: object, field_name: str) -> np.float64:
    if isinstance(value, float):
        return np.float64(value)
    if isinstance(value, np.floating):
        return cast(np.float64, value)
    raise EleanorException(f"{field_name} must be a floating-point number")


class ReactantType(StrEnum):
    MINERAL = "mineral"
    GAS = "gas"
    FIXED_GAS = "fixed gas"
    SPECIAL = "special"
    ELEMENT = "element"
    SOLID_SOLUTION = "solid solution"
    AQUEOUS = "aqueous"
    GLASS = "glass"


@dataclass
class AbstractReactant(ABC):
    name: str
    type: ReactantType

    @abstractmethod
    def parameters(self) -> list[Parameter]:
        return []

    @classmethod
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> "AbstractReactant":
        # ``cls`` is unused: concrete subclass dispatch is performed based on
        # ``raw['type']``. ``@classmethod`` is kept (instead of
        # ``@staticmethod``) so that subclass ``from_dict`` methods can be
        # typed as ``@classmethod`` + ``@override`` without triggering a
        # method-override-compatibility error from the type checker.
        _ = cls
        reactant_type = cast(object, ReactantType(_require_str(raw.get("type"), "reactant.type")))
        match reactant_type:
            case ReactantType.MINERAL:
                return MineralReactant.from_dict(raw, name)
            case ReactantType.AQUEOUS:
                return AqueousReactant.from_dict(raw, name)
            case ReactantType.GAS:
                return GasReactant.from_dict(raw, name)
            case ReactantType.FIXED_GAS:
                return FixedGasReactant.from_dict(raw, name)
            case ReactantType.SPECIAL:
                return SpecialReactant.from_dict(raw, name)
            case ReactantType.ELEMENT:
                return ElementReactant.from_dict(raw, name)
            case ReactantType.SOLID_SOLUTION:
                return SolidSolutionReactant.from_dict(raw, name)
            case ReactantType.GLASS:
                return GlassReactant.from_dict(raw, name)
            case _:
                raise EleanorException(f'unexpected reactant type "{reactant_type}"')

    @abstractmethod
    def volume(self) -> np.float64:
        raise NotImplementedError


@dataclass
class TitratedReactant(AbstractReactant):
    amount: Parameter
    titration_rate: Parameter

    @override
    def parameters(self) -> list[Parameter]:
        return [self.amount, self.titration_rate]

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> "TitratedReactant":
        if name is None:
            name = raw.get("name")
        if not isinstance(name, str):
            raise EleanorException("reactant name must be a string")

        reactant_type = ReactantType(_require_str(raw.get("type"), "reactant.type"))
        amount = Parameter.load(raw.get("amount"), "amount")
        titration_rate = Parameter.load(raw.get("titration_rate", 1.0), "titration_rate")

        return cls(name, reactant_type, amount, titration_rate)

    @override
    def volume(self) -> np.float64:
        return self.amount.volume() * self.titration_rate.volume()


_ = AbstractReactant.register(TitratedReactant)


@dataclass
class MineralReactant(TitratedReactant):
    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> "MineralReactant":
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.MINERAL:
            raise EleanorException(f'cannot create a mineral reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


_ = TitratedReactant.register(MineralReactant)


@dataclass
class AqueousReactant(TitratedReactant):
    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> "AqueousReactant":
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.AQUEOUS:
            raise EleanorException(f'cannot create an aqueous reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


_ = TitratedReactant.register(AqueousReactant)


@dataclass
class GasReactant(TitratedReactant):
    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> "GasReactant":
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.GAS:
            raise EleanorException(f'cannot create a gas reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


_ = TitratedReactant.register(GasReactant)


@dataclass
class FixedGasReactant(AbstractReactant):
    amount: Parameter
    fugacity: Parameter

    @override
    def parameters(self) -> list[Parameter]:
        return [self.amount, self.fugacity]

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> "FixedGasReactant":
        if name is None:
            name = raw.get("name")
        if not isinstance(name, str):
            raise EleanorException("reactant name must be a string")

        reactant_type = ReactantType(_require_str(raw.get("type"), "reactant.type"))
        if reactant_type != ReactantType.FIXED_GAS:
            raise EleanorException(f'cannot create a fixed gas reactant from config of type "{reactant_type}"')

        amount = Parameter.load(raw.get("amount"), "amount")
        fugacity = Parameter.load(raw.get("fugacity"), "fugacity")

        return cls(name, reactant_type, amount, fugacity)

    @override
    def volume(self) -> np.float64:
        return self.amount.volume() * self.fugacity.volume()


_ = AbstractReactant.register(FixedGasReactant)


@dataclass
class SpecialReactant(TitratedReactant):
    composition: dict[str, int]

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> "SpecialReactant":
        composition: dict[str, int] = _require_dict(raw.get("composition"), "special reactant composition")

        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.SPECIAL:
            raise EleanorException(f'cannot create a special reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate, composition)


_ = TitratedReactant.register(SpecialReactant)


@dataclass
class ElementReactant(TitratedReactant):
    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> "ElementReactant":
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.ELEMENT:
            raise EleanorException(f'cannot create a element reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


_ = TitratedReactant.register(ElementReactant)


@dataclass
class SolidSolutionReactant(TitratedReactant):
    end_members: dict[str, Parameter]

    @override
    def parameters(self) -> list[Parameter]:
        return [*super().parameters(), *self.end_members.values()]

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> "SolidSolutionReactant":
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.SOLID_SOLUTION:
            raise EleanorException(f'cannot create a solid solution reactant from config of type "{base.type}"')

        typed_end_members: dict[str, ParameterSource] = _require_dict(
            raw.get("end_members"),
            "solid solution end_members",
        )

        for end_member, raw_param in typed_end_members.items():
            if isinstance(raw_param, list):
                raise EleanorException(
                    f'solid solution "{base.name}" end member "{end_member}" has a non-value parameter; list parameters are not supported yet'
                )
            elif isinstance(raw_param, dict):
                raise EleanorException(
                    f'solid solution "{base.name}" end member "{end_member}" has a non-value parameter; range parameters are not supported yet'
                )

        end_members: dict[str, Parameter] = {
            str(end_member): Parameter.load(param, "fraction") for end_member, param in typed_end_members.items()
        }

        fraction = 0.0
        for em_name, param in end_members.items():
            if not isinstance(param, ValueParameter):
                raise EleanorException(
                    f'solid solution "{base.name}" end member "{em_name}" has a non-value parameter; list and range parameters are not supported yet'
                )
            elif 1.0 < param.value or param.value < 0:
                raise EleanorException(
                    f'solid solution "{base.name}" end member "{em_name}" has a value {param.value}; must be between 0 and 1 inclusive'
                )
            fraction += param.value

        if fraction != 1.0:
            raise EleanorException(
                f'solid solution "{base.name}" end member fractions sum to {fraction}; must sum to 1.0'
            )

        return cls(base.name, base.type, base.amount, base.titration_rate, end_members)

    @override
    def volume(self) -> np.float64:
        volume = super(SolidSolutionReactant, self).volume()
        volume += mapreduce(lambda em: em.volume(), operator.mul, self.end_members.values(), 1.0)
        return volume


_ = TitratedReactant.register(SolidSolutionReactant)


@dataclass
class GlassReactantOxide(object):
    name: str
    composition: dict[str, int]
    fraction: np.float64
    relative_rate: Parameter

    @classmethod
    def from_dict(cls, raw: GlassOxideRaw, name: str | None = None) -> "GlassReactantOxide":
        if name is None:
            name = raw.get("name")
        if not isinstance(name, str):
            raise EleanorException("oxide name must be a string")

        composition: dict[str, int] = _require_dict(
            raw.get("composition"),
            f'oxide "{name}" composition specification',
        )
        fraction = _require_float(raw.get("fraction"), f'oxide "{name}" fraction specification')

        if not (0.0 < fraction and fraction < 1.0):
            raise EleanorException(f'oxide "{name}" has a value {fraction}; must be between 0 and 1 exclusive')

        relative_rate = Parameter.load(raw.get("relative_rate", 1.0), name="relative_rate")

        return cls(name, composition, fraction, relative_rate)


@dataclass
class GlassReactant(TitratedReactant):
    oxides: dict[str, GlassReactantOxide]

    @override
    def parameters(self) -> list[Parameter]:
        params = super().parameters()
        for oxide in self.oxides.values():
            params.append(oxide.relative_rate)
        return params

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> "GlassReactant":
        typed_oxides: dict[str, GlassOxideRaw] = _require_dict(raw.get("oxides"), "glass oxides")

        oxides: dict[str, GlassReactantOxide] = {
            oxide: GlassReactantOxide.from_dict(data, oxide) for oxide, data in typed_oxides.items()
        }

        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.GLASS:
            raise EleanorException(f'cannot create a glass reactant from config of type "{base.type}"')

        if len(oxides) == 0:
            raise EleanorException(f'glass "{base.name}" has no oxides; consider removing it')
        elif len(oxides) == 1:
            raise EleanorException(
                f'glass "{base.name}" has only one oxide; consider replacing it with a special reactant'
            )

        fraction = mapreduce(lambda o: o.fraction, operator.add, oxides.values(), 0.0)
        if fraction != 1.0:
            raise EleanorException(f'glass "{base.name}" oxide fractions sum to {fraction}; must sum to 1.0')

        return cls(base.name, base.type, base.amount, base.titration_rate, oxides)


Reactant = (
    MineralReactant
    | AqueousReactant
    | GasReactant
    | FixedGasReactant
    | SpecialReactant
    | ElementReactant
    | SolidSolutionReactant
    | GlassReactant
)
