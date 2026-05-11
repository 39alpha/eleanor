from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import override

import numpy as np

import eleanor.variable_space as vs
from eleanor.query.path import MatchFilter, Segment, parse_path

from .exceptions import EleanorException
from .order import ConstraintConfig, Order
from .parameters import Parameter, ParameterRegistry, Valuation, ValueParameter
from .reactants import (
    AqueousReactant,
    ElementReactant,
    FixedGasReactant,
    GasReactant,
    GlassReactant,
    MineralReactant,
    SolidSolutionReactant,
    SpecialReactant,
)
from .typing import cast


class Transform(Enum):
    IDENTITY = "identity"
    LOG10 = "log10"
    POW10 = "pow10"

    def forward(self, x: np.float64) -> np.float64:
        with np.errstate(divide="raise", invalid="raise", over="raise"):
            try:
                match self:
                    case Transform.IDENTITY:
                        return x
                    case Transform.LOG10:
                        return cast(np.float64, np.log10(x))
                    case Transform.POW10:
                        return cast(np.float64, np.float_power(10.0, x))
                    case _:  # pyright: ignore[reportUnnecessaryComparison]
                        raise AssertionError(f"unhandled transform: {self}")  # pyright: ignore[reportUnreachable]
            except FloatingPointError as exc:
                raise EleanorException(f"{self.value} transform forward failed for input {x}") from exc

    def inverse(self, y: np.float64) -> np.float64:
        with np.errstate(divide="raise", invalid="raise", over="raise"):
            try:
                match self:
                    case Transform.IDENTITY:
                        return y
                    case Transform.LOG10:
                        return cast(np.float64, np.float_power(10.0, y))
                    case Transform.POW10:
                        return cast(np.float64, np.log10(y))
                    case _:  # pyright: ignore[reportUnnecessaryComparison]
                        raise AssertionError(f"unhandled transform: {self}")  # pyright: ignore[reportUnreachable]
            except FloatingPointError as exc:
                raise EleanorException(f"{self.value} transform inverse failed for input {y}") from exc


@dataclass
class LinearConstraintTerm:
    parameter: Parameter
    coefficient: np.float64
    transform: Transform


class AbstractConstraint(ABC):
    @property
    @abstractmethod
    def independent_parameters(self) -> list[Parameter]:
        pass

    @property
    @abstractmethod
    def dependent_parameters(self) -> list[Parameter]:
        pass

    def depends_on(self, parameter: Parameter) -> bool:
        return any(p is parameter for p in self.independent_parameters)

    def constrains(self, parameter: Parameter) -> bool:
        return any(p is parameter for p in self.dependent_parameters)

    def is_resolvable(self, registry: ParameterRegistry, valuation: Valuation) -> bool:
        return all(
            registry.id(p) in valuation and isinstance(valuation[registry.id(p)], ValueParameter)
            for p in self.independent_parameters
        )

    def resolve(self, registry: ParameterRegistry, valuation: Valuation):
        if not self.is_resolvable(registry, valuation):
            raise EleanorException("cannot resolve an unresolvable constraint")

        valuation.update(self.apply(registry, valuation))

    @abstractmethod
    def apply(self, registry: ParameterRegistry, valuation: Valuation) -> Valuation:
        pass

    @classmethod
    def from_order(cls, _order: Order, _constraint_config: ConstraintConfig) -> "AbstractConstraint | None":
        match _constraint_config.type:
            case "linear":
                return LinearConstraint.from_order(_order, _constraint_config)
            case _:
                return None

    def parameters(self) -> list[Parameter]:
        return []

    def volume(self) -> np.float64:
        return np.float64(1.0)


def resolve_parameter(order: Order, path_str: str) -> Parameter:
    """Walk the Order attribute tree to find the Parameter at ``path_str``."""
    path = parse_path(path_str)
    if path.meta is not None:
        raise EleanorException(f"meta-accessors are not valid in constraint variable paths: {path_str}")

    segments: tuple[Segment, ...] = path.segments
    missing = object()
    current: object = order
    for segment in segments:
        next_value = getattr(current, segment.name, missing)
        if next_value is missing:
            raise EleanorException(f"cannot resolve '{segment.name}' on {type(current).__name__} in path '{path_str}'")
        current = cast(object, next_value)

        for filt in segment.filters:
            if not isinstance(filt, MatchFilter):
                raise EleanorException(f"only match filters are supported in constraint paths: {path_str}")
            if len(filt.predicates) != 1:
                raise EleanorException(f"constraint path filters must have exactly one predicate: {path_str}")
            pred = filt.predicates[0]
            value = pred.value

            if isinstance(current, dict):
                current_dict = cast(dict[object, object], current)
                if pred.field != "key":
                    raise EleanorException(f"dict filters must use key=<value>: {path_str}")
                if value not in current_dict:
                    raise EleanorException(f"key '{value}' not found in dict for path '{path_str}'")
                current = current_dict[value]
            elif isinstance(current, list):
                found: object | None = None
                for item in cast(list[object], current):
                    item_value = cast(object, getattr(item, pred.field, missing))
                    if item_value is not missing and item_value == value:
                        found = item
                        break
                if found is None:
                    raise EleanorException(f"{pred.field}={value} not found in list for path '{path_str}'")
                current = found
            else:
                raise EleanorException(f"cannot apply filter to {type(current).__name__} in path '{path_str}'")

    if not isinstance(current, Parameter):
        raise EleanorException(f"path '{path_str}' does not resolve to a Parameter (got {type(current).__name__})")
    return current


