from ....connection import DatabaseConfig
from ..persistence.repositories import ScratchEntry, get_scratch_entry


def load_scratch_entry(config: DatabaseConfig, variable_space_id: int, verbose: bool = False) -> ScratchEntry | None:
    return get_scratch_entry(config, variable_space_id, verbose=verbose)
