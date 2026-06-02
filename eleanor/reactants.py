import operator
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast, override

import numpy as np

from eleanor.exceptions import EleanorException
from eleanor.parameters import Parameter, ParameterOrSource, ParameterSource, ValueParameter, load_parameter
from eleanor.util import mapreduce, require, require_dict, require_float, require_str


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


class ReactantType(StrEnum):
    MINERAL = "mineral"
    GAS = "gas"
    FIXED_GAS = "fixed gas"
    SPECIAL = "special"
    ELEMENT = "element"
    SOLID_SOLUTION = "solid solution"
    AQUEOUS = "aqueous"
    COMBINED = "combined"


@dataclass(kw_only=True)
class AbstractReactant(ABC):
    name: str
    type: ReactantType

    def __post_init__(self):
        if self.name == "":
            raise EleanorException("reactant name is empty")

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
        reactant_type = cast(object, ReactantType(require_str(raw.get("type"), "reactant.type")))
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


@dataclass(init=False)
class TitratedReactant(AbstractReactant):
    amount: Parameter
    titration_rate: Parameter

    def __init__(
        self,
        *,
        name: str,
        type: ReactantType,
        amount: ParameterOrSource,
        titration_rate: ParameterOrSource | None = None,
    ):
        super().__init__(name=name, type=type)
        self.amount = load_parameter(amount)
        self.titration_rate = load_parameter(1.0 if titration_rate is None else titration_rate)

    @override
    def parameters(self) -> list[Parameter]:
        return [self.amount, self.titration_rate]

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> Self:
        if name is None:
            name = raw.get("name")
        if not isinstance(name, str):
            raise EleanorException("reactant name must be a string")

        reactant_type = ReactantType(require_str(raw.get("type"), "reactant.type"))
        amount = require(raw.get("amount"), "reactant.amount")
        titration_rate = raw.get("titration_rate", 1.0)

        return cls(name=name, type=reactant_type, amount=amount, titration_rate=titration_rate)

    @override
    def volume(self) -> np.float64:
        return self.amount.volume() * self.titration_rate.volume()


_ = AbstractReactant.register(TitratedReactant)


@dataclass(init=False)
class MineralReactant(TitratedReactant):
    def __init__(self, *, name: str, amount: ParameterOrSource, titration_rate: ParameterOrSource | None = None):
        super().__init__(name=name, type=ReactantType.MINERAL, amount=amount, titration_rate=titration_rate)

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> Self:
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.MINERAL:
            raise EleanorException(f'cannot create a mineral reactant from config of type "{base.type}"')
        return cls(name=base.name, amount=base.amount, titration_rate=base.titration_rate)


_ = TitratedReactant.register(MineralReactant)


@dataclass(init=False)
class AqueousReactant(TitratedReactant):
    def __init__(self, *, name: str, amount: ParameterOrSource, titration_rate: ParameterOrSource | None = None):
        super().__init__(name=name, type=ReactantType.AQUEOUS, amount=amount, titration_rate=titration_rate)

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> Self:
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.AQUEOUS:
            raise EleanorException(f'cannot create an aqueous reactant from config of type "{base.type}"')
        return cls(name=base.name, amount=base.amount, titration_rate=base.titration_rate)


_ = TitratedReactant.register(AqueousReactant)


@dataclass(init=False)
class GasReactant(TitratedReactant):
    def __init__(self, *, name: str, amount: ParameterOrSource, titration_rate: ParameterOrSource | None = None):
        super().__init__(name=name, type=ReactantType.GAS, amount=amount, titration_rate=titration_rate)

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> Self:
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.GAS:
            raise EleanorException(f'cannot create a gas reactant from config of type "{base.type}"')
        return cls(name=base.name, amount=base.amount, titration_rate=base.titration_rate)


_ = TitratedReactant.register(GasReactant)


@dataclass(init=False)
class FixedGasReactant(AbstractReactant):
    amount: Parameter
    fugacity: Parameter

    def __init__(self, *, name: str, amount: ParameterOrSource, fugacity: ParameterOrSource):
        super().__init__(name=name, type=ReactantType.FIXED_GAS)
        self.amount = load_parameter(amount)
        self.fugacity = load_parameter(fugacity)

    @override
    def parameters(self) -> list[Parameter]:
        return [self.amount, self.fugacity]

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> Self:
        if name is None:
            name = raw.get("name")
        if not isinstance(name, str):
            raise EleanorException("reactant name must be a string")

        reactant_type = ReactantType(require_str(raw.get("type"), "reactant.type"))
        if reactant_type != ReactantType.FIXED_GAS:
            raise EleanorException(f'cannot create a fixed gas reactant from config of type "{reactant_type}"')

        amount = require(raw.get("amount"), "reactant.amount")
        fugacity = require(raw.get("fugacity"), "reactant.fugacity")

        return cls(name=name, amount=amount, fugacity=fugacity)

    @override
    def volume(self) -> np.float64:
        return self.amount.volume() * self.fugacity.volume()


_ = AbstractReactant.register(FixedGasReactant)


