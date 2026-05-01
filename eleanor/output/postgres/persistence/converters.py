"""Pure converter functions between core dataclasses and DB row dicts.

Each converter is a pure Python function taking a core dataclass (plus the
relevant parent FK id where applicable) and returning a
``dict[str, object]`` whose keys are the table's column names from
:mod:`schema` -- in any order, since psycopg3 binds named ``%(col)s``
placeholders by name. JSONB values are wrapped with
:class:`psycopg.types.json.Jsonb` so the DB driver knows to dump them as
``jsonb`` rather than fall back to the registered text adapter.

Reverse converters (``row_to_*``) are provided for the row shapes the
sink actually reads: orders (for ``get_order``) and scratch (for
``get_scratch_entry``). Tests round-trip via ``from_*_row(to_*_row(...))``
without ever touching a DB.

``-math.inf`` is materialised explicitly for the three saturation-state
tables (``equilibrium_pure_solids``, ``equilibrium_solid_solutions``,
``equilibrium_end_members``). Their ``log_moles`` / ``log_mass`` /
``log_volume`` columns are ``NOT NULL`` with a ``-Infinity`` default at
the schema level, but bulk INSERTs ship every key explicitly (so the
column default never triggers); the converter substitutes ``-math.inf``
whenever the dataclass field is ``None``.
"""

import math
from dataclasses import dataclass
from datetime import datetime

from psycopg.types.json import Jsonb

import eleanor.equilibrium_space as core_es
import eleanor.order as core_order
import eleanor.variable_space as core_vs

from ....exceptions import EleanorException
from ....kernel.config import Config as KernelConfig
from ....kernel.config import resolve_settings as resolve_kernel_settings
from ....typing import cast


def _or_neg_inf(value: float | None) -> float:
    """Return ``value`` or ``-math.inf`` when ``value`` is ``None``.

    Used by the saturation-state ES tables (``equilibrium_pure_solids``,
    ``equilibrium_solid_solutions``, ``equilibrium_end_members``). Their
    ``log_moles`` / ``log_mass`` / ``log_volume`` columns are ``NOT NULL``
    with a ``-Infinity`` schema-level default. Bulk INSERTs ship every
    key explicitly, so the column default never fires; we materialise
    ``-Infinity`` here.
    """
    return value if value is not None else -math.inf


def _normalise_dict(value: object, field_name: str) -> dict[str, object]:
    """Coerce ``value`` to a plain ``dict[str, object]`` or raise.

    Callers pass payloads like ``order.raw`` (already a dict) or the
    output of :meth:`KernelConfig.resolved_settings` (a dataclass that
    needs to be flattened). Anything that is neither raises
    :class:`EleanorException` so the failure surfaces at the converter
    boundary rather than as a JSON encoding error inside psycopg.
    """
    from dataclasses import asdict, is_dataclass

    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if not isinstance(value, dict):
        raise EleanorException(f"{field_name} must serialize to a dict")
    return cast(dict[str, object], value)


def order_to_row(order: core_order.Order) -> dict[str, object]:
    """Build the ``orders`` row dict for ``order``.

    Raises :class:`EleanorException` if identifying metadata is missing.
    The caller is responsible for stamping ``eleanor_version`` before
    handing the order over.
    """
    if order.eleanor_version is None:
        raise EleanorException("order eleanor_version is required before persistence")
    return {
        "name": order.name,
        "tag": order.tag,
        "eleanor_version": order.eleanor_version,
        "raw": Jsonb(_normalise_dict(order.raw, "order.raw")),
        "create_date": order.create_date,
    }


@dataclass(frozen=True, slots=True)
class OrderRecord(object):
    """Read-side projection of an ``orders`` row.

    The full ``Order`` dataclass tree is rich (suborders, transformers,
    parameters); reconstructing it from a single row is more work than
    the sink's read paths actually need. ``OrderRecord`` carries only the
    fields :meth:`PostgresSink.begin_run` consults: identifying metadata
    plus the raw config dict for any future EQL-driven re-parsing.
    """

    id: int
    name: str
    tag: str
    eleanor_version: str
    raw: dict[str, object]
    create_date: datetime


def row_to_order_record(row: dict[str, object]) -> OrderRecord:
    """Inverse of :func:`order_to_row` for the ``get_order`` read path."""
    return OrderRecord(
        id=cast(int, row["id"]),
        name=cast(str, row["name"]),
        tag=cast(str, row["tag"]),
        eleanor_version=cast(str, row["eleanor_version"]),
        raw=cast(dict[str, object], row["raw"]),
        create_date=cast(datetime, row["create_date"]),
    )


