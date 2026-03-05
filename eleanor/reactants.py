import operator
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from .exceptions import EleanorException
from .parameters import Parameter, ValueParameter
from .typing import Optional
from .util import mapreduce


class ReactantType(StrEnum):
    MINERAL = 'mineral'
    GAS = 'gas'
    FIXED_GAS = 'fixed gas'
    SPECIAL = 'special'
    ELEMENT = 'element'
    SOLID_SOLUTION = 'solid solution'
    AQUEOUS = 'aqueous'
    GLASS = 'glass'


@dataclass
class AbstractReactant(ABC):
    name: str
    type: ReactantType

    @abstractmethod
    def parameters(self) -> list[Parameter]:
        return []

    @staticmethod
    def from_dict(raw: dict, name: Optional[str] = None):
        reactant_type = ReactantType(raw['type'])
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
            case _:  # pyright: ignore[reportUnnecessaryComparison]
                raise EleanorException(f'unexpected reactant type "{reactant_type}"')  # pyright: ignore[reportUnreachable]


@dataclass
class TitratedReactant(AbstractReactant):
    amount: Parameter
    titration_rate: Parameter

    def parameters(self) -> list[Parameter]:
        return [self.amount, self.titration_rate]

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        if name is None:
            name = raw['name']

        reactant_type = ReactantType(raw['type'])
        amount = Parameter.load(raw['amount'], 'amount')
        titration_rate = Parameter.load(raw.get('titration_rate', 1.0), 'titration_rate')

        return cls(name, reactant_type, amount, titration_rate)

    def volume(self) -> float:
        return self.amount.volume() * self.titration_rate.volume()


AbstractReactant.register(TitratedReactant)


@dataclass
class MineralReactant(TitratedReactant):

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.MINERAL:
            raise EleanorException(f'cannot create a mineral reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


TitratedReactant.register(MineralReactant)


@dataclass
class AqueousReactant(TitratedReactant):

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.AQUEOUS:
            raise EleanorException(f'cannot create an aqueous reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


TitratedReactant.register(AqueousReactant)


@dataclass
class GasReactant(TitratedReactant):

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.GAS:
            raise EleanorException(f'cannot create a gas reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


TitratedReactant.register(GasReactant)


@dataclass
class FixedGasReactant(AbstractReactant):
    amount: Parameter
    fugacity: Parameter

    def parameters(self) -> list[Parameter]:
        return [self.amount, self.fugacity]

    @staticmethod
    def from_dict(raw: dict, name: Optional[str] = None):
        if name is None:
            name = raw['name']

        reactant_type = ReactantType(raw['type'])
        if reactant_type != ReactantType.FIXED_GAS:
            raise EleanorException(f'cannot create a fixed gas reactant from config of type "{reactant_type}"')

        amount = Parameter.load(raw['amount'], 'amount')
        fugacity = Parameter.load(raw['fugacity'], 'fugacity')

        return FixedGasReactant(name, reactant_type, amount, fugacity)

    def volume(self) -> float:
        return self.amount.volume() * self.fugacity.volume()


AbstractReactant.register(FixedGasReactant)


@dataclass
class SpecialReactant(TitratedReactant):
    composition: dict[str, int]

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        composition = raw['composition']
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.SPECIAL:
            raise EleanorException(f'cannot create a special reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate, composition)


TitratedReactant.register(SpecialReactant)


@dataclass
class ElementReactant(TitratedReactant):

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.ELEMENT:
            raise EleanorException(f'cannot create a element reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


TitratedReactant.register(ElementReactant)


@dataclass
class SolidSolutionReactant(TitratedReactant):
    end_members: dict[str, Parameter]

    def parameters(self) -> list[Parameter]:
        return [*super().parameters(), *self.end_members.values()]

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.SOLID_SOLUTION:
            raise EleanorException(f'cannot create a solid solution reactant from config of type "{base.type}"')

        for end_member, raw_param in raw['end_members'].items():
            if isinstance(raw_param, list):
                raise EleanorException(
                    f'solid solution \"{base.name}\" end member \"{end_member}\" has a non-value parameter; list parameters are not supported yet'
                )
            elif isinstance(raw_param, dict):
                raise EleanorException(
                    f'solid solution \"{base.name}\" end member \"{end_member}\" has a non-value parameter; range parameters are not supported yet'
                )

        end_members = {
            end_member: Parameter.load(param, 'fraction')
            for end_member, param in raw['end_members'].items()
        }

        fraction = 0.0
        for name, param in end_members.items():
            if not isinstance(param, ValueParameter):
                raise EleanorException(
                    f'solid solution "{base.name}" end member "{name}" has a non-value parameter; list and range parameters are not supported yet'
                )
            elif 1.0 < param.value or param.value < 0:
                raise EleanorException(
                    f'solid solution "{base.name}" end member "{name}" has a value {param.value}; must be between 0 and 1 inclusive'
                )
            fraction += param.value

        if fraction != 1.0:
            raise EleanorException(
                f'solid solution "{base.name}" end member fractions sum to {fraction}; must sum to 1.0')

        return cls(base.name, base.type, base.amount, base.titration_rate, end_members)

    def volume(self) -> float:
        volume = super(SolidSolutionReactant, self).volume()
        volume += mapreduce(lambda em: em.volume(), operator.mul, self.end_members.values(), 1.0)
        return volume


TitratedReactant.register(SolidSolutionReactant)


@dataclass
class GlassReactantOxide(object):
    name: str
    composition: dict[str, int]
    fraction: float

    @classmethod
    def from_dict(cls, raw: dict[str, str | dict[str, int] | float], name: str | None = None):
        if name is None:
            name = str(raw['name'])

        if not isinstance(raw['composition'], dict):
            raise EleanorException(f'oxide "{name}" has an invalid composition specification; it should be a dictionary')

        composition: dict[str, int] = raw['composition']

        if not isinstance(raw['fraction'], float):
            raise EleanorException(f'oxide "{name}" has an invalid fraction specification; it should be a floating-point number')
        fraction: float = raw['fraction']

        if not (0.0 < fraction and fraction < 1.0):
            raise EleanorException(
                f'oxide "{name}" has a value {fraction}; must be between 0 and 1 exclusive'
            )

        return cls(name, composition, fraction)


@dataclass
class GlassReactant(TitratedReactant):
    oxides: dict[str, GlassReactantOxide]

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        oxides: dict[str, GlassReactantOxide] = {
            oxide: GlassReactantOxide.from_dict(data, oxide)
            for oxide, data in raw['oxides'].items()
        }

        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.GLASS:
            raise EleanorException(f'cannot create a glass reactant from config of type "{base.type}"')

        if len(oxides) == 0:
            raise EleanorException(f'glass "{base.name}" has no oxides; consider removing it')
        elif len(oxides) == 1:
            raise EleanorException(f'glass "{base.name}" has only one oxide; consider replacing it with a special reactant')

        fraction = mapreduce(lambda o: o.fraction, operator.add, oxides.values(), 0.0)
        if fraction != 1.0:
            raise EleanorException(
                f'glass "{base.name}" oxide fractions sum to {fraction}; must sum to 1.0')

        return cls(base.name, base.type, base.amount, base.titration_rate, oxides)


Reactant = MineralReactant | AqueousReactant | GasReactant | FixedGasReactant | SpecialReactant | ElementReactant | SolidSolutionReactant | GlassReactant
