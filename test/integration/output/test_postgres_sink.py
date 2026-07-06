"""Real-Postgres integration tests for the rewritten output sink.

These tests are *gated* on the ``ELEANOR_TEST_DATABASE_URL`` environment
variable. When the variable is unset (the default for local dev), every
test in this file skips with a clear message. CI lanes that want
wire-level coverage should provision a Postgres instance and export
``ELEANOR_TEST_DATABASE_URL=postgresql://user:pass@host:port/dbname``
(only the credentials are read; the URL is parsed on each test).

Each test starts from a freshly-recreated ``public`` schema so cross-test
contamination cannot mask correctness regressions. The fixture also
clears the persistence layer's process-local connection cache between
tests so each test exercises the lazy-open path in :func:`connect`.

Layered coverage:

* :class:`TestPostgresSinkIntegration` -- schema and order round-trip.
* :class:`TestRepositoriesIntegration` -- the persistence hot path:
  ``insert_point`` round-trips, the chunked RETURNING-id branch in
  ``_bulk_insert_returning_ids``, and the binary-COPY route in
  ``_bulk_insert``.
* :class:`TestPostgresSinkWriteBatchIntegration` -- end-to-end through
  :class:`PostgresSink.write_batch`, including per-VS-point savepoint
  isolation against an actual constraint violation.
* :class:`TestStatementProfilerIntegration` -- a real-PG smoke for
  :class:`StatementProfiler` confirming both INSERT and COPY traffic
  surfaces in the report.
"""

import os
import unittest
import unittest.mock as mock
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import cast, override

import eleanor.equilibrium_space as core_es
from eleanor.exceptions import EleanorError
from eleanor.output import ErrorInfo
import eleanor.variable_space as core_vs
import numpy as np
import psycopg
from eleanor.config.kernel import KernelConfig
from eleanor.kernel.exceptions import EleanorKernelError
from eleanor.kernel.settings import KernelSettings
from eleanor.order import Order
from eleanor.output.interface import ComputeResult
from eleanor.output.postgres.persistence import connection, repositories, schema
from eleanor.output.postgres.persistence.converters import OrderRecord
from eleanor.output.postgres.settings import (
    PostgresDatabaseSettings,
    PostgresSinkSettings,
)
from eleanor.output.postgres.sink import PostgresSink
from eleanor.output.postgres.tools.profile import StatementProfiler
from psycopg import sql

_DATABASE_URL_ENV = "ELEANOR_TEST_DATABASE_URL"


def _config_from_env() -> PostgresDatabaseSettings | None:
    """Parse a libpq URL from the env var into a :class:`PostgresDatabaseSettings`.

    Returns ``None`` when the env var is unset so callers can skip with
    a single ``unittest.skipUnless`` decorator.
    """
    url = os.environ.get(_DATABASE_URL_ENV)
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    return PostgresDatabaseSettings(
        host=parsed.hostname,
        port=parsed.port,
        database=(parsed.path or "/").lstrip("/") or None,
        username=parsed.username,
        password=parsed.password,
    )


@dataclass(init=False)
class _MinimalOrder:
    """Stripped-down stand-in for ``Order`` carrying the fields the persistence layer reads.

    The full :class:`eleanor.order.Order` constructor parses YAML/TOML/JSON
    raw config; we don't need that machinery here, just the attributes
    :func:`converters.order_to_row` consults.
    """

    def __init__(self, name: str, eleanor_version: str) -> None:
        self.id: int | None = None
        self.name: str | None = name
        self.tags: list[str] = []
        self.eleanor_version: str | None = eleanor_version
        self.raw: dict[str, object] = {"name": name}
        self.create_date: datetime = datetime.now()


def _as_order(order: _MinimalOrder) -> Order:
    return cast(Order, cast(object, order))


def _make_kernel() -> KernelConfig:
    """Return a minimal :class:`KernelConfig` valid for the kernel converter.

    The converter only reads ``kernel.type`` and the ``asdict``-able
    payload from ``kernel.resolved_settings()``. The base
    :class:`KernelSettings` has a single ``timeout`` field and is enough
    to round-trip through JSONB without pulling in the eq36 plugin.
    """
    return KernelConfig(kind="test-kernel", settings=KernelSettings(timeout=None))


_DEFAULT_WATER_MASS: np.float64 = np.float64(1.0)


def _make_vs_point(*, water_mass: np.float64 = _DEFAULT_WATER_MASS) -> core_vs.Point:
    """Return a :class:`core_vs.Point` with empty side-collections by default.

    Tests overlay specific child collections (``elements``, ``species``,
    ``suppressions``, ``solid_solution_reactants``, etc.) on top of this
    skeleton so each test stays focused on the behaviour it's asserting.
    """
    now = datetime.now()
    return core_vs.Point(
        kernel=_make_kernel(),
        water_mass=water_mass,
        temperature=np.float64(25.0),
        pressure=np.float64(1.0),
        elements=[],
        species=[],
        suppressions=[],
        mineral_reactants=[],
        aqueous_reactants=[],
        gas_reactants=[],
        element_reactants=[],
        special_reactants=[],
        fixed_gas_reactants=[],
        solid_solution_reactants=[],
        es_points=[],
        exit_code=0,
        create_date=now,
        start_date=now,
        complete_date=now,
    )


