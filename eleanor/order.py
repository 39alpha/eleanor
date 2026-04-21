import hashlib
import json
import operator
import os.path
import tomllib
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Protocol, TypedDict, final

import yaml
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Table
from sqlalchemy.orm import relationship

import eleanor.variable_space as vs
from eleanor.kernel.registry import get_spec as get_kernel_spec
from eleanor.variable_space import Point as VSPoint

from .exceptions import EleanorException
from .kernel.config import Config as KernelConfig
from .kernel.config import Settings as KernelSettings
from .parameters import Parameter, ParameterSource
from .reactants import AbstractReactant, ReactantRaw
from .typing import Any, Callable, Self, cast
from .util import is_list_of, mapreduce
from .yeoman import Binary, JSONDict, reconstructor, yeoman_registry

type RawMap = dict[str, object]


# ``KernelRaw`` is intentionally an alias of ``RawMap``. The order parser only
# knows the ``type`` key; the rest of the kernel block is kernel-specific and
# validated inside ``<kernel_module>.Settings.from_dict``.
type KernelRaw = RawMap


class NavigatorRaw(TypedDict, total=False):
    type: str
    args: RawMap


class TransformerRaw(TypedDict, total=False):
    type: str
    args: RawMap


# ``except`` is a Python keyword, so the functional TypedDict syntax is used.
SuppressionRaw = TypedDict(
    'SuppressionRaw',
    {
        'name': str | None,
        'type': str | None,
        'except': list[str],
    },
    total=False,
)


class SuborderRaw(TypedDict, total=False):
    """Schema for a raw suborder document (also used for the top-level order).

    All keys are optional at the schema level; runtime validation enforces
    which are required in each concrete context.
    """
    name: str | None
    notes: str | None
    creator: str | None
    kernel: KernelRaw
    navigator: str | NavigatorRaw
    water_mass: ParameterSource
    temperature: ParameterSource
    pressure: ParameterSource
    elements: dict[str, ParameterSource]
    species: dict[str, ParameterSource]
    suppressions: list[str | SuppressionRaw]
    reactants: dict[str, ReactantRaw]
    constraints: list[RawMap]
    suborders: 'SubordersRaw | list[SuborderRaw]'
    transformers: list[str | TransformerRaw]


class SubordersRaw(TypedDict, total=False):
    combined: bool
    proportional_sampling: bool
    orders: list[SuborderRaw]


def _require_opt_str(value: object, field_name: str) -> str | None:
    """Validate that ``value`` is a string or ``None`` at runtime.

    Used at the boundary between untrusted raw-dict input (YAML/TOML/JSON)
    and the typed dataclass-backed suborder/order model. Taking ``object``
    here (rather than the TypedDict's narrower ``str | None``) is deliberate:
    it forces the ``isinstance`` check to be meaningful even when the caller
    reads a field whose ``TypedDict`` declaration promises the right type.
    """
    if value is not None and not isinstance(value, str):
        raise EleanorException(f'{field_name} must be a string')
    return value


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise EleanorException(f'{field_name} must be a string')
    return value


def _build_transformer(value: object) -> 'TransformerConfig':
    """Construct a :class:`TransformerConfig` from its raw string/dict form.

    Accepting ``object`` rather than ``str | TransformerRaw`` keeps the
    ``isinstance`` checks meaningful to the type checker: the TypedDict
    declaration is aspirational, so a raw ``123`` from YAML still has to
    be rejected at runtime.
    """
    if isinstance(value, str):
        return TransformerConfig(type=value)
    if isinstance(value, dict):
        return TransformerConfig(**cast(TransformerRaw, cast(object, value)))
    raise EleanorException(f'invalid transformer config "{value}"')


def load_kernel_settings(kernel_raw: KernelRaw) -> tuple[str, KernelSettings]:
    """Parse a raw kernel block into its ``(type, Settings)`` pair via the registry."""
    kernel_type = _require_str(kernel_raw.get('type'), 'kernel.type')
    kernel_args_raw = kernel_raw.get('args', {}) or {}
    if not isinstance(kernel_args_raw, dict):
        raise EleanorException('kernel.args must be a dict')
    spec = get_kernel_spec(kernel_type)
    kernel_args = cast(dict[str, Any], kernel_args_raw)  # pyright: ignore[reportExplicitAny]
    return kernel_type, cast(KernelSettings, spec.settings_from_dict(kernel_args))


class NavigatorProtocol(Protocol):
    def navigate(self, scale: int, *args: object, **kwargs: object) -> list[vs.Point]:
        ...
    def huffer_problem(self, *args: object, **kwargs: object) -> vs.Point:
        ...

    def supports_success_sampling(self) -> bool:
        ...

    def is_complete(self, batch: list[int]) -> bool:
        ...


