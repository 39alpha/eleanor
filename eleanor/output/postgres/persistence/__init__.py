"""Persistence layer for the postgres output sink.

The public surface is intentionally narrow. :class:`PostgresSink`
imports :mod:`.connection` and :mod:`.repositories` directly; tests and
the future EQL refit may reach into :mod:`.schema`, :mod:`.converters`,
or :mod:`.queries` as needed. Only the small dataclasses callers want to
type against (:class:`OrderRecord`, :class:`ScratchEntry`) are
re-exported at the package root, and we deliberately do **not**
``from . import repositories`` here -- ``repositories`` imports the
other submodules, which would create an init-time cycle that
basedpyright flags as ``reportImportCycles``.
"""

from .converters import OrderRecord, ScratchEntry

__all__ = [
    "OrderRecord",
    "ScratchEntry",
]
