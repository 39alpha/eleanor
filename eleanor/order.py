import json
import operator
import secrets
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import Self, cast, final

import numpy as np
import yaml

from eleanor.config.constraint import ConstraintConfig
from eleanor.config.kernel import KernelConfig
from eleanor.config.navigator import NavigatorConfig
from eleanor.exceptions import EleanorError
from eleanor.parameters import Parameter, ParameterOrSource, load_parameter
from eleanor.reactants import AbstractReactant, CombinedReactant
from eleanor.typing import StrPath
from eleanor.util import is_list_of, mapreduce, require, require_dict, require_opt_int, require_opt_str, require_str
from eleanor.variable_space import Point as VSPoint
from eleanor.version import __version__


@dataclass(init=False)
class Suppression:
    name: str | None
    type: str | None
    exceptions: list[str]

    def __init__(self, name: str | None, type: str | None, exceptions: list[str]) -> None:
        if name is None and type is None:
            msg = "suppression must have a name or a type"
            raise EleanorError(msg)

        self.name = name
        self.type = type
        self.exceptions = exceptions

    @staticmethod
    def from_dict(raw: dict[str, object], name: str | None = None) -> Suppression:
        if name is None:
            name = require_opt_str(raw.get("name"), "suppression.name")

        suppression_type = require_opt_str(raw.get("type"), "suppression.type")

        exceptions_raw = raw.get("except", raw.get("exceptions", []))
        if not is_list_of(exceptions_raw, str):
            msg = "suppression exceptions must be a list of strings"
            raise EleanorError(msg)

        return Suppression(name, suppression_type, cast(list[str], exceptions_raw))


def _prepare_tags(tags: object) -> list[str] | None:
    msg = "tags must be a string or list of strings"

    if tags is None:
        return tags
    if isinstance(tags, str):
        tags = [tags]
    elif isinstance(tags, list):
        if not all(isinstance(t, str) for t in cast(list[object], tags)):
            raise EleanorError(msg)
        tags = cast(list[str], tags)
    else:
        raise EleanorError(msg)

    return list(dict.fromkeys([tag for tag in tags if tag != ""]))


