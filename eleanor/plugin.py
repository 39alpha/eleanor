import os
import warnings
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Protocol, cast, final

from eleanor.exceptions import EleanorException, EleanorWarning
from eleanor.util import guard_is_int

PLUGIN_API_VERSIONS: dict[str, tuple[int, int]] = {}


class OverrideWarning(EleanorWarning): ...


class SettingsParser(Protocol):
    def __call__(self, raw: dict[str, object]) -> object: ...


class Factory(Protocol):
    def __call__(self, settings: object) -> object: ...


class SimpleFactory(Protocol):
    def __call__(self) -> object: ...


@dataclass(kw_only=True, frozen=True)
class SimplePluginSpec:
    build: SimpleFactory
    plugin_api_version: int = 1


@dataclass(kw_only=True, frozen=True)
class ConfigurablePluginSpec:
    parse_settings: SettingsParser
    build: Factory
    plugin_api_version: int = 1


type PluginSpec = SimplePluginSpec | ConfigurablePluginSpec


def _normalize_kind(kind: str) -> str:
    return kind.strip().lower()


def _overrides_allowed(override_env_var: str) -> bool:
    value = os.environ.get(override_env_var, "").strip().lower()
    return value not in ("", "0", "false", "no", "off")


@final
class PluginRegistry:
    _kind: str
    _entry_point_group: str
    _override_env_var: str
    _registry: dict[str, PluginSpec]
    _builtins: frozenset[str]
    _discovered: bool
    _current_api_version: int
    _min_api_version: int

    def __init__(
        self,
        *,
        kind: str,
        entry_point_group: str | None = None,
        override_env_var: str | None = None,
        builtin_names: frozenset[str] | None = None,
        api_version: int = 1,
        min_api_version: int = 1,
    ) -> None:
        self._kind = _normalize_kind(kind)
        if self._kind == "":
            msg = f"plugin kind {kind!r}: must be a non-empty string after stripping whitespace"
            raise EleanorException(msg)

        if min_api_version > api_version:
            msg = f"{kind!r}: min_api_version v{min_api_version} cannot exceed api_version v{api_version}"
            raise EleanorException(msg)

        self._entry_point_group = entry_point_group if entry_point_group is not None else f"eleanor.{self._kind}s"
        self._override_env_var = (
            override_env_var if override_env_var is not None else f"ELEANOR_{self._kind.upper()}_OVERRIDES"
        )

        self._registry = {}
        self._builtins = builtin_names if builtin_names is not None else frozenset()
        self._discovered = False
        self._current_api_version = api_version
        self._min_api_version = min_api_version

        PLUGIN_API_VERSIONS[self._kind] = (api_version, min_api_version)

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def entry_point_group(self) -> str:
        return self._entry_point_group

    @property
    def override_env_var(self) -> str:
        return self._override_env_var

    @property
    def builtins(self) -> frozenset[str]:
        return self._builtins

    @property
    def current_api_version(self) -> int:
        return self._current_api_version

    @property
    def min_api_version(self) -> int:
        return self._min_api_version

    def is_builtin(self, name: str) -> bool:
        return name in self._builtins

    def available(self) -> frozenset[str]:
        self._discover_entry_points()
        return frozenset(self._registry)

    def get(self, name: str) -> PluginSpec:
        self._discover_entry_points()
        try:
            return self._registry[name]
        except KeyError as e:
            choices = ", ".join(sorted(self._registry))
            msg = f"the {name!r} {self._kind} is not supported; choose one of {choices}"
            raise EleanorException(msg) from e

    def __contains__(self, name: object) -> bool:
        self._discover_entry_points()
        return name in self._registry

    def register(self, name: str, factory: object) -> None:
        if not name:
            msg = f"{self._kind} plugin name must be a non-empty string"
            raise EleanorException(msg)

        if name in self._builtins:
            msg = f"{name!r} is a built-in {self._kind} and cannot be overridden"
            raise EleanorException(msg)

        validated = self._validate(name, factory)

        existing = self._registry.get(name)
        if existing is validated:
            return

        if existing is not None:
            raise EleanorException(f"{self._kind} {name!r} is already registered")

        self._registry[name] = validated

    def _validate(self, name: str, factory: object) -> PluginSpec:
        if not isinstance(factory, (SimplePluginSpec, ConfigurablePluginSpec)):
            msg = f"{self._kind} factory for {name!r} must be a {SimplePluginSpec.__name__} or {ConfigurablePluginSpec.__name__}"
            raise EleanorException(msg)

        declared = factory.plugin_api_version
        guard_is_int(declared, "plugin_api_version")
        if declared > self._current_api_version:
            msg = (
                f"plugin {name!r} targets {self._kind} API v{declared}; "
                + f"this eleanor supports up to v{self._current_api_version}"
            )
        elif declared < self._min_api_version:
            msg = (
                f"plugin {name!r} targets {self._kind} API v{declared}; "
                + f"this eleanor requires v{self._min_api_version}"
            )
        else:
            return factory

        if _overrides_allowed(self._override_env_var):
            warnings.warn(
                msg + f"; loading anyway because {self._override_env_var} is set",
                OverrideWarning,
                stacklevel=3,
            )
            return factory

        raise EleanorException(msg)

    def _discover_entry_points(self) -> None:
        if self._discovered:
            return
        self._discovered = True

        eps = list(entry_points(group=self._entry_point_group))

        seen: dict[str, str] = {}
        for ep in eps:
            if ep.name in seen:
                first = seen[ep.name]
                if ep.name in self._builtins:
                    msg = f"multiple entry points claim built-in {self._kind} name {ep.name!r}: {first!r} and {ep.value!r}"
                    raise EleanorException(msg)

                msg = f"multiple entry points claim {self._kind} name {ep.name!r}: {first!r} and {ep.value!r}"
                raise EleanorException(msg)
            seen[ep.name] = ep.value

        for ep in eps:
            try:
                loaded = cast(object, ep.load())
            except Exception as e:
                msg = f"failed to load {self._kind} entry point {ep.name!r} from {ep.value!r}: {e}"
                raise EleanorException(msg) from e
            if ep.name in self._builtins:
                self._registry[ep.name] = self._validate(ep.name, loaded)
            else:
                self.register(ep.name, loaded)

        unregistered_builtins = self._builtins - set(self._registry.keys())
        if unregistered_builtins:
            msg = f"{self._kind}(s) have no registered entry point: {sorted(unregistered_builtins)}"
            raise EleanorException(msg)


