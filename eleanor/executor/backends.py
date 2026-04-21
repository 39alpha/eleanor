"""
Leaf module that exposes the current set of supported executor backend names.

Kept separate from :mod:`eleanor.executor.__init__` so that consumers (such as
:mod:`eleanor.config`) can validate backend names without pulling in the full
executor package — which eagerly imports multiprocessing primitives and the
individual backend implementations.

Third-party plugins can contribute new backend names via the
``eleanor.executors`` entry-point group (see :mod:`eleanor.executor.registry`),
so this set is computed at call time rather than being a module-level constant.

The :data:`SUPPORTED_BACKENDS` attribute is preserved as a backwards-compatible
alias that resolves lazily on first access.
"""
from .registry import available_backends as supported_backends

__all__ = ['supported_backends']


def __getattr__(name: str) -> frozenset[str]:
    # ``SUPPORTED_BACKENDS`` is a deprecated backwards-compatible alias for
    # :func:`supported_backends`.  It is intentionally excluded from
    # ``__all__`` (so star-imports don't pull it in) but kept here via
    # ``__getattr__`` so that ``from eleanor.executor.backends import
    # SUPPORTED_BACKENDS`` continues to work at runtime.
    if name == 'SUPPORTED_BACKENDS':
        return supported_backends()
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
