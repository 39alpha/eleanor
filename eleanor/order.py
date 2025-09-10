import hashlib
import json
import tomllib
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import asdict, dataclass, field
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
from .typing import Any, Callable, Optional, Self, cast
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
        Column('id', Integer, ForeignKey('orders.id', ondelete="CASCADE"), primary_key=True),
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


@dataclass
class Suborder(object):
    name: Optional[str] = None
    notes: Optional[str] = None
    creator: Optional[str] = None
    kernel: Optional[KernelConfig] = None
    temperature: Optional[Parameter] = None
    pressure: Optional[Parameter] = None
    elements: Optional[dict[str, Parameter]] = None
    species: Optional[dict[str, Parameter]] = None
    suppressions: Optional[list[Suppression]] = None
    reactants: Optional[list[Reactant]] = None
    constraints: Optional[list[ConstraintConfig]] = None
    suborders = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Self:
        suborder = cls()

        suborder.raw = raw

        suborder.name = raw.get('name')
        if suborder.name is not None and not isinstance(suborder.name, str):
            raise EleanorException('name must be a string')

        suborder.notes = raw.get('notes')
        if suborder.notes is not None and not isinstance(suborder.notes, str):
            raise EleanorException('notes must be a string')

        suborder.creator = raw.get('creator')
        if suborder.creator is not None and not isinstance(suborder.creator, str):
            raise EleanorException('creator must be a string')

        if 'kernel' in raw:
            kernel_module = import_kernel_module(raw['kernel']['type'])
            kernel_settings = kernel_module.Settings.from_dict(raw['kernel'])
            suborder.kernel = KernelConfig(type=raw['kernel']['type'], settings=kernel_settings)  # type: ignore

        if 'temperature' in raw:
            suborder.temperature = Parameter.load(raw['temperature'], 'temperature')

        if 'pressure' in raw:
            suborder.pressure = Parameter.load(raw['pressure'], 'pressure')

        if 'elements' in raw:
            suborder.elements = {
                name: Parameter.load(value, name=name)
                for name, value in (raw.get('elements', {}) or {}).items()
            }

        if 'species' in raw:
            suborder.species = {
                name: Parameter.load(value, name=name)
                for name, value in (raw.get('species', {}) or {}).items()
            }

        if 'suppressions' in raw:
            suborder.suppressions = [
                Suppression.from_dict({}, name=value) if isinstance(value, str) else Suppression.from_dict(value)
                for value in raw.get('suppressions', []) or []
            ]

        if 'reactants' in raw:
            suborder.reactants = [
                AbstractReactant.from_dict(value, name=name)
                for name, value in (raw.get('reactants', {}) or {}).items()
            ]

        if 'constraints' in raw:
            suborder.constraints = []

        if 'suborders' in raw:
            suborder.suborders = Suborders(raw['suborders'])

        return suborder

    def has_suborders(self) -> bool:
        return self.suborders is not None and len(self.suborders.suborders) != 0


@dataclass(init=False)
class Suborders(object):
    combined: bool = False
    suborders: list[Suborder] = field(default_factory=list)

    def __init__(self, raw: dict[str, Any] | list[dict[str, Any]]):
        if isinstance(raw, dict):
            self.combined = raw.get('combined', False)
            self.suborders = [Suborder.from_dict(suborder) for suborder in raw.get('suborders', [])]
        else:
            self.combined = False
            self.suborders = [Suborder.from_dict(suborder) for suborder in raw]