def is_abstract_instantiation_error(exc: TypeError) -> bool:
    return "Can't instantiate abstract class" in str(exc)


def load_plugin_settings[S](
    registry: PluginRegistry,
    settings_type: type[S],
    name: str,
    raw: dict[str, object],
) -> S | None:
    spec = registry.get(name)
    if isinstance(spec, ConfigurablePluginSpec):
        settings = spec.parse_settings(raw)

        if not isinstance(settings, settings_type):
            got = type(settings).__name__
            expected = settings_type.__name__
            msg = f"{registry.kind!r} plugin {name!r} returned settings type {got}, expected {expected}"
            raise EleanorException(msg)

        return settings

    if raw:
        msg = f"{registry.kind!r} plugin {name!r} does not support settings"
        raise EleanorException(msg)

    return None


def load_plugin[T](
    registry: PluginRegistry,
    plugin_type: type[T],
    name: str,
    settings: object = None,
) -> T:
    spec = registry.get(name)
    try:
        plugin = spec.build() if isinstance(spec, SimplePluginSpec) else spec.build(settings)
    except TypeError as e:
        if not is_abstract_instantiation_error(e):
            raise
        msg = f"{registry.kind!r} plugin {name!r} failed to instantiate (API v{spec.plugin_api_version}): {e}"
        raise EleanorException(msg) from e

    if not isinstance(plugin, plugin_type):
        got = type(plugin).__name__
        expected = plugin_type.__name__
        msg = f"{registry.kind!r} plugin {name!r} returned {got}, expected {expected}"
        raise EleanorException(msg)

    return plugin