def _make_es_point(
    *,
    elements: list[core_es.Element] | None = None,
    aqueous_species: list[core_es.AqueousSpecies] | None = None,
    pure_solids: list[core_es.PureSolid] | None = None,
    solid_solutions: list[core_es.SolidSolution] | None = None,
    gases: list[core_es.Gas] | None = None,
    redox_reactions: list[core_es.RedoxReaction] | None = None,
    reactants: list[core_es.Reactant] | None = None,
) -> core_es.Point:
    """Return a :class:`core_es.Point` with the ES leaf collections populated."""
    now = datetime.now()
    return core_es.Point(
        stage="eq3",
        temperature=np.float64(25.0),
        pressure=np.float64(1.0),
        ph=np.float64(7.0),
        log_fo2=-np.float64(60.0),
        eh=np.float64(0.1),
        log_activity_water=-np.float64(0.01),
        log_ionic_strength=-np.float64(2.0),
        solute_mass=np.float64(0.1),
        solvent_mass=np.float64(1.0),
        solution_mass=np.float64(1.1),
        tds=np.float64(100.0),
        elements=elements or [],
        aqueous_species=aqueous_species or [],
        pure_solids=pure_solids or [],
        solid_solutions=solid_solutions or [],
        gases=gases or [],
        redox_reactions=redox_reactions or [],
        reactants=reactants or [],
        start_date=now,
        complete_date=now,
        custom_properties={
            "mole_fraction_water": np.float64(0.98),
            "log_gamma_water": np.float64(0.02),
            "pe": np.float64(4.0),
            "Ah": np.float64(1.2),
            "log_stoichiometric_ionic_strength": -np.float64(1.8),
            "ionic_asymmetry": np.float64(0.006),
            "stoichiometric_ionic_asymmetry": np.float64(0.007),
            "osmotic_coefficient": np.float64(0.8),
            "stoichiometric_osmotic_coefficient": np.float64(0.81),
            "log_sum_molalities": -np.float64(1.0),
            "log_sum_stoichiometric_molalities": -np.float64(0.9),
            "charge_imbalance": np.float64(0.0),
            "solute_fraction": np.float64(0.1),
            "solvent_fraction": np.float64(0.9),
        },
    )


@unittest.skipUnless(
    os.environ.get(_DATABASE_URL_ENV),
    f"set {_DATABASE_URL_ENV}=postgresql://... to run real-PG integration tests",
)
class _RealPostgresTestCase(unittest.TestCase):
    """Common scaffolding: real connection, clean schema per test."""

    config: PostgresDatabaseSettings = cast(
        PostgresDatabaseSettings, cast(object, None)
    )

    @classmethod
    @override
    def setUpClass(cls) -> None:
        cfg = _config_from_env()
        if cfg is None:
            raise unittest.SkipTest(f"{_DATABASE_URL_ENV} not set")
        cls.config = cfg

    @override
    def setUp(self) -> None:
        # Drop and recreate the public schema so each test starts clean.
        # We open a fresh connection for the DROP/CREATE so we never have
        # to reason about a connection that was holding open transactions
        # or dangling savepoints from a previous test.
        connection.close_connection(self.config)
        with psycopg.connect(
            host=self.config.host,
            port=self.config.port,
            dbname=self.config.database,
            user=self.config.username,
            password=self.config.password,
        ) as raw_conn:
            with raw_conn.cursor() as cur:
                _ = cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
                _ = cur.execute("CREATE SCHEMA public")
            raw_conn.commit()
        # Re-establish the persistence-layer cache and emit our DDL.
        schema.ensure_schema(connection.connect(self.config))

    @override
    def tearDown(self) -> None:
        connection.close_connection(self.config)


