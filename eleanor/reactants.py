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


class CombinedComponentRaw(TypedDict, total=False):
    """Raw schema for a single component block inside a combined reactant."""

    name: str | None
    type: str
    fraction: float | np.float64
    relative_rate: ParameterSource
    composition: dict[str, int]
    end_members: dict[str, ParameterSource]


class ReactantRaw(TypedDict, total=False):
    """Raw schema shared by every reactant variant.

    Variant-specific keys (``fugacity`` for fixed gas, ``composition`` for
    special, ``end_members`` for solid solution, ``components`` for combined) are
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
    components: dict[str, CombinedComponentRaw]


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
    COMBINED = "combined"


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
            case ReactantType.COMBINED:
                return CombinedReactant.from_dict(raw, name)
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
class CombinedReactantComponent:
    """One component of a CombinedReactant.

    ``fraction`` and ``relative_rate`` drive decomposition math in the
    Boatswain: component_log_moles = log10(fraction) + parent_log_moles,
    component_titration_rate = parent_titration_rate * relative_rate.
    """

    name: str
    type: ReactantType
    fraction: np.float64
    relative_rate: Parameter
    composition: dict[str, int] | None = None
    end_members: dict[str, Parameter] | None = None

    def parameters(self) -> list[Parameter]:
        params: list[Parameter] = [self.relative_rate]
        if self.end_members is not None:
            params.extend(self.end_members.values())
        return params

    @classmethod
    def from_dict(cls, raw: CombinedComponentRaw, name: str | None = None) -> "CombinedReactantComponent":
        if name is None:
            name = raw.get("name")
        if not isinstance(name, str):
            raise EleanorException("combined component name must be a string")

        component_type = ReactantType(_require_str(raw.get("type"), f'combined component "{name}".type'))
        if component_type == ReactantType.FIXED_GAS or component_type == ReactantType.COMBINED:
            raise EleanorException(
                f'combined component "{name}" type "{component_type}" is not supported; '
                + "expected a titrated reactant type"
            )

        fraction = _require_float(raw.get("fraction"), f'combined component "{name}" fraction specification')

        if not (0.0 < fraction and fraction < 1.0):
            raise EleanorException(
                f'combined component "{name}" has a value {fraction}; must be between 0 and 1 exclusive'
            )

        relative_rate = Parameter.load(raw.get("relative_rate", 1.0), name="relative_rate")
        composition: dict[str, int] | None = None
        end_members: dict[str, Parameter] | None = None

        if component_type == ReactantType.SPECIAL:
            composition = _require_dict(
                raw.get("composition"),
                f'combined component "{name}" composition specification',
            )
        elif component_type == ReactantType.SOLID_SOLUTION:
            typed_end_members: dict[str, ParameterSource] = _require_dict(
                raw.get("end_members"),
                f'combined component "{name}" end_members',
            )

            for end_member, raw_param in typed_end_members.items():
                if isinstance(raw_param, list):
                    raise EleanorException(
                        f'combined component "{name}" end member "{end_member}" '
                        + "has a non-value parameter; list parameters are not supported yet"
                    )
                elif isinstance(raw_param, dict):
                    raise EleanorException(
                        f'combined component "{name}" end member "{end_member}" '
                        + "has a non-value parameter; range parameters are not supported yet"
                    )

            end_members = {
                str(end_member): Parameter.load(param, "fraction") for end_member, param in typed_end_members.items()
            }

            em_fraction = 0.0
            for em_name, param in end_members.items():
                if not isinstance(param, ValueParameter):
                    raise EleanorException(
                        f'combined component "{name}" end member "{em_name}" '
                        + "has a non-value parameter; list and range parameters are not supported yet"
                    )
                elif 1.0 < param.value or param.value < 0:
                    raise EleanorException(
                        f'combined component "{name}" end member "{em_name}" has a value {param.value}; '
                        + "must be between 0 and 1 inclusive"
                    )
                em_fraction += param.value

            if em_fraction != 1.0:
                raise EleanorException(
                    f'combined component "{name}" end member fractions sum to {em_fraction}; ' + "must sum to 1.0"
                )

        return cls(name, component_type, fraction, relative_rate, composition, end_members)


@dataclass
class CombinedReactant(TitratedReactant):
    components: dict[str, CombinedReactantComponent]

    @override
    def parameters(self) -> list[Parameter]:
        params = super().parameters()
        for component in self.components.values():
            params.extend(component.parameters())
        return params

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> "CombinedReactant":
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.COMBINED:
            raise EleanorException(f'cannot create a combined reactant from config of type "{base.type}"')
        typed_components: dict[str, CombinedComponentRaw] = _require_dict(
            raw.get("components"),
            "combined reactant components",
        )

        components: dict[str, CombinedReactantComponent] = {
            component_name: CombinedReactantComponent.from_dict(data, component_name)
            for component_name, data in typed_components.items()
        }

        if len(components) == 0:
            raise EleanorException(f'combined reactant "{base.name}" has no components; consider removing it')
        elif len(components) == 1:
            raise EleanorException(
                f'combined reactant "{base.name}" has only one component; consider replacing it with that standalone reactant'
            )

        fraction = mapreduce(lambda c: c.fraction, operator.add, components.values(), 0.0)
        if fraction != 1.0:
            raise EleanorException(
                f'combined reactant "{base.name}" component fractions sum to {fraction}; must sum to 1.0'
            )

        return cls(base.name, base.type, base.amount, base.titration_rate, components)

    @override
    def volume(self) -> np.float64:
        # Mirror SolidSolutionReactant.volume(): fold each component's own
        # parameter block (relative_rate plus any nested end_members) into the
        # parent volume as a sum of products. Per-component relative_rate is
        # a first-class Parameter that may be range- or list-valued, so a
        # variable component contributes its actual volume rather than 1.
        volume = super().volume()
        for component in self.components.values():
            volume += mapreduce(lambda p: p.volume(), operator.mul, component.parameters(), 1.0)
        return volume


_ = TitratedReactant.register(CombinedReactant)


Reactant = (
    MineralReactant
    | AqueousReactant
    | GasReactant
    | FixedGasReactant
    | SpecialReactant
    | ElementReactant
    | SolidSolutionReactant
    | CombinedReactant
)