@dataclass
class ConstraintConfig(object):
    type: str

    def volume(self) -> float:
        return 1.0


@dataclass(init=False)
class NavigatorConfig(object):
    type: str
    args: dict[str, Any]  # pyright: ignore[reportExplicitAny]

    def __init__(self, type: str = 'random', args: dict[str, Any] | None = None):  # pyright: ignore[reportExplicitAny]
        self.type = type
        self.args = args if args is not None else {}

    def load(self) -> Callable[..., NavigatorProtocol]:
        """Return the navigator factory registered under :attr:`type`."""
        from eleanor.navigator.registry import get_factory

        return cast(Callable[..., NavigatorProtocol], get_factory(self.type))


@dataclass(init=False)
class TransformerConfig(object):
    type: str
    args: RawMap

    def __init__(self, type: str = 'glass_reactant_embedder', args: RawMap | None = None):
        self.type = type
        self.args = args if args is not None else {}

    def load(self) -> Callable[..., object]:
        """Return the transformer factory registered under :attr:`type`."""
        from eleanor.transformers.registry import get_factory

        return cast(Callable[..., object], get_factory(self.type))


@dataclass(init=False)
class Suppression(object):
    name: str | None
    type: str | None
    exceptions: list[str]

    def __init__(self, name: str | None, type: str | None, exceptions: list[str]):
        if name is None and type is None:
            raise EleanorException(f'suppression must have a name or a type')

        self.name = name
        self.type = type
        self.exceptions = exceptions

    @staticmethod
    def from_dict(raw: SuppressionRaw, name: str | None = None) -> "Suppression":
        if name is None:
            name = _require_opt_str(raw.get('name'), 'suppression.name')

        suppression_type = _require_opt_str(raw.get('type'), 'suppression.type')

        exceptions_raw = raw.get('except', [])
        if not is_list_of(exceptions_raw, str, allowNone=False):
            raise EleanorException(f'suppression exceptions must be a list of strings')

        return Suppression(name, suppression_type, exceptions_raw)


@final
@yeoman_registry.mapped_as_dataclass(init=False)
class HufferResult(object):
    __table__ = Table(
        'huffer',
        yeoman_registry.metadata,
        Column('id', Integer, ForeignKey('orders.id', ondelete="CASCADE"), primary_key=True),
        Column('exit_code', Integer, nullable=False),
        Column('zip', Binary, nullable=False),
    )

    id: int | None
    exit_code: int | None
    zip: bytes

    def __init__(self, zip: bytes, exit_code: int, id: int | None = None):
        self.id = id
        self.exit_code = exit_code
        self.zip = zip

    @classmethod
    def from_scratch(cls, scratch: vs.Scratch | None, exit_code: int, id: int | None = None):
        if scratch is None:
            zip = bytes('\0', 'ascii')
        else:
            zip = scratch.zip

        return cls(id=id, exit_code=exit_code, zip=zip)