@dataclass(init=False)
class SpecialReactant(TitratedReactant):
    composition: dict[str, int]

    def __init__(
        self,
        *,
        name: str,
        amount: ParameterOrSource,
        titration_rate: ParameterOrSource | None = None,
        composition: dict[str, int],
    ):
        super().__init__(name=name, type=ReactantType.SPECIAL, amount=amount, titration_rate=titration_rate)
        self.composition = composition
        if len(self.composition) == 0:
            raise EleanorException(f"special reactant {self.name} has empty composition")

        for k, v in self.composition.items():
            if v <= 0:
                raise EleanorException(f"special reactant {self.name} has invalid stoichiometry ({v}) for element {k}")

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> Self:
        composition: dict[str, int] = require_dict(raw.get("composition"), "special reactant composition")

        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.SPECIAL:
            raise EleanorException(f'cannot create a special reactant from config of type "{base.type}"')

        return cls(name=base.name, amount=base.amount, titration_rate=base.titration_rate, composition=composition)


_ = TitratedReactant.register(SpecialReactant)


@dataclass(init=False)
class ElementReactant(TitratedReactant):
    def __init__(self, *, name: str, amount: ParameterOrSource, titration_rate: ParameterOrSource | None = None):
        super().__init__(name=name, type=ReactantType.ELEMENT, amount=amount, titration_rate=titration_rate)

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> Self:
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.ELEMENT:
            raise EleanorException(f'cannot create a element reactant from config of type "{base.type}"')
        return cls(name=base.name, amount=base.amount, titration_rate=base.titration_rate)


_ = TitratedReactant.register(ElementReactant)


@dataclass(init=False)
class SolidSolutionReactant(TitratedReactant):
    end_members: dict[str, Parameter]

    def __init__(
        self,
        *,
        name: str,
        amount: ParameterOrSource,
        titration_rate: ParameterOrSource | None = None,
        end_members: Mapping[str, ParameterOrSource],
    ):
        super().__init__(name=name, type=ReactantType.SOLID_SOLUTION, amount=amount, titration_rate=titration_rate)
        self.end_members = {k: load_parameter(v) for k, v in end_members.items()}
        fraction = 0.0
        for em_name, param in self.end_members.items():
            if not isinstance(param, ValueParameter):
                raise EleanorException(
                    f'solid solution "{self.name}" end member "{em_name}" has a non-value parameter; list and range parameters are not supported yet'
                )
            elif 1.0 < param.value or param.value < 0:
                raise EleanorException(
                    f'solid solution "{self.name}" end member "{em_name}" has a value {param.value}; must be between 0 and 1 inclusive'
                )
            fraction += param.value

        if fraction != 1.0:
            raise EleanorException(
                f'solid solution "{self.name}" end member fractions sum to {fraction}; must sum to 1.0'
            )

    @override
    def parameters(self) -> list[Parameter]:
        return [*super().parameters(), *self.end_members.values()]

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> Self:
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.SOLID_SOLUTION:
            raise EleanorException(f'cannot create a solid solution reactant from config of type "{base.type}"')

        end_members: dict[str, ParameterSource] = require_dict(
            raw.get("end_members"),
            "solid solution end_members",
        )

        return cls(name=base.name, amount=base.amount, titration_rate=base.titration_rate, end_members=end_members)

    @override
    def volume(self) -> np.float64:
        volume = super(SolidSolutionReactant, self).volume()
        volume += mapreduce(lambda em: em.volume(), operator.mul, self.end_members.values(), 1.0)
        return volume


_ = TitratedReactant.register(SolidSolutionReactant)