class LinearConstraint(AbstractConstraint):
    terms: list[LinearConstraintTerm]
    constant: Parameter
    tolerance: np.float64
    _dependent_term: LinearConstraintTerm | None
    _independent_terms: list[LinearConstraintTerm]

    def __init__(
        self,
        terms: list[LinearConstraintTerm],
        constant: Parameter | None = None,
        tolerance: np.float64 | None = None,
    ) -> None:
        if not terms:
            raise EleanorException("LinearConstraint requires at least one term")

        self.constant = constant if constant is not None else ValueParameter("constant", None, np.float64(0.0))
        self.tolerance = tolerance if tolerance is not None else np.float64(1e-6)
        self.terms = sorted(terms, key=lambda t: t.parameter.volume(), reverse=True)

        self._dependent_term = None
        self._independent_terms = []
        found_dependent = False
        for term in self.terms:
            if not found_dependent and not isinstance(term.parameter, ValueParameter):
                self._dependent_term = term
                found_dependent = True
            else:
                self._independent_terms.append(term)

    @property
    @override
    def independent_parameters(self) -> list[Parameter]:
        params: list[Parameter] = [t.parameter for t in self._independent_terms]
        params.append(self.constant)
        return params

    @property
    @override
    def dependent_parameters(self) -> list[Parameter]:
        if self._dependent_term is None:
            return []
        return [self._dependent_term.parameter]

    @override
    def parameters(self) -> list[Parameter]:
        # Term parameters are owned by the Order; only the constant is constraint-local.
        return [self.constant]

    @override
    def volume(self) -> np.float64:
        return self.constant.volume()

    @override
    def apply(self, registry: ParameterRegistry, valuation: Valuation) -> Valuation:
        constant_param = valuation[registry.id(self.constant)]
        if not isinstance(constant_param, ValueParameter):
            raise EleanorException("constant parameter is not resolved")
        c = constant_param.value

        if self._dependent_term is None:
            lhs = np.float64(0.0)
            for term in self._independent_terms:
                term_param = valuation[registry.id(term.parameter)]
                if not isinstance(term_param, ValueParameter):
                    raise EleanorException(f"parameter '{term.parameter.name}' is not resolved")
                lhs = np.float64(lhs + term.coefficient * term.transform.forward(term_param.value))
            if np.abs(lhs - c) > self.tolerance:
                raise EleanorException(
                    f"LinearConstraint violated: |{lhs} - {c}| = {np.abs(lhs - c)} > tolerance {self.tolerance}"
                )
            return {}

        rhs = c
        for term in self._independent_terms:
            term_param = valuation[registry.id(term.parameter)]
            if not isinstance(term_param, ValueParameter):
                raise EleanorException(f"independent parameter '{term.parameter.name}' is not resolved")
            rhs = np.float64(rhs - term.coefficient * term.transform.forward(term_param.value))

        dep = self._dependent_term
        if dep.coefficient == 0.0:
            raise EleanorException("dependent term has zero coefficient; equation is unsolvable")
        dep_transformed = np.float64(rhs / dep.coefficient)
        dep_value = dep.transform.inverse(dep_transformed)
        fixed = dep.parameter.fix(dep_value)
        if not dep.parameter.in_domain(fixed):
            raise EleanorException(
                f"linear constraint solved '{dep.parameter.name}' to {dep_value}, which is outside its admissible domain"
            )
        return {registry.id(dep.parameter): fixed}

    @classmethod
    @override
    def from_order(cls, order: Order, constraint_config: ConstraintConfig) -> "LinearConstraint":
        raw = constraint_config.raw
        terms_raw = raw.get("terms")
        if not isinstance(terms_raw, list):
            raise EleanorException("linear constraint must have a 'terms' list")

        terms: list[LinearConstraintTerm] = []
        for i, term_obj in enumerate(cast(list[object], terms_raw)):
            if not isinstance(term_obj, dict):
                raise EleanorException(f"constraint term {i} must be a dict")
            term_raw = cast(dict[str, object], term_obj)

            variable_str = term_raw.get("variable")
            if not isinstance(variable_str, str):
                raise EleanorException(f"constraint term {i} must have a string 'variable'")

            coeff_raw = term_raw.get("coefficient", 1.0)
            if isinstance(coeff_raw, bool) or not isinstance(coeff_raw, int | float | str):
                raise EleanorException(f"constraint term {i} coefficient must be numeric")
            try:
                coefficient = np.float64(float(coeff_raw))
            except (TypeError, ValueError) as exc:
                raise EleanorException(f"constraint term {i} coefficient must be numeric") from exc

            transform_str = term_raw.get("transform", "identity")
            if not isinstance(transform_str, str):
                raise EleanorException(f"constraint term {i} 'transform' must be a string")
            try:
                transform = Transform(transform_str)
            except ValueError as exc:
                raise EleanorException(
                    f"constraint term {i}: unknown transform '{transform_str}'; must be one of: identity, log10, pow10"
                ) from exc

            parameter = resolve_parameter(order, variable_str)
            terms.append(LinearConstraintTerm(parameter=parameter, coefficient=coefficient, transform=transform))

        constant: Parameter | None = None
        if "constant" in raw:
            constant = Parameter.load(raw["constant"], name="constant")

        tolerance: np.float64 | None = None
        if "tolerance" in raw:
            tolerance_raw = raw["tolerance"]
            if isinstance(tolerance_raw, bool) or not isinstance(tolerance_raw, int | float | str):
                raise EleanorException("constraint tolerance must be numeric")
            try:
                tolerance = np.float64(float(tolerance_raw))
            except (TypeError, ValueError) as exc:
                raise EleanorException("constraint tolerance must be numeric") from exc

        return cls(terms=terms, constant=constant, tolerance=tolerance)


