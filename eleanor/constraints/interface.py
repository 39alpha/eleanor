from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import cast, override

import numpy as np

from eleanor.config.constraint import ConstraintConfig
from eleanor.exceptions import EleanorException
from eleanor.order import Order
from eleanor.parameters import Parameter, ParameterRegistry, Valuation, ValueParameter
from eleanor.query.path import MatchFilter, Segment, parse_path


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

    def resolve(self, registry: ParameterRegistry, valuation: Valuation) -> None:
        if not self.is_resolvable(registry, valuation):
            msg = "cannot resolve an unresolvable constraint"
            raise EleanorException(msg)

        valuation.update(self.apply(registry, valuation))

    @abstractmethod
    def apply(self, registry: ParameterRegistry, valuation: Valuation) -> Valuation:
        pass

    @classmethod
    def from_order(cls, order: Order, constraint_config: ConstraintConfig) -> AbstractConstraint | None:
        match constraint_config.kind:
            case "linear":
                return LinearConstraint.from_order(order, constraint_config)
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
        msg = f"meta-accessors are not valid in constraint variable paths: {path_str}"
        raise EleanorException(msg)

    segments: tuple[Segment, ...] = path.segments
    missing = object()
    current: object = order
    for segment in segments:
        next_value = getattr(current, segment.name, missing)
        if next_value is missing:
            msg = f"cannot resolve {segment.name!r} on {type(current).__name__} in path {path_str!r}"
            raise EleanorException(msg)
        current = cast(object, next_value)

        for filt in segment.filters:
            if not isinstance(filt, MatchFilter):
                msg = f"only match filters are supported in constraint paths: {path_str}"
                raise EleanorException(msg)
            if len(filt.predicates) != 1:
                msg = f"constraint path filters must have exactly one predicate: {path_str}"
                raise EleanorException(msg)
            pred = filt.predicates[0]
            value = pred.value

            if isinstance(current, dict):
                current_dict = cast(dict[object, object], current)
                if pred.field != "key":
                    msg = f"dict filters must use key=<value>: {path_str}"
                    raise EleanorException(msg)
                if value not in current_dict:
                    msg = f"key {value!r} not found in dict for path {path_str!r}"
                    raise EleanorException(msg)
                current = current_dict[value]
            elif isinstance(current, list):
                found: object | None = None
                for item in cast(list[object], current):
                    item_value = cast(object, getattr(item, pred.field, missing))
                    if item_value is not missing and item_value == value:
                        found = item
                        break
                if found is None:
                    msg = f"{pred.field}={value} not found in list for path {path_str!r}"
                    raise EleanorException(msg)
                current = found
            else:
                msg = f"cannot apply filter to {type(current).__name__} in path {path_str!r}"
                raise EleanorException(msg)

    if not isinstance(current, Parameter):
        msg = f"path {path_str!r} does not resolve to a Parameter (got {type(current).__name__})"
        raise EleanorException(msg)
    return current


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
                        msg = f"unhandled transform: {self}"
                        raise AssertionError(msg)  # pyright: ignore[reportUnreachable]
            except FloatingPointError as exc:
                msg = f"{self.value} transform forward failed for input {x}"
                raise EleanorException(msg) from exc

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
                        msg = f"unhandled transform: {self}"
                        raise AssertionError(msg)  # pyright: ignore[reportUnreachable]
            except FloatingPointError as exc:
                msg = f"{self.value} transform inverse failed for input {y}"
                raise EleanorException(msg) from exc


