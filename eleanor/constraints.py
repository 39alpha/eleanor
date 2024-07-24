from abc import ABC, abstractmethod
from dataclasses import dataclass

import eleanor.models as models

from .config import Config, Parameter, ValueParameter
from .config.constraints import ConstraintConfig
from .config.reactant import *
from .exceptions import EleanorException
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
    def from_config(cls, config: Config, constraint_config: ConstraintConfig):
        pass


class Boatswain(object):
    config: Config
    parameters: list[Parameter]
    constraints: list[AbstractConstraint]
    valuations: dict[Parameter, Parameter]

    def __init__(self, config: Config, *constraints: AbstractConstraint):
        self.config = config
        self.parameters = config.parameters()

        self.constraints = [AbstractConstraint.from_config(self.config, c) for c in config.constraints]
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

    def generate_vs(self, order_id: Optional[int] = None) -> models.VSPoint:
        try:
            valuation: dict[Parameter, ValueParameter] = {}
            for original, refined in self.valuations.items():
                if not isinstance(refined, ValueParameter):
                    raise Exception(f'parameter {original} is not fully refined: {refined}')
                valuation[original] = refined

            elements = [
                models.Element(name=e.name, log_molality=valuation[e].value) for e in self.config.elements.values()
            ]

            species = [
                models.Species(name=s.name,
                               unit=s.unit if s.unit is not None else 'log_molality',
                               value=valuation[s].value) for s in self.config.species.values()
            ]

            suppressions = [
                models.Suppression(
                    name=s.name,
                    type=s.type,
                    exceptions=[models.SuppressionException(name=name) for name in s.exceptions],
                ) for s in self.config.suppressions
            ]

            reactants: list[models.Reactant] = []
            for reactant in self.config.reactants:
                match reactant:
                    case MineralReactant(name, rct_type, log_moles, log_titration_rate):
                        model: models.Reactant = models.MineralReactant(
                            id=None,
                            vs_id=None,
                            name=name,
                            type=rct_type,
                            log_moles=valuation[log_moles].value,
                            log_titration_rate=valuation[log_titration_rate].value,
                        )
                    case GasReactant(name, rct_type, log_moles, log_titration_rate):
                        model = models.GasReactant(
                            id=None,
                            vs_id=None,
                            name=name,
                            type=rct_type,
                            log_moles=valuation[log_moles].value,
                            log_titration_rate=valuation[log_titration_rate].value,
                        )
                    case ElementReactant(name, rct_type, log_moles, log_titration_rate):
                        model = models.ElementReactant(
                            id=None,
                            vs_id=None,
                            name=name,
                            type=rct_type,
                            log_moles=valuation[log_moles].value,
                            log_titration_rate=valuation[log_titration_rate].value,
                        )
                    case SpecialReactant(name, rct_type, log_moles, log_titration_rate, composition):
                        model = models.SpecialReactant(
                            id=None,
                            vs_id=None,
                            name=name,
                            type=rct_type,
                            log_moles=valuation[log_moles].value,
                            log_titration_rate=valuation[log_titration_rate].value,
                            composition=[
                                models.SpecialReactantComposition(element=k, count=v) for k, v in composition.items()
                            ],
                        )
                    case FixedGasReactant(name, rct_type, log_moles, log_fugacity):
                        model = models.FixedGasReactant(
                            id=None,
                            vs_id=None,
                            name=name,
                            type=rct_type,
                            log_moles=valuation[log_moles].value,
                            log_fugacity=valuation[log_fugacity].value,
                        )
                    case _:
                        raise Exception()
                reactants.append(model)

            return models.VSPoint(
                kernel=self.config.kernel,
                temperature=valuation[self.config.temperature].value,
                pressure=valuation[self.config.pressure].value,
                elements=elements,
                species=species,
                suppressions=suppressions,
                reactants=reactants,
            )
        except Exception as e:
            raise Exception('cannot generate VSPoint from config') from e
