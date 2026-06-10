from collections.abc import Callable
from dataclasses import replace
from typing import Never

import pytest
from eleanor.cli.registry import available_cli_commands, get_factory
from eleanor.exceptions import EleanorError
from eleanor.plugin import SimplePluginSpec
from pytest_mock import MockerFixture

type Ctor = Callable[..., object]


@pytest.mark.usefixtures("clean_registry")
def test_discovery_registers_entry_points(
    mocker: MockerFixture, makeEntryPoint: Ctor, spec: SimplePluginSpec
) -> None:
    ep = makeEntryPoint("plugin", "pkg.mod:build_cli", lambda: spec)

    _ = mocker.patch("eleanor.plugin.entry_points", return_value=[ep])
    plugins = available_cli_commands()

    assert "plugin" in plugins
    assert get_factory("plugin") is spec


@pytest.mark.usefixtures("clean_registry")
def test_discovery_raises_on_load_failure(
    mocker: MockerFixture, makeEntryPoint: Ctor
) -> None:
    def fail() -> Never:
        raise ImportError("boom")

    failing_ep = makeEntryPoint("broken", "pkg.bad:build", fail)

    _ = mocker.patch("eleanor.plugin.entry_points", return_value=[failing_ep])
    with pytest.raises(
        EleanorError, match="failed to load cli entry point 'broken'"
    ):
        _ = available_cli_commands()


@pytest.mark.usefixtures("clean_registry")
def test_discovery_raises_on_non_spec_entry_point(
    mocker: MockerFixture, makeEntryPoint: Ctor
) -> None:
    bad_ep = makeEntryPoint("bad", "pkg.bad:NOT_A_SPEC", lambda: 42)

    _ = mocker.patch("eleanor.plugin.entry_points", return_value=[bad_ep])
    with pytest.raises(EleanorError, match="must be a SimplePluginSpec"):
        _ = available_cli_commands()


@pytest.mark.usefixtures("clean_registry")
@pytest.mark.parametrize("version", [0, 99])
def test_discovery_raises_on_unsupported_version(
    mocker: MockerFixture,
    makeEntryPoint: Ctor,
    spec: SimplePluginSpec,
    version: int,
) -> None:
    spec = replace(spec, plugin_api_version=version)

    ep = makeEntryPoint("too_new", "pkg:spec", lambda: spec)

    _ = mocker.patch("eleanor.plugin.entry_points", return_value=[ep])
    with pytest.raises(EleanorError, match="targets cli API"):
        _ = available_cli_commands()
