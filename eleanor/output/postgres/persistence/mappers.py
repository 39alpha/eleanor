from dataclasses import asdict, is_dataclass

import eleanor.equilibrium_space as core_es
import eleanor.order as core_order
import eleanor.variable_space as core_vs

from ....exceptions import EleanorException
from ....kernel.config import Config as KernelConfig
from ....kernel.config import resolve_settings as resolve_kernel_settings
from ....typing import cast
from . import models


def _to_dict_payload(value: object, field_name: str) -> dict[str, object]:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if not isinstance(value, dict):
        raise EleanorException(f"{field_name} must serialize to a dict")
    return cast(dict[str, object], value)


def to_order_model(order: core_order.Order) -> models.OrderModel:
    if order.name is None:
        raise EleanorException("order name is required")
    if order.eleanor_version is None:
        raise EleanorException("order eleanor_version is required before persistence")
    return models.OrderModel(
        id=order.id,
        name=order.name,
        tag=order.tag,
        eleanor_version=order.eleanor_version,
        raw=_to_dict_payload(order.raw, "order.raw"),
        create_date=order.create_date,
    )


def from_order_model(model: models.OrderModel) -> core_order.Order:
    raw = cast(core_order.SuborderRaw, cast(object, dict(model.raw)))
    order = core_order.Order(raw, order_id=model.id, tag=model.tag, create_date=model.create_date)
    order.eleanor_version = model.eleanor_version
    return order


def to_kernel_config_model(config: KernelConfig) -> models.KernelConfigModel:
    return models.KernelConfigModel(
        type=config.type,
        settings=_to_dict_payload(config.resolved_settings(), "kernel.settings"),
    )


def from_kernel_config_model(model: models.KernelConfigModel) -> KernelConfig:
    settings = resolve_kernel_settings(model.type, dict(model.settings))
    return KernelConfig(type=model.type, settings=settings)


def to_vs_point_model(point: core_vs.Point, order_id: int) -> models.VSPointModel:
    return models.VSPointModel(
        order_id=order_id,
        kernel=to_kernel_config_model(point.kernel),
        water_mass=point.water_mass,
        temperature=point.temperature,
        pressure=point.pressure,
        elements=[models.VSElementModel(name=e.name, log_molality=e.log_molality) for e in point.elements],
        species=[models.VSSpeciesModel(name=s.name, value=s.value) for s in point.species],
        suppressions=[
            models.VSSuppressionModel(
                name=s.name,
                type=s.type,
                exceptions=[models.VSSuppressionExceptionModel(name=se.name) for se in s.exceptions],
            )
            for s in point.suppressions
        ],
        mineral_reactants=[
            models.VSMineralReactantModel(name=r.name, log_moles=r.log_moles, titration_rate=r.titration_rate)
            for r in point.mineral_reactants
        ],
        aqueous_reactants=[
            models.VSAqueousReactantModel(name=r.name, log_moles=r.log_moles, titration_rate=r.titration_rate)
            for r in point.aqueous_reactants
        ],
        gas_reactants=[
            models.VSGasReactantModel(name=r.name, log_moles=r.log_moles, titration_rate=r.titration_rate)
            for r in point.gas_reactants
        ],
        element_reactants=[
            models.VSElementReactantModel(name=r.name, log_moles=r.log_moles, titration_rate=r.titration_rate)
            for r in point.element_reactants
        ],
        special_reactants=[
            models.VSSpecialReactantModel(
                name=r.name,
                log_moles=r.log_moles,
                titration_rate=r.titration_rate,
                composition=[
                    models.VSSpecialReactantCompositionModel(element=c.element, count=c.count) for c in r.composition
                ],
            )
            for r in point.special_reactants
        ],
        fixed_gas_reactants=[
            models.VSFixedGasReactantModel(name=r.name, log_moles=r.log_moles, log_fugacity=r.log_fugacity)
            for r in point.fixed_gas_reactants
        ],
        solid_solution_reactants=[
            models.VSSolidSolutionReactantModel(
                name=r.name,
                log_moles=r.log_moles,
                titration_rate=r.titration_rate,
                end_members=[
                    models.VSSolidSolutionReactantEndMembersModel(name=em.name, fraction=em.fraction)
                    for em in r.end_members
                ],
            )
            for r in point.solid_solution_reactants
        ],
        glass_reactants=[
            models.VSGlassReactantModel(
                name=r.name,
                log_moles=r.log_moles,
                titration_rate=r.titration_rate,
                oxides=[
                    models.VSGlassReactantOxideModel(
                        name=o.name,
                        fraction=o.fraction,
                        log_moles=o.log_moles,
                        titration_rate=o.titration_rate,
                        composition=[
                            models.VSGlassReactantOxideCompositionModel(element=oc.element, count=oc.count)
                            for oc in o.composition
                        ],
                    )
                    for o in r.oxides
                ],
            )
            for r in point.glass_reactants
        ],
        es_points=[to_es_point_model(es_point) for es_point in point.es_points],
        scratch=None if point.scratch is None else models.VSScratchModel(zip=point.scratch.zip),
        exit_code=point.exit_code,
        create_date=point.create_date,
        start_date=point.start_date,
        complete_date=point.complete_date,
    )