@dataclass
class Suborder(object):
    name: str | None = None
    notes: str | None = None
    creator: str | None = None
    kernel: KernelConfig | None = None
    navigator: NavigatorConfig | None = None
    water_mass: Parameter | None = None
    temperature: Parameter | None = None
    pressure: Parameter | None = None
    elements: dict[str, Parameter] | None = None
    species: dict[str, Parameter] | None = None
    suppressions: list[Suppression] | None = None
    reactants: list[AbstractReactant] | None = None
    constraints: list[ConstraintConfig] | None = None
    suborders: Suborders | None = None
    raw: SuborderRaw = field(default_factory=SuborderRaw)

    def volume(self):
        volume = 1.0
        if self.kernel is not None:
            volume *= mapreduce(lambda p: p.volume(), operator.mul, self.kernel.parameters(), initial=1.0)
        if self.water_mass is not None:
            volume *= self.water_mass.volume()
        if self.temperature is not None:
            volume *= self.temperature.volume()
        if self.pressure is not None:
            volume *= self.pressure.volume()
        if self.elements is not None:
            volume *= mapreduce(lambda p: p.volume(), operator.mul, self.elements.values(), initial=1.0)
        if self.species is not None:
            volume *= mapreduce(lambda p: p.volume(), operator.mul, self.species.values(), initial=1.0)
        if self.reactants is not None:
            volume *= mapreduce(lambda p: p.volume(), operator.mul, self.reactants, initial=1.0)
        if self.constraints is not None:
            volume *= mapreduce(lambda p: p.volume(), operator.mul, self.constraints, initial=1.0)

        if self.suborders is not None:
            volume *= self.suborders.volume()

        return volume

    @classmethod
    def from_dict(cls, raw: SuborderRaw | None) -> Self:
        suborder = cls()

        if raw is None:
            raw = SuborderRaw()

        suborder.raw = raw

        suborder.name = _require_opt_str(raw.get('name'), 'name')
        suborder.notes = _require_opt_str(raw.get('notes'), 'notes')
        suborder.creator = _require_opt_str(raw.get('creator'), 'creator')

        if 'kernel' in raw:
            kernel_type, kernel_settings = load_kernel_settings(raw['kernel'])
            suborder.kernel = KernelConfig(type=kernel_type, settings=kernel_settings)

        if 'navigator' in raw:
            navigator_raw = raw['navigator']
            if isinstance(navigator_raw, str):
                suborder.navigator = NavigatorConfig(type=navigator_raw)
            else:
                suborder.navigator = NavigatorConfig(**navigator_raw)

        if 'water_mass' in raw:
            suborder.water_mass = Parameter.load(raw['water_mass'], 'water_mass')

        if 'temperature' in raw:
            suborder.temperature = Parameter.load(raw['temperature'], 'temperature')

        if 'pressure' in raw:
            suborder.pressure = Parameter.load(raw['pressure'], 'pressure')

        if 'elements' in raw:
            elements_raw = raw.get('elements') or {}
            suborder.elements = {
                name: Parameter.load(value, name=name)
                for name, value in elements_raw.items()
            }

        if 'species' in raw:
            species_raw = raw.get('species') or {}
            suborder.species = {
                name: Parameter.load(value, name=name)
                for name, value in species_raw.items()
            }

        if 'suppressions' in raw:
            suppressions_raw = raw.get('suppressions') or []
            suborder.suppressions = [
                Suppression.from_dict(SuppressionRaw(), name=value)
                if isinstance(value, str)
                else Suppression.from_dict(value)
                for value in suppressions_raw
            ]

        if 'reactants' in raw:
            reactants_raw = raw.get('reactants') or {}
            suborder.reactants = [
                AbstractReactant.from_dict(value, name=name)
                for name, value in reactants_raw.items()
            ]

        if 'constraints' in raw:
            suborder.constraints = []

        if 'suborders' in raw:
            suborder.suborders = Suborders(raw['suborders'])

        return suborder


@dataclass(init=False)
class Suborders(object):
    combined: bool = False
    proportional_sampling: bool = False
    suborders: list[Suborder] = field(default_factory=list)

    def __init__(self, raw: SubordersRaw | list[SuborderRaw]):
        if isinstance(raw, dict):
            self.combined = raw.get('combined', False)
            self.proportional_sampling = raw.get('proportional_sampling', False)
            self.suborders = [Suborder.from_dict(s) for s in raw.get('orders', [])]
        else:
            self.suborders = [Suborder.from_dict(s) for s in raw]

    def volume(self) -> float:
        return sum(map(lambda o: o.volume(), self.suborders))


