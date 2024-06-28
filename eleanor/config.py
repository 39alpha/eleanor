import datetime
import json
import os.path
import tomllib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import yaml

from .exceptions import EleanorException, EleanorParserException
from .hanger.tool_room import NumberFormat
from .kernel.interface import Config as KernelConfig
from .typing import Any, Callable, Number, Optional, Self


def convert_to_number(value: Number | str, types: Optional[list[type]] = None):
    if types is None:
        return convert_to_number(value, [int, np.integer, float, np.floating])
    elif len(types) == 0:
        raise EleanorParserException('could not convert string to numeric type')
    elif isinstance(value, tuple(types)):
        return value

    try:
        t, *types = types
        if t is np.floating:
            return np.float64(value)
        elif t is np.integer:
            return np.int64(value)
        else:
            return t(value)
    except ValueError:
        return convert_to_number(value, types)


def is_list_of(value: Any, types: type | tuple, allowNone: bool = False) -> bool:
    if allowNone:
        if isinstance(types, tuple):
            types = (*types, type(None))
        else:
            types = (types, type(None))

    if value is None:
        return allowNone

    return isinstance(value, list) and all(isinstance(x, types) for x in value)


def parse_date(date: str) -> datetime.date | datetime.datetime:
    try:
        return datetime.date.fromisoformat(date)
    except ValueError:
        try:
            return datetime.datetime.fromisoformat(date)
        except ValueError:
            raise EleanorParserException(f'failed to parse date "{date}"')


@dataclass
class Parameter(object):
    name: str
    type: Optional[str]
    unit: str
    min: Optional[Number]
    max: Optional[Number]
    value: Optional[Number]
    values: Optional[list[Number]]

    @property
    def is_fully_specified(self) -> bool:
        return self.value is not None and all(x is None for x in [self.min, self.max, self.values])

    def __init__(self,
                 name: str,
                 unit: str,
                 type: Optional[str] = None,
                 min: Optional[Number] = None,
                 max: Optional[Number] = None,
                 value: Optional[Number] = None,
                 values: Optional[list[Number]] = None):

        if min is None and max is None and value is None and values is None:
            raise EleanorParserException(
                f'must provide min and max, or value or values in parameter configuration {name}')
        elif min is not None or max is not None:
            if min is None or max is None:
                raise EleanorParserException(
                    f'if min or max is provided, then the other is required in parameter configuration {name}')
            elif value is not None or values is not None:
                raise EleanorParserException(
                    f'must provide min and max, or value or values in parameter configuration {name}')
            elif min > max:
                raise EleanorParserException(f'min and max values are out of order in parameter configuration {name}')
        elif value is not None and values is not None:
            raise EleanorParserException(
                f'must provide min and max, or value or values in parameter configuration {name}')

        if min is not None and min == max:
            value, min, max = min, None, None
        elif values is not None:
            values = list(set(values))
            if len(values) == 1:
                value = values[0]
                values = None

        self.name = name
        self.type = type
        self.unit = unit
        self.min = min
        self.max = max
        self.value = value
        self.values = values

    @property
    def range(self) -> tuple[Number, Number]:
        if self.value is not None:
            return (self.value, self.value)
        elif self.values is not None:
            return (self.values[0], self.values[-1])
        elif self.min is not None and self.max is not None:
            return (self.min, self.max)
        else:
            raise EleanorException(f'unexpected Parameter state: {self}')

    def fix(self, value: Number) -> Self:
        self.value = value
        self.min = None
        self.max = None
        self.values = None

        return self

    def mean(self) -> Self:
        if self.value is not None:
            value = self.value
        elif self.values is not None:
            value = np.mean(np.asarray(self.values))
        elif self.min is not None and self.max is not None:
            value = 0.5 * (self.min + self.max)
        else:
            raise EleanorException(f'unexpected Parameter state: {self}')

        return type(self)(name=self.name, unit=self.unit, type=self.type, value=value)

    def format(self, *args, formatter=NumberFormat.SCIENTIFIC, **kwargs):
        # TODO: Handle units

        if self.value is not None:
            return formatter.fmt(self.value, *args, **kwargs)
        elif self.values is not None:
            return '[' + ', '.join([formatter.fmt(v, *args, **kwargs) for v in self.values]) + ']'
        elif self.min is not None and self.max is not None:
            return f'({formatter.fmt(self.min, *args, **kwargs)}, {formatter.fmt(self.max, *args, **kwargs)})'

        raise EleanorException(f'unexpected Parameter state: {self}')

    @staticmethod
    def from_dict(raw: dict, name: Optional[str] = None):
        if name is None:
            name = raw['name']

        if not isinstance(name, str):
            raise EleanorParserException(f'parameter {name} name must be a string')

        param_type = raw.get('type')
        if not isinstance(param_type, (str, type(None))):
            raise EleanorParserException(f'parameter {name} type must be a string')

        unit = raw['unit']
        if not isinstance(unit, str):
            raise EleanorParserException(f'parameter {name} unit must be a string')

        min = raw.get('min')
        if min is not None:
            min = convert_to_number(min)

        max = raw.get('max')
        if max is not None:
            max = convert_to_number(min)

        value = raw.get('value')
        if value is not None:
            value = convert_to_number(value)

        values = raw.get('values')
        if values is not None:
            if not isinstance(values, list):
                raise EleanorParserException(f'parameter {name} values must be a list')
            values = [convert_to_number(value) for value in values]

        return Parameter(name, unit, param_type, min, max, value, values)


