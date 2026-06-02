from dataclasses import dataclass

import pytest
from pytest_mock import MockerFixture

from eleanor.config.kernel import KernelConfig
from eleanor.exceptions import EleanorException
from eleanor.kernel.registry import registry
from eleanor.kernel.settings import KernelSettings
from eleanor.parameters import Parameter


def test_can_construct_kernel_config() -> None:
    kind = "plugin"
    settings = KernelSettings()

    config = KernelConfig(kind=kind, settings=settings)

    assert config.kind == kind
    assert config.settings is settings


def test_kernel_config_requires_string_kind() -> None:
    with pytest.raises(EleanorException, match="must be a string"):
        _ = KernelConfig(kind=123, settings=KernelSettings())  # pyright: ignore[reportArgumentType]


def test_kernel_config_requires_settings_like_settings() -> None:
    with pytest.raises(EleanorException, match=f"requires {KernelSettings.__name__}"):
        _ = KernelConfig(kind="plugin", settings=5)  # pyright: ignore[reportArgumentType]


def test_kernel_config_propagates_settings_parameters(mocker: MockerFixture) -> None:
    config = KernelConfig(kind="plugin", settings=KernelSettings())
    assert config.parameters() == []

    parameters = [Parameter.load(123)]
    settings = mocker.MagicMock(spec=KernelSettings)
    settings.parameters.return_value = parameters
    config = KernelConfig(kind="plugin", settings=settings)

    assert config.parameters() == parameters


def test_kernel_config_from_dict_raises_for_non_string_kind() -> None:
    with pytest.raises(EleanorException, match="must be a string"):
        _ = KernelConfig.from_dict({"kind": 123})


def test_kernel_config_from_dict_requires_kind() -> None:
    with pytest.raises(EleanorException, match="must be a string"):
        _ = KernelConfig.from_dict({})


def test_kernel_settings_are_propagated(mocker: MockerFixture) -> None:
    @dataclass(kw_only=True)
    class Settings(KernelSettings):
        value: int

    kind = "other"
    settings_raw = {"value": 5}
    settings = Settings(value=5)

    load_plugin_settings = mocker.patch("eleanor.config.kernel.load_plugin_settings", return_value=settings)

    config = KernelConfig.from_dict({"kind": kind, **settings_raw})

    load_plugin_settings.assert_called_once_with(registry, KernelSettings, kind, {"value": 5})
    assert config == KernelConfig(kind=kind, settings=settings)
