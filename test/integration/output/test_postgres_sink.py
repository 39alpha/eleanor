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
import math
import os
import unittest
import unittest.mock as mock
import urllib.parse
from datetime import datetime

import psycopg

import eleanor.equilibrium_space as core_es
import eleanor.variable_space as core_vs
from eleanor.kernel.config import Config as KernelConfig
from eleanor.kernel.config import Settings as KernelSettings
from eleanor.output.interface import ComputeResult
from eleanor.output.postgres.config import DatabaseConfig
from eleanor.output.postgres.persistence import (
    connection,
    repositories,
    schema,
)
from eleanor.output.postgres.persistence.converters import OrderRecord
from eleanor.output.postgres.sink import PostgresSink
from eleanor.output.postgres.tools.profile import StatementProfiler


_DATABASE_URL_ENV = 'ELEANOR_TEST_DATABASE_URL'


def _config_from_env() -> DatabaseConfig | None:
    """Parse a libpq URL from the env var into a :class:`DatabaseConfig`.

    Returns ``None`` when the env var is unset so callers can skip with
    a single ``unittest.skipUnless`` decorator.
    """
    url = os.environ.get(_DATABASE_URL_ENV)
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    return DatabaseConfig(
        host=parsed.hostname,
        port=parsed.port,
        database=(parsed.path or '/').lstrip('/') or None,
        username=parsed.username,
        password=parsed.password,
    )


class _MinimalOrder:
    """Stripped-down stand-in for ``Order`` carrying the fields the persistence layer reads.

    The full :class:`eleanor.order.Order` constructor parses YAML/TOML/JSON
    raw config; we don't need that machinery here, just the attributes
    :func:`converters.order_to_row` consults.
    """

    def __init__(self, name: str, eleanor_version: str) -> None:
        self.id: int | None = None
        self.name: str | None = name
        self.tag: str = ''
        self.eleanor_version: str | None = eleanor_version
        self.raw: dict[str, object] = {'name': name}
        self.create_date: datetime = datetime.now()


def _make_kernel() -> KernelConfig:
    """Return a minimal :class:`KernelConfig` valid for the kernel converter.

    The converter only reads ``kernel.type`` and the ``asdict``-able
    payload from ``kernel.resolved_settings()``. The base
    :class:`KernelSettings` has a single ``timeout`` field and is enough
    to round-trip through JSONB without pulling in the eq36 plugin.
    """
    return KernelConfig(type='test-kernel', settings=KernelSettings(timeout=None))


def _make_vs_point(*, water_mass: float = 1.0) -> core_vs.Point:
    """Return a :class:`core_vs.Point` with empty side-collections by default.

    Tests overlay specific child collections (``elements``, ``species``,
    ``suppressions``, ``solid_solution_reactants``, etc.) on top of this
    skeleton so each test stays focused on the behaviour it's asserting.
    """
    now = datetime.now()
    return core_vs.Point(
        kernel=_make_kernel(),
        water_mass=water_mass,
        temperature=25.0,
        pressure=1.0,
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
        glass_reactants=[],
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
        stage='eq3',
        temperature=25.0,
        pressure=1.0,
        pH=7.0,
        log_fO2=-60.0,
        log_activity_water=-0.01,
        mole_fraction_water=0.98,
        log_gamma_water=0.02,
        Eh=0.1,
        pe=4.0,
        Ah=1.2,
        log_ionic_strength=-2.0,
        log_stoichiometric_ionic_strength=-1.8,
        log_ionic_asymmetry=-2.2,
        log_stoichiometric_ionic_asymmetry=-2.1,
        osmotic_coefficient=0.8,
        stoichiometric_osmotic_coefficient=0.81,
        log_sum_molalities=-1.0,
        log_sum_stoichiometric_molalities=-0.9,
        charge_imbalance=0.0,
        solute_mass=0.1,
        solvent_mass=1.0,
        solution_mass=1.1,
        tds=100.0,
        solute_fraction=0.1,
        solvent_fraction=0.9,
        elements=elements or [],
        aqueous_species=aqueous_species or [],
        pure_solids=pure_solids or [],
        solid_solutions=solid_solutions or [],
        gases=gases or [],
        redox_reactions=redox_reactions or [],
        reactants=reactants or [],
        start_date=now,
        complete_date=now,
    )


