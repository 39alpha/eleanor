"""Built-in kernel factories used by entry-point discovery."""

from eleanor.exceptions import EleanorException

from .registry import KernelSpec


def build_eq36_settings(raw: dict[str, object]) -> object:
    """Parse a raw ``kernel.args`` mapping into an eq36 :class:`Settings`."""
    from .eq36.settings import Settings

    return Settings.from_dict(raw)


def build_eq36(settings: object, *args: object) -> object:
    """Construct the eq36 :class:`Kernel` from its typed settings + CLI args."""
    from .eq36.kernel import Kernel
    from .eq36.settings import Settings

    if not isinstance(settings, Settings):
        raise EleanorException(
            f"eq36 kernel requires eq36 Settings, got {type(settings).__name__}",
        )
    if not args:
        raise EleanorException("eq36 kernel requires a data1_dir argument")
    data1_dir, *rest = args
    if not isinstance(data1_dir, str):
        raise EleanorException(
            f"eq36 kernel requires a string data1_dir, got {type(data1_dir).__name__}",
        )
    # ``rest`` contains any additional positional arguments supplied by the
    # caller (e.g. extra CLI arguments passed via ``Eleanor.kernel_args``).
    # They are forwarded to ``Kernel.__init__`` unvalidated; ``Kernel`` is
    # responsible for rejecting unexpected arguments.
    return Kernel(settings, data1_dir, *rest)


eq36_spec = KernelSpec(
    settings_from_dict=build_eq36_settings,
    build=build_eq36,
    plugin_api_version=1,
)