def vs_point_to_row(point: core_vs.Point, order_id: int) -> dict[str, object]:
    return {
        "order_id": order_id,
        "water_mass": point.water_mass,
        "temperature": point.temperature,
        "pressure": point.pressure,
        "exit_code": point.exit_code,
        "create_date": point.create_date,
        "start_date": point.start_date,
        "complete_date": point.complete_date,
    }


def kernel_to_row(kernel: KernelConfig, variable_space_id: int) -> dict[str, object]:
    """Build the ``kernel`` row.

    ``id`` is supplied explicitly (it is both the PK and the FK to
    ``variable_space.id``) -- this is one of the two tables whose primary
    key is *not* identity-generated.
    """
    return {
        "id": variable_space_id,
        "type": kernel.type,
        "settings": Jsonb(_normalise_dict(kernel.resolved_settings(), "kernel.settings")),
    }


def scratch_to_row(scratch: core_vs.Scratch, variable_space_id: int) -> dict[str, object]:
    """Build the ``scratch`` row. ``id`` doubles as the FK, like ``kernel``."""
    return {
        "id": variable_space_id,
        "zip": scratch.zip,
    }


def element_to_row(element: core_vs.Element, variable_space_id: int) -> dict[str, object]:
    return {
        "variable_space_id": variable_space_id,
        "name": element.name,
        "log_molality": element.log_molality,
    }


def species_to_row(species: core_vs.Species, variable_space_id: int) -> dict[str, object]:
    return {
        "variable_space_id": variable_space_id,
        "name": species.name,
        "value": species.value,
    }


def suppression_to_row(
    suppression: core_vs.Suppression,
    variable_space_id: int,
) -> dict[str, object]:
    return {
        "variable_space_id": variable_space_id,
        "name": suppression.name,
        "type": suppression.type,
    }


def suppression_exception_to_row(
    exception: core_vs.SuppressionException,
    suppression_id: int,
) -> dict[str, object]:
    return {
        "suppression_id": suppression_id,
        "name": exception.name,
    }


def _reactant_row(
    name: str,
    log_moles: float,
    titration_rate: float,
    variable_space_id: int,
) -> dict[str, object]:
    return {
        "variable_space_id": variable_space_id,
        "name": name,
        "log_moles": log_moles,
        "titration_rate": titration_rate,
    }


def mineral_reactant_to_row(r: core_vs.MineralReactant, variable_space_id: int) -> dict[str, object]:
    return _reactant_row(r.name, r.log_moles, r.titration_rate, variable_space_id)


def aqueous_reactant_to_row(r: core_vs.AqueousReactant, variable_space_id: int) -> dict[str, object]:
    return _reactant_row(r.name, r.log_moles, r.titration_rate, variable_space_id)


def gas_reactant_to_row(r: core_vs.GasReactant, variable_space_id: int) -> dict[str, object]:
    return _reactant_row(r.name, r.log_moles, r.titration_rate, variable_space_id)


def element_reactant_to_row(r: core_vs.ElementReactant, variable_space_id: int) -> dict[str, object]:
    return _reactant_row(r.name, r.log_moles, r.titration_rate, variable_space_id)


def special_reactant_to_row(r: core_vs.SpecialReactant, variable_space_id: int) -> dict[str, object]:
    return _reactant_row(r.name, r.log_moles, r.titration_rate, variable_space_id)


def special_reactant_composition_to_row(
    composition: core_vs.SpecialReactantComposition,
    special_reactant_id: int,
) -> dict[str, object]:
    return {
        "special_reactant_id": special_reactant_id,
        "element": composition.element,
        "count": composition.count,
    }


def fixed_gas_reactant_to_row(
    r: core_vs.FixedGasReactant,
    variable_space_id: int,
) -> dict[str, object]:
    return {
        "variable_space_id": variable_space_id,
        "name": r.name,
        "log_moles": r.log_moles,
        "log_fugacity": r.log_fugacity,
    }


def solid_solution_reactant_to_row(
    r: core_vs.SolidSolutionReactant,
    variable_space_id: int,
) -> dict[str, object]:
    return _reactant_row(r.name, r.log_moles, r.titration_rate, variable_space_id)


def solid_solution_reactant_end_member_to_row(
    em: core_vs.SolidSolutionReactantEndMembers,
    solid_solution_reactant_id: int,
) -> dict[str, object]:
    return {
        "solid_solution_reactant_id": solid_solution_reactant_id,
        "name": em.name,
        "fraction": em.fraction,
    }