class TestPostgresSinkIntegration(_RealPostgresTestCase):
    """Schema + order round-trip smoke tests."""

    def test_ensure_schema_is_idempotent(self) -> None:
        """
        Ensure :func:`schema.ensure_schema` succeeds on a fresh DB and is
        safe to call again on the same connection.
        """
        conn = connection.connect(self.config)
        schema.ensure_schema(conn)  # idempotent

        # Spot-check: ``orders`` shows up with the expected primary-key
        # column and one or more secondary indexes via information_schema.
        live = schema.inspect_schema(conn, ("orders",))
        self.assertIn("orders", live)
        cols = {row[0] for row in live["orders"]}
        self.assertIn("id", cols)
        self.assertIn("name", cols)
        self.assertIn("eleanor_version", cols)

    def test_insert_order_round_trip(self) -> None:
        """
        Ensure :func:`repositories.insert_order` writes a row and
        :func:`repositories.get_order` reads it back with matching
        identifying metadata.
        """
        order = _MinimalOrder(name="integration-smoke", eleanor_version="test-0.0.0")
        record: OrderRecord = repositories.insert_order(self.config, _as_order(order))
        self.assertEqual(record.name, "integration-smoke")
        self.assertEqual(record.eleanor_version, "test-0.0.0")

        fetched = repositories.get_order(self.config, record.id)
        self.assertIsNotNone(fetched)
        if fetched is not None:  # narrow for the type checker
            self.assertEqual(fetched.id, record.id)
            self.assertEqual(fetched.name, "integration-smoke")

    def test_apply_pending_migrations_invokes_connect_and_runs_loop(self) -> None:
        """
        Ensure :func:`repositories.apply_pending_migrations` is the public
        entry point that wires :func:`connection.connect` to the migration
        runner. Exercising it end-to-end keeps the sink's ``initialize``
        hook covered against a real DB.
        """
        # ``setUp`` already created all data tables via ``ensure_schema``.
        # The migration runner refuses to auto-stamp a database that has
        # data tables but no tracking — so we pre-stamp to tell it "this
        # schema was already applied via the legacy path." This mirrors
        # the operator workflow documented in PLAN.md "Breaking change".
        conn = connection.connect(self.config)
        with conn.transaction(), conn.cursor() as cur:
            _ = cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations " +
                "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, " +
                "applied_at TIMESTAMPTZ NOT NULL, eleanor_version TEXT NOT NULL)"
            )
            _ = cur.execute(
                "INSERT INTO schema_migrations (version, name, applied_at, eleanor_version) " +
                "VALUES (1, 'initial_schema', NOW(), 'test')," +
                "       (2, 'rename_tag_to_tags', NOW(), 'test')," +
                "       (3, 'indexes', NOW(), 'test')," +
                "       (4, 'add_exception_to_variable_space', NOW(), 'test') ON CONFLICT DO NOTHING"
            )
        # Now apply_pending_migrations should find no pending work and succeed.
        repositories.apply_pending_migrations(self.config)
        live = schema.inspect_schema(connection.connect(self.config), ("orders",))
        self.assertIn("orders", live)

    def test_inspect_schema_defaults_to_every_known_table(self) -> None:
        """
        Ensure :func:`schema.inspect_schema` called with no ``table_names``
        returns the full set of tables :data:`schema.TABLES` declares,
        which matches what the EQL conformance check (future) will rely
        on as the default scope.
        """
        live = schema.inspect_schema(connection.connect(self.config))
        self.assertEqual(
            {t.name for t in schema.TABLES},
            set(live.keys()),
        )


