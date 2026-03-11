from dataclasses import dataclass
from types import SimpleNamespace
from unittest import mock

from sqlalchemy import BLOB, JSON
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.orm import Session

from eleanor.config import DatabaseConfig
from eleanor.exceptions import EleanorException
from eleanor.yeoman import Binary, JSONDict, Yeoman, yeoman_registry

from .common import TestCase


class TestYeoman(TestCase):
    """
    Tests of the eleanor.yeoman module.
    """

    def test_jsondict_load_dialect_impl(self):
        """
        Ensure that :class:`JSONDict` chooses JSONB for postgresql and JSON otherwise.
        """
        typ = JSONDict()

        pg = SimpleNamespace(name='postgresql', type_descriptor=lambda t: ('pg', t))
        other = SimpleNamespace(name='sqlite', type_descriptor=lambda t: ('other', t))

        self.assertEqual(typ.load_dialect_impl(pg), ('pg', JSONB))
        self.assertEqual(typ.load_dialect_impl(other), ('other', JSON))

    def test_jsondict_process_bind_param(self):
        """
        Ensure that :class:`JSONDict` serializes dict/dataclass values and rejects invalid types.
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
        Ensure that :class:`Binary` chooses BYTEA for postgresql and BLOB otherwise.
        """
        typ = Binary()

        pg = SimpleNamespace(name='postgresql', type_descriptor=lambda t: ('pg', t))
        other = SimpleNamespace(name='sqlite', type_descriptor=lambda t: ('other', t))

        self.assertEqual(typ.load_dialect_impl(pg), ('pg', BYTEA))
        self.assertEqual(typ.load_dialect_impl(other), ('other', BLOB))

    def test_yeoman_init(self):
        """
        Ensure that :class:`Yeoman` builds an engine and initializes :class:`Session` with it.
        """
        engine = mock.Mock()
        cfg = DatabaseConfig(database='main', username='alice', password='secret')

        with (
            mock.patch('eleanor.yeoman.create_engine', return_value=engine) as create_engine_mock,
            mock.patch.object(Session, '__init__', return_value=None) as session_init_mock,
        ):
            session = Yeoman(cfg, verbose=True)

        create_engine_mock.assert_called_once_with(str(cfg), echo=True)
        session_init_mock.assert_called_once_with(engine)
        self.assertIs(session.engine, engine)

    def test_yeoman_exit_disposes_engine(self):
        """
        Ensure that :meth:`Yeoman.__exit__` delegates to Session and disposes the engine.
        """
        session = object.__new__(Yeoman)
        session.engine = mock.Mock()

        with mock.patch.object(Session, '__exit__', return_value=None) as session_exit_mock:
            Yeoman.__exit__(session, None, None, None)

        session_exit_mock.assert_called_once_with(None, None, None)
        session.engine.dispose.assert_called_once_with()

    def test_yeoman_setup(self):
        """
        Ensure that :meth:`Yeoman.setup` creates all mapped tables on the session engine.
        """
        session = object.__new__(Yeoman)
        session.engine = mock.Mock()

        with mock.patch.object(yeoman_registry.metadata, 'create_all') as create_all_mock:
            session.setup()

        create_all_mock.assert_called_once_with(session.engine)

    def test_yeoman_write_without_refresh(self):
        """
        Ensure that :meth:`Yeoman.write` adds and commits entities without refreshing by default.
        """
        session = object.__new__(Yeoman)
        entity = object()
        manager = mock.Mock()

        with (
            mock.patch.object(Yeoman, '__enter__', return_value=manager),
            mock.patch.object(Yeoman, '__exit__', return_value=None),
        ):
            session.write(entity, refresh=False)

        manager.add.assert_called_once_with(entity)
        manager.commit.assert_called_once_with()
        manager.refresh.assert_not_called()

    def test_yeoman_write_with_refresh(self):
        """
        Ensure that :meth:`Yeoman.write` refreshes entities when requested.
        """
        session = object.__new__(Yeoman)
        entity = object()
        manager = mock.Mock()

        with (
            mock.patch.object(Yeoman, '__enter__', return_value=manager),
            mock.patch.object(Yeoman, '__exit__', return_value=None),
        ):
            session.write(entity, refresh=True)

        manager.add.assert_called_once_with(entity)
        manager.commit.assert_called_once_with()
        manager.refresh.assert_called_once_with(entity)
