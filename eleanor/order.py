import json
import os.path
import tomllib
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict, final

import yaml

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
    name: str
    notes: str
    creator: str
    kernel: KernelConfig
    navigator: NavigatorConfig
    water_mass: Parameter
    temperature: Parameter
    pressure: Parameter
    elements: dict[str, Parameter]
    species: dict[str, Parameter]
    suppressions: list[Suppression]
    reactants: list[AbstractReactant]
    constraints: list[ConstraintConfig]
    raw: OrderRaw
    id: int | None
    vs_points: list[VSPoint]
    create_date: datetime
    eleanor_version: str | None
    tag: str

    def __init__(
        self,
        raw: OrderRaw,
        order_id: int | None = None,
        tag: str | None = None,
        vs_points: list[VSPoint] | None = None,
        create_date: datetime | None = None,
    ) -> None:
        self.raw = raw
        # Runtime metadata (legitimately optional / defaulted).
        self.vs_points = [] if vs_points is None else vs_points
        self.create_date = datetime.now() if create_date is None else create_date
        self.id = order_id if order_id is not None else _require_opt_int(self.raw.get("id"), "id")
        raw_tag = _require_opt_str(self.raw.get("tag"), "tag") or ""
        self.tag = tag if tag is not None else raw_tag
        self.eleanor_version = None
        # Required string fields.
        self.name = _require_str(self.raw.get("name"), "name")
        self.notes = _require_str(self.raw.get("notes", ""), "notes")
        self.creator = _require_str(self.raw.get("creator"), "creator")
        # Kernel (required).
        if "kernel" not in self.raw:
            raise EleanorException("kernel is required")
        kernel_type, kernel_settings = load_kernel_settings(self.raw["kernel"])
        self.kernel = KernelConfig(type=kernel_type, settings=kernel_settings)
        # Navigator (defaults to random).
        navigator_raw = self.raw.get("navigator", NavigatorRaw())
        if isinstance(navigator_raw, str):
            self.navigator = NavigatorConfig(type=navigator_raw)
        else:
            self.navigator = NavigatorConfig(**navigator_raw)
        # Water mass (defaults to 1.0 if absent from raw).
        self.water_mass = Parameter.load(self.raw.get("water_mass", 1.0), "water_mass")
        # Temperature (required, no default).
        if "temperature" not in self.raw:
            raise EleanorException("temperature is required")
        self.temperature = Parameter.load(self.raw["temperature"], "temperature")
        # Pressure (required, no default).
        if "pressure" not in self.raw:
            raise EleanorException("pressure is required")
        self.pressure = Parameter.load(self.raw["pressure"], "pressure")
        # Elements (required non-empty).
        elements_raw = self.raw.get("elements") or {}
        self.elements = {name: Parameter.load(value, name=name) for name, value in elements_raw.items()}
        if not self.elements:
            raise EleanorException("elements must not be empty")
        # Species (may be empty).
        species_raw = self.raw.get("species") or {}
        self.species = {name: Parameter.load(value, name=name) for name, value in species_raw.items()}
        # Suppressions (may be empty).
        suppressions_raw = self.raw.get("suppressions") or []
        self.suppressions = [
            Suppression.from_dict(SuppressionRaw(), name=value)
            if isinstance(value, str)
            else Suppression.from_dict(value)
            for value in suppressions_raw
        ]
        # Reactants (may be empty).
        reactants_raw = self.raw.get("reactants") or {}
        self.reactants = [AbstractReactant.from_dict(value, name=name) for name, value in reactants_raw.items()]
        # Constraints (may be empty; no constraint-config loader yet).
        self.constraints = []

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

    @staticmethod
    def from_yaml(fname: str):
        with open(fname, "rb") as handle:
            return Order(cast(OrderRaw, cast(object, yaml.safe_load(handle))))

    @staticmethod
    def from_yamls(content: str):
        return Order(cast(OrderRaw, cast(object, yaml.safe_load(content))))

    @staticmethod
    def from_toml(fname: str):
        with open(fname, "rb") as handle:
            return Order(cast(OrderRaw, cast(object, tomllib.load(handle))))

    @staticmethod
    def from_tomls(content: str):
        return Order(cast(OrderRaw, cast(object, tomllib.loads(content))))

    @staticmethod
    def from_json(fname: str):
        with open(fname, "rb") as handle:
            return Order(cast(OrderRaw, cast(object, json.load(handle))))

    @staticmethod
    def from_jsons(content: str):
        return Order(cast(OrderRaw, cast(object, json.loads(content))))

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