@unittest.skipUnless(
    os.environ.get(_DATABASE_URL_ENV),
    f'set {_DATABASE_URL_ENV}=postgresql://... to run real-PG integration tests',
)
class _RealPostgresTestCase(unittest.TestCase):
    """Common scaffolding: real connection, clean schema per test."""

    config: DatabaseConfig

    @classmethod
    def setUpClass(cls) -> None:
        cfg = _config_from_env()
        if cfg is None:
            raise unittest.SkipTest(f'{_DATABASE_URL_ENV} not set')
        cls.config = cfg

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
                cur.execute('DROP SCHEMA IF EXISTS public CASCADE')
                cur.execute('CREATE SCHEMA public')
            raw_conn.commit()
        # Re-establish the persistence-layer cache and emit our DDL.
        schema.ensure_schema(connection.connect(self.config))

    def tearDown(self) -> None:
        connection.close_connection(self.config)


class TestPostgresSinkIntegration(_RealPostgresTestCase):
    """Schema + order round-trip smoke tests."""

    def test_ensure_schema_is_idempotent(self):
        """
        Ensure :func:`schema.ensure_schema` succeeds on a fresh DB and is
        safe to call again on the same connection.
        """
        conn = connection.connect(self.config)
        schema.ensure_schema(conn)  # idempotent

        # Spot-check: ``orders`` shows up with the expected primary-key
        # column and one or more secondary indexes via information_schema.
        live = schema.inspect_schema(conn, ('orders',))
        self.assertIn('orders', live)
        cols = {row[0] for row in live['orders']}
        self.assertIn('id', cols)
        self.assertIn('name', cols)
        self.assertIn('eleanor_version', cols)

    def test_insert_order_round_trip(self):
        """
        Ensure :func:`repositories.insert_order` writes a row and
        :func:`repositories.get_order` reads it back with matching
        identifying metadata.
        """
        order = _MinimalOrder(name='integration-smoke', eleanor_version='test-0.0.0')
        record: OrderRecord = repositories.insert_order(self.config, order)  # type: ignore[arg-type]
        self.assertEqual(record.name, 'integration-smoke')
        self.assertEqual(record.eleanor_version, 'test-0.0.0')

        fetched = repositories.get_order(self.config, record.id)
        self.assertIsNotNone(fetched)
        if fetched is not None:  # narrow for the type checker
            self.assertEqual(fetched.id, record.id)
            self.assertEqual(fetched.name, 'integration-smoke')

    def test_setup_schema_invokes_connect_and_ensure_schema(self):
        """
        Ensure :func:`repositories.setup_schema` is the public entry
        point that wires :func:`connection.connect` to
        :func:`schema.ensure_schema`. Exercising it end-to-end keeps the
        sink's ``initialize`` hook covered against a real DB.
        """
        # ``setUp`` already created the schema; this re-runs it through
        # the public entry point and asserts a known table is still
        # present afterwards.
        repositories.setup_schema(self.config)
        live = schema.inspect_schema(connection.connect(self.config), ('orders',))
        self.assertIn('orders', live)

    def test_inspect_schema_defaults_to_every_known_table(self):
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
        order = _MinimalOrder(name=name, eleanor_version='test-0.0.0')
        record = repositories.insert_order(self.config, order)  # type: ignore[arg-type]
        return record.id, connection.connect(self.config)

    def test_insert_point_round_trip_persists_full_subtree(self):
        """
        Ensure ``insert_point`` lands every collection it owns -- VS-side
        side-tables, the equilibrium_space parent, every ES leaf table,
        and the solid_solutions / end_members fan-out -- inside a single
        savepoint when handed a populated VS point.
        """
        order_id, conn = self._make_order_and_vs('full-subtree')

        point = _make_vs_point()
        point.elements = [
            core_vs.Element(name='Na', log_molality=-1.0),
            core_vs.Element(name='Cl', log_molality=-1.0),
        ]
        point.species = [core_vs.Species(name='H+', value=-7.0)]
        point.suppressions = [
            core_vs.Suppression(
                name='graphite',
                type=None,
                exceptions=[core_vs.SuppressionException(name='diamond')],
            ),
        ]
        # Populate every reactant flavour so the converter + persistence
        # branches that fan out to their own child tables (special and
        # glass) plus the simple leaf-only reactant tables (mineral,
        # aqueous, gas, element, fixed_gas) all run end-to-end on a real
        # Postgres.
        point.mineral_reactants = [
            core_vs.MineralReactant(name='forsterite', log_moles=0.0, titration_rate=1.0),
        ]
        point.aqueous_reactants = [
            core_vs.AqueousReactant(name='Na+', log_moles=-1.0, titration_rate=1.0),
        ]
        point.gas_reactants = [
            core_vs.GasReactant(name='CO2(g)', log_moles=-3.0, titration_rate=1.0),
        ]
        point.element_reactants = [
            core_vs.ElementReactant(name='Fe', log_moles=-6.0, titration_rate=1.0),
        ]
        point.fixed_gas_reactants = [
            core_vs.FixedGasReactant(name='O2(g)', log_moles=-2.0, log_fugacity=-2.0),
        ]
        point.special_reactants = [
            core_vs.SpecialReactant(
                name='custom-mineral',
                log_moles=0.0,
                titration_rate=1.0,
                composition=[
                    core_vs.SpecialReactantComposition(element='Fe', count=1),
                    core_vs.SpecialReactantComposition(element='O', count=2),
                ],
            ),
        ]
        point.glass_reactants = [
            core_vs.GlassReactant(
                name='basalt-glass',
                log_moles=-1.0,
                titration_rate=1.0,
                oxides=[
                    core_vs.GlassReactantOxide(
                        name='SiO2', fraction=0.5, log_moles=-1.0, titration_rate=1.0,
                        composition=[
                            core_vs.GlassReactantOxideComposition(element='Si', count=1),
                            core_vs.GlassReactantOxideComposition(element='O', count=2),
                        ],
                    ),
                    core_vs.GlassReactantOxide(
                        name='MgO', fraction=0.5, log_moles=-1.0, titration_rate=1.0,
                        composition=[
                            core_vs.GlassReactantOxideComposition(element='Mg', count=1),
                            core_vs.GlassReactantOxideComposition(element='O', count=1),
                        ],
                    ),
                ],
            ),
        ]
        point.solid_solution_reactants = [
            core_vs.SolidSolutionReactant(
                name='ss-reactant-0',
                log_moles=0.0,
                titration_rate=1.0,
                end_members=[
                    core_vs.SolidSolutionReactantEndMembers(name='em-a', fraction=0.5),
                    core_vs.SolidSolutionReactantEndMembers(name='em-b', fraction=0.5),
                ],
            ),
        ]
        # Two ES points so the leaf-pool path runs across more than one
        # parent row -- exercises the ``zip(es_ids, es_points)`` loop.
        point.es_points = [
            _make_es_point(
                elements=[
                    core_es.Element(name='Na', log_molality=-1.0, mass_fraction=0.5),
                ],
                aqueous_species=[
                    core_es.AqueousSpecies(
                        name='Na+', log_molality=-1.0, log_activity=-1.1, log_gamma=-0.1,
                    ),
                ],
                pure_solids=[
                    core_es.PureSolid(name='Halite', log_qk=0.0, affinity=0.0),
                ],
                gases=[core_es.Gas(name='CO2(g)', log_fugacity=-3.5)],
                # ES-side reactants are accumulated in the same
                # VS-point-pooled fashion as the other ES leaf tables.
                reactants=[
                    core_es.Reactant(
                        name='forsterite',
                        affinity=1.0,
                        relative_rate=1.0,
                        log_moles_reacted=-2.0,
                        log_moles_remaining=-1.0,
                        log_mass_reacted=-2.0,
                        log_mass_remaining=-1.0,
                    ),
                ],
                redox_reactions=[
                    core_es.RedoxReaction(
                        couple='O2/H2O', Eh=0.8, pe=13.5, log_fO2=-60.0, Ah=1.0,
                    ),
                ],
                solid_solutions=[
                    core_es.SolidSolution(
                        name='ss0', log_qk=0.0, affinity=0.0,
                        log_moles=-math.inf, log_mass=-math.inf, log_volume=-math.inf,
                        end_members=[
                            core_es.EndMember(name='ss0_em0', log_qk=0.0, affinity=0.0),
                            core_es.EndMember(name='ss0_em1', log_qk=0.0, affinity=0.0),
                        ],
                    ),
                ],
            ),
            _make_es_point(
                elements=[core_es.Element(name='Cl', log_molality=-1.0, mass_fraction=0.5)],
                aqueous_species=[
                    core_es.AqueousSpecies(
                        name='Cl-', log_molality=-1.0, log_activity=-1.1, log_gamma=-0.1,
                    ),
                ],
            ),
        ]

        with conn.transaction(savepoint_name='vs_full'):
            vs_id = repositories.insert_point(conn, order_id, point)

        # Verify every parent and leaf table got the expected count.
        with conn.cursor() as cur:
            for table, expected in (
                ('variable_space', 1),
                ('kernel', 1),
                ('elements', 2),
                ('species', 1),
                ('suppressions', 1),
                ('suppression_exceptions', 1),
                ('mineral_reactants', 1),
                ('aqueous_reactants', 1),
                ('gas_reactants', 1),
                ('element_reactants', 1),
                ('fixed_gas_reactants', 1),
                ('special_reactants', 1),
                ('special_reactant_compositions', 2),
                ('glass_reactants', 1),
                ('glass_reactant_oxides', 2),
                ('glass_reactant_oxide_compositions', 4),
                ('solid_solution_reactants', 1),
                ('solid_solution_reactant_end_members', 2),
                ('equilibrium_space', 2),
                ('equilibrium_elements', 2),
                ('equilibrium_aqueous_species', 2),
                ('equilibrium_pure_solids', 1),
                ('equilibrium_gases', 1),
                ('equilibrium_reactants', 1),
                ('equilibrium_redox_reactions', 1),
                ('equilibrium_solid_solutions', 1),
                ('equilibrium_end_members', 2),
            ):
                cur.execute(f'SELECT count(*) FROM {table}')
                row = cur.fetchone()
                assert row is not None
                self.assertEqual(
                    row[0], expected,
                    f'{table} expected {expected} got {row[0]} after insert_point',
                )

            # Spot-check id fanout: every end_member's solid-solution id
            # references a real equilibrium_solid_solutions row.
            cur.execute("""
                SELECT count(*) FROM equilibrium_end_members em
                LEFT JOIN equilibrium_solid_solutions ss
                  ON ss.id = em.equilibrium_solid_solution_id
                WHERE ss.id IS NULL
            """)
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], 0, 'orphan end_members detected')

        self.assertGreater(vs_id, 0)

    def test_insert_point_chunks_solid_solutions_under_low_param_cap(self):
        """
        Ensure ``_bulk_insert_returning_ids`` chunks the SS fan-out under
        a deliberately-low parameter cap, that all rows land, and that
        ids are returned in input order so end_members fan out correctly.
        """
        order_id, conn = self._make_order_and_vs('chunking')

        n_ss = 80
        point = _make_vs_point()
        point.es_points = [
            _make_es_point(
                solid_solutions=[
                    core_es.SolidSolution(
                        name=f'ss{i}', log_qk=float(i), affinity=0.0,
                        log_moles=-math.inf, log_mass=-math.inf, log_volume=-math.inf,
                        end_members=[
                            core_es.EndMember(name=f'ss{i}_em0', log_qk=0.0, affinity=0.0),
                            core_es.EndMember(name=f'ss{i}_em1', log_qk=0.0, affinity=0.0),
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
            mock.patch.object(repositories, '_MAX_BIND_PARAMS_PER_STATEMENT', 175),
            conn.transaction(savepoint_name='vs_chunk'),
        ):
            _ = repositories.insert_point(conn, order_id, point)

        with conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM equilibrium_solid_solutions')
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], n_ss)

            cur.execute('SELECT count(*) FROM equilibrium_end_members')
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], n_ss * 2)

            # Each end_member's name encodes the SS index it belongs to;
            # verify the FK fan-out preserved input order across chunks.
            cur.execute("""
                SELECT em.name, ss.name
                FROM equilibrium_end_members em
                JOIN equilibrium_solid_solutions ss
                  ON ss.id = em.equilibrium_solid_solution_id
            """)
            rows = cur.fetchall()
            self.assertEqual(len(rows), n_ss * 2)
            for em_name, ss_name in rows:
                self.assertTrue(
                    em_name.startswith(f'{ss_name}_em'),
                    f'end_member {em_name!r} bound to wrong solid_solution {ss_name!r}',
                )

    def test_insert_point_routes_large_aqueous_batch_through_copy(self):
        """
        Ensure ``_bulk_insert`` switches to binary COPY for a leaf batch
        above :data:`_COPY_ROW_THRESHOLD`, that every row lands, and that
        text values round-trip through the binary protocol intact.
        """
        order_id, conn = self._make_order_and_vs('copy-route')

        n_aq = 1500  # exceeds the default _COPY_ROW_THRESHOLD of 1000
        point = _make_vs_point()
        point.es_points = [
            _make_es_point(
                aqueous_species=[
                    core_es.AqueousSpecies(
                        name=f'sp{i}',
                        log_molality=-1.0,
                        log_activity=-1.1,
                        log_gamma=-0.1,
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
            '_bulk_copy',
            wraps=repositories._bulk_copy,  # pyright: ignore[reportPrivateUsage]
        ) as bulk_copy_spy:
            with conn.transaction(savepoint_name='vs_copy'):
                _ = repositories.insert_point(conn, order_id, point)

        # equilibrium_aqueous_species was the only table over the threshold
        # in this test fixture, but the spy might also catch other large
        # leaf inserts -- we just require AT LEAST one COPY happened.
        copied_tables = [call.args[1] for call in bulk_copy_spy.call_args_list]
        self.assertIn('equilibrium_aqueous_species', copied_tables)

        with conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM equilibrium_aqueous_species')
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], n_aq)

            # Confirm the first and last rows survived intact through the
            # binary COPY's text encoding (both the column name list order
            # and the underlying psycopg adapter chain).
            cur.execute(
                'SELECT name FROM equilibrium_aqueous_species ORDER BY name COLLATE "C"'
            )
            names = {r[0] for r in cur.fetchall()}
            self.assertIn('sp0', names)
            self.assertIn(f'sp{n_aq - 1}', names)

    def test_get_scratch_entry_round_trips_zip_payload(self):
        """
        Ensure ``get_scratch_entry`` reads back the exact bytes a sink
        wrote into the scratch table via ``insert_point``. Distinguishes
        the three documented outcomes: row missing, scratch missing,
        scratch present.
        """
        order_id, conn = self._make_order_and_vs('scratch')

        # Case 1: no variable_space row at all.
        self.assertIsNone(repositories.get_scratch_entry(self.config, 99999))

        # Case 2: variable_space row with no scratch -> LookupError('scratch').
        plain = _make_vs_point()
        with conn.transaction(savepoint_name='vs_no_scratch'):
            plain_id = repositories.insert_point(conn, order_id, plain)
        with self.assertRaisesRegex(LookupError, 'scratch'):
            _ = repositories.get_scratch_entry(self.config, plain_id)

        # Case 3: variable_space row with scratch -> ScratchEntry round-trip.
        with_scratch = _make_vs_point()
        with_scratch.scratch = core_vs.Scratch(zip=b'\x00\x01compressed-bytes\xff')
        with_scratch.exit_code = 7
        with conn.transaction(savepoint_name='vs_with_scratch'):
            with_scratch_id = repositories.insert_point(conn, order_id, with_scratch)
        entry = repositories.get_scratch_entry(self.config, with_scratch_id)
        self.assertIsNotNone(entry)
        if entry is not None:
            self.assertEqual(entry.variable_space_id, with_scratch_id)
            self.assertEqual(entry.exit_code, 7)
            self.assertEqual(entry.zip, b'\x00\x01compressed-bytes\xff')


class TestPostgresSinkWriteBatchIntegration(_RealPostgresTestCase):
    """End-to-end coverage of :class:`PostgresSink.write_batch`."""

    def test_write_batch_commits_all_rows_when_every_point_succeeds(self):
        """
        Ensure a clean batch of two valid VS points commits both rows in
        a single outer transaction and returns ``committed=True``
        outcomes.
        """
        sink = PostgresSink(self.config)
        order = _MinimalOrder(name='wb-happy', eleanor_version='test-1.0.0')
        order_id = sink.begin_run(order)  # type: ignore[arg-type]

        point_a = _make_vs_point(water_mass=1.0)
        point_b = _make_vs_point(water_mass=2.0)
        results = [ComputeResult(point=point_a), ComputeResult(point=point_b)]

        outcomes = sink.write_batch(order_id=order_id, results=results)

        self.assertEqual(len(outcomes), 2)
        for outcome in outcomes:
            self.assertTrue(outcome.committed)

        conn = connection.connect(self.config)
        with conn.cursor() as cur:
            cur.execute(
                'SELECT count(*) FROM variable_space WHERE order_id = %s',
                (order_id,),
            )
            row = cur.fetchone()
            assert row is not None
            self.assertEqual(row[0], 2)

    def test_write_batch_isolates_failing_point_via_savepoint_at_wire_level(self):
        """
        Ensure a real-PG ``NotNullViolation`` on one VS point rolls back
        only that point's savepoint while the surviving point commits in
        the outer transaction. This is the same isolation guarantee the
        unit tests verify, but exercised against an actual constraint
        check rather than a mocked exception.
        """
        sink = PostgresSink(self.config)
        order = _MinimalOrder(name='wb-savepoint', eleanor_version='test-1.0.0')
        order_id = sink.begin_run(order)  # type: ignore[arg-type]

        good = _make_vs_point(water_mass=1.0)
        bad = _make_vs_point(water_mass=2.0)
        # ``variable_space.water_mass`` is NOT NULL -- forcing it to None
        # surfaces a real ``psycopg.errors.NotNullViolation`` from inside
        # ``insert_point``, which the per-VS-point savepoint must catch.
        bad.water_mass = None  # type: ignore[assignment]

        results = [ComputeResult(point=good), ComputeResult(point=bad)]
        outcomes = sink.write_batch(order_id=order_id, results=results)

        self.assertEqual(len(outcomes), 2)
        self.assertTrue(outcomes[0].committed)
        self.assertFalse(outcomes[1].committed)
        self.assertIsNotNone(outcomes[1].error_message)

        conn = connection.connect(self.config)
        with conn.cursor() as cur:
            cur.execute(
                'SELECT count(*) FROM variable_space WHERE order_id = %s',
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

    def test_profiler_counts_inserts_and_copies_during_write_batch(self):
        """
        Ensure a profiled ``write_batch`` with > 1000 aqueous species per
        ES point shows up in the per-table report with the COPY-driven
        leaf row count, and that no profiler-bucketed statement leaks
        into ``other_statements`` as a literal ``COPY`` keyword.
        """
        sink = PostgresSink(self.config)
        order = _MinimalOrder(name='profiler-smoke', eleanor_version='test-1.0.0')
        order_id = sink.begin_run(order)  # type: ignore[arg-type]

        n_aq = 1500
        point = _make_vs_point()
        # A handful of VS-side elements so the small-batch ``executemany``
        # path also runs through the profiled cursor (the COPY threshold
        # is 1000 rows, so a 5-row leaf insert deliberately stays on the
        # ``executemany`` branch and exercises the matching profiler
        # override).
        point.elements = [
            core_vs.Element(name=f'el{i}', log_molality=-1.0)
            for i in range(5)
        ]
        point.es_points = [
            _make_es_point(
                aqueous_species=[
                    core_es.AqueousSpecies(
                        name=f'sp{i}',
                        log_molality=-1.0,
                        log_activity=-1.1,
                        log_gamma=-0.1,
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
        self.assertIn('equilibrium_space', prof.insert_statements_by_table)
        self.assertIn('equilibrium_aqueous_species', prof.insert_statements_by_table)
        self.assertIn('elements', prof.insert_statements_by_table)
        self.assertEqual(
            prof.insert_rows_by_table['equilibrium_aqueous_species'], n_aq,
        )
        self.assertEqual(prof.insert_rows_by_table['elements'], 5)
        # COPY must not also leak into the keyword-only bucket.
        self.assertNotIn('COPY', prof.other_statements)

        # The render should include the new bulk-write section header.
        report = prof.report()
        self.assertIn('Bulk writes (INSERT/COPY)', report)
        self.assertIn('equilibrium_aqueous_species', report)
