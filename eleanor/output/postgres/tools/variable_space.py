import uuid
from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg import sql
from psycopg.rows import class_row, dict_row

from eleanor.config.kernel import KernelConfig
from eleanor.exceptions import EleanorError
from eleanor.order import Order, Suppression
from eleanor.output.postgres.persistence import connection, converters
from eleanor.output.postgres.persistence.repositories import get_order
from eleanor.output.postgres.settings import PostgresDatabaseSettings
from eleanor.reactants import (
    AbstractReactant,
    AqueousReactant,
    ElementReactant,
    FixedGasReactant,
    GasReactant,
    MineralReactant,
    SolidSolutionReactant,
    SpecialReactant,
    TitratedReactant,
)
from eleanor.util import (
    guard_is_float,
    guard_is_instance,
    guard_is_int,
    guard_is_str,
    guard_is_str_or_none,
    guard_is_uuid,
    require_int,
    require_str,
)


@dataclass
class _PointRow:
    id: uuid.UUID
    order_id: uuid.UUID
    water_mass: float
    temperature: float
    pressure: float
    create_date: datetime

    def __post_init__(self) -> None:
        guard_is_uuid(self.id, "id")
        guard_is_uuid(self.order_id, "order_id")
        guard_is_float(self.water_mass, "water_mass")
        guard_is_float(self.temperature, "temperature")
        guard_is_float(self.pressure, "pressure")
        guard_is_instance(self.create_date, datetime, "create_date")


def get_point_row(conn: psycopg.Connection, vs_id: uuid.UUID) -> _PointRow | None:
    with conn.cursor(row_factory=class_row(_PointRow)) as cur:
        return cur.execute(
            "SELECT id, order_id, water_mass, temperature, pressure, create_date FROM variable_space WHERE id = %s",
            (vs_id,),
        ).fetchone()


def get_kernel_config(conn: psycopg.Connection, vs_id: uuid.UUID) -> KernelConfig:
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute("SELECT type, settings FROM kernel WHERE id = %s", (vs_id,)).fetchone()

    if row is None:
        msg = f"failed to fetch kernel settings for variable space point {vs_id}"
        raise EleanorError(msg)

    return converters.row_to_kernel_config(row)


@dataclass
class _ElementRow:
    name: str
    log_molality: float

    def __post_init__(self) -> None:
        guard_is_str(self.name, "name")
        guard_is_float(self.log_molality, "log_molality")


def get_elements(conn: psycopg.Connection, vs_id: uuid.UUID) -> dict[str, float]:
    elements: dict[str, float] = {}
    with conn.cursor(row_factory=class_row(_ElementRow)) as cur:
        _ = cur.execute("SELECT name, log_molality FROM elements WHERE variable_space_id = %s", (vs_id,))
        for row in cur:
            if row.name in elements:
                msg = f"duplicate element {row.name!r} found for variable space point {vs_id}"
                raise EleanorError(msg)
            elements[row.name] = row.log_molality
    return elements


@dataclass
class _SpeciesRow:
    name: str
    value: float

    def __post_init__(self) -> None:
        guard_is_str(self.name, "name")
        guard_is_float(self.value, "value")


def get_species(conn: psycopg.Connection, vs_id: uuid.UUID) -> dict[str, float]:
    species: dict[str, float] = {}
    with conn.cursor(row_factory=class_row(_SpeciesRow)) as cur:
        _ = cur.execute("SELECT name, value FROM species WHERE variable_space_id = %s", (vs_id,))
        for row in cur:
            if row.name in species:
                msg = f"duplicate species {row.name!r} found for variable space point {vs_id}"
                raise EleanorError(msg)
            species[row.name] = row.value
    return species


_SIMPLE_REACTANT_TABLES: dict[type[TitratedReactant], str] = {
    MineralReactant: "mineral_reactants",
    AqueousReactant: "aqueous_reactants",
    GasReactant: "gas_reactants",
    ElementReactant: "element_reactants",
}


