from ..config import DatabaseConfig
from ..persistence.converters import ScratchEntry
from ..persistence.repositories import get_scratch_entry


def load_scratch_entry(
    config: DatabaseConfig,
    variable_space_id: int,
) -> ScratchEntry | None:
    """Diagnostic helper: fetch a persisted scratch payload by VS-point id.

    Callers wanting raw SQL traces should configure :mod:`logging` for
    the ``psycopg`` logger (or construct :class:`PostgresSink` with
    ``verbose=True``, which raises that logger to ``DEBUG`` for the
    sink's lifetime).
    """
    return get_scratch_entry(config, variable_space_id)
