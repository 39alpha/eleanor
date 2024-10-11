from abc import ABC, abstractmethod
from copy import deepcopy

import eleanor.variable_space as vs

from .exceptions import EleanorException
from .order import ConstraintConfig, Order
from .parameters import Parameter, ValueParameter
from .reactants import *
from .typing import Optional

Valuation = dict[Parameter, Parameter]


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

    def is_resolvable(self, valuation: Valuation) -> bool:
        return all(p in valuation and isinstance(valuation[p], ValueParameter) for p in self.independent_parameters)

    def resolve(self, valuation: Valuation):
        if not self.is_resolvable(valuation):
            raise EleanorException('cannot resolve an unresolvable constraint')

        valuation.update(self.apply(valuation))

    @abstractmethod
    def apply(self, valuation: Valuation) -> dict[Parameter, Parameter]:
        pass

    @classmethod
    def from_order(cls, order: Order, constraint_config: ConstraintConfig):
        pass


class Boatswain(object):
    order: Order
    parameters: list[Parameter]
    constraints: list[AbstractConstraint]
    valuations: dict[Parameter, Parameter]

    def __init__(self, order: Order, *constraints: AbstractConstraint):
        self.order = order
        self.parameters = order.parameters()

        self.constraints = [AbstractConstraint.from_order(self.order, c) for c in self.order.constraints]
        self.constraints.extend(constraints)

        self.valuations = {p: p for p in self.parameters}

    def __getitem__(self, parameter: Parameter) -> Parameter:
        return self.valuations[parameter]

    def __setitem__(self, parameter: Parameter, value: Parameter):
        if parameter not in self.valuations and not parameter.in_domain(value):
            raise Exception(f'{value} is not a refinment of {parameter}')

        refined = self.valuations[parameter]
        if not refined.in_domain(value):
            raise Exception(f'{value} is not a refinement of {refined}')

        self.valuations[parameter] = value

    def constrain(self) -> list[Parameter]:
        unresolved_constraints: list[AbstractConstraint] = []

        while self.constraints:
            constraint = self.constraints.pop()
            if constraint.is_resolvable(self.valuations):
                constraint.resolve(self.valuations)
            else:
                unresolved_constraints.append(constraint)

        fully_constrained: list[Parameter] = []
        under_constrained: list[Parameter] = []

        for original, refined in self.valuations.items():
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

    def generate_vs(self, order_id: Optional[int] = None) -> vs.Point:
        try:
            valuation: dict[Parameter, ValueParameter] = {}
            for original, refined in self.valuations.items():
                if not isinstance(refined, ValueParameter):
                    raise Exception(f'parameter {original} is not fully refined: {refined}')
                valuation[original] = refined

            elements = [vs.Element(name=e.name, log_molality=valuation[e].value) for e in self.order.elements.values()]

            species = [
                vs.Species(name=s.name, unit=s.unit if s.unit is not None else 'log_molality', value=valuation[s].value)
                for s in self.order.species.values()
            ]

            suppressions = [
                vs.Suppression(
                    name=s.name,
                    type=s.type,
                    exceptions=[vs.SuppressionException(name=name) for name in s.exceptions],
                ) for s in self.order.suppressions
            ]

            reactants: list[vs.Reactant] = []
            for reactant in self.order.reactants:
                match reactant:
                    case MineralReactant(name, rct_type, log_moles, titration_rate):
                        model: vs.Reactant = vs.MineralReactant(
                            id=None,
                            variable_space_id=None,
                            name=name,
                            type=rct_type,
                            log_moles=valuation[log_moles].value,
                            titration_rate=valuation[titration_rate].value,
                        )
                    case GasReactant(name, rct_type, log_moles, titration_rate):
                        model = vs.GasReactant(
                            id=None,
                            variable_space_id=None,
                            name=name,
                            type=rct_type,
                            log_moles=valuation[log_moles].value,
                            titration_rate=valuation[titration_rate].value,
                        )
                    case ElementReactant(name, rct_type, log_moles, titration_rate):
                        model = vs.ElementReactant(
                            id=None,
                            variable_space_id=None,
                            name=name,
                            type=rct_type,
                            log_moles=valuation[log_moles].value,
                            titration_rate=valuation[titration_rate].value,
                        )
                    case SpecialReactant(name, rct_type, log_moles, titration_rate, composition):
                        model = vs.SpecialReactant(
                            id=None,
                            variable_space_id=None,
                            name=name,
                            type=rct_type,
                            log_moles=valuation[log_moles].value,
                            titration_rate=valuation[titration_rate].value,
                            composition=[
                                vs.SpecialReactantComposition(element=k, count=v) for k, v in composition.items()
                            ],
                        )
                    case FixedGasReactant(name, rct_type, log_moles, log_fugacity):
                        model = vs.FixedGasReactant(
                            id=None,
                            variable_space_id=None,
                            name=name,
                            type=rct_type,
                            log_moles=valuation[log_moles].value,
                            log_fugacity=valuation[log_fugacity].value,
                        )
                    case _:
                        raise Exception()
                reactants.append(model)

            return vs.Point(
                order_id=order_id,
                kernel=deepcopy(self.order.kernel),
                temperature=valuation[self.order.temperature].value,
                pressure=valuation[self.order.pressure].value,
                elements=elements,
                species=species,
                suppressions=suppressions,
                reactants=reactants,
            )
        except Exception as e:
            raise Exception('cannot generate Point from config') from e
