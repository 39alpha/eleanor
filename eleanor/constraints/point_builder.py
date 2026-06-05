from copy import deepcopy
from typing import cast

import numpy as np

import eleanor.variable_space as vs
from eleanor.constraints.interface import AbstractConstraint
from eleanor.order import Order
from eleanor.parameters import Parameter, ParameterRegistry, Valuation, ValueParameter
from eleanor.reactants import (
    AqueousReactant,
    CombinedReactant,
    ElementReactant,
    FixedGasReactant,
    GasReactant,
    MineralReactant,
    ReactantType,
    SolidSolutionReactant,
    SpecialReactant,
)


class PointBuilder:
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
            raise Exception(f"{value} is not a refinement of {parameter}")

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
                vs.Element(
                    name=name,
                    log_molality=valuation[self.registry.id(p)].value,
                )
                for name, p in self.order.elements.items()
            ]

            species = [
                vs.Species(
                    name=name,
                    value=valuation[self.registry.id(p)].value,
                )
                for name, p in self.order.species.items()
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
            for reactant in self.order.reactants:
                match reactant:
                    case MineralReactant(name=name, amount=log_moles, titration_rate=titration_rate):
                        mineral_reactants.append(
                            vs.MineralReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                titration_rate=valuation[self.registry.id(titration_rate)].value,
                            ),
                        )
                    case AqueousReactant(name=name, amount=log_moles, titration_rate=titration_rate):
                        aqueous_reactants.append(
                            vs.AqueousReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                titration_rate=valuation[self.registry.id(titration_rate)].value,
                            ),
                        )
                    case GasReactant(name=name, amount=log_moles, titration_rate=titration_rate):
                        gas_reactants.append(
                            vs.GasReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                titration_rate=valuation[self.registry.id(titration_rate)].value,
                            ),
                        )
                    case ElementReactant(name=name, amount=log_moles, titration_rate=titration_rate):
                        element_reactants.append(
                            vs.ElementReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                titration_rate=valuation[self.registry.id(titration_rate)].value,
                            ),
                        )
                    case SpecialReactant(
                        name=name, amount=log_moles, titration_rate=titration_rate, composition=composition
                    ):
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
                    case FixedGasReactant(name=name, amount=log_moles, fugacity=log_fugacity):
                        fixed_gas_reactants.append(
                            vs.FixedGasReactant(
                                name=name,
                                log_moles=valuation[self.registry.id(log_moles)].value,
                                log_fugacity=valuation[self.registry.id(log_fugacity)].value,
                            ),
                        )
                    case SolidSolutionReactant(
                        name=name, amount=log_moles, titration_rate=titration_rate, end_members=end_members
                    ):
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
                    case CombinedReactant(amount=log_moles, titration_rate=titration_rate, components=components):
                        parent_log_moles = valuation[self.registry.id(log_moles)].value
                        parent_titration_rate = valuation[self.registry.id(titration_rate)].value
                        for component_name, component in components.items():
                            component_log_moles = (
                                cast(np.float64, np.log10(component.fraction.value)) + parent_log_moles
                            )
                            if component.relative_rate is not None:
                                component_relative_rate = valuation[self.registry.id(component.relative_rate)].value
                            else:
                                component_relative_rate = component.fraction.value
                            component_titration_rate = parent_titration_rate * component_relative_rate
                            match component.type:
                                case ReactantType.MINERAL:
                                    mineral_reactants.append(
                                        vs.MineralReactant(
                                            name=component_name,
                                            log_moles=component_log_moles,
                                            titration_rate=component_titration_rate,
                                        ),
                                    )
                                case ReactantType.AQUEOUS:
                                    aqueous_reactants.append(
                                        vs.AqueousReactant(
                                            name=component_name,
                                            log_moles=component_log_moles,
                                            titration_rate=component_titration_rate,
                                        ),
                                    )
                                case ReactantType.GAS:
                                    gas_reactants.append(
                                        vs.GasReactant(
                                            name=component_name,
                                            log_moles=component_log_moles,
                                            titration_rate=component_titration_rate,
                                        ),
                                    )
                                case ReactantType.ELEMENT:
                                    element_reactants.append(
                                        vs.ElementReactant(
                                            name=component_name,
                                            log_moles=component_log_moles,
                                            titration_rate=component_titration_rate,
                                        ),
                                    )
                                case ReactantType.SPECIAL:
                                    assert component.composition is not None
                                    special_reactants.append(
                                        vs.SpecialReactant(
                                            name=component_name,
                                            log_moles=component_log_moles,
                                            titration_rate=component_titration_rate,
                                            composition=[
                                                vs.SpecialReactantComposition(element=k, count=v)
                                                for k, v in component.composition.items()
                                            ],
                                        ),
                                    )
                                case ReactantType.SOLID_SOLUTION:
                                    assert component.end_members is not None
                                    solid_solution_reactants.append(
                                        vs.SolidSolutionReactant(
                                            name=component_name,
                                            log_moles=component_log_moles,
                                            titration_rate=component_titration_rate,
                                            end_members=[
                                                vs.SolidSolutionReactantEndMembers(
                                                    name=end_member_name,
                                                    fraction=valuation[self.registry.id(end_member_parameter)].value,
                                                )
                                                for end_member_name, end_member_parameter in component.end_members.items()
                                            ],
                                        ),
                                    )
                                case _:
                                    raise Exception(f"unexpected combined component type {component.type}")
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
            )
        except Exception as e:
            raise Exception("cannot generate Point from config") from e