def glass_reactant_to_row(r: core_vs.GlassReactant, variable_space_id: int) -> dict[str, object]:
    return _reactant_row(r.name, r.log_moles, r.titration_rate, variable_space_id)


def glass_reactant_oxide_to_row(
    oxide: core_vs.GlassReactantOxide,
    glass_reactant_id: int,
) -> dict[str, object]:
    return {
        "glass_reactant_id": glass_reactant_id,
        "name": oxide.name,
        "fraction": oxide.fraction,
        "log_moles": oxide.log_moles,
        "titration_rate": oxide.titration_rate,
    }


def glass_reactant_oxide_composition_to_row(
    composition: core_vs.GlassReactantOxideComposition,
    glass_reactant_oxide_id: int,
) -> dict[str, object]:
    return {
        "glass_reactant_oxide_id": glass_reactant_oxide_id,
        "element": composition.element,
        "count": composition.count,
    }


def es_point_to_row(point: core_es.Point, variable_space_id: int) -> dict[str, object]:
    """Build the ``equilibrium_space`` row.

    All ~50 columns are spelled out explicitly: every batch INSERT must
    have the same key set (psycopg's ``executemany`` requires uniform
    parameter mappings), so we emit the same row shape for every ES point
    regardless of which optional fields the kernel populated.
    """
    return {
        "variable_space_id": variable_space_id,
        "stage": point.stage,
        "log_xi": point.log_xi,
        "temperature": point.temperature,
        "pressure": point.pressure,
        "pH": point.pH,
        "log_fO2": point.log_fO2,
        "log_activity_water": point.log_activity_water,
        "mole_fraction_water": point.mole_fraction_water,
        "log_gamma_water": point.log_gamma_water,
        "Eh": point.Eh,
        "pe": point.pe,
        "Ah": point.Ah,
        "pcH": point.pcH,
        "pHCl": point.pHCl,
        "log_ionic_strength": point.log_ionic_strength,
        "log_stoichiometric_ionic_strength": point.log_stoichiometric_ionic_strength,
        "log_ionic_asymmetry": point.log_ionic_asymmetry,
        "log_stoichiometric_ionic_asymmetry": point.log_stoichiometric_ionic_asymmetry,
        "osmotic_coefficient": point.osmotic_coefficient,
        "stoichiometric_osmotic_coefficient": point.stoichiometric_osmotic_coefficient,
        "log_sum_molalities": point.log_sum_molalities,
        "log_sum_stoichiometric_molalities": point.log_sum_stoichiometric_molalities,
        "charge_imbalance": point.charge_imbalance,
        "expected_charge_imbalance": point.expected_charge_imbalance,
        "sigma": point.sigma,
        "charge_discrepancy": point.charge_discrepancy,
        "anions": point.anions,
        "cations": point.cations,
        "total_charge": point.total_charge,
        "mean_charge": point.mean_charge,
        "solute_mass": point.solute_mass,
        "solvent_mass": point.solvent_mass,
        "solution_mass": point.solution_mass,
        "solution_volume": point.solution_volume,
        "tds": point.tds,
        "solute_fraction": point.solute_fraction,
        "solvent_fraction": point.solvent_fraction,
        "extended_alkalinity": point.extended_alkalinity,
        "overall_affinity": point.overall_affinity,
        "reactant_mass_reacted": point.reactant_mass_reacted,
        "reactant_mass_remaining": point.reactant_mass_remaining,
        "solid_mass_change": point.solid_mass_change,
        "solid_mass_created": point.solid_mass_created,
        "solid_mass_destroyed": point.solid_mass_destroyed,
        "solid_volume_change": point.solid_volume_change,
        "solid_volume_created": point.solid_volume_created,
        "solid_volume_destroyed": point.solid_volume_destroyed,
        "start_date": point.start_date,
        "complete_date": point.complete_date,
        "custom_properties": Jsonb(dict(point.custom_properties)),
    }


def es_element_to_row(element: core_es.Element, equilibrium_space_id: int) -> dict[str, object]:
    return {
        "equilibrium_space_id": equilibrium_space_id,
        "name": element.name,
        "log_molality": element.log_molality,
        "mass_fraction": element.mass_fraction,
    }


def es_aqueous_species_to_row(
    species: core_es.AqueousSpecies,
    equilibrium_space_id: int,
) -> dict[str, object]:
    return {
        "equilibrium_space_id": equilibrium_space_id,
        "name": species.name,
        "log_molality": species.log_molality,
        "log_activity": species.log_activity,
        "log_gamma": species.log_gamma,
    }