class TestRepositoriesIntegration(_RealPostgresTestCase):
    """Wire-level coverage of the persistence hot path.

    These tests exercise :func:`repositories.insert_point` and the bulk
    helpers it leans on against a live Postgres so the chunked RETURNING
    branch and the binary-COPY branch run end-to-end.
    """

    def _make_order_and_vs(self, name: str) -> tuple[int, psycopg.Connection]:
        """Insert an ``orders`` row and return ``(order_id, connection)``."""
        order = _MinimalOrder(name=name, eleanor_version="test-0.0.0")
        record = repositories.insert_order(self.config, _as_order(order))
        return record.id, connection.connect(self.config)

    def test_insert_point_round_trip_persists_full_subtree(self) -> None:
        """
        Ensure ``insert_point`` lands every collection it owns -- VS-side
        side-tables, the equilibrium_space parent, every ES leaf table,
        and the solid_solutions / end_members fan-out -- inside a single
        savepoint when handed a populated VS point.
        """
        order_id, conn = self._make_order_and_vs("full-subtree")

        point = _make_vs_point()
        point.elements = [
            core_vs.Element(name="Na", log_molality=-np.float64(1.0)),
            core_vs.Element(name="Cl", log_molality=-np.float64(1.0)),
        ]
        point.species = [core_vs.Species(name="H+", value=-np.float64(7.0))]
        point.suppressions = [
            core_vs.Suppression(
                name="graphite",
                type=None,
                exceptions=[core_vs.SuppressionException(name="diamond")],
            ),
        ]
        # Populate every reactant flavour so converter + persistence
        # branches that fan out to child tables (special and
        # solid-solution) plus simple leaf-only reactant tables (mineral,
        # aqueous, gas, element, fixed_gas) all run end-to-end on a real
        # Postgres.
        point.mineral_reactants = [
            core_vs.MineralReactant(
                name="forsterite",
                log_moles=np.float64(0.0),
                titration_rate=np.float64(1.0),
            ),
        ]
        point.aqueous_reactants = [
            core_vs.AqueousReactant(
                name="Na+", log_moles=-np.float64(1.0), titration_rate=np.float64(1.0)
            ),
        ]
        point.gas_reactants = [
            core_vs.GasReactant(
                name="CO2(g)",
                log_moles=-np.float64(3.0),
                titration_rate=np.float64(1.0),
            ),
        ]
        point.element_reactants = [
            core_vs.ElementReactant(
                name="Fe", log_moles=-np.float64(6.0), titration_rate=np.float64(1.0)
            ),
        ]
        point.fixed_gas_reactants = [
            core_vs.FixedGasReactant(
                name="O2(g)", log_moles=-np.float64(2.0), log_fugacity=-np.float64(2.0)
            ),
        ]
        point.special_reactants = [
            core_vs.SpecialReactant(
                name="custom-mineral",
                log_moles=np.float64(0.0),
                titration_rate=np.float64(1.0),
                composition=[
                    core_vs.SpecialReactantComposition(element="Fe", count=1),
                    core_vs.SpecialReactantComposition(element="O", count=2),
                ],
            ),
        ]
        point.solid_solution_reactants = [
            core_vs.SolidSolutionReactant(
                name="ss-reactant-0",
                log_moles=np.float64(0.0),
                titration_rate=np.float64(1.0),
                end_members=[
                    core_vs.SolidSolutionReactantEndMembers(
                        name="em-a", fraction=np.float64(0.5)
                    ),
                    core_vs.SolidSolutionReactantEndMembers(
                        name="em-b", fraction=np.float64(0.5)
                    ),
                ],
            ),
        ]
        # Two ES points so the leaf-pool path runs across more than one
        # parent row -- exercises the ``zip(es_ids, es_points)`` loop.
        point.es_points = [
            _make_es_point(
                elements=[
                    core_es.Element(
                        name="Na",
                        log_molality=-np.float64(1.0),
                        mass_fraction=np.float64(0.5),
                    ),
                ],
                aqueous_species=[
                    core_es.AqueousSpecies(
                        name="Na+",
                        log_molality=-np.float64(1.0),
                        log_activity=-np.float64(1.1),
                        log_gamma=-np.float64(0.1),
                    ),
                ],
                pure_solids=[
                    core_es.PureSolid(
                        name="Halite", log_qk=np.float64(0.0), affinity=np.float64(0.0)
                    ),
                ],
                gases=[core_es.Gas(name="CO2(g)", log_fugacity=-np.float64(3.5))],
                # ES-side reactants are accumulated in the same
                # VS-point-pooled fashion as the other ES leaf tables.
                reactants=[
                    core_es.Reactant(
                        name="forsterite",
                        affinity=np.float64(1.0),
                        relative_rate=np.float64(1.0),
                        log_moles_reacted=-np.float64(2.0),
                        log_moles_remaining=-np.float64(1.0),
                        log_mass_reacted=-np.float64(2.0),
                        log_mass_remaining=-np.float64(1.0),
                    ),
                ],
                redox_reactions=[
                    core_es.RedoxReaction(
                        couple="O2/H2O",
                        eh=np.float64(0.8),
                        pe=np.float64(13.5),
                        log_fo2=-np.float64(60.0),
                        ah=np.float64(1.0),
                    ),
                ],
                solid_solutions=[
                    core_es.SolidSolution(
                        name="ss0",
                        log_qk=np.float64(0.0),
                        affinity=np.float64(0.0),
                        log_moles=np.float64(-np.inf),
                        log_mass=np.float64(-np.inf),
                        log_volume=np.float64(-np.inf),
                        end_members=[
                            core_es.EndMember(
                                name="ss0_em0",
                                log_qk=np.float64(0.0),
                                affinity=np.float64(0.0),
                            ),
                            core_es.EndMember(
                                name="ss0_em1",
                                log_qk=np.float64(0.0),
                                affinity=np.float64(0.0),
                            ),
                        ],
                    ),
                ],
            ),
            _make_es_point(
                elements=[
                    core_es.Element(
                        name="Cl",
                        log_molality=-np.float64(1.0),
                        mass_fraction=np.float64(0.5),
                    )
                ],
                aqueous_species=[
                    core_es.AqueousSpecies(
                        name="Cl-",
                        log_molality=-np.float64(1.0),
                        log_activity=-np.float64(1.1),
                        log_gamma=-np.float64(0.1),
                    ),
                ],
            ),
        ]

        with conn.transaction(savepoint_name="vs_full"):
            vs_id = repositories.insert_point(conn, order_id, point)

        # Verify every parent and leaf table got the expected count.
        with conn.cursor() as cur:
            for table, expected in (
                ("variable_space", 1),
                ("kernel", 1),
                ("elements", 2),
                ("species", 1),
                ("suppressions", 1),
                ("suppression_exceptions", 1),
                ("mineral_reactants", 1),
                ("aqueous_reactants", 1),
                ("gas_reactants", 1),
                ("element_reactants", 1),
                ("fixed_gas_reactants", 1),
                ("special_reactants", 1),
                ("special_reactant_compositions", 2),
                ("solid_solution_reactants", 1),
                ("solid_solution_reactant_end_members", 2),
                ("equilibrium_space", 2),
                ("equilibrium_elements", 2),
                ("equilibrium_aqueous_species", 2),
                ("equilibrium_pure_solids", 1),
                ("equilibrium_gases", 1),
                ("equilibrium_reactants", 1),
                ("equilibrium_redox_reactions", 1),
                ("equilibrium_solid_solutions", 1),
                ("equilibrium_end_members", 2),
            ):
                _ = cur.execute(
                    sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
                )
                row = cur.fetchone()
                assert row is not None
                self.assertEqual(
                    row[0],
                    expected,
                    f"{table} expected {expected} got {row[0]} after insert_point",
                )

            # Spot-check id fanout: every end_member's solid-solution id
            # references a real equilibrium_solid_solutions row.
            _ = cur.execute("""
                SELECT count(*) FROM equilibrium_end_members em
                LEFT JOIN equilibrium_solid_solutions ss
                  ON ss.id = em.equilibrium_solid_solution_id
                WHERE ss.id IS NULL
            """)
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], 0, "orphan end_members detected")

        self.assertGreater(vs_id, 0)

    def test_insert_point_float64_values_round_trip(self) -> None:
        """
        Ensure np.float64 values survive the Postgres write/read round-trip
        across multiple tables and value categories: positive, negative,
        zero, and -Infinity.
        """
        import math

        order_id, conn = self._make_order_and_vs("float64-roundtrip")

        point = _make_vs_point(water_mass=np.float64(0.987654321))
        point.elements = [
            core_vs.Element(name="Na", log_molality=-np.float64(3.456)),
        ]
        point.es_points = [
            _make_es_point(
                elements=[
                    core_es.Element(
                        name="Ca",
                        log_molality=-np.float64(4.567),
                        mass_fraction=np.float64(0.00123),
                    ),
                ],
                aqueous_species=[
                    core_es.AqueousSpecies(
                        name="HCO3-",
                        log_molality=-np.float64(2.345),
                        log_activity=-np.float64(2.456),
                        log_gamma=-np.float64(0.111),
                    ),
                ],
                solid_solutions=[
                    core_es.SolidSolution(
                        name="ss-rt",
                        log_qk=np.float64(0.0),
                        affinity=np.float64(0.0),
                        log_moles=np.float64(-np.inf),
                        log_mass=np.float64(-np.inf),
                        log_volume=np.float64(-np.inf),
                        end_members=[],
                    ),
                ],
            ),
        ]

        with conn.transaction(savepoint_name="vs_rt"):
            vs_id = repositories.insert_point(conn, order_id, point)

        with conn.cursor() as cur:
            # variable_space: positive float, zero implicit in charge_imbalance via _make_es_point
            _ = cur.execute(
                "SELECT water_mass, temperature, pressure FROM variable_space WHERE id = %s",
                (vs_id,),
            )
            vs_row = cur.fetchone()
            assert vs_row is not None
            self.assertEqual(vs_row[0], 0.987654321)
            self.assertEqual(vs_row[1], 25.0)
            self.assertEqual(vs_row[2], 1.0)

            # VS-side elements: negative float
            _ = cur.execute(
                "SELECT log_molality FROM elements WHERE variable_space_id = %s AND name = 'Na'",
                (vs_id,),
            )
            el_row = cur.fetchone()
            assert el_row is not None
            self.assertEqual(el_row[0], -3.456)

            # equilibrium_space: zero (charge_imbalance) and typical scalars
            _ = cur.execute(
                "SELECT temperature, pressure, (custom_properties->>'charge_imbalance')::double precision FROM equilibrium_space WHERE variable_space_id = %s",
                (vs_id,),
            )
            es_row = cur.fetchone()
            assert es_row is not None
            self.assertEqual(es_row[0], 25.0)
            self.assertEqual(es_row[1], 1.0)
            self.assertEqual(es_row[2], 0.0)

            # ES elements: small positive fraction
            _ = cur.execute(
                "SELECT log_molality, mass_fraction FROM equilibrium_elements WHERE name = 'Ca'"
            )
            ee_row = cur.fetchone()
            assert ee_row is not None
            self.assertEqual(ee_row[0], -4.567)
            self.assertEqual(ee_row[1], 0.00123)

            # ES aqueous species: three distinct negative values
            _ = cur.execute(
                "SELECT log_molality, log_activity, log_gamma FROM equilibrium_aqueous_species WHERE name = 'HCO3-'"
            )
            aq_row = cur.fetchone()
            assert aq_row is not None
            self.assertEqual(aq_row[0], -2.345)
            self.assertEqual(aq_row[1], -2.456)
            self.assertEqual(aq_row[2], -0.111)

            # ES solid solutions: -Infinity round-trip
            _ = cur.execute(
                "SELECT log_moles, log_mass, log_volume FROM equilibrium_solid_solutions WHERE name = 'ss-rt'"
            )
            ss_row = cur.fetchone()
            assert ss_row is not None
            self.assertEqual(ss_row[0], -math.inf)
            self.assertEqual(ss_row[1], -math.inf)
            self.assertEqual(ss_row[2], -math.inf)

    def test_insert_point_chunks_solid_solutions_under_low_param_cap(self) -> None:
        """
        Ensure ``_bulk_insert_returning_ids`` chunks the SS fan-out under
        a deliberately-low parameter cap, that all rows land, and that
        ids are returned in input order so end_members fan out correctly.
        """
        order_id, conn = self._make_order_and_vs("chunking")

        n_ss = 80
        point = _make_vs_point()
        point.es_points = [
            _make_es_point(
                solid_solutions=[
                    core_es.SolidSolution(
                        name=f"ss{i}",
                        log_qk=np.float64(i),
                        affinity=np.float64(0.0),
                        log_moles=np.float64(-np.inf),
                        log_mass=np.float64(-np.inf),
                        log_volume=np.float64(-np.inf),
                        end_members=[
                            core_es.EndMember(
                                name=f"ss{i}_em0",
                                log_qk=np.float64(0.0),
                                affinity=np.float64(0.0),
                            ),
                            core_es.EndMember(
                                name=f"ss{i}_em1",
                                log_qk=np.float64(0.0),
                                affinity=np.float64(0.0),
                            ),
                        ],
                    )
                    for i in range(n_ss)
                ],
            ),
        ]

        # equilibrium_solid_solutions has 7 non-identity columns; 7 * 25 = 175
        # bind params per chunk -> 4 chunks for 80 rows. The point is to force
        # multiple ``execute`` calls inside one ``insert_point`` invocation so
        # we exercise the chunk-concatenation code path against real Postgres.
        with (
            mock.patch.object(repositories, "_MAX_BIND_PARAMS_PER_STATEMENT", 175),
            conn.transaction(savepoint_name="vs_chunk"),
        ):
            _ = repositories.insert_point(conn, order_id, point)

        with conn.cursor() as cur:
            _ = cur.execute("SELECT count(*) FROM equilibrium_solid_solutions")
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], n_ss)

            _ = cur.execute("SELECT count(*) FROM equilibrium_end_members")
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], n_ss * 2)

            # Each end_member's name encodes the SS index it belongs to;
            # verify the FK fan-out preserved input order across chunks.
            _ = cur.execute("""
                SELECT em.name, ss.name
                FROM equilibrium_end_members em
                JOIN equilibrium_solid_solutions ss
                  ON ss.id = em.equilibrium_solid_solution_id
            """)
            rows = cur.fetchall()
            self.assertEqual(len(rows), n_ss * 2)
            for em_name, ss_name in rows:  # pyright: ignore[reportAny]
                self.assertTrue(
                    em_name.startswith(f"{ss_name}_em"),  # pyright: ignore[reportAny]
                    f"end_member {em_name!r} bound to wrong solid_solution {ss_name!r}",
                )

    def test_insert_point_routes_large_aqueous_batch_through_copy(self) -> None:
        """
        Ensure ``_bulk_insert`` switches to binary COPY for a leaf batch
        above :data:`_COPY_ROW_THRESHOLD`, that every row lands, and that
        text values round-trip through the binary protocol intact.
        """
        order_id, conn = self._make_order_and_vs("copy-route")

        n_aq = 1500  # exceeds the default _COPY_ROW_THRESHOLD of 1000
        point = _make_vs_point()
        point.es_points = [
            _make_es_point(
                aqueous_species=[
                    core_es.AqueousSpecies(
                        name=f"sp{i}",
                        log_molality=-np.float64(1.0),
                        log_activity=-np.float64(1.1),
                        log_gamma=-np.float64(0.1),
                    )
                    for i in range(n_aq)
                ],
            ),
        ]

        # Wrap ``_bulk_copy`` so we can assert the COPY path was taken
        # (otherwise this test would silently pass on the executemany
        # path and not actually exercise the new helper).
        with mock.patch.object(
            repositories,
            "_bulk_copy",
            wraps=repositories._bulk_copy,  # pyright: ignore[reportPrivateUsage]
        ) as bulk_copy_spy:
            with conn.transaction(savepoint_name="vs_copy"):
                _ = repositories.insert_point(conn, order_id, point)

        # equilibrium_aqueous_species was the only table over the threshold
        # in this test fixture, but the spy might also catch other large
        # leaf inserts -- we just require AT LEAST one COPY happened.
        copied_tables = [call.args[1] for call in bulk_copy_spy.call_args_list]
        self.assertIn("equilibrium_aqueous_species", copied_tables)

        with conn.cursor() as cur:
            _ = cur.execute("SELECT count(*) FROM equilibrium_aqueous_species")
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], n_aq)

            # Confirm the first and last rows survived intact through the
            # binary COPY's text encoding (both the column name list order
            # and the underlying psycopg adapter chain).
            _ = cur.execute(
                'SELECT name FROM equilibrium_aqueous_species ORDER BY name COLLATE "C"'
            )
            names = {r[0] for r in cur.fetchall()}
            self.assertIn("sp0", names)
            self.assertIn(f"sp{n_aq - 1}", names)

    def test_writes_exception_message(self) -> None:
        order_id, conn = self._make_order_and_vs("exceptions")

        msg = "something wicked this way comes"
        code = 19

        # Case 1: No exception
        plain = _make_vs_point()
        with conn.transaction(savepoint_name="exceptions"):
            plain_id = repositories.insert_point(conn, order_id, plain)

        with conn.cursor() as cur:
            _ = cur.execute(
                "SELECT error, exit_code FROM variable_space WHERE id = %s", (plain_id,)
            )
            row = cur.fetchone()
            assert row is not None
            self.assertIsNone(row[0])  # pyright: ignore[reportAny]
            self.assertEqual(row[1], 0)

        # Case 2: Exception on Point only
        plain = _make_vs_point()
        plain.exception = EleanorKernelError(msg, code=code)
        plain.exit_code = plain.exception.code
        with conn.transaction(savepoint_name="exceptions"):
            plain_id = repositories.insert_point(conn, order_id, plain)

        with conn.cursor() as cur:
            _ = cur.execute(
                "SELECT error, exit_code FROM variable_space WHERE id = %s", (plain_id,)
            )
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], msg)
            self.assertEqual(row[1], code)

        # Case 3: Exception on ErrorInfo only
        plain = _make_vs_point()
        plain.exception = EleanorKernelError(msg, code=code)
        plain.exit_code = plain.exception.code
        error = ErrorInfo.from_exception(plain.exception)
        plain.exception = None
        with conn.transaction(savepoint_name="exceptions"):
            plain_id = repositories.insert_point(conn, order_id, plain, error)

        with conn.cursor() as cur:
            _ = cur.execute(
                "SELECT error, exit_code FROM variable_space WHERE id = %s", (plain_id,)
            )
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], msg)
            self.assertEqual(row[1], code)

        # Case 4: Exception on Point wins
        plain = _make_vs_point()
        plain.exception = EleanorKernelError(msg, code=code)
        plain.exit_code = plain.exception.code
        error = ErrorInfo.from_exception(EleanorError("shouldn't match"))
        with conn.transaction(savepoint_name="exceptions"):
            plain_id = repositories.insert_point(conn, order_id, plain, error)

        with conn.cursor() as cur:
            _ = cur.execute(
                "SELECT error, exit_code FROM variable_space WHERE id = %s", (plain_id,)
            )
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], msg)
            self.assertEqual(row[1], code)

    def test_get_scratch_entry_round_trips_zip_payload(self) -> None:
        """
        Ensure ``get_scratch_entry`` reads back the exact bytes a sink
        wrote into the scratch table via ``insert_point``. Distinguishes
        the three documented outcomes: row missing, scratch missing,
        scratch present.
        """
        order_id, conn = self._make_order_and_vs("scratch")

        # Case 1: no variable_space row at all.
        self.assertIsNone(repositories.get_scratch_entry(self.config, 99999))

        # Case 2: variable_space row with no scratch -> LookupError('scratch').
        plain = _make_vs_point()
        with conn.transaction(savepoint_name="vs_no_scratch"):
            plain_id = repositories.insert_point(conn, order_id, plain)
        with self.assertRaisesRegex(LookupError, "scratch"):
            _ = repositories.get_scratch_entry(self.config, plain_id)

        # Case 3: variable_space row with scratch -> ScratchEntry round-trip.
        with_scratch = _make_vs_point()
        with_scratch.scratch = core_vs.Scratch(zip=b"\x00\x01compressed-bytes\xff")
        with_scratch.exit_code = 7
        with conn.transaction(savepoint_name="vs_with_scratch"):
            with_scratch_id = repositories.insert_point(conn, order_id, with_scratch)
        entry = repositories.get_scratch_entry(self.config, with_scratch_id)
        self.assertIsNotNone(entry)
        if entry is not None:
            self.assertEqual(entry.variable_space_id, with_scratch_id)
            self.assertEqual(entry.exit_code, 7)
            self.assertEqual(entry.zip, b"\x00\x01compressed-bytes\xff")


