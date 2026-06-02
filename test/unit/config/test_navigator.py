from dataclasses import dataclass

import pytest
from pytest_mock import MockerFixture

from eleanor.config.navigator import NavigatorConfig
from eleanor.exceptions import EleanorException
from eleanor.navigator.registry import registry
from eleanor.navigator.settings import NavigatorSettings
from eleanor.parameters import Parameter


def test_can_construct_navigator_config() -> None:
    kind = "plugin"
    settings = NavigatorSettings()

    config = NavigatorConfig(kind=kind, settings=settings)

    assert config.kind == kind
    assert config.settings is settings


def test_navigator_config_requires_string_kind() -> None:
    with pytest.raises(EleanorException, match="must be a string"):
        _ = NavigatorConfig(kind=123, settings=NavigatorSettings())  # pyright: ignore[reportArgumentType]


def test_navigator_config_requires_settings_like_settings() -> None:
    with pytest.raises(EleanorException, match=f"requires {NavigatorSettings.__name__}"):
        _ = NavigatorConfig(kind="plugin", settings=5)  # pyright: ignore[reportArgumentType]


def test_navigator_config_propagates_settings_parameters(mocker: MockerFixture) -> None:
    config = NavigatorConfig(kind="plugin", settings=NavigatorSettings())
    assert config.parameters() == []

    parameters = [Parameter.load(123)]
    settings = mocker.MagicMock(spec=NavigatorSettings)
    settings.parameters.return_value = parameters
    config = NavigatorConfig(kind="plugin", settings=settings)

    assert config.parameters() == parameters


def test_navigator_config_from_dict_raises_for_non_string_kind() -> None:
    with pytest.raises(EleanorException, match="must be a string"):
        _ = NavigatorConfig.from_dict({"kind": 123})


def test_navigator_config_from_dict_kind_defaults_to_random(mocker: MockerFixture) -> None:
    settings = NavigatorSettings()

    load_plugin_settings = mocker.patch("eleanor.config.navigator.load_plugin_settings", return_value=settings)

    config = NavigatorConfig.from_dict({})

    load_plugin_settings.assert_called_once_with(registry, NavigatorSettings, "random", {})
    assert config == NavigatorConfig(kind="random", settings=settings)


def test_navigator_settings_are_propagated(mocker: MockerFixture) -> None:
    @dataclass(kw_only=True)
    class Settings(NavigatorSettings):
        value: int

    kind = "other"
    settings_raw = {"value": 5}
    settings = Settings(value=5)

    load_plugin_settings = mocker.patch("eleanor.config.navigator.load_plugin_settings", return_value=settings)

    config = NavigatorConfig.from_dict({"kind": kind, **settings_raw})

    load_plugin_settings.assert_called_once_with(registry, NavigatorSettings, kind, {"value": 5})
    assert config == NavigatorConfig(kind=kind, settings=settings)