def es_pure_solid_to_row(
    solid: core_es.PureSolid,
    equilibrium_space_id: int,
) -> dict[str, object]:
    return {
        "equilibrium_space_id": equilibrium_space_id,
        "name": solid.name,
        "log_qk": solid.log_qk,
        "affinity": solid.affinity,
        "log_moles": _or_neg_inf(solid.log_moles),
        "log_mass": _or_neg_inf(solid.log_mass),
        "log_volume": _or_neg_inf(solid.log_volume),
    }


def es_solid_solution_to_row(
    ss: core_es.SolidSolution,
    equilibrium_space_id: int,
) -> dict[str, object]:
    return {
        "equilibrium_space_id": equilibrium_space_id,
        "name": ss.name,
        "log_qk": ss.log_qk,
        "affinity": ss.affinity,
        "log_moles": _or_neg_inf(ss.log_moles),
        "log_mass": _or_neg_inf(ss.log_mass),
        "log_volume": _or_neg_inf(ss.log_volume),
    }


def es_end_member_to_row(
    em: core_es.EndMember,
    equilibrium_solid_solution_id: int,
) -> dict[str, object]:
    return {
        "equilibrium_solid_solution_id": equilibrium_solid_solution_id,
        "name": em.name,
        "log_qk": em.log_qk,
        "affinity": em.affinity,
        "log_moles": _or_neg_inf(em.log_moles),
        "log_mass": _or_neg_inf(em.log_mass),
        "log_volume": _or_neg_inf(em.log_volume),
    }


def es_gas_to_row(gas: core_es.Gas, equilibrium_space_id: int) -> dict[str, object]:
    return {
        "equilibrium_space_id": equilibrium_space_id,
        "name": gas.name,
        "log_fugacity": gas.log_fugacity,
    }


def es_reactant_to_row(
    reactant: core_es.Reactant,
    equilibrium_space_id: int,
) -> dict[str, object]:
    return {
        "equilibrium_space_id": equilibrium_space_id,
        "name": reactant.name,
        "affinity": reactant.affinity,
        "relative_rate": reactant.relative_rate,
        "log_moles_reacted": reactant.log_moles_reacted,
        "log_moles_remaining": reactant.log_moles_remaining,
        "log_mass_reacted": reactant.log_mass_reacted,
        "log_mass_remaining": reactant.log_mass_remaining,
    }


def es_redox_reaction_to_row(
    reaction: core_es.RedoxReaction,
    equilibrium_space_id: int,
) -> dict[str, object]:
    return {
        "equilibrium_space_id": equilibrium_space_id,
        "couple": reaction.couple,
        "Eh": reaction.Eh,
        "pe": reaction.pe,
        "log_fO2": reaction.log_fO2,
        "Ah": reaction.Ah,
    }


@dataclass(frozen=True, slots=True)
class ScratchEntry(object):
    """Read-side projection of a ``scratch`` row joined with its parent.

    Read by :func:`PostgresSink.tools.load_scratch_entry`.
    """

    variable_space_id: int
    exit_code: int
    zip: bytes


def row_to_scratch_entry(row: dict[str, object]) -> ScratchEntry:
    """Reconstruct a :class:`ScratchEntry` from a joined ``scratch`` row.

    The query in ``repositories.get_scratch_entry`` is responsible for
    joining ``scratch`` and ``variable_space`` and returning
    ``(variable_space.id AS variable_space_id, variable_space.exit_code,
    scratch.zip)``. psycopg3 returns ``BYTEA`` columns as ``bytes``
    natively, so no ``memoryview`` handling is needed.
    """
    return ScratchEntry(
        variable_space_id=cast(int, row["variable_space_id"]),
        exit_code=cast(int, row["exit_code"]),
        zip=cast(bytes, row["zip"]),
    )


def row_to_kernel_config(row: dict[str, object]) -> KernelConfig:
    """Reconstruct a :class:`KernelConfig` from a ``kernel`` row.

    The kernel registry's :func:`resolve_settings` handles the
    plugin-specific dict-to-Settings dispatch; we just pass the JSONB
    payload through.
    """
    type_name = cast(str, row["type"])
    settings_dict = cast(dict[str, object], row["settings"])
    settings = resolve_kernel_settings(type_name, dict(settings_dict))
    return KernelConfig(type=type_name, settings=settings)