@dataclass(init=False)
class CombinedReactantComponent:
    """One component of a CombinedReactant.

    ``fraction`` and ``relative_rate`` drive decomposition math in the PointBuilder:
    ``component_log_moles = log10(fraction) + parent_log_moles``.
    When ``relative_rate`` is a ``Parameter``, the component's absolute titration
    rate is ``parent_titration_rate * relative_rate``. When ``relative_rate`` is
    ``None``, it falls back to ``parent_titration_rate * fraction``.
    """

    name: str
    type: ReactantType
    fraction: np.float64
    relative_rate: Parameter | None
    composition: dict[str, int] | None = None
    end_members: dict[str, Parameter] | None = None

    def __init__(
        self,
        *,
        name: str,
        type: ReactantType,
        fraction: np.float64,
        relative_rate: ParameterOrSource | None,
        composition: dict[str, int] | None = None,
        end_members: Mapping[str, ParameterOrSource] | None = None,
    ):
        self.name = name
        self.type = type
        self.fraction = fraction
        self.relative_rate = None if relative_rate is None else load_parameter(relative_rate)
        self.composition = composition
        self.end_members = None if end_members is None else {k: load_parameter(v) for k, v in end_members.items()}

        match self.type:
            case ReactantType.SPECIAL:
                if self.composition is None:
                    raise EleanorException(f'special combined component "{self.name}" must have a composition')
                if self.end_members is not None:
                    raise EleanorException(f'special combined component "{self.name}" cannot have end_members')

                if len(self.composition) == 0:
                    raise EleanorException(f"special combined component {self.name} has empty composition")

                for k, v in self.composition.items():
                    if v <= 0:
                        raise EleanorException(
                            f"special reactant {self.name} has invalid stoichiometry ({v}) for element {k}"
                        )

            case ReactantType.SOLID_SOLUTION:
                if self.composition is not None:
                    raise EleanorException(f'solid solution combined component "{self.name}" cannot have a composition')
                if self.end_members is None or len(self.end_members) == 0:
                    raise EleanorException(f'solid solution combined component "{self.name}" must have end_members')

                em_fraction = 0.0
                for em_name, param in self.end_members.items():
                    if not isinstance(param, ValueParameter):
                        raise EleanorException(
                            f'combined component "{self.name}" end member "{em_name}" '
                            + "has a non-value parameter; list and range parameters are not supported yet"
                        )
                    elif 1.0 < param.value or param.value < 0:
                        raise EleanorException(
                            f'combined component "{self.name}" end member "{em_name}" has a value {param.value}; '
                            + "must be between 0 and 1 inclusive"
                        )
                    em_fraction += param.value

                if em_fraction != 1.0:
                    raise EleanorException(
                        f'combined component "{self.name}" end member fractions sum to {em_fraction}; '
                        + "must sum to 1.0"
                    )
            case _:
                if self.composition is not None:
                    raise EleanorException(
                        f'"{self.type.value}" combined component "{self.name}" cannot have a composition'
                    )
                if self.end_members is not None:
                    raise EleanorException(
                        f'"{self.type.value}" combined component "{self.name}" cannot have end_members'
                    )

    def parameters(self) -> list[Parameter]:
        params: list[Parameter] = []
        if self.relative_rate is not None:
            params.append(self.relative_rate)
        if self.end_members is not None:
            params.extend(self.end_members.values())
        return params

    @classmethod
    def from_dict(cls, raw: CombinedComponentRaw, name: str | None = None) -> Self:
        if name is None:
            name = raw.get("name")
        if not isinstance(name, str):
            raise EleanorException("combined component name must be a string")

        component_type = ReactantType(require_str(raw.get("type"), f'combined component "{name}".type'))
        if component_type == ReactantType.FIXED_GAS or component_type == ReactantType.COMBINED:
            raise EleanorException(
                f'combined component "{name}" type "{component_type}" is not supported; '
                + "expected a titrated reactant type"
            )

        fraction = require_float(raw.get("fraction"), f'combined component "{name}" fraction specification')

        if not (0.0 < fraction and fraction < 1.0):
            raise EleanorException(
                f'combined component "{name}" has a value {fraction}; must be between 0 and 1 exclusive'
            )

        relative_rate = raw.get("relative_rate")
        composition: dict[str, int] | None = None
        end_members: dict[str, ParameterSource] | None = None

        if component_type == ReactantType.SPECIAL:
            composition = require_dict(
                raw.get("composition"),
                f'combined component "{name}" composition specification',
            )
        elif component_type == ReactantType.SOLID_SOLUTION:
            end_members = require_dict(
                raw.get("end_members"),
                f'combined component "{name}" end_members',
            )

        return cls(
            name=name,
            type=component_type,
            fraction=fraction,
            relative_rate=relative_rate,
            composition=composition,
            end_members=end_members,
        )


@dataclass(init=False)
class CombinedReactant(TitratedReactant):
    components: dict[str, CombinedReactantComponent]

    def __init__(
        self,
        *,
        name: str,
        amount: ParameterOrSource,
        titration_rate: ParameterOrSource | None = None,
        components: dict[str, CombinedReactantComponent],
    ):
        super().__init__(name=name, type=ReactantType.COMBINED, amount=amount, titration_rate=titration_rate)
        self.components = components
        if len(components) == 0:
            raise EleanorException(f'combined reactant "{self.name}" has no components; consider removing it')
        elif len(components) == 1:
            raise EleanorException(
                f'combined reactant "{self.name}" has only one component; consider replacing it with that standalone reactant'
            )

        fraction = mapreduce(lambda c: c.fraction, operator.add, components.values(), 0.0)
        if fraction != 1.0:
            raise EleanorException(
                f'combined reactant "{self.name}" component fractions sum to {fraction}; must sum to 1.0'
            )

    @override
    def parameters(self) -> list[Parameter]:
        params = super().parameters()
        for component in self.components.values():
            params.extend(component.parameters())
        return params

    @classmethod
    @override
    def from_dict(cls, raw: ReactantRaw, name: str | None = None) -> Self:
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.COMBINED:
            raise EleanorException(f'cannot create a combined reactant from config of type "{base.type}"')
        typed_components: dict[str, CombinedComponentRaw] = require_dict(
            raw.get("components"),
            "combined reactant components",
        )

        components: dict[str, CombinedReactantComponent] = {
            component_name: CombinedReactantComponent.from_dict(data, component_name)
            for component_name, data in typed_components.items()
        }

        return cls(name=base.name, amount=base.amount, titration_rate=base.titration_rate, components=components)

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
