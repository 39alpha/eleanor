from eleanor.exceptions import EleanorException
from eleanor.plugin import ConfigurablePluginSpec


def build_eq36_settings(raw: dict[str, object]) -> object:
    """Parse a raw ``kernel.args`` mapping into an eq36 :class:`Settings`."""
    from eleanor.kernel.eq36.settings import Settings

    return Settings.from_dict(raw)


def build_eq36(settings: object) -> object:
    """Construct the eq36 :class:`Kernel` from its typed settings + CLI args."""
    from eleanor.kernel.eq36.kernel import Kernel
    from eleanor.kernel.eq36.settings import Settings

    if not isinstance(settings, Settings):
        msg = f"eq36 kernel requires eq36 Settings, got {type(settings).__name__}"
        raise EleanorException(msg)

    return Kernel()


eq36_spec = ConfigurablePluginSpec(
    parse_settings=build_eq36_settings,
    build=build_eq36,
    plugin_api_version=1,
)


__all__ = [
    "build_eq36_settings",
    "build_eq36",
    "eq36_spec",
]
