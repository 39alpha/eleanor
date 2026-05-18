import json
import operator
import os.path
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Self, TypedDict, final

import numpy as np
import yaml

from .exceptions import EleanorException
from .kernel.config import Config as KernelConfig
from .kernel.config import Settings as KernelSettings
from .kernel.config import resolve_settings as resolve_kernel_settings
from .parameters import Parameter, ParameterSource
from .reactants import AbstractReactant, CombinedReactant, ReactantRaw
from .typing import cast
from .util import is_list_of, mapreduce
from .variable_space import Point as VSPoint
from .version import __version__

type RawMap = dict[str, object]


# ``KernelRaw`` is intentionally an alias of ``RawMap``. The order parser only
# knows the ``type`` key; the rest of the kernel block is kernel-specific and
# validated inside ``<kernel_module>.Settings.from_dict``.
type KernelRaw = RawMap


class NavigatorRaw(TypedDict, total=False):
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


class OrderRaw(TypedDict, total=False):
    """Schema for a raw order document.

    All keys are optional at the schema level; runtime validation enforces
    which are required in each concrete context.
    """

    id: int | None
    tag: str | None
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


def _require_opt_int(value: object, field_name: str) -> int | None:
    """Validate that ``value`` is an int or ``None`` at runtime.

    Used at the boundary between untrusted raw-dict input (YAML/TOML/JSON)
    and the typed dataclass-backed order model. Taking ``object``
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
    and the typed dataclass-backed order model. Taking ``object``
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


@dataclass
class ConstraintConfig(object):
    type: str
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(init=False)
class NavigatorConfig(object):
    type: str
    args: RawMap

    def __init__(self, type: str = "random", args: RawMap | None = None):
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
@dataclass(init=True, kw_only=True)
class Order:
    name: str
    creator: str
    kernel: KernelConfig
    temperature: Parameter
    pressure: Parameter
    id: int | None = None
    tag: str = ""
    notes: str = ""
    eleanor_version: str = __version__
    create_date: datetime = field(default_factory=datetime.now)
    navigator: NavigatorConfig = field(default_factory=NavigatorConfig)
    water_mass: Parameter = field(default_factory=lambda: Parameter.load(1.0, "water_mass"))
    elements: dict[str, Parameter] = field(default_factory=dict)
    species: dict[str, Parameter] = field(default_factory=dict)
    suppressions: list[Suppression] = field(default_factory=list)
    reactants: list[AbstractReactant] = field(default_factory=list)
    constraints: list[ConstraintConfig] = field(default_factory=list)
    vs_points: list[VSPoint] = field(default_factory=list)

    def __post_init__(self):
        if self.name == "":
            raise EleanorException("name must not be empty")

        if self.creator == "":
            raise EleanorException("creator must not be empty")

        if not self.elements:
            raise EleanorException("elements must not be empty")

        seen_names: set[str] = set()

        def _add_unique(candidate: str) -> None:
            if candidate in seen_names:
                raise EleanorException(
                    f'reactant name "{candidate}" appears more than once '
                    + "across reactants and combined-reactant components"
                )
            seen_names.add(candidate)

        for reactant in self.reactants:
            if isinstance(reactant, CombinedReactant):
                for component_name in reactant.components:
                    _add_unique(component_name)
            else:
                _add_unique(reactant.name)

    @classmethod
    def from_dict(
        cls,
        raw: OrderRaw,
        *,
        order_id: int | None = None,
        tag: str | None = None,
        create_date: datetime | None = None,
        vs_points: list[VSPoint] | None = None,
    ) -> Self:
        if order_id is None:
            order_id = _require_opt_int(raw.get("id"), "id")

        raw_tag = _require_opt_str(raw.get("tag"), "tag") or ""
        tag = tag if tag is not None else raw_tag

        name = _require_str(raw.get("name"), "name")
        notes = _require_str(raw.get("notes", ""), "notes")
        creator = _require_str(raw.get("creator"), "creator")

        create_date = create_date if create_date is not None else datetime.now()

        if "kernel" not in raw:
            raise EleanorException("kernel is required")
        kernel_type, kernel_settings = load_kernel_settings(raw["kernel"])
        kernel_config = KernelConfig(type=kernel_type, settings=kernel_settings)

        navigator_raw = raw.get("navigator", NavigatorRaw())
        if isinstance(navigator_raw, str):
            navigator = NavigatorConfig(type=navigator_raw)
        else:
            try:
                navigator = NavigatorConfig(**navigator_raw)
            except TypeError as e:
                raise EleanorException("invalid navigator config") from e

        if "temperature" not in raw:
            raise EleanorException("temperature is required")
        temperature = Parameter.load(raw["temperature"], "temperature")

        if "pressure" not in raw:
            raise EleanorException("pressure is required")
        pressure = Parameter.load(raw["pressure"], "pressure")

        elements_raw = raw.get("elements") or {}
        elements = {el_name: Parameter.load(value, name=el_name) for el_name, value in elements_raw.items()}

        species_raw = raw.get("species") or {}
        species = {sp_name: Parameter.load(value, name=sp_name) for sp_name, value in species_raw.items()}

        suppressions_raw = raw.get("suppressions") or []
        suppressions = [
            Suppression.from_dict(SuppressionRaw(), name=value)
            if isinstance(value, str)
            else Suppression.from_dict(value)
            for value in suppressions_raw
        ]

        reactants_raw = raw.get("reactants") or {}
        reactants = [AbstractReactant.from_dict(value, name=re_name) for re_name, value in reactants_raw.items()]

        constraints_obj = cast(object, raw.get("constraints") or [])
        if not isinstance(constraints_obj, list):
            raise EleanorException("constraints must be a list")
        constraints_list = cast(list[object], constraints_obj)
        constraints: list[ConstraintConfig] = []
        for c_obj in constraints_list:
            if not isinstance(c_obj, dict):
                raise EleanorException("each constraint must be a dict")
            c_raw = cast(dict[str, object], c_obj)
            c_type = _require_str(c_raw.get("type"), "constraint.type")
            constraints.append(ConstraintConfig(type=c_type, raw=c_raw))

        vs_points = vs_points or []

        return cls(
            id=order_id,
            tag=tag,
            name=name,
            notes=notes,
            creator=creator,
            create_date=create_date,
            kernel=kernel_config,
            navigator=navigator,
            water_mass=Parameter.load(raw.get("water_mass", 1.0), "water_mass"),
            temperature=temperature,
            pressure=pressure,
            elements=elements,
            species=species,
            suppressions=suppressions,
            reactants=reactants,
            constraints=constraints,
            vs_points=vs_points,
        )

    def parameters(self) -> list[Parameter]:
        parameters: list[Parameter] = [
            self.water_mass,
            self.temperature,
            self.pressure,
        ]
        parameters.extend(self.kernel.parameters())
        parameters.extend(self.elements.values())
        parameters.extend(self.species.values())
        for reactant in self.reactants:
            parameters.extend(reactant.parameters())

        return parameters

    def volume(self) -> np.float64:
        return mapreduce(
            lambda p: p.volume(),
            operator.mul,
            self.parameters(),
            np.float64(1.0),
        )

    @classmethod
    def from_yaml(cls, fname: str) -> Self:
        with open(fname, "rb") as handle:
            return cls.from_dict(cast(OrderRaw, cast(object, yaml.safe_load(handle))))

    @classmethod
    def from_yamls(cls, content: str) -> Self:
        return cls.from_dict(cast(OrderRaw, cast(object, yaml.safe_load(content))))

    @classmethod
    def from_toml(cls, fname: str) -> Self:
        with open(fname, "rb") as handle:
            return cls.from_dict(cast(OrderRaw, cast(object, tomllib.load(handle))))

    @classmethod
    def from_tomls(cls, content: str) -> Self:
        return cls.from_dict(cast(OrderRaw, cast(object, tomllib.loads(content))))

    @classmethod
    def from_json(cls, fname: str) -> Self:
        with open(fname, "rb") as handle:
            return cls.from_dict(cast(OrderRaw, cast(object, json.load(handle))))

    @classmethod
    def from_jsons(cls, content: str) -> Self:
        return cls.from_dict(cast(OrderRaw, cast(object, json.loads(content))))

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