class TestPostgresSinkWriteBatchIntegration(_RealPostgresTestCase):
    """End-to-end coverage of :class:`PostgresSink.write_batch`."""

    def test_write_batch_commits_all_rows_when_every_point_succeeds(self) -> None:
        """
        Ensure a clean batch of two valid VS points commits both rows in
        a single outer transaction and returns ``committed=True``
        outcomes.
        """
        sink = PostgresSink(PostgresSinkSettings(database=self.config))
        order = _MinimalOrder(name="wb-happy", eleanor_version="test-1.0.0")
        order_id = sink.begin_run(_as_order(order))

        point_a = _make_vs_point(water_mass=np.float64(1.0))
        point_b = _make_vs_point(water_mass=np.float64(2.0))
        results = [ComputeResult(point=point_a), ComputeResult(point=point_b)]

        outcomes = sink.write_batch(order_id=order_id, results=results)

        self.assertEqual(len(outcomes), 2)
        for outcome in outcomes:
            self.assertTrue(outcome.committed)

        conn = connection.connect(self.config)
        with conn.cursor() as cur:
            _ = cur.execute(
                "SELECT count(*) FROM variable_space WHERE order_id = %s",
                (order_id,),
            )
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], 2)

    def test_write_batch_isolates_failing_point_via_savepoint_at_wire_level(
        self,
    ) -> None:
        """
        Ensure a real-PG ``NotNullViolation`` on one VS point rolls back
        only that point's savepoint while the surviving point commits in
        the outer transaction. This is the same isolation guarantee the
        unit tests verify, but exercised against an actual constraint
        check rather than a mocked exception.
        """
        sink = PostgresSink(PostgresSinkSettings(database=self.config))
        order = _MinimalOrder(name="wb-savepoint", eleanor_version="test-1.0.0")
        order_id = sink.begin_run(_as_order(order))

        good = _make_vs_point(water_mass=np.float64(1.0))
        bad = _make_vs_point(water_mass=np.float64(2.0))
        # ``variable_space.water_mass`` is NOT NULL -- forcing it to None
        # surfaces a real ``psycopg.errors.NotNullViolation`` from inside
        # ``insert_point``, which the per-VS-point savepoint must catch.
        bad.water_mass = None  # pyright: ignore[reportAttributeAccessIssue]

        results = [ComputeResult(point=good), ComputeResult(point=bad)]
        outcomes = sink.write_batch(order_id=order_id, results=results)

        self.assertEqual(len(outcomes), 2)
        self.assertTrue(outcomes[0].committed)
        self.assertFalse(outcomes[1].committed)
        self.assertIsNotNone(outcomes[1].error_message)

        conn = connection.connect(self.config)
        with conn.cursor() as cur:
            _ = cur.execute(
                "SELECT count(*) FROM variable_space WHERE order_id = %s",
                (order_id,),
            )
            row = cur.fetchone()
            assert row is not None
            # Only the surviving good point committed.
            self.assertEqual(row[0], 1)


