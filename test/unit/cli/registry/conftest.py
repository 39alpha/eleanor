# pyright: reportPrivateUsage=false
from collections.abc import Callable
from dataclasses import dataclass

import click
import pytest
from eleanor.cli.registry import registry
from eleanor.plugin import SimplePluginSpec


@pytest.fixture
def spec() -> SimplePluginSpec:
    @click.command("hello")
    def hello() -> None:
        """Smoke command."""

    def build() -> click.Command:
        return hello

    return SimplePluginSpec(build=build, plugin_api_version=1)


@pytest.fixture
def clean_registry():
    saved_registry = dict(registry._registry)
    saved_discovered = registry._discovered
    registry._discovered = False
    yield
    registry._registry.clear()
    registry._registry.update(saved_registry)
    registry._discovered = saved_discovered


@dataclass
class FakeEntryPoint:
    name: str
    value: str
    loader: Callable[[], object]

    def load(self) -> object:
        return self.loader()


@pytest.fixture
def makeEntryPoint() -> Callable[..., object]:
    return FakeEntryPoint