def get_simple_reactants[T: TitratedReactant](
    conn: psycopg.Connection,
    reactant_class: type[T],
    vs_id: uuid.UUID,
) -> list[T]:
    query = sql.SQL(
        "SELECT name, log_moles AS amount, titration_rate FROM {table} WHERE variable_space_id = %s"
    ).format(table=sql.Identifier(_SIMPLE_REACTANT_TABLES[reactant_class]))
    with conn.cursor(row_factory=class_row(reactant_class)) as cur:
        return cur.execute(query, (vs_id,)).fetchall()


def get_fixed_gas_reactants(conn: psycopg.Connection, vs_id: uuid.UUID) -> list[FixedGasReactant]:
    with conn.cursor(row_factory=class_row(FixedGasReactant)) as cur:
        return cur.execute(
            """
            SELECT
                name, log_moles AS amount, log_fugacity AS fugacity
            FROM fixed_gas_reactants
            WHERE variable_space_id = %s
            """,
            (vs_id,),
        ).fetchall()


@dataclass
class _SpecialReactantRow:
    id: uuid.UUID
    name: str
    amount: float
    titration_rate: float
    element: str
    count: int

    def __post_init__(self) -> None:
        guard_is_uuid(self.id, "id")
        guard_is_str(self.name, "name")
        guard_is_float(self.amount, "amount")
        guard_is_float(self.titration_rate, "titration_rate")
        guard_is_str(self.element, "element")
        guard_is_int(self.count, "count")


def get_special_reactants(conn: psycopg.Connection, vs_id: uuid.UUID) -> list[SpecialReactant]:
    special_reactants: dict[uuid.UUID, SpecialReactant] = {}
    with conn.cursor(row_factory=class_row(_SpecialReactantRow)) as cur:
        _ = cur.execute(
            """
            SELECT
                id, name, log_moles AS amount, titration_rate, element, count
            FROM special_reactants sr
            JOIN special_reactant_compositions src ON sr.id = src.special_reactant_id
            WHERE variable_space_id = %s
            """,
            (vs_id,),
        )

        for row in cur:
            if row.id not in special_reactants:
                special_reactants[row.id] = SpecialReactant(
                    name=row.name,
                    amount=row.amount,
                    titration_rate=row.titration_rate,
                    composition={row.element: row.count},
                )
            else:
                reactant = special_reactants[row.id]
                if row.element in reactant.composition:
                    msg = f"encountered duplicate element {row.element} in special reactant {row.id} composition for variable space point {vs_id}"
                    raise EleanorError(msg)
                reactant.composition[row.element] = row.count

    return list(special_reactants.values())


@dataclass
class _SolidSolutionRow:
    id: uuid.UUID
    name: str
    amount: float
    titration_rate: float
    end_member: str
    fraction: float

    def __post_init__(self) -> None:
        guard_is_uuid(self.id, "id")
        guard_is_str(self.name, "name")
        guard_is_float(self.amount, "amount")
        guard_is_float(self.titration_rate, "titration_rate")
        guard_is_str(self.end_member, "end_member")
        guard_is_float(self.fraction, "fraction")


@dataclass
class _SolidSolutionStub:
    name: str
    amount: float
    titration_rate: float
    end_members: dict[str, float]


def get_solid_solution_reactants(conn: psycopg.Connection, vs_id: uuid.UUID) -> list[SolidSolutionReactant]:
    solid_solution_reactants: dict[uuid.UUID, _SolidSolutionStub] = {}
    with conn.cursor(row_factory=class_row(_SolidSolutionRow)) as cur:
        _ = cur.execute(
            """
            SELECT
                id,
                ssr.name AS name,
                log_moles AS amount,
                titration_rate,
                ssrem.name AS end_member,
                fraction
            FROM solid_solution_reactants ssr
            JOIN solid_solution_reactant_end_members ssrem ON ssr.id = ssrem.solid_solution_reactant_id
            WHERE variable_space_id = %s
            """,
            (vs_id,),
        )

        for row in cur:
            if row.id not in solid_solution_reactants:
                solid_solution_reactants[row.id] = _SolidSolutionStub(
                    name=row.name,
                    amount=row.amount,
                    titration_rate=row.titration_rate,
                    end_members={row.end_member: row.fraction},
                )
            else:
                reactant = solid_solution_reactants[row.id]
                if row.end_member in reactant.end_members:
                    msg = f"encountered duplicate end member {row.end_member} in solid solution reactant {row.id} for variable space point {vs_id}"
                    raise EleanorError(msg)
                reactant.end_members[row.end_member] = row.fraction

    return [
        SolidSolutionReactant(
            name=reactant.name,
            amount=reactant.amount,
            titration_rate=reactant.titration_rate,
            end_members=reactant.end_members,
        )
        for reactant in solid_solution_reactants.values()
    ]


