import os
from typing import override
from unittest import mock

import click

from eleanor.cli.registry import (
    BUILTIN_CLI_COMMANDS,
    OVERRIDE_ENV_VAR,
    CliCommandSpec,
    available_cli_commands,
    get_factory,
    register_cli_commands,
    registry,
)
from eleanor.exceptions import EleanorException
from eleanor.plugin import OverrideWarning

from ..common import TestCase

_ = available_cli_commands()  # trigger builtin_loader to register built-in CLI specs


@click.command("hello")
def _hello() -> None:
    """Smoke command."""


def _spec(*, plugin_api_version: int = 1) -> CliCommandSpec:
    return CliCommandSpec(
        commands=(_hello,),
        plugin_api_version=plugin_api_version,
    )


class _FakeEntryPoint:
    """Lightweight stand-in for :class:`importlib.metadata.EntryPoint`."""

    def __init__(self, name: str, value: str, loader):
        self.name = name
        self.value = value
        self._loader = loader

    def load(self):
        return self._loader()


class _CliRegistryTestCase(TestCase):
    """Base class that snapshots / restores CLI registry state between tests."""

    _saved_entries: dict[str, CliCommandSpec] = {}
    _saved_discovered: bool = False
    _saved_unversioned_warned: set[str] = set()

    @override
    def setUp(self) -> None:
        self._saved_entries = dict(registry._registry)
        self._saved_discovered = registry._discovered
        self._saved_unversioned_warned = set(registry._unversioned_warned)

    @override
    def tearDown(self) -> None:
        registry._registry.clear()
        registry._registry.update(self._saved_entries)
        registry._discovered = self._saved_discovered
        registry._unversioned_warned.clear()
        registry._unversioned_warned.update(self._saved_unversioned_warned)


class TestBuiltinCliPlugins(TestCase):
    def test_postgres_is_registered(self):
        self.assertIn("postgres", BUILTIN_CLI_COMMANDS)
        self.assertIn("postgres", available_cli_commands())


class TestRegisterCliCommands(_CliRegistryTestCase):
    def test_register_and_retrieve(self):
        spec = _spec()
        register_cli_commands("plugin", spec)

        self.assertIn("plugin", available_cli_commands())
        self.assertIs(get_factory("plugin"), spec)

    def test_unknown_name_raises(self):
        with self.assertRaises(EleanorException):
            get_factory("nope")

    def test_register_callable_returning_spec(self):
        spec = _spec()
        register_cli_commands("lazy", lambda: spec)
        self.assertIs(get_factory("lazy"), spec)

    def test_register_rejects_non_spec_factory(self):
        with self.assertRaises(EleanorException):
            register_cli_commands("bad", lambda: None)  # pyright: ignore[reportArgumentType]

    def test_register_rejects_bad_commands_field(self):
        bad_list = CliCommandSpec(commands=[_hello])  # pyright: ignore[reportArgumentType]
        with self.assertRaisesRegex(EleanorException, "commands must be a tuple"):
            register_cli_commands("bad_list", bad_list)

        bad_member = CliCommandSpec(commands=("not-a-command",))  # pyright: ignore[reportArgumentType]
        with self.assertRaisesRegex(EleanorException, "commands must be a tuple"):
            register_cli_commands("bad_member", bad_member)

    def test_register_rejects_bool_api_version(self):
        bad = CliCommandSpec(commands=(_hello,), plugin_api_version=True)
        with self.assertRaisesRegex(EleanorException, "plugin_api_version must be int"):
            register_cli_commands("bad_bool", bad)

    def test_register_rejects_too_new_api_version(self):
        with self.assertRaises(EleanorException):
            register_cli_commands("too_new", _spec(plugin_api_version=99))

        with mock.patch.dict(os.environ, {OVERRIDE_ENV_VAR: "1"}):
            with self.assertWarnsRegex(OverrideWarning, "loading anyway because"):
                register_cli_commands("too_new_override", _spec(plugin_api_version=99))
        self.assertIn("too_new_override", available_cli_commands())

    def test_register_rejects_builtin_override_without_env(self):
        original = registry._registry["postgres"]
        replacement = _spec()

        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop(OVERRIDE_ENV_VAR, None)
            with self.assertWarnsRegex(RuntimeWarning, "refusing to override built-in"):
                register_cli_commands("postgres", replacement)

        self.assertIs(registry._registry["postgres"], original)

    def test_register_allows_builtin_override_with_env(self):
        original = registry._registry["postgres"]
        replacement = _spec()
        try:
            with mock.patch.dict(os.environ, {OVERRIDE_ENV_VAR: "1"}):
                register_cli_commands("postgres", replacement)
            self.assertIs(registry._registry["postgres"], replacement)
        finally:
            registry._registry["postgres"] = original


class TestEntryPointDiscovery(_CliRegistryTestCase):
    @override
    def setUp(self) -> None:
        super().setUp()
        registry._discovered = False

    def test_discovery_registers_entry_points(self):
        spec = _spec()
        ep = _FakeEntryPoint("plugin", "pkg.mod:build_cli", lambda: spec)

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            plugins = available_cli_commands()

        self.assertIn("plugin", plugins)
        self.assertIs(get_factory("plugin"), spec)

    def test_discovery_warns_and_continues_on_load_failure(self):
        good_spec = _spec()

        def _fail():
            raise ImportError("boom")

        failing_ep = _FakeEntryPoint("broken", "pkg.bad:build", _fail)
        working_ep = _FakeEntryPoint("working", "pkg.ok:build", lambda: good_spec)

        with mock.patch("eleanor.plugin.entry_points", return_value=[failing_ep, working_ep]):
            with self.assertWarnsRegex(RuntimeWarning, 'failed to load cli entry point "broken"'):
                plugins = available_cli_commands()

        self.assertNotIn("broken", plugins)
        self.assertIn("working", plugins)

    def test_discovery_rejects_non_spec_entry_point(self):
        bad_ep = _FakeEntryPoint("bad", "pkg.bad:NOT_A_SPEC", lambda: 42)

        with mock.patch("eleanor.plugin.entry_points", return_value=[bad_ep]):
            with self.assertWarnsRegex(RuntimeWarning, "is invalid"):
                plugins = available_cli_commands()

        self.assertNotIn("bad", plugins)

    def test_discovery_skips_too_new_api_plugin_with_warning(self):
        spec = _spec(plugin_api_version=99)
        ep = _FakeEntryPoint("too_new", "pkg:spec", lambda: spec)

        with mock.patch("eleanor.plugin.entry_points", return_value=[ep]):
            with self.assertWarnsRegex(RuntimeWarning, 'cli entry point "too_new"'):
                plugins = available_cli_commands()

        self.assertNotIn("too_new", plugins)
