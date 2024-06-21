import datetime
import json
import tomllib
from dataclasses import dataclass
from typing import Any, Optional

import yaml

from .exceptions import EleanorParserException


def islistof(value: Any, types: type | tuple, allowNone: bool = False) -> bool:
    if allowNone:
        if isinstance(types, tuple):
            types = (*types, type(None))
        else:
            types = (types, type(None))

    if value is None:
        return allowNone

    return isinstance(value, list) and all(isinstance(x, types) for x in value)


def parsedate(date: str) -> datetime.date | datetime.datetime:
    try:
        return datetime.date.fromisoformat(date)
    except ValueError:
        try:
            return datetime.datetime.fromisoformat(date)
        except ValueError:
            raise EleanorParserException(f'failed to parse date "{date}"')


@dataclass
class KernelConfig(object):
    type: str

    @property
    def is_fully_specified(self) -> bool:
        return True


@dataclass(init=False)
class Eq36KernelConfig(KernelConfig):
    model: str
    charge_balance: str

    def __init__(self, model: str, charge_balance: str):
        super().__init__(type='eq36')
        self.model = model
        self.charge_balance = charge_balance

    @staticmethod
    def from_dict(raw: dict):
        model = raw['model']
        if not isinstance(model, str):
            raise EleanorParserException('kernel.model must be a string')

        charge_balance = raw['charge_balance']
        if not isinstance(charge_balance, str):
            raise EleanorParserException('kernel.charge_balance must be a string')

        return Eq36KernelConfig(model, charge_balance)


@dataclass
class ParameterConfig(object):
    name: str
    type: Optional[str]
    unit: str
    min: Optional[int | float]
    max: Optional[int | float]
    value: Optional[int | float]
    values: Optional[list[int | float]]

    def fix(self, value: int | float):
        self.value = value
        self.min = None
        self.max = None
        self.values = None

    @property
    def is_fully_specified(self) -> bool:
        return self.value is not None and all(x is None for x in [self.min, self.max, self.values])

    def __init__(self, name: str, type: Optional[str], unit: str, min: Optional[int | float],
                 max: Optional[int | float], value: Optional[int | float], values: Optional[list[int | float]]):

        if min is not None or max is not None:
            if min is None or max is None:
                raise EleanorParserException(
                    f'if min or max is provided, then the other is required in parameter configuration {name}')
            elif value is not None or values is not None:
                raise EleanorParserException(
                    f'must provide min and max, or value or values in parameter configuration {name}')
        elif value is not None and values is not None:
            raise EleanorParserException(
                f'must provide min and max, or value or values in parameter configuration {name}')

        self.name = name
        self.type = type
        self.unit = unit
        self.min = min
        self.max = max
        self.value = value
        self.values = values

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
        if not isinstance(min, (int, float, type(None))):
            raise EleanorParserException(f'parameter {name} min must be an int or float')

        max = raw.get('max')
        if not isinstance(max, (int, float, type(None))):
            raise EleanorParserException(f'parameter {name} max must be an int or float')

        value = raw.get('value')
        if not isinstance(value, (int, float, type(None))):
            raise EleanorParserException(f'parameter {name} value must be an int or float')

        values = raw.get('values')
        if not islistof(values, (int, float), allowNone=True):
            raise EleanorParserException(f'parameter {name} values must be a list of int or float')

        return ParameterConfig(name, param_type, unit, min, max, value, values)


@dataclass(init=False)
class SuppressionConfig(object):
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
        if not islistof(exceptions, (str), allowNone=False):
            raise EleanorParserException(f'suppression exceptions must be a list of int or float')

        return SuppressionConfig(name, suppression_type, exceptions)


@dataclass
class ConstraintsConfig(object):
    temperature: ParameterConfig
    pressure: ParameterConfig
    elements: dict[str, ParameterConfig]
    species: dict[str, ParameterConfig]
    suppressions: list[SuppressionConfig]

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

    @staticmethod
    def from_dict(raw: dict):
        temperature = ParameterConfig.from_dict(raw['temperature'], 'temperature')
        pressure = ParameterConfig.from_dict(raw['pressure'], 'pressure')
        elements = {name: ParameterConfig.from_dict(value, name=name) for name, value in raw['elements'].items()}
        species = {name: ParameterConfig.from_dict(value, name=name) for name, value in raw['species'].items()}
        suppressions = [
            SuppressionConfig.from_dict({}, name=value)
            if isinstance(value, str) else SuppressionConfig.from_dict(value) for value in raw.get('suppress', [])
        ]

        return ConstraintsConfig(temperature, pressure, elements, species, suppressions)


@dataclass
class Problem(object):
    kernel: KernelConfig
    constraints: ConstraintsConfig
    reactants: list[ParameterConfig]

    @staticmethod
    def from_dict(raw: dict):
        kernel_type = raw['kernel']['type'].lower()
        if kernel_type == 'eq36':
            kernel = Eq36KernelConfig.from_dict(raw['kernel'])
        else:
            raise EleanorParserException(f'invalid kernel type {kernel_type}')

        constraints = ConstraintsConfig.from_dict(raw['constraints'])
        reactants = [ParameterConfig.from_dict(value, name=name) for name, value in raw.get('reactants', []).items()]

        return Problem(kernel, constraints, reactants)

    @property
    def is_fully_specified(self):
        return self.constraints.is_fully_specified and all(reactant.is_fully_specified for reactant in self.reactants)


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

    @staticmethod
    def from_problem(name: str, date: datetime.date | datetime.datetime, notes: str, creator: str, problem: Problem):
        return Config(name, date, notes, creator, problem.kernel, problem.constraints, problem.reactants)

    @staticmethod
    def from_dict(raw: dict):
        name = raw['name']
        if not isinstance(name, str):
            raise EleanorParserException('name must be a string')

        config_date = raw['date']
        if isinstance(config_date, str):
            config_date = parsedate(config_date)

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
    def from_yaml(fname: str):
        with open(fname, 'rb') as handle:
            raw = yaml.safe_load(handle)
            return Config.from_dict(raw)

    @staticmethod
    def from_toml(fname: str):
        with open(fname, 'rb') as handle:
            raw = tomllib.load(handle)
            return Config.from_dict(raw)

    @staticmethod
    def from_json(fname: str):
        with open(fname, 'rb') as handle:
            raw = json.load(handle)
            return Config.from_dict(raw)