def to_es_point_model(point: core_es.Point) -> models.ESPointModel:
    return models.ESPointModel(
        stage=point.stage,
        log_xi=point.log_xi,
        temperature=point.temperature,
        pressure=point.pressure,
        pH=point.pH,
        log_fO2=point.log_fO2,
        log_activity_water=point.log_activity_water,
        mole_fraction_water=point.mole_fraction_water,
        log_gamma_water=point.log_gamma_water,
        Eh=point.Eh,
        pe=point.pe,
        Ah=point.Ah,
        pcH=point.pcH,
        pHCl=point.pHCl,
        log_ionic_strength=point.log_ionic_strength,
        log_stoichiometric_ionic_strength=point.log_stoichiometric_ionic_strength,
        log_ionic_asymmetry=point.log_ionic_asymmetry,
        log_stoichiometric_ionic_asymmetry=point.log_stoichiometric_ionic_asymmetry,
        osmotic_coefficient=point.osmotic_coefficient,
        stoichiometric_osmotic_coefficient=point.stoichiometric_osmotic_coefficient,
        log_sum_molalities=point.log_sum_molalities,
        log_sum_stoichiometric_molalities=point.log_sum_stoichiometric_molalities,
        charge_imbalance=point.charge_imbalance,
        expected_charge_imbalance=point.expected_charge_imbalance,
        sigma=point.sigma,
        charge_discrepancy=point.charge_discrepancy,
        anions=point.anions,
        cations=point.cations,
        total_charge=point.total_charge,
        mean_charge=point.mean_charge,
        solute_mass=point.solute_mass,
        solvent_mass=point.solvent_mass,
        solution_mass=point.solution_mass,
        solution_volume=point.solution_volume,
        tds=point.tds,
        solute_fraction=point.solute_fraction,
        solvent_fraction=point.solvent_fraction,
        extended_alkalinity=point.extended_alkalinity,
        overall_affinity=point.overall_affinity,
        reactant_mass_reacted=point.reactant_mass_reacted,
        reactant_mass_remaining=point.reactant_mass_remaining,
        solid_mass_change=point.solid_mass_change,
        solid_mass_created=point.solid_mass_created,
        solid_mass_destroyed=point.solid_mass_destroyed,
        solid_volume_change=point.solid_volume_change,
        solid_volume_created=point.solid_volume_created,
        solid_volume_destroyed=point.solid_volume_destroyed,
        start_date=point.start_date,
        complete_date=point.complete_date,
        custom_properties=dict(point.custom_properties),
        elements=[
            models.ESElementModel(name=e.name, log_molality=e.log_molality, mass_fraction=e.mass_fraction)
            for e in point.elements
        ],
        aqueous_species=[
            models.ESAqueousSpeciesModel(
                name=s.name,
                log_molality=s.log_molality,
                log_activity=s.log_activity,
                log_gamma=s.log_gamma,
            )
            for s in point.aqueous_species
        ],
        pure_solids=[
            models.ESPureSolidModel(
                name=s.name,
                log_qk=s.log_qk,
                affinity=s.affinity,
                log_moles=s.log_moles,
                log_mass=s.log_mass,
                log_volume=s.log_volume,
            )
            for s in point.pure_solids
        ],
        solid_solutions=[
            models.ESSolidSolutionModel(
                name=s.name,
                log_qk=s.log_qk,
                affinity=s.affinity,
                log_moles=s.log_moles,
                log_mass=s.log_mass,
                log_volume=s.log_volume,
                end_members=[
                    models.ESEndMemberModel(
                        name=em.name,
                        log_qk=em.log_qk,
                        affinity=em.affinity,
                        log_moles=em.log_moles,
                        log_mass=em.log_mass,
                        log_volume=em.log_volume,
                    )
                    for em in s.end_members
                ],
            )
            for s in point.solid_solutions
        ],
        gases=[models.ESGasModel(name=g.name, log_fugacity=g.log_fugacity) for g in point.gases],
        reactants=[
            models.ESReactantModel(
                name=r.name,
                affinity=r.affinity,
                relative_rate=r.relative_rate,
                log_moles_reacted=r.log_moles_reacted,
                log_moles_remaining=r.log_moles_remaining,
                log_mass_reacted=r.log_mass_reacted,
                log_mass_remaining=r.log_mass_remaining,
            )
            for r in point.reactants
        ],
        redox_reactions=[
            models.ESRedoxReactionModel(
                couple=r.couple,
                Eh=r.Eh,
                pe=r.pe,
                log_fO2=r.log_fO2,
                Ah=r.Ah,
            )
            for r in point.redox_reactions
        ],
    )