class Boatswain(object):
    order: Order
    registry: ParameterRegistry
    parameters: list[Parameter]
    constraints: list[AbstractConstraint]
    valuations: Valuation

    def __init__(self, order: Order, *constraints: AbstractConstraint):
        self.order = order
        self.registry = ParameterRegistry()
        self.registry.add_parameters(order.parameters())

        self.parameters = order.parameters()

        order_constraints = self.order.constraints
        self.constraints = [
            loaded
            for loaded in (AbstractConstraint.from_order(self.order, c) for c in order_constraints)
            if loaded is not None
        ]
        self.constraints.extend(constraints)
        for constraint in self.constraints:
            self.registry.add_parameters(constraint.parameters())

        self.valuations = self.registry.valuation()

    def __getitem__(self, parameter: Parameter) -> Parameter:
        return self.valuations[self.registry.id(parameter)]

    def __setitem__(self, parameter: Parameter, value: Parameter):
        if self.registry.id(parameter) not in self.valuations:
            raise Exception(f"{parameter} ({self.registry.id(parameter)}) is not in the registry")
        elif not parameter.in_domain(value):
            raise Exception(f"{value} is not a refinment of {parameter}")

        parameter_id = self.registry.id(parameter)

        refined = self.valuations[parameter_id]
        if not refined.in_domain(value):
            raise Exception(f"{value} is not a refinement of {refined}")

        self.valuations[parameter_id] = value

    def hardset(self, parameter: Parameter, value: Parameter):
        self.valuations[self.registry.id(parameter)] = value

    def constrain(self) -> list[Parameter]:
        unresolved_constraints: list[AbstractConstraint] = []

        while self.constraints:
            constraint = self.constraints.pop()
            if constraint.is_resolvable(self.registry, self.valuations):
                constraint.resolve(self.registry, self.valuations)
            else:
                unresolved_constraints.append(constraint)

        fully_constrained: list[Parameter] = []
        under_constrained: list[Parameter] = []

        for parameter_id, refined in self.valuations.items():
            original = self.registry.parameter(parameter_id)
            if isinstance(refined, ValueParameter):
                continue

            is_fully_constrained = all(not c.constrains(original) for c in unresolved_constraints)
            if is_fully_constrained:
                fully_constrained.append(original)
            else:
                under_constrained.append(original)

        self.parameters = under_constrained
        self.constraints = unresolved_constraints

        return fully_constrained

    def generate_vs(self, order_id: int | None = None) -> vs.Point:
        try:
            valuation: dict[int, ValueParameter] = {}
            for parameter_id, refined in self.valuations.items():
                original = self.registry.parameter(parameter_id)
                if not isinstance(refined, ValueParameter):
                    raise Exception(f"parameter {original} is not fully refined: {refined}")
                valuation[parameter_id] = refined

            elements = [
                vs.Element(name=e.name, log_molality=valuation[self.registry.id(e)].value)
                for e in self.order.elements.values()
            ]

            species = [
                vs.Species(
                    name=s.name,
                    value=valuation[self.registry.id(s)].value,
                )
                for s in self.order.species.values()
            ]

            suppressions = [
                vs.Suppression(
                    name=s.name,
                    type=s.type,
                    exceptions=[vs.SuppressionException(name=name) for name in s.exceptions],
                )
                for s in self.order.suppressions
            ]

            mineral_reactants: list[vs.MineralReactant] = []
            aqueous_reactants: list[vs.AqueousReactant] = []
            gas_reactants: list[vs.GasReactant] = []
            element_reactants: list[vs.ElementReactant] = []
            special_reactants: list[vs.SpecialReactant] = []
            fixed_gas_reactants: list[vs.FixedGasReactant] = []
            solid_solution_reactants: list[vs.SolidSolutionReactant] = []
            glass_reactants: list[vs.GlassReactant] = []
            for reactant in self.order.reactants:
                match reactant:
                    case MineralReactant(name, _, log_moles, titration_rate):
                        mineral_reactants.append(
                            vs.MineralReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                titration_rate=valuation[self.registry.id(titration_rate)].value,
                            ),
                        )
                    case AqueousReactant(name, _, log_moles, titration_rate):
                        aqueous_reactants.append(
                            vs.AqueousReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                titration_rate=valuation[self.registry.id(titration_rate)].value,
                            ),
                        )
                    case GasReactant(name, _, log_moles, titration_rate):
                        gas_reactants.append(
                            vs.GasReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                titration_rate=valuation[self.registry.id(titration_rate)].value,
                            ),
                        )
                    case ElementReactant(name, _, log_moles, titration_rate):
                        element_reactants.append(
                            vs.ElementReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                titration_rate=valuation[self.registry.id(titration_rate)].value,
                            ),
                        )
                    case SpecialReactant(name, _, log_moles, titration_rate, composition):
                        special_reactants.append(
                            vs.SpecialReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                titration_rate=valuation[self.registry.id(titration_rate)].value,
                                composition=[
                                    vs.SpecialReactantComposition(element=k, count=v) for k, v in composition.items()
                                ],
                            ),
                        )
                    case FixedGasReactant(name, _, log_moles, log_fugacity):
                        fixed_gas_reactants.append(
                            vs.FixedGasReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                log_fugacity=valuation[self.registry.id(log_fugacity)].value,
                            ),
                        )
                    case SolidSolutionReactant(name, _, log_moles, titration_rate, end_members):
                        solid_solution_reactants.append(
                            vs.SolidSolutionReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                titration_rate=valuation[self.registry.id(titration_rate)].value,
                                end_members=[
                                    vs.SolidSolutionReactantEndMembers(
                                        name=name, fraction=valuation[self.registry.id(end_member_param)].value
                                    )
                                    for name, end_member_param in end_members.items()
                                ],
                            ),
                        )
                    case GlassReactant(name, _, log_moles, titration_rate, oxides):
                        log_moles = valuation[self.registry.id(log_moles)].value
                        titration_rate = valuation[self.registry.id(titration_rate)].value

                        glass_reactants.append(
                            vs.GlassReactant(
                                name=name,
                                log_moles=log_moles,
                                titration_rate=titration_rate,
                                oxides=[
                                    vs.GlassReactantOxide(
                                        name=name,
                                        fraction=oxide.fraction,
                                        log_moles=cast(np.float64, np.log10(oxide.fraction)) + log_moles,
                                        titration_rate=titration_rate
                                        * valuation[self.registry.id(oxide.relative_rate)].value,
                                        composition=[
                                            vs.GlassReactantOxideComposition(element=k, count=v)
                                            for k, v in oxide.composition.items()
                                        ],
                                    )
                                    for name, oxide in oxides.items()
                                ],
                            ),
                        )
                    case _:
                        raise Exception(f"Unexpected reactant type {reactant}")

            return vs.Point(
                order_id=order_id,
                kernel=deepcopy(self.order.kernel),
                water_mass=valuation[self.registry.id(self.order.water_mass)].value,
                temperature=valuation[self.registry.id(self.order.temperature)].value,
                pressure=valuation[self.registry.id(self.order.pressure)].value,
                elements=elements,
                species=species,
                suppressions=suppressions,
                mineral_reactants=mineral_reactants,
                aqueous_reactants=aqueous_reactants,
                gas_reactants=gas_reactants,
                element_reactants=element_reactants,
                special_reactants=special_reactants,
                fixed_gas_reactants=fixed_gas_reactants,
                solid_solution_reactants=solid_solution_reactants,
                glass_reactants=glass_reactants,
            )
        except Exception as e:
            raise Exception("cannot generate Point from config") from e
