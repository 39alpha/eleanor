import hashlib
import json
import tomllib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

import yaml
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Table
from sqlalchemy.orm import reconstructor, relationship

import eleanor.variable_space as vs
from eleanor.kernel.discover import import_kernel_module

from .exceptions import EleanorException
from .kernel.config import Config as KernelConfig
from .parameters import Parameter
from .reactants import AbstractReactant, Reactant
from .typing import Any, Callable, Optional, cast
from .util import is_list_of
from .yeoman import Binary, JSONDict, yeoman_registry


@dataclass
class ConstraintConfig(object):
    type: str


@dataclass(init=False)
class Suppression(object):
    name: Optional[str]
    type: Optional[str]
    exceptions: list[str]

    def __init__(self, name: Optional[str], type: Optional[str], exceptions: list[str]):
        if name is None and type is None:
            raise EleanorException(f'suppression must have a name or a type')

        self.name = name
        self.type = type
        self.exceptions = exceptions

    @staticmethod
    def from_dict(raw: dict, name: Optional[str] = None):
        if name is None:
            name = raw.get('name')

        if not isinstance(name, (str, type(None))):
            raise EleanorException(f'suppression name must be a string')

        suppression_type = raw.get('type')
        if not isinstance(suppression_type, (str, type(None))):
            raise EleanorException(f'supression type must be a string')

        exceptions = raw.get('except', [])
        if not is_list_of(exceptions, (str), allowNone=False):
            raise EleanorException(f'suppression exceptions must be a list of int or float')

        return Suppression(name, suppression_type, exceptions)


@yeoman_registry.mapped_as_dataclass(init=False)
class HufferResult(object):
    __table__ = Table(
        'huffer',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('orders.id'), primary_key=True),
        Column('exit_code', Integer, nullable=False),
        Column('zip', Binary, nullable=False),
    )

    id: Optional[int]
    exit_code: Optional[int]
    zip: bytes

    def __init__(self, zip: bytes, exit_code: int, id: Optional[int] = None):
        self.id = id
        self.exit_code = exit_code
        self.zip = zip

    @classmethod
    def from_scratch(cls, scratch: Optional[vs.Scratch], exit_code: int, id: Optional[int] = None):
        if scratch is None:
            zip = bytes('\0', 'ascii')
        else:
            zip = scratch.zip

        return cls(id=id, exit_code=exit_code, zip=zip)


@yeoman_registry.mapped_as_dataclass(init=False)
class Order(object):
    __table__ = Table(
        'orders',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('name', String, nullable=False, index=True),
        Column('hash', String, nullable=False, index=True),
        Column('eleanor_version', String, nullable=False),
        Column('kernel_version', String, nullable=False),
        Column('raw', JSONDict, nullable=False),
        Column('create_date', DateTime, nullable=False),
    )

    __table_args__ = (Index('hash_version', 'hash', 'eleanor_version', 'kernel_version', unique=True), )

    __mapper_args__ = {
        'properties': {
            'vs_points': relationship(vs.Point),
            'huffer_result': relationship(HufferResult, uselist=False),
        }
    }

    hash: str
    name: str
    notes: str
    creator: str
    kernel: KernelConfig
    temperature: Parameter
    pressure: Parameter
    elements: dict[str, Parameter]
    species: dict[str, Parameter]
    suppressions: list[Suppression]
    reactants: list[Reactant]
    constraints: list[ConstraintConfig]
    raw: dict[str, Any]
    huffer_result: Optional[HufferResult] = None
    id: Optional[int] = None
    vs_points: list[vs.Point] = field(default_factory=list)
    create_date: datetime = field(default_factory=datetime.now)
    eleanor_version: Optional[str] = None
    kernel_version: Optional[str] = None

    def __init__(
        self,
        raw: dict,
        huffer_result: Optional[HufferResult] = None,
        vs_points: Optional[list[vs.Point]] = None,
        create_date: Optional[datetime] = None,
    ):
        self.raw = raw
        self.huffer_result = huffer_result
        self.vs_points = [] if vs_points is None else vs_points
        self.create_date = datetime.now() if create_date is None else create_date

        self.__post_init__()

    @reconstructor
    def __post_init__(self):
        self.name = self.raw['name']
        if not isinstance(self.name, str):
            raise EleanorException('name must be a string')

        self.notes = self.raw.get('notes', '')
        if not isinstance(self.notes, str):
            raise EleanorException('notes must be a string')

        self.creator = self.raw['creator']
        if not isinstance(self.creator, str):
            raise EleanorException('creator must be a string')

        kernel_module = import_kernel_module(self.raw['kernel']['type'])
        self.kernel = kernel_module.Config.from_dict(self.raw['kernel'])

        self.temperature = Parameter.from_dict(self.raw['temperature'], 'temperature')
        self.pressure = Parameter.from_dict(self.raw['pressure'], 'pressure')
        self.elements = {name: Parameter.from_dict(value, name=name) for name, value in self.raw['elements'].items()}
        self.species = {name: Parameter.from_dict(value, name=name) for name, value in self.raw['species'].items()}
        self.suppressions = [
            Suppression.from_dict({}, name=value) if isinstance(value, str) else Suppression.from_dict(value)
            for value in self.raw.get('suppressions', [])
        ]

        self.reactants = [
            AbstractReactant.from_dict(value, name=name) for name, value in self.raw.get('reactants', {}).items()
        ]

        self.constraints: list[ConstraintConfig] = []

        hasher = hashlib.sha256()
        content: bytes = bytes(json.dumps(self.raw, sort_keys=True, default=str), 'utf-8')
        hasher.update(content)

        self.hash = hasher.hexdigest()

    def parameters(self) -> list[Parameter]:
        parameters: list[Parameter] = [self.temperature, self.pressure]
        parameters.extend(self.kernel.parameters())
        parameters.extend(e for e in self.elements.values())
        parameters.extend(s for s in self.species.values())
        for reactant in self.reactants:
            parameters.extend(reactant.parameters())

        return parameters

    @staticmethod
    def from_yaml(fname: str):
        with open(fname, 'rb') as handle:
            raw = yaml.safe_load(handle)
            return Order(raw)

    @staticmethod
    def from_yamls(content: str):
        raw = yaml.safe_load(content)
        return Order(raw)

    @staticmethod
    def from_toml(fname: str):
        with open(fname, 'rb') as handle:
            raw = tomllib.load(handle)
            return Order(raw)

    @staticmethod
    def from_tomls(content: str):
        raw = tomllib.loads(content)
        return Order(raw)

    @staticmethod
    def from_json(fname: str):
        with open(fname, 'rb') as handle:
            raw = json.load(handle)
            return Order(raw)

    @staticmethod
    def from_jsons(content: str):
        raw = json.loads(content)
        return Order(raw)

    @staticmethod
    def from_file(fname: str):
        parsers: dict[str, Callable[[str], Order]] = {
            'yaml': Order.from_yaml,
            'toml': Order.from_toml,
            'json': Order.from_json,
        }

        for filetype, func in parsers.items():
            try:
                return func(fname)
            except tomllib.TOMLDecodeError:
                pass
            except json.decoder.JSONDecodeError:
                pass
            except yaml.scanner.ScannerError:
                pass

        raise EleanorException(f'failed to parse "{fname}" as yaml, toml or json')


def load_order(order: str | Order) -> Order:
    if isinstance(order, str):
        order = Order.from_file(order)

    return cast(Order, order)
