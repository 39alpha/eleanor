from typing import TYPE_CHECKING

from eleanor.exceptions import EleanorException
from eleanor.plugin import ConfigurablePluginSpec

if TYPE_CHECKING:
    from eleanor.kernel.eq36.kernel import Eq36Kernel
    from eleanor.kernel.eq36.settings import Eq36Settings


def build_eq36_settings(raw: dict[str, object]) -> Eq36Settings:
    """Parse a raw ``kernel.args`` mapping into an eq36 :class:`Settings`."""
    from eleanor.kernel.eq36.settings import Eq36Settings

    return Eq36Settings.from_dict(raw)


def build_eq36(settings: object) -> Eq36Kernel:
    """Construct the eq36 :class:`Kernel` from its typed settings + CLI args."""
    from eleanor.kernel.eq36.kernel import Eq36Kernel
    from eleanor.kernel.eq36.settings import Eq36Settings

    if not isinstance(settings, Eq36Settings):
        msg = f"eq36 kernel requires eq36 Settings, got {type(settings).__name__}"
        raise EleanorException(msg)

    return Eq36Kernel()


eq36_spec = ConfigurablePluginSpec(
    parse_settings=build_eq36_settings,
    build=build_eq36,
    plugin_api_version=1,
)


__all__ = [
    "build_eq36",
    "build_eq36_settings",
    "eq36_spec",
]
