from eleanor.output.postgres.persistence.converters import ScratchEntry
from eleanor.output.postgres.persistence.repositories import get_scratch_entry
from eleanor.output.postgres.settings import PostgresDatabaseSettings


def load_scratch_entry(
    settings: PostgresDatabaseSettings,
    variable_space_id: int,
) -> ScratchEntry | None:
    """Diagnostic helper: fetch a persisted scratch payload by VS-point id.

    Callers wanting raw SQL traces should configure :mod:`logging` for
    the ``psycopg`` logger (or construct :class:`PostgresSink` with
    ``verbose=True``, which raises that logger to ``DEBUG`` for the
    sink's lifetime).
    """
    return get_scratch_entry(settings, variable_space_id)


__all__ = ["load_scratch_entry"]
