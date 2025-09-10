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
        if reactant_type == ReactantType.MINERAL:
            return MineralReactant.from_dict(raw, name)
        elif reactant_type == ReactantType.AQUEOUS:
            return AqueousReactant.from_dict(raw, name)
        elif reactant_type == ReactantType.GAS:
            return GasReactant.from_dict(raw, name)
        elif reactant_type == ReactantType.FIXED_GAS:
            return FixedGasReactant.from_dict(raw, name)
        elif reactant_type == ReactantType.SPECIAL:
            return SpecialReactant.from_dict(raw, name)
        elif reactant_type == ReactantType.ELEMENT:
            return ElementReactant.from_dict(raw, name)
        elif reactant_type == ReactantType.SOLID_SOLUTION:
            return SolidSolutionReactant.from_dict(raw, name)

        raise EleanorException(f'unexpected reactant type "{reactant_type}"')


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
        titration_rate = Parameter.load(raw['titration_rate'], 'titration_rate')

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
        volume += mapreduce(lambda em: em.volume(), operator.mul, self.end_members.values())
        return volume


TitratedReactant.register(SpecialReactant)

Reactant = MineralReactant | AqueousReactant | GasReactant | FixedGasReactant | SpecialReactant | ElementReactant