def from_vs_point_model(model: models.VSPointModel) -> core_vs.Point:
    return core_vs.Point(
        order_id=model.order_id,
        kernel=from_kernel_config_model(model.kernel),
        water_mass=model.water_mass,
        temperature=model.temperature,
        pressure=model.pressure,
        elements=[core_vs.Element(name=e.name, log_molality=e.log_molality) for e in model.elements],
        species=[core_vs.Species(name=s.name, value=s.value) for s in model.species],
        suppressions=[
            core_vs.Suppression(
                name=s.name,
                type=s.type,
                exceptions=[core_vs.SuppressionException(name=se.name) for se in s.exceptions],
            )
            for s in model.suppressions
        ],
        mineral_reactants=[
            core_vs.MineralReactant(
                name=r.name,
                log_moles=r.log_moles,
                titration_rate=r.titration_rate,
            )
            for r in model.mineral_reactants
        ],
        aqueous_reactants=[
            core_vs.AqueousReactant(
                name=r.name,
                log_moles=r.log_moles,
                titration_rate=r.titration_rate,
            )
            for r in model.aqueous_reactants
        ],
        gas_reactants=[
            core_vs.GasReactant(
                name=r.name,
                log_moles=r.log_moles,
                titration_rate=r.titration_rate,
            )
            for r in model.gas_reactants
        ],
        element_reactants=[
            core_vs.ElementReactant(
                name=r.name,
                log_moles=r.log_moles,
                titration_rate=r.titration_rate,
            )
            for r in model.element_reactants
        ],
        special_reactants=[
            core_vs.SpecialReactant(
                name=r.name,
                log_moles=r.log_moles,
                titration_rate=r.titration_rate,
                composition=[
                    core_vs.SpecialReactantComposition(element=c.element, count=c.count) for c in r.composition
                ],
            )
            for r in model.special_reactants
        ],
        fixed_gas_reactants=[
            core_vs.FixedGasReactant(
                name=r.name,
                log_moles=r.log_moles,
                log_fugacity=r.log_fugacity,
            )
            for r in model.fixed_gas_reactants
        ],
        solid_solution_reactants=[
            core_vs.SolidSolutionReactant(
                name=r.name,
                log_moles=r.log_moles,
                titration_rate=r.titration_rate,
                end_members=[
                    core_vs.SolidSolutionReactantEndMembers(name=em.name, fraction=em.fraction) for em in r.end_members
                ],
            )
            for r in model.solid_solution_reactants
        ],
        glass_reactants=[
            core_vs.GlassReactant(
                name=r.name,
                log_moles=r.log_moles,
                titration_rate=r.titration_rate,
                oxides=[
                    core_vs.GlassReactantOxide(
                        name=o.name,
                        fraction=o.fraction,
                        log_moles=o.log_moles,
                        titration_rate=o.titration_rate,
                        composition=[
                            core_vs.GlassReactantOxideComposition(element=oc.element, count=oc.count)
                            for oc in o.composition
                        ],
                    )
                    for o in r.oxides
                ],
            )
            for r in model.glass_reactants
        ],
        es_points=[from_es_point_model(cast(models.ESPointModel, es_point)) for es_point in model.es_points],
        scratch=None if model.scratch is None else core_vs.Scratch(zip=model.scratch.zip),
        exit_code=model.exit_code,
        create_date=model.create_date,
        start_date=model.start_date,
        complete_date=model.complete_date,
    )