@dataclass
class _SuppressionRow:
    id: uuid.UUID
    name: str | None
    type: str | None
    exception: str | None

    def __post_init__(self) -> None:
        guard_is_uuid(self.id, "id")
        guard_is_str_or_none(self.name, "name")
        guard_is_str_or_none(self.type, "type")
        guard_is_str_or_none(self.exception, "exception")


def get_suppressions(conn: psycopg.Connection, vs_id: uuid.UUID) -> list[Suppression]:
    suppressions: dict[uuid.UUID, Suppression] = {}
    with conn.cursor(row_factory=class_row(_SuppressionRow)) as cur:
        _ = cur.execute(
            """
            SELECT
                id,
                s.name,
                type,
                se.name AS exception
            FROM suppressions s
            LEFT JOIN suppression_exceptions se ON s.id = se.suppression_id
            WHERE variable_space_id = %s
            """,
            (vs_id,),
        )
        for row in cur:
            if row.id not in suppressions:
                suppressions[row.id] = Suppression(
                    name=row.name,
                    type=row.type,
                    exceptions=[row.exception] if row.exception is not None else [],
                )
            elif row.exception is not None:
                suppression = suppressions[row.id]
                if row.exception in suppression.exceptions:
                    msg = f"duplicate suppression exception {row.exception} encountered for suppression {row.id} of variable space point {vs_id}"
                    raise EleanorError(msg)
                suppression.exceptions.append(row.exception)
            else:
                msg = f"duplicate suppression {row.id} row encountered for variable space point {vs_id}"
                raise EleanorError(msg)

    for suppression in suppressions.values():
        suppression.exceptions = sorted(suppression.exceptions)

    return list(suppressions.values())


def get_reactants(conn: psycopg.Connection, vs_id: uuid.UUID) -> list[AbstractReactant]:
    reactants: list[AbstractReactant] = []

    for reactant_class in _SIMPLE_REACTANT_TABLES:
        reactants.extend(get_simple_reactants(conn, reactant_class, vs_id))

    reactants.extend(get_fixed_gas_reactants(conn, vs_id))
    reactants.extend(get_special_reactants(conn, vs_id))
    reactants.extend(get_solid_solution_reactants(conn, vs_id))

    return reactants


def get_vs_as_order(config: PostgresDatabaseSettings, vs_id: uuid.UUID) -> Order | None:
    conn = connection.connect(config)

    point = get_point_row(conn, vs_id)
    if point is None:
        return None

    order_id = point.order_id
    order_row = get_order(config, order_id)
    if order_row is None:
        msg = f"failed to find order {order_id} associated with variable space point {vs_id}"
        raise EleanorError(msg)

    creator = require_str(order_row.raw.get("creator"), "order creator")
    notes = require_str(order_row.raw.get("notes"), "order notes").strip()
    notes += ("\n\n" if notes != "" else "") + f"Dumped from order {order_row.id}"
    seed = require_int(order_row.raw.get("seed"), "order seed")

    return Order(
        name=f"{order_row.name}; Point {vs_id}",
        creator=creator,
        tags=order_row.tags,
        notes=notes,
        seed=seed,
        kernel=get_kernel_config(conn, vs_id),
        water_mass=point.water_mass,
        temperature=point.temperature,
        pressure=point.pressure,
        elements=get_elements(conn, vs_id),
        species=get_species(conn, vs_id),
        reactants=get_reactants(conn, vs_id),
        suppressions=get_suppressions(conn, vs_id),
        create_date=point.create_date,
    )
