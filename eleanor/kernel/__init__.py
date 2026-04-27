"""Public surface of the ``eleanor.kernel`` extension point.

The registry API (:func:`available_kernels`, :func:`get_factory`,
:func:`register_kernel`) is re-exported from :mod:`eleanor.kernel.registry`.

Built-in kernel factories are defined and registered **here**, in the parent
package, so registration is triggered by any import that reaches into
``eleanor.kernel`` (every CLI entry point already does, transitively through
``eleanor.order``, ``eleanor.eleanor``, etc.). This matches the pattern used
by :mod:`eleanor.executor` and :mod:`eleanor.output` and replaces the older
arrangement that relied on some unrelated module pre-importing
``eleanor.kernel.eq36`` for its registration side effect.

The heavy dependencies of each built-in (for example eq36's numpy / Fortran
/ ORM imports) are deferred inside the factory bodies, so merely touching
:mod:`eleanor.kernel` does not drag them in.
"""

from eleanor.exceptions import EleanorException

from .registry import KernelSpec, register_kernel


def _build_eq36_settings(raw: dict[str, object]) -> object:
    """Parse a raw ``kernel.args`` mapping into an eq36 :class:`Settings`.

    Imported lazily so :mod:`eleanor.kernel` can register the ``eq36`` factory
    without eagerly pulling in ``eleanor.kernel.eq36``'s heavy transitive
    dependencies.
    """
    from .eq36.settings import Settings  # noqa: PLC0415

    return Settings.from_dict(raw)


def _build_eq36(settings: object, *args: object) -> object:
    """Construct the eq36 :class:`Kernel` from its typed settings + CLI args.

    Deferred eq36 imports mirror :func:`_build_eq36_settings`; invoking the
    factory is what pays for the subpackage's transitive imports (numpy,
    the Fortran data1 loader, constraint helpers, etc.).
    """
    from .eq36.kernel import Kernel  # noqa: PLC0415
    from .eq36.settings import Settings  # noqa: PLC0415

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


register_kernel(
    "eq36",
    KernelSpec(settings_from_dict=_build_eq36_settings, build=_build_eq36),
)
