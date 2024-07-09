from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from ..exceptions import EleanorParserException
from ..typing import Number, Optional
from .parameter import Parameter


class ReactantType(StrEnum):
    MINERAL = 'mineral'
    GAS = 'gas'
    FIXED_GAS = 'fixed gas'
    SPECIAL = 'special'
    ELEMENT = 'element'


@dataclass
class AbstractReactant(ABC):
    name: str
    type: ReactantType

    @property
    def parameters(self) -> list[Parameter]:
        return []

    @property
    @abstractmethod
    def is_fully_specified(self) -> bool:
        return False

    @abstractmethod
    def to_row(self) -> dict[str, Number]:
        pass

    @staticmethod
    def from_dict(raw: dict, name: Optional[str] = None):
        reactant_type = ReactantType(raw['type'])
        if reactant_type == ReactantType.MINERAL:
            return MineralReactant.from_dict(raw, name)
        elif reactant_type == ReactantType.GAS:
            return GasReactant.from_dict(raw, name)
        elif reactant_type == ReactantType.FIXED_GAS:
            return FixedGasReactant.from_dict(raw, name)
        elif reactant_type == ReactantType.SPECIAL:
            return SpecialReactant.from_dict(raw, name)
        elif reactant_type == ReactantType.ELEMENT:
            return ElementReactant.from_dict(raw, name)

        raise EleanorParserException(f'unexpected reactant type "{reactant_type}"')


@dataclass
class TitratedReactant(AbstractReactant):
    amount: Parameter
    titration_rate: Parameter

    @property
    def is_fully_specified(self) -> bool:
        return self.amount.is_fully_specified and self.titration_rate.is_fully_specified

    @property
    def parameters(self) -> list[Parameter]:
        return [self.amount, self.titration_rate]

    def to_row(self) -> dict[str, Number]:
        d = self.amount.to_row()
        d.update(self.titration_rate.to_row())
        for key in list(d.keys()):
            d[f'{self.name}_{key}'] = d.pop(key)
        return d

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        if name is None:
            name = raw['name']

        reactant_type = ReactantType(raw['type'])
        amount = Parameter.from_dict(raw['amount'], 'amount')
        titration_rate = Parameter.from_dict(raw['titration_rate'], 'titration_rate')

        return cls(name, reactant_type, amount, titration_rate)


AbstractReactant.register(TitratedReactant)


@dataclass
class MineralReactant(TitratedReactant):

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.MINERAL:
            raise EleanorParserException(f'cannot create a mineral reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


TitratedReactant.register(MineralReactant)


@dataclass
class GasReactant(TitratedReactant):

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.GAS:
            raise EleanorParserException(f'cannot create a gas reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


TitratedReactant.register(GasReactant)


@dataclass
class FixedGasReactant(AbstractReactant):
    amount: Parameter
    fugacity: Parameter

    @property
    def parameters(self) -> list[Parameter]:
        return [self.amount, self.fugacity]

    @property
    def is_fully_specified(self) -> bool:
        return self.amount.is_fully_specified and self.fugacity.is_fully_specified

    def to_row(self) -> dict[str, Number]:
        d = self.amount.to_row()
        d.update(self.fugacity.to_row())
        for key in list(d.keys()):
            d[f'{self.name}_{key}'] = d.pop(key)
        return d

    @staticmethod
    def from_dict(raw: dict, name: Optional[str] = None):
        if name is None:
            name = raw['name']

        reactant_type = ReactantType(raw['type'])
        if reactant_type != ReactantType.FIXED_GAS:
            raise EleanorParserException(f'cannot create a fixed gas reactant from config of type "{reactant_type}"')

        amount = Parameter.from_dict(raw['amount'], 'amount')
        fugacity = Parameter.from_dict(raw['fugacity'], 'fugacity')

        return FixedGasReactant(name, reactant_type, amount, fugacity)


AbstractReactant.register(FixedGasReactant)


@dataclass
class SpecialReactant(TitratedReactant):
    composition: dict[str, int]

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        composition = raw['composition']
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.SPECIAL:
            raise EleanorParserException(f'cannot create a special reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate, composition)


TitratedReactant.register(SpecialReactant)


@dataclass
class ElementReactant(TitratedReactant):

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.ELEMENT:
            raise EleanorParserException(f'cannot create a element reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


TitratedReactant.register(ElementReactant)

Reactant = MineralReactant | GasReactant | FixedGasReactant | SpecialReactant | ElementReactant
