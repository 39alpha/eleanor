"""Flat vs nested plugin-settings parsing, shared by every plugin config.

Authoring files write settings inline (``{kind, <setting>...}``); ``asdict``
re-emits them nested (``{kind, settings: {...}}``). Both must parse, and mixing
the two must be rejected.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from eleanor.config.constraint import ConstraintConfig
from eleanor.config.executor import ExecutorConfig
from eleanor.config.kernel import KernelConfig
from eleanor.config.navigator import NavigatorConfig
from eleanor.config.output import OutputSinkConfig
from eleanor.exceptions import EleanorError
from eleanor.executor.settings import ExecutorSettings
from eleanor.kernel.settings import KernelSettings
from eleanor.navigator.settings import NavigatorSettings
from eleanor.output.settings import OutputSinkSettings
from pytest_mock import MockerFixture


@dataclass(frozen=True)
class Case:
    config: Any
    settings_type: Any
    target: str
    kind: str
    kind_required: bool
    extra: dict[str, object]

    @property
    def id(self) -> str:
        return str(self.config.__name__)


CASES = [
    Case(KernelConfig, KernelSettings, "eleanor.config.kernel.load_plugin_settings", "eq36", True, {}),
    Case(NavigatorConfig, NavigatorSettings, "eleanor.config.navigator.load_plugin_settings", "random", False, {}),
    Case(
        ExecutorConfig,
        ExecutorSettings,
        "eleanor.config.executor.load_plugin_settings",
        "multiprocessing",
        False,
        {},
    ),
    Case(
        OutputSinkConfig,
        OutputSinkSettings,
        "eleanor.config.output.load_plugin_settings",
        "csv",
        True,
        {"name": "sink"},
    ),
]

_IDS = [c.id for c in CASES]


def _patch(mocker: MockerFixture, case: Case):
    return mocker.patch(case.target, return_value=case.settings_type())


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_flat_and_nested_settings_reach_the_plugin_identically(mocker: MockerFixture, case: Case) -> None:
    flat = _patch(mocker, case)
    _ = case.config.from_dict({"kind": case.kind, **case.extra, "value": 5})
    flat_settings = flat.call_args.args[-1]

    nested = _patch(mocker, case)
    _ = case.config.from_dict({"kind": case.kind, **case.extra, "settings": {"value": 5}})
    nested_settings = nested.call_args.args[-1]

    assert flat_settings == {"value": 5}
    assert nested_settings == flat_settings


@pytest.mark.parametrize("case", CASES, ids=_IDS)
def test_mixing_flat_and_nested_settings_is_rejected(mocker: MockerFixture, case: Case) -> None:
    _ = _patch(mocker, case)

    with pytest.raises(EleanorError, match="cannot mix flat and nested settings"):
        _ = case.config.from_dict({"kind": case.kind, **case.extra, "settings": {"value": 5}, "stray": 1})


@pytest.mark.parametrize("case", [c for c in CASES if not c.kind_required], ids=lambda c: c.id)
def test_nested_settings_parse_without_an_explicit_kind(mocker: MockerFixture, case: Case) -> None:
    """``kind`` is optional for these, so requiring it alongside ``settings`` would be wrong."""
    patched = _patch(mocker, case)

    _ = case.config.from_dict({"settings": {"value": 5}})

    assert patched.call_args.args[-1] == {"value": 5}


def test_nested_output_settings_parse_without_an_explicit_name(mocker: MockerFixture) -> None:
    """``name`` defaults to ``kind``, so it must not be mandatory in the nested form."""
    patched = mocker.patch("eleanor.config.output.load_plugin_settings", return_value=OutputSinkSettings())

    config = OutputSinkConfig.from_dict({"kind": "csv", "settings": {"value": 5}})

    assert patched.call_args.args[-1] == {"value": 5}
    assert config.name == "csv"


def test_constraint_args_accept_the_flat_form() -> None:
    config = ConstraintConfig.from_dict({"kind": "linear", "x": 1})

    assert (config.kind, config.args) == ("linear", {"x": 1})


def test_constraint_args_accept_the_nested_form() -> None:
    config = ConstraintConfig.from_dict({"kind": "linear", "args": {"x": 1}})

    assert (config.kind, config.args) == ("linear", {"x": 1})


def test_constraint_rejects_mixed_flat_and_nested_args() -> None:
    with pytest.raises(EleanorError, match="cannot mix flat and nested args"):
        _ = ConstraintConfig.from_dict({"kind": "linear", "args": {"x": 1}, "stray": 2})
