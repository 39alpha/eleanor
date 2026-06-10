import pytest
from eleanor.config.plugin import PluginConfig
from eleanor.exceptions import EleanorError
from eleanor.parameters import Parameter
from eleanor.settings import Settings, SettingsLike
from pytest_mock import MockerFixture


def test_can_construct_plugin_config() -> None:
    kind = "plugin"
    settings = Settings()

    config = PluginConfig(kind=kind, settings=settings)

    assert config.kind == kind
    assert config.settings is settings


def test_plugin_config_requires_string_kind() -> None:
    with pytest.raises(EleanorError, match="must be a string"):
        _ = PluginConfig(kind=123, settings=Settings())  # pyright: ignore[reportArgumentType]


def test_plugin_config_requires_settings_like_settings() -> None:
    with pytest.raises(EleanorError, match="must implement SettingsLike"):
        _ = PluginConfig(kind="plugin", settings=5)  # pyright: ignore[reportArgumentType]


def test_plugin_config_is_settings_like() -> None:
    config = PluginConfig(kind="plugin", settings=Settings())

    assert isinstance(config, SettingsLike)


def test_plugin_config_propagates_settings_parameters(mocker: MockerFixture) -> None:
    config = PluginConfig(kind="plugin", settings=Settings())
    assert config.parameters() == []

    parameters = [Parameter.load(123)]
    settings = mocker.MagicMock(spec=Settings)
    settings.parameters.return_value = parameters
    config = PluginConfig(kind="plugin", settings=settings)

    assert config.parameters() == parameters