class TestStatementProfilerIntegration(_RealPostgresTestCase):
    """Real-PG smoke for :class:`StatementProfiler`.

    Verifies the cursor-factory swap does not break a real psycopg
    workload and that both the multi-row INSERT path and the COPY path
    are bucketed under the per-table counters in the report.
    """

    def test_profiler_counts_inserts_and_copies_during_write_batch(self) -> None:
        """
        Ensure a profiled ``write_batch`` with > 1000 aqueous species per
        ES point shows up in the per-table report with the COPY-driven
        leaf row count, and that no profiler-bucketed statement leaks
        into ``other_statements`` as a literal ``COPY`` keyword.
        """
        sink = PostgresSink(PostgresSinkSettings(database=self.config))
        order = _MinimalOrder(name="profiler-smoke", eleanor_version="test-1.0.0")
        order_id = sink.begin_run(_as_order(order))

        n_aq = 1500
        point = _make_vs_point()
        # A handful of VS-side elements so the small-batch ``executemany``
        # path also runs through the profiled cursor (the COPY threshold
        # is 1000 rows, so a 5-row leaf insert deliberately stays on the
        # ``executemany`` branch and exercises the matching profiler
        # override).
        point.elements = [
            core_vs.Element(name=f"el{i}", log_molality=-np.float64(1.0))
            for i in range(5)
        ]
        point.es_points = [
            _make_es_point(
                aqueous_species=[
                    core_es.AqueousSpecies(
                        name=f"sp{i}",
                        log_molality=-np.float64(1.0),
                        log_activity=-np.float64(1.1),
                        log_gamma=-np.float64(0.1),
                    )
                    for i in range(n_aq)
                ],
            ),
        ]

        with StatementProfiler() as prof:
            outcomes = sink.write_batch(
                order_id=order_id,
                results=[ComputeResult(point=point)],
            )

        self.assertEqual(len(outcomes), 1)
        self.assertTrue(outcomes[0].committed)

        # All three bulk-write paths land in the per-table bucket:
        #  * multi-row INSERT for equilibrium_space (RETURNING-id branch);
        #  * binary-COPY for equilibrium_aqueous_species (large leaf);
        #  * executemany for elements (small leaf below the COPY threshold).
        self.assertIn("equilibrium_space", prof.insert_statements_by_table)
        self.assertIn("equilibrium_aqueous_species", prof.insert_statements_by_table)
        self.assertIn("elements", prof.insert_statements_by_table)
        self.assertEqual(
            prof.insert_rows_by_table["equilibrium_aqueous_species"],
            n_aq,
        )
        self.assertEqual(prof.insert_rows_by_table["elements"], 5)
        # COPY must not also leak into the keyword-only bucket.
        self.assertNotIn("COPY", prof.other_statements)

        # The render should include the new bulk-write section header.
        report = prof.report()
        self.assertIn("Bulk writes (INSERT/COPY)", report)
        self.assertIn("equilibrium_aqueous_species", report)