@final
@dataclass(init=False)
class Order:
    tags: list[str]
    name: str
    notes: str
    creator: str
    seed: int
    kernel: KernelConfig
    temperature: Parameter
    water_mass: Parameter
    pressure: Parameter
    navigator: NavigatorConfig
    elements: dict[str, Parameter]
    species: dict[str, Parameter]
    suppressions: list[Suppression]
    reactants: list[AbstractReactant]
    constraints: list[ConstraintConfig]
    vs_points: list[VSPoint]
    eleanor_version: str
    create_date: datetime = field(compare=False)

    def __init__(
        self,
        *,
        name: str,
        creator: str,
        kernel: KernelConfig,
        temperature: ParameterOrSource,
        pressure: ParameterOrSource,
        elements: Mapping[str, ParameterOrSource],
        tags: list[str] | None = None,
        notes: str = "",
        seed: int | None = None,
        water_mass: ParameterOrSource | None = None,
        navigator: NavigatorConfig | None = None,
        species: Mapping[str, ParameterOrSource] | None = None,
        suppressions: list[Suppression] | None = None,
        reactants: list[AbstractReactant] | None = None,
        constraints: list[ConstraintConfig] | None = None,
        vs_points: list[VSPoint] | None = None,
        eleanor_version: str | None = None,
        create_date: datetime | None = None,
    ) -> None:
        self.name = name
        if self.name == "":
            msg = "name must not be empty"
            raise EleanorError(msg)

        self.creator = creator
        if self.creator == "":
            msg = "creator must not be empty"
            raise EleanorError(msg)

        self.tags = list(dict.fromkeys(tags)) if tags is not None else []
        self.notes = notes
        self.seed = seed if seed is not None else secrets.randbits(63)

        self.kernel = kernel
        self.water_mass = load_parameter(water_mass if water_mass is not None else 1.0)
        self.temperature = load_parameter(temperature)
        self.pressure = load_parameter(pressure)
        self.navigator = navigator if navigator is not None else NavigatorConfig()

        self.elements = {k: load_parameter(v) for k, v in elements.items()}
        if not self.elements:
            msg = "elements must not be empty"
            raise EleanorError(msg)

        self.species = {k: load_parameter(v) for k, v in species.items()} if species is not None else {}
        self.suppressions = suppressions if suppressions is not None else []
        self.reactants = reactants if reactants is not None else []

        seen_names: set[str] = set()

        def _add_unique(candidate: str) -> None:
            if candidate in seen_names:
                msg = (
                    f"reactant name {candidate!r} appears more than once across"
                    + " reactants and combined-reactant components"
                )
                raise EleanorError(msg)
            seen_names.add(candidate)

        for reactant in self.reactants:
            if isinstance(reactant, CombinedReactant):
                for component_name in reactant.components:
                    _add_unique(component_name)
            else:
                _add_unique(reactant.name)

        self.constraints = constraints if constraints is not None else []
        self.vs_points = vs_points if vs_points is not None else []
        self.eleanor_version = eleanor_version if eleanor_version is not None else __version__
        self.create_date = create_date if create_date is not None else datetime.now()

    @cached_property
    def rng(self) -> np.random.Generator:
        return np.random.default_rng(seed=self.seed)

    @classmethod
    def from_dict(
        cls,
        raw: dict[str, object],
        *,
        seed: int | None = None,
        tags: str | list[str] | None = None,
        create_date: datetime | None = None,
        vs_points: list[VSPoint] | None = None,
    ) -> Self:
        if "id" in raw:
            msg = "user-specified order ids are no longer supported"
            raise EleanorError(msg)

        raw_tags = cast(object, raw.get("tags"))
        tags = _prepare_tags(tags) if tags is not None else _prepare_tags(raw_tags)

        name = require_str(raw.get("name"), "name")
        notes = require_str(raw.get("notes", ""), "notes")
        creator = require_str(raw.get("creator"), "creator")

        create_date = create_date if create_date is not None else datetime.now()

        seed = seed if seed is not None else require_opt_int(raw.get("seed"), "seed")

        if "kernel" not in raw:
            msg = "kernel is required"
            raise EleanorError(msg)

        kernel_config = KernelConfig.from_dict(require_dict(raw["kernel"], "kernel"))

        navigator_raw = raw.get("navigator", {})
        if isinstance(navigator_raw, str):
            navigator = NavigatorConfig(kind=navigator_raw)
        else:
            try:
                navigator = NavigatorConfig.from_dict(require_dict(navigator_raw, "navigator"))
            except TypeError as e:
                msg = "invalid navigator config"
                raise EleanorError(msg) from e

        water_mass = cast(ParameterOrSource | None, raw.get("water_mass"))
        temperature = cast(ParameterOrSource, require(raw.get("temperature"), "temperature"))
        pressure = cast(ParameterOrSource, require(raw.get("pressure"), "pressure"))
        elements = cast(Mapping[str, ParameterOrSource], require_dict(raw.get("elements") or {}, "elements"))
        species = cast(Mapping[str, ParameterOrSource], require_dict(raw.get("species") or {}, "species"))

        suppressions_raw = cast(Sequence[str | dict[str, object]], raw.get("suppressions") or [])
        suppressions = [
            Suppression.from_dict({"name": value}) if isinstance(value, str) else Suppression.from_dict(value)
            for value in suppressions_raw
        ]

        if "reactants" in raw:
            if isinstance(raw["reactants"], dict) or raw["reactants"] is None:
                reactants_raw = cast(dict[str, dict[str, object]], raw["reactants"] or {})
                reactants = [
                    AbstractReactant.from_dict(value, name=re_name) for re_name, value in reactants_raw.items()
                ]
            elif isinstance(raw["reactants"], list):
                reactants_raw = cast(list[dict[str, object]], raw.get("reactants") or [])
                reactants = [AbstractReactant.from_dict(value) for value in reactants_raw]
            else:
                msg = "reactants must be a dict or list of dicts"
                raise EleanorError(msg)
        else:
            reactants = []

        constraints_obj = cast(object, raw.get("constraints") or [])
        if not isinstance(constraints_obj, list):
            msg = "constraints must be a list"
            raise EleanorError(msg)
        constraints_list = cast(list[object], constraints_obj)
        constraints: list[ConstraintConfig] = []
        for constraint in constraints_list:
            if not isinstance(constraint, dict):
                msg = "each constraint must be a dict"
                raise EleanorError(msg)
            constraint_raw = cast(dict[str, object], constraint)
            constraints.append(ConstraintConfig.from_dict(constraint_raw))

        vs_points = vs_points or []

        return cls(
            name=name,
            creator=creator,
            tags=tags,
            notes=notes,
            seed=seed,
            kernel=kernel_config,
            navigator=navigator,
            water_mass=water_mass,
            temperature=temperature,
            pressure=pressure,
            elements=elements,
            species=species,
            suppressions=suppressions,
            reactants=reactants,
            constraints=constraints,
            vs_points=vs_points,
            create_date=create_date,
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
    def from_yaml(
        cls,
        fname: StrPath,
        *,
        seed: int | None = None,
        tags: str | list[str] | None = None,
        create_date: datetime | None = None,
        vs_points: list[VSPoint] | None = None,
    ) -> Self:
        with Path(fname).open("rb") as handle:
            return cls.from_dict(
                cast(dict[str, object], yaml.safe_load(handle)),
                seed=seed,
                tags=tags,
                create_date=create_date,
                vs_points=vs_points,
            )

    @classmethod
    def from_yamls(
        cls,
        content: str,
        *,
        seed: int | None = None,
        tags: str | list[str] | None = None,
        create_date: datetime | None = None,
        vs_points: list[VSPoint] | None = None,
    ) -> Self:
        return cls.from_dict(
            cast(dict[str, object], yaml.safe_load(content)),
            seed=seed,
            tags=tags,
            create_date=create_date,
            vs_points=vs_points,
        )

    @classmethod
    def from_toml(
        cls,
        fname: StrPath,
        *,
        seed: int | None = None,
        tags: str | list[str] | None = None,
        create_date: datetime | None = None,
        vs_points: list[VSPoint] | None = None,
    ) -> Self:
        with Path(fname).open("rb") as handle:
            return cls.from_dict(
                cast(dict[str, object], tomllib.load(handle)),
                seed=seed,
                tags=tags,
                create_date=create_date,
                vs_points=vs_points,
            )

    @classmethod
    def from_tomls(
        cls,
        content: str,
        *,
        seed: int | None = None,
        tags: str | list[str] | None = None,
        create_date: datetime | None = None,
        vs_points: list[VSPoint] | None = None,
    ) -> Self:
        return cls.from_dict(
            cast(dict[str, object], tomllib.loads(content)),
            seed=seed,
            tags=tags,
            create_date=create_date,
            vs_points=vs_points,
        )

    @classmethod
    def from_json(
        cls,
        fname: StrPath,
        *,
        seed: int | None = None,
        tags: str | list[str] | None = None,
        create_date: datetime | None = None,
        vs_points: list[VSPoint] | None = None,
    ) -> Self:
        with Path(fname).open("rb") as handle:
            return cls.from_dict(
                cast(dict[str, object], json.load(handle)),
                seed=seed,
                tags=tags,
                create_date=create_date,
                vs_points=vs_points,
            )

    @classmethod
    def from_jsons(
        cls,
        content: str,
        *,
        seed: int | None = None,
        tags: str | list[str] | None = None,
        create_date: datetime | None = None,
        vs_points: list[VSPoint] | None = None,
    ) -> Self:
        return cls.from_dict(
            cast(dict[str, object], json.loads(content)),
            seed=seed,
            tags=tags,
            create_date=create_date,
            vs_points=vs_points,
        )

    @classmethod
    def from_file(
        cls,
        fname: StrPath,
        *,
        seed: int | None = None,
        tags: str | list[str] | None = None,
        create_date: datetime | None = None,
        vs_points: list[VSPoint] | None = None,
    ) -> Self:
        try:
            fname = Path(fname)
            match fname.suffix:
                case ".yaml":
                    return cls.from_yaml(fname, seed=seed, tags=tags, create_date=create_date, vs_points=vs_points)
                case ".yml":
                    return cls.from_yaml(fname, seed=seed, tags=tags, create_date=create_date, vs_points=vs_points)
                case ".toml":
                    return cls.from_toml(fname, seed=seed, tags=tags, create_date=create_date, vs_points=vs_points)
                case ".json":
                    return cls.from_json(fname, seed=seed, tags=tags, create_date=create_date, vs_points=vs_points)
                case _:
                    msg = f"unsupported file extension {fname.suffix!r}"
                    raise RuntimeError(msg)
        except EleanorError:
            raise
        except Exception as e:
            msg = f"failed to parse {str(fname)!r} as yaml, toml or json"
            raise EleanorError(msg) from e


def load_order(
    order: StrPath | Order,
    *,
    seed: int | None = None,
    tags: str | list[str] | None = None,
    create_date: datetime | None = None,
    vs_points: list[VSPoint] | None = None,
) -> Order:
    """Load and/or override an order.

    If the provided :paramref:`order` is a string, it is assumed to be a
    filename and the order is first loaded from disk.

    If the provided :paramref:`order` is an Order, then this call is a no-op.
    """
    if isinstance(order, (str, Path)):
        order = Order.from_file(order, seed=seed, tags=tags, create_date=create_date, vs_points=vs_points)
    return order


__all__ = [
    "Order",
    "load_order",
]