class ReactantType(StrEnum):
    MINERAL = 'mineral'
    GAS = 'gas'
    FIXED_GAS = 'fixed gas'
    SPECIAL = 'special'
    ELEMENT = 'element'


@dataclass
class AbstractReactant(ABC):

    @property
    @abstractmethod
    def is_fully_specified(self) -> bool:
        return False

    @abstractmethod
    def mean(self) -> Self:
        return self

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
    name: str
    type: ReactantType
    amount: Parameter
    titration_rate: Parameter

    @property
    def is_fully_specified(self) -> bool:
        return self.amount.is_fully_specified and self.titration_rate.is_fully_specified

    def mean(self) -> Self:
        return type(self)(self.name, self.type, self.amount.mean(), self.titration_rate.mean())

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


@dataclass
class GasReactant(TitratedReactant):

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.GAS:
            raise EleanorParserException(f'cannot create a gas reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


@dataclass
class FixedGasReactant(AbstractReactant):
    name: str
    type: ReactantType
    amount: Parameter
    fugacity: Parameter

    @property
    def is_fully_specified(self) -> bool:
        return self.amount.is_fully_specified and self.fugacity.is_fully_specified

    def mean(self) -> Self:
        return type(self)(self.name, self.type, self.amount, self.fugacity)

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


@dataclass
class ElementReactant(TitratedReactant):

    @classmethod
    def from_dict(cls, raw: dict, name: Optional[str] = None):
        base = TitratedReactant.from_dict(raw, name)
        if base.type != ReactantType.ELEMENT:
            raise EleanorParserException(f'cannot create a element reactant from config of type "{base.type}"')
        return cls(base.name, base.type, base.amount, base.titration_rate)


Reactant = MineralReactant | GasReactant | FixedGasReactant | SpecialReactant | ElementReactant


@dataclass(init=False)
class Suppression(object):
    name: Optional[str]
    type: Optional[str]
    exceptions: list[str]

    def __init__(self, name: Optional[str], type: Optional[str], exceptions: list[str]):
        if name is None and type is None:
            raise EleanorParserException(f'suppression must have a name or a type')

        self.name = name
        self.type = type
        self.exceptions = exceptions

    @staticmethod
    def from_dict(raw: dict, name: Optional[str] = None):
        if name is None:
            name = raw.get('name')

        if not isinstance(name, (str, type(None))):
            raise EleanorParserException(f'suppression name must be a string')

        suppression_type = raw.get('type')
        if not isinstance(suppression_type, (str, type(None))):
            raise EleanorParserException(f'supression type must be a string')

        exceptions = raw.get('except', [])
        if not is_list_of(exceptions, (str), allowNone=False):
            raise EleanorParserException(f'suppression exceptions must be a list of int or float')

        return Suppression(name, suppression_type, exceptions)


@dataclass
class Constraints(object):
    temperature: Parameter
    pressure: Parameter
    elements: dict[str, Parameter]
    species: dict[str, Parameter]
    suppressions: list[Suppression]

    @property
    def is_fully_specified(self) -> bool:
        if not self.temperature.is_fully_specified:
            return False
        elif not self.pressure.is_fully_specified:
            return False
        elif not all(param.is_fully_specified for param in self.elements.values()):
            return False
        else:
            return all(param.is_fully_specified for param in self.species.values())

    def has_species(self, species: str) -> bool:
        return species in self.species

    def mean(self) -> Self:
        temperature = self.temperature.mean()
        pressure = self.pressure.mean()
        elements = {k: v.mean() for k, v in self.elements.items()}
        species = {k: v.mean() for k, v in self.species.items()}
        suppressions = [s for s in self.suppressions]

        return type(self)(temperature, pressure, elements, species, suppressions)

    @staticmethod
    def from_dict(raw: dict):
        temperature = Parameter.from_dict(raw['temperature'], 'temperature')
        pressure = Parameter.from_dict(raw['pressure'], 'pressure')
        elements = {name: Parameter.from_dict(value, name=name) for name, value in raw['elements'].items()}
        species = {name: Parameter.from_dict(value, name=name) for name, value in raw['species'].items()}
        suppressions = [
            Suppression.from_dict({}, name=value) if isinstance(value, str) else Suppression.from_dict(value)
            for value in raw.get('suppress', [])
        ]

        return Constraints(temperature, pressure, elements, species, suppressions)


@dataclass
class Problem(object):
    kernel: KernelConfig
    constraints: Constraints
    reactants: list[Reactant]

    @property
    def is_fully_specified(self):
        return self.constraints.is_fully_specified and all(reactant.is_fully_specified for reactant in self.reactants)

    def mean(self) -> Self:
        kernel = self.kernel.mean()
        constraints = self.constraints.mean()
        reactants = [r.mean() for r in self.reactants]

        return type(self)(kernel, constraints, reactants)

    def has_species_constraint(self, species: str) -> bool:
        return self.constraints.has_species(species)

    @staticmethod
    def from_dict(raw: dict):
        kernel_type = raw['kernel']['type'].lower()
        if kernel_type == 'eq36':
            # DGM: Ideally this would be done via some type of registration
            from eleanor.kernel.eq36 import Config as Eq36KernelConfig
            kernel = Eq36KernelConfig.from_dict(raw['kernel'])
        else:
            raise EleanorParserException(f'unsupported kernel type "{kernel_type}"')

        constraints = Constraints.from_dict(raw['constraints'])
        reactants = [AbstractReactant.from_dict(value, name=name) for name, value in raw.get('reactants', []).items()]

        return Problem(kernel, constraints, reactants)


@dataclass(init=False)
class Config(Problem):
    name: str
    date: datetime.date | datetime.datetime
    notes: str
    creator: str
    raw: Optional[dict]

    def __init__(self,
                 name: str,
                 date: datetime.date | datetime.datetime,
                 notes: str,
                 creator: str,
                 *args,
                 raw: Optional[dict] = None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.date = date
        self.notes = notes
        self.creator = creator
        self.raw = raw

    def to_problem(self) -> Problem:
        return Problem(self.kernel, self.constraints, self.reactants)

    def mean(self) -> Config:
        return Config.from_problem(self.name, self.date, self.notes, self.creator, self.to_problem().mean())

    @staticmethod
    def from_problem(name: str, date: datetime.date | datetime.datetime, notes: str, creator: str,
                     problem: Problem) -> Config:
        return Config(name, date, notes, creator, problem.kernel, problem.constraints, problem.reactants)

    @staticmethod
    def from_dict(raw: dict) -> Config:
        name = raw['name']
        if not isinstance(name, str):
            raise EleanorParserException('name must be a string')

        config_date = raw['date']
        if isinstance(config_date, str):
            config_date = parse_date(config_date)

        if not isinstance(config_date, (datetime.date, datetime.datetime)):
            raise EleanorParserException('date must be a date or datetime')

        notes = raw.get('notes', '')
        if not isinstance(notes, str):
            raise EleanorParserException('notes must be a string')

        creator = raw['creator']
        if not isinstance(creator, str):
            raise EleanorParserException('creator must be a string')

        problem = Problem.from_dict(raw)

        return Config.from_problem(name, config_date, notes, creator, problem)

    @staticmethod
    def from_yaml(fname: str) -> Config:
        with open(fname, 'rb') as handle:
            raw = yaml.safe_load(handle)
            return Config.from_dict(raw)

    @staticmethod
    def from_toml(fname: str) -> Config:
        with open(fname, 'rb') as handle:
            raw = tomllib.load(handle)
            return Config.from_dict(raw)

    @staticmethod
    def from_json(fname: str) -> Config:
        with open(fname, 'rb') as handle:
            raw = json.load(handle)
            return Config.from_dict(raw)

    @staticmethod
    def from_file(fname: str) -> Config:
        parsers: dict[str, Callable[[str], Config]] = {
            'yaml': Config.from_yaml,
            'toml': Config.from_toml,
            'json': Config.from_json
        }

        for filetype, func in parsers.items():
            try:
                return func(fname)
            except EleanorParserException as e:
                raise
            except Exception:
                pass

        raise EleanorParserException(f'failed to parse "{fname}" as yaml, toml or json')