@dataclass
class LinearConstraintTerm:
    parameter: Parameter
    coefficient: np.float64
    transform: Transform
    name: str = ""

    def label(self) -> str:
        return self.name or f"<unnamed term @{id(self.parameter):x}>"


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
            msg = "LinearConstraint requires at least one term"
            raise EleanorException(msg)

        self.constant = constant if constant is not None else ValueParameter(np.float64(0.0))
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
            msg = "constant parameter is not resolved"
            raise EleanorException(msg)
        c = constant_param.value

        if self._dependent_term is None:
            lhs = np.float64(0.0)
            for term in self._independent_terms:
                term_param = valuation[registry.id(term.parameter)]
                if not isinstance(term_param, ValueParameter):
                    msg = f"parameter {term.label()!r} is not resolved"
                    raise EleanorException(msg)
                lhs = np.float64(lhs + term.coefficient * term.transform.forward(term_param.value))
            if np.abs(lhs - c) > self.tolerance:
                msg = f"LinearConstraint violated: |{lhs} - {c}| = {np.abs(lhs - c)} > tolerance {self.tolerance}"
                raise EleanorException(msg)
            return {}

        rhs = c
        for term in self._independent_terms:
            term_param = valuation[registry.id(term.parameter)]
            if not isinstance(term_param, ValueParameter):
                msg = f"independent parameter {term.label()!r} is not resolved"
                raise EleanorException(msg)
            rhs = np.float64(rhs - term.coefficient * term.transform.forward(term_param.value))

        dep = self._dependent_term
        if dep.coefficient == 0.0:
            msg = "dependent term has zero coefficient; equation is unsolvable"
            raise EleanorException(msg)
        dep_transformed = np.float64(rhs / dep.coefficient)
        dep_value = dep.transform.inverse(dep_transformed)
        fixed = dep.parameter.fix(dep_value)
        if not dep.parameter.in_domain(fixed):
            msg = f"linear constraint solved {dep.label()!r} to {dep_value}, which is outside its admissible domain"
            raise EleanorException(msg)
        return {registry.id(dep.parameter): fixed}

    @classmethod
    @override
    def from_order(cls, order: Order, constraint_config: ConstraintConfig) -> LinearConstraint:
        raw = constraint_config.args
        terms_args = raw.get("terms")
        if not isinstance(terms_args, list):
            msg = "linear constraint must have a 'terms' list"
            raise EleanorException(msg)

        terms: list[LinearConstraintTerm] = []
        for i, term_obj in enumerate(cast(list[object], terms_args)):
            if not isinstance(term_obj, dict):
                msg = f"constraint term {i} must be a dict"
                raise EleanorException(msg)
            term_args = cast(dict[str, object], term_obj)

            variable_str = term_args.get("variable")
            if not isinstance(variable_str, str):
                msg = f"constraint term {i} must have a string 'variable'"
                raise EleanorException(msg)

            coeff_args = term_args.get("coefficient", 1.0)
            if isinstance(coeff_args, bool) or not isinstance(coeff_args, int | float | str):
                msg = f"constraint term {i} coefficient must be numeric"
                raise EleanorException(msg)
            try:
                coefficient = np.float64(float(coeff_args))
            except (TypeError, ValueError) as exc:
                msg = f"constraint term {i} coefficient must be numeric"
                raise EleanorException(msg) from exc

            transform_str = term_args.get("transform", "identity")
            if not isinstance(transform_str, str):
                msg = f"constraint term {i} 'transform' must be a string"
                raise EleanorException(msg)
            try:
                transform = Transform(transform_str)
            except ValueError as exc:
                msg = (
                    f"constraint term {i}: unknown transform {transform_str!r}; must be one of: identity, log10, pow10"
                )
                raise EleanorException(msg) from exc

            parameter = resolve_parameter(order, variable_str)
            terms.append(
                LinearConstraintTerm(
                    parameter=parameter,
                    coefficient=coefficient,
                    transform=transform,
                    name=variable_str,
                ),
            )

        constant: Parameter | None = None
        if "constant" in raw:
            constant = Parameter.load(raw["constant"])

        tolerance: np.float64 | None = None
        if "tolerance" in raw:
            tolerance_args = raw["tolerance"]
            if isinstance(tolerance_args, bool) or not isinstance(tolerance_args, int | float | str):
                msg = "constraint tolerance must be numeric"
                raise EleanorException(msg)
            try:
                tolerance = np.float64(float(tolerance_args))
            except (TypeError, ValueError) as exc:
                msg = "constraint tolerance must be numeric"
                raise EleanorException(msg) from exc

        return cls(terms=terms, constant=constant, tolerance=tolerance)