@yeoman_registry.mapped_as_dataclass(init=False)
class Order(Suborder):
    __table__ = Table(
        'orders',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('name', String, nullable=False, index=True),
        Column('hash', String, nullable=False, index=True),
        Column('eleanor_version', String, nullable=False),
        Column('raw', JSONDict, nullable=False),
        Column('create_date', DateTime, nullable=False),
    )

    __table_args__ = (Index('hash_version', 'hash', 'eleanor_version', unique=True), )

    __mapper_args__ = {
        'properties': {
            'vs_points': relationship(vs.Point, cascade="all, delete"),
            'huffer_result': relationship(HufferResult, cascade="all, delete", uselist=False),
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

    suborders: Optional[Suborders] = None

    huffer_result: Optional[HufferResult] = None
    id: Optional[int] = None
    vs_points: list[vs.Point] = field(default_factory=list)
    create_date: datetime = field(default_factory=datetime.now)
    eleanor_version: Optional[str] = None

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

        if 'kernel' in self.raw:
            kernel_module = import_kernel_module(self.raw['kernel']['type'])
            kernel_settings = kernel_module.Settings.from_dict(self.raw['kernel'])
            self.kernel = KernelConfig(type=self.raw['kernel']['type'], settings=kernel_settings)  # type: ignore

        if 'temperature' in self.raw:
            self.temperature = Parameter.load(self.raw['temperature'], 'temperature')

        if 'pressure' in self.raw:
            self.pressure = Parameter.load(self.raw['pressure'], 'pressure')

        self.elements = {
            name: Parameter.load(value, name=name)
            for name, value in (self.raw.get('elements', {}) or {}).items()
        }

        self.species = {
            name: Parameter.load(value, name=name)
            for name, value in (self.raw.get('species', {}) or {}).items()
        }

        self.suppressions = [
            Suppression.from_dict({}, name=value) if isinstance(value, str) else Suppression.from_dict(value)
            for value in self.raw.get('suppressions', []) or []
        ]

        self.reactants = [
            AbstractReactant.from_dict(value, name=name)
            for name, value in (self.raw.get('reactants', {}) or {}).items()
        ]

        self.constraints = []

        if 'suborders' in self.raw:
            self.suborders = Suborders(self.raw['suborders'])

        self.rehash()

    def rehash(self) -> str:
        data = asdict(self)
        for k in ['huffer_result', 'id', 'vs_points', 'create_date', 'eleanor_version']:
            del data[k]

        hasher = hashlib.sha256()
        content: bytes = bytes(json.dumps(data, sort_keys=True, default=str), 'utf-8')
        hasher.update(content)

        self.hash = hasher.hexdigest()

        return self.hash

    def parameters(self) -> list[Parameter]:
        parameters: list[Parameter] = []

        if self.temperature is not None:
            parameters.append(self.temperature)

        if self.pressure is not None:
            parameters.append(self.pressure)

        if self.kernel is not None:
            parameters.extend(self.kernel.parameters())

        if self.elements is not None:
            parameters.extend(e for e in self.elements.values())

        if self.species is not None:
            parameters.extend(s for s in self.species.values())

        if self.reactants is not None:
            for reactant in self.reactants:
                parameters.extend(reactant.parameters())

        return parameters

    def split_suborders(self) -> tuple[list[Self], bool]:
        combined = False
        orders: list[Self] = []
        if self.suborders is not None:
            combined = self.suborders.combined
            for suborder in self.suborders.suborders:
                order = deepcopy(self)
                order.name = suborder.name if suborder.name is not None else order.name
                order.notes = suborder.notes if suborder.notes is not None else order.notes
                order.creator = suborder.creator if suborder.creator is not None else order.creator
                order.temperature = suborder.temperature if suborder.temperature is not None else order.temperature
                order.pressure = suborder.pressure if suborder.pressure is not None else order.pressure
                order.elements = suborder.elements if suborder.elements is not None else order.elements
                order.species = suborder.species if suborder.species is not None else order.species
                order.suppressions = suborder.suppressions if suborder.suppressions is not None else order.suppressions
                order.reactants = suborder.reactants if suborder.reactants is not None else order.reactants
                order.constraints = suborder.constraints if suborder.constraints is not None else order.constraints
                order.suborders = suborder.suborders

                del order.raw['suborders']
                order.raw.update(suborder.raw)
                order.rehash()

                orders.append(order)

        return orders, combined

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
            'toml': Order.from_toml,
            'json': Order.from_json,
            'yaml': Order.from_yaml,
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
