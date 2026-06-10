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
:func:`eleanor.kernel.factories.build_eq36` when the CLI asks the registry to
build an eq36 kernel).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eleanor.kernel.eq36.kernel import Eq36Kernel
    from eleanor.kernel.eq36.settings import Eq36Settings


def __getattr__(name: str) -> object:
    match name:
        case "Eq36Settings":
            from eleanor.kernel.eq36.settings import Eq36Settings

            return Eq36Settings
        case "Eq36Kernel":
            from eleanor.kernel.eq36.kernel import Eq36Kernel

            return Eq36Kernel
        case _:
            msg = f"module {__name__!r} has no attribute {name!r}"
            raise AttributeError(msg)


__all__ = ["Eq36Kernel", "Eq36Settings"]
