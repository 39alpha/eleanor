import json
import os.path
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypedDict, final, runtime_checkable

import yaml

import eleanor.variable_space as vs
from eleanor.variable_space import Point as VSPoint

from .exceptions import EleanorException
from .kernel.config import Config as KernelConfig
from .kernel.config import Settings as KernelSettings
from .kernel.config import resolve_settings as resolve_kernel_settings
from .parameters import Parameter, ParameterSource
from .reactants import AbstractReactant, ReactantRaw
from .typing import cast
from .util import is_list_of

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
    "SuppressionRaw",
    {
        "name": str | None,
        "type": str | None,
        "except": list[str],
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
    suborders: "SubordersRaw | list[SuborderRaw]"
    transformers: list[str | TransformerRaw]


class SubordersRaw(TypedDict, total=False):
    combined: bool
    proportional_sampling: bool
    orders: list[SuborderRaw]


def _require_opt_int(value: object, field_name: str) -> int | None:
    """Validate that ``value`` is an int or ``None`` at runtime.

    Used at the boundary between untrusted raw-dict input (YAML/TOML/JSON)
    and the typed dataclass-backed suborder/order model. Taking ``object``
    here (rather than the TypedDict's narrower ``int | None``) is deliberate:
    it forces the ``isinstance`` check to be meaningful even when the caller
    reads a field whose ``TypedDict`` declaration promises the right type.
    """
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise EleanorException(f"{field_name} must be an integer")
    return value


def _require_opt_str(value: object, field_name: str) -> str | None:
    """Validate that ``value`` is a string or ``None`` at runtime.

    Used at the boundary between untrusted raw-dict input (YAML/TOML/JSON)
    and the typed dataclass-backed suborder/order model. Taking ``object``
    here (rather than the TypedDict's narrower ``str | None``) is deliberate:
    it forces the ``isinstance`` check to be meaningful even when the caller
    reads a field whose ``TypedDict`` declaration promises the right type.
    """
    if value is not None and not isinstance(value, str):
        raise EleanorException(f"{field_name} must be a string")
    return value


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise EleanorException(f"{field_name} must be a string")
    return value


def _build_transformer(value: object) -> "TransformerConfig":
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
    kernel_type = _require_str(kernel_raw.get("type"), "kernel.type")
    kernel_args_raw: object = kernel_raw.get("args", {}) or {}
    if not isinstance(kernel_args_raw, dict):
        raise EleanorException("kernel.args must be a dict")
    # YAML/TOML/JSON loaders always produce str-keyed mappings; widen the
    # ``dict[Unknown, Unknown]`` that ``isinstance`` leaves us with back to
    # the registry's declared ``dict[str, object]`` input shape.
    kernel_args_items = cast(dict[object, object], kernel_args_raw).items()
    kernel_args: dict[str, object] = {str(k): v for k, v in kernel_args_items}
    return kernel_type, resolve_kernel_settings(kernel_type, kernel_args)


@runtime_checkable
class NavigatorProtocol(Protocol):
    """Structural protocol for navigator plugins.

    :meth:`navigate` and :meth:`num_systems` are verified by the
    ``isinstance`` check performed after a navigator factory returns
    (see :meth:`Eleanor.run` in :mod:`eleanor.eleanor`).
    """

    def navigate(self, scale: int, batch_size: int, *args: object, **kwargs: object) -> Iterator[list[vs.Point]]: ...

    def num_systems(self, scale: int) -> int: ...


@dataclass
class ConstraintConfig(object):
    type: str

    def volume(self) -> float:
        return 1.0


@dataclass(init=False)
class NavigatorConfig(object):
    type: str
    args: RawMap

    def __init__(self, type: str = "random", args: RawMap | None = None):
        self.type = type
        self.args = args if args is not None else {}


@dataclass(init=False)
class TransformerConfig(object):
    type: str
    args: RawMap

    def __init__(self, type: str, args: RawMap | None = None):
        self.type = type
        self.args = args if args is not None else {}


@dataclass(init=False)
class Suppression(object):
    name: str | None
    type: str | None
    exceptions: list[str]

    def __init__(self, name: str | None, type: str | None, exceptions: list[str]):
        if name is None and type is None:
            raise EleanorException("suppression must have a name or a type")

        self.name = name
        self.type = type
        self.exceptions = exceptions

    @staticmethod
    def from_dict(raw: SuppressionRaw, name: str | None = None) -> "Suppression":
        if name is None:
            name = _require_opt_str(raw.get("name"), "suppression.name")

        suppression_type = _require_opt_str(raw.get("type"), "suppression.type")

        exceptions_raw = raw.get("except", [])
        if not is_list_of(exceptions_raw, str, allowNone=False):
            raise EleanorException("suppression exceptions must be a list of strings")

        return Suppression(name, suppression_type, exceptions_raw)


@final
@dataclass(init=False)
class Order:
    name: str | None
    notes: str | None
    creator: str | None
    kernel: KernelConfig | None
    navigator: NavigatorConfig | None
    water_mass: Parameter | None
    temperature: Parameter | None
    pressure: Parameter | None
    elements: dict[str, Parameter] | None
    species: dict[str, Parameter] | None
    suppressions: list[Suppression] | None
    reactants: list[AbstractReactant] | None
    constraints: list[ConstraintConfig] | None
    raw: SuborderRaw
    transformers: list[TransformerConfig]
    id: int | None
    vs_points: list[VSPoint]
    create_date: datetime
    eleanor_version: str | None
    tag: str

    def __init__(
        self,
        raw: SuborderRaw,
        order_id: int | None = None,
        tag: str | None = None,
        vs_points: list[VSPoint] | None = None,
        create_date: datetime | None = None,
    ):
        self.name = None
        self.notes = None
        self.creator = None
        self.kernel = None
        self.navigator = None
        self.water_mass = None
        self.temperature = None
        self.pressure = None
        self.elements = None
        self.species = None
        self.suppressions = None
        self.reactants = None
        self.constraints = None
        self.raw = SuborderRaw()
        self.transformers = []
        self.id = None
        self.vs_points = []
        self.create_date = datetime.now()
        self.eleanor_version = None
        self.tag = ""
        self.raw = raw
        self.vs_points = [] if vs_points is None else vs_points
        self.create_date = datetime.now() if create_date is None else create_date
        self.id = order_id if order_id is not None else _require_opt_int(self.raw.get("id"), "id")

        raw_tag = _require_opt_str(self.raw.get("tag"), "tag") or ""
        self.tag = tag if tag is not None else raw_tag

        self.name = _require_str(self.raw.get("name"), "name")

        self.eleanor_version = None

        self.__post_init__()

    def __post_init__(self) -> None:
        self.notes = _require_str(self.raw.get("notes", ""), "notes")
        self.creator = _require_str(self.raw.get("creator"), "creator")

        if "kernel" in self.raw:
            kernel_type, kernel_settings = load_kernel_settings(self.raw["kernel"])
            self.kernel = KernelConfig(type=kernel_type, settings=kernel_settings)

        navigator_raw = self.raw.get("navigator", NavigatorRaw())
        if isinstance(navigator_raw, str):
            self.navigator = NavigatorConfig(type=navigator_raw)
        else:
            self.navigator = NavigatorConfig(**navigator_raw)

        self.water_mass = Parameter.load(self.raw.get("water_mass", 1.0), "water_mass")

        if "temperature" in self.raw:
            self.temperature = Parameter.load(self.raw["temperature"], "temperature")

        if "pressure" in self.raw:
            self.pressure = Parameter.load(self.raw["pressure"], "pressure")

        elements_raw = self.raw.get("elements") or {}
        self.elements = {name: Parameter.load(value, name=name) for name, value in elements_raw.items()}

        species_raw = self.raw.get("species") or {}
        self.species = {name: Parameter.load(value, name=name) for name, value in species_raw.items()}

        suppressions_raw = self.raw.get("suppressions") or []
        self.suppressions = [
            Suppression.from_dict(SuppressionRaw(), name=value)
            if isinstance(value, str)
            else Suppression.from_dict(value)
            for value in suppressions_raw
        ]

        reactants_raw = self.raw.get("reactants") or {}
        self.reactants = [AbstractReactant.from_dict(value, name=name) for name, value in reactants_raw.items()]

        self.constraints = []

        transformers_raw = self.raw.get("transformers") or []
        self.transformers = [_build_transformer(t) for t in transformers_raw]

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

    @staticmethod
    def from_yaml(fname: str):
        with open(fname, "rb") as handle:
            return Order(cast(SuborderRaw, cast(object, yaml.safe_load(handle))))

    @staticmethod
    def from_yamls(content: str):
        return Order(cast(SuborderRaw, cast(object, yaml.safe_load(content))))

    @staticmethod
    def from_toml(fname: str):
        with open(fname, "rb") as handle:
            return Order(cast(SuborderRaw, cast(object, tomllib.load(handle))))

    @staticmethod
    def from_tomls(content: str):
        return Order(cast(SuborderRaw, cast(object, tomllib.loads(content))))

    @staticmethod
    def from_json(fname: str):
        with open(fname, "rb") as handle:
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
    """Load and/or override an order.

    If the provided :paramref:`order` is a string, it is assumed to be a
    filename and the order is first loaded from disk.

    If the provided :paramref:`order` is an Order, then this call is a no-op.
    """
    if isinstance(order, str):
        order = Order.from_file(order)
    return order