def from_es_point_model(model: models.ESPointModel) -> core_es.Point:
    return core_es.Point(
        stage=model.stage,
        log_xi=model.log_xi,
        temperature=model.temperature,
        pressure=model.pressure,
        pH=model.pH,
        log_fO2=model.log_fO2,
        log_activity_water=model.log_activity_water,
        mole_fraction_water=model.mole_fraction_water,
        log_gamma_water=model.log_gamma_water,
        Eh=model.Eh,
        pe=model.pe,
        Ah=model.Ah,
        pcH=model.pcH,
        pHCl=model.pHCl,
        log_ionic_strength=model.log_ionic_strength,
        log_stoichiometric_ionic_strength=model.log_stoichiometric_ionic_strength,
        log_ionic_asymmetry=model.log_ionic_asymmetry,
        log_stoichiometric_ionic_asymmetry=model.log_stoichiometric_ionic_asymmetry,
        osmotic_coefficient=model.osmotic_coefficient,
        stoichiometric_osmotic_coefficient=model.stoichiometric_osmotic_coefficient,
        log_sum_molalities=model.log_sum_molalities,
        log_sum_stoichiometric_molalities=model.log_sum_stoichiometric_molalities,
        charge_imbalance=model.charge_imbalance,
        expected_charge_imbalance=model.expected_charge_imbalance,
        sigma=model.sigma,
        charge_discrepancy=model.charge_discrepancy,
        anions=model.anions,
        cations=model.cations,
        total_charge=model.total_charge,
        mean_charge=model.mean_charge,
        solute_mass=model.solute_mass,
        solvent_mass=model.solvent_mass,
        solution_mass=model.solution_mass,
        solution_volume=model.solution_volume,
        tds=model.tds,
        solute_fraction=model.solute_fraction,
        solvent_fraction=model.solvent_fraction,
        extended_alkalinity=model.extended_alkalinity,
        overall_affinity=model.overall_affinity,
        reactant_mass_reacted=model.reactant_mass_reacted,
        reactant_mass_remaining=model.reactant_mass_remaining,
        solid_mass_change=model.solid_mass_change,
        solid_mass_created=model.solid_mass_created,
        solid_mass_destroyed=model.solid_mass_destroyed,
        solid_volume_change=model.solid_volume_change,
        solid_volume_created=model.solid_volume_created,
        solid_volume_destroyed=model.solid_volume_destroyed,
        start_date=model.start_date,
        complete_date=model.complete_date,
        custom_properties=dict(model.custom_properties),
        elements=[
            core_es.Element(name=e.name, log_molality=e.log_molality, mass_fraction=e.mass_fraction)
            for e in model.elements
        ],
        aqueous_species=[
            core_es.AqueousSpecies(
                name=s.name,
                log_molality=s.log_molality,
                log_activity=s.log_activity,
                log_gamma=s.log_gamma,
            )
            for s in model.aqueous_species
        ],
        pure_solids=[
            core_es.PureSolid(
                name=s.name,
                log_qk=s.log_qk,
                affinity=s.affinity,
                log_moles=s.log_moles,
                log_mass=s.log_mass,
                log_volume=s.log_volume,
            )
            for s in model.pure_solids
        ],
        solid_solutions=[
            core_es.SolidSolution(
                name=s.name,
                log_qk=s.log_qk,
                affinity=s.affinity,
                log_moles=s.log_moles,
                log_mass=s.log_mass,
                log_volume=s.log_volume,
                end_members=[
                    core_es.EndMember(
                        name=em.name,
                        log_qk=em.log_qk,
                        affinity=em.affinity,
                        log_moles=em.log_moles,
                        log_mass=em.log_mass,
                        log_volume=em.log_volume,
                    )
                    for em in s.end_members
                ],
            )
            for s in model.solid_solutions
        ],
        gases=[core_es.Gas(name=g.name, log_fugacity=g.log_fugacity) for g in model.gases],
        reactants=[
            core_es.Reactant(
                name=r.name,
                affinity=r.affinity,
                relative_rate=r.relative_rate,
                log_moles_reacted=r.log_moles_reacted,
                log_moles_remaining=r.log_moles_remaining,
                log_mass_reacted=r.log_mass_reacted,
                log_mass_remaining=r.log_mass_remaining,
            )
            for r in model.reactants
        ],
        redox_reactions=[
            core_es.RedoxReaction(
                couple=r.couple,
                Eh=r.Eh,
                pe=r.pe,
                log_fO2=r.log_fO2,
                Ah=r.Ah,
            )
            for r in model.redox_reactions
        ],
    )