@final
@yeoman_registry.mapped_as_dataclass(init=False)
class Order(Suborder):
    __table__: Table = Table(
        'orders',
        yeoman_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('name', String, nullable=False, index=True),
        Column('hash', String, nullable=False, index=True),
        Column('eleanor_version', String, nullable=False),
        Column('raw', JSONDict, nullable=False),
        Column('create_date', DateTime, nullable=False),
    )

    __table_args__: tuple[Index] = (Index('hash_version', 'hash', 'eleanor_version', unique=True), )

    __mapper_args__: dict[str, object] = {
        'properties': {
            'vs_points': relationship(vs.Point, cascade="all, delete"),
            'huffer_result': relationship(HufferResult, cascade="all, delete", uselist=False),
        }
    }

    hash: str = ''
    transformers: list[TransformerConfig]

    suborders: Suborders | None = None

    huffer_result: HufferResult | None = None
    id: int | None = None
    vs_points: list[VSPoint] = field(default_factory=lambda: [])
    create_date: datetime = field(default_factory=datetime.now)
    eleanor_version: str | None = None

    def __init__(
        self,
        raw: SuborderRaw,
        huffer_result: HufferResult | None = None,
        vs_points: list[VSPoint] | None = None,
        create_date: datetime | None = None,
    ):
        # Delegate to ``Suborder``'s dataclass-generated ``__init__`` so every
        # inherited field is initialized to its declared default before
        # ``__post_init__`` populates them from ``raw``. This also keeps
        # basedpyright's ``reportMissingSuperCall`` check happy.
        super().__init__()
        self.raw = raw
        self.huffer_result = huffer_result
        self.vs_points = [] if vs_points is None else vs_points
        self.create_date = datetime.now() if create_date is None else create_date

        self.__post_init__()

    @reconstructor
    def __post_init__(self):
        self.name = _require_str(self.raw.get('name'), 'name')
        self.notes = _require_str(self.raw.get('notes', ''), 'notes')
        self.creator = _require_str(self.raw.get('creator'), 'creator')

        if 'kernel' in self.raw:
            kernel_type, kernel_settings = load_kernel_settings(self.raw['kernel'])
            self.kernel = KernelConfig(type=kernel_type, settings=kernel_settings)

        navigator_raw = self.raw.get('navigator', NavigatorRaw())
        if isinstance(navigator_raw, str):
            self.navigator = NavigatorConfig(type=navigator_raw)
        else:
            self.navigator = NavigatorConfig(**navigator_raw)

        self.water_mass = Parameter.load(self.raw.get('water_mass', 1.0), 'water_mass')

        if 'temperature' in self.raw:
            self.temperature = Parameter.load(self.raw['temperature'], 'temperature')

        if 'pressure' in self.raw:
            self.pressure = Parameter.load(self.raw['pressure'], 'pressure')

        elements_raw = self.raw.get('elements') or {}
        self.elements = {
            name: Parameter.load(value, name=name)
            for name, value in elements_raw.items()
        }

        species_raw = self.raw.get('species') or {}
        self.species = {
            name: Parameter.load(value, name=name)
            for name, value in species_raw.items()
        }

        suppressions_raw = self.raw.get('suppressions') or []
        self.suppressions = [
            Suppression.from_dict(SuppressionRaw(), name=value)
            if isinstance(value, str)
            else Suppression.from_dict(value)
            for value in suppressions_raw
        ]

        reactants_raw = self.raw.get('reactants') or {}
        self.reactants = [
            AbstractReactant.from_dict(value, name=name)
            for name, value in reactants_raw.items()
        ]

        self.constraints = []

        transformers_raw = self.raw.get('transformers') or []
        self.transformers = [_build_transformer(t) for t in transformers_raw]

        if 'suborders' in self.raw:
            self.suborders = Suborders(self.raw['suborders'])
        _ = self.rehash()

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

        if self.water_mass is not None:
            parameters.append(self.water_mass)

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

    def split_suborders(self) -> list[Self]:
        orders: list[Self] = []
        if self.suborders is not None:
            for suborder in self.suborders.suborders:
                order = deepcopy(self)
                order.name = suborder.name if suborder.name is not None else order.name
                order.notes = suborder.notes if suborder.notes is not None else order.notes
                order.creator = suborder.creator if suborder.creator is not None else order.creator
                order.water_mass = suborder.water_mass if suborder.water_mass is not None else order.water_mass
                order.temperature = suborder.temperature if suborder.temperature is not None else order.temperature
                order.pressure = suborder.pressure if suborder.pressure is not None else order.pressure
                order.elements = suborder.elements if suborder.elements is not None else order.elements
                order.species = suborder.species if suborder.species is not None else order.species
                order.suppressions = suborder.suppressions if suborder.suppressions is not None else order.suppressions
                order.reactants = suborder.reactants if suborder.reactants is not None else order.reactants
                order.constraints = suborder.constraints if suborder.constraints is not None else order.constraints
                order.suborders = suborder.suborders

                if 'suborders' in order.raw:
                    del order.raw['suborders']
                order.raw.update(suborder.raw)
                _ = order.rehash()

                orders.append(order)

        return orders

    @staticmethod
    def from_yaml(fname: str):
        with open(fname, 'rb') as handle:
            return Order(cast(SuborderRaw, cast(object, yaml.safe_load(handle))))

    @staticmethod
    def from_yamls(content: str):
        return Order(cast(SuborderRaw, cast(object, yaml.safe_load(content))))

    @staticmethod
    def from_toml(fname: str):
        with open(fname, 'rb') as handle:
            return Order(cast(SuborderRaw, cast(object, tomllib.load(handle))))

    @staticmethod
    def from_tomls(content: str):
        return Order(cast(SuborderRaw, cast(object, tomllib.loads(content))))

    @staticmethod
    def from_json(fname: str):
        with open(fname, 'rb') as handle:
            return Order(cast(SuborderRaw, cast(object, json.load(handle))))

    @staticmethod
    def from_jsons(content: str):
        return Order(cast(SuborderRaw, cast(object, json.loads(content))))

    @staticmethod
    def from_file(fname: str):
        try:
            _, ext = os.path.splitext(fname)
            match ext:
                case ".yaml":
                    return Order.from_yaml(fname)
                case ".yml":
                    return Order.from_yaml(fname)
                case ".toml":
                    return Order.from_toml(fname)
                case ".json":
                    return Order.from_json(fname)
                case _:
                    raise RuntimeError(f'unsupported file extension "{ext}"')
        except EleanorException:
            raise
        except Exception as e:
            raise EleanorException(f'failed to parse "{fname}" as yaml, toml or json') from e


def load_order(order: str | Order) -> Order:
    if isinstance(order, str):
        order = Order.from_file(order)
    return order
