"""
Registry and discovery for eleanor transformer plugins.

Eleanor ships with no built-in transformers. Third-party transformers
advertise themselves through the ``eleanor.transformers`` entry-point group.

Each registered factory is a callable invoked as ``factory(**args)``, where
``args`` is the ``args`` block from the order file's ``transformers`` entry.
Factories are typed as ``Callable[..., object]`` so this module has no
structural dependency on :mod:`eleanor.transformer`; callers validate the
returned transformer against
:class:`~eleanor.transformer.AbstractTransformer` before use.
"""

from collections.abc import Callable
from typing import TypeAlias

from eleanor.plugin import PluginRegistry

#: Name of the entry-point group inspected on first registry access.
ENTRY_POINT_GROUP = "eleanor.transformers"

#: Environment variable that allows plugin registrations to override built-ins
#: or previously-registered plugins.
OVERRIDE_ENV_VAR = "ELEANOR_TRANSFORMER_OVERRIDES"

#: Factory callable shape. Each registered transformer is invoked with the
#: keyword args from the order file.
TransformerFactory: TypeAlias = Callable[..., object]

#: Canonical names of the transformers shipped inside the eleanor
#: distribution.
BUILTIN_TRANSFORMERS: frozenset[str] = frozenset()

#: The shared :class:`PluginRegistry` instance backing this module's helpers.
registry: PluginRegistry[TransformerFactory] = PluginRegistry(
    kind="transformer",
    entry_point_group=ENTRY_POINT_GROUP,
    override_env_var=OVERRIDE_ENV_VAR,
    builtins={},
    builtin_names=BUILTIN_TRANSFORMERS,
)


def register_transformer(name: str, factory: TransformerFactory) -> None:
    """Register ``factory`` under ``name`` in the transformer registry."""
    registry.register(name, factory)


def available_transformers() -> frozenset[str]:
    """Return the set of currently-registered transformer names."""
    return registry.available()


def get_factory(name: str) -> TransformerFactory:
    """Return the :data:`TransformerFactory` registered under ``name``."""
    return registry.get(name)
