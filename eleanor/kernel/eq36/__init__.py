"""The built-in eq36 kernel plugin.

Registration now lives in :mod:`eleanor.kernel` so every import path that
reaches into the kernel package (``eleanor.order`` → ``eleanor.kernel.config``,
``eleanor.eleanor`` → ``eleanor.kernel.registry``, and so on) drives the
``eq36`` entry into the registry without anyone having to pre-import this
subpackage for its side effects.

The concrete :class:`Kernel` and :class:`Settings` classes are re-exported
here for callers that want to talk to eq36 directly (tests, notebooks,
documentation examples). :class:`Kernel` is loaded through :pep:`562`'s
``__getattr__`` hook so that merely importing ``eleanor.kernel.eq36`` does
not pay the cost of its heavy numpy / Fortran / ORM dependencies; they are
only imported when the attribute is actually dereferenced (for example by
:func:`eleanor.kernel._build_eq36` when the CLI asks the registry to build
an eq36 kernel).
"""

from typing import TYPE_CHECKING

from .settings import Settings

__all__ = ["Kernel", "Settings"]

if TYPE_CHECKING:
    from .kernel import Kernel as Kernel


def __getattr__(name: str) -> object:
    if name == "Kernel":
        from .kernel import Kernel  # noqa: PLC0415

        return Kernel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
