from dataclasses import dataclass
from types import SimpleNamespace
from unittest import mock

from sqlalchemy import BLOB, JSON
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.orm import Session

from eleanor.config import DatabaseConfig
from eleanor.exceptions import EleanorException
from eleanor.output.postgres.persistence import repositories
from eleanor.output.postgres.persistence.session import PostgresSession
from eleanor.output.postgres.persistence.types import Binary, JSONDict

from .common import TestCase


class TestPostgresPersistence(TestCase):
    """
    Tests of the sink-owned Postgres persistence modules.
    """

    def test_jsondict_load_dialect_impl(self):
        """
        Ensure JSONDict chooses JSONB for postgresql and JSON otherwise.
        """
        typ = JSONDict()

        pg = SimpleNamespace(name='postgresql', type_descriptor=lambda t: ('pg', t))
        other = SimpleNamespace(name='sqlite', type_descriptor=lambda t: ('other', t))

        self.assertEqual(typ.load_dialect_impl(pg), ('pg', JSONB))
        self.assertEqual(typ.load_dialect_impl(other), ('other', JSON))

    def test_jsondict_process_bind_param(self):
        """
        Ensure JSONDict serializes dict/dataclass values and rejects invalid types.
        """

        @dataclass
        class Sample:
            a: int
            b: str

        typ = JSONDict()

        self.assertIsNone(typ.process_bind_param(None, None))
        self.assertEqual(typ.process_bind_param({'z': 2, 'a': 1}, None), {'a': 1, 'z': 2})
        self.assertEqual(typ.process_bind_param(Sample(a=1, b='x'), None), {'a': 1, 'b': 'x'})

        with self.assertRaises(EleanorException):
            typ.process_bind_param('not-a-dict', None)

    def test_binary_load_dialect_impl(self):
        """
        Ensure Binary chooses BYTEA for postgresql and BLOB otherwise.
        """
        typ = Binary()

        pg = SimpleNamespace(name='postgresql', type_descriptor=lambda t: ('pg', t))
        other = SimpleNamespace(name='sqlite', type_descriptor=lambda t: ('other', t))

        self.assertEqual(typ.load_dialect_impl(pg), ('pg', BYTEA))
        self.assertEqual(typ.load_dialect_impl(other), ('other', BLOB))

    def test_postgres_session_init(self):
        """
        Ensure PostgresSession builds an engine and initializes Session with it.
        """
        engine = mock.Mock()
        cfg = DatabaseConfig(database='main', username='alice', password='secret')

        with (
            mock.patch('eleanor.output.postgres.persistence.session.create_engine', return_value=engine) as create_engine_mock,
            mock.patch.object(Session, '__init__', return_value=None) as session_init_mock,
        ):
            session = PostgresSession(cfg, verbose=True)

        create_engine_mock.assert_called_once_with(str(cfg), echo=True)
        session_init_mock.assert_called_once_with(engine)
        self.assertIs(session.engine, engine)

    def test_postgres_session_init_with_sslmode(self):
        """
        Ensure PostgresSession forwards sslmode via connect_args when configured.
        """
        engine = mock.Mock()
        cfg = DatabaseConfig(database='main', username='alice', password='secret', sslmode='verify-full')

        with (
            mock.patch('eleanor.output.postgres.persistence.session.create_engine', return_value=engine) as create_engine_mock,
            mock.patch.object(Session, '__init__', return_value=None) as session_init_mock,
        ):
            session = PostgresSession(cfg)

        create_engine_mock.assert_called_once_with(
            str(cfg),
            connect_args={'sslmode': 'verify-full'},
            echo=False,
        )
        session_init_mock.assert_called_once_with(engine)
        self.assertIs(session.engine, engine)

    def test_postgres_session_exit_disposes_engine(self):
        """
        Ensure PostgresSession.__exit__ delegates to Session and disposes the engine.
        """
        session = object.__new__(PostgresSession)
        session.engine = mock.Mock()

        with mock.patch.object(Session, '__exit__', return_value=None) as session_exit_mock:
            PostgresSession.__exit__(session, None, None, None)

        session_exit_mock.assert_called_once_with(None, None, None)
        session.engine.dispose.assert_called_once_with()

    def test_setup_schema_creates_all_tables(self):
        """
        Ensure setup_schema calls metadata.create_all against the session engine.
        """
        cfg = DatabaseConfig(database='main', username='alice', password='secret')
        engine = mock.Mock()
        metadata = mock.Mock()
        session = mock.MagicMock()
        session.__enter__.return_value = SimpleNamespace(engine=engine)
        session.__exit__.return_value = None

        with (
            mock.patch('eleanor.output.postgres.persistence.repositories.PostgresSession', return_value=session),
            mock.patch(
                'eleanor.output.postgres.persistence.repositories.postgres_registry',
                new=SimpleNamespace(metadata=metadata),
            ),
        ):
            repositories.setup_schema(cfg, verbose=True)

        metadata.create_all.assert_called_once_with(engine)
