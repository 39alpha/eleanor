import os
from dataclasses import replace
from typing import cast

import pytest
from eleanor.cli.registry import (
    available_cli_commands,
    get_factory,
    register_cli_command,
    registry,
)
from eleanor.exceptions import EleanorError
from eleanor.plugin import OverrideWarning, SimplePluginSpec
from pytest_mock import MockerFixture


@pytest.mark.usefixtures("clean_registry")
def test_register_and_retrieve(spec: SimplePluginSpec) -> None:
    name = "plugin"

    register_cli_command(name, spec)

    assert name in available_cli_commands()
    assert get_factory(name) is spec


@pytest.mark.usefixtures("clean_registry")
def test_unknown_name_raises() -> None:
    name = "nope"
    with pytest.raises(EleanorError, match=f"the {name!r} cli is not supported"):
        _ = get_factory(name)


@pytest.mark.usefixtures("clean_registry")
def test_register_rejects_non_spec_factory() -> None:
    with pytest.raises(EleanorError, match="must be a SimplePluginSpec"):
        register_cli_command("bad", None)  # pyright: ignore[reportArgumentType]


@pytest.mark.usefixtures("clean_registry")
def test_register_rejects_bool_api_version(spec: SimplePluginSpec) -> None:
    spec = replace(spec, plugin_api_version=cast(int, True))
    with pytest.raises(EleanorError, match="plugin_api_version must be an int"):
        register_cli_command("bad_bool", spec)


@pytest.mark.usefixtures("clean_registry")
def test_register_rejects_too_new_api_version(spec: SimplePluginSpec) -> None:
    name = "too_new"
    with pytest.raises(EleanorError, match=f"plugin {name!r} targets cli API"):
        register_cli_command(name, replace(spec, plugin_api_version=99))


@pytest.mark.usefixtures("clean_registry")
def test_register_can_override_max_plugin_version(
    mocker: MockerFixture, spec: SimplePluginSpec
) -> None:
    mocker.patch.dict(os.environ, {registry.override_env_var: "1"})
    with pytest.warns(OverrideWarning, match="loading anyway because"):
        register_cli_command("too_new_override", replace(spec, plugin_api_version=99))
    assert "too_new_override" in available_cli_commands()


@pytest.mark.usefixtures("clean_registry")
def test_register_rejects_builtin_name(spec: SimplePluginSpec) -> None:
    name = "postgres"
    with pytest.raises(EleanorError, match=f"{name!r} is a built-in"):
        register_cli_command(name, spec)
